# =====================================================================
# run_benchmark.py (Phase 3 - étape 3.5)
# Exécute automatiquement le benchmark des stratégies basées sur Athena,
# TOUJOURS avec l'identité de l'analyste France :
#   S0_reference : table brute (aucune sécurité)      -> lakehouse_curated.bank_churn_xN
#   S1_lakeform  : table gouvernée par Lake Formation  -> lakehouse_lf.bank_churn_xN
#   S3_vues      : vue Athena sécurisée                -> lakehouse_curated.v_secure_xN
# Protocole : 3 volumes x 3 requêtes x (1 échauffement + 5 mesures)
# Sortie : output/bench_athena.json
# =====================================================================
import sys, os, json, time, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import SCALES, WORKGROUP, DB_CURATED, PROJECT_DIR
from as_analyst import analyst_session

REPS = int(sys.argv[1]) if len(sys.argv) > 1 else 5
PRICE_PER_TB = 5.0                      # tarif Athena ($ par To scanné)
MIN_BILLED = 10 * 1024**2               # minimum facturé : 10 Mo par requête

STRATEGIES = {
    "S0_reference": "lakehouse_curated.bank_churn_x{s}",
    "S1_lakeformation": "lakehouse_lf.bank_churn_x{s}",
    "S3_vues": "lakehouse_curated.v_secure_x{s}",
}
# Mêmes requêtes que le job Spark (S2), sur des colonnes visibles dans TOUTES les stratégies
QUERIES = {
    "Q1_agregation": "SELECT gender, COUNT(*) AS n, AVG(churn) AS churn_rate FROM {obj} GROUP BY gender",
    "Q2_selection":  "SELECT * FROM {obj} WHERE tenure >= 5 LIMIT 1000",
    "Q3_filtre_tri": "SELECT tenure, products_number, COUNT(*) AS n FROM {obj} "
                     "WHERE active_member = 1 GROUP BY tenure, products_number ORDER BY n DESC LIMIT 10",
}


def execute(athena, sql):
    """Lance une requête, attend la fin, renvoie ses statistiques."""
    qid = athena.start_query_execution(QueryString=sql, WorkGroup=WORKGROUP,
                                       QueryExecutionContext={"Database": DB_CURATED})["QueryExecutionId"]
    while True:
        q = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
        if q["Status"]["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            return q
        time.sleep(0.3)


def main():
    session_start = time.time()
    athena = analyst_session().client("athena")
    results, total = [], len(STRATEGIES) * len(SCALES) * len(QUERIES) * (REPS + 1)
    done = 0
    for strat, pattern in STRATEGIES.items():
        for s in SCALES:
            obj = pattern.format(s=s)
            for qname, qsql in QUERIES.items():
                sql = qsql.format(obj=obj)
                for rep in range(0, REPS + 1):            # rep 0 = échauffement
                    if time.time() - session_start > 3000:  # identifiants valables 1 h : on renouvelle
                        athena, session_start = analyst_session().client("athena"), time.time()
                    q = execute(athena, sql)
                    done += 1
                    st = q.get("Statistics", {})
                    scanned = st.get("DataScannedInBytes", 0)
                    row = {"strategy": strat, "table": obj, "scale": s, "query": qname, "rep": rep,
                           "state": q["Status"]["State"],
                           "engine_ms": st.get("EngineExecutionTimeInMillis"),
                           "total_ms": st.get("TotalExecutionTimeInMillis"),
                           "queue_ms": st.get("QueryQueueTimeInMillis"),
                           "planning_ms": st.get("QueryPlanningTimeInMillis"),
                           "scanned_bytes": scanned,
                           "cost_usd": max(scanned, MIN_BILLED) / 1024**4 * PRICE_PER_TB,
                           "error": q["Status"].get("StateChangeReason")}
                    if rep > 0:
                        results.append(row)
                    print(f"[{done:>3}/{total}] {strat:<17} x{s:<5} {qname:<14} "
                          f"{'warmup' if rep == 0 else 'rep' + str(rep):<7} {row['state']:<9} "
                          f"{row['engine_ms']} ms  {scanned/1024:.1f} Ko")

    out = {"generated_at": datetime.datetime.now().isoformat(), "reps": REPS,
           "strategies": list(STRATEGIES), "queries": QUERIES, "results": results}
    path = os.path.join(PROJECT_DIR, "output", "bench_athena.json")
    json.dump(out, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    failed = sum(r["state"] != "SUCCEEDED" for r in results)
    print(f"\n{len(results)} mesures enregistrées ({failed} échecs) -> {path}")


if __name__ == "__main__":
    main()