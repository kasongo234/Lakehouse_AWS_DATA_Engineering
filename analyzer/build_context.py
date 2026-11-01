# =====================================================================
# build_context.py (Objectif 1 - étape 2.5)
# Assemble les 4 analyses (catalogue, sensibilité, sécurité, requêtes)
# en UN contexte unique, et le traduit en indicateurs exploitables par
# le moteur de recommandation (objectif 3).
# Sortie : output/context.json
# =====================================================================
import sys, os, json, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PROJECT_DIR

OUT = os.path.join(PROJECT_DIR, "output")
load = lambda name: json.load(open(os.path.join(OUT, name), encoding="utf-8"))


def volume_class(rows):
    """Classe de volumétrie (seuils du protocole de benchmark)."""
    if rows is None:
        return "inconnue"
    if rows < 100_000:
        return "petite"
    if rows < 5_000_000:
        return "moyenne"
    return "grande"


def build():
    catalog = load("context_catalog.json")
    sensitive = load("context_sensitive.json")
    security = load("context_security.json")
    queries = load("context_queries.json")

    high = [c["column"] for c in sensitive["columns"] if c["level"] == "ELEVE"]
    medium = [c["column"] for c in sensitive["columns"] if c["level"] == "MOYEN"]
    row_keys = [c["column"] for c in sensitive["columns"] if c.get("partition_key")]

    tables = []
    for t in catalog["tables"]:
        sec = security["tables"].get(t["name"], {})
        tables.append({
            "name": t["name"],
            "rows": t["rows"],
            "size_mb": t["size_mb"],
            "volume_class": volume_class(t["rows"]),
            "partitioned_by": t["partition_keys"],
            "open_to_all_iam": sec.get("open_to_all_iam"),
            "granular_security": sec.get("column_level_security") or sec.get("row_level_security"),
        })

    # --- Indicateurs normalisés (0 à 1) utilisés par le moteur de recommandation
    indicators = {
        "sensitivity_ratio": sensitive["sensitivity_ratio"],           # part de colonnes sensibles
        "high_sensitivity_columns": len(high),
        "sensitive_access_ratio": queries["sensitive_access_ratio"],   # requêtes touchant du sensible
        "aggregation_ratio": queries["aggregation_ratio"],             # usage analytique
        "row_filter_relevance": 1.0 if row_keys else 0.0,              # une clé de cloisonnement existe
        "partition_filter_ratio": queries["partition_filter_ratio"],
        "current_protection": 1.0 if security["diagnostic"]["granular_security_in_place"] else 0.0,
    }

    # --- Besoins déduits (règles explicites, donc explicables au jury)
    needs = {
        "column_security": len(high) > 0,
        "row_security": bool(row_keys),
        "generalization": len(medium) > 0,
        "urgency": "ELEVEE" if indicators["current_protection"] == 0 and indicators["sensitive_access_ratio"] > 0.3
                   else "NORMALE",
    }

    context = {
        "generated_at": datetime.datetime.now().isoformat(),
        "database": catalog["database"],
        "tables": tables,
        "sensitive_columns": {"eleve": high, "moyen": medium, "row_filter_keys": row_keys},
        "security_state": {
            "iam_compatibility_mode": security["lake_formation"]["iam_compatibility_mode"],
            "curated_bucket_registered": security["lake_formation"]["curated_bucket_registered"],
            "lake_formation_ready": security["diagnostic"]["lake_formation_ready"],
            "diagnostic": security["diagnostic"]["level"],
        },
        "usage": {k: queries[k] for k in ("queries_analyzed", "aggregation_ratio",
                                           "sensitive_access_ratio", "avg_engine_ms", "avg_scanned_kb")},
        "indicators": indicators,
        "needs": needs,
    }

    path = os.path.join(OUT, "context.json")
    json.dump(context, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

    # --- Synthèse lisible
    print("=== CONTEXTE DU LAKEHOUSE ===")
    for t in tables:
        print(f"{t['name']:<18} {t['rows']:>10} lignes  {t['size_mb']:>8} Mo  volume={t['volume_class']}")
    print(f"\nColonnes sensibles (élevé) : {high}")
    print(f"Quasi-identifiants (moyen) : {medium}")
    print(f"Clé de filtrage par ligne  : {row_keys}")
    print(f"État de la sécurité        : {context['security_state']['diagnostic']}")
    print(f"Indicateurs                : {indicators}")
    print(f"Besoins déduits            : {needs}")
    print("\nContexte unique enregistré :", path)


if __name__ == "__main__":
    build()