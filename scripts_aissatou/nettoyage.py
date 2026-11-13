import pandas as pd
import glob
import re

# 1. Trouver le fichier source (le plus récent s'il y en a plusieurs : la date est dans le nom)
fichiers = sorted(glob.glob("bdi_etape1_*.xlsx"))
if not fichiers:
    raise SystemExit("ERREUR : Je ne trouve pas le fichier bdi_etape1_*.xlsx dans le dossier.")
fichier_source = fichiers[-1]
print(f"--- Nettoyage du fichier : {fichier_source} ---")

# Date de l'export, lue dans le nom du fichier (ex. bdi_etape1_2026-10-09_... -> 2026-10-09)
trouve = re.search(r"\d{4}-\d{2}-\d{2}", fichier_source)
date_export = pd.Timestamp(trouve.group()) if trouve else None

# 2. Charger les données
df = pd.read_excel(fichier_source)
total_initial = len(df)

# 3. Appliquer la Règle 1 : doublons le même jour (garder le dernier)
# Le « dernier » test du jour est celui qui a le plus grand numéro (colonne num),
# comme dans l'entrepôt. On compare les jours, sans l'heure.
df['jour'] = pd.to_datetime(df['date_etape1'], errors='coerce', format='mixed').dt.normalize()
df['num_tri'] = pd.to_numeric(df['num'], errors='coerce')
df = df.sort_values(by=['participant', 'jour', 'num_tri'])
# On supprime les doublons en gardant la dernière ligne (le plus grand numéro)
df = df.drop_duplicates(subset=['participant', 'jour'], keep='last')
df = df.drop(columns=['jour', 'num_tri'])
total_apres_doublons = len(df)

# 4. Appliquer la Règle 2 : marquer les one-shot professionnels
# On compte combien de participants différents chaque créateur a évalués
nb_participants_par_createur = df.groupby('id_createur')['participant'].transform('nunique')
# On crée la colonne de marquage
df['one_shot_pro'] = 'NON'
df.loc[(df['saisie'] == 'professionnel') & (nb_participants_par_createur == 1), 'one_shot_pro'] = 'OUI'

# 5. Appliquer la Règle 3 : marquer les moins de 60 ans
df['moins_60_ans'] = 'NON'
df.loc[pd.to_numeric(df['age_etape1'], errors='coerce') < 60, 'moins_60_ans'] = 'OUI'

# 5 bis. Marquer les essais probables : moins de 50 ans (règle de l'équipe, partie 1). On marque, on ne supprime pas.
df['essai_probable'] = 'NON'
df.loc[pd.to_numeric(df['age_etape1'], errors='coerce') < 50, 'essai_probable'] = 'OUI'

# 6. Sauvegarder la base propre
# Onglet 1 « Donnees » : la base nettoyée (lu par les scripts suivants)
# Onglet 2 « Bilan » : les chiffres du nettoyage (lignes au départ, date de l'export)
bilan = pd.DataFrame({
    "Indicateur": ["Fichier source", "Date de l'export", "Lignes au départ", "Lignes après suppression des doublons",
                   "Essais probables (moins de 50 ans) marqués"],
    "Valeur": [fichier_source, date_export.strftime("%Y-%m-%d") if date_export is not None else "", total_initial,
               total_apres_doublons, int((df['essai_probable'] == 'OUI').sum())]
})
fichier_sortie = "Base_Nettoyee.xlsx"
with pd.ExcelWriter(fichier_sortie, engine='openpyxl') as writer:
    df.to_excel(writer, sheet_name='Donnees', index=False)
    bilan.to_excel(writer, sheet_name='Bilan', index=False)

# 7. Afficher le bilan
print("\n--- BILAN DU NETTOYAGE ---")
print(f"Lignes au départ : {total_initial}")
print(f"Lignes après suppression des doublons : {total_apres_doublons}")
print(f"Tests 'one-shot' de professionnels marqués : {(df['one_shot_pro'] == 'OUI').sum()}")
print(f"Personnes de moins de 60 ans marquées : {(df['moins_60_ans'] == 'OUI').sum()}")
print(f"Essais probables (moins de 50 ans) marqués : {(df['essai_probable'] == 'OUI').sum()}")
print(f"\n✅ Fichier '{fichier_sortie}' généré avec succès.")
