"""Outils communs aux scripts de la partie 1 (alertes et profils des personnes).

Tout ce qui se répétait dans chaque script est ici, écrit une seule fois :
ouvrir l'entrepôt, choisir les tests analysés, rendre les valeurs lisibles, écrire le fichier Excel.
"""
import os

import duckdb
import pandas as pd
from scipy.stats import chi2_contingency

# Dossier privé des données (jamais dans le dépôt) ; une autre personne peut donner le sien avec DONNEES_ICOPE
DOSSIER = os.path.expanduser(os.environ.get("DONNEES_ICOPE", "~/donnees_icope"))

# Règles de la partie 1 (décidées avec Marine) : un test par personne et par jour (le dernier),
# sans les essais probables (moins de 50 ans). Les moins de 60 ans sont gardés.
# Seulement les tests faits avant le dernier export des alertes (couvert_par_alertes), pour que
# tests et alertes s'arrêtent à la même date.
TESTS_ANALYSES = "d.retenu AND NOT d.test_probable AND d.couvert_par_alertes"

DOMAINES = {
    'cognition': 'Cognition', 'nutrition': 'Nutrition', 'vision': 'Vision',
    'audition': 'Audition', 'psychologie': 'Psychologie', 'mobilite': 'Mobilité',
    'social': 'Social', 'aidant': 'Aidant', 'incontinence': 'Incontinence'
}
DEPARTEMENTS = {'14': '14 Calvados', '27': '27 Eure', '50': '50 Manche',
                '61': '61 Orne', '76': '76 Seine-Maritime'}
CLASSES_AGE = {'bins': [49, 59, 69, 79, 89, 120],
               'labels': ['50-59 ans', '60-69 ans', '70-79 ans', '80-89 ans', '90 ans et plus']}

pd.set_option('display.width', 250)
pd.set_option('display.max_columns', 30)


# --------------------------------------------------------------------------
# Lire l'entrepôt
# --------------------------------------------------------------------------
def connecter():
    """Ouvre l'entrepôt en lecture seule : les scripts ne peuvent rien y changer."""
    return duckdb.connect(os.path.join(DOSSIER, "entrepot_icope.duckdb"), read_only=True)


def lire(con, requete):
    """Exécute une requête SQL et renvoie un tableau pandas.

    Les colonnes oui / non sont rendues comme avec DuckDB 1.0 (vrai, faux ou None) : les versions récentes
    donnent des cases vides « NA » qui font planter `if x == True` et changent le calcul des moyennes."""
    df = con.execute(requete).df()
    for col in df.columns:
        if isinstance(df[col].dtype, pd.BooleanDtype):
            df[col] = df[col].astype(object).where(df[col].notna(), None)
    return df


def tests_analyses(con, colonnes="d.*", condition=""):
    """Les tests analysés (une ligne par test)."""
    return lire(con, f"SELECT {colonnes} FROM icope_depistage d WHERE {TESTS_ANALYSES} {condition}")


def alertes_analysees(con, colonnes="v.*"):
    """Les alertes analysées (une ligne par alerte, vue v_alerte_issue), avec leur test."""
    return lire(con, f"""SELECT {colonnes} FROM v_alerte_issue v JOIN icope_depistage d USING (id_depistage)
                         WHERE {TESTS_ANALYSES}""")


def actions_analysees(con, colonnes="t.*"):
    """Les actions des professionnels sur les alertes analysées (une ligne par action)."""
    return lire(con, f"""SELECT {colonnes} FROM icope_traitement t JOIN icope_depistage d USING (id_depistage)
                         WHERE {TESTS_ANALYSES}""")


# --------------------------------------------------------------------------
# Rendre les valeurs lisibles
# --------------------------------------------------------------------------
def departement_lisible(serie):
    """'50' -> '50 Manche' ; autre code -> 'Hors Normandie' ; vide -> 'Non renseigné'."""
    return serie.map(DEPARTEMENTS).fillna(serie.notna().map({True: 'Hors Normandie', False: 'Non renseigné'}))


def site_lisible(serie):
    """Site d'expérimentation, ou 'Hors sites'."""
    return serie.fillna('Hors sites')


def classe_age(serie):
    return pd.cut(serie, **CLASSES_AGE).astype(str)


def pct(partie, total):
    """Pourcentage arrondi à 0,1 (marche aussi sur des colonnes)."""
    return (partie / total * 100).round(1)


def khi2(df, colonne, cible, nom):
    """Test du khi-deux : la part de « cible » est-elle différente selon « colonne » ?"""
    statistique, p, ddl, _ = chi2_contingency(pd.crosstab(df[colonne], df[cible]))
    return {'Caractéristique': nom, 'Khi-deux': round(statistique, 2), 'Degrés de liberté': ddl,
            'p-valeur': round(p, 4), 'Différence significative (p < 0,05)': 'OUI' if p < 0.05 else 'NON'}


# --------------------------------------------------------------------------
# Écrire les résultats
# --------------------------------------------------------------------------
def ecrire_excel(nom_fichier, titre, parties):
    """Écrit un fichier Excel dans le dossier privé.

    parties : liste de (question, [(onglet, tableau), ...]).
    Le premier onglet « Sommaire » liste chaque onglet avec la question à laquelle il répond.
    Un onglet peut recevoir plusieurs tableaux : on passe alors une liste de tableaux, écrits l'un sous l'autre.
    """
    sommaire = pd.DataFrame([{'Onglet': onglet, 'Question': question}
                             for question, onglets in parties for onglet, _ in onglets])
    chemin = os.path.join(DOSSIER, nom_fichier)
    with pd.ExcelWriter(chemin, engine='openpyxl') as writer:
        pd.DataFrame({titre: []}).to_excel(writer, sheet_name='Sommaire', index=False)
        sommaire.to_excel(writer, sheet_name='Sommaire', index=False, startrow=2)
        for question, onglets in parties:
            print(f"\n===== {question} =====")
            for onglet, tableaux in onglets:
                ligne = 0
                for tableau in (tableaux if isinstance(tableaux, list) else [tableaux]):
                    tableau.to_excel(writer, sheet_name=onglet, index=False, startrow=ligne)
                    ligne += len(tableau) + 2
                    print(f"\n--- {onglet} ---\n{tableau.to_string(index=False)}")
    print(f"\n Fichier écrit : {chemin}")
