import os
import sys
from pathlib import Path

import pandas as pd

# Les territoires sont reconnus comme dans l'entrepôt (partie 1) : on réutilise ses outils.
# Centre Manche et Elbeuf : par la liste des communes (entrepot/communes_experimentation.csv) ;
# Lisieux : par code postal, en attendant sa liste de communes (entrepot/territoires_experimentation.csv).
DEPOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DEPOT / "entrepot"))
from construire_entrepot import LocalisateurCommune, localiser, site_experimentation  # noqa: E402

fichier = "Base_Nettoyee.xlsx"

if not os.path.exists(fichier):
    print(f"ERREUR : Le fichier '{fichier}' n'existe pas dans ce dossier.")
else:
    print("Chargement du fichier...")
    df = pd.read_excel(fichier, sheet_name='Donnees', dtype={'cp': str})
    bilan_nettoyage = pd.read_excel(fichier, sheet_name='Bilan').set_index('Indicateur')['Valeur']
    lignes_depart = int(bilan_nettoyage["Lignes au départ"])

    # Calcul du total pour les pourcentages (toutes les lignes de la base nettoyée)
    total_lignes = len(df)

    print("Création du fichier Excel...")
    if os.path.exists("Base_Statistiques_Completes.xlsx"):
        os.remove("Base_Statistiques_Completes.xlsx")

    with pd.ExcelWriter("Base_Statistiques_Completes.xlsx", engine='openpyxl') as writer:

        # --- Onglet 1 : Bilan ---
        bilan = pd.DataFrame({
            "Indicateur": ["Lignes au départ", "Lignes après nettoyage", "Tests one-shot marqués", "Personnes < 60 ans marquées"],
            "Valeur": [lignes_depart, len(df), (df['one_shot_pro'] == 'OUI').sum(), (df['moins_60_ans'] == 'OUI').sum()]
        })
        bilan.to_excel(writer, sheet_name='1_Bilan', index=False)

        # --- Onglet 2 : Modalités ---
        df['modalite_lisible'] = df['saisie'].map({
            'participant': 'Auto-évaluation', 'aide': 'Avec un aidant', 'professionnel': 'Par un professionnel'
        }).fillna(df['saisie'])
        modalite = df['modalite_lisible'].value_counts().reset_index()
        modalite.columns = ['Modalité', 'Nombre']
        modalite['Pourcentage (%)'] = (modalite['Nombre'] / total_lignes * 100).round(1)
        modalite.to_excel(writer, sheet_name='2_Modalites', index=False)

        # --- Onglet 3 : Suivi ---
        suivi = df['type_suivi'].value_counts().reset_index()
        suivi.columns = ['Type de suivi', 'Nombre']
        suivi['Pourcentage (%)'] = (suivi['Nombre'] / total_lignes * 100).round(1)
        suivi.to_excel(writer, sheet_name='3_Suivi', index=False)

        # --- Onglet 4 : Années ---
        df['date_etape1'] = pd.to_datetime(df['date_etape1'], errors='coerce', format='mixed')
        annee = df['date_etape1'].dt.year.value_counts().sort_index().reset_index()
        annee.columns = ['Année', 'Nombre']
        annee['Pourcentage (%)'] = (annee['Nombre'] / total_lignes * 100).round(1)
        annee.to_excel(writer, sheet_name='4_Annees', index=False)

        # --- Onglet 5 : Sexe ---
        sexe = df['sexe'].value_counts().reset_index()
        sexe.columns = ['Sexe', 'Nombre']
        sexe['Pourcentage (%)'] = (sexe['Nombre'] / total_lignes * 100).round(1)
        sexe.to_excel(writer, sheet_name='5_Sexe', index=False)

        # --- Onglet 6 : Âge (pas de pourcentage ici, on garde les stats) ---
        age_stats = df['age_etape1'].describe().reset_index()
        age_stats.columns = ['Statistique', 'Valeur']
        age_stats.to_excel(writer, sheet_name='6_Age', index=False)

        # --- Onglet 7 : Territoires (mêmes règles que l'entrepôt et la partie 1) ---
        # a) retrouver le code INSEE de la commune à partir du code postal et de la ville
        communes = pd.read_csv(DEPOT / "bases" / "communes_normandie.csv", sep=";",
                               dtype={"code_insee": str, "code_epci": str, "departement": str})
        df['cp'] = df['cp'].astype(str).str.strip().where(df['cp'].notna())
        df['cp'] = df['cp'].where(~df['cp'].isin(['dm', '']))   # « dm » = donnée manquante
        df = localiser(df, LocalisateurCommune(communes), 'cp', 'ville')
        # b) site d'expérimentation de la commune, sinon « Hors sites » (comme dans la partie 1)
        df['territoire'] = site_experimentation(df['cp'], df['code_insee']).fillna('Hors sites').values

        territoire = df['territoire'].value_counts().reset_index()
        territoire.columns = ['Territoire', 'Nombre']
        territoire['Pourcentage (%)'] = (territoire['Nombre'] / total_lignes * 100).round(1)
        territoire.to_excel(writer, sheet_name='7_Territoires', index=False)

    print("\n✅ Fichier 'Base_Statistiques_Completes.xlsx' généré avec succès (avec les pourcentages) !")
