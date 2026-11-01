import sys, os, hashlib, base64, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boto3
from config import REGION, RAW_BUCKET, SOURCE, LOCAL_CSV

s3 = boto3.client("s3", region_name=REGION)

# (A) Emplacement : source + date d'ingestion (partitionnement de type Hive)
today = datetime.date.today().isoformat()
key = f"source={SOURCE}/ingest_date={today}/{os.path.basename(LOCAL_CSV)}"

# (B) Empreinte numérique SHA-256 du fichier local
data = open(LOCAL_CSV, "rb").read()
sha_hex = hashlib.sha256(data).hexdigest()

# (C) Envoi avec contrôle d'intégrité côté AWS + métadonnées de traçabilité
s3.put_object(Bucket=RAW_BUCKET, Key=key, Body=data,
              ChecksumAlgorithm="SHA256",
              Metadata={"sha256": sha_hex, "source": SOURCE,
                        "ingest-date": today, "rows": str(data.count(b"\n") - 1)})

# (D) Vérification : relire ce que S3 a réellement stocké
head = s3.head_object(Bucket=RAW_BUCKET, Key=key, ChecksumMode="ENABLED")
s3_sha = base64.b64decode(head["ChecksumSHA256"]).hex()

print("Fichier  :", f"s3://{RAW_BUCKET}/{key}")
print("Taille   :", head["ContentLength"], "octets (local :", len(data), ")")
print("SHA local:", sha_hex)
print("SHA S3   :", s3_sha)
print("Intégrité:", "OK" if s3_sha == sha_hex else "ÉCHEC")
print("Chiffré  :", head.get("ServerSideEncryption"))