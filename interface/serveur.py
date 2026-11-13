"""Boussole ICOPE : serveur de l'interface du parcours (bloc 2).

API (JSON) au-dessus du moteur (moteur_parcours.py) et page web (dossier static/).

    GET  /api/meta                 chiffres de l'offre, capacités, profils types
    GET  /api/communes?q=Saint-Lô  suggestions de communes (nom, code postal ou code INSEE)
    POST /api/parcours             {"code_insee": "50502", "age": 84, "alertes": ["cognition"]}

Lancement (depuis la racine du projet, après construire_entrepot.py) :
    python3 interface/serveur.py            puis ouvrir http://localhost:8000
Le serveur n'écoute que sur cet ordinateur (127.0.0.1) : l'entrepôt contient des données de santé.
"""
import math
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from moteur_parcours import CAPACITES, charger_parcours, commune_par_code, connecter, parcours_personne

STATIC = Path(__file__).resolve().parent / "static"

# 5 profils types de la partie 1 (partie1_alertes/1_personnes_en_alerte.py), avec une commune d'exemple
PROFILS = [
    {"titre": "Vision seule", "detail": "65 ans · hors sites", "code_insee": "14762", "commune": "Vire Normandie", "age": 65, "alertes": ["vision"],
     "pourquoi": "Le cas le plus fréquent : une seule alerte."},
    {"titre": "Cognition + mobilité", "detail": "84 ans · Manche", "code_insee": "50502", "commune": "Saint-Lô", "age": 84,
     "alertes": ["cognition", "mobilite"], "pourquoi": "Profil type du Step 2 : très âgée, plusieurs alertes."},
    {"titre": "Psychologie", "detail": "55 ans", "code_insee": "76540", "commune": "Rouen", "age": 55, "alertes": ["psychologie"],
     "pourquoi": "Hors de la cible ICOPE : que lui propose-t-on ?"},
    {"titre": "Nutrition + mobilité", "detail": "75 ans · Calvados", "code_insee": "14366", "commune": "Lisieux", "age": 75,
     "alertes": ["nutrition", "mobilite"], "pourquoi": "Territoire où les alertes sont peu traitées."},
    {"titre": "Audition + vision", "detail": "74 ans · Orne", "code_insee": "61001", "commune": "Alençon", "age": 74,
     "alertes": ["audition", "vision"], "pourquoi": "Personne souvent déjà suivie."},
]

app = FastAPI(title="Boussole ICOPE", docs_url="/api/docs", redoc_url=None)


@lru_cache(maxsize=1)
def _connexion():
    return connecter()


def curseur():
    return _connexion().cursor()


def propre(v):
    """Valeur JSON : NaN -> None, dates -> texte."""
    if v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NaT:
        return None
    if isinstance(v, pd.Timestamp):
        return v.date().isoformat()
    if hasattr(v, "item"):  # nombres numpy
        return v.item()
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def lignes(df):
    if df is None or len(df) == 0:
        return []
    return [{k: propre(v) for k, v in r.items()} for r in df.to_dict("records")]


def statut(prop):
    """Pourquoi une proposition est (ou n'est pas) retenue."""
    if prop.source == "conseil":
        return "conseil"
    if prop.source == "a_obtenir":
        return "a_obtenir"
    if prop.disponible:
        return "trouve"
    if prop.plus_proche_km is not None:
        return "trop_loin"
    return "absent"


def etape_json(e):
    retenu = e.retenu
    return {
        "titre": e.titre, "note": e.note, "type": e.type, "domaine": e.domaine,
        "domaine_nom": CAPACITES.get(e.domaine, ""), "a_parcours": e.a_parcours,
        "plan_retenu": None if retenu is None or retenu.plan == "–" else retenu.plan,
        "plans": [{
            "plan": None if p.plan == "–" else p.plan,
            "disponible": p.disponible,
            "retenu": p is retenu,
            "propositions": [{
                "source": pr.source, "valeur": pr.valeur, "remarque": pr.remarque,
                "distance_max_km": propre(pr.distance_max_km), "plus_proche_km": propre(pr.plus_proche_km),
                "statut": statut(pr), "offres": lignes(pr.offres),
            } for pr in p.propositions],
        } for p in e.plans],
    }


class Demande(BaseModel):
    code_insee: str = Field(pattern=r"^\d{5}$|^2[AB]\d{3}$")
    age: int = Field(ge=18, le=110)
    alertes: list[str] = Field(default_factory=list, max_length=9)

    @field_validator("alertes")
    @classmethod
    def capacites_connues(cls, v):
        inconnues = [a for a in v if a not in CAPACITES]
        if inconnues:
            raise ValueError(f"capacités inconnues : {inconnues}")
        return list(dict.fromkeys(v))  # sans doublon, dans l'ordre


@app.get("/api/meta")
def meta():
    con = curseur()
    compte = lambda sql: con.execute(sql).fetchall()[0][0]
    p = charger_parcours()
    avec_parcours = sorted(set(p[(p.etape == "orientation")].domaine))
    return {
        "chiffres": {
            "professionnels": compte("SELECT count(DISTINCT id_rpps) FROM offre_rpps"),
            "structures": compte("SELECT count(*) FROM offre_finess"),
            "actions": compte("SELECT count(*) FROM offre_action_collective WHERE NOT coalesce(doublon_probable, false)"),
            "communes": compte("SELECT count(*) FROM ref_commune"),
        },
        "capacites": [{"code": c, "nom": n, "a_parcours": c in avec_parcours} for c, n in CAPACITES.items()],
        "profils": PROFILS,
    }


@app.get("/api/communes")
def communes(q: str = Query(min_length=2, max_length=60)):
    con = curseur()
    q = q.strip()
    if re.fullmatch(r"\d{2,5}", q):
        filtre = "(list_has_any(string_split(codes_postaux, '|'), [$q]) OR codes_postaux LIKE $q || '%' OR code_insee = $q)"
        ordre = "TRY_CAST(population AS INTEGER) DESC NULLS LAST"
    else:
        cle = "regexp_replace(lower(strip_accents({})), '[^a-z0-9]+', ' ', 'g')"
        filtre = f"{cle.format('nom')} LIKE '%' || {cle.format('$q')} || '%'"
        ordre = (f"{cle.format('nom')} = {cle.format('$q')} DESC, {cle.format('nom')} LIKE {cle.format('$q')} || '%' DESC, "
                 "TRY_CAST(population AS INTEGER) DESC NULLS LAST")
    res = con.execute(f"""SELECT code_insee, nom, departement, replace(codes_postaux, '|', ', ') AS codes_postaux
                          FROM ref_commune WHERE latitude IS NOT NULL AND {filtre} ORDER BY {ordre} LIMIT 8""",
                      {"q": q}).fetchall()
    return [{"code_insee": c, "nom": n, "departement": d, "codes_postaux": cp} for c, n, d, cp in res]


@app.post("/api/parcours")
def parcours(demande: Demande):
    con = curseur()
    commune = commune_par_code(con, demande.code_insee)
    if commune is None:
        raise HTTPException(404, "Commune introuvable en Normandie")
    etapes, prevention = parcours_personne(con, commune, demande.age, demande.alertes)
    return {
        "personne": {"commune": commune.nom, "code_insee": commune.code_insee,
                     "latitude": commune.latitude, "longitude": commune.longitude,
                     "age": demande.age, "alertes": demande.alertes},
        "etapes": [etape_json(e) for e in etapes],
        "prevention": [{"domaine": d, "domaine_nom": CAPACITES[d], "plan": plan, "generique": plan != "A",
                        "actions": lignes(a)} for d, plan, a in prevention],
    }


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def accueil():
    return FileResponse(STATIC / "index.html")


if __name__ == "__main__":
    import uvicorn
    print("Boussole ICOPE : http://localhost:8000  (Ctrl+C pour arrêter)")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
