# =====================================================================
# build_matrix.py (Phase 4 - étape 4.1)
# Construit la MATRICE DE DÉCISION : 3 alternatives (stratégies) x 6 critères,
# à partir des résultats MESURÉS (benchmark + tests de sécurité) et du contexte.
#   Usage : python recommender\build_matrix.py          (volume du contexte)
#           python recommender\build_matrix.py 100      (forcer un volume : 1, 100, 1000)
# Sortie : output/decision_matrix.json
# =====================================================================
import sys, os, json, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PROJECT_DIR

OUT = os.path.join(PROJECT_DIR, "output")
load = lambda f: json.load(open(os.path.join(OUT, f), encoding="utf-8"))

ALTERNATIVES = {"S1_lakeformation": "AWS Lake Formation",
                "S2_spark": "Masquage applicatif Spark",
                "S3_vues": "Vues Athena sécurisées"}

# Critères : (libellé, sens) -> "min" = plus petit est meilleur, "max" = plus grand est meilleur
CRITERIA = {
    "C1_latence_ms":   ("Temps de réponse médian (ms)", "min"),
    "C2_cout_usd":     ("Coût par requête ($)", "min"),
    "C3_stabilite":    ("Instabilité P95 / médiane", "min"),
    "C4_robustesse":   ("Robustesse aux fuites (0-1)", "max"),
    "C5_fonctions":    ("Richesse fonctionnelle (0-4)", "max"),
    "C6_complexite":   ("Complexité de mise en oeuvre (1-5)", "min"),
}

# C6 : échelle ordinale justifiée (1 = très simple, 5 = très complexe)
COMPLEXITY = {
    "S1_lakeformation": (3, "Configuration par API, sans code ; mais enregistrement du bucket, "
                            "retrait des droits IAM et gestion des filtres par table"),
    "S2_spark":         (4, "Code applicatif à écrire, tester et maintenir ; job et cluster à gérer"),
    "S3_vues":          (2, "Une requête SQL CREATE VIEW par table ; aucun service supplémentaire"),
}


def target_scale(ctx):
    """Volume de référence : celui de la plus grande table du contexte (cas de production)."""
    t = max(ctx["tables"], key=lambda x: x["rows"] or 0)
    return int(t["name"].split("_x")[-1]), t["volume_class"]


def matrix_for(scale):
    """Matrice de décision pour un volume donné (fonction réutilisée par l'analyse de sensibilité)."""
    summary = load("benchmark_results.json")["summary"]
    security = load("security_results_hardened.json")
    matrix = {}
    for alt in ALTERNATIVES:
        rows = [x for x in summary if x["strategy"] == alt and x["scale"] == scale]
        sec = security[alt]
        matrix[alt] = {
            "C1_latence_ms": round(statistics.mean(x["median_ms"] for x in rows)),
            "C2_cout_usd":   round(statistics.mean(x["cost_usd"] for x in rows), 7),
            "C3_stabilite":  round(statistics.mean(x["p95_ms"] / x["median_ms"] for x in rows), 3),
            "C4_robustesse": sec["robustness"],
            # lignes + colonnes (toutes les stratégies) + hachage + généralisation
            "C5_fonctions":  2 + int(sec["pseudonymisation"]) + int(sec["generalisation"]),
            "C6_complexite": COMPLEXITY[alt][0],
        }
    return matrix


def build(scale=None):
    ctx = load("context.json")
    vclass = None
    if scale is None:
        scale, vclass = target_scale(ctx)
    matrix = matrix_for(scale)

    out = {"scale": scale, "volume_class": vclass, "alternatives": ALTERNATIVES,
           "criteria": {k: {"label": v[0], "direction": v[1]} for k, v in CRITERIA.items()},
           "complexity_justification": {k: v[1] for k, v in COMPLEXITY.items()},
           "matrix": matrix,
           "context_needs": ctx["needs"], "context_indicators": ctx["indicators"]}
    json.dump(out, open(os.path.join(OUT, "decision_matrix.json"), "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)

    print(f"=== MATRICE DE DÉCISION (volume x{scale}) ===\n")
    print(f"{'Critère':<38}{'Sens':<6}" + "".join(f"{a.split('_')[0]:>12}" for a in ALTERNATIVES))
    for c, (label, d) in CRITERIA.items():
        print(f"{label:<38}{d:<6}" + "".join(f"{matrix[a][c]:>12}" for a in ALTERNATIVES))
    print("\nS1 = Lake Formation | S2 = Spark | S3 = Vues Athena")
    print("Matrice enregistrée : output/decision_matrix.json")


if __name__ == "__main__":
    build(int(sys.argv[1]) if len(sys.argv) > 1 else None)