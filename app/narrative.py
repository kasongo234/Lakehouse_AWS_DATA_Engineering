# =====================================================================
# narrative.py (Phase 5 - étape 5.1) - Recommandation en LANGAGE NATUREL
# Traduit les résultats chiffrés (contexte, WSM, TOPSIS, sensibilité, tests
# de fuite) en un texte compréhensible par un non-expert.
# Génération par GABARITS (templates) : déterministe, reproductible et explicable.
# Sorties : output/recommendation.json (sections, réutilisées par HTML/Streamlit)
#           output/recommendation.txt  (texte complet)
#           output/recommendation_voice.txt (version courte pour Amazon Polly)
# =====================================================================
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PROJECT_DIR

OUT = os.path.join(PROJECT_DIR, "output")
load = lambda f: json.load(open(os.path.join(OUT, f), encoding="utf-8"))

# Explications « grand public » de chaque critère
PLAIN = {   # atouts formulés en groupe nominal (s'accorde avec toutes les stratégies)
    "C1_latence_ms": "des temps de réponse rapides",
    "C2_cout_usd":   "le coût d'utilisation le plus faible",
    "C3_stabilite":  "des temps de réponse réguliers",
    "C4_robustesse": "la meilleure résistance aux tentatives d'accès non autorisé",
    "C5_fonctions":  "la capacité à masquer et généraliser les données (par exemple remplacer l'âge par une tranche d'âge)",
    "C6_complexite": "une mise en place et une maintenance simples",
}
NAMES = {"S1_lakeformation": "AWS Lake Formation", "S2_spark": "le masquage applicatif Spark",
         "S3_vues": "les vues Athena sécurisées"}
ACTIONS = {
    "S1_lakeformation": ["Enregistrer l'emplacement S3 des données dans Lake Formation.",
                         "Retirer l'accès IAM implicite (IAM_ALLOWED_PRINCIPALS) sur les tables sensibles.",
                         "Créer un filtre de données par profil d'utilisateur (lignes et colonnes autorisées).",
                         "Retirer aux utilisateurs l'accès direct aux fichiers S3.",
                         "Pour hacher ou généraliser certaines colonnes, compléter par une vue construite au-dessus des tables gouvernées."],
    "S3_vues": ["Créer une vue par profil d'utilisateur, avec hachage, généralisation et filtre.",
                "Interdire l'accès direct aux tables sources (sinon la vue peut être contournée).",
                "Versionner les définitions de vues pour suivre leurs évolutions."],
    "S2_spark": ["Centraliser les règles de masquage dans une bibliothèque de code testée.",
                 "Restreindre strictement l'accès au rôle d'exécution du job.",
                 "Prévoir le coût du démarrage du cluster pour chaque traitement."],
}


def pct(x):
    return f"{round(100 * x)} %"


def num(x):
    return f"{x:.2f}".replace(".", ",")          # 0.86 -> 0,86 (format français)


def cap(t):
    return t[0].upper() + t[1:]                  # majuscule initiale sans toucher au reste


def build():
    ctx, dm = load("context.json"), load("decision_matrix.json")
    wsm, top, sens = load("wsm_result.json"), load("topsis_result.json"), load("sensitivity_result.json")
    sec = load("security_results_hardened.json")

    best = wsm["recommended"]
    second = wsm["ranking"][1]
    agree = top["comparison"]["same_recommendation"]
    big = max(ctx["tables"], key=lambda t: t["rows"] or 0)
    sens_cols = ", ".join(ctx["sensitive_columns"]["eleve"])
    quasi = ", ".join(ctx["sensitive_columns"]["moyen"])
    usage = ctx["usage"]

    # --- 1. Situation ---------------------------------------------------
    rows_txt = f"{big['rows']:,}".replace(",", " ")            # 10000000 -> 10 000 000
    situation = (
        f"Le Lakehouse analysé contient {len(ctx['tables'])} tables, la plus grande comptant "
        f"{rows_txt} lignes. L'outil a détecté {len(ctx['sensitive_columns']['eleve'])} colonnes très sensibles ({sens_cols}) "
        f"et {len(ctx['sensitive_columns']['moyen'])} informations pouvant permettre d'identifier une personne "
        f"({quasi}). Aujourd'hui, aucune protection fine n'est en place : {pct(usage['sensitive_access_ratio'])} "
        f"des requêtes observées lisent des données sensibles. La situation est jugée "
        f"{'urgente' if ctx['needs']['urgency'] == 'ELEVEE' else 'à surveiller'}.")

    # --- 2. Recommandation ----------------------------------------------
    decisive = wsm["decisive_criterion"][best]
    recommendation = (
        f"La stratégie recommandée est {NAMES[best]}. Elle obtient le meilleur score avec les deux méthodes "
        f"de calcul utilisées (score pondéré : {num(wsm['scores'][best])} ; TOPSIS : {num(top['closeness'][best])})"
        if agree else
        f"La stratégie recommandée est {NAMES[best]} selon le score pondéré ({num(wsm['scores'][best])}), "
        f"mais la méthode TOPSIS préfère {NAMES[top['recommended']]} : les deux options sont très proches")
    recommendation += f". Ce qui la distingue le plus des autres options : {PLAIN[decisive]}."

    # --- 3. Pourquoi (critères les plus favorables, en langage simple) ---
    contrib = wsm["contributions"][best]
    top_criteria = sorted(contrib, key=contrib.get, reverse=True)[:3]
    why = [f"Elle offre {PLAIN[c]}." for c in top_criteria]
    if sec[best]["robustness"] == 1.0:
        why.append("Elle a bloqué les 4 tentatives de fuite testées (autre pays, colonne sensible, "
                   "contournement, accès direct aux fichiers).")

    # --- 4. Alternatives --------------------------------------------------
    pl = second == "S3_vues"                                   # accord : « les vues » est au pluriel
    weak = "" if sec[second]["robustness"] == 1.0 else \
        f", mais {'restent contournables' if pl else 'reste contournable'} dans la configuration testée"
    alternatives = (
        f"En deuxième position, {NAMES[second]} (score {num(wsm['scores'][second])}) "
        f"{'offrent' if pl else 'offre'} {PLAIN[wsm['decisive_criterion'][second]]}{weak}. "
        f"{cap(NAMES[wsm['ranking'][2]])} {'arrivent' if wsm['ranking'][2] == 'S3_vues' else 'arrive'} en dernier"
        + (f", principalement à cause d'un coût environ "
           f"{round(dm['matrix']['S2_spark']['C2_cout_usd'] / dm['matrix']['S1_lakeformation']['C2_cout_usd'])} "
           f"fois plus élevé par requête." if wsm["ranking"][2] == "S2_spark" else "."))

    # --- 5. Limites / conditions -------------------------------------------
    tp = sens.get("tipping_point_robustness")
    caveats = (
        f"Cette recommandation suppose que la sécurité reste la priorité : elle est valable tant que la "
        f"robustesse pèse au moins {pct(tp)} dans la décision. Si la priorité devenait la simplicité ou la "
        f"rapidité, les vues Athena seraient préférables. Sur des volumes moyens (environ un million de lignes), "
        f"les vues sont également légèrement plus rapides.") if tp else ""

    sections = {"situation": situation, "recommendation": recommendation, "why": why,
                "alternatives": alternatives, "caveats": caveats, "actions": ACTIONS[best],
                "recommended": best, "recommended_name": NAMES[best]}
    json.dump(sections, open(os.path.join(OUT, "recommendation.json"), "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)

    text = ("RECOMMANDATION DE SÉCURITÉ\n\n1. Situation\n" + situation +
            "\n\n2. Recommandation\n" + recommendation +
            "\n\n3. Pourquoi ce choix\n" + "\n".join("- " + w for w in why) +
            "\n\n4. Les autres options\n" + alternatives +
            "\n\n5. À savoir\n" + caveats +
            "\n\n6. Prochaines étapes\n" + "\n".join(f"{i}. {a}" for i, a in enumerate(ACTIONS[best], 1)))
    open(os.path.join(OUT, "recommendation.txt"), "w", encoding="utf-8").write(text)

    voice = (f"Bonjour. Voici la recommandation de sécurité pour votre Lakehouse. {situation} "
             f"{recommendation} {' '.join(why[:2])} {caveats}")
    open(os.path.join(OUT, "recommendation_voice.txt"), "w", encoding="utf-8").write(voice)

    print(text)
    print("\nFichiers : output/recommendation.json, recommendation.txt, recommendation_voice.txt")


if __name__ == "__main__":
    build()