# =====================================================================
# catalog_scanner.py (Objectif 1 - étape 2.1)
# Interroge automatiquement le Glue Data Catalog et S3 pour extraire,
# pour chaque table : colonnes, partitions, format, taille, nb de lignes.
# Sortie : output/context_catalog.json
# =====================================================================
import sys, os, json, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boto3
from config import REGION, CURATED_BUCKET, PROJECT_DIR

DATABASE = "lakehouse_curated"
glue = boto3.client("glue", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)

def list_tables(db):
    """Découvre toutes les tables de la base (aucun nom écrit en dur)."""
    tables = []
    for page in glue.get_paginator("get_tables").paginate(DatabaseName=db):
        tables.extend(page["TableList"])          # AWS renvoie par pages -> on les enchaîne
    return tables

def count_partitions(db, table):
    """Liste les partitions (ex. France, Germany, Spain)."""
    values = []
    for page in glue.get_paginator("get_partitions").paginate(DatabaseName=db, TableName=table):
        values += ["/".join(p["Values"]) for p in page["Partitions"]]
    return len(values), values

def s3_volume(location):
    """Mesure la taille réelle des fichiers de la table dans S3."""
    bucket, _, prefix = location.replace("s3://", "").partition("/")
    prefix = prefix.rstrip("/") + "/"     # "/" final : sinon bank_churn_x1 inclut x100 et x1000
    size = files = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].rsplit("/", 1)[-1].startswith(("_", ".")):   # ignore fichiers techniques
                continue
            size += obj["Size"]; files += 1
    return size, files

def row_count(table):
    """Nombre de lignes lu dans le rapport qualité du job Spark (pas de requête payante)."""
    try:
        body = s3.get_object(Bucket=CURATED_BUCKET, Key=f"_quality/{table}.json")["Body"].read()
        return json.loads(body)["rows_written"]
    except Exception:
        return None

def scan():
    result = {"database": DATABASE, "scanned_at": datetime.datetime.now().isoformat(), "tables": []}
    for t in list_tables(DATABASE):
        sd = t["StorageDescriptor"]                       # description du stockage de la table
        n_part, part_values = count_partitions(DATABASE, t["Name"])
        size, files = s3_volume(sd["Location"])
        info = {
            "name": t["Name"],
            "location": sd["Location"],
            "format": "parquet" if "parquet" in sd.get("InputFormat", "").lower() else sd.get("InputFormat"),
            "columns": [{"name": c["Name"], "type": c["Type"]} for c in sd["Columns"]],
            "partition_keys": [p["Name"] for p in t.get("PartitionKeys", [])],
            "partitions": n_part,
            "partition_values": part_values,
            "size_bytes": size,
            "size_mb": round(size / 1024**2, 2),
            "files": files,
            "rows": row_count(t["Name"]),
            "avg_file_mb": round(size / files / 1024**2, 2) if files else 0}
        result["tables"].append(info)
        print(f"{info['name']:<18} {len(info['columns']):>2} col  {n_part} part  "
              f"{info['size_mb']:>8} Mo  {files:>3} fichiers  {info['rows']} lignes")

    os.makedirs(os.path.join(PROJECT_DIR, "output"), exist_ok=True)
    out = os.path.join(PROJECT_DIR, "output", "context_catalog.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print("\nContexte enregistré :", out)

if __name__ == "__main__":
    scan()