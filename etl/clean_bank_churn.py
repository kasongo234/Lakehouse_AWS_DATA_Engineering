"""Job Spark (AWS Glue 5.0) : raw (CSV) ,curated (Parquet, catalogué)."""
import sys, json
import boto3
from awsglue.utils import getResolvedOptions
from pyspark.sql import SparkSession, functions as F, types as T

args = getResolvedOptions(sys.argv, ["RAW_PATH", "CURATED_BUCKET", "DATABASE", "SCALE"])
SCALE = int(args["SCALE"])
TABLE = f"bank_churn_x{SCALE}"
OUT = f"s3://{args['CURATED_BUCKET']}/{TABLE}/"

spark = SparkSession.builder.appName(f"clean-{TABLE}").enableHiveSupport().getOrCreate()

# (1) Lecture brute : tout en texte
raw = spark.read.option("header", True).csv(args["RAW_PATH"])
n_raw = raw.count()

# (2) Normalisation : espaces et casse
df = raw.select([F.trim(F.col(c)).alias(c) for c in raw.columns])
df = df.withColumn("country", F.initcap("country")).withColumn("gender", F.initcap("gender"))

# (3) Typage explicite
schema = {
    "customer_id": T.LongType(), "credit_score": T.IntegerType(),
    "age": T.IntegerType(), "tenure": T.IntegerType(),
    "balance": T.DecimalType(12, 2), "products_number": T.IntegerType(),
    "credit_card": T.IntegerType(), "active_member": T.IntegerType(),
    "estimated_salary": T.DecimalType(12, 2), "churn": T.IntegerType()}
for c, t in schema.items():
    df = df.withColumn(c, F.col(c).cast(t))

# (4) Règles de qualité
rules = {
    "id_non_nul": F.col("customer_id").isNotNull(),
    "credit_score_300_850": F.col("credit_score").between(300, 850),
    "age_18_100": F.col("age").between(18, 100),
    "tenure_0_50": F.col("tenure").between(0, 50),
    "balance_positif": F.col("balance") >= 0,
    "products_1_4": F.col("products_number").between(1, 4),
    "flags_binaires": F.col("credit_card").isin(0, 1) & F.col("active_member").isin(0, 1)
                      & F.col("churn").isin(0, 1),
    "salaire_positif": F.col("estimated_salary") > 0,
    "pays_connu": F.col("country").isin("France", "Germany", "Spain"),
    "genre_connu": F.col("gender").isin("Male", "Female")}
valid = F.lit(True)
for r in rules.values():
    valid = valid & F.coalesce(r, F.lit(False))
df = df.withColumn("_valid", valid)

rejected = df.filter(~F.col("_valid"))
clean = df.filter("_valid").drop("_valid").dropDuplicates(["customer_id"])
n_rejected, n_clean = rejected.count(), clean.count()
if n_rejected:
    rejected.write.mode("overwrite").json(f"s3://{args['CURATED_BUCKET']}/_quarantine/{TABLE}/")

# (5) Montée en volumétrie (utilisée seulement si SCALE > 1)
if SCALE > 1:
    reps = spark.range(SCALE).withColumnRenamed("id", "rep")
    clean = clean.crossJoin(reps)
    noise = lambda c: F.when(F.col("rep") == 0, F.col(c)).otherwise(
        (F.col(c) * (F.lit(0.95) + F.rand(seed=42) * 0.10)).cast(T.DecimalType(12, 2)))
    clean = (clean
             .withColumn("customer_id", F.col("customer_id") + F.col("rep") * F.lit(1_000_000_000))
             .withColumn("balance", noise("balance"))
             .withColumn("estimated_salary", noise("estimated_salary"))
             .drop("rep"))

# (6) Lignage
clean = clean.withColumn("ingest_ts", F.current_timestamp()) \
             .withColumn("source_file", F.input_file_name())

# (7) Écriture Parquet partitionnée par pays + enregistrement dans le catalogue
spark.sql(f"DROP TABLE IF EXISTS {args['DATABASE']}.{TABLE}")
(clean.repartition("country").write.mode("overwrite")
      .format("parquet").option("compression", "snappy")
      .partitionBy("country").option("path", OUT)
      .saveAsTable(f"{args['DATABASE']}.{TABLE}"))

# (8) Rapport qualité
report = {"table": TABLE, "scale": SCALE, "rows_raw": n_raw, "rows_rejected": n_rejected,
          "rows_clean_base": n_clean, "rows_written": n_clean * SCALE, "rules": list(rules)}
print(json.dumps(report))
boto3.client("s3").put_object(Bucket=args["CURATED_BUCKET"],
    Key=f"_quality/{TABLE}.json", Body=json.dumps(report, indent=2).encode())