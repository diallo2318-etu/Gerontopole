"""Rattache aux communes les territoires cités dans les fichiers « Actions collectives » (UTAS, MDS).

Écrit DONNEES_ICOPE/ref_territoire_action.csv (colonnes departement;niveau;territoire;codes_insee),
lu par charger_prevention.py à la construction de l'entrepôt.

  - Seine-Maritime (76) : les 5 UTAS, d'après bases/utas_seine_maritime.csv (open data du Département 76).
  - Calvados (14) : les 5 territoires d'action sociale (Maisons départementales des solidarités), d'après
    bases/territoires_action_sociale_calvados.csv. Ce fichier est construit à partir des contours publiés par
    le Département du Calvados (data.calvados.fr, jeu « Les Maisons Départementales des Solidarités » sur
    data.gouv.fr) : une commune appartient au territoire qui contient son centre (coordonnées de ref_commune).
    Il est téléchargé et construit au premier lancement s'il n'existe pas.
  - Manche (50) : les secteurs restent vides (la plupart des actions sont déjà rattachées par l'intercommunalité).

Utilisation :
    python3 entrepot/rattacher_territoires.py
    python3 entrepot/construire_entrepot.py      # puis reconstruire l'entrepôt
"""
import json
import urllib.request

import pandas as pd

from construire_entrepot import BASES, DONNEES, slug

URL_CALVADOS = "https://data.calvados.fr/solidarite/territoires_action_sociale.geojson"
CALVADOS = BASES / "territoires_action_sociale_calvados.csv"

# Nom du territoire dans les fichiers « Actions collectives » -> nom dans la base de référence
UTAS_76 = {"UTAS Rouen": "UTAS Rouen", "UTAS BDS": "UTAS Boucles de Seine",
           "UTAS Seine et Mer": "UTAS Entre Seine et Mer", "UTAS DNB": "UTAS Dieppe/Neufchâtel",
           "UTAS LH Pointe de Caux": "UTAS Le Havre Pointe de Caux"}
TAS_14 = {"Caen Elargi": "Caen élargi", "Bessin": "Bessin", "Bocage": "Bocage",
          "Falaise": "Falaise","Pays d'Auge": "Pays d'Auge"}


def dans_anneau(x, y, anneau):
    """Le point (x, y) est-il dans le polygone ? (méthode du rayon)"""
    dedans = False
    for (x1, y1), (x2, y2) in zip(anneau, anneau[1:] + anneau[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            dedans = not dedans
    return dedans


def dans_multipolygone(x, y, geometrie):
    polygones = geometrie["coordinates"] if geometrie["type"] == "MultiPolygon" else [geometrie["coordinates"]]
    # premier anneau = contour extérieur, les suivants = trous
    return any(dans_anneau(x, y, p[0]) and not any(dans_anneau(x, y, t) for t in p[1:]) for p in polygones)


def construire_calvados():
    print(f"Téléchargement des territoires d'action sociale du Calvados : {URL_CALVADOS}")
    with urllib.request.urlopen(URL_CALVADOS, timeout=60) as r:
        territoires = json.load(r)["features"]
    communes = pd.read_csv(BASES / "communes_normandie.csv", sep=";", dtype={"code_insee": str, "departement": str})
    communes = communes[communes["departement"] == "14"]
    lignes = []
    for c in communes.itertuples():
        noms = [t["properties"]["nom"] for t in territoires if dans_multipolygone(c.longitude, c.latitude, t["geometry"])]
        lignes.append((c.code_insee, c.nom, noms[0] if len(noms) == 1 else None))
    df = pd.DataFrame(lignes, columns=["code_insee", "commune", "territoire_action_sociale"])
    df["source"] = "contours data.calvados.fr (territoires_action_sociale.geojson), centre de la commune"
    df.to_csv(CALVADOS, sep=";", index=False)
    sans = df["territoire_action_sociale"].isna().sum()
    print(f"  {len(df)} communes du Calvados, {sans} sans territoire (centre hors des contours)")
    return df


def main():
    calvados = pd.read_csv(CALVADOS, sep=";", dtype=str) if CALVADOS.exists() else construire_calvados()
    utas = pd.read_csv(BASES / "utas_seine_maritime.csv", sep=";", dtype=str)

    lignes = []
    for nom_fichier, nom_ref in UTAS_76.items():
        codes = utas.loc[utas["utas"] == nom_ref, "code_insee"]
        lignes.append(("76", "utas", nom_fichier, "|".join(codes)))
    for nom_fichier, nom_ref in TAS_14.items():
        codes = calvados.loc[calvados["territoire_action_sociale"].map(slug) == slug(nom_ref), "code_insee"]
        lignes.append(("14", "mds", nom_fichier, "|".join(codes)))
    ref = pd.DataFrame(lignes, columns=["departement", "niveau", "territoire", "codes_insee"])

    vides = ref[ref["codes_insee"] == ""]
    if len(vides):
        raise SystemExit(f"Territoires sans commune (nom à vérifier) : {list(vides['territoire'])}")
    sortie = DONNEES / "ref_territoire_action.csv"
    ref.to_csv(sortie, sep=";", index=False)
    print(f"Fichier écrit : {sortie}")
    for r in ref.itertuples():
        print(f"  {r.departement} {r.niveau:5s} {r.territoire:24s} {len(r.codes_insee.split('|')):>4} communes")
    print("Relancer maintenant : python3 entrepot/construire_entrepot.py")


if __name__ == "__main__":
    main()
