"""Partie 1 - 1. Les personnes en alerte : combien d'alertes, chez qui, quel âge selon le territoire,
quels profils types pour le modèle.

Demandé : liste des tâches du 20/10 (domaines, nombre d'anomalies, âge, sexe, 5 profils types,
format d'entrée du modèle) et réunion du 16/10 (âge moyen et écart type, âge selon les territoires).
Produit : ~/donnees_icope/Partie1_1_Personnes_en_alerte.xlsx
"""
import pandas as pd

from commun import (DOMAINES, alertes_analysees, classe_age, connecter, departement_lisible,
                    ecrire_excel, khi2, lire, pct, site_lisible, tests_analyses, TESTS_ANALYSES)


def frequence(con):
    """Combien d'alertes, et dans quels domaines ?"""
    tests = tests_analyses(con)
    alertes = lire(con, f"""SELECT a.id_depistage, a.domaine, a.alerte FROM icope_alerte a
                            JOIN icope_depistage d USING (id_depistage) WHERE {TESTS_ANALYSES}""")
    alertes['domaine'] = alertes['domaine'].map(DOMAINES)

    total = con.sql("SELECT count(*) FROM icope_depistage").fetchone()[0]
    retenus = con.sql("SELECT count(*) FROM icope_depistage WHERE retenu").fetchone()[0]
    perimetre = pd.DataFrame({
        "Indicateur": ["Tests au départ", "Tests après doublons du même jour",
                       "Essais probables retirés (moins de 50 ans)", "Tests analysés", "Personnes analysées"],
        "Valeur": [total, retenus, retenus - len(tests), len(tests), tests['participant'].nunique()]})

    nb_alertes = tests['nb_alertes'].value_counts().sort_index().reset_index()
    nb_alertes.columns = ["Nombre d'alertes", 'Nombre de tests']
    nb_alertes['Pourcentage (%)'] = pct(nb_alertes['Nombre de tests'], len(tests))

    resume = pd.DataFrame({
        "Indicateur": ["Tests avec au moins une alerte", "Pourcentage (%)",
                       "Nombre moyen d'alertes par test", "Nombre médian d'alertes par test"],
        "Valeur": [(tests['nb_alertes'] >= 1).sum(), round((tests['nb_alertes'] >= 1).mean() * 100, 1),
                   round(tests['nb_alertes'].mean(), 2), tests['nb_alertes'].median()]})

    # Le pourcentage se calcule parmi les tests où la question a été posée
    # (audition, social, incontinence et aidant ne sont pas posés à tout le monde).
    domaines = alertes.groupby('domaine').agg(
        alertes=('alerte', lambda x: (x == True).sum()),
        posee=('alerte', lambda x: x.notna().sum()),
        non_posee=('alerte', lambda x: x.isna().sum())).reset_index()
    domaines['pct'] = pct(domaines['alertes'], domaines['posee'])
    domaines = domaines.sort_values('alertes', ascending=False)
    domaines.columns = ['Domaine', "Tests en alerte", 'Question posée', 'Question non posée',
                        'Pourcentage en alerte (%)']

    # Combinaison = liste exacte des domaines en alerte d'un test ; paire = deux domaines au moins en alerte
    en_alerte = alertes[alertes['alerte'] == True]
    combinaisons = en_alerte.sort_values('domaine').groupby('id_depistage')['domaine'].apply(' + '.join)
    top_combinaisons = combinaisons.value_counts().head(15).reset_index()
    top_combinaisons.columns = ['Combinaison', 'Nombre de tests']
    top_combinaisons['Pourcentage des tests en alerte (%)'] = pct(top_combinaisons['Nombre de tests'],
                                                                  len(combinaisons))
    paires = en_alerte.merge(en_alerte, on='id_depistage')
    paires = paires[paires['domaine_x'] < paires['domaine_y']]
    top_paires = (paires.groupby(['domaine_x', 'domaine_y']).size().sort_values(ascending=False)
                  .head(15).reset_index())
    top_paires.columns = ['Domaine 1', 'Domaine 2', 'Nombre de tests']

    return [('Freq_Perimetre', perimetre), ('Freq_Resume', resume), ('Freq_Nb_alertes', nb_alertes),
            ('Freq_Domaines', domaines), ('Freq_Combinaisons', top_combinaisons), ('Freq_Paires', top_paires)]


def profil(con):
    """Qui est en alerte (âge, sexe, modalité, territoire) ?"""
    tests = tests_analyses(con)
    tests['en_alerte'] = tests['nb_alertes'] >= 1
    tests['classe_age'] = classe_age(tests['age'])
    tests['sexe'] = tests['sexe'].map({'F': 'Femme', 'M': 'Homme'}).fillna('Non renseigné')
    tests['modalite'] = tests['modalite'].fillna('Non renseigné')
    tests['type_suivi'] = tests['type_suivi'].map({'initiale': 'Test initial', 'suivi': 'Test de suivi'})
    tests['medecin_traitant'] = tests['a_medecin_traitant'].map({True: 'Oui', False: 'Non'}).fillna('Non renseigné')
    tests['departement'] = departement_lisible(tests['departement'])
    tests['site'] = site_lisible(tests['experimentation'])
    variables = {'classe_age': "Classe d'âge", 'sexe': 'Sexe', 'modalite': 'Modalité du test',
                 'type_suivi': 'Type de test', 'medecin_traitant': 'Médecin traitant',
                 'departement': 'Département', 'site': "Site d'expérimentation"}

    perimetre = pd.DataFrame({
        "Indicateur": ["Tests analysés", "Tests avec au moins une alerte", "Tests sans alerte"],
        "Valeur": [len(tests), tests['en_alerte'].sum(), (~tests['en_alerte']).sum()]})

    age = (tests.groupby('en_alerte')['age'].describe()[['count', 'mean', 'min', '25%', '50%', '75%', 'max']]
           .reset_index())
    age['en_alerte'] = age['en_alerte'].map({True: 'Avec au moins une alerte', False: 'Sans alerte'})
    age.columns = ['Groupe', 'Nombre de tests', 'Âge moyen', 'Âge minimum', '1er quartile', 'Âge médian',
                   '3e quartile', 'Âge maximum']
    age['Âge moyen'] = age['Âge moyen'].round(1)
    entiers = ['Nombre de tests', 'Âge minimum', 'Âge maximum']
    age[entiers] = age[entiers].astype(int)

    # Part des tests en alerte selon chaque caractéristique, et test du khi-deux
    # (sans « Non renseigné » ni « Hors Normandie », trop peu de tests)
    lignes, tests_khi2 = [], []
    for col, nom in variables.items():
        g = tests.groupby(col).agg(n=('en_alerte', 'size'), alerte=('en_alerte', 'sum'),
                                   moyenne=('nb_alertes', 'mean')).reset_index()
        lignes += [{'Caractéristique': nom, 'Valeur': r[col], 'Nombre de tests': r['n'],
                    'Tests en alerte': r['alerte'], 'Pourcentage en alerte (%)': round(r['alerte'] / r['n'] * 100, 1),
                    "Nombre moyen d'alertes": round(r['moyenne'], 2)} for _, r in g.iterrows()]
        tests_khi2.append(khi2(tests[~tests[col].isin(['Non renseigné', 'Hors Normandie'])], col, 'en_alerte', nom))

    # Part en alerte par domaine, selon le sexe et l'âge (cases vides sous 30 tests)
    alertes = lire(con, f"""SELECT a.id_depistage, a.domaine, a.alerte FROM icope_alerte a
                            JOIN icope_depistage d USING (id_depistage) WHERE {TESTS_ANALYSES}""")
    alertes['domaine'] = alertes['domaine'].map(DOMAINES)
    alertes = alertes[alertes['alerte'].notna()].merge(
        tests[['id_depistage', 'sexe', 'classe_age', 'age', 'modalite', 'medecin_traitant', 'hors_cible_moins_60']],
        on='id_depistage')
    alertes['alerte'] = alertes['alerte'].astype(bool)
    par_sexe = alertes[alertes['sexe'] != 'Non renseigné'].pivot_table(
        index='domaine', columns='sexe', values='alerte', aggfunc=['mean', 'size'])
    par_age = alertes.pivot_table(index='domaine', columns='classe_age', values='alerte', aggfunc=['mean', 'size'])
    effectifs = pd.concat([par_sexe['size'], par_age['size']], axis=1).fillna(0).astype(int)
    pourcentages = (pd.concat([par_sexe['mean'], par_age['mean']], axis=1) * 100).where(effectifs >= 30).round(1)

    # Profil des tests en alerte, domaine par domaine
    en_alerte = alertes[alertes['alerte']]
    profil_domaines = en_alerte.groupby('domaine').agg(
        n=('id_depistage', 'size'), age_moyen=('age', 'mean'),
        femmes=('sexe', lambda x: (x == 'Femme').mean() * 100),
        plus_80=('age', lambda x: (x >= 80).mean() * 100),
        pro=('modalite', lambda x: (x == 'par un professionnel').mean() * 100),
        sans_medecin=('medecin_traitant', lambda x: (x == 'Non').mean() * 100),
        moins_60=('hors_cible_moins_60', lambda x: x.mean() * 100)).reset_index()
    profil_domaines = profil_domaines.round(1).sort_values('n', ascending=False)
    profil_domaines.columns = ['Domaine', 'Tests en alerte', 'Âge moyen', 'Femmes (%)', '80 ans et plus (%)',
                               'Test par un professionnel (%)', 'Sans médecin traitant (%)', 'Moins de 60 ans (%)']

    return [('Profil_Perimetre', perimetre), ('Profil_Age', age), ('Profil_Caracteristiques', pd.DataFrame(lignes)),
            ('Profil_Khi2', pd.DataFrame(tests_khi2)),
            ('Profil_Domaines_sexe_age', pourcentages.reset_index().rename(columns={'domaine': 'Domaine'})),
            ('Profil_Domaines_effectifs', effectifs.reset_index().rename(columns={'domaine': 'Domaine'})),
            ('Profil_Domaines', profil_domaines)]


def decrire_age(groupe):
    """Âge d'un groupe de personnes ; vide sous 30 personnes (trop peu pour être fiable)."""
    ligne = {'Personnes': len(groupe)}
    if len(groupe) < 30:
        return ligne
    age = groupe['age']
    return {**ligne, 'Âge moyen': round(age.mean(), 1), 'Écart type': round(age.std(), 1),
            'Âge médian': age.median(),
            'La moitié a entre (1er quartile)': age.quantile(0.25), 'et (3e quartile)': age.quantile(0.75),
            '8 sur 10 ont entre (10e centile)': age.quantile(0.10), 'et (90e centile)': age.quantile(0.90),
            'Moins de 60 ans (%)': round((age < 60).mean() * 100, 1),
            '80 ans et plus (%)': round((age >= 80).mean() * 100, 1)}


def age_territoires(con):
    """Quel âge ont les personnes, selon le territoire ? (une ligne par personne : son premier test)"""
    personnes = lire(con, f"""SELECT * FROM (
        SELECT *, row_number() OVER (PARTITION BY participant ORDER BY date_depistage, numero) AS rang
        FROM icope_depistage d WHERE {TESTS_ANALYSES}) WHERE rang = 1""")
    personnes['departement'] = departement_lisible(personnes['departement'])
    personnes['site'] = site_lisible(personnes['experimentation'])
    personnes['modalite'] = personnes['modalite'].fillna('Non renseigné')

    def par_groupe(colonne, titre):
        tableau = pd.DataFrame([{titre: v, **decrire_age(g)} for v, g in personnes.groupby(colonne)])
        tableau = tableau.sort_values('Personnes', ascending=False)
        return pd.concat([tableau, pd.DataFrame([{titre: 'Ensemble', **decrire_age(personnes)}])], ignore_index=True)

    ensemble = pd.DataFrame([
        {'Groupe': 'Toutes les personnes', **decrire_age(personnes)},
        {'Groupe': 'Personnes en alerte au premier test', **decrire_age(personnes[personnes['nb_alertes'] >= 1])}])
    site_modalite = pd.DataFrame([{"Site d'expérimentation": s, 'Modalité du test': m, **decrire_age(g)}
                                  for (s, m), g in personnes.groupby(['site', 'modalite'])])
    site_modalite = site_modalite.sort_values(["Site d'expérimentation", 'Personnes'], ascending=[True, False])

    return [('Age_Ensemble', ensemble), ('Age_Departement', par_groupe('departement', 'Département')),
            ('Age_Site', par_groupe('site', "Site d'expérimentation")), ('Age_Site_modalite', site_modalite)]


def profils_types(con):
    """5 profils types pour tester le parcours, et format d'entrée du modèle."""
    tests = tests_analyses(con, condition="AND d.nb_alertes >= 1")
    tests['combinaison'] = tests.apply(
        lambda t: ' + '.join(nom for d, nom in DOMAINES.items() if t[f'alerte_{d}'] == True), axis=1)
    # Devenir de chaque test : pris en charge si au moins une de ses alertes l'est
    devenir = alertes_analysees(con, "v.id_depistage, v.issue").groupby('id_depistage').agg(
        prise_en_charge=('issue', lambda x: (~x.str.startswith('0.')).any()),
        orientee=('issue', lambda x: x.str.startswith('1.').any()),
        deja_suivie=('issue', lambda x: x.str.startswith('3.').any())).reset_index()
    tests = tests.merge(devenir, on='id_depistage', how='left')

    def decrire(g):
        return {'Tests': len(g), 'Part des tests en alerte (%)': round(len(g) / len(tests) * 100, 1),
                'Âge médian': g['age'].median(), 'Femmes (%)': round((g['sexe'] == 'F').mean() * 100, 1),
                'Auto-évaluation (%)': round((g['modalite'] == 'auto-évaluation').mean() * 100, 1),
                'Sans médecin traitant (%)': round((g['a_medecin_traitant'] == False).mean() * 100, 1),
                'Département le plus fréquent': g['departement'].mode().iloc[0] if g['departement'].notna().any() else '',
                'Sur un site expérimental (%)': round(g['experimentation'].notna().mean() * 100, 1),
                'Pris en charge (%)': round((g['prise_en_charge'] == True).mean() * 100, 1),
                'Orientés (%)': round((g['orientee'] == True).mean() * 100, 1),
                'Déjà suivis (%)': round((g['deja_suivie'] == True).mean() * 100, 1)}

    top10 = tests['combinaison'].value_counts().head(10).index
    combinaisons = pd.DataFrame([{'Combinaison': c, **decrire(tests[tests['combinaison'] == c])} for c in top10])
    combinaisons['Part cumulée (%)'] = combinaisons['Part des tests en alerte (%)'].cumsum().round(1)

    # Chaque profil pose une question différente au parcours
    t = tests
    definitions = [
        ("1. Vision seule, 60-69 ans, auto-évaluation, hors sites",
         "Le cas le plus fréquent (tâche A) : une alerte simple",
         (t['combinaison'] == 'Vision') & t['age'].between(60, 69) & (t['modalite'] == 'auto-évaluation')
         & t['experimentation'].isna()),
        ("2. Cognition + mobilité, 80 ans et plus, Manche",
         "Le profil type du Step 2 (tâche H) : personne très âgée, plusieurs anomalies",
         t['alerte_cognition'] & t['alerte_mobilite'] & (t['age'] >= 80) & (t['departement'] == '50')),
        ("3. Psychologie, moins de 60 ans",
         "Hors de la cible ICOPE (réunion du 16/10) : que lui propose-t-on ?",
         t['alerte_psychologie'] & (t['age'] < 60)),
        ("4. Nutrition + mobilité, Calvados",
         "Territoire où presque personne ne traite les alertes (tâches C et F)",
         t['alerte_nutrition'] & t['alerte_mobilite'] & (t['departement'] == '14')),
        ("5. Audition + vision, 70-79 ans",
         "Quand l'alerte est vérifiée, la personne est souvent déjà suivie (tâche D)",
         t['alerte_audition'] & t['alerte_vision'] & t['age'].between(70, 79)),
    ]
    profils = pd.DataFrame([{'Profil': nom, 'Pourquoi ce profil': pourquoi, **decrire(t[filtre == True])}
                            for nom, pourquoi, filtre in definitions])

    def renseigne(colonne):
        return round(t[colonne].notna().mean() * 100, 1)

    champs = [
        ('Code postal', 'texte (5 chiffres)', 'ex. 50000', 'icope_depistage.code_postal', renseigne('code_postal')),
        ('Commune (code INSEE)', 'texte (5 caractères)', 'ex. 50502', 'icope_depistage.code_insee', renseigne('code_insee')),
        ('Département', 'texte', '14, 27, 50, 61, 76…', 'icope_depistage.departement', renseigne('departement')),
        ('Site expérimental', 'texte ou vide', 'Centre Manche, Elbeuf, Lisieux, vide', 'icope_depistage.experimentation', 100.0),
        ('Âge', 'nombre entier', '50 à 100 et plus', 'icope_depistage.age', renseigne('age')),
        ('Sexe', 'texte', 'F, M', 'icope_depistage.sexe', renseigne('sexe')),
        ('Modalité du test', 'texte', 'auto-évaluation, avec un aidant, par un professionnel', 'icope_depistage.modalite', renseigne('modalite')),
        ('A un médecin traitant', 'oui / non', 'oui, non, vide', 'icope_depistage.a_medecin_traitant', renseigne('a_medecin_traitant')),
    ] + [(f'Alerte {nom.lower()}', 'oui / non', 'oui, non, vide (question non posée)', f'icope_depistage.alerte_{d}',
          renseigne(f'alerte_{d}')) for d, nom in DOMAINES.items()] + [
        ("Nombre d'alertes", 'nombre entier', '1 à 9', 'icope_depistage.nb_alertes', renseigne('nb_alertes')),
        ('Levée de doute : alerte confirmée', 'oui / non', 'oui, non, vide (pas de levée de doute)', 'v_alerte_issue.alerte_confirmee', None),
        ('Déjà suivi pour ce domaine', 'oui / non', 'oui, non, vide', 'v_alerte_issue.issue (« 3. Pas orientée : déjà prise en charge »)', None),
    ]
    format_entree = pd.DataFrame(champs, columns=['Champ', 'Type', 'Valeurs possibles', 'Colonne ICOPE',
                                                  'Renseigné dans les tests en alerte (%)'])

    # Un exemple d'entrée par profil type : valeurs les plus fréquentes du groupe
    exemples = []
    for nom, _, filtre in definitions:
        g = t[filtre == True]
        exemple = {'Profil': nom, 'Département': g['departement'].mode().iloc[0], 'Âge': int(g['age'].median()),
                   'Sexe': g['sexe'].mode().iloc[0], 'Modalité du test': g['modalite'].mode().iloc[0],
                   'A un médecin traitant': 'oui' if (g['a_medecin_traitant'] == True).mean() >= 0.5 else 'non'}
        for d, nom_d in DOMAINES.items():
            exemple[f'Alerte {nom_d.lower()}'] = 'oui' if (g[f'alerte_{d}'] == True).mean() >= 0.5 else 'non'
        exemples.append(exemple)

    return [('Types_Top10_combinaisons', combinaisons), ('Types_Profils', profils),
            ('Types_Format_entree', format_entree), ('Types_Exemples_entree', pd.DataFrame(exemples))]


if __name__ == "__main__":
    con = connecter()
    ecrire_excel("Partie1_1_Personnes_en_alerte.xlsx", "1. Les personnes en alerte", [
        ("Combien d'alertes, et dans quels domaines ?", frequence(con)),
        ("Qui est en alerte (âge, sexe, modalité, territoire) ?", profil(con)),
        ("Quel âge ont les personnes, selon le territoire ?", age_territoires(con)),
        ("Quels profils types pour tester le parcours, et quel format d'entrée pour le modèle ?", profils_types(con)),
    ])
