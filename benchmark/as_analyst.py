# =====================================================================
# as_analyst.py (Phase 3 - étape 3.1)
# Exécute une requête Athena EN TANT QUE l'analyste France (rôle IAM),
# et non avec vos droits d'administratrice.
# Usage : python benchmark\as_analyst.py "SELECT ..."
# Réutilisé par le benchmark pour mesurer chaque stratégie.
# =====================================================================
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boto3
from config import REGION, ACCOUNT, WORKGROUP, DB_CURATED

ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/LakehouseAnalystFR"


def analyst_session():
    """Obtient des identifiants TEMPORAIRES du rôle analyste (STS AssumeRole)."""
    c = boto3.client("sts").assume_role(RoleArn=ROLE_ARN, RoleSessionName="benchmark-analyst",
                                        DurationSeconds=3600)["Credentials"]
    return boto3.Session(aws_access_key_id=c["AccessKeyId"],
                         aws_secret_access_key=c["SecretAccessKey"],
                         aws_session_token=c["SessionToken"], region_name=REGION)


def run(sql, athena=None, show=True):
    """Exécute la requête ; renvoie (état, lignes, statistiques, message d'erreur)."""
    athena = athena or analyst_session().client("athena")
    qid = athena.start_query_execution(QueryString=sql, WorkGroup=WORKGROUP,
                                       QueryExecutionContext={"Database": DB_CURATED})["QueryExecutionId"]
    while True:
        q = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
        if q["Status"]["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(0.5)
    state, rows = q["Status"]["State"], []
    if state == "SUCCEEDED":
        rows = [[c.get("VarCharValue") for c in r["Data"]]
                for r in athena.get_query_results(QueryExecutionId=qid)["ResultSet"]["Rows"]]
    if show:
        print("État :", state, q["Status"].get("StateChangeReason", ""))
        for r in rows[:10]:
            print(" | ".join(str(v) for v in r))
        s = q.get("Statistics", {})
        print(f"Temps moteur : {s.get('EngineExecutionTimeInMillis')} ms | "
              f"scanné : {s.get('DataScannedInBytes', 0)/1024:.1f} Ko")
    return state, rows, q.get("Statistics", {}), q["Status"].get("StateChangeReason")


if __name__ == "__main__":
    who = boto3.client("sts")
    s = analyst_session()
    print("Identité utilisée :", s.client("sts").get_caller_identity()["Arn"], "\n")
    run(sys.argv[1], s.client("athena"))