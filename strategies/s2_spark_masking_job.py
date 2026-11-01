# =====================================================================
# s2_spark_masking_job.py (Phase 3 - étape 3.4) - Stratégie S2 : masquage applicatif Spark
# Job AWS Glue (Spark). La règle de sécurité est appliquée DANS LE CODE :
#   - LIGNES   : filtre country = 'France'
#   - COLONNES : customer_id haché (SHA-256), âge en tranches,
#                balance / estimated_salary / credit_score supprimées
# Puis les 3 requêtes du benchmark sont exécutées et chronométrées.
# Arguments : --CURATED_BUCKET --DATABASE --SCALES (ex. "1,100,1000") --REPS (ex. 5)
# =====================================================================
import sys, json, time
import boto3
from awsglue.utils import getResolvedOptions
from pyspark.sql import SparkSession, functions as F

args = getResolvedOptions(sys.argv, ["CURATED_BUCKET", "DATABASE", "SCALES", "REPS"])
SCALES = [int(s) for s in args["SCALES"].split(",")]
REPS = int(args["REPS"])
spark = SparkSession.builder.appName("s2-spark-masking").enableHiveSupport().getOrCreate()

# --- Les 3 requêtes du benchmark (identiques pour les 3 stratégies) ------
QUERIES = {
    "Q1_agregation": "SELECT gender, COUNT(*) AS n, AVG(churn) AS churn_rate FROM secure GROUP BY gender",
    "Q2_selection":  "SELECT * FROM secure WHERE tenure >= 5 LIMIT 1000",
    "Q3_filtre_tri": "SELECT tenure, products_number, COUNT(*) AS n FROM secure "
                     "WHERE active_member = 1 GROUP BY tenure, products_number ORDER BY n DESC LIMIT 10",
}


def secure_view(table):
    """Applique la règle de sécurité dans le code Spark (masquage applicatif)."""
    df = spark.table(f"{args['DATABASE']}.{table}")
    return (df.filter(F.col("country") == "France")                                   # lignes
              .withColumn("customer_hash", F.sha2(F.col("customer_id").cast("string"), 256))  # hachage
              .withColumn("age_band", (F.floor(F.col("age") / 10) * 10).cast("int"))  # généralisation
              .drop("customer_id", "age", "balance", "estimated_salary", "credit_score",
                    "ingest_date", "ingest_ts", "source_file"))                        # exclusion


results, checks = [], {}
for scale in SCALES:
    table = f"bank_churn_x{scale}"
    secure_view(table).createOrReplaceTempView("secure")

    # Vérification de sécurité : colonnes visibles + pays présents
    checks[table] = {
        "columns": spark.table("secure").columns,
        "countries": [r[0] for r in spark.sql("SELECT DISTINCT country FROM secure").collect()],
    }
    print(table, checks[table])

    for qname, sql in QUERIES.items():
        spark.sql(sql).collect()                      # échauffement (non mesuré)
        for rep in range(1, REPS + 1):
            t0 = time.perf_counter()
            spark.sql(sql).collect()                  # exécution complète (pas de cache)
            ms = round((time.perf_counter() - t0) * 1000)
            results.append({"strategy": "S2_spark", "table": table, "scale": scale,
                            "query": qname, "rep": rep, "engine_ms": ms})
            print(f"{table} {qname} rep{rep}: {ms} ms")

out = {"results": results, "security_checks": checks}
boto3.client("s3").put_object(Bucket=args["CURATED_BUCKET"], Key="_benchmark/s2_spark.json",
                              Body=json.dumps(out, indent=2).encode())
print("Résultats écrits : _benchmark/s2_spark.json")