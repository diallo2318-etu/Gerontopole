"""Vérifie le fichier du parcours (entrepot/parcours_capacites.csv) avec les données de l'entrepôt.

1. Chaque ligne est-elle bien écrite (étape, plan, source connus) ? Chaque métier existe-t-il dans l'offre ?
2. Pour chaque commune de Normandie, quel plan serait proposé ? Le plan A est retenu si l'offre la plus
   proche est à moins de distance_max_km (à vol d'oiseau entre centres des communes), sinon le plan B,
   puis le plan C. Résultat en part de la population, pour juger si les distances choisies sont raisonnables.

Utilisation (après construire_entrepot.py) :
    python3 entrepot/verifier_parcours.py
    python3 entrepot/verifier_parcours.py --domaine vision
"""
import argparse
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from construire_entrepot import ENTREPOT

PARCOURS = Path(__file__).resolve().parent / "parcours_capacites.csv"
ETAPES = {"levee_de_doute", "etape2", "orientation", "sans_alerte", "moins_60"}
PLANS = {"A", "B", "C"}
# Où trouver l'offre de chaque source (code INSEE des lieux). None : pas de distance (conseil, action...).
OFFRE = {
    "rpps_profession": "SELECT DISTINCT code_insee FROM v_offre_par_domaine WHERE critere = ?",
    "finess_categorie": "SELECT DISTINCT code_insee FROM offre_finess WHERE categorie = ?",
    "ipa": "SELECT DISTINCT code_insee FROM offre_ipa WHERE pathologies_chroniques AND ? IS NOT NULL",
    "mon_bilan_prevention": "SELECT DISTINCT code_insee FROM offre_mon_bilan_prevention WHERE ? IS NOT NULL",
    "agirc_arrco": "SELECT DISTINCT code_insee FROM offre_centre_agirc_arrco WHERE ? IS NOT NULL",
    "pro_forme_icope": "SELECT DISTINCT code_insee FROM offre_pro_forme_icope WHERE ? IS NOT NULL",
    "maison_sport_sante": "SELECT DISTINCT code_insee FROM offre_maison_sport_sante WHERE ? IS NOT NULL",
    "a_obtenir": None, "conseil": None, "action_collective": None, "action_domaine": None,
}
# Âges testés quand une proposition dépend de l'âge (ex. Mon bilan prévention : 60-65 et 70-75 ans)
AGES_TESTES = [62, 68, 72, 80]


def distances_au_plus_proche(con, communes, source, valeur):
    """Distance (km) de chaque commune à l'offre la plus proche ; None si l'offre est absente de l'entrepôt."""
    if OFFRE[source] is None:
        return None
    try:
        lieux = con.execute(OFFRE[source], [valeur]).df().dropna().merge(communes, on="code_insee")
    except duckdb.CatalogException:
        return None
    if lieux.empty:
        return None
    lat, lon = np.radians(communes[["latitude", "longitude"]].to_numpy()).T
    la, lo = np.radians(lieux[["latitude", "longitude"]].to_numpy()).T
    d = 2 * 6371 * np.arcsin(np.sqrt(np.sin((la[None] - lat[:, None]) / 2) ** 2
                                     + np.cos(lat[:, None]) * np.cos(la[None]) * np.sin((lo[None] - lon[:, None]) / 2) ** 2))
    return d.min(axis=1)


def controler(con, parcours):
    """Lignes mal écrites et métiers introuvables."""
    problemes = []
    for i, l in parcours.iterrows():
        ligne = f"ligne {i + 2} ({l.domaine}, {l.etape}, plan {l.plan})"
        if l.etape not in ETAPES:
            problemes.append(f"{ligne} : étape inconnue « {l.etape} »")
        if l.plan not in PLANS:
            problemes.append(f"{ligne} : plan inconnu « {l.plan} »")
        if l.source not in OFFRE:
            problemes.append(f"{ligne} : source inconnue « {l.source} »")
        elif l.source == "rpps_profession" and not con.execute(
                "SELECT count(*) FROM v_offre_par_domaine WHERE critere = ?", [l.valeur]).fetchone()[0]:
            problemes.append(f"{ligne} : « {l.valeur} » absent de v_offre_par_domaine (ajouter le métier à referentiel_alertes.csv)")
        elif l.source == "action_domaine" and not con.execute(
                "SELECT count(*) FROM offre_action_collective WHERE domaine_icope = ?", [l.valeur]).fetchall()[0][0]:
            problemes.append(f"{ligne} : aucune action collective classée « {l.valeur} » (colonne domaine_icope)")
    return problemes


def plan_retenu(con, communes, lignes):
    """Pour chaque commune, le premier plan dont l'offre est assez proche (ou sans distance : conseil)."""
    retenu = pd.Series(pd.NA, index=communes.index, dtype="string")
    for plan in sorted(lignes.plan.unique()):
        possible = pd.Series(False, index=communes.index)
        for _, l in lignes[lignes.plan == plan].iterrows():
            if l.source in ("conseil", "action_collective", "action_domaine"):
                possible[:] = True
                continue
            d = distances_au_plus_proche(con, communes, l.source, l.valeur)
            if d is not None:
                possible |= d <= (l.distance_max_km if pd.notna(l.distance_max_km) else np.inf)
        retenu = retenu.mask(retenu.isna() & possible, plan)
    return retenu.fillna("aucun")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--domaine", help="ne vérifier qu'une capacité (ex. vision)")
    args = parser.parse_args()

    parcours = pd.read_csv(PARCOURS, sep=";", dtype={"distance_max_km": float})
    con = duckdb.connect(str(ENTREPOT), read_only=True)
    communes = con.execute("SELECT code_insee, latitude, longitude, TRY_CAST(population AS DOUBLE) AS population "
                           "FROM ref_commune WHERE latitude IS NOT NULL").df()
    communes["population"] = communes["population"].fillna(0)

    problemes = controler(con, parcours)
    print("Contrôle du fichier :", "aucun problème" if not problemes else "")
    for p in problemes:
        print("  -", p)

    if args.domaine:
        parcours = parcours[parcours.domaine.isin([args.domaine, "tous"])]
    resultats = []
    for (domaine, etape), lignes in parcours[parcours.etape.isin(["levee_de_doute", "etape2", "orientation"])].groupby(
            ["domaine", "etape"], sort=False):
        # Si une proposition dépend de l'âge, on refait le calcul pour plusieurs âges
        depend_age = lignes[["age_min", "age_max"]].notna().any().any()
        for age in (AGES_TESTES if depend_age else [None]):
            sous = lignes if age is None else lignes[(lignes.age_min.isna() | (lignes.age_min <= age))
                                                     & (lignes.age_max.isna() | (lignes.age_max >= age))]
            retenu = plan_retenu(con, communes, sous)
            part = communes.groupby(retenu)["population"].sum() / communes["population"].sum() * 100
            resultats.append({"Capacité": domaine, "Étape": etape, "Âge": f"{age} ans" if age else "tous",
                              **{f"Plan {p} (% pop.)": round(part.get(p, 0), 1) for p in ["A", "B", "C"]},
                              "Aucun (% pop.)": round(part.get("aucun", 0), 1)})
    print("\nPlan proposé selon la commune (part de la population de Normandie) :")
    print(pd.DataFrame(resultats).to_string(index=False))
    print("\nRemarques : distance à vol d'oiseau entre centres des communes ; une source « a_obtenir » "
          "(liste pas encore disponible) n'est jamais proposée, on passe au plan suivant.")


if __name__ == "__main__":
    main()
