# =====================================================================
# s3_secure_views.py (Phase 3 - étape 3.2) - Stratégie S3 : vues Athena sécurisées
# Crée, pour chaque volumétrie, une vue SQL qui applique la règle de sécurité :
#   - LIGNES   : uniquement country = 'France'
#   - COLONNES : customer_id haché (SHA-256), age généralisé en tranches,
#                balance / estimated_salary / credit_score EXCLUS
# Puis teste la vue avec l'identité de l'analyste.
# =====================================================================
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boto3
from config import REGION, WORKGROUP, DB_CURATED, SCALES
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "benchmark"))
from as_analyst import run as run_as_analyst, analyst_session

admin_athena = boto3.client("athena", region_name=REGION)

VIEW_SQL = """
CREATE OR REPLACE VIEW {view} AS
SELECT
    to_hex(sha256(to_utf8(CAST(customer_id AS varchar)))) AS customer_hash,  -- pseudonymisation
    gender,
    CAST(floor(age / 10) * 10 AS integer)                AS age_band,       -- généralisation
    tenure, products_number, credit_card, active_member, churn,
    country
FROM {table}
WHERE country = 'France'                                                     -- filtrage par ligne
"""


def admin_run(sql):
    """Exécute une requête DDL avec les droits administrateur (création de la vue)."""
    qid = admin_athena.start_query_execution(QueryString=sql, WorkGroup=WORKGROUP,
                                             QueryExecutionContext={"Database": DB_CURATED})["QueryExecutionId"]
    while True:
        st = admin_athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        if st["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            return st["State"], st.get("StateChangeReason", "")
        time.sleep(0.5)


if __name__ == "__main__":
    # 1. Création d'une vue sécurisée par volumétrie
    for s in SCALES:
        table, view = f"bank_churn_x{s}", f"v_secure_x{s}"
        state, why = admin_run(VIEW_SQL.format(view=view, table=table))
        print(f"Vue {view:<16} -> {state} {why}")

    # 2. Test avec l'identité de l'analyste
    athena = analyst_session().client("athena")
    print("\n--- TEST 1 : l'analyste interroge la VUE ---")
    run_as_analyst("SELECT * FROM v_secure_x1 LIMIT 3", athena)
    run_as_analyst("SELECT country, COUNT(*) FROM v_secure_x1 GROUP BY country", athena)

    print("\n--- TEST 2 : l'analyste tente de contourner la vue (table de base) ---")
    run_as_analyst("SELECT customer_id, country, balance FROM bank_churn_x1 "
                   "WHERE country = 'Germany' LIMIT 2", athena)