# =====================================================================
# lf_inspector.py (Objectif 1 - étape 2.3)
# Analyse automatiquement la configuration de sécurité existante :
#   - mode de Lake Formation (IAM seul ou contrôle fin)
#   - emplacements S3 enregistrés dans Lake Formation
#   - permissions accordées sur la base et les tables
#   - filtres de lignes/colonnes (data cells filters) et LF-Tags
# Sortie : output/context_security.json
# =====================================================================
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boto3
from config import REGION, PROJECT_DIR, CURATED_BUCKET

DB = "lakehouse_curated"
lf = boto3.client("lakeformation", region_name=REGION)
glue = boto3.client("glue", region_name=REGION)


def lf_settings():
    """Mode de fonctionnement : si IAM_ALLOWED_PRINCIPALS a les droits par défaut,
    Lake Formation délègue tout à IAM (aucun contrôle fin)."""
    s = lf.get_data_lake_settings()["DataLakeSettings"]
    default = [p["Principal"]["DataLakePrincipalIdentifier"]
               for p in s.get("CreateTableDefaultPermissions", [])]
    return {"admins": [a["DataLakePrincipalIdentifier"] for a in s.get("DataLakeAdmins", [])],
            "iam_compatibility_mode": "IAM_ALLOWED_PRINCIPALS" in default}


def registered_locations():
    """Emplacements S3 placés sous le contrôle de Lake Formation."""
    res = lf.list_resources().get("ResourceInfoList", [])
    return [r["ResourceArn"] for r in res]


def list_all_permissions(resource):
    """list_permissions n'a pas de paginator boto3 : on enchaîne les pages
    manuellement avec le jeton NextToken."""
    items, token = [], None
    while True:
        kwargs = {"Resource": resource}
        if token:
            kwargs["NextToken"] = token
        resp = lf.list_permissions(**kwargs)
        items += resp.get("PrincipalResourcePermissions", [])
        token = resp.get("NextToken")
        if not token:
            return items


def table_permissions(table):
    """Qui a quels droits sur une table (et sur quelles colonnes)."""
    perms = []
    for p in list_all_permissions({"Table": {"DatabaseName": DB, "Name": table}}):
        perms.append({"principal": p["Principal"]["DataLakePrincipalIdentifier"].split(":")[-1],
                      "permissions": p["Permissions"]})
    # Permissions au niveau colonnes (TableWithColumns)
    try:
        for p in list_all_permissions({"TableWithColumns": {"DatabaseName": DB, "Name": table}}):
            cols = p["Resource"].get("TableWithColumns", {})
            names = cols.get("ColumnNames")
            excluded = cols.get("ColumnWildcard", {}).get("ExcludedColumnNames", [])
            if not names and not excluded:      # accès à toutes les colonnes = pas de restriction
                continue
            perms.append({"principal": p["Principal"]["DataLakePrincipalIdentifier"].split(":")[-1],
                          "permissions": p["Permissions"],
                          "columns": names or {"excluded": excluded}})
    except Exception:
        pass
    return perms


def data_filters(table):
    """Filtres de cellules (lignes + colonnes) définis sur la table."""
    try:
        f = lf.list_data_cells_filter(Table={"DatabaseName": DB, "Name": table}).get("DataCellsFilters", [])
        return [{"name": x["Name"], "row_filter": x.get("RowFilter", {}).get("FilterExpression"),
                 "columns": x.get("ColumnNames")} for x in f]
    except Exception:
        return []


def lf_tags():
    try:
        return [t["TagKey"] for t in lf.list_lf_tags().get("LFTags", [])]
    except Exception:
        return []


def inspect():
    settings = lf_settings()
    locations = registered_locations()
    curated_registered = any(CURATED_BUCKET in l for l in locations)
    tables = [t["Name"] for p in glue.get_paginator("get_tables").paginate(DatabaseName=DB)
              for t in p["TableList"]]

    report = {"lake_formation": {**settings,
                                 "registered_locations": locations,
                                 "curated_bucket_registered": curated_registered,
                                 "lf_tags": lf_tags()},
              "tables": {}}
    print(f"Administrateurs LF        : {len(settings['admins'])}")
    print(f"Mode compatibilité IAM    : {settings['iam_compatibility_mode']}")
    print(f"Bucket curated enregistré : {curated_registered}")
    print(f"LF-Tags                   : {report['lake_formation']['lf_tags'] or 'aucun'}\n")

    for t in tables:
        perms, filters = table_permissions(t), data_filters(t)
        open_to_iam = any(p["principal"] == "IAM_ALLOWED_PRINCIPALS" for p in perms)
        col_level = any("columns" in p for p in perms)
        report["tables"][t] = {"permissions": perms, "data_filters": filters,
                               "open_to_all_iam": open_to_iam,
                               "column_level_security": col_level,
                               "row_level_security": any(f["row_filter"] for f in filters)}
        print(f"{t:<18} ouverte à tout IAM={open_to_iam}  colonnes={col_level}  "
              f"lignes={report['tables'][t]['row_level_security']}  filtres={len(filters)}")

    # Diagnostic global : niveau de protection actuel (0 = aucun contrôle granulaire)
    any_fine = any(v["column_level_security"] or v["row_level_security"] for v in report["tables"].values())
    report["diagnostic"] = {
        "granular_security_in_place": any_fine,
        "level": "AUCUN contrôle granulaire" if not any_fine else "contrôle granulaire partiel",
        "lake_formation_ready": bool(settings["admins"]),
    }
    print("\nDiagnostic :", report["diagnostic"]["level"])

    path = os.path.join(PROJECT_DIR, "output", "context_security.json")
    json.dump(report, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("Contexte enregistré :", path)


if __name__ == "__main__":
    inspect()