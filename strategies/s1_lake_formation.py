# =====================================================================
# s1_lake_formation.py (Phase 3 - étape 3.3) - Stratégie S1 : AWS Lake Formation
# Applique la MÊME règle de sécurité, mais imposée par le service :
#   - LIGNES   : filtre country = 'France'
#   - COLONNES : customer_id, balance, estimated_salary, credit_score exclues
# Pour ne pas perturber le reste du compte, on travaille dans une base dédiée
# "lakehouse_lf" dont les tables pointent vers les MÊMES fichiers S3.
# =====================================================================
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boto3
from config import REGION, ACCOUNT, CURATED_BUCKET, DB_CURATED, SCALES
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "benchmark"))
from as_analyst import run as run_as_analyst, analyst_session

DB_LF = "lakehouse_lf"
FILTER = "fr_analyst_filter"
EXCLUDED = ["customer_id", "balance", "estimated_salary", "credit_score"]
ANALYST = f"arn:aws:iam::{ACCOUNT}:role/LakehouseAnalystFR"
ME = boto3.client("sts").get_caller_identity()["Arn"]
IAM_ALL = {"DataLakePrincipalIdentifier": "IAM_ALLOWED_PRINCIPALS"}

lf = boto3.client("lakeformation", region_name=REGION)
glue = boto3.client("glue", region_name=REGION)


def step(msg):
    print(f"\n>> {msg}")


def safe(fn, **kw):
    """Exécute un appel AWS en ignorant 'existe déjà / absent' (script relançable)."""
    try:
        fn(**kw)
        return "OK"
    except Exception as e:
        name = type(e).__name__
        if any(k in name for k in ("AlreadyExists", "EntityNotFound", "InvalidInput")):
            return f"ignoré ({name}: {str(e)[:110]})"
        raise


# 1. Placer le bucket curated sous le contrôle de Lake Formation
step("Enregistrement du bucket curated dans Lake Formation")
print(safe(lf.register_resource, ResourceArn=f"arn:aws:s3:::{CURATED_BUCKET}", UseServiceLinkedRole=True))

# 2. Base dédiée
step(f"Création de la base {DB_LF}")
print(safe(glue.create_database, DatabaseInput={"Name": DB_LF, "LocationUri": f"s3://{CURATED_BUCKET}/",
           "Description": "Tables gouvernées par Lake Formation (stratégie S1)"}))
print("Retrait IAM_ALLOWED_PRINCIPALS (base) :",
      safe(lf.revoke_permissions, Principal=IAM_ALL, Resource={"Database": {"Name": DB_LF}}, Permissions=["ALL"]))

for s in SCALES:
    t = f"bank_churn_x{s}"
    step(f"Table {DB_LF}.{t}")

    # 3. Copie de la DÉFINITION de la table (pas des données : mêmes fichiers S3)
    src = glue.get_table(DatabaseName=DB_CURATED, Name=t)["Table"]
    tinput = {k: src[k] for k in ("Name", "StorageDescriptor", "PartitionKeys", "TableType", "Parameters") if k in src}
    print("  définition :", safe(glue.create_table, DatabaseName=DB_LF, TableInput=tinput))
    parts = glue.get_partitions(DatabaseName=DB_CURATED, TableName=t)["Partitions"]
    glue.batch_create_partition(DatabaseName=DB_LF, TableName=t, PartitionInputList=[
        {"Values": p["Values"], "StorageDescriptor": p["StorageDescriptor"]} for p in parts])
    print(f"  partitions : {len(parts)}")

    # 4. Fermer la "porte" : plus aucun accès IAM implicite à cette table
    print("  retrait IAM_ALLOWED_PRINCIPALS :", safe(lf.revoke_permissions, Principal=IAM_ALL,
          Resource={"Table": {"DatabaseName": DB_LF, "Name": t}}, Permissions=["ALL"]))

    # 5. L'administratrice garde un accès complet (pour les vérifications)
    print("  accès admin :", safe(lf.grant_permissions, Principal={"DataLakePrincipalIdentifier": ME},
          Resource={"Table": {"DatabaseName": DB_LF, "Name": t}}, Permissions=["SELECT", "DESCRIBE"]))

    # 6. Filtre de cellules : lignes France + colonnes sensibles exclues
    print("  filtre :", safe(lf.create_data_cells_filter, TableData={
        "TableCatalogId": ACCOUNT, "DatabaseName": DB_LF, "TableName": t, "Name": FILTER,
        "RowFilter": {"FilterExpression": "country = 'France'"},
        "ColumnWildcard": {"ExcludedColumnNames": EXCLUDED}}))

    # 7. L'analyste n'a accès QU'AU filtre (jamais à la table complète)
    print("  accès analyste au filtre :", safe(lf.grant_permissions,
          Principal={"DataLakePrincipalIdentifier": ANALYST},
          Resource={"DataCellsFilter": {"TableCatalogId": ACCOUNT, "DatabaseName": DB_LF,
                                        "TableName": t, "Name": FILTER}},
          Permissions=["SELECT"]))

step("Accès analyste à la base (DESCRIBE)")
print(safe(lf.grant_permissions, Principal={"DataLakePrincipalIdentifier": ANALYST},
           Resource={"Database": {"Name": DB_LF}}, Permissions=["DESCRIBE"]))

print("\nPropagation des droits (20 s)..."); time.sleep(20)

# 8. Tests avec l'identité de l'analyste
athena = analyst_session().client("athena")
print("\n--- TEST 1 : l'analyste lit la table gouvernée ---")
run_as_analyst(f"SELECT * FROM {DB_LF}.bank_churn_x1 LIMIT 3", athena)
run_as_analyst(f"SELECT country, COUNT(*) FROM {DB_LF}.bank_churn_x1 GROUP BY country", athena)
print("\n--- TEST 2 : l'analyste demande l'Allemagne ---")
run_as_analyst(f"SELECT COUNT(*) FROM {DB_LF}.bank_churn_x1 WHERE country = 'Germany'", athena)
print("\n--- TEST 3 : l'analyste demande une colonne sensible ---")
run_as_analyst(f"SELECT balance FROM {DB_LF}.bank_churn_x1 LIMIT 1", athena)