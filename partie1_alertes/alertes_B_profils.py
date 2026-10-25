import os
import duckdb
import pandas as pd
from scipy.stats import chi2_contingency

# Partie 1 - Tâche B : le profil des personnes en alerte

# 1. Ouvrir l'entrepôt (dans le dossier privé des données, jamais dans le dépôt)
dossier = os.path.expanduser(os.environ.get("DONNEES_ICOPE", "~/donnees_icope"))
con = duckdb.connect(os.path.join(dossier, "entrepot_icope.duckdb"), read_only=True)

# 2. Choisir les tests analysés (mêmes règles que la tâche A) :
#    retenus (un test par personne et par jour), sans les essais probables (moins de 50 ans)
tests = con.sql("""
    SELECT * FROM icope_depistage
    WHERE retenu AND NOT test_probable
""").df()

alertes = con.sql("""
    SELECT a.id_depistage, a.domaine, a.alerte
    FROM icope_alerte a
    JOIN icope_depistage d USING (id_depistage)
    WHERE d.retenu AND NOT d.test_probable
""").df()

# 3. Préparer des variables lisibles
tests['en_alerte'] = tests['nb_alertes'] >= 1

tests['classe_age'] = pd.cut(tests['age'], bins=[49, 59, 69, 79, 89, 120],
                             labels=['50-59 ans', '60-69 ans', '70-79 ans', '80-89 ans', '90 ans et plus'])
tests['classe_age'] = tests['classe_age'].astype(str)

tests['sexe'] = tests['sexe'].map({'F': 'Femme', 'M': 'Homme'}).fillna('Non renseigné')
tests['modalite'] = tests['modalite'].fillna('Non renseigné')
tests['type_suivi'] = tests['type_suivi'].map({'initiale': 'Test initial', 'suivi': 'Test de suivi'})
tests['medecin_traitant'] = tests['a_medecin_traitant'].map({True: 'Oui', False: 'Non'}).fillna('Non renseigné')

noms_departements = {'14': '14 Calvados', '27': '27 Eure', '50': '50 Manche',
                     '61': '61 Orne', '76': '76 Seine-Maritime'}
tests['departement'] = tests['departement'].map(noms_departements).fillna(
    tests['departement'].notna().map({True: 'Hors Normandie', False: 'Non renseigné'}))
tests['site'] = tests['experimentation'].fillna('Hors sites')

variables = {
    'classe_age': "Classe d'âge",
    'sexe': 'Sexe',
    'modalite': 'Modalité du test',
    'type_suivi': 'Type de test',
    'medecin_traitant': 'Médecin traitant',
    'departement': 'Département',
    'site': "Site d'expérimentation"
}

# 4. Périmètre
perimetre = pd.DataFrame({
    "Indicateur": ["Tests analysés", "Tests avec au moins une alerte", "Tests sans alerte"],
    "Valeur": [len(tests), tests['en_alerte'].sum(), (~tests['en_alerte']).sum()]
})

# 5. Âge des tests en alerte et sans alerte
age = tests.groupby('en_alerte')['age'].describe()[['count', 'mean', '50%', 'min', 'max']].reset_index()
age['en_alerte'] = age['en_alerte'].map({True: 'Avec au moins une alerte', False: 'Sans alerte'})
age.columns = ['Groupe', 'Nombre de tests', 'Âge moyen', 'Âge médian', 'Âge minimum', 'Âge maximum']
age['Âge moyen'] = age['Âge moyen'].round(1)
age[['Nombre de tests', 'Âge minimum', 'Âge maximum']] = age[['Nombre de tests', 'Âge minimum', 'Âge maximum']].astype(int)

# 6. Part des tests en alerte selon chaque caractéristique
lignes = []
for col, nom in variables.items():
    groupes = tests.groupby(col).agg(
        nb_tests=('en_alerte', 'size'),
        nb_en_alerte=('en_alerte', 'sum'),
        nb_moyen_alertes=('nb_alertes', 'mean')
    ).reset_index()
    for _, g in groupes.iterrows():
        lignes.append({
            'Caractéristique': nom,
            'Valeur': g[col],
            'Nombre de tests': g['nb_tests'],
            'Tests en alerte': g['nb_en_alerte'],
            'Pourcentage en alerte (%)': round(g['nb_en_alerte'] / g['nb_tests'] * 100, 1),
            "Nombre moyen d'alertes": round(g['nb_moyen_alertes'], 2)
        })
profil = pd.DataFrame(lignes)

# 7. Test du khi-deux : la part d'alertes est-elle vraiment différente selon la caractéristique ?
#    On retire les valeurs "Non renseigné" et "Hors Normandie" (trop peu de tests pour le test).
tests_khi2 = []
for col, nom in variables.items():
    sous = tests[~tests[col].isin(['Non renseigné', 'Hors Normandie'])]
    tableau = pd.crosstab(sous[col], sous['en_alerte'])
    khi2, p, ddl, _ = chi2_contingency(tableau)
    tests_khi2.append({
        'Caractéristique': nom,
        'Khi-deux': round(khi2, 2),
        'Degrés de liberté': ddl,
        'p-valeur': round(p, 4),
        'Différence significative (p < 0,05)': 'OUI' if p < 0.05 else 'NON'
    })
tests_khi2 = pd.DataFrame(tests_khi2)

# 8. Part en alerte par domaine, selon le sexe et l'âge
#    (parmi les tests où la question a été posée, comme dans la tâche A)
noms_domaines = {
    'cognition': 'Cognition', 'nutrition': 'Nutrition', 'vision': 'Vision',
    'audition': 'Audition', 'psychologie': 'Psychologie', 'mobilite': 'Mobilité',
    'social': 'Social', 'aidant': 'Aidant', 'incontinence': 'Incontinence'
}
alertes['domaine'] = alertes['domaine'].map(noms_domaines)
alertes = alertes[alertes['alerte'].notna()]
alertes = alertes.merge(tests[['id_depistage', 'sexe', 'classe_age', 'age', 'modalite',
                               'medecin_traitant', 'hors_cible_moins_60']], on='id_depistage')
alertes['alerte'] = alertes['alerte'].astype(bool)

par_sexe = alertes[alertes['sexe'] != 'Non renseigné'].pivot_table(
    index='domaine', columns='sexe', values='alerte', aggfunc=['mean', 'size'])
par_age = alertes.pivot_table(index='domaine', columns='classe_age', values='alerte', aggfunc=['mean', 'size'])
pourcentages = pd.concat([par_sexe['mean'], par_age['mean']], axis=1) * 100
effectifs = pd.concat([par_sexe['size'], par_age['size']], axis=1).fillna(0).astype(int)

# Un pourcentage calculé sur moins de 30 tests n'a pas de sens : on laisse la case vide
pourcentages = pourcentages.where(effectifs >= 30).round(1)

domaines_sexe_age = pourcentages.reset_index().rename(columns={'domaine': 'Domaine'})
domaines_effectifs = effectifs.reset_index().rename(columns={'domaine': 'Domaine'})

# 9. Profil des tests en alerte, domaine par domaine
en_alerte = alertes[alertes['alerte']]
profil_domaines = en_alerte.groupby('domaine').agg(
    tests_en_alerte=('id_depistage', 'size'),
    age_moyen=('age', 'mean'),
    pct_femmes=('sexe', lambda x: (x == 'Femme').mean() * 100),
    pct_80_ans_et_plus=('age', lambda x: (x >= 80).mean() * 100),
    pct_par_un_professionnel=('modalite', lambda x: (x == 'par un professionnel').mean() * 100),
    pct_sans_medecin=('medecin_traitant', lambda x: (x == 'Non').mean() * 100),
    pct_moins_60=('hors_cible_moins_60', 'mean')
).reset_index()
profil_domaines['pct_moins_60'] = profil_domaines['pct_moins_60'] * 100
profil_domaines = profil_domaines.round(1).sort_values('tests_en_alerte', ascending=False)
profil_domaines.columns = ['Domaine', 'Tests en alerte', 'Âge moyen', 'Femmes (%)',
                           '80 ans et plus (%)', 'Test par un professionnel (%)',
                           'Sans médecin traitant (%)', 'Moins de 60 ans (%)']

# 10. Sauvegarder (dans le dossier des données)
fichier_sortie = os.path.join(dossier, "Partie1_B_Profils_Alertes.xlsx")
with pd.ExcelWriter(fichier_sortie, engine='openpyxl') as writer:
    perimetre.to_excel(writer, sheet_name='1_Perimetre', index=False)
    age.to_excel(writer, sheet_name='2_Age', index=False)
    profil.to_excel(writer, sheet_name='3_Profil', index=False)
    tests_khi2.to_excel(writer, sheet_name='4_Tests_khi2', index=False)
    domaines_sexe_age.to_excel(writer, sheet_name='5_Domaines_sexe_age', index=False)
    domaines_effectifs.to_excel(writer, sheet_name='6_Domaines_effectifs', index=False)
    profil_domaines.to_excel(writer, sheet_name='7_Domaines_profil', index=False)

print("--- ÂGE ---")
print(age.to_string(index=False))
print("\n--- PROFIL ---")
print(profil.to_string(index=False))
print("\n--- TESTS DU KHI-DEUX ---")
print(tests_khi2.to_string(index=False))
print("\n--- DOMAINES PAR SEXE ET ÂGE (% en alerte, vide si moins de 30 tests) ---")
print(domaines_sexe_age.to_string(index=False))
print("\n--- EFFECTIFS (tests où la question a été posée) ---")
print(domaines_effectifs.to_string(index=False))
print("\n--- PROFIL PAR DOMAINE ---")
print(profil_domaines.to_string(index=False))
print(f"\n✅ Fichier '{fichier_sortie}' généré avec succès !")
