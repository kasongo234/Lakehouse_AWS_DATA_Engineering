# =====================================================================
# s2_run_spark.py (Phase 3 - étape 3.4)
# Déploie et lance le job Spark de masquage, puis récupère les mesures.
# Usage : python strategies\s2_run_spark.py            (toutes les tailles, 5 répétitions)
#         python strategies\s2_run_spark.py 1 2         (x1 seulement, 2 répétitions : test)
# =====================================================================
import sys, os, time, json, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boto3
from config import REGION, RAW_BUCKET, CURATED_BUCKET, GLUE_ROLE, DB_CURATED, SCALES, PROJECT_DIR

JOB = "bank-churn-spark-masking"
s3 = boto3.client("s3", region_name=REGION)
glue = boto3.client("glue", region_name=REGION)

scales = sys.argv[1] if len(sys.argv) > 1 else ",".join(str(s) for s in SCALES)
reps = sys.argv[2] if len(sys.argv) > 2 else "5"

# 1. Envoi du script et création/mise à jour du job (même configuration que l'ETL)
key = "_scripts/s2_spark_masking_job.py"
s3.upload_file(os.path.join(os.path.dirname(os.path.abspath(__file__)), "s2_spark_masking_job.py"),
               RAW_BUCKET, key)
job = {"Role": GLUE_ROLE,
       "Command": {"Name": "glueetl", "ScriptLocation": f"s3://{RAW_BUCKET}/{key}", "PythonVersion": "3"},
       "GlueVersion": "5.0", "WorkerType": "G.1X", "NumberOfWorkers": 4, "Timeout": 60,
       "DefaultArguments": {"--enable-glue-datacatalog": "true", "--enable-metrics": "true"}}
try:
    glue.create_job(Name=JOB, **job); print("Job créé")
except glue.exceptions.AlreadyExistsException:
    glue.update_job(JobName=JOB, JobUpdate=job); print("Job mis à jour")

# 2. Lancement (avec réessai si le job est encore occupé)
for _ in range(10):
    try:
        run_id = glue.start_job_run(JobName=JOB, Arguments={
            "--CURATED_BUCKET": CURATED_BUCKET, "--DATABASE": DB_CURATED,
            "--SCALES": scales, "--REPS": reps})["JobRunId"]
        break
    except glue.exceptions.ConcurrentRunsExceededException:
        print("   job occupé, nouvel essai dans 15 s..."); time.sleep(15)
print("Lancé :", run_id, "| tailles :", scales, "| répétitions :", reps)

while True:
    r = glue.get_job_run(JobName=JOB, RunId=run_id)["JobRun"]
    if r["JobRunState"] in ("SUCCEEDED", "FAILED", "STOPPED", "TIMEOUT", "ERROR"):
        break
    print("   ...", r["JobRunState"]); time.sleep(20)
dpu_h = r.get("DPUSeconds", 0) / 3600
print(f"{r['JobRunState']}  durée={r.get('ExecutionTime')}s  DPU-h={dpu_h:.3f}  {r.get('ErrorMessage', '')}")
if r["JobRunState"] != "SUCCEEDED":
    sys.exit(1)

# 3. Récupération des mesures + synthèse
data = json.loads(s3.get_object(Bucket=CURATED_BUCKET, Key="_benchmark/s2_spark.json")["Body"].read())
data["job"] = {"run_id": run_id, "duration_s": r.get("ExecutionTime"), "dpu_hours": round(dpu_h, 4),
               "cost_usd": round(dpu_h * 0.44, 4)}          # tarif Glue : 0,44 $ par DPU-heure
os.makedirs(os.path.join(PROJECT_DIR, "output"), exist_ok=True)
path = os.path.join(PROJECT_DIR, "output", "bench_s2_spark.json")
json.dump(data, open(path, "w", encoding="utf-8"), indent=2)

print("\n=== Vérification de sécurité ===")
for t, c in data["security_checks"].items():
    print(f"{t}: pays={c['countries']}  colonnes={c['columns']}")
print("\n=== Temps médian par requête (ms) ===")
groups = {}
for x in data["results"]:
    groups.setdefault((x["table"], x["query"]), []).append(x["engine_ms"])
for (t, q), v in groups.items():
    print(f"{t:<18} {q:<15} médiane={statistics.median(v):>7.0f} ms")
print(f"\nCoût du job : {data['job']['cost_usd']} $  |  Résultats : {path}")