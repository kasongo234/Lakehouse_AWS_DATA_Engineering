# =====================================================================
# security_tests.py (Phase 3 - étape 3.6)
# Vérifie l'EFFICACITÉ de chaque stratégie avec l'identité de l'analyste France.
# 4 tests de fuite par stratégie :
#   T1 isolation des lignes   : voit-il un autre pays que la France ?
#   T2 protection colonnes    : peut-il lire une colonne sensible (balance) ?
#   T3 contournement logique  : peut-il atteindre les données non filtrées par une autre requête ?
#   T4 accès direct aux fichiers S3 : peut-il télécharger un fichier Parquet d'un autre pays ?
# + capacités fonctionnelles : pseudonymisation (hachage), généralisation (tranches).
# Sortie : output/security_results.json
# =====================================================================
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import CURATED_BUCKET, PROJECT_DIR
from as_analyst import analyst_session, run

session = analyst_session()
athena, s3 = session.client("athena"), session.client("s3")


def q(sql):
    """Renvoie (réussi, première valeur) pour une requête de l'analyste."""
    state, rows, _, err = run(sql, athena, show=False)
    return state == "SUCCEEDED", (rows[1][0] if state == "SUCCEEDED" and len(rows) > 1 else err)


def s3_direct_leak():
    """T4 : l'analyste télécharge-t-il un fichier de la partition Germany ?"""
    try:
        objs = s3.list_objects_v2(Bucket=CURATED_BUCKET, Prefix="bank_churn_x1/country=Germany/")["Contents"]
        key = next(o["Key"] for o in objs if o["Key"].endswith(".parquet") or "part-" in o["Key"])
        s3.get_object(Bucket=CURATED_BUCKET, Key=key, Range="bytes=0-100")
        return True
    except Exception:
        return False


spark_checks = json.load(open(os.path.join(PROJECT_DIR, "output", "bench_s2_spark.json"),
                              encoding="utf-8"))["security_checks"]["bank_churn_x1"]
leak_s3 = s3_direct_leak()
results = {}

# --- S0 : référence (aucune sécurité) ---------------------------------
ok, n = q("SELECT COUNT(*) FROM lakehouse_curated.bank_churn_x1 WHERE country <> 'France'")
ok2, _ = q("SELECT balance FROM lakehouse_curated.bank_churn_x1 LIMIT 1")
results["S0_reference"] = {"T1_lignes": not (ok and int(n) > 0), "T2_colonnes": not ok2,
                           "T3_contournement": False, "T4_fichiers_s3": not leak_s3}
available = {"S0_reference": q("SELECT COUNT(*) FROM lakehouse_curated.bank_churn_x1")[0]}

# --- S1 : Lake Formation ----------------------------------------------
ok, n = q("SELECT COUNT(*) FROM lakehouse_lf.bank_churn_x1 WHERE country <> 'France'")
ok2, _ = q("SELECT balance FROM lakehouse_lf.bank_churn_x1 LIMIT 1")
ok3, n3 = q("SELECT COUNT(*) FROM lakehouse_lf.bank_churn_x1")          # sans filtre : 5014 attendu
results["S1_lakeformation"] = {"T1_lignes": not (ok and int(n) > 0), "T2_colonnes": not ok2,
                               "T3_contournement": ok3 and int(n3) == 5014,
                               "T4_fichiers_s3": not leak_s3}
available["S1_lakeformation"] = ok3

# --- S3 : vues Athena -------------------------------------------------
ok, n = q("SELECT COUNT(*) FROM lakehouse_curated.v_secure_x1 WHERE country <> 'France'")
ok2, _ = q("SELECT balance FROM lakehouse_curated.v_secure_x1 LIMIT 1")
ok3, _ = q("SELECT balance FROM lakehouse_curated.bank_churn_x1 WHERE country = 'Germany' LIMIT 1")
results["S3_vues"] = {"T1_lignes": not (ok and int(n) > 0), "T2_colonnes": not ok2,
                      "T3_contournement": not ok3, "T4_fichiers_s3": not leak_s3}
available["S3_vues"] = q("SELECT COUNT(*) FROM lakehouse_curated.v_secure_x1")[0]
available["S2_spark"] = True     # l'analyste consomme la sortie du job (rôle du job)

# --- S2 : masquage Spark (sortie du job + accès hors du job) -----------
results["S2_spark"] = {"T1_lignes": spark_checks["countries"] == ["France"],
                       "T2_colonnes": not any(c in spark_checks["columns"]
                                              for c in ("balance", "estimated_salary", "customer_id")),
                       "T3_contournement": not ok3,      # hors du job, la table brute reste lisible
                       "T4_fichiers_s3": not leak_s3}

# --- Capacités fonctionnelles (constatées aux étapes 3.2 à 3.4) --------
features = {"S0_reference": (False, False), "S1_lakeformation": (False, False),
            "S2_spark": (True, True), "S3_vues": (True, True)}

print(f"{'Stratégie':<18} {'T1 lignes':<10} {'T2 colonnes':<12} {'T3 contourn.':<13} "
      f"{'T4 fichiers':<12} {'Robustesse':<11} {'Utilisable':<11} Hachage/Généralisation")
for s, t in results.items():
    passed = sum(t.values())
    t["robustness"] = round(passed / 4, 2)
    t["pseudonymisation"], t["generalisation"] = features[s]
    t["available"] = available[s]
    mark = lambda b: "OK" if b else "FUITE"
    print(f"{s:<18} {mark(t['T1_lignes']):<10} {mark(t['T2_colonnes']):<12} {mark(t['T3_contournement']):<13} "
          f"{mark(t['T4_fichiers_s3']):<12} {passed}/4 ({t['robustness']:.0%})  "
          f"{'oui' if t['available'] else 'NON':<11} "
          f"{'oui' if features[s][0] else 'non'}/{'oui' if features[s][1] else 'non'}")

TAG = sys.argv[1] if len(sys.argv) > 1 else ""          # ex. "hardened" après durcissement
path = os.path.join(PROJECT_DIR, "output", f"security_results{'_' + TAG if TAG else ''}.json")
json.dump(results, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("\nRésultats :", path)