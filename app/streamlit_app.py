# =====================================================================
# streamlit_app.py (Phase 5 - étape 5.3) - Console « Lakehouse Security Advisor »
# Lancement : streamlit run app\streamlit_app.py
# Inspiré des consoles de recommandation en production (AWS Trusted Advisor,
# Security Hub, Microsoft Defender) : constats classés par gravité,
# recommandation unique avec niveau de confiance, comparaison tabulaire,
# plan d'action. La pondération se règle dans la barre latérale ;
# le WSM et TOPSIS sont recalculés en direct.
# =====================================================================
import sys, os, json, datetime
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "recommender"))
import pandas as pd
import altair as alt
import streamlit as st
from config import PROJECT_DIR, REGION
from weights import contextual_weights
from wsm import wsm
from topsis import topsis
from build_matrix import matrix_for

OUT = os.path.join(PROJECT_DIR, "output")
load = lambda f: json.load(open(os.path.join(OUT, f), encoding="utf-8"))

LABEL = {"S0_reference": "Sans protection", "S1_lakeformation": "AWS Lake Formation",
         "S2_spark": "Masquage applicatif Spark", "S3_vues": "Vues Athena sécurisées"}
SHORT = {"S0_reference": "Sans protection", "S1_lakeformation": "Lake Formation",
         "S2_spark": "Masquage Spark", "S3_vues": "Vues Athena"}
COLOR = {"S0_reference": "#9ba7b6", "S1_lakeformation": "#0972d3",
         "S2_spark": "#e07941", "S3_vues": "#1a9c6d"}
CRIT = {"C4_robustesse": "Robustesse aux fuites", "C2_cout_usd": "Coût par requête",
        "C1_latence_ms": "Temps de réponse", "C6_complexite": "Simplicité de mise en œuvre",
        "C5_fonctions": "Masquage et généralisation", "C3_stabilite": "Régularité des temps"}
UNIT = {"C1_latence_ms": lambda v: f"{v:,.0f} ms".replace(",", " "),
        "C2_cout_usd": lambda v: f"{v * 1000:.3f} m$".replace(".", ","),
        "C3_stabilite": lambda v: f"{v:.2f}".replace(".", ","),
        "C4_robustesse": lambda v: f"{round(v * 4)} / 4",
        "C5_fonctions": lambda v: f"{v} / 4",
        "C6_complexite": lambda v: f"{v} / 5"}

st.set_page_config(page_title="Lakehouse Security Advisor", page_icon="🔒", layout="wide")

# --------------------------------------------------------------------------
# Style sobre, type console cloud : neutres, une couleur d'accent, statuts
# --------------------------------------------------------------------------
st.html("""
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
html, body, .stApp, .stMarkdown, p, li, label, button, input { font-family: 'Inter', system-ui, sans-serif !important; }
.stApp { background: #f4f5f7; color: #16191f; }
header[data-testid="stHeader"] { background: transparent; }
[data-testid="stToolbar"] { display: none; }
.block-container { padding-top: 2.4rem; max-width: 1240px; }
section[data-testid="stSidebar"] { background: #fff; border-right: 1px solid #e3e6ea; }
section[data-testid="stSidebar"] h3 { font-size: 13px; text-transform: uppercase; letter-spacing: .06em; color: #5f6b7a; }

.topbar { display: flex; justify-content: space-between; align-items: flex-end; padding-bottom: 14px;
          border-bottom: 1px solid #e3e6ea; margin-bottom: 20px; }
.crumb { font-size: 13px; color: #5f6b7a; }
.pagetitle { font-size: 26px; font-weight: 700; color: #16191f; margin-top: 2px; }
.meta { font-size: 13px; color: #5f6b7a; text-align: right; line-height: 1.6; }

.panel { background: #fff; border: 1px solid #e3e6ea; border-radius: 8px; padding: 20px 22px; margin-bottom: 16px; }
.ptitle { font-size: 15px; font-weight: 700; color: #16191f; margin-bottom: 4px; }
.psub { font-size: 13px; color: #5f6b7a; margin-bottom: 14px; }

.reco { display: grid; grid-template-columns: 1fr auto; gap: 18px; align-items: start; }
.reco .k { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; color: #5f6b7a; }
.reco .name { font-size: 24px; font-weight: 700; margin: 4px 0 8px; color: #16191f; }
.reco .why { font-size: 14.5px; color: #414d5c; line-height: 1.6; max-width: 720px; }
.conf { text-align: right; min-width: 190px; }
.conf .v { font-size: 28px; font-weight: 700; color: #16191f; }
.conf .l { font-size: 12.5px; color: #5f6b7a; }

.kpis { display: grid; grid-template-columns: repeat(4, 1fr); border-top: 1px solid #e9ebed; margin-top: 18px; }
.kpi { padding: 14px 16px 2px 0; border-right: 1px solid #e9ebed; margin-right: 16px; }
.kpi:last-child { border-right: none; }
.kpi .l { font-size: 12.5px; color: #5f6b7a; }
.kpi .v { font-size: 22px; font-weight: 700; color: #16191f; margin-top: 2px; }

.badge { display: inline-block; font-size: 12px; font-weight: 600; padding: 2px 9px; border-radius: 4px; }
.b-high { background: #fde8e8; color: #b0161a; } .b-med { background: #fff4d6; color: #855c00; }
.b-info { background: #e8f1fc; color: #0758a8; }
.finding { display: grid; grid-template-columns: 80px 1fr; gap: 12px; padding: 12px 0; border-top: 1px solid #f0f1f3; }
.finding.first { border-top: none; }
.finding .t { font-size: 14.5px; font-weight: 600; color: #16191f; }
.finding .d { font-size: 13.5px; color: #5f6b7a; margin-top: 2px; }

.steps { counter-reset: s; margin: 0; padding: 0; list-style: none; }
.steps li { counter-increment: s; position: relative; padding: 10px 0 10px 38px; border-top: 1px solid #f0f1f3;
            font-size: 14px; color: #414d5c; line-height: 1.5; margin: 0; }
.steps li:first-child { border-top: none; }
.steps li::before { content: counter(s); position: absolute; left: 0; top: 9px; width: 24px; height: 24px;
                    border-radius: 50%; border: 1px solid #c6ccd4; font-size: 12px; font-weight: 600;
                    display: flex; align-items: center; justify-content: center; color: #414d5c; }

table.grid { width: 100%; border-collapse: collapse; font-size: 14px; }
table.grid th { text-align: left; font-weight: 600; color: #5f6b7a; font-size: 12px; text-transform: uppercase;
                letter-spacing: .04em; padding: 10px 12px; border: none; border-bottom: 1px solid #e3e6ea; background: #fafbfc; }
table.grid td { padding: 11px 12px; border: none; border-bottom: 1px solid #f0f1f3; color: #16191f; }
table.grid td.best { font-weight: 700; }
table.grid th.win, table.grid td.win { background: #f2f8fe; }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 7px; vertical-align: 1px; }
.ok { color: #0f6b4a; font-weight: 500; } .ko { color: #b0161a; font-weight: 500; }
.mini { background: #eef0f3; height: 6px; border-radius: 3px; width: 110px; display: inline-block;
        vertical-align: middle; margin-right: 8px; }
.mini > i { display: block; height: 100%; border-radius: 3px; }
.note { font-size: 13px; color: #5f6b7a; margin-top: 12px; line-height: 1.55; }
.alert { background: #fff4d6; border: 1px solid #f2d68a; color: #5c4300; border-radius: 6px; padding: 10px 14px;
         font-size: 14px; margin-bottom: 16px; }

.stTabs [role="tablist"] { gap: 24px; border-bottom: 1px solid #e3e6ea; }
.stTabs [role="tab"] { padding: 10px 2px; background: transparent; }
.stTabs [role="tab"] p { font-size: 14.5px; font-weight: 600; color: #5f6b7a; }
.stTabs [role="tab"][aria-selected="true"] p { color: #0972d3; }
.stTabs [data-baseweb="tab-highlight"] { background-color: #0972d3; height: 3px; }
.stTabs [data-baseweb="tab-border"] { display: none; }
</style>""")

try:
    ctx, dm, rec = load("context.json"), load("decision_matrix.json"), load("recommendation.json")
    summary = load("benchmark_results.json")["summary"]
    sec = load("security_results_hardened.json")
except FileNotFoundError as e:
    st.error(f"Fichier de résultats manquant : {e.filename}. Exécutez d'abord les phases 2 à 5.1.")
    st.stop()
try:
    sec_before = load("security_results.json")
except FileNotFoundError:
    sec_before = None

# --------------------------------------------------------------------------
# Barre latérale : paramètres de décision
# --------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Paramètres de décision")
    vol = st.selectbox("Volume de données évalué",
                       ["10 millions de lignes", "1 million de lignes", "10 000 lignes"])
    scale = 1000 if vol.startswith("10 m") else 100 if vol.startswith("1 m") else 1
    vclass = {1: "petite", 100: "moyenne", 1000: "grande"}[scale]
    ctx_w, rules = contextual_weights(dm["context_needs"], vclass)
    st.markdown("### Pondération des critères")
    st.caption("Valeurs proposées à partir du contexte analysé. Modifiez-les pour simuler d'autres priorités.")
    raw = {c: st.slider(CRIT[c], 0, 100, int(round(ctx_w[c] * 100)), key=c) for c in CRIT}
    if st.button("Rétablir les valeurs proposées", use_container_width=True):
        for c in ctx_w:
            st.session_state[c] = int(round(ctx_w[c] * 100))
        st.rerun()
    with st.expander("Règles d'ajustement appliquées"):
        for r in rules:
            st.write("–", r)

total = sum(raw.values()) or 1
weights = {c: v / total for c, v in raw.items()}
matrix = matrix_for(scale)
_, contrib, scores, ranking = wsm({"matrix": matrix, "criteria": dm["criteria"]}, weights)
_, _, _, closeness, t_rank = topsis(matrix, dm["criteria"], weights)
best = ranking[0]
agree = best == t_rank[0]
gap = scores[ranking[0]] - scores[ranking[1]]
confidence = "Élevée" if agree and gap > 0.05 else "Modérée" if agree else "Faible"

# --------------------------------------------------------------------------
# En-tête
# --------------------------------------------------------------------------
big = max(ctx["tables"], key=lambda t: t["rows"] or 0)
st.markdown(
    f'<div class="topbar"><div><div class="crumb">Lakehouse · Sécurité des données</div>'
    f'<div class="pagetitle">Lakehouse Security Advisor</div></div>'
    f'<div class="meta">Base <b>{ctx["database"]}</b> · région {REGION}<br>'
    f'{len(ctx["tables"])} tables · analyse du {datetime.date.today():%d/%m/%Y}</div></div>',
    unsafe_allow_html=True)

if best != rec["recommended"]:
    st.markdown(f'<div class="alert">Avec la pondération actuelle, la recommandation devient '
                f'<b>{LABEL[best]}</b> (recommandation initiale : {rec["recommended_name"]}).</div>',
                unsafe_allow_html=True)

# --- Recommandation ---------------------------------------------------------
n_high, n_med = len(ctx["sensitive_columns"]["eleve"]), len(ctx["sensitive_columns"]["moyen"])
risk = ctx.get("usage", {}).get("sensitive_access_ratio", 0)
kpis = [("Score global (WSM)", f"{scores[best]:.2f}".replace(".", ",")),
        ("Proximité de l'idéal (TOPSIS)", f"{closeness[best]:.2f}".replace(".", ",")),
        ("Tentatives de fuite bloquées", f"{round(sec[best]['robustness'] * 4)} sur 4"),
        ("Coût par requête", UNIT["C2_cout_usd"](matrix[best]["C2_cout_usd"]))]
reason = (rec["recommendation"] if best == rec["recommended"] else
          f"Avec la pondération choisie, {LABEL[best]} obtient le meilleur score global.")
st.markdown(
    '<div class="panel"><div class="reco"><div>'
    '<div class="k">Stratégie recommandée</div>'
    f'<div class="name">{LABEL[best]}</div>'
    f'<div class="why">{reason}</div></div>'
    f'<div class="conf"><div class="l">Niveau de confiance</div><div class="v">{confidence}</div>'
    f'<div class="l">{"Les deux modèles concordent" if agree else "Les modèles divergent"}<br>'
    f'écart de {gap:.2f} point avec la 2<sup>e</sup></div></div></div>'.replace("0.", "0,") +
    '<div class="kpis">' + "".join(f'<div class="kpi"><div class="l">{l}</div><div class="v">{v}</div></div>'
                                   for l, v in kpis) + '</div></div>',
    unsafe_allow_html=True)

tab1, tab2, tab3, tab4 = st.tabs(["Vue d'ensemble", "Comparaison des stratégies",
                                  "Tests de sécurité", "Performance mesurée"])

# --- Vue d'ensemble ---------------------------------------------------------
with tab1:
    findings = []
    if dm["context_indicators"].get("current_protection", 0) == 0:
        findings.append(("high", "Élevé", f"{n_high + n_med} colonnes sensibles sans contrôle d'accès granulaire",
                         f"{n_high} à sensibilité élevée ({', '.join(ctx['sensitive_columns']['eleve'])}) et "
                         f"{n_med} quasi-identifiants ({', '.join(ctx['sensitive_columns']['moyen'])})."))
    if risk > 0.3:
        findings.append(("high", "Élevé", f"{round(risk * 100)} % des requêtes lisent des données sensibles",
                         "Mesuré sur l'historique des requêtes Athena du groupe de travail."))
    if sec_before and not sec_before.get("S0_reference", {}).get("T4_fichiers_s3", True):
        findings.append(("med", "Moyen", "Accès direct aux fichiers S3 possible pour les analystes",
                         "Ce droit permettait de contourner toutes les protections ; il a été retiré lors du durcissement."))
    if ctx.get("security_state", {}).get("iam_compatibility_mode"):
        findings.append(("med", "Moyen", "Lake Formation fonctionne en mode compatibilité IAM",
                         "Le contrôle fin ne s'applique qu'aux tables dont l'accès implicite a été retiré."))
    findings.append(("info", "Info", f"Volume de référence : {big['rows']:,} lignes".replace(",", " "),
                     f"La plus grande table du contexte ({big['name']}) sert de base à la recommandation."))

    left, right = st.columns([3, 2], gap="medium")
    with left:
        st.markdown(
            '<div class="panel"><div class="ptitle">Constats</div>'
            f'<div class="psub">{len(findings)} éléments relevés par l\'analyse automatique</div>' +
            "".join(f'<div class="finding{" first" if i == 0 else ""}"><div><span class="badge b-{k}">{lv}</span></div>'
                    f'<div><div class="t">{t}</div><div class="d">{d}</div></div></div>'
                    for i, (k, lv, t, d) in enumerate(findings)) + '</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="panel"><div class="ptitle">Justification</div>'
            '<div class="psub">Critères ayant le plus contribué au choix initial</div><ul class="steps">' +
            "".join(f'<li>{w}</li>' for w in rec["why"]) + f'</ul><div class="note">{rec["caveats"]}</div></div>',
            unsafe_allow_html=True)
    with right:
        st.markdown(
            '<div class="panel"><div class="ptitle">Plan d\'action</div>'
            f'<div class="psub">Mise en œuvre de {LABEL[rec["recommended"]]}</div><ol class="steps">' +
            "".join(f'<li>{a}</li>' for a in rec["actions"]) + '</ol></div>', unsafe_allow_html=True)
        audio = os.path.join(OUT, "recommendation.mp3")
        if os.path.exists(audio):
            st.markdown('<div class="ptitle" style="margin:4px 0 6px">Synthèse audio</div>', unsafe_allow_html=True)
            st.audio(audio)
        if st.button("Générer le rapport HTML", use_container_width=True):
            import report_html
            st.success(f"Rapport généré : {report_html.build()}")

# --- Comparaison --------------------------------------------------------------
with tab2:
    alts = ranking
    head = "".join(f'<th class="{"win" if a == best else ""}">{SHORT[a]}</th>' for a in alts)
    rows = []
    for c in CRIT:
        vals = {a: matrix[a][c] for a in alts}
        good = (min if dm["criteria"][c]["direction"] == "min" else max)(vals.values())
        rows.append(f'<tr><td>{CRIT[c]}</td><td style="color:#5f6b7a">{weights[c]:.0%}</td>' + "".join(
            f'<td class="{"win " if a == best else ""}{"best" if vals[a] == good else ""}">{UNIT[c](vals[a])}</td>'
            for a in alts) + "</tr>")
    bar = lambda v, a: (f'<span class="mini"><i style="width:{v * 100:.0f}%;background:{COLOR[a]}"></i></span>'
                        + f'{v:.2f}'.replace(".", ","))
    rows.append('<tr><td><b>Score global (WSM)</b></td><td></td>' + "".join(
        f'<td class="{"win" if a == best else ""}">{bar(scores[a], a)}</td>' for a in alts) + "</tr>")
    rows.append('<tr><td><b>Proximité de l\'idéal (TOPSIS)</b></td><td></td>' + "".join(
        f'<td class="{"win" if a == best else ""}">{bar(closeness[a], a)}</td>' for a in alts) + "</tr>")
    rows.append('<tr><td><b>Rang</b></td><td></td>' + "".join(
        f'<td class="{"win" if a == best else ""}">{i} / 3</td>' for i, a in enumerate(alts, 1)) + "</tr>")
    st.markdown(
        '<div class="panel"><div class="ptitle">Matrice de décision</div>'
        f'<div class="psub">Valeurs mesurées sur {vol} ; la meilleure valeur de chaque critère est en gras</div>'
        f'<table class="grid"><tr><th>Critère</th><th>Poids</th>{head}</tr>{"".join(rows)}</table>'
        '<div class="note">Score global : modèle WSM (somme pondérée des critères normalisés). '
        'Proximité de l\'idéal : modèle TOPSIS. Les deux modèles utilisent les mêmes poids.</div></div>',
        unsafe_allow_html=True)

# --- Tests de sécurité --------------------------------------------------------
with tab3:
    tests = {"T1_lignes": "Accès à un autre pays", "T2_colonnes": "Lecture d'une colonne sensible",
             "T3_contournement": "Contournement de la protection", "T4_fichiers_s3": "Téléchargement des fichiers S3"}
    order = [s for s in ["S1_lakeformation", "S3_vues", "S2_spark", "S0_reference"] if s in sec]
    cell = lambda ok: ('<span class="ok"><span class="dot" style="background:#1a9c6d"></span>Bloqué</span>' if ok
                       else '<span class="ko"><span class="dot" style="background:#d91515"></span>Exposé</span>')
    body = "".join(f'<tr><td>{t}</td>' + "".join(f'<td>{cell(sec[s][k])}</td>' for s in order) + "</tr>"
                   for k, t in tests.items())
    body += '<tr><td><b>Tentatives bloquées</b></td>' + "".join(
        f'<td><b>{round(sec[s]["robustness"] * 4)} / 4</b></td>' for s in order) + "</tr>"
    st.markdown(
        '<div class="panel"><div class="ptitle">Résultats des tests de fuite</div>'
        '<div class="psub">Tentatives d\'accès menées avec l\'identité d\'un analyste autorisé uniquement sur la France, '
        'après retrait de son accès direct aux fichiers</div>'
        f'<table class="grid"><tr><th>Test</th>{"".join(f"<th>{SHORT[s]}</th>" for s in order)}</tr>{body}</table>'
        '</div>', unsafe_allow_html=True)

# --- Performance --------------------------------------------------------------
with tab4:
    df = pd.DataFrame(summary)
    df["Stratégie"] = df["strategy"].map(SHORT)
    df["Volume"] = df["scale"].map({1: "10 000 lignes", 100: "1 million", 1000: "10 millions"})
    agg = df.groupby(["Volume", "Stratégie"], as_index=False)["median_ms"].mean()
    st.markdown('<div class="ptitle" style="margin-top:6px">Temps de réponse médian</div>'
                '<div class="psub">Moyenne des 3 requêtes de référence, 5 mesures chacune, '
                'exécutées avec l\'identité de l\'analyste</div>', unsafe_allow_html=True)
    chart = alt.Chart(agg).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3, size=26).encode(
        x=alt.X("Volume:N", sort=["10 000 lignes", "1 million", "10 millions"], title=None,
                axis=alt.Axis(labelAngle=0, labelColor="#414d5c", domainColor="#c6ccd4", ticks=False)),
        xOffset=alt.XOffset("Stratégie:N", sort=[SHORT[s] for s in COLOR]),
        y=alt.Y("median_ms:Q", title="ms", axis=alt.Axis(gridColor="#eef0f3", domain=False, ticks=False,
                                                         labelColor="#5f6b7a", titleColor="#5f6b7a")),
        color=alt.Color("Stratégie:N", scale=alt.Scale(domain=[SHORT[s] for s in COLOR], range=list(COLOR.values())),
                        legend=alt.Legend(orient="top", title=None, labelColor="#414d5c")),
        tooltip=["Stratégie", "Volume", alt.Tooltip("median_ms:Q", format=".0f", title="ms")]
    ).properties(height=340, background="#ffffff", padding=16).configure_view(strokeWidth=0)
    st.altair_chart(chart, width="stretch")
    with st.expander("Données détaillées"):
        st.dataframe(df[["Volume", "query", "Stratégie", "median_ms", "p95_ms", "overhead_pct", "scanned_kb"]]
                     .rename(columns={"query": "Requête", "median_ms": "Médiane (ms)", "p95_ms": "P95 (ms)",
                                      "overhead_pct": "Écart / référence (%)", "scanned_kb": "Données lues (Ko)"}),
                     hide_index=True, width="stretch")