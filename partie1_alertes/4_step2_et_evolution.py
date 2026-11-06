"""Partie 1 - 4. Le Step 2 et l'évolution dans le temps : qui va jusqu'au Step 2, où, par qui ?
Comment les tests, les alertes et leur traitement évoluent-ils mois par mois ?

Demandé : liste des tâches du 20/10 (alertes et Step 2 par mois), mail de Marine du 17/10 (Step 2 : où,
par qui, en équipe, pour qui ; « lié à une période ou pérenne ? ») et réunion du 16/10.
Produit : ~/donnees_icope/Partie1_4_Step2_et_evolution.xlsx (équipes et pros anonymisés)
"""
import pandas as pd

from commun import (DOMAINES, TESTS_ANALYSES, actions_analysees, alertes_analysees, connecter, ecrire_excel, lire,
                    pct, site_lisible, tests_analyses)


def step2(con):
    """Qui va jusqu'au Step 2, où, par qui, et pour quel profil ?"""
    evaluations = lire(con, "SELECT * FROM icope_evaluation")
    evaluations['site'] = site_lisible(evaluations['experimentation'])
    # Équipes anonymisées, de la plus active à la moins active (la colonne « centre » contient des noms)
    equipes = {e: 'Équipe ' + chr(65 + i) for i, e in enumerate(evaluations['centre'].value_counts().index)}
    evaluations['equipe'] = evaluations['centre'].map(equipes).fillna('Non renseignée')
    evaluations = evaluations.drop(columns=['centre'])

    # Le dernier test étape 1 avant chaque Step 2 (quand la personne est dans l'export étape 1)
    tests = lire(con, f"""SELECT participant, date_depistage, nb_alertes, modalite,
                                 {', '.join('alerte_' + d for d in DOMAINES)}
                          FROM icope_depistage WHERE retenu""")
    avant = evaluations[['id_evaluation', 'participant', 'date_evaluation']].merge(tests, on='participant')
    avant = avant[pd.to_datetime(avant['date_depistage']) <= pd.to_datetime(avant['date_evaluation'])]
    avant = avant.sort_values('date_depistage').groupby('id_evaluation').tail(1)
    evaluations = evaluations.merge(avant.drop(columns=['participant', 'date_evaluation']), on='id_evaluation',
                                    how='left')
    evaluations['test_retrouve'] = evaluations['date_depistage'].notna()

    perimetre = pd.DataFrame({
        "Indicateur": ["Évaluations Step 2", "Personnes", "Évaluations initiales", "Évaluations de suivi",
                       "Évaluations avec un test étape 1 retrouvé avant", "Équipes (lieux d'évaluation) différentes"],
        "Valeur": [len(evaluations), evaluations['participant'].nunique(),
                   (evaluations['type_visite'] == 'initiale').sum(), (evaluations['type_visite'] == 'suivi').sum(),
                   evaluations['test_retrouve'].sum(),
                   evaluations.loc[evaluations['equipe'] != 'Non renseignée', 'equipe'].nunique()]})

    def compter(colonne, titre, noms):
        serie = evaluations[colonne].map(noms).fillna(evaluations[colonne])
        t = serie.fillna('Non renseigné').astype(str).value_counts().reset_index()
        t.columns = [titre, 'Évaluations']
        t['Pourcentage (%)'] = pct(t['Évaluations'], len(evaluations))
        return t

    oui_non = {True: 'Oui', False: 'Non'}
    evaluateur = compter('evaluateur', 'Évaluateur', {
        'infirmiere_devaluation_gerontologique': "Infirmière d'évaluation gérontologique",
        'interne': 'Interne', 'autre': 'Autre'})
    reperage = compter('reperage_par', 'Repéré par', {
        'medecin_generaliste': 'Médecin généraliste', 'infirmier': 'Infirmier',
        'alerte_bd_icope': 'Alerte ICOPE (base de données)', 'autre_professionnel': 'Autre professionnel',
        'mutuelle-assurance': 'Mutuelle / assurance', 'autre': 'Autre'})

    # Équipes : où, combien, sur quelle période (en équipe ou non ? pérenne ?)
    par_equipe = evaluations.groupby('equipe').agg(
        site=('site', lambda x: ', '.join(sorted(x.unique()))), n=('id_evaluation', 'size'),
        premiere=('date_evaluation', 'min'), derniere=('date_evaluation', 'max')
    ).sort_values('n', ascending=False).reset_index()
    for c in ['premiere', 'derniere']:
        par_equipe[c] = pd.to_datetime(par_equipe[c]).dt.strftime('%m/%Y')
    par_equipe.columns = ['Équipe', 'Site', 'Évaluations', 'Première', 'Dernière']

    # Pour toutes les personnes en alerte de la zone ? Step 2 comparés aux alertes de chaque site
    alertes_site = lire(con, f"""
        SELECT coalesce(v.experimentation, 'Hors sites') AS site, count(*) AS alertes,
               count(*) FILTER (WHERE v.modalite_test = 'par un professionnel') AS alertes_test_pro
        FROM v_alerte_issue v JOIN icope_depistage d USING (id_depistage)
        WHERE {TESTS_ANALYSES} GROUP BY 1 ORDER BY alertes DESC""")
    couverture = evaluations.groupby('site').agg(step2=('id_evaluation', 'size'),
                                                 personnes=('participant', 'nunique')).reset_index()
    couverture = alertes_site.merge(couverture, on='site', how='left').fillna(0)
    couverture[['step2', 'personnes']] = couverture[['step2', 'personnes']].astype(int)
    couverture['pour_100'] = pct(couverture['step2'], couverture['alertes'])
    couverture.columns = ['Site', 'Alertes (2020-2026)', 'dont tests faits par un professionnel',
                          'Step 2', 'Personnes en Step 2', 'Step 2 pour 100 alertes']

    # Seulement en cas de plusieurs anomalies ?
    avec_test = evaluations[evaluations['test_retrouve']]
    en_alerte = tests_analyses(con, "d.age, d.sexe, d.nb_alertes", "AND d.nb_alertes >= 1")
    nb_anomalies = avec_test['nb_alertes'].astype(int).value_counts().sort_index().reset_index()
    nb_anomalies.columns = ["Nombre d'alertes au dernier test avant le Step 2", 'Évaluations']
    anomalies = pd.DataFrame({
        'Groupe': ['Personnes en Step 2 (dernier test avant)', 'Tous les tests en alerte (tâche A)'],
        "Nombre moyen d'alertes": [round(g['nb_alertes'].mean(), 2) for g in (avec_test, en_alerte)],
        "Avec 3 alertes ou plus (%)": [round((g['nb_alertes'] >= 3).mean() * 100, 1) for g in (avec_test, en_alerte)]})

    def profil(df, nom):
        return {'Groupe': nom, 'Nombre': len(df), 'Âge moyen': round(df['age'].mean(), 1),
                'Âge médian': df['age'].median(), '1er quartile': df['age'].quantile(0.25),
                '3e quartile': df['age'].quantile(0.75), '80 ans et plus (%)': round((df['age'] >= 80).mean() * 100, 1),
                'Femmes (%)': round((df['sexe'] == 'F').mean() * 100, 1)}

    return [('Step2_Perimetre', perimetre), ('Step2_Evaluateur', evaluateur), ('Step2_Repere_par', reperage),
            ('Step2_Domicile', compter('visite_domicile', 'Visite à domicile', oui_non)),
            ('Step2_Protocole', compter('protocole_fragilite', 'Protocole fragilité', oui_non)),
            ('Step2_Equipes', par_equipe), ('Step2_Couverture_sites', couverture),
            ('Step2_Nb_anomalies', nb_anomalies), ('Step2_Anomalies_comparees', anomalies),
            ('Step2_Profil', pd.DataFrame([profil(evaluations, 'Évaluations Step 2'),
                                           profil(en_alerte, 'Tests en alerte (tâche B)')]))]


def evolution(con):
    """Comment les tests, les alertes, les actions et les Step 2 évoluent-ils, mois par mois ?"""
    tests = tests_analyses(con, "d.id_depistage, d.date_depistage, d.nb_alertes")
    alertes = alertes_analysees(con, "v.id_alerte, v.date_alerte, v.statut_alerte, v.issue")
    actions = actions_analysees(con, "t.id_traitement, t.id_auteur, t.date_prise_en_charge AS date_action")
    # Step 2 : toutes les évaluations (32 personnes sur 58 ne sont pas dans l'export étape 1)
    evaluations = lire(con, "SELECT id_evaluation, date_evaluation, experimentation FROM icope_evaluation")

    for df, date in [(tests, 'date_depistage'), (alertes, 'date_alerte'), (actions, 'date_action'),
                     (evaluations, 'date_evaluation')]:
        df['mois'] = pd.to_datetime(df[date]).dt.to_period('M')
    alertes['prise_en_charge'] = alertes['statut_alerte'] != 'non_traitee'
    alertes['orientee'] = alertes['issue'].str.startswith('1.')

    # Les 2 professionnels qui font 85 % des actions, anonymisés
    top = actions['id_auteur'].value_counts().index
    actions['qui'] = actions['id_auteur'].map({top[0]: 'Professionnel 1', top[1]: 'Professionnel 2'}).fillna(
        'Autres professionnels')

    prises = "Alertes prises en charge (selon le mois de l'alerte)"
    par_mois = pd.DataFrame(index=pd.period_range('2022-01', max(tests['mois'].max(), alertes['mois'].max()), freq='M'))
    par_mois['Tests'] = tests.groupby('mois').size()
    par_mois['Alertes'] = alertes.groupby('mois').size()
    par_mois[prises] = alertes.groupby('mois')['prise_en_charge'].sum()
    par_mois['Alertes orientées vers un professionnel'] = alertes.groupby('mois')['orientee'].sum()
    par_mois['Actions faites dans le mois'] = actions.groupby('mois').size()
    for qui in ['Professionnel 1', 'Professionnel 2', 'Autres professionnels']:
        par_mois[f'Actions : {qui}'] = actions[actions['qui'] == qui].groupby('mois').size()
    par_mois['Step 2'] = evaluations.groupby('mois').size()
    par_mois = par_mois.fillna(0).astype(int)
    par_mois['Prises en charge (%)'] = pct(par_mois[prises], par_mois['Alertes'])
    par_mois = par_mois.reset_index().rename(columns={'index': 'Mois'})
    par_mois['Mois'] = par_mois['Mois'].astype(str)

    # Même chose par trimestre (plus lisible)
    trimestre = par_mois.assign(Trimestre=pd.PeriodIndex(par_mois['Mois'], freq='M').asfreq('Q').astype(str))
    sommes = [c for c in par_mois.columns if c not in ('Mois', 'Prises en charge (%)')]
    par_trimestre = trimestre.groupby('Trimestre')[sommes].sum().reset_index()
    par_trimestre['Prises en charge (%)'] = pct(par_trimestre[prises], par_trimestre['Alertes'])

    # Activité des professionnels : le traitement des alertes est-il pérenne ou lié à une période ?
    activite = actions.groupby('qui').agg(n=('id_traitement', 'size'), premier=('mois', 'min'),
                                          dernier=('mois', 'max'), mois_actifs=('mois', 'nunique')).reset_index()
    activite[['premier', 'dernier']] = activite[['premier', 'dernier']].astype(str)
    activite.columns = ['Qui', 'Actions', "Premier mois d'action", "Dernier mois d'action",
                        'Nombre de mois avec au moins une action']

    evaluations['annee'] = pd.to_datetime(evaluations['date_evaluation']).dt.year
    step2_annee = (pd.crosstab(evaluations['annee'], site_lisible(evaluations['experimentation']),
                               margins=True, margins_name='Total').reset_index().rename(columns={'annee': 'Année'}))
    step2_annee.columns.name = None

    return [('Evol_Par_mois', par_mois), ('Evol_Par_trimestre', par_trimestre), ('Evol_Activite_pros', activite),
            ('Evol_Step2_annee_site', step2_annee)]


if __name__ == "__main__":
    con = connecter()
    ecrire_excel("Partie1_4_Step2_et_evolution.xlsx", "4. Le Step 2 et l'évolution dans le temps", [
        ("Qui va jusqu'au Step 2, où, par qui, et pour quel profil ?", step2(con)),
        ("Comment les tests, les alertes, les actions et les Step 2 évoluent-ils, mois par mois ?", evolution(con)),
    ])
