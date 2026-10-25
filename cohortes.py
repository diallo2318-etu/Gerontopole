import pandas as pd

# 1. Charger la base nettoyée
df = pd.read_excel("Base_Nettoyee.xlsx")

# 2. Filtrer les personnes cibles (exclure <60 ans)
df_cible = df[df['moins_60_ans'] == 'NON'].copy()

# 3. Convertir les dates (on s'assure que c'est bien un format date)
df_cible['date_etape1'] = pd.to_datetime(df_cible['date_etape1'], errors='coerce')

# 4. Définir la date de référence (le test le plus récent de la base)
date_reference = df_cible['date_etape1'].max()
print(f"Date de référence : {date_reference.date()}")

# 5. Trouver le premier test de chaque personne et son ancienneté
premier_test = df_cible.groupby('participant').agg(
    date_premier_test=('date_etape1', 'min'),
    modalite_premier_test=('saisie', 'first'),
    nb_total_tests=('date_etape1', 'count')
).reset_index()

# On s'assure que la date du premier test est bien au format date
premier_test['date_premier_test'] = pd.to_datetime(premier_test['date_premier_test'])

# 6. Calculer l'ancienneté en jours
premier_test['anciennete_jours'] = (date_reference - premier_test['date_premier_test']).dt.days

# 7. Filtrer : on ne garde que ceux dont le premier test a plus d'un an (365 jours)
total_avant = len(premier_test)
premier_test_eligible = premier_test[premier_test['anciennete_jours'] >= 365].copy()
total_apres = len(premier_test_eligible)

print(f"Personnes au total (cibles) : {total_avant}")
print(f"Personnes exclues car premier test < 1 an : {total_avant - total_apres}")
print(f"Personnes analysées (recul > 1 an) : {total_apres}")

# 8. Appliquer les règles de classification
def definir_cohorte(row):
    if row['modalite_premier_test'] == 'professionnel':
        return 'Cohorte 1 : Par un professionnel'
    elif row['nb_total_tests'] == 1:
        return 'Cohorte 2 : Auto-évaluation isolée'
    else:
        return 'Cohorte 3 : Autonome avec suivi'

premier_test_eligible['cohorte'] = premier_test_eligible.apply(definir_cohorte, axis=1)

# 9. Compter les effectifs
resultats = premier_test_eligible['cohorte'].value_counts().reset_index()
resultats.columns = ['Cohorte', 'Nombre de personnes']
total = resultats['Nombre de personnes'].sum()
resultats['Pourcentage (%)'] = (resultats['Nombre de personnes'] / total * 100).round(1)

# 10. Sauvegarder
resultats.to_excel("Resultats_Cohortes_Filtrees.xlsx", index=False)

print("\n✅ Fichier 'Resultats_Cohortes_Filtrees.xlsx' généré avec succès !")
print("\n--- RÉSULTATS ---")
print(resultats.to_string(index=False))