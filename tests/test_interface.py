"""Tests de l'API de Boussole ICOPE (interface/serveur.py), sur l'entrepôt réel.

Lancement, depuis la racine du projet :  python3 -m pytest tests/
Les tests sont ignorés si l'entrepôt n'a pas encore été construit.
"""
import json
import sys
from pathlib import Path

import pytest

DEPOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DEPOT / "interface"))
sys.path.insert(0, str(DEPOT / "entrepot"))

from construire_entrepot import ENTREPOT  # noqa: E402

if not ENTREPOT.exists():
    pytest.skip("entrepôt absent : lancer entrepot/construire_entrepot.py", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from serveur import PROFILS, app  # noqa: E402

client = TestClient(app)


def parcours(code_insee, age, alertes):
    r = client.post("/api/parcours", json={"code_insee": code_insee, "age": age, "alertes": alertes})
    assert r.status_code == 200, r.text
    return r.json()


def test_meta():
    m = client.get("/api/meta").json()
    assert m["chiffres"]["communes"] == 2644
    assert m["chiffres"]["professionnels"] > 10000
    assert len(m["capacites"]) == 9
    assert len(m["profils"]) == 5


@pytest.mark.parametrize("q, attendu", [("saint lo", "Saint-Lô"), ("Saint-Lô", "Saint-Lô"), ("50000", "Saint-Lô"),
                                         ("evreux", "Évreux"), ("14400", "Bayeux")])
def test_suggestions_de_communes(q, attendu):
    r = client.get("/api/communes", params={"q": q})
    assert r.status_code == 200
    assert r.json()[0]["nom"] == attendu


def test_suggestions_requete_trop_courte():
    assert client.get("/api/communes", params={"q": "a"}).status_code == 422


@pytest.mark.parametrize("profil", PROFILS, ids=[p["titre"] for p in PROFILS])
def test_les_5_profils_types(profil):
    r = parcours(profil["code_insee"], profil["age"], profil["alertes"])
    types = [e["type"] for e in r["etapes"]]
    if profil["age"] < 60:
        assert types == ["moins_60"]
        assert r["prevention"] == []
    else:
        assert types[0] == "levee_de_doute" and types[-1] == "etape2"
        assert [e["domaine"] for e in r["etapes"] if e["type"] == "orientation"] == profil["alertes"]


def test_levee_de_doute_selon_l_age():
    # Mon bilan prévention (plan A) n'est pris en charge qu'à 60-65 et 70-75 ans
    assert parcours("50502", 72, ["vision"])["etapes"][0]["plan_retenu"] == "A"
    assert parcours("50502", 84, ["vision"])["etapes"][0]["plan_retenu"] != "A"


def test_repli_quand_le_plan_b_est_trop_loin():
    # Rives d'Andaine, 78 ans : le centre Agirc-Arrco le plus proche est à plus de 60 km -> plan C
    levee = parcours("61096", 78, ["vision"])["etapes"][0]
    assert levee["plan_retenu"] == "C"
    plan_b = next(p for p in levee["plans"] if p["plan"] == "B")
    assert plan_b["propositions"][0]["statut"] == "trop_loin"


def test_distances_respectees():
    for e in parcours("14366", 75, ["nutrition", "mobilite", "vision"])["etapes"]:
        for p in e["plans"]:
            for pr in p["propositions"]:
                for o in pr["offres"]:
                    assert pr["distance_max_km"] is None or o["distance_km"] <= pr["distance_max_km"]


def test_capacite_sans_parcours_ecrit():
    etape = parcours("61096", 78, ["incontinence"])["etapes"][1]
    assert etape["a_parcours"] is False and etape["plan_retenu"] is None
    assert any(pr["offres"] for p in etape["plans"] for pr in p["propositions"])


def test_sans_alerte_seulement_la_prevention():
    r = parcours("27229", 70, [])
    assert r["etapes"] == [] and len(r["prevention"]) > 0


def test_aucune_donnee_personnelle_ni_nom_de_professionnel_forme():
    texte = json.dumps(parcours("50502", 84, ["cognition", "mobilite"]), ensure_ascii=False)
    for cle in ("participant", "id_depistage", "ddn", "mt_nom"):
        assert cle not in texte
    r = parcours("14118", 80, ["vision"])  # Caen
    for e in r["etapes"]:
        for p in e["plans"]:
            for pr in p["propositions"]:
                if pr["source"] == "pro_forme_icope":
                    assert all(o["nom"] == "Professionnel formé à ICOPE" and o["telephone"] is None for o in pr["offres"])


@pytest.mark.parametrize("corps, code", [
    ({"code_insee": "50502", "age": 84, "alertes": ["inconnue"]}, 422),
    ({"code_insee": "50502", "age": 12, "alertes": []}, 422),
    ({"code_insee": "abc", "age": 70, "alertes": []}, 422),
    ({"code_insee": "75056", "age": 70, "alertes": []}, 404),  # Paris : hors Normandie
])
def test_demandes_invalides(corps, code):
    assert client.post("/api/parcours", json=corps).status_code == code


def test_page_et_fichiers_statiques():
    assert "Boussole ICOPE" in client.get("/").text
    for f in ("style.css", "app.js", "vendor/leaflet/leaflet.js"):
        assert client.get(f"/static/{f}").status_code == 200
