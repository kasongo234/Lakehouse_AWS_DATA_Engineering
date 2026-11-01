# =====================================================================
# sensitive_detector.py (Objectif 1 - étape 2.2)
# Détecte automatiquement les colonnes sensibles d'une table avec 2 signaux :
#   1. le NOM de la colonne (dictionnaire de motifs, catégories RGPD)
#   2. le PROFIL des données (cardinalité mesurée via Athena)
# Sortie : output/context_sensitive.json
# =====================================================================
import sys, os, re, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boto3
from config import REGION, PROJECT_DIR

WG, DB = "lakehouse-memoire", "lakehouse_curated"
athena = boto3.client("athena", region_name=REGION)

# --- 1. Dictionnaire de motifs : (catégorie, niveau, motifs du nom) -----
RULES = [
    ("identifiant_direct", "ELEVE",  r"(^|_)(id|customer_id|client_id|user_id|iban|email|phone|tel|ssn|passport|name|nom)($|_)"),
    ("financier",          "ELEVE",  r"(balance|salary|salaire|income|revenu|amount|montant|credit_score|card_number)"),
    ("quasi_identifiant",  "MOYEN",  r"(^|_)(age|gender|sexe|birth|naissance|zip|postal|city|ville)($|_)"),
    ("localisation",       "FAIBLE", r"(country|pays|region)"),
    ("technique",          "AUCUN",  r"(ingest|source_file|_ts$|timestamp)"),
]

# Traitement recommandé selon la catégorie (utilisé plus tard par les stratégies)
TREATMENT = {
    "identifiant_direct": "hachage ou masquage complet",
    "financier":          "masquage ou exclusion de colonne",
    "quasi_identifiant":  "généralisation (ex. tranches d'âge)",
    "localisation":       "clé de filtrage par ligne (row-level)",
    "technique":          "aucun",
    "non_sensible":       "aucun",
}


def classify_by_name(col):
    """Retourne (catégorie, niveau) selon le nom de la colonne."""
    for category, level, pattern in RULES:
        if re.search(pattern, col.lower()):
            return category, level
    return "non_sensible", "AUCUN"


def athena_query(sql):
    """Exécute une requête et renvoie les lignes (sans l'en-tête)."""
    qid = athena.start_query_execution(QueryString=sql, WorkGroup=WG,
                                       QueryExecutionContext={"Database": DB})["QueryExecutionId"]
    while True:
        st = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]["State"]
        if st in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(0.5)
    if st != "SUCCEEDED":
        raise RuntimeError(f"Requête échouée : {sql}")
    rows = athena.get_query_results(QueryExecutionId=qid)["ResultSet"]["Rows"]
    return [[c.get("VarCharValue") for c in r["Data"]] for r in rows[1:]]


def profile(table, columns):
    """2e signal : cardinalité de chaque colonne (nb de valeurs distinctes / nb de lignes).
    Une seule requête pour toutes les colonnes -> coût minimal."""
    exprs = ", ".join(f'approx_distinct("{c}")' for c in columns)
    row = athena_query(f"SELECT COUNT(*), {exprs} FROM {table}")[0]
    total = int(row[0])
    return total, {c: int(v) / total for c, v in zip(columns, row[1:])}


def detect(table="bank_churn_x1"):
    # Colonnes lues dans le contexte produit à l'étape 2.1
    ctx = json.load(open(os.path.join(PROJECT_DIR, "output", "context_catalog.json"), encoding="utf-8"))
    tinfo = next(t for t in ctx["tables"] if t["name"] == table)
    columns = [c["name"] for c in tinfo["columns"]]

    total, card = profile(table, columns)
    results = []
    for c in columns:
        category, level = classify_by_name(c)
        ratio = round(card[c], 4)
        # Règle de profil : valeurs quasi toutes uniques -> identifiant probable
        if ratio > 0.95 and category not in ("identifiant_direct", "technique", "financier"):
            category, level = "identifiant_direct", "ELEVE"
        results.append({"column": c, "category": category, "level": level,
                        "cardinality_ratio": ratio, "treatment": TREATMENT[category]})
        print(f"{c:<18} {level:<7} {category:<20} cardinalité={ratio:<7} -> {TREATMENT[category]}")

    # Colonnes de partition : candidates naturelles au filtrage par ligne
    for p in tinfo["partition_keys"]:
        results.append({"column": p, "category": "localisation", "level": "FAIBLE",
                        "cardinality_ratio": None, "treatment": TREATMENT["localisation"],
                        "partition_key": True})
        print(f"{p:<18} FAIBLE  localisation (partition) -> {TREATMENT['localisation']}")

    summary = {lvl: sum(r["level"] == lvl for r in results) for lvl in ("ELEVE", "MOYEN", "FAIBLE", "AUCUN")}
    out = {"table": table, "rows_profiled": total, "columns": results, "summary": summary,
           "sensitivity_ratio": round((summary["ELEVE"] + summary["MOYEN"]) / len(results), 2)}
    path = os.path.join(PROJECT_DIR, "output", "context_sensitive.json")
    json.dump(out, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"\nRésumé : {summary}  | part de colonnes sensibles = {out['sensitivity_ratio']:.0%}")
    print("Contexte enregistré :", path)


if __name__ == "__main__":
    detect(sys.argv[1] if len(sys.argv) > 1 else "bank_churn_x1")