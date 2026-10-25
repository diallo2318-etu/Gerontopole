import pandas as pd
import glob

# 1. Trouver le fichier source
fichiers = glob.glob("bdi_etape1_*.xlsx")
fichier_source = fichiers[0]
print(f"--- Nettoyage du fichier : {fichier_source} ---")

# 2. Charger les données
df = pd.read_excel(fichier_source)
total_initial = len(df)

# 3. Appliquer la Règle 1 : doublons le même jour (garder le dernier)
# On trie d'abord par participant et par date
df = df.sort_values(by=['participant', 'date_etape1'])
# On supprime les doublons en gardant la dernière ligne
df = df.drop_duplicates(subset=['participant', 'date_etape1'], keep='last')
total_apres_doublons = len(df)

# 4. Appliquer la Règle 2 : marquer les one-shot professionnels
# On compte combien de participants différents chaque créateur a évalués
nb_participants_par_createur = df.groupby('id_createur')['participant'].transform('nunique')
# On crée la colonne de marquage
df['one_shot_pro'] = 'NON'
df.loc[(df['saisie'] == 'professionnel') & (nb_participants_par_createur == 1), 'one_shot_pro'] = 'OUI'

# 5. Appliquer la Règle 3 : marquer les moins de 60 ans
df['moins_60_ans'] = 'NON'
df.loc[df['age_etape1'] < 60, 'moins_60_ans'] = 'OUI'

# 6. Sauvegarder la base propre
fichier_sortie = "Base_Nettoyee.xlsx"
df.to_excel(fichier_sortie, index=False)

# 7. Afficher le bilan
print("\n--- BILAN DU NETTOYAGE ---")
print(f"Lignes au départ : {total_initial}")
print(f"Lignes après suppression des doublons : {total_apres_doublons}")
print(f"Tests 'one-shot' de professionnels marqués : {(df['one_shot_pro'] == 'OUI').sum()}")
print(f"Personnes de moins de 60 ans marquées : {(df['moins_60_ans'] == 'OUI').sum()}")
print(f"\n✅ Fichier '{fichier_sortie}' généré avec succès.")