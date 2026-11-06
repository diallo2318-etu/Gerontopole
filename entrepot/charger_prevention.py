"""Charge dans l'entrepôt les fichiers de prévention.

Fichiers lus dans DONNEES_ICOPE (les noms peuvent avoir des espaces ou des underscores) :
  - « Actions collectives <département>.xlsx » (Seine-Maritime, Calvados, Eure, Manche, Orne)
  - « liste pro formés icope Normandie.xlsx »  (liste Toulouse, toute la France)
  - « complet bdi_professionnels_<date>.xlsx » (avec les numéros RPPS)

Tables créées :
  offre_action_collective      une ligne par action, colonnes harmonisées entre les 5 départements
  offre_action_territoire      où se déroule chaque action (UTAS, territoire MDS, EPCI, secteur, commune...)
  v_action_commune (vue)       action x commune couverte : à utiliser pour proposer des actions à une personne
  offre_pro_forme_icope        professionnels formés à ICOPE, avec rapprochement vers l'annuaire RPPS
  icope_professionnel_complet  professionnels ICOPE avec RPPS / ADELI (sans nom ni coordonnées)
  offre_centre_agirc_arrco     les 5 centres de bilan de prévention Agirc-Arrco (levée de doute)

Règle de l'équipe : on ne supprime aucune ligne, on marque (doublon_probable, incomplet, region_normandie,
compte_test_probable...). Les fichiers d'origine restent la référence : `fichier_origine` et `ligne_origine`
permettent de retrouver chaque ligne.

Branchement dans construire_entrepot.py, dans main(), juste après  charger_icope(con, loc)  :
    from charger_prevention import charger_prevention
    charger_prevention(con, loc)
(l'import se fait dans main() et non en haut du fichier, sinon les deux fichiers s'importent l'un l'autre)

Voir les en-têtes détectés dans chaque fichier :  python3 entrepot/charger_prevention.py --inspecter
"""
import argparse
import re
import unicodedata

import pandas as pd

from construire_entrepot import DONNEES, localiser, slug

DEPARTEMENTS = {"seine_maritime": "76", "calvados": "14", "eure": "27", "manche": "50", "orne": "61"}
MOTIFS = {
    "actions": "*ctions[ _]collectives*.xlsx",
    "formes": "liste[ _]pro[ _]form*.xlsx",
    "complet": "complet[ _]bdi_professionnels*.xlsx",
}
# Fichier à remplir à la main : quelles communes couvre chaque UTAS / territoire MDS / secteur (voir plus bas)
REF_TERRITOIRES = DONNEES / "ref_territoire_action.csv"
MODELE_TERRITOIRES = DONNEES / "territoires_a_rattacher.csv"


# --------------------------------------------------------------------------
# Outils de lecture
# --------------------------------------------------------------------------
def snake(texte):
    """'Intitulé de l’action ' -> 'intitule_de_l_action'."""
    if texte is None or (isinstance(texte, float) and pd.isna(texte)):
        return ""
    t = str(texte).replace("’", "'")
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")


def noms_uniques(noms):
    vus, res = {}, []
    for i, n in enumerate(noms):
        base = snake(n) or f"colonne_{i + 1}"
        vus[base] = vus.get(base, 0) + 1
        res.append(base if vus[base] == 1 else f"{base}_{vus[base]}")
    return res


def fichiers(motif):
    return sorted(f for f in DONNEES.glob(motif) if not f.name.startswith("~"))


def tableau(chemin, feuille, mot_entete):
    """Lit une feuille dont la ligne d'en-tête n'est pas la première : on la cherche par un mot-clé.
    Renvoie (tableau, étiquettes d'origine). `ligne_origine` = numéro de ligne dans Excel."""
    brut = pd.read_excel(chemin, sheet_name=feuille, header=None, dtype=str)
    cle = snake(mot_entete)
    idx = next((i for i in range(min(15, len(brut)))
                if any(cle in snake(v) for v in brut.iloc[i] if isinstance(v, str))), None)
    if idx is None:
        raise ValueError(f"{chemin.name} / {feuille} : en-tête « {mot_entete} » introuvable dans les 15 premières lignes")
    noms = noms_uniques(brut.iloc[idx])
    etiquettes = {n: re.sub(r"\s+", " ", str(v)).strip() for n, v in zip(noms, brut.iloc[idx])}
    df = brut.iloc[idx + 1:].copy()
    df.columns = noms
    df["ligne_origine"] = df.index + 1
    df = df.dropna(how="all", subset=[c for c in noms])
    return df, etiquettes


def trouve(df, *prefixes):
    """Première colonne dont le nom commence par un des préfixes (None si absente)."""
    for p in prefixes:
        for c in df.columns:
            if c.startswith(p):
                return c
    return None


def valeur(df, *prefixes):
    c = trouve(df, *prefixes)
    return df[c].str.strip() if c else pd.Series([None] * len(df), index=df.index, dtype="object")


def vers_date(serie):
    return pd.to_datetime(serie, errors="coerce").dt.date


# --------------------------------------------------------------------------
# Classement des actions par thème (règles simples, à valider avec le Gérontopôle)
# --------------------------------------------------------------------------
REGLES = [
    ("aidants", ["aidant"]),
    ("nutrition", ["nutrition", "alimentation", "culinaire", "cuisine", "diet", "manger", "repas"]),
    ("activite_physique", ["physique", "phsyique", "sport", "apa", "equilibre", "chute", "marche", "gym", "danse",
                           "tai chi", "natation", "pilates", "randonn", "yoga", "qi gong", "foot", "marchant", "self defense", "bouger", "corps"]),
    ("memoire", ["memoire", "cognitif", "cognitiv", "cognition", "alzheimer", "neuro", "stimulation"]),
    ("audition", ["audition", "auditive", "surdi"]),
    ("vision", ["vision", "visuel", "ophtalm", "malvoyan"]),
    ("mobilite", ["mobilite", "securite routiere", "transport", "conduite", "conduire", "volant", "permis", "covoiturage", "route"]),
    ("numerique", ["numerique", "informatique", "tablette", "digital"]),
    ("aides_techniques_habitat", ["aides techniques", "aide technique", "habitat", "logement", "ergoth", "ati",
                                  "domotique", "cadre de vie"]),
    ("sante_mentale_bien_etre", ["sante mentale", "bien etre", "estime", "psychosocial", "sophro", "relaxation",
                                 "sommeil", "depression", "stress"]),
    ("lien_social", ["lien social", "isolement", "convivial", "intergeneration", "sortie", "culturel", "loisir",
                     "cafe", "jeux", "chorale", "chant", "musique", "solidarite", "solitude", "entoure", "retrouver", "forum"]),
    ("prevention_sante_generale", ["prevention sante", "sensibilisation", "information", "bucco"]),
]
# Correspondance vers les 9 capacités ICOPE (proposition à valider)
DOMAINE_ICOPE = {"nutrition": "nutrition", "activite_physique": "mobilite", "memoire": "cognition",
                 "audition": "audition", "vision": "vision", "lien_social": "social", "aidants": "aidant",
                 "sante_mentale_bien_etre": "psychologie"}
# Thèmes trop généraux pour trancher : on regarde alors le titre de l'action en premier
GENERIQUE = re.compile(r"\b(autre|prevention sante|sensibilisation|information|aller vers|formation|evaluation|coordination)")


def _motif(terme):
    fin = r"\b" if len(terme) <= 4 else ""
    return re.compile(r"\b" + re.escape(terme) + fin)


_REGLES = [(cat, [_motif(t) for t in termes]) for cat, termes in REGLES]


def _cherche(texte):
    t = " ".join(snake(texte).split("_"))
    for cat, motifs in _REGLES:
        if any(m.search(t) for m in motifs):
            return cat
    return None


def classer(theme_brut, titre):
    """-> (thème, d'où il vient : theme / titre / aucun)."""
    theme_brut = theme_brut if isinstance(theme_brut, str) else ""
    titre = titre if isinstance(titre, str) else ""
    t_theme = _cherche(theme_brut) if theme_brut else None
    t_titre = _cherche(titre) if titre else None
    if theme_brut and GENERIQUE.search(" ".join(snake(theme_brut).split("_"))):
        if t_titre:
            return t_titre, "titre"
        if t_theme:
            return t_theme, "theme"
    elif t_theme:
        return t_theme, "theme"
    if t_titre:
        return t_titre, "titre"
    return "autre", "aucun"


# --------------------------------------------------------------------------
# Un chargeur par département (les 5 fichiers n'ont pas le même format)
# --------------------------------------------------------------------------
COLONNES = ["cle_action", "departement", "fichier_origine", "feuille_origine", "ligne_origine", "porteur",
            "intitule", "theme_brut", "public", "nb_beneficiaires", "type_action", "axe", "financement",
            "montant_annuel", "description", "adresse_porteur", "lieu_texte", "date_debut", "date_fin",
            "territoire_texte", "incomplet"]


def _base(df, dep, chemin, feuille, **champs):
    out = pd.DataFrame(index=df.index)
    out["departement"] = dep
    out["fichier_origine"] = chemin.name
    out["feuille_origine"] = feuille
    out["ligne_origine"] = df["ligne_origine"]
    out["cle_action"] = [f"{dep}|{feuille}|{n}" for n in df["ligne_origine"]]
    for c in COLONNES:
        if c not in out.columns:
            out[c] = champs.get(c)
    for c, v in champs.items():
        out[c] = v
    out["incomplet"] = out["intitule"].isna() | (out["intitule"].astype(str).str.strip() == "")
    return out[COLONNES]


def charger_76(chemin):
    """Seine-Maritime : une feuille « Dossiers », territoires = 5 UTAS (colonnes cochées d'un X)."""
    feuille = "Dossiers"
    df, etiq = tableau(chemin, feuille, "Organisme porteur")
    df = df[df[trouve(df, "titre")].notna()]
    out = _base(df, "76", chemin, feuille,
                porteur=valeur(df, "organisme_porteur"), intitule=valeur(df, "titre"),
                theme_brut=valeur(df, "thematique"), public=valeur(df, "quel_est_le_public"),
                nb_beneficiaires=pd.to_numeric(valeur(df, "nombre_de_benef"), errors="coerce"),
                type_action=valeur(df, "votre_projet"), description=valeur(df, "description"),
                adresse_porteur=valeur(df, "adresse_complete"), territoire_texte=valeur(df, "sur_quelle_s_utas"),
                lieu_texte=valeur(df, "sur_quel_s_territoire"))
    terr = [(f"76|{feuille}|{df.at[i, 'ligne_origine']}", "utas", etiq[c])
            for c in df.columns if c.startswith("utas_") for i in df.index[df[c].notna()]]
    return out, terr


def charger_14(chemin):
    """Calvados : une feuille, 5 territoires de Maison du département (colonnes cochées d'un 1)."""
    feuille = "SUIVI CFPPA"
    df, etiq = tableau(chemin, feuille, "Porteur de projet")
    df = df[df[trouve(df, "intitule")].notna()]
    pas_territoire = {"ligne_origine", trouve(df, "porteur"), trouve(df, "email"), trouve(df, "intitule")}
    cols_terr = [c for c in df.columns if c not in pas_territoire]
    out = _base(df, "14", chemin, feuille, porteur=valeur(df, "porteur"), intitule=valeur(df, "intitule"),
                territoire_texte=df[cols_terr].apply(lambda r: ", ".join(etiq[c] for c in cols_terr if pd.notna(r[c])), axis=1))
    terr = [(f"14|{feuille}|{df.at[i, 'ligne_origine']}", "mds", etiq[c]) for c in cols_terr for i in df.index[df[c].notna()]]
    return out, terr


AXES_EURE = {"1": "Aides techniques", "3": "Coordination des services d'aide à domicile",
             "4": "Proches aidants", "5": "Autres actions collectives de prévention",
             "6": "Lien social (lutte contre l'isolement)"}


def charger_27(chemin):
    """Eure : feuille « Axe 1-3-4-5-6 » (liste des lauréats) + « Extraction mobilité ». « Par EPCI » est une
    vue de la même liste (avec une liste déroulante) : on ne la charge pas pour ne pas doubler les actions."""
    morceaux, terr = [], []
    df, _ = tableau(chemin, "Axe 1-3-4-5-6", "Nom du porteur")
    feuille = "Axe 1-3-4-5-6"
    df = df[df[trouve(df, "nom_du_porteur")].notna()]  # les lignes sans porteur sont des titres d'axe
    morceaux.append((feuille, df))
    mob = pd.read_excel(chemin, sheet_name="Extraction mobilité", header=None, dtype=str)
    mob.columns = ["axe", "nom_du_porteur", "mail_de_la_structure", "nom_du_projet", "financement", "montant_annuel", "epci"]
    mob["ligne_origine"] = mob.index + 1
    morceaux.append(("Extraction mobilité", mob.dropna(how="all", subset=list(mob.columns[:-1]))))
    sorties = []
    for feuille, d in morceaux:
        num = d[trouve(d, "axe")].str.extract(r"(\d)")[0]
        out = _base(d, "27", chemin, feuille, porteur=valeur(d, "nom_du_porteur"), intitule=valeur(d, "nom_du_projet"),
                    axe=d[trouve(d, "axe")].str.extract(r"(Axe\s*\d)")[0], theme_brut=num.map(AXES_EURE),
                    financement=valeur(d, "financement"),
                    montant_annuel=pd.to_numeric(valeur(d, "montant_annuel"), errors="coerce"),
                    territoire_texte=valeur(d, "epci"))
        sorties.append(out)
        for i in d.index[d[trouve(d, "epci")].notna()]:
            for epci in re.split(r",\s*", d.at[i, trouve(d, "epci")]):
                if epci.strip():
                    terr.append((f"27|{feuille}|{d.at[i, 'ligne_origine']}", "epci", epci.strip()))
    return pd.concat(sorties), terr


SECTEURS_MANCHE = {"COUTANCIAS": "COUTANCAIS", "CENTRE": "CENTRE MANCHE"}  # fautes de frappe du fichier


def charger_50(chemin):
    """Manche : une feuille, « SECTEUR » (découpage du département) + « Lieu de réalisation » (EPCI)."""
    feuille = "Feuil1"
    df, _ = tableau(chemin, feuille, "Nom du porteur de projet")
    df = df[df[trouve(df, "intitule")].notna()]
    out = _base(df, "50", chemin, feuille, porteur=valeur(df, "nom_du_porteur"), intitule=valeur(df, "intitule"),
                theme_brut=valeur(df, "thematique"), type_action=valeur(df, "type_d_action"),
                territoire_texte=valeur(df, "secteur"), lieu_texte=valeur(df, "lieu_de_realisation"))
    terr = []
    for i in df.index[df[trouve(df, "secteur")].notna()]:
        # « GTM/VI » est un seul secteur ; « NORD / CENTRE » ou « COUTANCAIS / SAINT LOIS » en sont deux
        brut = re.sub(r"GTM\s*/\s*VI", "GTM-VI", df.at[i, trouve(df, "secteur")], flags=re.I)
        for s in re.split(r"\s*/\s*", brut):
            s = snake(s).replace("_", " ").upper()
            s = SECTEURS_MANCHE.get(s, s)
            cle = f"50|{feuille}|{df.at[i, 'ligne_origine']}"
            terr.append((cle, "departement", "Ensemble du département") if s == "DEPARTEMENT"
                        else (cle, "secteur", "GTM/VI" if s == "GTM VI" else s.title()))
    return out, terr


def charger_61(chemin):
    """Orne : une feuille « Dossiers », lieux en texte libre (communes citées ou « ensemble du département »)."""
    feuille = "Dossiers"
    df, _ = tableau(chemin, feuille, "Entreprise raison sociale")
    df = df[df[trouve(df, "entreprise")].notna() | df[trouve(df, "intitule")].notna()]
    out = _base(df, "61", chemin, feuille, porteur=valeur(df, "entreprise"), intitule=valeur(df, "intitule"),
                theme_brut=valeur(df, "thematique"), type_action=valeur(df, "l_action_se_deroule"),
                nb_beneficiaires=pd.to_numeric(valeur(df, "nombre_de_participants_uniques"), errors="coerce"),
                description=valeur(df, "description_des_effets"), lieu_texte=valeur(df, "adresses_des_lieux"),
                date_debut=vers_date(valeur(df, "date_de_debut")), date_fin=vers_date(valeur(df, "date_de_fin")))
    out["axe"] = valeur(df, "n_dossier")  # numéro de dossier de la plateforme de dépôt
    terr = []
    for i in df.index[df[trouve(df, "adresses_des_lieux")].notna()]:
        txt = df.at[i, trouve(df, "adresses_des_lieux")]
        niveau = "departement" if re.search(r"ensemble du d[ée]partement", txt, re.I) else "adresse"
        terr.append((f"61|{feuille}|{df.at[i, 'ligne_origine']}", niveau, txt.strip()))
    return out, terr


CHARGEURS = {"14": charger_14, "27": charger_27, "50": charger_50, "61": charger_61, "76": charger_76}


# --------------------------------------------------------------------------
# Territoires : à quelles communes correspond chaque action ?
# --------------------------------------------------------------------------
MOTS_EPCI = {"ca", "cc", "cu", "communaute", "agglomeration", "agglo", "communes", "urbaine", "metropole",
             "de", "du", "des", "d", "la", "le", "les", "l"}


def cle_epci(nom):
    return "_".join(t for t in snake(nom).split("_") if t and t not in MOTS_EPCI)


def index_epci(con):
    """{clé du nom d'EPCI: code EPCI}, d'après ref_commune (les colonnes sont détectées)."""
    cols = [c for (c,) in con.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'ref_commune'").fetchall()]
    code = "code_epci" if "code_epci" in cols else None
    nom = next((c for c in ("nom_epci", "epci_nom", "libelle_epci", "lib_epci", "epci") if c in cols), None) \
        or next((c for c in cols if "epci" in c and c != code), None)
    if not code or not nom:
        print("  (ref_commune : colonne du nom de l'intercommunalité introuvable : EPCI non rattachés)")
        return {}
    return {cle_epci(n): c for c, n in con.execute(f"SELECT DISTINCT {code}, {nom} FROM ref_commune WHERE {nom} IS NOT NULL").fetchall()}


def epci_dans_texte(texte, epci):
    """Un nom d'EPCI exact, ou plusieurs cités dans un texte de lieu."""
    cle = cle_epci(texte)
    if cle in epci:
        return [epci[cle]]
    cle_t = "_" + cle + "_"
    return sorted({code for k, code in epci.items() if len(k) >= 6 and "_" + k + "_" in cle_t})


def construire_territoires(con, terr, actions):
    ids = dict(zip(actions["cle_action"], actions["id_action"]))
    dep = dict(zip(actions["cle_action"], actions["departement"]))
    lieu = dict(zip(actions["cle_action"], actions["lieu_texte"]))
    epci = index_epci(con)
    communes = {}
    rows = []

    def ajouter(cle, niveau, territoire, couverture, code_epci=None, code_insee=None, methode=None):
        rows.append((ids[cle], dep[cle], niveau, territoire, couverture, code_epci, code_insee, methode))

    for cle, niveau, territoire in terr:
        if niveau == "departement":
            ajouter(cle, niveau, territoire, "departement", methode="texte")
        elif niveau == "epci":
            codes = epci_dans_texte(territoire, epci)
            for c in codes or [None]:
                ajouter(cle, niveau, territoire, "epci" if c else "a_rattacher", code_epci=c, methode="nom_epci")
        elif niveau == "adresse":  # Orne : on cherche les noms de communes cités dans le texte
            d = dep[cle]
            if d not in communes:
                communes[d] = [(snake(n), c) for c, n in con.execute(
                    "SELECT code_insee, nom FROM ref_commune WHERE departement = ?", [d]).fetchall() if len(snake(n)) >= 4]
            txt = "_" + snake(territoire) + "_"
            trouvees = sorted({c for k, c in communes[d] if "_" + k + "_" in txt})
            for c in trouvees or [None]:
                ajouter(cle, niveau, territoire[:200], "commune" if c else "a_rattacher", code_insee=c, methode="nom_commune_dans_texte")
        else:  # utas, mds, secteur : découpages du département, à rattacher via ref_territoire_action.csv
            ajouter(cle, niveau, territoire, "a_rattacher")
    # Manche : le lieu de réalisation cite l'intercommunalité
    for cle, niveau, _ in terr:
        if niveau == "secteur" and isinstance(lieu.get(cle), str):
            for c in epci_dans_texte(lieu[cle], epci):
                ajouter(cle, "epci", lieu[cle][:200], "epci", code_epci=c, methode="lieu_de_realisation")
    t = pd.DataFrame(rows, columns=["id_action", "departement", "niveau", "territoire", "couverture",
                                    "code_epci", "code_insee", "methode"]).drop_duplicates()
    # UTAS / MDS / secteurs : correspondance fournie par l'équipe (colonnes : departement;niveau;territoire;codes_insee)
    if REF_TERRITOIRES.exists():
        ref = pd.read_csv(REF_TERRITOIRES, sep=";", dtype=str).dropna(subset=["codes_insee"])
        liste = {f"{d}|{n}|{snake(te)}": v.split("|") for d, n, te, v in
                 zip(ref["departement"], ref["niveau"], ref["territoire"], ref["codes_insee"])}
        cle_t = t["departement"] + "|" + t["niveau"] + "|" + t["territoire"].map(snake)
        masque = (t["couverture"] == "a_rattacher") & cle_t.isin(liste)
        sup = [(r.id_action, r.departement, r.niveau, r.territoire, "commune", None, c.strip(), "ref_territoire_action")
               for r, k in zip(t[masque].itertuples(), cle_t[masque]) for c in liste[k]]
        t = pd.concat([t[~masque], pd.DataFrame(sup, columns=t.columns)], ignore_index=True)
    reste = t[t["couverture"] == "a_rattacher"]
    reste = reste[reste["niveau"].isin(["utas", "mds", "secteur"])][["departement", "niveau", "territoire"]].drop_duplicates()
    if len(reste):
        reste.assign(codes_insee="").to_csv(MODELE_TERRITOIRES, sep=";", index=False)
    return t, reste


def charger_actions_collectives(con, loc):
    morceaux, terr = [], []
    for f in fichiers(MOTIFS["actions"]):
        dep = next((code for nom, code in DEPARTEMENTS.items() if nom in slug(f.stem)), None)
        if dep is None:
            print(f"  {f.name} : département non reconnu dans le nom du fichier, ignoré")
            continue
        out, t = CHARGEURS[dep](f)
        morceaux.append(out)
        terr += t
        print(f"  {f.name:48s} {len(out):>5} actions (département {dep})")
    if not morceaux:
        print("  (aucun fichier « Actions collectives » trouvé : tables non créées)")
        return
    a = pd.concat(morceaux, ignore_index=True)
    a["id_action"] = range(1, len(a) + 1)
    cl = [classer(t, i) for t, i in zip(a["theme_brut"], a["intitule"])]
    a["theme"] = [c[0] for c in cl]
    a["theme_source"] = [c[1] for c in cl]
    a["domaine_icope"] = a["theme"].map(DOMAINE_ICOPE)
    cle = a["departement"] + "|" + a["porteur"].map(snake) + "|" + a["intitule"].map(snake)
    a["doublon_probable"] = cle.duplicated() & ~a["incomplet"]
    t, reste = construire_territoires(con, terr, a)
    con.register("actions_df", a)
    con.execute("CREATE TABLE offre_action_collective AS SELECT * FROM actions_df")
    con.unregister("actions_df")
    con.register("terr_df", t)
    con.execute("CREATE TABLE offre_action_territoire AS SELECT * FROM terr_df")
    con.unregister("terr_df")
    # Une ligne par action et par commune couverte (commune citée, commune d'une intercommunalité, département entier)
    con.execute("""
        CREATE VIEW v_action_commune AS
        SELECT DISTINCT id_action, code_insee FROM (
            SELECT t.id_action, t.code_insee FROM offre_action_territoire t WHERE t.code_insee IS NOT NULL
            UNION ALL
            SELECT t.id_action, c.code_insee FROM offre_action_territoire t
                JOIN ref_commune c ON c.code_epci = t.code_epci WHERE t.code_epci IS NOT NULL
            UNION ALL
            SELECT t.id_action, c.code_insee FROM offre_action_territoire t
                JOIN ref_commune c ON c.departement = t.departement WHERE t.couverture = 'departement'
        )""")
    bilan = con.execute("""
        SELECT a.departement, count(*) AS actions,
               count(*) FILTER (WHERE a.id_action IN (SELECT id_action FROM v_action_commune)) AS avec_communes
        FROM offre_action_collective a GROUP BY 1 ORDER BY 1""").fetchall()
    print("\n  Actions rattachées à des communes (le reste attend ref_territoire_action.csv) :")
    for d, n, k in bilan:
        print(f"    département {d} : {k:>4} / {n:<4} actions")
    print("  Thèmes :", a["theme"].value_counts().to_dict())
    epci_non = con.execute("""SELECT DISTINCT territoire FROM offre_action_territoire
                              WHERE niveau = 'epci' AND couverture = 'a_rattacher' ORDER BY 1""").fetchall()
    if epci_non:
        print(f"\n  {len(epci_non)} noms d'intercommunalités non reconnus dans ref_commune (ex. : "
              + " ; ".join(n for (n,) in epci_non[:5]) + ")")
    if len(reste):
        print(f"\n  {len(reste)} territoires (UTAS, MDS, secteurs) à rattacher à des communes : modèle écrit dans\n"
              f"    {MODELE_TERRITOIRES}\n  Remplis la colonne codes_insee (codes séparés par |), enregistre-le sous\n"
              f"    {REF_TERRITOIRES.name} dans le même dossier, puis relance la construction.")


# --------------------------------------------------------------------------
# Professionnels : liste des formés, fichier complet avec RPPS
# --------------------------------------------------------------------------
def prenom1(p):
    return snake(p).split("_")[0] if isinstance(p, str) and snake(p) else ""


def rapprocher_rpps(con, df):
    """Retrouve le numéro RPPS d'un professionnel formé : nom + prénom + code postal, sinon nom + prénom
    + département quand c'est sans ambiguïté."""
    annuaire = con.execute("SELECT id_rpps, nom, prenom, code_postal FROM offre_rpps").fetchall()
    par_cp, par_dep = {}, {}
    for r, n, p, cp in annuaire:
        k = (snake(n), prenom1(p))
        par_cp.setdefault(k + (cp,), set()).add(r)
        par_dep.setdefault(k + ((cp or "")[:2],), set()).add(r)
    ids, quals = [], []
    for nom, pre, cp, ok in zip(df["nom"], df["prenom"], df["code_postal"], df["a_rapprocher"]):
        if not ok:
            ids.append(None); quals.append("non_cherche"); continue
        k = (snake(nom), prenom1(pre))
        c = par_cp.get(k + (cp,), set())
        d = par_dep.get(k + ((cp or "")[:2],), set())
        for cand, label in ((c, "nom_prenom_code_postal"), (d, "nom_prenom_departement")):
            if len(cand) == 1:
                ids.append(next(iter(cand))); quals.append(label); break
            if len(cand) > 1:
                ids.append(None); quals.append("ambigu"); break
        else:
            ids.append(None); quals.append("aucun")
    df["id_rpps_apparie"] = ids
    df["qualite_appariement"] = quals
    return df


def charger_pros_formes(con, loc):
    f = fichiers(MOTIFS["formes"])
    if not f:
        print("  (« liste pro formés icope Normandie » absente : table non créée)")
        return
    feuilles = pd.read_excel(f[-1], sheet_name=None, dtype=str)
    noms = list(feuilles)
    df = feuilles[noms[0]].copy()  # la grande feuille : toute la France ; « Feuil1 » en est un extrait
    df.columns = noms_uniques(df.columns)
    df = df.drop(columns=[c for c in df.columns if c.startswith("j_accepte")])  # consentement à la newsletter
    df["ligne_origine"] = df.index + 2
    df["fichier_origine"] = f[-1].name
    df["feuille_origine"] = noms[0]
    df["region_normandie"] = df["region"].map(slug).eq("normandie")
    df["compte_test_probable"] = df["nom"].isna() & df["prenom"].isna()
    etapes = [c for c in df.columns if c.startswith("etape_2")]
    df["formation_etape2_commencee"] = df[etapes].notna().any(axis=1)
    df["grade"] = pd.to_numeric(df["grade"], errors="coerce")
    for c in ("last_login", "inscription_date"):
        df[c] = vers_date(df[c])
    if len(noms) > 1:  # extrait « Feuil1 » : on garde la trace de qui y figure
        ex = feuilles[noms[1]]
        cles = set(zip(ex["Nom"].map(snake), ex["Code postal"]))
        df["dans_feuil1"] = [(snake(n), c) in cles for n, c in zip(df["nom"], df["code_postal"])]
    df = localiser(df, loc, "code_postal", "ville")
    df["a_rapprocher"] = df["region_normandie"] & ~df["compte_test_probable"]
    df = rapprocher_rpps(con, df)
    df = df.drop(columns=["a_rapprocher", "adresse"])  # adresse de saisie, parfois personnelle : la commune suffit
    con.register("formes_df", df)
    con.execute("CREATE TABLE offre_pro_forme_icope AS SELECT * FROM formes_df")
    con.unregister("formes_df")
    n = df[df["region_normandie"]]
    print(f"  {f[-1].name:48s} {len(df):>5} lignes, dont {len(n)} en Normandie")
    print("  Rapprochement avec l'annuaire RPPS (Normandie, hors comptes sans nom) :",
          n[~n["compte_test_probable"]]["qualite_appariement"].value_counts().to_dict())


def oui_non_bool(df):
    for c in df.columns:
        v = set(df[c].dropna().astype(str).str.lower())
        if v and v <= {"oui", "non", "dm"}:
            df[c] = df[c].str.lower().map({"oui": True, "non": False}).astype("boolean")
    return df


def charger_pros_complet(con, loc):
    f = fichiers(MOTIFS["complet"])
    if not f:
        print("  (« complet bdi_professionnels » absent : table non créée)")
        return
    df = pd.read_excel(f[-1], dtype=str)
    df.columns = noms_uniques(df.columns)
    # Pas de nom, prénom, e-mail ni téléphone : le numéro RPPS suffit pour retrouver la personne dans l'annuaire
    df = df.drop(columns=[c for c in df.columns if c in ("nom", "prenom", "civilite", "email") or c.startswith("telephone")])
    df["ligne_origine"] = df.index + 2
    df["fichier_origine"] = f[-1].name
    for c in ("date_de_creation", "date_de_modification"):
        df[c] = vers_date(df[c])
    df = localiser(df, loc, "code_postal", "ville")
    df["a_rpps"] = df["rpps"].notna()
    df["rpps_dans_annuaire"] = df["rpps"].isin([r for (r,) in con.execute("SELECT DISTINCT id_rpps FROM offre_rpps").fetchall()])
    if con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = 'icope_professionnel'").fetchall()[0][0]:
        deja = {i for (i,) in con.execute("SELECT id_professionnel FROM icope_professionnel").fetchall()}
        df["dans_icope_professionnel"] = df["id"].isin(deja)
    df = oui_non_bool(df)
    con.register("complet_df", df)
    con.execute("CREATE TABLE icope_professionnel_complet AS SELECT * FROM complet_df")
    con.unregister("complet_df")
    print(f"  {f[-1].name:48s} {len(df):>5} lignes : RPPS renseigné pour {int(df['a_rpps'].sum())}, "
          f"trouvé dans l'annuaire pour {int(df['rpps_dans_annuaire'].sum())}, ADELI pour {int(df['adeli'].notna().sum())}")


# Centres de consultation des bilans de prévention Agirc-Arrco en Normandie (adresses transmises par le
# Gérontopôle par mail le 27/10/2026). Ils tiennent lieu de « centre de prévention Agirc-Arrco » dans l'organigramme :
# lieu possible de la levée de doute après un Step 1 anormal.
CENTRES_AGIRC_ARRCO = [
    ("Site de Caen", "site", "14-16 rue des Jacobins", "14000", "CAEN"),
    ("Antenne de Saint-Lô", "antenne", "341 boulevard de Strasbourg", "50000", "SAINT-LO"),
    ("Site de Rouen", "site", "57 avenue de Bretagne, immeuble Le Bretagne, 9e étage", "76000", "ROUEN"),
    ("Antenne d'Évreux", "antenne", "Maison des Solidarités, 11 rue Jean de la Bruyère", "27000", "EVREUX"),
    ("Antenne du Havre", "antenne", "160 rue Massillon, locaux de l'UC IRSA", "76600", "LE HAVRE"),
]


def charger_centres_agirc_arrco(con, loc):
    df = pd.DataFrame(CENTRES_AGIRC_ARRCO, columns=["nom", "type", "adresse", "code_postal", "ville"])
    df["id_centre"] = range(1, len(df) + 1)
    df["role"] = "levee_de_doute"
    df["departement"] = df["code_postal"].str[:2]
    df["source"] = "mail Gérontopôle 27/10/2026"
    df = localiser(df, loc, "code_postal", "ville")
    con.register("agirc_df", df)
    con.execute("CREATE TABLE offre_centre_agirc_arrco AS SELECT * FROM agirc_df")
    con.unregister("agirc_df")
    print(f"  centres Agirc-Arrco : {len(df)} sites, localisation : {df['qualite_localisation'].value_counts().to_dict()}")


def charger_prevention(con, loc):
    print("\nChargement des fichiers de prévention :")
    charger_actions_collectives(con, loc)
    charger_pros_formes(con, loc)
    charger_pros_complet(con, loc)
    charger_centres_agirc_arrco(con, loc)


def inspecter():
    """Affiche, pour chaque fichier, les feuilles et les colonnes détectées (aucune donnée n'est affichée)."""
    entetes = {"76": "Organisme porteur", "14": "Porteur de projet", "27": "Nom du porteur",
               "50": "Nom du porteur de projet", "61": "Entreprise raison sociale"}
    for f in fichiers(MOTIFS["actions"]):
        dep = next((code for nom, code in DEPARTEMENTS.items() if nom in slug(f.stem)), None)
        print(f"\n=== {f.name} (département {dep})")
        for feuille in pd.ExcelFile(f).sheet_names:
            try:
                df, etiq = tableau(f, feuille, entetes.get(dep, "porteur"))
                print(f"  feuille « {feuille} » : {len(df)} lignes ; colonnes : {list(etiq.values())}")
            except ValueError as e:
                print(f"  feuille « {feuille} » : en-tête non détecté ({e})")
    for cle in ("formes", "complet"):
        for f in fichiers(MOTIFS[cle]):
            print(f"\n=== {f.name}")
            for feuille, d in pd.read_excel(f, sheet_name=None, dtype=str, nrows=0).items():
                print(f"  feuille « {feuille} » : {list(d.columns)}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--inspecter", action="store_true", help="affiche les en-têtes de colonnes des fichiers")
    a = p.parse_args()
    if a.inspecter:
        inspecter()
    else:
        p.print_help()