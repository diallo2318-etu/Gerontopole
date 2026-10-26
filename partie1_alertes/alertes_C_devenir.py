import os
import duckdb
import pandas as pd
from scipy.stats import chi2_contingency

# Partie 1 - Tâche C : ce que deviennent les alertes

# 1. Ouvrir l'entrepôt (dans le dossier privé des données, jamais dans le dépôt)
dossier = os.path.expanduser(os.environ.get("DONNEES_ICOPE", "~/donnees_icope"))
con = duckdb.connect(os.path.join(dossier, "entrepot_icope.duckdb"), read_only=True)

# 2. Charger les alertes avec le test qui les a déclenchées
#    Une alerte = un test en alerte (tous domaines confondus).
#    v_alerte_issue donne pour chaque alerte son statut, ses actions et son issue.
toutes = con.sql("""
    SELECT v.*, d.retenu, d.test_probable, d.modalite,
           d.alerte_cognition, d.alerte_nutrition, d.alerte_vision, d.alerte_audition,
           d.alerte_psychologie, d.alerte_mobilite, d.alerte_social, d.alerte_aidant,
           d.alerte_incontinence
    FROM v_alerte_issue v
    LEFT JOIN icope_depistage d USING (id_depistage)
""").df()

# 3. Choisir les alertes analysées (mêmes règles que les tâches A et B)
sans_test = toutes['retenu'].isna()
doublons = toutes['retenu'] == False
probables = (toutes['retenu'] == True) & (toutes['test_probable'] == True)
alertes = toutes[(toutes['retenu'] == True) & (toutes['test_probable'] == False)].copy()

perimetre = pd.DataFrame({
    "Indicateur": ["Alertes au départ",
                   "Alertes sans test dans l'export étape 1 (surtout créées après le 08/10/2026)",
                   "Alertes sur un test en doublon le même jour",
                   "Alertes sur un essai probable (moins de 50 ans)",
                   "Alertes analysées",
                   "Personnes concernées"],
    "Valeur": [len(toutes), sans_test.sum(), doublons.sum(), probables.sum(),
               len(alertes), alertes['participant'].nunique()]
})

# 4. Variables lisibles
alertes['prise_en_charge'] = alertes['statut_alerte'] != 'non_traitee'
alertes['orientee'] = alertes['issue'].str.startswith('1.')
alertes['annee'] = pd.to_datetime(alertes['date_alerte']).dt.year
alertes['classe_age'] = pd.cut(alertes['age'], bins=[49, 59, 69, 79, 89, 120],
                               labels=['50-59 ans', '60-69 ans', '70-79 ans', '80-89 ans',
                                       '90 ans et plus']).astype(str)
alertes['sexe'] = alertes['sexe'].map({'F': 'Femme', 'M': 'Homme'}).fillna('Non renseigné')
alertes['modalite'] = alertes['modalite'].fillna('Non renseigné')
noms_departements = {'14': '14 Calvados', '27': '27 Eure', '50': '50 Manche',
                     '61': '61 Orne', '76': '76 Seine-Maritime'}
alertes['departement'] = alertes['departement'].map(noms_departements).fillna(
    alertes['departement'].notna().map({True: 'Hors Normandie', False: 'Non renseigné'}))
alertes['site'] = alertes['experimentation'].fillna('Hors sites')

# 5. Statut des alertes
noms_statuts = {'non_traitee': 'Non traitée', 'en_cours': 'En cours', 'traitee': 'Traitée'}
statut = alertes['statut_alerte'].map(noms_statuts).value_counts().reset_index()
statut.columns = ['Statut', "Nombre d'alertes"]
statut['Pourcentage (%)'] = (statut["Nombre d'alertes"] / len(alertes) * 100).round(1)

# 6. Issue des alertes
issue = alertes['issue'].value_counts().sort_index().reset_index()
issue.columns = ['Issue', "Nombre d'alertes"]
issue['Pourcentage de toutes les alertes (%)'] = (issue["Nombre d'alertes"] / len(alertes) * 100).round(1)
nb_prises = alertes['prise_en_charge'].sum()
issue['Pourcentage des alertes prises en charge (%)'] = (issue["Nombre d'alertes"] / nb_prises * 100).round(1)
issue.loc[issue['Issue'].str.startswith('0.'), 'Pourcentage des alertes prises en charge (%)'] = None

# 7. Prise en charge selon les domaines en alerte
#    Une alerte avec plusieurs domaines compte dans chacun de ses domaines.
noms_domaines = {
    'cognition': 'Cognition', 'nutrition': 'Nutrition', 'vision': 'Vision',
    'audition': 'Audition', 'psychologie': 'Psychologie', 'mobilite': 'Mobilité',
    'social': 'Social', 'aidant': 'Aidant', 'incontinence': 'Incontinence'
}
lignes = []
for code, nom in noms_domaines.items():
    avec = alertes[alertes['alerte_' + code] == True]
    lignes.append({
        'Domaine': nom,
        "Alertes contenant ce domaine": len(avec),
        'Prises en charge (%)': round(avec['prise_en_charge'].mean() * 100, 1),
        'Orientées vers un professionnel (%)': round(avec['orientee'].mean() * 100, 1)
    })
par_domaine = pd.DataFrame(lignes).sort_values("Alertes contenant ce domaine", ascending=False)

# 8. Prise en charge selon le profil
variables = {
    'annee': "Année de l'alerte",
    'modalite': 'Modalité du test',
    'classe_age': "Classe d'âge",
    'sexe': 'Sexe',
    'departement': 'Département',
    'site': "Site d'expérimentation"
}
lignes = []
tests_khi2 = []
for col, nom in variables.items():
    groupes = alertes.groupby(col).agg(
        nb=('prise_en_charge', 'size'),
        prises=('prise_en_charge', 'sum'),
        orientees=('orientee', 'sum')
    ).reset_index()
    for _, g in groupes.iterrows():
        lignes.append({
            'Caractéristique': nom,
            'Valeur': g[col],
            "Nombre d'alertes": g['nb'],
            'Prises en charge': g['prises'],
            'Prises en charge (%)': round(g['prises'] / g['nb'] * 100, 1),
            'Orientées vers un professionnel': g['orientees'],
            'Orientées (%)': round(g['orientees'] / g['nb'] * 100, 1)
        })
    # Test du khi-deux sur la prise en charge (sans les petites catégories)
    sous = alertes[~alertes[col].isin(['Non renseigné', 'Hors Normandie'])]
    if col == 'annee':
        sous = sous[sous['annee'] >= 2022]   # 2020-2021 : trop peu d'alertes
    tableau = pd.crosstab(sous[col], sous['prise_en_charge'])
    khi2, p, ddl, _ = chi2_contingency(tableau)
    tests_khi2.append({
        'Caractéristique': nom,
        'Khi-deux': round(khi2, 2),
        'Degrés de liberté': ddl,
        'p-valeur': round(p, 4),
        'Différence significative (p < 0,05)': 'OUI' if p < 0.05 else 'NON'
    })
profil = pd.DataFrame(lignes)
tests_khi2 = pd.DataFrame(tests_khi2)

# 9. Délai entre l'alerte et la première action
avec_action = alertes[alertes['premiere_action'].notna()].copy()
avec_action['delai_jours'] = (pd.to_datetime(avec_action['premiere_action'])
                              - pd.to_datetime(avec_action['date_alerte'])).dt.days
delais = avec_action['delai_jours'].describe(percentiles=[0.25, 0.5, 0.75]).reset_index()
delais.columns = ['Statistique', 'Délai en jours']
delais['Statistique'] = delais['Statistique'].map({
    'count': "Alertes avec au moins une action", 'mean': 'Délai moyen', 'std': 'Écart-type',
    'min': 'Délai minimum', '25%': '1er quartile', '50%': 'Délai médian',
    '75%': '3e quartile', 'max': 'Délai maximum'})
delais['Délai en jours'] = delais['Délai en jours'].round(1)

avec_action['classe_delai'] = pd.cut(avec_action['delai_jours'], bins=[-1000, 0, 7, 30, 90, 100000],
                                     labels=['Le jour même', '1 à 7 jours', '8 à 30 jours',
                                             '31 à 90 jours', 'Plus de 90 jours'])
classes_delai = avec_action['classe_delai'].value_counts().sort_index().reset_index()
classes_delai.columns = ['Délai', "Nombre d'alertes"]
classes_delai['Pourcentage (%)'] = (classes_delai["Nombre d'alertes"] / len(avec_action) * 100).round(1)

# 10. Sauvegarder (dans le dossier des données)
fichier_sortie = os.path.join(dossier, "Partie1_C_Devenir_Alertes.xlsx")
with pd.ExcelWriter(fichier_sortie, engine='openpyxl') as writer:
    perimetre.to_excel(writer, sheet_name='1_Perimetre', index=False)
    statut.to_excel(writer, sheet_name='2_Statut', index=False)
    issue.to_excel(writer, sheet_name='3_Issue', index=False)
    par_domaine.to_excel(writer, sheet_name='4_Par_domaine', index=False)
    profil.to_excel(writer, sheet_name='5_Par_profil', index=False)
    tests_khi2.to_excel(writer, sheet_name='6_Tests_khi2', index=False)
    delais.to_excel(writer, sheet_name='7_Delais', index=False)
    classes_delai.to_excel(writer, sheet_name='8_Classes_delai', index=False)

print("--- PÉRIMÈTRE ---")
print(perimetre.to_string(index=False))
print("\n--- STATUT ---")
print(statut.to_string(index=False))
print("\n--- ISSUE ---")
print(issue.to_string(index=False))
print("\n--- PAR DOMAINE ---")
print(par_domaine.to_string(index=False))
print("\n--- PAR PROFIL ---")
print(profil.to_string(index=False))
print("\n--- TESTS DU KHI-DEUX (prise en charge) ---")
print(tests_khi2.to_string(index=False))
print("\n--- DÉLAIS ---")
print(delais.to_string(index=False))
print(classes_delai.to_string(index=False))
print(f"\n✅ Fichier '{fichier_sortie}' généré avec succès !")
