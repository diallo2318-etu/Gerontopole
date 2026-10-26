import os
import duckdb
import pandas as pd

# Partie 1 - Tâche G : évolution dans le temps (par mois)
# Demandé : liste des tâches du 20/10 (« nombre d'alertes et de Step 2 par mois ») et
# mail de Marine du 17/10 (« est-ce lié à une période ou est-ce pérenne ? »).

# 1. Ouvrir l'entrepôt (dans le dossier privé des données, jamais dans le dépôt)
dossier = os.path.expanduser(os.environ.get("DONNEES_ICOPE", "~/donnees_icope"))
con = duckdb.connect(os.path.join(dossier, "entrepot_icope.duckdb"), read_only=True)

# 2. Charger les données (mêmes règles que les tâches A à F)
tests = con.sql("""
    SELECT id_depistage, date_depistage, nb_alertes
    FROM icope_depistage WHERE retenu AND NOT test_probable
""").df()

alertes = con.sql("""
    SELECT v.id_alerte, v.date_alerte, v.statut_alerte, v.issue
    FROM v_alerte_issue v JOIN icope_depistage d USING (id_depistage)
    WHERE d.retenu AND NOT d.test_probable
""").df()

actions = con.sql("""
    SELECT t.id_traitement, t.id_auteur, t.date_prise_en_charge AS date_action
    FROM icope_traitement t JOIN icope_depistage d USING (id_depistage)
    WHERE d.retenu AND NOT d.test_probable
""").df()

# Step 2 : toutes les évaluations (32 personnes sur 58 ne sont pas dans l'export étape 1)
step2 = con.sql("SELECT id_evaluation, date_evaluation, experimentation FROM icope_evaluation").df()

# 3. Le mois de chaque événement
tests['mois'] = pd.to_datetime(tests['date_depistage']).dt.to_period('M')
alertes['mois'] = pd.to_datetime(alertes['date_alerte']).dt.to_period('M')
actions['mois'] = pd.to_datetime(actions['date_action']).dt.to_period('M')
step2['mois'] = pd.to_datetime(step2['date_evaluation']).dt.to_period('M')

alertes['prise_en_charge'] = alertes['statut_alerte'] != 'non_traitee'
alertes['orientee'] = alertes['issue'].str.startswith('1.')

# Les 2 professionnels qui font 85 % des actions (tâche D), anonymisés
top = actions['id_auteur'].value_counts().index
noms_pros = {top[0]: 'Professionnel 1', top[1]: 'Professionnel 2'}
actions['qui'] = actions['id_auteur'].map(noms_pros).fillna('Autres professionnels')

# 4. Tableau mois par mois, de janvier 2022 au dernier mois
mois = pd.period_range('2022-01', max(tests['mois'].max(), alertes['mois'].max()), freq='M')
par_mois = pd.DataFrame(index=mois)
par_mois['Tests'] = tests.groupby('mois').size()
par_mois['Alertes'] = alertes.groupby('mois').size()
par_mois["Alertes prises en charge (selon le mois de l'alerte)"] = alertes.groupby('mois')['prise_en_charge'].sum()
par_mois['Alertes orientées vers un professionnel'] = alertes.groupby('mois')['orientee'].sum()
par_mois['Actions faites dans le mois'] = actions.groupby('mois').size()
for qui in ['Professionnel 1', 'Professionnel 2', 'Autres professionnels']:
    par_mois[f'Actions : {qui}'] = actions[actions['qui'] == qui].groupby('mois').size()
par_mois['Step 2'] = step2.groupby('mois').size()
par_mois = par_mois.fillna(0).astype(int)
par_mois['Prises en charge (%)'] = (par_mois["Alertes prises en charge (selon le mois de l'alerte)"]
                                    / par_mois['Alertes'] * 100).round(1)
par_mois = par_mois.reset_index().rename(columns={'index': 'Mois'})
par_mois['Mois'] = par_mois['Mois'].astype(str)

# 5. Même chose par trimestre (plus lisible)
trimestre = par_mois.copy()
trimestre['Trimestre'] = pd.PeriodIndex(trimestre['Mois'], freq='M').asfreq('Q').astype(str)
colonnes_sommes = [c for c in trimestre.columns if c not in ('Mois', 'Trimestre', 'Prises en charge (%)')]
par_trimestre = trimestre.groupby('Trimestre')[colonnes_sommes].sum().reset_index()
par_trimestre['Prises en charge (%)'] = (par_trimestre["Alertes prises en charge (selon le mois de l'alerte)"]
                                         / par_trimestre['Alertes'] * 100).round(1)

# 6. Activité des professionnels : premier et dernier mois d'action, nombre de mois actifs
#    Pour savoir si le traitement des alertes est pérenne ou lié à une période.
activite = actions.groupby('qui').agg(
    actions=('id_traitement', 'size'),
    premier_mois=('mois', 'min'),
    dernier_mois=('mois', 'max'),
    mois_actifs=('mois', 'nunique')
).reset_index()
activite['premier_mois'] = activite['premier_mois'].astype(str)
activite['dernier_mois'] = activite['dernier_mois'].astype(str)
activite.columns = ['Qui', 'Actions', "Premier mois d'action", "Dernier mois d'action", 'Nombre de mois avec au moins une action']

# 7. Step 2 par année et par site
step2['annee'] = pd.to_datetime(step2['date_evaluation']).dt.year
step2['site'] = step2['experimentation'].fillna('Hors sites')
step2_annee = pd.crosstab(step2['annee'], step2['site'], margins=True, margins_name='Total').reset_index()
step2_annee = step2_annee.rename(columns={'annee': 'Année'})

# 8. Sauvegarder (dans le dossier des données)
fichier_sortie = os.path.join(dossier, "Partie1_G_Evolution.xlsx")
with pd.ExcelWriter(fichier_sortie, engine='openpyxl') as writer:
    par_mois.to_excel(writer, sheet_name='1_Par_mois', index=False)
    par_trimestre.to_excel(writer, sheet_name='2_Par_trimestre', index=False)
    activite.to_excel(writer, sheet_name='3_Activite_pros', index=False)
    step2_annee.to_excel(writer, sheet_name='4_Step2_annee_site', index=False)

pd.set_option('display.width', 250)
print("--- PAR TRIMESTRE ---")
print(par_trimestre.to_string(index=False))
print("\n--- ACTIVITÉ DES PROFESSIONNELS ---")
print(activite.to_string(index=False))
print("\n--- STEP 2 PAR ANNÉE ET SITE ---")
print(step2_annee.to_string(index=False))
print(f"\n✅ Fichier '{fichier_sortie}' généré avec succès !")
