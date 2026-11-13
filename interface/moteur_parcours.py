"""Moteur du parcours ICOPE : pour une personne (commune, âge, alertes), qui proposer et où ?

Lit le fichier commun des parcours (entrepot/parcours_capacites.csv) et l'offre de l'entrepôt.
Pour chaque étape, le plan A est retenu si une offre est à moins de distance_max_km (à vol d'oiseau
entre les centres des communes), sinon le plan B, puis le plan C.

Utilisé par l'interface (interface/app.py). Test sans interface :
    python3 interface/moteur_parcours.py "Vire Normandie" 72 vision audition
"""
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import pandas as pd

DEPOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DEPOT / "entrepot"))
from construire_entrepot import ENTREPOT  # noqa: E402

PARCOURS = DEPOT / "entrepot" / "parcours_capacites.csv"

CAPACITES = {"vision": "Vision", "audition": "Audition", "cognition": "Cognition (mémoire)",
             "mobilite": "Mobilité", "nutrition": "Nutrition", "psychologie": "Psychologie (moral)",
             "incontinence": "Incontinence", "social": "Social", "aidant": "Aidant"}

# Offre de chaque source, avec les mêmes colonnes partout. $valeur = colonne « valeur » du parcours.
# Les professionnels formés à ICOPE viennent d'une liste privée : on n'affiche ni nom ni coordonnées.
OFFRE_SQL = {
    "rpps_profession": """
        SELECT identifiant, nom, coalesce(profession || ' - ' || savoir_faire, profession) AS detail,
               adresse, code_postal, telephone, code_insee
        FROM v_offre_par_domaine WHERE source = 'rpps' AND critere = $valeur""",
    "finess_categorie": """
        SELECT finess AS identifiant, nom, categorie AS detail, adresse, code_postal, telephone, code_insee
        FROM offre_finess WHERE categorie = $valeur""",
    "ipa": """
        SELECT i.id_rpps AS identifiant, i.nom || ' ' || i.prenom AS nom,
               'Infirmier en pratique avancée' AS detail, any_value(r.adresse) AS adresse,
               any_value(r.code_postal) AS code_postal, any_value(r.telephone) AS telephone, i.code_insee
        FROM offre_ipa i LEFT JOIN offre_rpps r ON r.id_rpps = i.id_rpps AND r.code_insee = i.code_insee
        WHERE i.pathologies_chroniques GROUP BY i.id_rpps, i.nom, i.prenom, i.code_insee""",
    "mon_bilan_prevention": """
        SELECT coalesce(identifiant_rpps, identifiant_finess, nom) AS identifiant, nom,
               coalesce(profession, CASE WHEN nom ILIKE 'pharmacie%' THEN 'Pharmacie' ELSE 'Professionnel' END)
                   || ' (Mon bilan prévention)' AS detail, adresse, cp AS code_postal,
               numero_de_telephone AS telephone, code_insee
        FROM offre_mon_bilan_prevention""",
    "agirc_arrco": """
        SELECT 'agirc_' || id_centre AS identifiant, 'Agirc-Arrco - ' || nom AS nom,
               'Centre de prévention Agirc-Arrco (retraités du privé)' AS detail, adresse, code_postal,
               CAST(NULL AS VARCHAR) AS telephone, code_insee
        FROM offre_centre_agirc_arrco""",
    "pro_forme_icope": """
        SELECT 'forme_' || ligne_origine AS identifiant, 'Professionnel formé à ICOPE' AS nom,
               coalesce(profession_si_autre, profession) AS detail, CAST(NULL AS VARCHAR) AS adresse,
               code_postal, CAST(NULL AS VARCHAR) AS telephone, code_insee
        FROM offre_pro_forme_icope WHERE region_normandie AND NOT compte_test_probable""",
    "maison_sport_sante": """
        SELECT nom AS identifiant, nom, 'Maison sport-santé' AS detail, adresse, code_postal, telephone, code_insee
        FROM offre_maison_sport_sante""",
}

DISTANCE_KM = """2 * 6371 * asin(sqrt(
    pow(sin(radians(c.latitude - $lat) / 2), 2)
    + cos(radians($lat)) * cos(radians(c.latitude)) * pow(sin(radians(c.longitude - $lon) / 2), 2)))"""


@dataclass
class Commune:
    code_insee: str
    nom: str
    latitude: float
    longitude: float


@dataclass
class Proposition:
    """Une ligne du parcours, avec l'offre trouvée près de la personne."""
    source: str
    valeur: str
    remarque: str
    distance_max_km: float | None
    offres: pd.DataFrame | None = None      # les plus proches, dans la limite de distance
    plus_proche_km: float | None = None     # distance de l'offre la plus proche, même hors limite

    @property
    def disponible(self):
        if self.source == "conseil":
            return True
        return self.offres is not None and len(self.offres) > 0


@dataclass
class Plan:
    plan: str
    propositions: list = field(default_factory=list)

    @property
    def disponible(self):
        return any(p.disponible for p in self.propositions)


@dataclass
class Etape:
    titre: str
    plans: list
    note: str = ""

    @property
    def retenu(self):
        return next((p for p in self.plans if p.disponible), None)


def sans_accents(texte):
    return unicodedata.normalize("NFKD", str(texte)).encode("ascii", "ignore").decode().lower()


def connecter():
    return duckdb.connect(str(ENTREPOT), read_only=True)


def charger_parcours():
    p = pd.read_csv(PARCOURS, sep=";", dtype=str).fillna("")
    for col in ("distance_max_km", "age_min", "age_max"):
        p[col] = pd.to_numeric(p[col], errors="coerce")
    return p


def trouver_communes(con, texte):
    """Code postal, code INSEE ou nom -> liste de communes (la plus peuplée d'abord)."""
    texte = str(texte).strip()
    colonnes = "code_insee, nom, latitude, longitude"
    if re.fullmatch(r"\d{5}|2[AB]\d{3}", texte):
        lignes = con.execute(f"""SELECT {colonnes} FROM ref_commune
                                 WHERE list_contains(string_split(codes_postaux, '|'), $t) OR code_insee = $t
                                 ORDER BY TRY_CAST(population AS INTEGER) DESC NULLS LAST""", {"t": texte}).fetchall()
    else:
        cle = "regexp_replace(lower(strip_accents({})), '[^a-z0-9]+', ' ', 'g')"
        lignes = con.execute(f"""SELECT {colonnes} FROM ref_commune
                                 WHERE {cle.format('nom')} LIKE '%' || {cle.format('$t')} || '%'
                                 ORDER BY {cle.format('nom')} = {cle.format('$t')} DESC,
                                          TRY_CAST(population AS INTEGER) DESC NULLS LAST LIMIT 20""",
                             {"t": texte}).fetchall()
    return [Commune(*l) for l in lignes if l[2] is not None]


def plus_proches(con, source, valeur, commune, nombre=3):
    """Les `nombre` offres les plus proches de la commune (un même professionnel n'apparaît qu'une fois)."""
    sql = OFFRE_SQL[source]
    params = {"lat": commune.latitude, "lon": commune.longitude}
    if "$valeur" in sql:
        params["valeur"] = valeur
    try:
        return con.execute(f"""
            WITH o AS ({sql}),
            d AS (SELECT o.*, c.nom AS commune, round({DISTANCE_KM}, 1) AS distance_km
                  FROM o JOIN ref_commune c USING (code_insee)
                  QUALIFY row_number() OVER (PARTITION BY o.identifiant ORDER BY distance_km) = 1)
            SELECT nom, detail, adresse, code_postal, commune, distance_km, telephone
            FROM d ORDER BY distance_km, nom LIMIT {int(nombre)}""", params).df()
    except duckdb.CatalogException:   # table absente de l'entrepôt (fichier pas encore reçu)
        return pd.DataFrame()


def evaluer(con, lignes, commune, nombre=3):
    """Transforme les lignes du parcours d'une étape en plans A / B / C avec l'offre trouvée."""
    plans = []
    for nom_plan in sorted(lignes["plan"].unique()):
        plan = Plan(nom_plan)
        for l in lignes[lignes["plan"] == nom_plan].itertuples():
            limite = None if pd.isna(l.distance_max_km) else float(l.distance_max_km)
            prop = Proposition(l.source, l.valeur, l.remarque, limite)
            if l.source in OFFRE_SQL:
                toutes = plus_proches(con, l.source, l.valeur, commune, nombre)
                if len(toutes):
                    prop.plus_proche_km = float(toutes["distance_km"].iloc[0])
                    prop.offres = toutes if limite is None else toutes[toutes["distance_km"] <= limite]
            plan.propositions.append(prop)
        plans.append(plan)
    return plans


def filtre_age(lignes, age):
    return lignes[(lignes["age_min"].isna() | (lignes["age_min"] <= age))
                  & (lignes["age_max"].isna() | (lignes["age_max"] >= age))]


def actions_prevention(con, commune, source, valeur, nombre=3):
    """Actions collectives accessibles depuis la commune (les plus locales d'abord), encore en cours."""
    if source == "action_domaine":
        filtre, params = "a.domaine_icope = $valeur", {"valeur": valeur}
    else:  # action_collective : mots-clés séparés par |, au début d'un mot (« vision » mais pas « révision »)
        filtre = """regexp_matches(lower(strip_accents(coalesce(a.intitule, '') || ' ' || coalesce(a.theme_brut, ''))), $motif)"""
        params = {"motif": r"\b(" + sans_accents(valeur) + ")"}
    params["insee"] = commune.code_insee
    try:
        return con.execute(f"""
            WITH couverture AS (SELECT id_action, count(*) AS nb_communes FROM v_action_commune GROUP BY 1)
            SELECT DISTINCT a.intitule AS action, a.porteur, a.lieu_texte AS lieu, a.date_fin, k.nb_communes
            FROM offre_action_collective a
            JOIN v_action_commune v USING (id_action) JOIN couverture k USING (id_action)
            WHERE v.code_insee = $insee AND a.intitule IS NOT NULL AND NOT coalesce(a.doublon_probable, false)
              AND (TRY_CAST(a.date_fin AS DATE) IS NULL OR TRY_CAST(a.date_fin AS DATE) >= current_date)
              AND {filtre}
            ORDER BY k.nb_communes, a.intitule LIMIT {int(nombre)}""", params).df().drop(columns="nb_communes")
    except duckdb.CatalogException:
        return pd.DataFrame()


def offre_referentiel(con, domaine, commune, nombre=3):
    """Capacité sans parcours écrit : les métiers du référentiel d'alertes, les plus proches."""
    criteres = [c for (c,) in con.execute(
        "SELECT DISTINCT critere FROM v_offre_par_domaine WHERE domaine = $d AND source = 'rpps'", {"d": domaine}).fetchall()]
    plan = Plan("–")
    for c in criteres:
        prop = Proposition("rpps_profession", c, "", None, plus_proches(con, "rpps_profession", c, commune, nombre))
        plan.propositions.append(prop)
    return [plan]


def parcours_personne(con, commune, age, alertes, nombre=3):
    """Le parcours complet d'une personne : une liste d'étapes à afficher, dans l'ordre."""
    p = charger_parcours()
    etapes = []
    if age < 60:
        etapes.append(Etape("Moins de 60 ans : un conseil", evaluer(con, p[p.etape == "moins_60"], commune, nombre),
                            "Pas d'orientation avant 60 ans (décision du Gérontopôle)."))
        return etapes, []
    if alertes:
        etapes.append(Etape("1. Levée de doute : qui vérifie l'alerte ?",
                            evaluer(con, filtre_age(p[p.etape == "levee_de_doute"], age), commune, nombre),
                            f"Propositions pour une personne de {age} ans."))
        for d in alertes:
            lignes = filtre_age(p[(p.domaine == d) & (p.etape == "orientation")], age)
            titre = f"2. Alerte {CAPACITES[d].lower()} confirmée : vers qui orienter ?"
            if len(lignes):
                etapes.append(Etape(titre, evaluer(con, lignes, commune, nombre)))
            else:
                etapes.append(Etape(titre, offre_referentiel(con, d, commune, nombre),
                                    "Parcours pas encore écrit pour cette capacité : métiers du référentiel d'alertes, sans plan A/B/C."))
        etapes.append(Etape("3. Évaluation approfondie (Step 2)",
                            evaluer(con, filtre_age(p[p.etape == "etape2"], age), commune, nombre)))
    # Prévention : pour chaque capacité sans alerte, le premier plan qui trouve des actions
    prevention = []
    for d in CAPACITES:
        if d in alertes:
            continue
        lignes = p[(p.domaine == d) & (p.etape == "sans_alerte")]
        for nom_plan in sorted(lignes["plan"].unique()):
            trouvees = [actions_prevention(con, commune, l.source, l.valeur, nombre)
                        for l in lignes[lignes.plan == nom_plan].itertuples()]
            trouvees = pd.concat([t for t in trouvees if len(t)], ignore_index=True) if any(len(t) for t in trouvees) else None
            if trouvees is not None:
                prevention.append((d, nom_plan, trouvees.drop_duplicates("action").head(nombre)))
                break
    return etapes, prevention


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    con = connecter()
    communes = trouver_communes(con, sys.argv[1])
    if not communes:
        sys.exit(f"Commune introuvable : {sys.argv[1]}")
    commune, age, alertes = communes[0], int(sys.argv[2]), sys.argv[3:]
    etapes, prevention = parcours_personne(con, commune, age, alertes)
    print(f"{commune.nom} ({commune.code_insee}), {age} ans, alertes : {', '.join(alertes) or 'aucune'}\n")
    for e in etapes:
        r = e.retenu
        print(f"== {e.titre}  ->  plan retenu : {r.plan if r else 'aucun'}")
        if r:
            for prop in r.propositions:
                if prop.source == "conseil":
                    print(f"   conseil : {prop.valeur}")
                elif prop.disponible:
                    for o in prop.offres.itertuples():
                        print(f"   {o.distance_km:5.1f} km  {o.detail} - {o.nom}, {o.commune}")
    for d, plan, actions in prevention:
        print(f"== Prévention {d} (plan {plan}) : " + " ; ".join(actions["action"].str[:60]))


if __name__ == "__main__":
    main()
