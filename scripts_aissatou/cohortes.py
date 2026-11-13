import pandas as pd

# 1. Charger la base nettoyée (onglet « Donnees ») et le bilan du nettoyage (onglet « Bilan »)
fichier = "Base_Nettoyee.xlsx"
df = pd.read_excel(fichier, sheet_name='Donnees')
bilan_nettoyage = pd.read_excel(fichier, sheet_name='Bilan').set_index('Indicateur')['Valeur']

# 2. Filtrer les personnes cibles (exclure <60 ans)
df_cible = df[df['moins_60_ans'] == 'NON'].copy()

# 3. Convertir les dates (on s'assure que c'est bien un format date)
df_cible['date_etape1'] = pd.to_datetime(df_cible['date_etape1'], errors='coerce', format='mixed')

# 4. Définir la date de référence : la date de l'export (lue dans le nom du fichier par nettoyage.py).
#    Si elle est absente, on prend le test le plus récent de la base.
date_export = pd.to_datetime(bilan_nettoyage.get("Date de l'export"), errors='coerce')
date_reference = date_export if pd.notna(date_export) else df_cible['date_etape1'].max()
print(f"Date de référence : {date_reference.date()}")

# 5. Une ligne par personne : son premier test, et combien de tests elle a faits
# On trie par date puis par numéro de test : « first » est alors bien le premier test de la personne
df_cible['num_tri'] = pd.to_numeric(df_cible['num'], errors='coerce')
df_cible = df_cible.sort_values(by=['participant', 'date_etape1', 'num_tri'])
personnes = df_cible.groupby('participant').agg(
    date_premier_test=('date_etape1', 'first'),
    modalite_premier_test=('saisie', 'first'),
    sexe=('sexe', 'first'),
    age_premier_test=('age_etape1', 'first'),
    nb_total_tests=('date_etape1', 'count')
).reset_index()
personnes['age_premier_test'] = pd.to_numeric(personnes['age_premier_test'], errors='coerce')

# 6. Ancienneté : nombre de jours entre le premier test et la date de l'export
personnes['anciennete_jours'] = (date_reference - personnes['date_premier_test']).dt.days

# 7. Cohortes : TOUTES les personnes sont gardées (on n'exclut plus celles entrées depuis moins d'un an).
#    Le recul est pris en compte dans le calcul du suivi (étape 9).
def definir_cohorte(row):
    if row['modalite_premier_test'] == 'professionnel':
        return 'Cohorte 1 : Par un professionnel'
    elif row['nb_total_tests'] == 1:
        return 'Cohorte 2 : Auto-évaluation isolée'
    else:
        return 'Cohorte 3 : Autonome avec suivi'

personnes['cohorte'] = personnes.apply(definir_cohorte, axis=1)

MODALITES = {'participant': 'Auto-évaluation', 'aide': 'Avec un aidant', 'professionnel': 'Par un professionnel'}
personnes['modalite_lisible'] = personnes['modalite_premier_test'].map(MODALITES).fillna('Non renseigné')
personnes['sexe_lisible'] = personnes['sexe'].map({'feminin': 'Femme', 'masculin': 'Homme'}).fillna('Non renseigné')
personnes['classe_age'] = pd.cut(personnes['age_premier_test'], bins=[59, 69, 79, 89, 120],
                                 labels=['60-69 ans', '70-79 ans', '80-89 ans', '90 ans et plus']).astype(str)
personnes['classe_age'] = personnes['classe_age'].replace('nan', 'Non renseigné')

# 8. Effectifs des cohortes
resultats = personnes['cohorte'].value_counts().sort_index().reset_index()
resultats.columns = ['Cohorte', 'Nombre de personnes']
resultats['Pourcentage (%)'] = (resultats['Nombre de personnes'] / len(personnes) * 100).round(1)

# 9. Suivi : parmi les personnes qui AURAIENT DÉJÀ DÛ refaire le test (premier test il y a plus
#    de 6 mois, ou plus d'un an), combien l'ont refait (au moins 2 tests) ?
#    Les personnes entrées récemment ne comptent pas : elles n'ont pas encore eu le temps de le refaire.
def suivi(groupe_par, nom_colonne):
    lignes = []
    for seuil_nom, seuil_jours in [('6 mois', 183), ('1 an', 365)]:
        eligibles = personnes[personnes['anciennete_jours'] >= seuil_jours]
        groupes = [('Toutes les personnes', eligibles)]
        if groupe_par:
            groupes += [(valeur, g) for valeur, g in eligibles.groupby(groupe_par)]
        for valeur, g in groupes:
            refait = (g['nb_total_tests'] >= 2).sum()
            lignes.append({
                'Recul minimum': seuil_nom,
                nom_colonne: valeur,
                "Personnes qui auraient dû refaire le test": len(g),
                'Ont refait au moins un test': refait,
                'Suivi (%)': round(refait / len(g) * 100, 1) if len(g) else None,
            })
    return pd.DataFrame(lignes)

suivi_modalite = suivi('modalite_lisible', 'Modalité du premier test')
suivi_sexe = suivi('sexe_lisible', 'Sexe')
suivi_age = suivi('classe_age', "Classe d'âge au premier test")

# 10. Description de chaque cohorte : sexe et âge
def decrire(g, nom):
    age = g['age_premier_test']
    ligne = {'Cohorte': nom, 'Nombre de personnes': len(g),
             'Femmes (%)': round((g['sexe_lisible'] == 'Femme').mean() * 100, 1),
             'Hommes (%)': round((g['sexe_lisible'] == 'Homme').mean() * 100, 1),
             'Âge moyen': round(age.mean(), 1), 'Écart-type': round(age.std(), 1),
             'Âge médian': age.median(), 'Âge minimum': age.min(), 'Âge maximum': age.max()}
    for classe in ['60-69 ans', '70-79 ans', '80-89 ans', '90 ans et plus']:
        ligne[f'{classe} (%)'] = round((g['classe_age'] == classe).mean() * 100, 1)
    return ligne

description = pd.DataFrame([decrire(g, nom) for nom, g in personnes.groupby('cohorte')]
                           + [decrire(personnes, 'Toutes les cohortes')])

# 11. Sauvegarder
with pd.ExcelWriter("Resultats_Cohortes.xlsx", engine='openpyxl') as writer:
    resultats.to_excel(writer, sheet_name='1_Cohortes', index=False)
    description.to_excel(writer, sheet_name='2_Description', index=False)
    suivi_modalite.to_excel(writer, sheet_name='3_Suivi_modalite', index=False)
    suivi_sexe.to_excel(writer, sheet_name='4_Suivi_sexe', index=False)
    suivi_age.to_excel(writer, sheet_name='5_Suivi_age', index=False)

print(f"Personnes analysées (60 ans et plus) : {len(personnes)}")
print("\n--- COHORTES ---")
print(resultats.to_string(index=False))
print("\n--- DESCRIPTION ---")
print(description.to_string(index=False))
print("\n--- SUIVI (selon la modalité du premier test) ---")
print(suivi_modalite.to_string(index=False))
print("\n✅ Fichier 'Resultats_Cohortes.xlsx' généré avec succès !")
