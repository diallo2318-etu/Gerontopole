"""Partie 1 - 3. Les professionnels : qui traite les alertes, où ? Qui teste une seule personne puis décroche ?

Demandé : liste des tâches du 20/10 (répartition par type de professionnel), mail de Marine du 17/10
(par quel pro, où mettre en place des choses) et réunion du 16/10 (diffus ou collectifs ? les pros
« one-shot » : quand, quel type de pro ? hypothèse des kinés payés 18 € par test vers 2022-2023).
Produit : ~/donnees_icope/Partie1_3_Professionnels.xlsx (aucun nom ni identifiant de professionnel)
"""
import pandas as pd

from commun import (DEPARTEMENTS, TESTS_ANALYSES, alertes_analysees, connecter, departement_lisible, ecrire_excel,
                    lire, pct)

NON_RETROUVE = 'Non retrouvé dans la liste des professionnels'


def qui_traite(con):
    """Quels professionnels traitent les alertes, et où ?"""
    actions = lire(con, f"""
        SELECT t.id_traitement, t.id_alerte, t.id_auteur, t.departement AS departement_personne,
               p.profession, p.type_activite, p.type_etablissement, p.departement AS departement_pro,
               p.id_professionnel IS NOT NULL AS retrouve
        FROM icope_traitement t JOIN icope_depistage d USING (id_depistage)
        LEFT JOIN icope_professionnel p ON p.id_professionnel = t.id_auteur
        WHERE {TESTS_ANALYSES}""")
    inscrits = lire(con, "SELECT * FROM icope_professionnel")
    alertes = alertes_analysees(con, "v.id_alerte, v.departement, v.statut_alerte")

    actions['profession'] = actions['profession'].fillna(NON_RETROUVE)
    actions['type_activite'] = actions['type_activite'].fillna('Non retrouvé')
    actions['type_etablissement'] = actions['type_etablissement'].fillna('Non retrouvé')
    actions['departement_pro'] = departement_lisible(actions['departement_pro'])
    actions.loc[~actions['retrouve'], 'departement_pro'] = 'Non retrouvé'
    alertes['departement'] = departement_lisible(alertes['departement'])
    inscrits['departement'] = departement_lisible(inscrits['departement'])

    actifs = actions.groupby('id_auteur')['retrouve'].first()
    perimetre = pd.DataFrame({
        "Indicateur": ["Professionnels ayant fait au moins une action",
                       "dont retrouvés dans la liste des professionnels ICOPE",
                       "dont non retrouvés (pas dans l'export du 09/10/2026)", "Actions au total",
                       "Professionnels inscrits sur ICOPE", "dont autorisés à gérer les alertes"],
        "Valeur": [len(actifs), actifs.sum(), (~actifs).sum(), len(actions), len(inscrits),
                   inscrits['gestion_alerte'].sum()]})

    def repartition(colonne, titre):
        t = (actions.groupby(colonne).agg(pros=('id_auteur', 'nunique'), actions=('id_traitement', 'size'),
                                          alertes=('id_alerte', 'nunique'))
             .sort_values('actions', ascending=False).reset_index())
        t['part'] = pct(t['actions'], len(actions))
        t.columns = [titre, 'Professionnels', 'Actions', 'Alertes traitées', 'Part des actions (%)']
        return t

    # Inscrits autorisés à gérer les alertes, comparés à ceux qui l'ont vraiment fait
    autorises = inscrits[inscrits['gestion_alerte'] == True]
    ids_actifs = set(actions['id_auteur'])
    inscrits_actifs = (autorises.groupby('profession')
                       .agg(autorises=('id_professionnel', 'size'),
                            actifs=('id_professionnel', lambda x: x.isin(ids_actifs).sum()))
                       .sort_values('autorises', ascending=False).reset_index())
    inscrits_actifs['part'] = pct(inscrits_actifs['actifs'], inscrits_actifs['autorises'])
    inscrits_actifs.columns = ['Profession', 'Inscrits autorisés à gérer les alertes',
                               'Ont traité au moins une alerte', 'Part active (%)']

    # Par département : où y a-t-il des pros qui pourraient traiter les alertes mais ne le font pas ?
    par_dep = alertes.groupby('departement').agg(alertes=('id_alerte', 'size'),
                                                 non_traitees=('statut_alerte', lambda x: (x == 'non_traitee').sum()))
    par_dep['pct'] = pct(par_dep['non_traitees'], par_dep['alertes'])
    par_dep['autorises'] = autorises.groupby('departement').size()
    par_dep['actifs'] = actions.drop_duplicates('id_auteur').groupby('departement_pro').size()
    par_dep = par_dep.fillna(0)
    par_dep[['autorises', 'actifs']] = par_dep[['autorises', 'actifs']].astype(int)
    par_dep = par_dep.reset_index()
    par_dep.columns = ['Département', 'Alertes', 'Alertes non traitées', 'Non traitées (%)',
                       'Professionnels autorisés à gérer les alertes', 'Professionnels ayant traité']
    par_dep = par_dep[~par_dep['Département'].isin(['Hors Normandie', 'Non renseigné'])]

    # Le professionnel traite-t-il des personnes de son département ?
    retrouves = actions[actions['retrouve']].copy()
    meme = departement_lisible(retrouves['departement_personne']) == retrouves['departement_pro']
    meme_dep = pd.DataFrame({
        'Indicateur': ["Actions sur une personne du même département que le professionnel",
                       "Actions sur une personne d'un autre département"],
        "Nombre d'actions": [meme.sum(), (~meme).sum()]})
    meme_dep['Pourcentage (%)'] = pct(meme_dep["Nombre d'actions"], len(retrouves))

    return [('Pros_Perimetre', perimetre), ('Pros_Profession', repartition('profession', 'Profession')),
            ('Pros_Activite', repartition('type_activite', "Type d'activité")),
            ('Pros_Lieu_exercice', repartition('type_etablissement', "Lieu d'exercice")),
            ('Pros_Departement_pro', repartition('departement_pro', 'Département du professionnel')),
            ('Pros_Meme_departement', meme_dep), ('Pros_Inscrits_vs_actifs', inscrits_actifs),
            ('Pros_Territoires', par_dep)]


def one_shot(con):
    """Quels professionnels n'ont fait passer le test qu'à une seule personne, et quand ?"""
    tests = lire(con, f"""
        SELECT d.id_depistage, d.participant, d.id_createur, d.date_depistage, d.one_shot_pro, d.departement,
               p.profession, p.date_inscription
        FROM icope_depistage d LEFT JOIN icope_professionnel p ON p.id_professionnel = d.id_createur
        WHERE {TESTS_ANALYSES} AND d.saisie_par = 'professionnel'""")
    tests['profession'] = tests['profession'].fillna(NON_RETROUVE)
    tests['annee'] = pd.to_datetime(tests['date_depistage']).dt.year
    tests['departement'] = tests['departement'].map(DEPARTEMENTS).fillna('Hors Normandie ou non renseigné')

    # Une ligne par professionnel
    pros = tests.groupby('id_createur').agg(
        profession=('profession', 'first'), one_shot=('one_shot_pro', 'max'), tests=('id_depistage', 'size'),
        premier_test=('date_depistage', 'min'), date_inscription=('date_inscription', 'first'),
        departement=('departement', lambda x: x.value_counts().index[0])).reset_index()
    pros['annee_premier_test'] = pd.to_datetime(pros['premier_test']).dt.year
    pros['jours_inscription_test'] = (pd.to_datetime(pros['premier_test'])
                                      - pd.to_datetime(pros['date_inscription'])).dt.days

    perimetre = pd.DataFrame({
        "Indicateur": ["Tests faits par un professionnel", "Professionnels ayant fait au moins un test",
                       "dont « one-shot » (une seule personne testée)", "Part des pros one-shot (%)",
                       "Tests faits par des pros one-shot", "Part des tests pros (%)"],
        "Valeur": [len(tests), len(pros), int(pros['one_shot'].sum()), round(pros['one_shot'].mean() * 100, 1),
                   int(tests['one_shot_pro'].sum()), round(tests['one_shot_pro'].mean() * 100, 1)]})

    def par(colonne, titre):
        t = pros.groupby(colonne).agg(n=('id_createur', 'size'), os=('one_shot', 'sum'),
                                      tests=('tests', 'sum')).reset_index()
        t['part'] = pct(t['os'], t['n'])
        t.columns = [titre, 'Professionnels', 'dont one-shot', 'Tests', 'Part one-shot (%)']
        return t.sort_values('Professionnels', ascending=False)

    par_annee = par('annee_premier_test', 'Année du premier test du pro').sort_values('Année du premier test du pro')
    tests_annee = tests.groupby('annee').agg(n=('id_depistage', 'size'), os=('one_shot_pro', 'sum')).reset_index()
    tests_annee['part'] = pct(tests_annee['os'], tests_annee['n'])
    tests_annee.columns = ['Année du test', 'Tests faits par des pros', 'dont tests de pros one-shot', 'Part one-shot (%)']

    seuls = pros[pros['one_shot']]
    profession_annee = (pd.crosstab(seuls['profession'], seuls['annee_premier_test'], margins=True, margins_name='Total')
                        .sort_values('Total', ascending=False).reset_index()
                        .rename(columns={'profession': 'Profession (pros one-shot)'}))

    # L'hypothèse des kinés : tous leurs tests par année
    kines = (tests[tests['profession'] == 'Masseur-Kinésithérapeute'].groupby('annee')
             .agg(n=('id_depistage', 'size'), os=('one_shot_pro', 'sum'), kines=('id_createur', 'nunique'))
             .reset_index())
    kines.columns = ['Année', 'Tests faits par des kinés', 'dont tests de kinés one-shot', 'Kinés différents']

    # Inscrits puis un seul test : délai entre l'inscription et le test
    delai = seuls['jours_inscription_test'].dropna()
    delai_inscription = pd.DataFrame({
        "Indicateur": ["Pros one-shot avec une date d'inscription", "Test le jour même de l'inscription",
                       "Test dans le mois de l'inscription", "Délai médian (jours)"],
        "Valeur": [len(delai), int((delai <= 0).sum()), int((delai <= 31).sum()),
                   float(delai.median()) if len(delai) else None]})

    return [('OneShot_Perimetre', perimetre), ('OneShot_Par_profession', par('profession', 'Profession')),
            ('OneShot_Par_annee_pro', par_annee), ('OneShot_Par_annee_tests', tests_annee),
            ('OneShot_Profession_x_annee', profession_annee), ('OneShot_Kines_par_annee', kines),
            ('OneShot_Par_departement', par('departement', 'Département (le plus fréquent des personnes testées)')),
            ('OneShot_Delai_inscription', delai_inscription)]


if __name__ == "__main__":
    con = connecter()
    ecrire_excel("Partie1_3_Professionnels.xlsx", "3. Les professionnels", [
        ("Quels professionnels traitent les alertes, et où ?", qui_traite(con)),
        ("Quels professionnels n'ont testé qu'une seule personne, et quand ?", one_shot(con)),
    ])
