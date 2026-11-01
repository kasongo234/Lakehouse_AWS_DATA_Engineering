# =====================================================================
# create_analyst_role.py (Phase 3 - étape 3.1)
# Crée le rôle IAM de test "LakehouseAnalystFR" : l'identité d'un analyste
# qui ne devrait voir que la France, sans les colonnes sensibles.
# Les 3 stratégies de sécurité seront testées AVEC cette identité.
# =====================================================================
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boto3
from config import REGION, ACCOUNT, CURATED_BUCKET, WORKGROUP

ROLE = "LakehouseAnalystFR"
iam = boto3.client("iam")
me = boto3.client("sts").get_caller_identity()["Arn"]     # votre utilisateur IAM

# (A) Politique de confiance : seul VOTRE utilisateur peut endosser ce rôle
trust = {"Version": "2012-10-17", "Statement": [{
    "Effect": "Allow", "Principal": {"AWS": me}, "Action": "sts:AssumeRole"}]}
try:
    iam.create_role(RoleName=ROLE, AssumeRolePolicyDocument=json.dumps(trust),
                    MaxSessionDuration=3600,
                    Description="Analyste France - identité de test du benchmark")
    print("Rôle créé :", ROLE)
except iam.exceptions.EntityAlreadyExistsException:
    iam.update_assume_role_policy(RoleName=ROLE, PolicyDocument=json.dumps(trust))
    print("Rôle existant :", ROLE)

# (B) Droits MINIMAUX pour interroger les données avec Athena
policy = {"Version": "2012-10-17", "Statement": [
    # Athena : uniquement dans le workgroup du projet
    {"Effect": "Allow",
     "Action": ["athena:StartQueryExecution", "athena:GetQueryExecution",
                "athena:GetQueryResults", "athena:StopQueryExecution", "athena:GetWorkGroup"],
     "Resource": f"arn:aws:athena:{REGION}:{ACCOUNT}:workgroup/{WORKGROUP}"},
    # Catalogue : lecture seule des métadonnées
    {"Effect": "Allow",
     "Action": ["glue:GetDatabase", "glue:GetDatabases", "glue:GetTable", "glue:GetTables",
                "glue:GetPartition", "glue:GetPartitions"],
     "Resource": "*"},
    # S3 : lecture des données curated + écriture des résultats Athena
    {"Effect": "Allow", "Action": ["s3:GetObject", "s3:ListBucket", "s3:GetBucketLocation"],
     "Resource": [f"arn:aws:s3:::{CURATED_BUCKET}", f"arn:aws:s3:::{CURATED_BUCKET}/*"]},
    {"Effect": "Allow", "Action": ["s3:PutObject", "s3:AbortMultipartUpload"],
     "Resource": f"arn:aws:s3:::{CURATED_BUCKET}/_athena_results/*"},
    # Lake Formation : nécessaire pour la stratégie S1 (identifiants temporaires)
    {"Effect": "Allow", "Action": ["lakeformation:GetDataAccess"], "Resource": "*"}]}
iam.put_role_policy(RoleName=ROLE, PolicyName="AnalystAthenaAccess", PolicyDocument=json.dumps(policy))
print("Politique attachée : AnalystAthenaAccess")
print("ARN :", f"arn:aws:iam::{ACCOUNT}:role/{ROLE}")
print("Attente de la propagation IAM (15 s)..."); time.sleep(15)
print("Prêt.")