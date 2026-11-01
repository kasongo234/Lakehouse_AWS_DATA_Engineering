# =====================================================================
# wsm.py (Phase 4 - étape 4.2) - Modèle principal : SCORE PONDÉRÉ (WSM)
#   1. Normalisation linéaire de chaque critère entre 0 et 1
#        critère à maximiser : r = x / max(x)
#        critère à minimiser : r = min(x) / x
#   2. Score de chaque stratégie : S = somme( poids_j x r_j )
#   3. Classement + contribution de chaque critère (explicabilité)
# Sortie : output/wsm_result.json
# =====================================================================
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PROJECT_DIR
from weights import contextual_weights

OUT = os.path.join(PROJECT_DIR, "output")


def normalize(matrix, criteria):
    alts = list(matrix)
    norm = {a: {} for a in alts}
    for c, meta in criteria.items():
        col = [matrix[a][c] for a in alts]
        for a in alts:
            x = matrix[a][c]
            norm[a][c] = round(x / max(col) if meta["direction"] == "max" else min(col) / x, 4)
    return norm


def wsm(dm, weights):
    norm = normalize(dm["matrix"], dm["criteria"])
    contrib = {a: {c: round(weights[c] * norm[a][c], 4) for c in weights} for a in norm}
    scores = {a: round(sum(v.values()), 4) for a, v in contrib.items()}
    ranking = sorted(scores, key=scores.get, reverse=True)
    return norm, contrib, scores, ranking


if __name__ == "__main__":
    dm = json.load(open(os.path.join(OUT, "decision_matrix.json"), encoding="utf-8"))
    weights, rules = contextual_weights(dm["context_needs"], dm["volume_class"])
    norm, contrib, scores, ranking = wsm(dm, weights)

    print("=== POIDS CONTEXTUELS ===")
    for r in rules:
        print("  -", r)
    for c, w in weights.items():
        print(f"  {dm['criteria'][c]['label']:<38} {w:.3f}")

    print("\n=== MATRICE NORMALISÉE (0 à 1, 1 = meilleur) ===")
    print(f"{'Critère':<38}" + "".join(f"{a.split('_')[0]:>9}" for a in norm))
    for c in weights:
        print(f"{dm['criteria'][c]['label']:<38}" + "".join(f"{norm[a][c]:>9.3f}" for a in norm))

    print("\n=== SCORES WSM ===")
    # Avantage décisif : critère où la stratégie devance le plus la moyenne des autres
    advantage = {}
    for a in ranking:
        others = [o for o in ranking if o != a]
        gap = {c: contrib[a][c] - sum(contrib[o][c] for o in others) / len(others) for c in weights}
        advantage[a] = max(gap, key=gap.get)
    for i, a in enumerate(ranking, 1):
        print(f"  {i}. {dm['alternatives'][a]:<28} score = {scores[a]:.4f}   "
              f"(avantage décisif : {dm['criteria'][advantage[a]]['label']})")

    json.dump({"model": "WSM", "weights": weights, "weight_rules": rules, "normalized": norm,
               "contributions": contrib, "scores": scores, "ranking": ranking,
               "recommended": ranking[0], "decisive_criterion": advantage},
              open(os.path.join(OUT, "wsm_result.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("\nRecommandation WSM :", dm["alternatives"][ranking[0]])
    print("Résultat : output/wsm_result.json")