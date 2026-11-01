# =====================================================================
# summarize.py (Phase 3 - étape 3.5)
# Fusionne les mesures Athena (S0, S1, S3) et Spark (S2), puis calcule :
#   médiane, P95, écart-type, coût moyen, surcoût par rapport à S0
# Sorties : output/benchmark_results.json (toutes les mesures)
#           output/benchmark_summary.csv  (tableau de synthèse, ouvrable dans Excel)
# =====================================================================
import sys, os, json, csv, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PROJECT_DIR

OUT = os.path.join(PROJECT_DIR, "output")
athena = json.load(open(os.path.join(OUT, "bench_athena.json"), encoding="utf-8"))
spark = json.load(open(os.path.join(OUT, "bench_s2_spark.json"), encoding="utf-8"))

rows = [r for r in athena["results"] if r["state"] == "SUCCEEDED"]
# Coût Spark par requête = coût du job réparti sur toutes les exécutions (échauffements compris)
n_exec = len(spark["results"]) * (1 + 1 / max(r["rep"] for r in spark["results"]))
spark_cost_per_query = spark["job"]["cost_usd"] / n_exec
for r in spark["results"]:
    rows.append({**r, "strategy": "S2_spark", "total_ms": r["engine_ms"],
                 "scanned_bytes": None, "cost_usd": spark_cost_per_query})


def p95(v):
    return sorted(v)[max(0, int(round(0.95 * len(v))) - 1)]


groups = {}
for r in rows:
    groups.setdefault((r["strategy"], r["scale"], r["query"]), []).append(r)

summary = []
for (strat, scale, query), g in sorted(groups.items(), key=lambda k: (k[0][1], k[0][2], k[0][0])):
    t = [x["engine_ms"] for x in g]
    scanned = [x["scanned_bytes"] for x in g if x["scanned_bytes"] is not None]
    summary.append({"strategy": strat, "scale": scale, "query": query, "n": len(t),
                    "median_ms": statistics.median(t), "p95_ms": p95(t),
                    "stdev_ms": round(statistics.stdev(t), 1) if len(t) > 1 else 0,
                    "scanned_kb": round(statistics.mean(scanned) / 1024, 1) if scanned else None,
                    "cost_usd": round(statistics.mean(x["cost_usd"] for x in g), 8)})

# Surcoût en temps par rapport à la référence S0 (même volume, même requête)
ref = {(x["scale"], x["query"]): x["median_ms"] for x in summary if x["strategy"] == "S0_reference"}
for x in summary:
    base = ref.get((x["scale"], x["query"]))
    x["overhead_pct"] = round(100 * (x["median_ms"] - base) / base, 1) if base else None

json.dump({"measures": rows, "summary": summary}, open(os.path.join(OUT, "benchmark_results.json"), "w",
          encoding="utf-8"), indent=2, ensure_ascii=False)
with open(os.path.join(OUT, "benchmark_summary.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(summary[0]), delimiter=";")
    w.writeheader(); w.writerows(summary)

print(f"{'Volume':<7} {'Requête':<14} {'Stratégie':<17} {'Médiane':>8} {'P95':>7} {'Surcoût':>8} {'Scan Ko':>8}")
for x in summary:
    oh = f"{x['overhead_pct']:+.0f}%" if x["overhead_pct"] is not None else "-"
    sc = x["scanned_kb"] if x["scanned_kb"] is not None else "-"
    print(f"x{x['scale']:<6} {x['query']:<14} {x['strategy']:<17} {x['median_ms']:>6.0f}ms "
          f"{x['p95_ms']:>5}ms {oh:>8} {sc:>8}")
print("\nFichiers : output/benchmark_results.json et output/benchmark_summary.csv")