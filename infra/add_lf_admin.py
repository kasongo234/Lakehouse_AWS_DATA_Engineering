import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boto3
from config import REGION

lf = boto3.client("lakeformation", region_name=REGION)
me = boto3.client("sts").get_caller_identity()["Arn"]
print("Mon identité :", me)

# 1. Lire les paramètres actuels (pour ne rien écraser)
settings = lf.get_data_lake_settings()["DataLakeSettings"]

# 2. Ajouter mon ARN à la liste des administrateurs s'il n'y est pas
admins = settings.get("DataLakeAdmins", [])
if any(a["DataLakePrincipalIdentifier"] == me for a in admins):
    print("Déjà administrateur")
else:
    admins.append({"DataLakePrincipalIdentifier": me})
    settings["DataLakeAdmins"] = admins
    # 3. Réécrire les paramètres complets, inchangés sauf la liste des admins
    lf.put_data_lake_settings(DataLakeSettings=settings)
    print("Ajouté comme administrateur Lake Formation")

print(lf.get_data_lake_settings()["DataLakeSettings"]["DataLakeAdmins"])