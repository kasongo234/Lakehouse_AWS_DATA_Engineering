# =====================================================================
# run_etl.py : déploie le job Spark sur Glue et l'exécute par volumétrie
# Usage :  python etl\run_etl.py 1000
# =====================================================================
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boto3
from config import REGION, RAW_BUCKET, CURATED_BUCKET, GLUE_ROLE, GLUE_JOB, DB_CURATED, SOURCE, SCALES

s3 = boto3.client("s3", region_name=REGION)
glue = boto3.client("glue", region_name=REGION)

# (A) Envoi du script Spark dans S3
script_key = "_scripts/clean_bank_churn.py"
s3.upload_file(os.path.join(os.path.dirname(os.path.abspath(__file__)), "clean_bank_churn.py"),
               RAW_BUCKET, script_key)

# (B) Définition du job (même configuration pour toutes les tailles)
job = {"Role": GLUE_ROLE,
       "Command": {"Name": "glueetl", "ScriptLocation": f"s3://{RAW_BUCKET}/{script_key}",
                   "PythonVersion": "3"},
       "GlueVersion": "5.0", "WorkerType": "G.1X", "NumberOfWorkers": 4, "Timeout": 30,
       "DefaultArguments": {"--enable-glue-datacatalog": "true", "--enable-metrics": "true"}}
try:
    glue.create_job(Name=GLUE_JOB, **job); print("Job créé")
except glue.exceptions.AlreadyExistsException:
    glue.update_job(JobName=GLUE_JOB, JobUpdate=job); print("Job mis à jour")

# (C) Une exécution par volumétrie
scales = [int(a) for a in sys.argv[1:]] or SCALES
for scale in scales:
    # Réessai : si le run précédent n'est pas encore libéré, on attend 15 s (max 10 essais)
    run_id = None
    for attempt in range(10):
        try:
            run_id = glue.start_job_run(JobName=GLUE_JOB, Arguments={
                "--RAW_PATH": f"s3://{RAW_BUCKET}/source={SOURCE}/",
                "--CURATED_BUCKET": CURATED_BUCKET, "--DATABASE": DB_CURATED,
                "--SCALE": str(scale)})["JobRunId"]
            break
        except glue.exceptions.ConcurrentRunsExceededException:
            print("   job encore occupé, nouvel essai dans 15 s...")
            time.sleep(15)
    if run_id is None:
        print(f"[x{scale}] impossible de lancer le job"); continue
    print(f"[x{scale}] lancé : {run_id}")

    # (D) Suivi jusqu'à la fin
    while True:
        r = glue.get_job_run(JobName=GLUE_JOB, RunId=run_id)["JobRun"]
        if r["JobRunState"] in ("SUCCEEDED", "FAILED", "STOPPED", "TIMEOUT", "ERROR"):
            break
        print("   ...", r["JobRunState"]); time.sleep(20)

    # (E) Bilan
    print(f"[x{scale}] {r['JobRunState']}  durée={r.get('ExecutionTime')}s  "
          f"DPU-h={r.get('DPUSeconds', 0)/3600:.3f}  {r.get('ErrorMessage', '')}")