# =====================================================================
# report_html.py (Phase 5 - étape 5.2) - Rapport HTML autonome
# Assemble la recommandation (5.1), le contexte (phase 2), le benchmark
# (phase 3) et les modèles de décision (phase 4) dans UN fichier HTML,
# lisible hors ligne (graphiques SVG intégrés, aucune dépendance).
# Sortie : output/rapport_recommandation.html
# =====================================================================
import sys, os, json, html, datetime, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import PROJECT_DIR

OUT = os.path.join(PROJECT_DIR, "output")
load = lambda f: json.load(open(os.path.join(OUT, f), encoding="utf-8"))
E = html.escape

STRATS = ["S0_reference", "S1_lakeformation", "S2_spark", "S3_vues"]
LABEL = {"S0_reference": "Référence (sans sécurité)", "S1_lakeformation": "Lake Formation",
         "S2_spark": "Masquage Spark", "S3_vues": "Vues Athena"}
VAR = {"S0_reference": "--ref", "S1_lakeformation": "--s1", "S2_spark": "--s2", "S3_vues": "--s3"}


def bar_chart_grouped(summary):
    """Temps médian moyen (3 requêtes) par volume et par stratégie : barres groupées."""
    scales = [1, 100, 1000]
    data = {(s, sc): statistics.mean(x["median_ms"] for x in summary
                                      if x["strategy"] == s and x["scale"] == sc)
            for s in STRATS for sc in scales}
    W, H, L, B, T = 640, 300, 56, 40, 16
    ymax = max(data.values()) * 1.15
    gw = (W - L - 16) / len(scales)
    bw = 22
    y = lambda v: T + (H - T - B) * (1 - v / ymax)
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Temps de réponse médian par volume">']
    for i in range(0, int(ymax) + 1, 250):                     # grille discrète
        parts.append(f'<line x1="{L}" x2="{W-16}" y1="{y(i):.1f}" y2="{y(i):.1f}" class="grid"/>'
                     f'<text x="{L-8}" y="{y(i)+4:.1f}" class="tick" text-anchor="end">{i}</text>')
    for gi, sc in enumerate(scales):
        x0 = L + gi * gw + (gw - len(STRATS) * (bw + 2)) / 2
        for si, s in enumerate(STRATS):
            v = data[(s, sc)]
            x, top = x0 + si * (bw + 2), y(v)
            h = H - B - top
            parts.append(f'<path d="M{x},{H-B} V{top+4} q0,-4 4,-4 h{bw-8} q4,0 4,4 V{H-B} Z" '
                         f'style="fill:var({VAR[s]})" class="mark"><title>{LABEL[s]} - x{sc} : '
                         f'{v:.0f} ms</title></path>')
        parts.append(f'<text x="{L + gi*gw + gw/2:.1f}" y="{H-B+20}" class="tick" text-anchor="middle">'
                     f'x{sc} ({["10 000", "1 million", "10 millions"][gi]} lignes)</text>')
    parts.append(f'<line x1="{L}" x2="{W-16}" y1="{H-B}" y2="{H-B}" class="axis"/>')
    parts.append(f'<text x="12" y="{T+4}" class="tick">ms</text></svg>')
    return "".join(parts)


def hbar(scores, title):
    """Barres horizontales pour un score de 0 à 1 (WSM ou TOPSIS)."""
    alts = sorted(scores, key=scores.get, reverse=True)
    W, rowh, L = 420, 34, 130
    H = rowh * len(alts) + 10
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{E(title)}">']
    for i, a in enumerate(alts):
        w = (W - L - 60) * scores[a]
        yy = 6 + i * rowh
        parts.append(f'<text x="{L-8}" y="{yy+17}" class="lbl" text-anchor="end">{LABEL[a]}</text>'
                     f'<path d="M{L},{yy+4} h{max(w-4,1):.1f} q4,0 4,4 v10 q0,4 -4,4 h-{max(w-4,1):.1f} Z" '
                     f'style="fill:var({VAR[a]})" class="mark"><title>{LABEL[a]} : {scores[a]:.3f}</title></path>'
                     f'<text x="{L+w+6:.1f}" y="{yy+17}" class="val">{scores[a]:.2f}</text>')
    return "".join(parts) + "</svg>"


def build():
    rec, ctx = load("recommendation.json"), load("context.json")
    summary = load("benchmark_results.json")["summary"]
    dm, wsm, top = load("decision_matrix.json"), load("wsm_result.json"), load("topsis_result.json")
    sens, sec = load("sensitivity_result.json"), load("security_results_hardened.json")
    best = rec["recommended"]
    m = dm["matrix"][best]

    tiles = [("Stratégie recommandée", LABEL[best], "par le WSM et TOPSIS"
              if top["comparison"]["same_recommendation"] else "selon le WSM"),
             ("Robustesse", f"{round(sec[best]['robustness']*4)}/4", "tentatives de fuite bloquées"),
             ("Coût par requête", f"{m['C2_cout_usd']*1000:.3f} m$".replace(".", ","), "millièmes de dollar"),
             ("Colonnes sensibles", str(len(ctx["sensitive_columns"]["eleve"]) +
                                        len(ctx["sensitive_columns"]["moyen"])), "détectées automatiquement")]
    tiles_html = "".join(f'<div class="tile"><div class="tl">{E(a)}</div><div class="tv">{E(b)}</div>'
                         f'<div class="ts">{E(c)}</div></div>' for a, b, c in tiles)

    legend = "".join(f'<span class="key"><i style="background:var({VAR[s]})"></i>{LABEL[s]}</span>'
                     for s in STRATS)

    tests = ["T1_lignes", "T2_colonnes", "T3_contournement", "T4_fichiers_s3"]
    sec_rows = "".join(
        f"<tr><td>{LABEL[s]}</td>" + "".join(
            f'<td class="{"ok" if sec[s][t] else "ko"}">{"✔ Bloqué" if sec[s][t] else "✖ Fuite"}</td>'
            for t in tests) + f"<td><b>{round(sec[s]['robustness']*4)}/4</b></td></tr>"
        for s in STRATS)

    crit = dm["criteria"]
    mat_rows = "".join(
        f"<tr><td>{E(crit[c]['label'])}</td><td>{'↓ min' if crit[c]['direction']=='min' else '↑ max'}</td>"
        + "".join(f"<td>{dm['matrix'][a][c]:.6g}</td>" for a in dm["matrix"])
        + f"<td>{wsm['weights'][c]:.0%}</td></tr>" for c in crit)
    mat_head = "".join(f"<th>{LABEL[a]}</th>" for a in dm["matrix"])

    mc = sens["monte_carlo"]
    vol = sens.get("volume", {})
    vol_rows = "".join(f"<tr><td>{k}</td><td>{LABEL[v['wsm']]}</td><td>{LABEL[v['topsis']]}</td></tr>"
                       for k, v in vol.items())

    page = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Recommandation de sécurité</title>
<style>
:root{{color-scheme:light;--bg:#f6f6f4;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#8a8984;
--line:#e4e3df;--ref:#9a9993;--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--ok:#0f7a3d;--ko:#c0392b;--accent:#2a78d6}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{color-scheme:dark;--bg:#121211;
--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#8f8e88;--line:#2e2e2c;--ref:#77766f;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--ok:#4cc27e;--ko:#ef6b5e;--accent:#3987e5}}}}
:root[data-theme="dark"]{{color-scheme:dark;--bg:#121211;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;
--muted:#8f8e88;--line:#2e2e2c;--ref:#77766f;--s1:#3987e5;--s2:#d95926;--s3:#199e70;--ok:#4cc27e;--ko:#ef6b5e;--accent:#3987e5}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}}
main{{max-width:980px;margin:0 auto;padding:32px 16px 64px}}
h1{{font-size:28px;margin:0 0 4px;letter-spacing:-.01em}}h2{{font-size:19px;margin:40px 0 12px}}
.sub{{color:var(--ink2);margin:0 0 24px}}
.card{{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:20px 22px;margin:12px 0}}
.hero{{border-left:4px solid var(--accent)}}.hero p{{margin:.4em 0}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}}
.tile{{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px 16px}}
.tl{{color:var(--ink2);font-size:13px}}.tv{{font-size:24px;font-weight:650;margin:2px 0}}
.ts{{color:var(--muted);font-size:12px}}
table{{width:100%;border-collapse:collapse;font-size:14px}}th,td{{text-align:left;padding:8px 10px;
border-bottom:1px solid var(--line)}}th{{color:var(--ink2);font-weight:600}}
.ok{{color:var(--ok)}}.ko{{color:var(--ko)}}
.scroll{{overflow-x:auto}}svg{{width:100%;height:auto;display:block}}
.grid{{stroke:var(--line);stroke-width:1}}.axis{{stroke:var(--muted);stroke-width:1}}
.tick,.lbl{{fill:var(--ink2);font-size:12px}}.val{{fill:var(--ink);font-size:12px;font-weight:600}}
.mark:hover{{opacity:.8}}.legend{{display:flex;flex-wrap:wrap;gap:14px;margin:0 0 8px;font-size:13px;color:var(--ink2)}}
.key i{{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px}}
.two{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}}
ol li,ul li{{margin:4px 0}}.foot{{color:var(--muted);font-size:12px;margin-top:40px}}
</style></head><body><main>
<h1>Recommandation de sécurité du Lakehouse</h1>
<p class="sub">Généré automatiquement le {datetime.datetime.now():%d/%m/%Y à %H:%M} · base <code>{E(ctx['database'])}</code></p>

<div class="tiles">{tiles_html}</div>

<div class="card hero"><h2 style="margin-top:0">En résumé</h2>
<p>{E(rec['recommendation'])}</p><p>{E(rec['situation'])}</p></div>

<h2>Pourquoi ce choix</h2>
<div class="card"><ul>{''.join(f'<li>{E(w)}</li>' for w in rec['why'])}</ul>
<p><b>Les autres options.</b> {E(rec['alternatives'])}</p>
<p><b>À savoir.</b> {E(rec['caveats'])}</p></div>

<h2>Prochaines étapes</h2>
<div class="card"><ol>{''.join(f'<li>{E(a)}</li>' for a in rec['actions'])}</ol></div>

<h2>Performance mesurée</h2>
<div class="card"><div class="legend">{legend}</div>{bar_chart_grouped(summary)}
<p class="ts">Temps médian moyen des 3 requêtes de référence (5 mesures chacune), exécutées avec l'identité de l'analyste. Survolez une barre pour sa valeur.</p></div>

<h2>Efficacité de la sécurité</h2>
<div class="card scroll"><table><tr><th>Stratégie</th><th>Autre pays</th><th>Colonne sensible</th>
<th>Contournement</th><th>Fichiers S3</th><th>Robustesse</th></tr>{sec_rows}</table></div>

<h2>Décision multicritère</h2>
<div class="two">
<div class="card"><b>Score pondéré (WSM)</b>{hbar(wsm['scores'], 'Score WSM')}</div>
<div class="card"><b>TOPSIS (proximité de l'idéal)</b>{hbar(top['closeness'], 'Proximité TOPSIS')}</div></div>
<div class="card scroll"><table><tr><th>Critère</th><th>Sens</th>{mat_head}<th>Poids</th></tr>{mat_rows}</table>
<p class="ts">Accord des deux modèles : corrélation de Spearman = {top['comparison']['spearman']}.</p></div>

<h2>Robustesse de la recommandation</h2>
<div class="card"><p>Sur {mc['n']} jeux de poids aléatoires, les deux modèles désignent la même stratégie dans
<b>{mc['agreement']:.0%}</b> des cas. Lake Formation est recommandée dès que la robustesse pèse au moins
<b>{sens.get('tipping_point_robustness', 0):.0%}</b> de la décision.</p>
<div class="scroll"><table><tr><th>Volume</th><th>WSM</th><th>TOPSIS</th></tr>{vol_rows}</table></div></div>

<p class="foot">Outil d'analyse et de recommandation - mémoire de Master Data Engineering (DIT).
Données : jeu Bank Customer Churn, répliqué à 10⁴, 10⁶ et 10⁷ lignes. Services : S3, Glue, Lake Formation, Athena.</p>
</main></body></html>"""
    path = os.path.join(OUT, "rapport_recommandation.html")
    open(path, "w", encoding="utf-8").write(page)
    print("Rapport généré :", path)
    return path


if __name__ == "__main__":
    p = build()
    if "--open" in sys.argv:
        import webbrowser; webbrowser.open("file://" + os.path.abspath(p))