import pandas as pd
import os

fichier = "Base_Nettoyee.xlsx"

if not os.path.exists(fichier):
    print(f"ERREUR : Le fichier '{fichier}' n'existe pas dans ce dossier.")
else:
    print("Chargement du fichier...")
    df = pd.read_excel(fichier, dtype={'cp': str})
    
    # Calcul du total pour les pourcentages (toutes les lignes de la base nettoyée)
    total_lignes = len(df)

    print("Création du fichier Excel...")
    if os.path.exists("Base_Statistiques_Completes.xlsx"):
        os.remove("Base_Statistiques_Completes.xlsx")

    with pd.ExcelWriter("Base_Statistiques_Completes.xlsx", engine='openpyxl') as writer:
        
        # --- Onglet 1 : Bilan ---
        bilan = pd.DataFrame({
            "Indicateur": ["Lignes au départ", "Lignes après nettoyage", "Tests one-shot marqués", "Personnes < 60 ans marquées"],
            "Valeur": [2971, len(df), (df['one_shot_pro'] == 'OUI').sum(), (df['moins_60_ans'] == 'OUI').sum()]
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
        df['date_etape1'] = pd.to_datetime(df['date_etape1'], errors='coerce')
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

        # --- Onglet 7 : Territoires ---
        codes_lisieux = ['14100']
        codes_elbeuf = ['76500', '76320', '76410']
        codes_manche = ['50250', '50500']
        
        def classer_territoire(cp):
            cp = str(cp).strip()
            if cp in codes_lisieux: return 'Lisieux'
            elif cp in codes_elbeuf: return 'Elbeuf'
            elif cp in codes_manche: return 'Centre Manche'
            else: return 'Reste de la Normandie'

        df['cp'] = df['cp'].astype(str).str.strip()
        df['territoire'] = df['cp'].apply(classer_territoire)
        
        territoire = df['territoire'].value_counts().reset_index()
        territoire.columns = ['Territoire', 'Nombre']
        territoire['Pourcentage (%)'] = (territoire['Nombre'] / total_lignes * 100).round(1)
        territoire.to_excel(writer, sheet_name='7_Territoires', index=False)

    print("\n✅ Fichier 'Base_Statistiques_Completes.xlsx' généré avec succès (avec les pourcentages) !")