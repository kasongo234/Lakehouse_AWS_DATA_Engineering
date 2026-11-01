import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boto3
from config import REGION, RAW_BUCKET, CURATED_BUCKET

s3 = boto3.client("s3", region_name=REGION)

def secure_bucket(name):
    # (1) Création du bucket dans la région Paris
    try:
        s3.create_bucket(Bucket=name, CreateBucketConfiguration={"LocationConstraint": REGION})
    except s3.exceptions.BucketAlreadyOwnedByYou:
        print("Existe déjà :", name)

    # (2) Blocage de TOUT accès public
    s3.put_public_access_block(Bucket=name, PublicAccessBlockConfiguration={
        "BlockPublicAcls": True, "IgnorePublicAcls": True,
        "BlockPublicPolicy": True, "RestrictPublicBuckets": True})

    # (3) Chiffrement automatique de chaque fichier stocké
    s3.put_bucket_encryption(Bucket=name, ServerSideEncryptionConfiguration={"Rules": [{
        "ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}, "BucketKeyEnabled": True}]})

    # (4) Versioning : un fichier écrasé ou supprimé reste récupérable
    s3.put_bucket_versioning(Bucket=name, VersioningConfiguration={"Status": "Enabled"})

    # (5) Politique : refuser toute connexion non chiffrée (sans HTTPS)
    s3.put_bucket_policy(Bucket=name, Policy=json.dumps({"Version": "2012-10-17", "Statement": [{
        "Sid": "DenyInsecureTransport", "Effect": "Deny", "Principal": "*", "Action": "s3:*",
        "Resource": [f"arn:aws:s3:::{name}", f"arn:aws:s3:::{name}/*"],
        "Condition": {"Bool": {"aws:SecureTransport": "false"}}}]}))

    # (6) Désactivation des ACL : seules les politiques IAM décident des accès
    s3.put_bucket_ownership_controls(Bucket=name, OwnershipControls={
        "Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]})
    print("OK", name)

for b in (RAW_BUCKET, CURATED_BUCKET):
    secure_bucket(b)