# =====================================================================
# harden_analyst.py (Phase 3 - étape 3.7)
# Durcissement Zero Trust de l'analyste : on RETIRE son accès direct aux
# fichiers de données S3. Il ne garde que ses propres résultats de requêtes.
#   python infra\harden_analyst.py           -> applique le durcissement
#   python infra\harden_analyst.py restore   -> revient à la politique initiale
# =====================================================================
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boto3
from config import REGION, ACCOUNT, CURATED_BUCKET, WORKGROUP

ROLE = "LakehouseAnalystFR"
iam = boto3.client("iam")
restore = len(sys.argv) > 1 and sys.argv[1] == "restore"

common = [
    {"Effect": "Allow",
     "Action": ["athena:StartQueryExecution", "athena:GetQueryExecution",
                "athena:GetQueryResults", "athena:StopQueryExecution", "athena:GetWorkGroup"],
     "Resource": f"arn:aws:athena:{REGION}:{ACCOUNT}:workgroup/{WORKGROUP}"},
    {"Effect": "Allow",
     "Action": ["glue:GetDatabase", "glue:GetDatabases", "glue:GetTable", "glue:GetTables",
                "glue:GetPartition", "glue:GetPartitions"], "Resource": "*"},
    {"Effect": "Allow", "Action": ["lakeformation:GetDataAccess"], "Resource": "*"},
    # Résultats de SES requêtes uniquement (écriture + relecture)
    {"Effect": "Allow", "Action": ["s3:PutObject", "s3:GetObject", "s3:AbortMultipartUpload"],
     "Resource": f"arn:aws:s3:::{CURATED_BUCKET}/_athena_results/*"},
    {"Effect": "Allow", "Action": ["s3:GetBucketLocation"], "Resource": f"arn:aws:s3:::{CURATED_BUCKET}"},
]
if restore:
    # Politique initiale : lecture de TOUT le bucket curated (fichiers de données compris)
    common.append({"Effect": "Allow", "Action": ["s3:GetObject", "s3:ListBucket"],
                   "Resource": [f"arn:aws:s3:::{CURATED_BUCKET}", f"arn:aws:s3:::{CURATED_BUCKET}/*"]})

iam.put_role_policy(RoleName=ROLE, PolicyName="AnalystAthenaAccess",
                    PolicyDocument=json.dumps({"Version": "2012-10-17", "Statement": common}))
print("Politique", "RESTAURÉE (accès S3 complet)" if restore else
      "DURCIE : plus aucun accès direct aux fichiers de données")
print("Propagation IAM (20 s)..."); time.sleep(20); print("Prêt.")