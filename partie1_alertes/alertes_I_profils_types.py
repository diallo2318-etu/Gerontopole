import os
import duckdb
import pandas as pd

# Partie 1 - Tâche I : profils patients types et format d'entrée du modèle
# Demandé : liste des tâches du 20/10 (Personne 1) : « 5 profils patients types » et
# « format d'entrée du modèle (code postal, domaines altérés, résultat Step 1) ».
# On ajoute les 10 combinaisons d'alertes les plus fréquentes pour couvrir plus de monde.

# 1. Ouvrir l'entrepôt (dans le dossier privé des données, jamais dans le dépôt)
dossier = os.path.expanduser(os.environ.get("DONNEES_ICOPE", "~/donnees_icope"))
con = duckdb.connect(os.path.join(dossier, "entrepot_icope.duckdb"), read_only=True)

domaines = {'cognition': 'Cognition', 'nutrition': 'Nutrition', 'vision': 'Vision', 'audition': 'Audition',
            'psychologie': 'Psychologie', 'mobilite': 'Mobilité', 'social': 'Social', 'aidant': 'Aidant',
            'incontinence': 'Incontinence'}

# 2. Charger les tests en alerte (mêmes règles que les tâches A à H)
tests = con.sql("""
    SELECT * FROM icope_depistage
    WHERE retenu AND NOT test_probable AND nb_alertes >= 1
""").df()
tests['combinaison'] = tests.apply(
    lambda t: ' + '.join(nom for d, nom in domaines.items() if t[f'alerte_{d}'] == True), axis=1)

# Le devenir de chaque test : pris en charge si au moins une de ses alertes l'est
alertes = con.sql("""
    SELECT v.id_depistage, v.issue
    FROM v_alerte_issue v JOIN icope_depistage d USING (id_depistage)
    WHERE d.retenu AND NOT d.test_probable
""").df()
devenir = alertes.groupby('id_depistage').agg(
    prise_en_charge=('issue', lambda x: (~x.str.startswith('0.')).any()),
    orientee=('issue', lambda x: x.str.startswith('1.').any()),
    deja_suivie=('issue', lambda x: x.str.startswith('3.').any())
).reset_index()
tests = tests.merge(devenir, on='id_depistage', how='left')

# 3. Décrire un groupe de tests (même description pour les combinaisons et les profils types)
def decrire(groupe):
    return {
        'Tests': len(groupe),
        'Part des tests en alerte (%)': round(len(groupe) / len(tests) * 100, 1),
        'Âge médian': groupe['age'].median(),
        'Femmes (%)': round((groupe['sexe'] == 'F').mean() * 100, 1),
        'Auto-évaluation (%)': round((groupe['modalite'] == 'auto-évaluation').mean() * 100, 1),
        'Sans médecin traitant (%)': round((groupe['a_medecin_traitant'] == False).mean() * 100, 1),
        'Département le plus fréquent': groupe['departement'].mode().iloc[0] if groupe['departement'].notna().any() else '',
        'Sur un site expérimental (%)': round(groupe['experimentation'].notna().mean() * 100, 1),
        'Pris en charge (%)': round((groupe['prise_en_charge'] == True).mean() * 100, 1),
        'Orientés (%)': round((groupe['orientee'] == True).mean() * 100, 1),
        'Déjà suivis (%)': round((groupe['deja_suivie'] == True).mean() * 100, 1)
    }

# 4. Les 10 combinaisons d'alertes les plus fréquentes
top10 = tests['combinaison'].value_counts().head(10).index
combinaisons = pd.DataFrame([{'Combinaison': c, **decrire(tests[tests['combinaison'] == c])} for c in top10])
combinaisons['Part cumulée (%)'] = combinaisons['Part des tests en alerte (%)'].cumsum().round(1)

# 5. Les 5 profils types (choisis à partir des résultats des tâches A à H)
#    Chacun pose une question différente au parcours.
profils_types = [
    ("1. Vision seule, 60-69 ans, auto-évaluation, hors sites",
     "Le cas le plus fréquent (tâche A) : une alerte simple",
     (tests['combinaison'] == 'Vision') & tests['age'].between(60, 69)
     & (tests['modalite'] == 'auto-évaluation') & tests['experimentation'].isna()),
    ("2. Cognition + mobilité, 80 ans et plus, Manche",
     "Le profil type du Step 2 (tâche H) : personne très âgée, plusieurs anomalies",
     tests['alerte_cognition'] & tests['alerte_mobilite'] & (tests['age'] >= 80) & (tests['departement'] == '50')),
    ("3. Psychologie, moins de 60 ans",
     "Hors de la cible ICOPE (réunion du 16/10) : que lui propose-t-on ?",
     tests['alerte_psychologie'] & (tests['age'] < 60)),
    ("4. Nutrition + mobilité, Calvados",
     "Territoire où presque personne ne traite les alertes (tâches C et F)",
     tests['alerte_nutrition'] & tests['alerte_mobilite'] & (tests['departement'] == '14')),
    ("5. Audition + vision, 70-79 ans",
     "Quand l'alerte est vérifiée, la personne est souvent déjà suivie (tâche D)",
     tests['alerte_audition'] & tests['alerte_vision'] & tests['age'].between(70, 79)),
]
profils = pd.DataFrame([{'Profil': nom, 'Pourquoi ce profil': pourquoi, **decrire(tests[filtre == True])}
                        for nom, pourquoi, filtre in profils_types])

# 6. Format d'entrée du modèle : un champ par ligne, avec sa source dans ICOPE
#    et la part des tests en alerte où il est renseigné.
def renseigne(colonne):
    return round(tests[colonne].notna().mean() * 100, 1)

champs = [
    ('Code postal', 'texte (5 chiffres)', 'ex. 50000', 'icope_depistage.code_postal', renseigne('code_postal')),
    ('Commune (code INSEE)', 'texte (5 caractères)', 'ex. 50502', 'icope_depistage.code_insee', renseigne('code_insee')),
    ('Département', 'texte', '14, 27, 50, 61, 76…', 'icope_depistage.departement', renseigne('departement')),
    ('Site expérimental', 'texte ou vide', 'Centre Manche, Elbeuf, Lisieux, vide', 'icope_depistage.experimentation', 100.0),
    ('Âge', 'nombre entier', '50 à 100 et plus', 'icope_depistage.age', renseigne('age')),
    ('Sexe', 'texte', 'F, M', 'icope_depistage.sexe', renseigne('sexe')),
    ('Modalité du test', 'texte', 'auto-évaluation, avec un aidant, par un professionnel', 'icope_depistage.modalite', renseigne('modalite')),
    ('A un médecin traitant', 'oui / non', 'oui, non, vide', 'icope_depistage.a_medecin_traitant', renseigne('a_medecin_traitant')),
] + [
    (f'Alerte {nom.lower()}', 'oui / non', 'oui, non, vide (question non posée)', f'icope_depistage.alerte_{d}', renseigne(f'alerte_{d}'))
    for d, nom in domaines.items()
] + [
    ("Nombre d'alertes", 'nombre entier', '1 à 9', 'icope_depistage.nb_alertes', renseigne('nb_alertes')),
    ('Levée de doute : alerte confirmée', 'oui / non', 'oui, non, vide (pas de levée de doute)', 'v_alerte_issue.alerte_confirmee', None),
    ('Déjà suivi pour ce domaine', 'oui / non', 'oui, non, vide', 'v_alerte_issue.issue (« 3. Pas orientée : déjà prise en charge »)', None),
]
format_entree = pd.DataFrame(champs, columns=['Champ', 'Type', 'Valeurs possibles', 'Colonne ICOPE',
                                              'Renseigné dans les tests en alerte (%)'])

# Un exemple d'entrée pour chaque profil type (valeurs les plus fréquentes du groupe)
exemples = []
for nom, _, filtre in profils_types:
    groupe = tests[filtre == True]
    exemple = {'Profil': nom,
               'Département': groupe['departement'].mode().iloc[0],
               'Âge': int(groupe['age'].median()),
               'Sexe': groupe['sexe'].mode().iloc[0],
               'Modalité du test': groupe['modalite'].mode().iloc[0],
               'A un médecin traitant': 'oui' if (groupe['a_medecin_traitant'] == True).mean() >= 0.5 else 'non'}
    for d, nom_d in domaines.items():
        exemple[f'Alerte {nom_d.lower()}'] = 'oui' if (groupe[f'alerte_{d}'] == True).mean() >= 0.5 else 'non'
    exemples.append(exemple)
exemples = pd.DataFrame(exemples)

# 7. Sauvegarder (dans le dossier des données)
fichier_sortie = os.path.join(dossier, "Partie1_I_Profils_Types.xlsx")
with pd.ExcelWriter(fichier_sortie, engine='openpyxl') as writer:
    combinaisons.to_excel(writer, sheet_name='1_Top10_combinaisons', index=False)
    profils.to_excel(writer, sheet_name='2_Profils_types', index=False)
    format_entree.to_excel(writer, sheet_name='3_Format_entree', index=False)
    exemples.to_excel(writer, sheet_name='4_Exemples_entree', index=False)

pd.set_option('display.width', 250)
pd.set_option('display.max_columns', 30)
for titre, tableau in [('TOP 10 COMBINAISONS', combinaisons), ('PROFILS TYPES', profils),
                       ("FORMAT D'ENTRÉE", format_entree), ("EXEMPLES D'ENTRÉE", exemples)]:
    print(f"\n--- {titre} ---")
    print(tableau.to_string(index=False))
print(f"\n✅ Fichier '{fichier_sortie}' généré avec succès !")
