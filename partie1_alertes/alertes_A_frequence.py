import os
import duckdb
import pandas as pd

# Partie 1 - Tâche A : combien d'alertes, et dans quels domaines

# 1. Ouvrir l'entrepôt (dans le dossier privé des données, jamais dans le dépôt)
dossier = os.path.expanduser(os.environ.get("DONNEES_ICOPE", "~/donnees_icope"))
con = duckdb.connect(os.path.join(dossier, "entrepot_icope.duckdb"), read_only=True)

# 2. Choisir les tests analysés :
#    - un seul test par personne et par jour (retenu)
#    - sans les essais probables (moins de 50 ans, règle de Marine)
#    - les moins de 60 ans sont gardés
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

noms_domaines = {
    'cognition': 'Cognition', 'nutrition': 'Nutrition', 'vision': 'Vision',
    'audition': 'Audition', 'psychologie': 'Psychologie', 'mobilite': 'Mobilité',
    'social': 'Social', 'aidant': 'Aidant', 'incontinence': 'Incontinence'
}
alertes['domaine'] = alertes['domaine'].map(noms_domaines)

# 3. Périmètre
total_depart = con.sql("SELECT count(*) FROM icope_depistage").fetchone()[0]
total_retenus = con.sql("SELECT count(*) FROM icope_depistage WHERE retenu").fetchone()[0]
perimetre = pd.DataFrame({
    "Indicateur": ["Tests au départ", "Tests après doublons du même jour",
                   "Essais probables retirés (moins de 50 ans)", "Tests analysés",
                   "Personnes analysées"],
    "Valeur": [total_depart, total_retenus, total_retenus - len(tests), len(tests),
               tests['participant'].nunique()]
})

# 4. Nombre d'alertes par test
nb_alertes = tests['nb_alertes'].value_counts().sort_index().reset_index()
nb_alertes.columns = ["Nombre d'alertes", 'Nombre de tests']
nb_alertes['Pourcentage (%)'] = (nb_alertes['Nombre de tests'] / len(tests) * 100).round(1)

resume = pd.DataFrame({
    "Indicateur": ["Tests avec au moins une alerte", "Pourcentage (%)",
                   "Nombre moyen d'alertes par test", "Nombre médian d'alertes par test"],
    "Valeur": [(tests['nb_alertes'] >= 1).sum(),
               round((tests['nb_alertes'] >= 1).mean() * 100, 1),
               round(tests['nb_alertes'].mean(), 2),
               tests['nb_alertes'].median()]
})

# 5. Alertes par domaine
#    Certaines questions ne sont pas posées à tout le monde (audition, social,
#    incontinence selon la version du questionnaire ; aidant seulement aux aidants) :
#    le pourcentage se calcule parmi les tests où la question a été posée.
domaines = alertes.groupby('domaine').agg(
    alertes=('alerte', lambda x: (x == True).sum()),
    question_posee=('alerte', lambda x: x.notna().sum()),
    question_non_posee=('alerte', lambda x: x.isna().sum())
).reset_index()
domaines['pourcentage'] = (domaines['alertes'] / domaines['question_posee'] * 100).round(1)
domaines = domaines.sort_values('alertes', ascending=False)
domaines.columns = ['Domaine', "Tests en alerte", 'Question posée', 'Question non posée',
                    'Pourcentage en alerte (%)']

# 6. Combinaisons d'alertes les plus fréquentes
en_alerte = alertes[alertes['alerte'] == True]
combinaisons = (en_alerte.sort_values('domaine')
                .groupby('id_depistage')['domaine']
                .apply(lambda x: ' + '.join(x)))
top_combinaisons = combinaisons.value_counts().head(15).reset_index()
top_combinaisons.columns = ['Combinaison', 'Nombre de tests']
top_combinaisons['Pourcentage des tests en alerte (%)'] = (
    top_combinaisons['Nombre de tests'] / len(combinaisons) * 100).round(1)

# 7. Paires de domaines souvent en alerte ensemble
paires = en_alerte.merge(en_alerte, on='id_depistage')
paires = paires[paires['domaine_x'] < paires['domaine_y']]
top_paires = paires.groupby(['domaine_x', 'domaine_y']).size().sort_values(ascending=False).head(15).reset_index()
top_paires.columns = ['Domaine 1', 'Domaine 2', 'Nombre de tests']

# 8. Sauvegarder (dans le dossier des données)
fichier_sortie = os.path.join(dossier, "Partie1_A_Frequence_Alertes.xlsx")
with pd.ExcelWriter(fichier_sortie, engine='openpyxl') as writer:
    perimetre.to_excel(writer, sheet_name='1_Perimetre', index=False)
    resume.to_excel(writer, sheet_name='2_Resume', index=False)
    nb_alertes.to_excel(writer, sheet_name='3_Nb_alertes', index=False)
    domaines.to_excel(writer, sheet_name='4_Domaines', index=False)
    top_combinaisons.to_excel(writer, sheet_name='5_Combinaisons', index=False)
    top_paires.to_excel(writer, sheet_name='6_Paires', index=False)

print("--- PÉRIMÈTRE ---")
print(perimetre.to_string(index=False))
print("\n--- RÉSUMÉ ---")
print(resume.to_string(index=False))
print("\n--- DOMAINES ---")
print(domaines.to_string(index=False))
print("\n--- COMBINAISONS (top 5) ---")
print(top_combinaisons.head(5).to_string(index=False))
print(f"\n✅ Fichier '{fichier_sortie}' généré avec succès !")
