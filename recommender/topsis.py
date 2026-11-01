# =====================================================================
# topsis.py (Phase 4 - étape 4.3) - Modèle de comparaison : TOPSIS
# (Technique for Order of Preference by Similarity to Ideal Solution)
#   1. Normalisation vectorielle : r = x / racine(somme des x²)
#   2. Pondération : v = poids x r            (MÊMES poids que le WSM)
#   3. Solution idéale A+ (meilleure valeur de chaque critère)
#      Solution anti-idéale A- (pire valeur de chaque critère)
#   4. Distances euclidiennes D+ (vers A+) et D- (vers A-)
#   5. Proximité relative : C = D- / (D+ + D-)   (1 = idéal, 0 = pire)
# Puis comparaison avec le classement du WSM.
# Sortie : output/topsis_result.json
# =====================================================================
import sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PROJECT_DIR

OUT = os.path.join(PROJECT_DIR, "output")


def topsis(matrix, criteria, weights):
    alts = list(matrix)
    v = {a: {} for a in alts}
    for c in weights:
        norm = math.sqrt(sum(matrix[a][c] ** 2 for a in alts))
        for a in alts:
            v[a][c] = weights[c] * matrix[a][c] / norm
    best, worst = {}, {}
    for c, meta in criteria.items():
        col = [v[a][c] for a in alts]
        best[c], worst[c] = (max(col), min(col)) if meta["direction"] == "max" else (min(col), max(col))
    d_plus = {a: math.sqrt(sum((v[a][c] - best[c]) ** 2 for c in weights)) for a in alts}
    d_minus = {a: math.sqrt(sum((v[a][c] - worst[c]) ** 2 for c in weights)) for a in alts}
    closeness = {a: round(d_minus[a] / (d_plus[a] + d_minus[a]), 4) for a in alts}
    ranking = sorted(closeness, key=closeness.get, reverse=True)
    return v, d_plus, d_minus, closeness, ranking


def spearman(r1, r2):
    """Corrélation de rang de Spearman entre deux classements (1 = identiques)."""
    n = len(r1)
    d2 = sum((r1.index(a) - r2.index(a)) ** 2 for a in r1)
    return round(1 - 6 * d2 / (n * (n ** 2 - 1)), 3)


if __name__ == "__main__":
    dm = json.load(open(os.path.join(OUT, "decision_matrix.json"), encoding="utf-8"))
    wsm = json.load(open(os.path.join(OUT, "wsm_result.json"), encoding="utf-8"))
    weights = wsm["weights"]                                 # mêmes poids que le WSM
    v, dp, dmn, cl, ranking = topsis(dm["matrix"], dm["criteria"], weights)

    print("=== TOPSIS ===")
    print(f"{'Stratégie':<28}{'D+ (idéal)':>12}{'D- (anti-idéal)':>17}{'Proximité C':>13}")
    for a in ranking:
        print(f"{dm['alternatives'][a]:<28}{dp[a]:>12.4f}{dmn[a]:>17.4f}{cl[a]:>13.4f}")

    rho = spearman(wsm["ranking"], ranking)
    same_top = wsm["ranking"][0] == ranking[0]
    print("\n=== COMPARAISON WSM / TOPSIS ===")
    print(f"{'Rang':<6}{'WSM':<30}{'TOPSIS':<30}")
    for i in range(len(ranking)):
        print(f"{i+1:<6}{dm['alternatives'][wsm['ranking'][i]]:<30}{dm['alternatives'][ranking[i]]:<30}")
    print(f"\nMême stratégie recommandée : {'OUI' if same_top else 'NON'}")
    print(f"Corrélation de Spearman    : {rho}  (1 = classements identiques)")

    json.dump({"model": "TOPSIS", "weights": weights, "weighted_normalized": v,
               "d_plus": dp, "d_minus": dmn, "closeness": cl, "ranking": ranking,
               "recommended": ranking[0],
               "comparison": {"wsm_ranking": wsm["ranking"], "same_recommendation": same_top,
                              "spearman": rho}},
              open(os.path.join(OUT, "topsis_result.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("Résultat : output/topsis_result.json")