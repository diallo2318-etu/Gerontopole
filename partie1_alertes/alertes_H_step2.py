import os
import duckdb
import pandas as pd

# Partie 1 - Tâche H : le Step 2 (évaluation approfondie)
# Demandé par Marine (mail du 17/10 et réunion du 16/10) : où, par qui, en équipe ou non,
# pour toutes les personnes en alerte de la zone ou non, seulement en cas de plusieurs anomalies ou non,
# quel profil de personne âgée passe en Step 2.
# La colonne « centre » contient des noms de professionnels : elle ne sert qu'à compter les équipes,
# qui sont anonymisées (Équipe A, B…). Aucun nom n'est écrit dans le fichier.

# 1. Ouvrir l'entrepôt (dans le dossier privé des données, jamais dans le dépôt)
dossier = os.path.expanduser(os.environ.get("DONNEES_ICOPE", "~/donnees_icope"))
con = duckdb.connect(os.path.join(dossier, "entrepot_icope.duckdb"), read_only=True)

# 2. Charger les Step 2
step2 = con.sql("SELECT * FROM icope_evaluation").df()
step2['site'] = step2['experimentation'].fillna('Hors sites')
step2['annee'] = pd.to_datetime(step2['date_evaluation']).dt.year

# Équipes anonymisées, de la plus active à la moins active
equipes = step2['centre'].value_counts().index
noms_equipes = {e: 'Équipe ' + chr(65 + i) for i, e in enumerate(equipes)}
step2['equipe'] = step2['centre'].map(noms_equipes).fillna('Non renseignée')
step2 = step2.drop(columns=['centre'])

# 3. Le dernier test étape 1 avant chaque Step 2 (quand la personne est dans l'export étape 1)
#    Pour savoir combien d'alertes la personne avait au moment d'aller en Step 2.
tests = con.sql("""
    SELECT participant, date_depistage, nb_alertes, modalite,
           alerte_cognition, alerte_nutrition, alerte_vision, alerte_audition,
           alerte_psychologie, alerte_mobilite, alerte_social, alerte_aidant, alerte_incontinence
    FROM icope_depistage WHERE retenu
""").df()
avant = step2[['id_evaluation', 'participant', 'date_evaluation']].merge(tests, on='participant')
avant = avant[pd.to_datetime(avant['date_depistage']) <= pd.to_datetime(avant['date_evaluation'])]
avant = avant.sort_values('date_depistage').groupby('id_evaluation').tail(1)
step2 = step2.merge(avant.drop(columns=['participant', 'date_evaluation']), on='id_evaluation', how='left')
step2['test_retrouve'] = step2['date_depistage'].notna()

# 4. Périmètre
perimetre = pd.DataFrame({
    "Indicateur": ["Évaluations Step 2", "Personnes", "Évaluations initiales", "Évaluations de suivi",
                   "Évaluations avec un test étape 1 retrouvé avant", "Équipes (lieux d'évaluation) différentes"],
    "Valeur": [len(step2), step2['participant'].nunique(), (step2['type_visite'] == 'initiale').sum(),
               (step2['type_visite'] == 'suivi').sum(), step2['test_retrouve'].sum(),
               step2.loc[step2['equipe'] != 'Non renseignée', 'equipe'].nunique()]
})

# 5. Par qui et comment
def compter(colonne, titre, noms=None):
    serie = step2[colonne].map(noms).fillna(step2[colonne]) if noms else step2[colonne]
    tableau = serie.fillna('Non renseigné').astype(str).value_counts().reset_index()
    tableau.columns = [titre, 'Évaluations']
    tableau['Pourcentage (%)'] = (tableau['Évaluations'] / len(step2) * 100).round(1)
    return tableau

evaluateur = compter('evaluateur', 'Évaluateur', {
    'infirmiere_devaluation_gerontologique': "Infirmière d'évaluation gérontologique",
    'interne': 'Interne', 'autre': 'Autre'})
reperage = compter('reperage_par', 'Repéré par', {
    'medecin_generaliste': 'Médecin généraliste', 'infirmier': 'Infirmier',
    'alerte_bd_icope': 'Alerte ICOPE (base de données)', 'autre_professionnel': 'Autre professionnel',
    'mutuelle-assurance': 'Mutuelle / assurance', 'autre': 'Autre'})
domicile = compter('visite_domicile', 'Visite à domicile', {True: 'Oui', False: 'Non'})
protocole = compter('protocole_fragilite', 'Protocole fragilité', {True: 'Oui', False: 'Non'})

# 6. Équipes : où, combien, sur quelle période (en équipe ou non ? pérenne ?)
par_equipe = step2.groupby('equipe').agg(
    site=('site', lambda x: ', '.join(sorted(x.unique()))),
    evaluations=('id_evaluation', 'size'),
    premiere=('date_evaluation', 'min'),
    derniere=('date_evaluation', 'max')
).sort_values('evaluations', ascending=False).reset_index()
par_equipe['premiere'] = pd.to_datetime(par_equipe['premiere']).dt.strftime('%m/%Y')
par_equipe['derniere'] = pd.to_datetime(par_equipe['derniere']).dt.strftime('%m/%Y')
par_equipe.columns = ['Équipe', 'Site', 'Évaluations', 'Première', 'Dernière']

# 7. Pour toutes les personnes en alerte de la zone ? Step 2 comparés aux alertes de chaque site
alertes_site = con.sql("""
    SELECT coalesce(v.experimentation, 'Hors sites') AS site, count(*) AS alertes,
           count(*) FILTER (WHERE v.modalite_test = 'par un professionnel') AS alertes_test_pro
    FROM v_alerte_issue v JOIN icope_depistage d USING (id_depistage)
    WHERE d.retenu AND NOT d.test_probable GROUP BY 1
""").df()
couverture = step2.groupby('site').agg(step2=('id_evaluation', 'size'),
                                       personnes=('participant', 'nunique')).reset_index()
couverture = alertes_site.merge(couverture, on='site', how='left').fillna(0)
couverture[['step2', 'personnes']] = couverture[['step2', 'personnes']].astype(int)
couverture['Step 2 pour 100 alertes'] = (couverture['step2'] / couverture['alertes'] * 100).round(1)
couverture.columns = ['Site', 'Alertes (2020-2026)', 'dont tests faits par un professionnel',
                      'Step 2', 'Personnes en Step 2', 'Step 2 pour 100 alertes']

# 8. Seulement en cas de plusieurs anomalies ? (évaluations avec un test retrouvé)
avec_test = step2[step2['test_retrouve']]
tests_alerte = con.sql("""
    SELECT nb_alertes FROM icope_depistage WHERE retenu AND NOT test_probable AND nb_alertes >= 1
""").df()
nb_anomalies = avec_test['nb_alertes'].astype(int).value_counts().sort_index().reset_index()
nb_anomalies.columns = ["Nombre d'alertes au dernier test avant le Step 2", 'Évaluations']
comparaison_anomalies = pd.DataFrame({
    'Groupe': ['Personnes en Step 2 (dernier test avant)', 'Tous les tests en alerte (tâche A)'],
    "Nombre moyen d'alertes": [round(avec_test['nb_alertes'].mean(), 2),
                               round(tests_alerte['nb_alertes'].mean(), 2)],
    "Avec 3 alertes ou plus (%)": [round((avec_test['nb_alertes'] >= 3).mean() * 100, 1),
                                   round((tests_alerte['nb_alertes'] >= 3).mean() * 100, 1)]
})

# 9. Profil des personnes en Step 2, comparé aux personnes en alerte
en_alerte = con.sql("""
    SELECT age, sexe FROM icope_depistage WHERE retenu AND NOT test_probable AND nb_alertes >= 1
""").df()
def profil(df, nom):
    return {
        'Groupe': nom,
        'Nombre': len(df),
        'Âge moyen': round(df['age'].mean(), 1),
        'Âge médian': df['age'].median(),
        '1er quartile': df['age'].quantile(0.25),
        '3e quartile': df['age'].quantile(0.75),
        '80 ans et plus (%)': round((df['age'] >= 80).mean() * 100, 1),
        'Femmes (%)': round((df['sexe'] == 'F').mean() * 100, 1)
    }
profils = pd.DataFrame([profil(step2, 'Évaluations Step 2'), profil(en_alerte, 'Tests en alerte (tâche B)')])

# 10. Sauvegarder (dans le dossier des données)
fichier_sortie = os.path.join(dossier, "Partie1_H_Step2.xlsx")
with pd.ExcelWriter(fichier_sortie, engine='openpyxl') as writer:
    perimetre.to_excel(writer, sheet_name='1_Perimetre', index=False)
    evaluateur.to_excel(writer, sheet_name='2_Evaluateur', index=False)
    reperage.to_excel(writer, sheet_name='3_Repere_par', index=False)
    domicile.to_excel(writer, sheet_name='4_Domicile', index=False)
    protocole.to_excel(writer, sheet_name='5_Protocole', index=False)
    par_equipe.to_excel(writer, sheet_name='6_Equipes', index=False)
    couverture.to_excel(writer, sheet_name='7_Couverture_sites', index=False)
    nb_anomalies.to_excel(writer, sheet_name='8_Nb_anomalies', index=False)
    comparaison_anomalies.to_excel(writer, sheet_name='9_Anomalies_comparees', index=False)
    profils.to_excel(writer, sheet_name='10_Profil', index=False)

for titre, tableau in [('PÉRIMÈTRE', perimetre), ('ÉVALUATEUR', evaluateur), ('REPÉRÉ PAR', reperage),
                       ('DOMICILE', domicile), ('PROTOCOLE', protocole), ('ÉQUIPES', par_equipe),
                       ('COUVERTURE', couverture), ("NOMBRE D'ANOMALIES", nb_anomalies),
                       ('ANOMALIES COMPARÉES', comparaison_anomalies), ('PROFIL', profils)]:
    print(f"\n--- {titre} ---")
    print(tableau.to_string(index=False))
print(f"\n✅ Fichier '{fichier_sortie}' généré avec succès !")
