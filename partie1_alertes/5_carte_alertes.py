"""Partie 1 – Carte : part des alertes traitées selon le territoire.

Chaque commune de Normandie est coloriée selon son territoire : un des 3 sites d'expérimentation,
ou le reste de son département. « Traitée » = au moins une action d'un professionnel sur l'alerte
(même règle que l'onglet OQQ_Ou du fichier 2).

Les contours des communes viennent de geo.api.gouv.fr (données publiques) : ils sont téléchargés
une seule fois dans le dossier privé (20 Mo, trop lourd pour le dépôt).
Produit : ~/donnees_icope/Partie1_5_Carte_alertes_traitees.png
"""
import json
import os
import urllib.request

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import pandas as pd
from collections import Counter

from matplotlib.collections import LineCollection, PolyCollection

from commun import DEPARTEMENTS, DOSSIER, alertes_analysees, connecter, pct

DEPOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTOURS = os.path.join(DOSSIER, "contours_communes_normandie.geojson")
URL_CONTOURS = "https://geo.api.gouv.fr/communes?codeRegion=28&fields=code,nom&format=geojson&geometry=contour"
SITES = ["Centre Manche", "Elbeuf", "Lisieux"]


def contours():
    if not os.path.exists(CONTOURS):
        print(f"Téléchargement des contours des communes ({URL_CONTOURS})…")
        urllib.request.urlretrieve(URL_CONTOURS, CONTOURS)
    with open(CONTOURS) as f:
        return json.load(f)["features"]


def territoire_des_communes():
    """Territoire de chaque commune : son site d'expérimentation, sinon le reste de son département."""
    communes = pd.read_csv(os.path.join(DEPOT, "bases", "communes_normandie.csv"), sep=";", dtype=str)
    par_commune = pd.read_csv(os.path.join(DEPOT, "entrepot", "communes_experimentation.csv"), sep=";", dtype=str)
    par_cp = pd.read_csv(os.path.join(DEPOT, "entrepot", "territoires_experimentation.csv"), sep=";", dtype=str)
    par_cp = par_cp[~par_cp.experimentation.isin(par_commune.experimentation)]

    site = communes.code_insee.map(dict(zip(par_commune.code_insee, par_commune.experimentation)))
    for cp, nom in zip(par_cp.code_postal, par_cp.experimentation):
        site[site.isna() & communes.codes_postaux.str.contains(cp, na=False)] = nom
    communes["territoire"] = site.fillna("Hors sites - " + communes.departement.map(DEPARTEMENTS))
    return communes


def part_traitee(con):
    alertes = alertes_analysees(con, "v.experimentation, d.departement, v.nb_actions")
    alertes["territoire"] = alertes.experimentation.fillna("Hors sites - " + alertes.departement.map(DEPARTEMENTS))
    taux = alertes.groupby("territoire").agg(alertes=("nb_actions", "size"),
                                            traitees=("nb_actions", lambda s: (s > 0).sum())).reset_index()
    taux["part_traitee"] = pct(taux.traitees, taux.alertes)
    return taux[taux.territoire.str.startswith(("Hors sites - 1", "Hors sites - 2", "Hors sites - 5",
                                                 "Hors sites - 6", "Hors sites - 7")) | taux.territoire.isin(SITES)]


def anneaux(geometrie):
    if geometrie["type"] == "Polygon":
        return [geometrie["coordinates"][0]]
    return [poly[0] for poly in geometrie["coordinates"]]


def limites(contours_par_territoire):
    """Contour de chaque territoire : les côtés de communes qui n'appartiennent qu'à une seule de ses communes."""
    traits = {}
    for territoire, anneaux_t in contours_par_territoire.items():
        cotes = Counter()
        for anneau in anneaux_t:
            points = [tuple(round(c, 5) for c in p) for p in anneau]
            cotes.update(tuple(sorted(c)) for c in zip(points, points[1:]))
        traits[territoire] = [c for c, n in cotes.items() if n == 1]
    return traits


def dessiner(communes, taux):
    valeur = dict(zip(taux.territoire, taux.part_traitee))
    terr = dict(zip(communes.code_insee, communes.territoire))
    cmap = plt.get_cmap("Blues")

    formes, couleurs, par_territoire = [], [], {}
    for f in contours():
        t = terr.get(f["properties"]["code"])
        for anneau in anneaux(f["geometry"]):
            formes.append(anneau)
            couleurs.append(cmap(0.08 + 0.85 * valeur.get(t, 0) / 100))
            par_territoire.setdefault(t, []).append(anneau)

    fig, ax = plt.subplots(figsize=(10, 7.4))
    ax.add_collection(PolyCollection(formes, facecolors=couleurs, edgecolors=couleurs, linewidths=0.2))
    for t, traits in limites(par_territoire).items():
        site = t in SITES
        ax.add_collection(LineCollection(traits, colors="#1a1a1a" if site else "#9aa5b1",
                                         linewidths=1.1 if site else 0.6, zorder=3 if site else 2))
    ax.autoscale_view()
    ax.set_aspect(1 / 0.66)  # correction de la latitude (environ 49° N)
    ax.axis("off")

    # Une étiquette par territoire, au centre de ses communes
    communes = communes.assign(lon=pd.to_numeric(communes.longitude), lat=pd.to_numeric(communes.latitude))
    centres = communes.groupby("territoire")[["lon", "lat"]].mean()
    decalage = {"Hors sites - 50 Manche": (0, 0.35), "Hors sites - 27 Eure": (0.2, -0.25),
                "Hors sites - 14 Calvados": (-0.25, -0.15), "Elbeuf": (0.05, 0.12), "Lisieux": (-0.42, 0.02)}
    for _, ligne in taux.iterrows():
        lon, lat = centres.loc[ligne.territoire]
        dx, dy = decalage.get(ligne.territoire, (0, 0))
        nom = ligne.territoire.replace("Hors sites - ", "")[3:] if ligne.territoire.startswith("Hors") else ligne.territoire
        site = ligne.territoire in SITES
        ax.text(lon + dx, lat + dy, f"{nom}\n{ligne.part_traitee:.0f} %".replace(".", ","), ha="center", va="center",
                fontsize=11 if site else 9.5, fontweight="bold" if site else "normal", color="#1a1a1a",
                path_effects=[pe.withStroke(linewidth=3, foreground="white")])

    ax.set_title("Part des alertes traitées selon le territoire", fontsize=14, color="#1F4E79", fontweight="bold")
    fig.text(0.02, 0.03, "Traitée : au moins une action d'un professionnel notée dans ICOPE. Lisieux : le suivi est fait "
             "par l'équipe Allo Gériatrie, qui ne le note pas toujours dans ICOPE.\nHors des sites, le département est "
             "colorié sans les communes des sites. Contours : geo.api.gouv.fr.", fontsize=8, color="#555555")
    chemin = os.path.join(DOSSIER, "Partie1_5_Carte_alertes_traitees.png")
    fig.savefig(chemin, dpi=200, bbox_inches="tight", facecolor="white")
    print(f"✅ Carte écrite : {chemin}")


if __name__ == "__main__":
    con = connecter()
    taux = part_traitee(con)
    print(taux.to_string(index=False))
    dessiner(territoire_des_communes(), taux)
