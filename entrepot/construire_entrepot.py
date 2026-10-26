"""Construit l'entrepôt de données régional ICOPE (DuckDB).

Assemble dans un seul fichier :
  - les exports ICOPE Monitor (étape 1, étape 2, professionnels), lus dans le
    dossier privé DONNEES_ICOPE (par défaut ~/donnees_icope) ;
  - les bases publiques de Normandie du dossier bases/ ;
  - le référentiel des communes et le référentiel alerte -> professionnels.

L'entrepôt est écrit dans DONNEES_ICOPE/entrepot_icope.duckdb : il contient des
données de patients, il ne doit jamais être mis dans le dépôt git.

Utilisation :  python3 entrepot/construire_entrepot.py
"""
import os
import re
import sys
import unicodedata
import warnings
from pathlib import Path

import duckdb
import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

DEPOT = Path(__file__).resolve().parent.parent
BASES = DEPOT / "bases"


def lire_env():
    """Lit le fichier .env du dépôt (KEY=valeur), s'il existe."""
    env = DEPOT / ".env"
    if env.exists():
        for ligne in env.read_text(encoding="utf-8").splitlines():
            if "=" in ligne and not ligne.lstrip().startswith("#"):
                cle, val = ligne.split("=", 1)
                os.environ.setdefault(cle.strip(), val.strip())


lire_env()
DONNEES = Path(os.path.expanduser(os.environ.get("DONNEES_ICOPE", "~/donnees_icope")))
ENTREPOT = DONNEES / "entrepot_icope.duckdb"

DOMAINES = ["cognition", "nutrition", "vision", "audition", "psychologie",
            "mobilite", "social", "aidant", "incontinence"]


# --------------------------------------------------------------------------
# Outils
# --------------------------------------------------------------------------
def slug(texte):
    """'Saint-Lô' -> 'saint_lo' ; 'la_haye_50250' -> 'la_haye'."""
    if texte is None or (isinstance(texte, float) and pd.isna(texte)):
        return ""
    t = unicodedata.normalize("NFKD", str(texte)).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-z]+", "_", t.lower())
    t = re.sub(r"\b(st)\b", "saint", t)
    t = re.sub(r"\b(ste)\b", "sainte", t)
    return t.strip("_")


def dernier_fichier(motif):
    fichiers = sorted(DONNEES.glob(motif))
    if not fichiers:
        sys.exit(f"Fichier introuvable : {DONNEES / motif}")
    return fichiers[-1]


def oui_non(serie):
    """'oui'/'non' -> True/False ; 'dm' (donnée manquante) et vide -> NA."""
    return serie.str.lower().map({"oui": True, "non": False}).astype("boolean")


def sans_dm(serie):
    return serie.where(~serie.isin(["dm", ""]))


class LocalisateurCommune:
    """Retrouve le code INSEE d'une commune à partir du code postal et du nom."""

    def __init__(self, communes):
        self.par_cp = {}
        self.par_nom = {}  # (département, nom) -> code INSEE
        for c in communes.itertuples():
            for cp in str(c.codes_postaux).split("|"):
                self.par_cp.setdefault(cp, []).append((slug(c.nom), c.code_insee, c.population or 0))
            self.par_nom.setdefault((c.departement, slug(c.nom)), c.code_insee)

    def __call__(self, cp, ville):
        cp = str(cp).strip()[:5] if cp is not None and not pd.isna(cp) else ""
        candidats = self.par_cp.get(cp, [])
        v = re.sub(r"_?\d{5}_?", "_", slug(ville)).strip("_")
        v = re.sub(r"_cedex.*$", "", v)
        if not candidats:
            # CP CEDEX, ou code INSEE saisi à la place du CP : on cherche le nom dans le département
            code = self.par_nom.get((cp[:2], v)) if v else None
            return (code, "nom_dans_departement") if code else (None, "hors_normandie_ou_cp_inconnu")
        for nom, code, _ in candidats:
            if v and nom == v:
                return code, "exact"
        for nom, code, _ in candidats:
            if v and (nom.startswith(v) or v.startswith(nom)):
                return code, "approche"
        if len(candidats) == 1:
            return candidats[0][1], "cp_unique"
        # nom non reconnu (ancienne commune, faute de frappe) : commune la plus peuplée du CP
        return max(candidats, key=lambda x: x[2])[1], "cp_principale"


def localiser(df, loc, col_cp, col_ville):
    res = [loc(cp, v) for cp, v in zip(df[col_cp], df[col_ville])]
    df["code_insee"] = [r[0] for r in res]
    df["qualite_localisation"] = [r[1] for r in res]
    return df


# --------------------------------------------------------------------------
# Chargement
# --------------------------------------------------------------------------
def charger_referentiels(con):
    communes = pd.read_csv(BASES / "communes_normandie.csv", sep=";", dtype={"code_insee": str, "code_epci": str, "departement": str})
    con.register("communes_df", communes)
    con.execute("CREATE TABLE ref_commune AS SELECT * FROM communes_df")
    con.execute(f"""
        CREATE TABLE ref_alerte_professionnel AS
        SELECT *, row_number() OVER () AS ordre FROM read_csv('{DEPOT / "entrepot" / "referentiel_alertes.csv"}', delim=';', header=true, all_varchar=true)
    """)
    return communes


def charger_observatoire(con):
    obs = BASES / "observatoire_fragilites"
    for theme in ("fragilite", "bienvieillir"):
        for niveau in ("commune", "epci", "departement"):
            con.execute(f"""
                CREATE TABLE obs_{theme}_{niveau} AS
                SELECT * FROM read_csv('{obs / f"{theme}_{niveau}.csv"}', delim=';', header=true, types={{'code': 'VARCHAR'}})
            """)
            # Valeurs codées « secret statistique / non disponible » : -9999, -99999, -999999 -> vide
            cols = con.execute(f"""SELECT column_name FROM information_schema.columns
                                   WHERE table_name = 'obs_{theme}_{niveau}' AND data_type IN ('BIGINT', 'DOUBLE', 'INTEGER')""").fetchall()
            for (col,) in cols:
                con.execute(f'UPDATE obs_{theme}_{niveau} SET "{col}" = NULL WHERE "{col}" IN (-9999, -99999, -999999)')
        con.execute(f"""
            CREATE TABLE obs_{theme}_dictionnaire AS
            SELECT * FROM read_csv('{obs / f"{theme}_indicateurs.csv"}', delim=';', header=true, all_varchar=true)
        """)


def recaler_communes(con, loc, table, col_cp, col_ville):
    """Remplace les codes INSEE absents du référentiel des communes actuelles."""
    a_recaler = con.execute(f"""
        SELECT DISTINCT {col_cp}, {col_ville} FROM {table}
        WHERE code_insee IS NULL OR code_insee NOT IN (SELECT code_insee FROM ref_commune)""").fetchall()
    corr = pd.DataFrame([(cp, v, loc(cp, v)[0]) for cp, v in a_recaler], columns=["cp", "ville", "nouveau"])
    corr = corr.dropna(subset=["nouveau"])
    if len(corr):
        con.register("corr_df", corr)
        con.execute(f"""
            UPDATE {table} SET code_insee = corr_df.nouveau FROM corr_df
            WHERE {table}.{col_cp} IS NOT DISTINCT FROM corr_df.cp AND {table}.{col_ville} IS NOT DISTINCT FROM corr_df.ville
              AND ({table}.code_insee IS NULL OR {table}.code_insee NOT IN (SELECT code_insee FROM ref_commune))""")
        con.unregister("corr_df")


def charger_offre_publique(con, loc):
    # Annuaire Santé (RPPS) : une ligne par professionnel et lieu d'exercice
    con.execute(f"""
        CREATE TABLE offre_rpps AS
        SELECT DISTINCT
            identifiant_pp AS id_rpps,
            nom_d_exercice AS nom, prenom_d_exercice AS prenom,
            libelle_profession AS profession,
            libelle_savoir_faire AS savoir_faire,
            CASE WHEN libelle_mode_exercice LIKE 'Lib%' THEN 'liberal' ELSE lower(libelle_mode_exercice) END AS mode_exercice,
            raison_sociale_site AS structure,
            numero_finess_site AS finess_site,
            trim(concat_ws(' ', numero_voie_coord_structure, libelle_type_de_voie_coord_structure, libelle_voie_coord_structure)) AS adresse,
            code_postal_coord_structure AS code_postal,
            code_commune_coord_structure AS code_insee,
            libelle_commune_coord_structure AS commune,
            departement,
            telephone_coord_structure AS telephone
        FROM read_csv('{BASES / "annuaire_sante_rpps_normandie.csv"}', delim=';', header=true, all_varchar=true)
        WHERE identifiant_pp IS NOT NULL
    """)
    # FINESS : le code commune est sur 3 chiffres, à préfixer par le département
    con.execute(f"""
        CREATE TABLE offre_finess AS
        SELECT nofinesset AS finess, rs AS nom, rslongue AS nom_long,
               libcategetab AS categorie, libcategagretab AS categorie_agregee,
               trim(concat_ws(' ', numvoie, typvoie, voie)) AS adresse,
               ligneacheminement, departement || commune AS code_insee, departement,
               telephone, TRY_CAST(latitude AS DOUBLE) AS latitude, TRY_CAST(longitude AS DOUBLE) AS longitude,
               TRY_CAST(dateouv AS DATE) AS date_ouverture
        FROM read_csv('{BASES / "finess_etablissements_normandie.csv"}', delim=';', header=true, all_varchar=true)
    """)
    # Codes communes absents ou anciens (communes fusionnées) : on les retrouve par CP + nom de commune
    recaler_communes(con, loc, "offre_rpps", "code_postal", "commune")
    con.execute("ALTER TABLE offre_finess ADD COLUMN ville VARCHAR")
    con.execute("UPDATE offre_finess SET ville = trim(substr(ligneacheminement, 7))")
    con.execute("ALTER TABLE offre_finess ADD COLUMN code_postal VARCHAR")
    con.execute("UPDATE offre_finess SET code_postal = left(ligneacheminement, 5)")
    recaler_communes(con, loc, "offre_finess", "code_postal", "ville")

    # Mon Bilan Prévention : pas de code commune, on le retrouve par CP + ville
    mbp = pd.read_csv(BASES / "mon_bilan_prevention_normandie.csv", sep=";", dtype=str)
    mbp = localiser(mbp, loc, "cp", "ville")
    con.register("mbp_df", mbp)
    con.execute("CREATE TABLE offre_mon_bilan_prevention AS SELECT * FROM mbp_df")


def charger_icope(con, loc):
    # ---- Étape 1 : dépistages
    e1 = pd.read_excel(dernier_fichier("bdi_etape1_*.xlsx"), dtype=str)
    e1 = localiser(e1, loc, "cp", "ville")
    dep = pd.DataFrame({
        "id_depistage": e1["id_etape1"],
        "participant": e1["participant"],
        "type_suivi": e1["type_suivi"],
        "numero": pd.to_numeric(e1["num"], errors="coerce").astype("Int64"),
        "date_depistage": pd.to_datetime(e1["date_etape1"], errors="coerce").dt.date,
        "age": pd.to_numeric(e1["age_etape1"], errors="coerce").astype("Int64"),
        "sexe": e1["sexe"].map({"feminin": "F", "masculin": "M"}),
        "code_postal": sans_dm(e1["cp"]),
        "departement": sans_dm(e1["cp"]).str[:2],
        "code_insee": e1["code_insee"],
        "qualite_localisation": e1["qualite_localisation"],
        "a_medecin_traitant": oui_non(e1["mt"]),
        "consentement_recherche": oui_non(e1["consent_recherche"]),
        "centre": e1["centre"],
        "saisie_par": e1["saisie"],
        "source": e1["source"],
        "version_questionnaire": e1["quest_version"],
        "nb_alertes": pd.to_numeric(e1["nb_alertes"], errors="coerce").astype("Int64"),
        "orientation": e1["orientation"],
        "tags": e1["tags"],
        # identifiant (pseudonyme) du compte qui a saisi le test : sert à repérer les tests
        "id_createur": e1["id_createur"],
    })
    for d in DOMAINES:
        dep[f"alerte_{d}"] = oui_non(e1[f"alerte_{d}"])

    # Modalité ICOPE : auto-évaluation, avec un aidant, ou par un professionnel
    dep["modalite"] = dep["saisie_par"].map({"participant": "auto-évaluation", "aide": "avec un aidant",
                                             "professionnel": "par un professionnel"})

    # Décisions de la réunion du 16/10/2026 avec le Gérontopôle (on marque, on ne supprime rien) :
    #  - deux tests le même jour pour une personne : on ne retient que le dernier (doublon_meme_jour) ;
    #  - essai probable : personne de moins de 50 ans (avant_2022 = indice faible, signalé seulement) ;
    #  - test « one-shot » d'un professionnel (il n'a évalué qu'une personne) : ce n'est plus un essai,
    #    c'est un indicateur à analyser (engagement du professionnel dans le suivi) ;
    #  - moins de 60 ans : gardés dans l'analyse, exclus du parcours.
    dernier_du_jour = dep.groupby(["participant", "date_depistage"])["numero"].transform("max")
    dep["doublon_meme_jour"] = dep["numero"] != dernier_du_jour
    dep["retenu"] = ~dep["doublon_meme_jour"]
    nb_pers = dep.groupby("id_createur")["participant"].transform("nunique")
    dep["nb_personnes_createur"] = nb_pers
    dep["one_shot_pro"] = (dep["saisie_par"] == "professionnel") & (nb_pers == 1)
    raisons = pd.DataFrame({
        "age_moins_50": dep["age"].fillna(99) < 50,
        "avant_2022": pd.to_datetime(dep["date_depistage"]).dt.year < 2022,
    })
    dep["raisons_test"] = raisons.apply(lambda r: ", ".join(c for c in raisons.columns if r[c]) or None, axis=1)
    dep["test_probable"] = raisons["age_moins_50"]
    dep["hors_cible_moins_60"] = dep["age"].fillna(99) < 60

    exp = pd.read_csv(DEPOT / "entrepot" / "territoires_experimentation.csv", sep=";", dtype=str)
    dep["experimentation"] = dep["code_postal"].map(dict(zip(exp.code_postal, exp.experimentation))).astype("string")
    con.register("dep_df", dep)
    con.execute("CREATE TABLE icope_depistage AS SELECT * FROM dep_df")

    # Format long : une ligne par dépistage et par domaine
    con.execute("CREATE TABLE icope_alerte AS " + " UNION ALL ".join(
        f"SELECT id_depistage, participant, date_depistage, departement, code_insee, modalite, retenu, '{d}' AS domaine, alerte_{d} AS alerte FROM icope_depistage"
        for d in DOMAINES))

    # ---- Étape 2 : évaluations
    e2 = pd.read_excel(dernier_fichier("bdi_etape2_*.xlsx"), dtype=str)
    e2 = localiser(e2, loc, "cp", "ville")
    ev = pd.DataFrame({
        "id_evaluation": e2["id_etape2"],
        "participant": e2["participant"],
        "type_visite": e2["type_visite"],
        "date_evaluation": pd.to_datetime(e2["date_etape2"], errors="coerce").dt.date,
        "age": pd.to_numeric(e2["age_etape2"], errors="coerce").astype("Int64"),
        "sexe": e2["sexe"].map({"feminin": "F", "masculin": "M"}),
        "code_postal": sans_dm(e2["cp"]),
        "departement": sans_dm(e2["cp"]).str[:2],
        "code_insee": e2["code_insee"],
        "experimentation": sans_dm(e2["cp"]).map(dict(zip(exp.code_postal, exp.experimentation))).astype("string"),
        "centre": e2["centre"],
        "protocole_fragilite": oui_non(e2["protocole_fragilite_ou_51"]),
        "visite_domicile": oui_non(e2["visite_domicile"]),
        "nb_km": pd.to_numeric(e2["nb_km"], errors="coerce"),
        "reperage_par": e2["reperage"],
        "evaluateur": e2["evaluateur"],
    })
    con.register("ev_df", ev)
    con.execute("CREATE TABLE icope_evaluation AS SELECT * FROM ev_df")

    # ---- Professionnels inscrits sur ICOPE
    pr = pd.read_excel(dernier_fichier("bdi_professionnels_*.xlsx"), dtype=str)
    pr = localiser(pr, loc, "Code postal", "Ville")
    pro = pd.DataFrame({
        "id_professionnel": pr["ID"],
        "profession": pr["Profession"],
        "autre_profession": pr["Autre profession"],
        "type_activite": pr["Type d’activité"],
        "gestion_alerte": oui_non(pr["Gestion d’alerte"]),
        "type_etablissement": pr["Type d’établissement"],
        "etablissement": pr["Nom établissement"],
        "code_postal": pr["Code postal"],
        "departement": pr["Code postal"].str[:2],
        "code_insee": pr["code_insee"],
        "profil": pr["Profil"],
        "statut": pr["Statut"],
        "date_inscription": pd.to_datetime(pr["Date de création"], errors="coerce").dt.date,
    })
    con.register("pro_df", pro)
    con.execute("CREATE TABLE icope_professionnel AS SELECT * FROM pro_df")

    charger_alertes(con, loc, exp)


# Colonnes jamais chargées (données identifiantes, en attendant l'avis du Gérontopôle) :
# date de naissance, nom et ville du médecin traitant, commentaires libres, noms des professionnels.
COLONNES_EXCLUES = {"ddn", "mt_nom", "mt_ville", "commentaires", "nom_auteur_prise_en_charge", "nom_createur", "ville"}


def oui_non_partout(df):
    """Colonnes ne contenant que oui / non / dm -> vrai / faux / vide."""
    for col in df.columns:
        if df[col].dtype != object:
            continue
        valeurs = set(df[col].dropna().astype(str).str.lower())
        if valeurs and valeurs <= {"oui", "non", "dm"}:
            df[col] = oui_non(df[col])
    return df


def charger_alertes(con, loc, exp):
    """Statut des alertes et traitements (levée de doute, orientations) : fichiers du 17/10/2026."""
    f_alertes = sorted(DONNEES.glob("bdi_alertes_*.xlsx"))
    f_traitements = sorted(DONNEES.glob("bdi_traitements_alertes_*.xlsx"))
    if not f_alertes or not f_traitements:
        print("(fichiers bdi_alertes / bdi_traitements_alertes absents : tables d'alertes non créées)")
        return
    sites = dict(zip(exp.code_postal, exp.experimentation))

    def commun(df):
        df = localiser(df, loc, "cp", "ville")
        date = pd.to_datetime(df["date_alerte"], errors="coerce")
        naissance = pd.to_datetime(df["ddn"], errors="coerce")
        df["age"] = ((date - naissance).dt.days // 365.25).astype("Int64")  # on garde l'âge, pas la date de naissance
        df["code_postal"] = sans_dm(df["cp"])
        df["departement"] = df["code_postal"].str[:2]
        df["experimentation"] = df["code_postal"].map(sites).astype("string")
        df["modalite_test"] = df["saisie"].map({"participant": "auto-évaluation", "aide": "avec un aidant",
                                                "professionnel": "par un professionnel"})
        df["sexe"] = df["sexe"].map({"feminin": "F", "masculin": "M"})
        df["date_alerte"] = date.dt.date
        df["date_etape1"] = pd.to_datetime(df["date_etape1"], errors="coerce").dt.date
        df = df.rename(columns={"alerte": "id_alerte", "etape1": "id_depistage", "mt": "a_medecin_traitant"})
        return oui_non_partout(df.drop(columns=[c for c in df.columns if c in COLONNES_EXCLUES or c in ("cp", "saisie")]))

    al = commun(pd.read_excel(f_alertes[-1], dtype=str))
    con.register("al_df", al)
    con.execute("CREATE TABLE icope_alerte_statut AS SELECT * FROM al_df")

    tr = pd.read_excel(f_traitements[-1], dtype=str)
    tr = tr.rename(columns={"traitement": "id_traitement", "id_auteur_prise_en_charge": "id_auteur"})
    tr["date_prise_en_charge"] = pd.to_datetime(tr["date_prise_en_charge"], errors="coerce").dt.date
    tr = commun(tr)
    con.register("tr_df", tr)
    con.execute("CREATE TABLE icope_traitement AS SELECT * FROM tr_df")
    for nom in ("al_df", "tr_df"):
        con.unregister(nom)
    # Âge : celui d'ICOPE quand le dépistage est connu (le calcul depuis la date de naissance peut différer d'un an)
    for table in ("icope_alerte_statut", "icope_traitement"):
        con.execute(f"UPDATE {table} t SET age = d.age FROM icope_depistage d WHERE t.id_depistage = d.id_depistage")


def creer_vues(con):
    # Parcours d'une personne : premier dépistage, suivis, alertes, étape 2
    con.execute("""
        CREATE VIEW v_parcours_participant AS
        WITH d AS (
            -- tests retenus seulement (un seul par jour : le dernier)
            SELECT participant,
                   min(date_depistage) AS premier_depistage,
                   max(date_depistage) AS dernier_depistage,
                   count(*) AS nb_depistages,
                   count(*) = 1 AS one_shot,
                   arg_min(modalite, numero) AS modalite_premier_test,
                   arg_max(modalite, numero) AS modalite_dernier_test,
                   arg_min(age, numero) AS age_premier_test,
                   arg_min(nb_alertes, numero) AS nb_alertes_initial,
                   arg_min(departement, numero) AS departement,
                   arg_min(code_insee, numero) AS code_insee,
                   arg_min(experimentation, numero) AS experimentation,
                   bool_or(orientation IS NOT NULL) AS orientation_renseignee,
                   bool_or(hors_cible_moins_60) AS moins_60_ans,
                   bool_or(test_probable) AS test_probable
            FROM icope_depistage WHERE retenu GROUP BY participant
        ), e AS (
            SELECT participant, min(date_evaluation) AS premiere_evaluation, count(*) AS nb_evaluations
            FROM icope_evaluation GROUP BY participant
        )
        SELECT d.*, e.premiere_evaluation, coalesce(e.nb_evaluations, 0) AS nb_evaluations,
               e.participant IS NOT NULL AS a_etape2
        FROM d LEFT JOIN e USING (participant)
    """)
    # Offre de professionnels utiles pour chaque domaine d'alerte, par commune
    con.execute("""
        CREATE VIEW v_offre_par_domaine AS
        SELECT r.domaine, r.role, r.ordre, r.valeur AS critere, 'rpps' AS source, o.profession, o.savoir_faire,
               o.id_rpps AS identifiant, o.nom || ' ' || o.prenom AS nom, o.structure,
               o.adresse, o.code_postal, o.code_insee, o.departement, o.telephone
        FROM ref_alerte_professionnel r
        JOIN offre_rpps o
          ON r.source = 'rpps_profession'
         AND (r.valeur = o.profession OR r.valeur = o.profession || '|' || o.savoir_faire)
         AND o.adresse <> ''
        UNION ALL
        SELECT r.domaine, r.role, r.ordre, r.valeur, 'finess', f.categorie, NULL, f.finess, f.nom, f.nom_long,
               f.adresse, left(f.ligneacheminement, 5), f.code_insee, f.departement, f.telephone
        FROM ref_alerte_professionnel r
        JOIN offre_finess f ON r.source = 'finess_categorie' AND r.valeur = f.categorie
    """)

    # Issue de chaque alerte : une ligne par alerte. Dans ICOPE, un « traitement » est une action
    # sur l'alerte (appel, vérification, conseil...) ; on ne parle d'« orientation » que lorsque la
    # personne est dirigée vers un professionnel ou une structure.
    tables = {t for (t,) in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
    if {"icope_alerte_statut", "icope_traitement"} <= tables:
        con.execute("""
            CREATE VIEW v_alerte_issue AS
            WITH t AS (
                SELECT id_alerte,
                       count(*) AS nb_actions,
                       min(date_prise_en_charge) AS premiere_action,
                       max(date_prise_en_charge) AS derniere_action,
                       arg_min(id_auteur, date_prise_en_charge) AS id_auteur_premiere_action,
                       bool_or(veracite IS NOT NULL) AS levee_doute_faite,
                       bool_or(veracite = 'alerte_vraie') AS alerte_confirmee,
                       bool_or(orientation_rdv_medecin OR orientation_contact_medecin OR orientation_oriente_etape2
                               OR orientation_fait_etape2 OR orientation_structure_hospitaliere) AS oriente,
                       bool_or(orientation_autre) AS oriente_autre,
                       bool_or(orientation_infos) AS informations,
                       bool_or(pas_orientation_domaines_deja_pris_en_charge) AS deja_pris_en_charge,
                       bool_or(pas_orientation_pas_necessaire OR pas_orientation_refus) AS pas_necessaire_ou_refus,
                       bool_or(veracite = 'alerte_fausse') AS fausse_alerte,
                       bool_and(coalesce(distance_participant_non_joignable, false)) AS seulement_injoignable
                FROM icope_traitement GROUP BY id_alerte
            )
            SELECT a.id_alerte, a.id_depistage, a.participant, a.date_alerte, a.statut_alerte,
                   a.modalite_test, a.age, a.sexe, a.departement, a.code_insee, a.experimentation,
                   coalesce(t.nb_actions, 0) AS nb_actions, t.premiere_action, t.derniere_action,
                   t.id_auteur_premiere_action, coalesce(t.levee_doute_faite, false) AS levee_doute_faite,
                   coalesce(t.alerte_confirmee, false) AS alerte_confirmee, coalesce(t.oriente, false) AS oriente,
                   CASE
                       WHEN t.id_alerte IS NULL THEN '0. Pas prise en charge'
                       WHEN t.oriente THEN '1. Orientée vers un professionnel ou une structure'
                       WHEN t.oriente_autre THEN '2. Orientée « autre » (sans précision)'
                       WHEN t.deja_pris_en_charge THEN '3. Pas orientée : déjà prise en charge'
                       WHEN t.fausse_alerte THEN '4. Fausse alerte'
                       WHEN t.pas_necessaire_ou_refus THEN '5. Pas orientée : pas nécessaire ou refus'
                       WHEN t.informations THEN '6. Informations données seulement'
                       WHEN t.seulement_injoignable THEN '7. Personne injoignable'
                       WHEN t.levee_doute_faite THEN '8. Levée de doute faite, suite non renseignée'
                       ELSE '9. Prise en charge, rien de renseigné'
                   END AS issue
            FROM icope_alerte_statut a LEFT JOIN t USING (id_alerte)
        """)


def main():
    DONNEES.mkdir(parents=True, exist_ok=True)
    if ENTREPOT.exists():
        ENTREPOT.unlink()
    con = duckdb.connect(str(ENTREPOT))
    communes = charger_referentiels(con)
    loc = LocalisateurCommune(communes)
    charger_observatoire(con)
    charger_offre_publique(con, loc)
    charger_icope(con, loc)
    creer_vues(con)
    for nom in ("communes_df", "mbp_df", "dep_df", "ev_df", "pro_df"):
        con.unregister(nom)

    print(f"Entrepôt construit : {ENTREPOT}\n")
    for (table,) in con.execute("SELECT table_name FROM information_schema.tables ORDER BY 1").fetchall():
        n = con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
        print(f"  {table:32s} {n:>8,} lignes".replace(",", " "))
    print("\nLocalisation des dépistages :")
    for q, n in con.execute("SELECT qualite_localisation, count(*) FROM icope_depistage GROUP BY 1 ORDER BY 2 DESC").fetchall():
        print(f"  {q:32s} {n:>8}")
    con.close()


if __name__ == "__main__":
    main()
