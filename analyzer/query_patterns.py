# =====================================================================
# query_patterns.py (Objectif 1 - étape 2.4)
# Analyse l'historique des requêtes Athena du workgroup pour en déduire
# les habitudes d'usage :
#   - type de requêtes (agrégation / sélection de lignes détaillées)
#   - colonnes les plus consultées, dont les colonnes SENSIBLES
#   - usage du filtre par partition (country)
#   - temps moyen et volume scanné
# Sortie : output/context_queries.json
# =====================================================================
import sys, os, re, json
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boto3
from config import REGION, PROJECT_DIR

WG = "lakehouse-memoire"
MAX_QUERIES = 200                       # historique analysé (les plus récentes)
athena = boto3.client("athena", region_name=REGION)
AGG = re.compile(r"\b(count|sum|avg|min|max|approx_distinct)\s*\(|\bgroup\s+by\b", re.I)


def history():
    """Récupère les identifiants des dernières requêtes du workgroup,
    puis leurs détails par lots de 50 (limite de l'API)."""
    ids, token = [], None
    while len(ids) < MAX_QUERIES:
        kw = {"WorkGroup": WG, "MaxResults": 50}
        if token:
            kw["NextToken"] = token
        r = athena.list_query_executions(**kw)
        ids += r["QueryExecutionIds"]
        token = r.get("NextToken")
        if not token:
            break
    queries = []
    for i in range(0, len(ids), 50):
        queries += athena.batch_get_query_execution(QueryExecutionIds=ids[i:i + 50])["QueryExecutions"]
    return [q for q in queries if q["Status"]["State"] == "SUCCEEDED"
            and q.get("StatementType") == "DML"]          # uniquement les SELECT réussis


def analyze():
    sens = json.load(open(os.path.join(PROJECT_DIR, "output", "context_sensitive.json"), encoding="utf-8"))
    all_cols = [c["column"] for c in sens["columns"]]
    sensitive = {c["column"] for c in sens["columns"] if c["level"] in ("ELEVE", "MOYEN")}
    partition_keys = [c["column"] for c in sens["columns"] if c.get("partition_key")]

    qs = history()
    col_usage, kinds = Counter(), Counter()
    touches_sensitive = partition_filtered = 0
    times, scanned = [], []

    for q in qs:
        sql = q["Query"].lower()
        kind = "agregation" if AGG.search(sql) else "selection_detaillee"
        kinds[kind] += 1
        used = {c for c in all_cols if re.search(rf"\b{c}\b", sql)}
        if "select *" in sql:                       # SELECT * = toutes les colonnes
            used = set(all_cols)
        col_usage.update(used)
        if used & sensitive:
            touches_sensitive += 1
        where = sql.split("where", 1)[1] if "where" in sql else ""
        if any(re.search(rf"\b{p}\b", where) for p in partition_keys):
            partition_filtered += 1
        st = q["Statistics"]
        times.append(st.get("EngineExecutionTimeInMillis", 0))
        scanned.append(st.get("DataScannedInBytes", 0))

    n = len(qs) or 1
    out = {
        "workgroup": WG,
        "queries_analyzed": len(qs),
        "query_types": dict(kinds),
        "aggregation_ratio": round(kinds["agregation"] / n, 2),
        "sensitive_access_ratio": round(touches_sensitive / n, 2),
        "partition_filter_ratio": round(partition_filtered / n, 2),
        "top_columns": col_usage.most_common(10),
        "sensitive_columns_accessed": {c: col_usage[c] for c in sensitive if col_usage[c]},
        "avg_engine_ms": round(sum(times) / n),
        "avg_scanned_kb": round(sum(scanned) / n / 1024, 1),
    }

    print(f"Requêtes analysées          : {out['queries_analyzed']}")
    print(f"Types                       : {out['query_types']}")
    print(f"Part d'agrégations          : {out['aggregation_ratio']:.0%}")
    print(f"Part touchant du sensible   : {out['sensitive_access_ratio']:.0%}")
    print(f"Part filtrée par partition  : {out['partition_filter_ratio']:.0%}")
    print(f"Colonnes les plus utilisées : {out['top_columns'][:5]}")
    print(f"Colonnes sensibles lues     : {out['sensitive_columns_accessed']}")
    print(f"Temps moteur moyen          : {out['avg_engine_ms']} ms | scan moyen : {out['avg_scanned_kb']} Ko")

    path = os.path.join(PROJECT_DIR, "output", "context_queries.json")
    json.dump(out, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("Contexte enregistré :", path)


if __name__ == "__main__":
    analyze()