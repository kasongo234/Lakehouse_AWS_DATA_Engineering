# =====================================================================
# config.py : configuration centrale du projet (importée par tous les scripts)
# =====================================================================
import os
import boto3

# --- Dossier du projet (chemins indépendants du dossier courant) -------
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# --- AWS ---------------------------------------------------------------
REGION = "eu-west-3"                                   # Paris
PREFIX = "lakehouse-memoire"
ACCOUNT = boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]

# --- Stockage S3 -------------------------------------------------------
RAW_BUCKET = f"{PREFIX}-raw-{ACCOUNT}"                 # zone brute
CURATED_BUCKET = f"{PREFIX}-curated-{ACCOUNT}"         # zone nettoyée

# --- Données source ----------------------------------------------------
SOURCE = "bank_churn"
LOCAL_CSV = os.path.join(PROJECT_DIR, "data", "Bank_Customer_Churn_Prediction.csv")

# --- Glue / Catalogue --------------------------------------------------
GLUE_ROLE = "LakehouseGlueRole"
GLUE_JOB = "bank-churn-clean"
DB_RAW = "lakehouse_raw"
DB_CURATED = "lakehouse_curated"

# --- Athena ------------------------------------------------------------
WORKGROUP = "lakehouse-memoire"

# --- Volumétries du benchmark (10k, 1M, 10M lignes) --------------------
SCALES = [1, 100, 1000]