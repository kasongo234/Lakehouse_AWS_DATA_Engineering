import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boto3
from config import REGION, ACCOUNT, RAW_BUCKET, CURATED_BUCKET

GLUE_ROLE, DB_RAW, DB_CURATED = "LakehouseGlueRole", "lakehouse_raw", "lakehouse_curated"
iam = boto3.client("iam")
glue = boto3.client("glue", region_name=REGION)
lf = boto3.client("lakeformation", region_name=REGION)

# (A) Rôle IAM que le job Spark « endosse » quand il s'exécute
trust = {"Version": "2012-10-17", "Statement": [{
    "Effect": "Allow", "Principal": {"Service": "glue.amazonaws.com"},
    "Action": "sts:AssumeRole"}]}
try:
    iam.create_role(RoleName=GLUE_ROLE, AssumeRolePolicyDocument=json.dumps(trust))
    print("Rôle créé")
except iam.exceptions.EntityAlreadyExistsException:
    print("Rôle existant")

# (B) Droits de base du service Glue (logs, catalogue)
iam.attach_role_policy(RoleName=GLUE_ROLE,
    PolicyArn="arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole")

# (C) Moindre privilège sur S3 : LIRE raw, LIRE/ÉCRIRE curated, rien d'autre
s3_policy = {"Version": "2012-10-17", "Statement": [
    {"Effect": "Allow", "Action": ["s3:ListBucket"],
     "Resource": [f"arn:aws:s3:::{RAW_BUCKET}", f"arn:aws:s3:::{CURATED_BUCKET}"]},
    {"Effect": "Allow", "Action": ["s3:GetObject"],
     "Resource": [f"arn:aws:s3:::{RAW_BUCKET}/*"]},
    {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
     "Resource": [f"arn:aws:s3:::{CURATED_BUCKET}/*"]},
    {"Effect": "Allow", "Action": ["lakeformation:GetDataAccess"], "Resource": "*"}]}
iam.put_role_policy(RoleName=GLUE_ROLE, PolicyName="LakehouseS3Access",
                    PolicyDocument=json.dumps(s3_policy))

# (D) Deux bases dans le Glue Data Catalog (une par zone)
for db, bucket in [(DB_RAW, RAW_BUCKET), (DB_CURATED, CURATED_BUCKET)]:
    try:
        glue.create_database(DatabaseInput={"Name": db, "LocationUri": f"s3://{bucket}/"})
        print("Base créée :", db)
    except glue.exceptions.AlreadyExistsException:
        print("Base existante :", db)

# (E) Lake Formation : le rôle Spark peut créer et écrire des tables dans curated
role_arn = f"arn:aws:iam::{ACCOUNT}:role/{GLUE_ROLE}"
try:
    lf.grant_permissions(Principal={"DataLakePrincipalIdentifier": role_arn},
        Resource={"Database": {"Name": DB_CURATED}},
        Permissions=["CREATE_TABLE", "ALTER", "DESCRIBE", "DROP"])
    lf.grant_permissions(Principal={"DataLakePrincipalIdentifier": role_arn},
        Resource={"Table": {"DatabaseName": DB_CURATED, "TableWildcard": {}}},
        Permissions=["ALL"])
    print("Droits Lake Formation accordés")
except Exception as e:
    print("Lake Formation :", e)