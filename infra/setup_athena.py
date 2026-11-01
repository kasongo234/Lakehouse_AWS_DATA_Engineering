
# setup_athena.py
# Rôle : créer un "workgroup" Athena dédié au projet.
# Un workgroup = un espace de travail Athena avec ses propres règles :
#   - où sont stockés les résultats des requêtes
#   - s'ils sont chiffrés
#   - combien une requête a le droit de scanner (contrôle du coût)
#   - la collecte des métriques (temps, octets scannés) pour le benchmark


# --- Imports -----------------------------------------------------------
import sys, os
# sys et os servent à manipuler les chemins de fichiers.

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Ce script est dans le dossier "infra\", mais config.py est un niveau au-dessus.
# __file__                     -> chemin de ce script : ...\Memoire_DATA\infra\setup_athena.py
# os.path.dirname(...) 1 fois  -> ...\Memoire_DATA\infra
# os.path.dirname(...) 2 fois  -> ...\Memoire_DATA   (le dossier du projet)
# sys.path.insert(0, ...)      -> dit à Python : "cherche aussi les modules ici"
# Résultat : la ligne suivante "from config import ..." fonctionne.

import boto3
# boto3 = SDK officiel AWS pour Python. Il utilise les clés de "aws configure".

from config import REGION, CURATED_BUCKET
# On récupère la région (eu-west-3) et le nom du bucket curated depuis config.py.
# Aucun nom n'est écrit "en dur" ici : tout vient d'un seul fichier de configuration.

# --- Connexion au service Athena ---------------------------------------
athena = boto3.client("athena", region_name=REGION)
# Crée un "client" : un objet qui permet d'appeler les fonctions d'Athena
# (créer un workgroup, lancer une requête...) dans la région Paris.

WG = "lakehouse-memoire"
# Nom du workgroup. Tous les tests du benchmark tourneront dans celui-ci,
# ce qui isole nos mesures de celles des autres utilisateurs du compte.

# --- Configuration du workgroup -----------------------------------------
conf = {

    "ResultConfiguration": {
        # Athena écrit TOUJOURS le résultat de chaque requête dans un fichier S3.
        "OutputLocation": f"s3://{CURATED_BUCKET}/_athena_results/",
        # -> les résultats vont dans notre bucket curated, dossier _athena_results/
        "EncryptionConfiguration": {"EncryptionOption": "SSE_S3"}},
        # -> ces fichiers de résultats sont chiffrés (AES-256).
        #    Important : un résultat de requête peut contenir des données
        #    sensibles (salaires...). Il doit être protégé comme la table elle-même.

    "EnforceWorkGroupConfiguration": True,
    # Oblige tous les utilisateurs du workgroup à respecter CES réglages.
    # Sans cela, un utilisateur pourrait envoyer ses résultats ailleurs,
    # non chiffrés. -> principe Zero Trust : on ne laisse pas le choix.

    "PublishCloudWatchMetricsEnabled": True,
    # Envoie automatiquement vers CloudWatch (service de supervision AWS)
    # les métriques de chaque requête : durée, octets scannés...
    # -> source des mesures de performance du benchmark (objectif 2).

    "BytesScannedCutoffPerQuery": 10 * 1024**3,
    # Plafond : une requête est annulée si elle doit scanner plus de 10 Go.
    # 1024**3 = 1 073 741 824 octets = 1 Go, donc 10 * 1 Go = 10 Go.
    # Athena facture environ 5 $ par To scanné : le plafond protège le compte
    # contre une requête mal écrite (ex. SELECT * sur une très grosse table).

    "EngineVersion": {"SelectedEngineVersion": "Athena engine version 3"}}
    # On fixe la version du moteur (v3, basée sur Trino).
    # -> reproductibilité : toutes les mesures sont faites avec le même moteur,
    #    même si AWS change la version par défaut plus tard.

# --- Création du workgroup ---------------------------------------------
try:
    athena.create_work_group(
        Name=WG,                       # nom du workgroup
        Configuration=conf,            # les règles définies ci-dessus
        Description="Benchmark sécurité Lakehouse - mémoire")  # description visible en console
    print("Workgroup créé :", WG)

except athena.exceptions.InvalidRequestException:
    # Si le workgroup existe déjà, AWS renvoie cette erreur.
    # On l'intercepte pour que le script puisse être relancé sans planter
    # -> script "idempotent" (même résultat qu'on le lance 1 ou 10 fois).
    print("Workgroup existant :", WG)