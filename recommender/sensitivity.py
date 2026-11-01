# =====================================================================
# sensitivity.py (Phase 4 - étape 4.4) - Analyse de sensibilité
# La recommandation résiste-t-elle à un changement des poids ou du volume ?
#   A. Variation d'un poids à la fois (x0,5 à x2)
#   B. Profils de décideur (sécurité, performance, coût, simplicité, fonctions)
#   C. Monte-Carlo : 1000 jeux de poids aléatoires (graine fixe = reproductible)
#   D. Volume : x1, x100, x1000
# Pour chaque cas : stratégie gagnante selon WSM et selon TOPSIS.
# Sortie : output/sensitivity_result.json
# =====================================================================
import sys, os, json, random
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PROJECT_DIR
from weights import BASE_WEIGHTS, contextual_weights
from wsm import wsm
from topsis import topsis

OUT = os.path.join(PROJECT_DIR, "output")
dm = json.load(open(os.path.join(OUT, "decision_matrix.json"), encoding="utf-8"))
ref_w = json.load(open(os.path.join(OUT, "wsm_result.json"), encoding="utf-8"))["weights"]
short = {"S1_lakeformation": "LakeFormation", "S2_spark": "Spark", "S3_vues": "Vues"}


def winners(matrix, weights):
    w = wsm({"matrix": matrix, "criteria": dm["criteria"]}, weights)[3][0]
    t = topsis(matrix, dm["criteria"], weights)[4][0]
    return w, t


def renorm(w):
    s = sum(w.values())
    return {k: v / s for k, v in w.items()}


result = {}

# --- A. Un poids à la fois --------------------------------------------
print("=== A. VARIATION D'UN POIDS (les autres renormalisés) ===")
print(f"{'Critère':<16}" + "".join(f"{'x' + str(f):>30}" for f in (0.5, 1.5, 2.0)))
result["one_at_a_time"] = {}
for c in ref_w:
    line, res = f"{c:<16}", {}
    for f in (0.5, 1.5, 2.0):
        w = renorm({**ref_w, c: ref_w[c] * f})
        ww, tt = winners(dm["matrix"], w)
        res[str(f)] = {"wsm": ww, "topsis": tt}
        line += f"{short[ww] + '/' + short[tt]:>30}"
    result["one_at_a_time"][c] = res
    print(line)
print("(lecture : gagnant WSM / gagnant TOPSIS)")

# --- B. Profils de décideur -------------------------------------------
PROFILES = {"Sécurité d'abord": "C4_robustesse", "Performance d'abord": "C1_latence_ms",
            "Coût d'abord": "C2_cout_usd", "Simplicité d'abord": "C6_complexite",
            "Fonctionnalités d'abord": "C5_fonctions"}
print("\n=== B. PROFILS DE DÉCIDEUR (critère dominant = 50 % du poids) ===")
result["profiles"] = {}
for name, c in PROFILES.items():
    w = {k: (0.5 if k == c else 0.5 / (len(BASE_WEIGHTS) - 1)) for k in BASE_WEIGHTS}
    ww, tt = winners(dm["matrix"], w)
    result["profiles"][name] = {"wsm": ww, "topsis": tt}
    print(f"  {name:<26} WSM -> {short[ww]:<14} TOPSIS -> {short[tt]}")

# --- C. Monte-Carlo ----------------------------------------------------
random.seed(42)
N = 1000
cw, ct, agree = Counter(), Counter(), 0
for _ in range(N):
    w = renorm({k: random.expovariate(1.0) for k in BASE_WEIGHTS})   # poids aléatoires (Dirichlet)
    ww, tt = winners(dm["matrix"], w)
    cw[ww] += 1; ct[tt] += 1; agree += ww == tt
result["monte_carlo"] = {"n": N, "wsm": dict(cw), "topsis": dict(ct), "agreement": agree / N}
print(f"\n=== C. MONTE-CARLO ({N} jeux de poids aléatoires) ===")
for a in dm["alternatives"]:
    print(f"  {short[a]:<14} gagne {cw[a] / N:>6.1%} (WSM)   {ct[a] / N:>6.1%} (TOPSIS)")
print(f"  Accord WSM / TOPSIS sur le gagnant : {agree / N:.1%}")

# --- E. Point de bascule sur la robustesse ---------------------------
# Poids minimal de C4 à partir duquel Lake Formation gagne avec les DEUX modèles
others = {k: v for k, v in ref_w.items() if k != "C4_robustesse"}
tipping = None
for i in range(5, 96):
    w4 = i / 100
    w = {**{k: v / sum(others.values()) * (1 - w4) for k, v in others.items()}, "C4_robustesse": w4}
    if winners(dm["matrix"], w) == ("S1_lakeformation", "S1_lakeformation"):
        tipping = w4
        break
result["tipping_point_robustness"] = tipping
print(f"\n=== E. POINT DE BASCULE ===\n  Lake Formation est recommandée (WSM et TOPSIS) dès que "
      f"la robustesse pèse au moins {tipping:.0%} (poids actuel : {ref_w['C4_robustesse']:.0%})")

# --- D. Volume ---------------------------------------------------------
print("\n=== D. SELON LE VOLUME (poids contextuels) ===")
result["volume"] = {}
try:
    from build_matrix import matrix_for
    for scale, vclass in ((1, "petite"), (100, "moyenne"), (1000, "grande")):
        w, _ = contextual_weights(dm["context_needs"], vclass)
        ww, tt = winners(matrix_for(scale), w)
        result["volume"][f"x{scale}"] = {"wsm": ww, "topsis": tt}
        print(f"  x{scale:<6} ({vclass:<8}) WSM -> {short[ww]:<14} TOPSIS -> {short[tt]}")
except Exception as e:
    print("  (non calculé :", e, ")")

json.dump(result, open(os.path.join(OUT, "sensitivity_result.json"), "w", encoding="utf-8"),
          indent=2, ensure_ascii=False)
print("\nRésultat : output/sensitivity_result.json")