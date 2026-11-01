# =====================================================================
# weights.py (Phase 4) - Pondération CONTEXTUELLE des critères
# Partagé par le WSM et TOPSIS : les deux modèles utilisent les MÊMES poids,
# pour que leur comparaison soit équitable.
# =====================================================================

# Poids de base (somme = 1) : la sécurité (robustesse) pèse le plus
BASE_WEIGHTS = {
    "C1_latence_ms": 0.15,
    "C2_cout_usd":   0.15,
    "C3_stabilite":  0.10,
    "C4_robustesse": 0.30,
    "C5_fonctions":  0.15,
    "C6_complexite": 0.15,
}


def contextual_weights(needs, volume_class, base=None):
    """Ajuste les poids selon le contexte (objectif 1), puis renormalise à 1.
    Chaque règle est explicite pour pouvoir être justifiée."""
    w = dict(base or BASE_WEIGHTS)
    rules = []
    if needs.get("urgency") == "ELEVEE":
        w["C4_robustesse"] *= 1.5
        rules.append("Urgence élevée (données sensibles exposées) : robustesse x1,5")
    if needs.get("generalization"):
        w["C5_fonctions"] *= 1.3
        rules.append("Quasi-identifiants présents (âge, genre) : richesse fonctionnelle x1,3")
    if volume_class == "grande":
        w["C1_latence_ms"] *= 1.2
        w["C2_cout_usd"] *= 1.2
        rules.append("Grand volume : temps de réponse et coût x1,2")
    total = sum(w.values())
    return {k: round(v / total, 4) for k, v in w.items()}, rules