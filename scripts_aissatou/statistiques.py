import pandas as pd

# 1. Charger la base nettoyée (onglet « Donnees ») et le bilan du nettoyage (onglet « Bilan »)
fichier = "Base_Nettoyee.xlsx"
df = pd.read_excel(fichier, sheet_name='Donnees')
bilan_nettoyage = pd.read_excel(fichier, sheet_name='Bilan').set_index('Indicateur')['Valeur']
lignes_depart = int(bilan_nettoyage["Lignes au départ"])

# 2. Créer le fichier de statistiques
with pd.ExcelWriter("Base_Statistiques.xlsx", engine='openpyxl') as writer:

    # --- Tableau 1 : Bilan du nettoyage ---
    bilan = pd.DataFrame({
        "Indicateur": ["Lignes au départ", "Lignes après nettoyage", "Tests one-shot marqués", "Personnes < 60 ans marquées"],
        "Valeur": [lignes_depart, len(df), (df['one_shot_pro'] == 'OUI').sum(), (df['moins_60_ans'] == 'OUI').sum()]
    })
    bilan.to_excel(writer, sheet_name='1_Bilan', index=False)

    # --- Tableau 2 : Répartition par modalité ---
    # On remplace les codes par des noms lisibles
    df['modalite_lisible'] = df['saisie'].map({
        'participant': 'Auto-évaluation',
        'aide': 'Avec un aidant',
        'professionnel': 'Par un professionnel'
    }).fillna(df['saisie'])

    modalite = df['modalite_lisible'].value_counts().reset_index()
    modalite.columns = ['Modalité', 'Nombre de tests']
    modalite['Pourcentage'] = (modalite['Nombre de tests'] / len(df) * 100).round(1)
    modalite.to_excel(writer, sheet_name='2_Modalites', index=False)

    # --- Tableau 3 : Répartition par année ---
    df['date_etape1'] = pd.to_datetime(df['date_etape1'], errors='coerce', format='mixed')
    df['annee'] = df['date_etape1'].dt.year
    annee = df['annee'].value_counts().sort_index().reset_index()
    annee.columns = ['Année', 'Nombre de tests']
    annee.to_excel(writer, sheet_name='3_Annees', index=False)

    # --- Tableau 4 : Répartition par sexe ---
    sexe = df['sexe'].value_counts().reset_index()
    sexe.columns = ['Sexe', 'Nombre']
    sexe.to_excel(writer, sheet_name='4_Sexe', index=False)

    # --- Tableau 5 : Statistiques d'âge ---
    age_stats = df['age_etape1'].describe().reset_index()
    age_stats.columns = ['Statistique', 'Valeur']
    age_stats.to_excel(writer, sheet_name='5_Age', index=False)

print("Fichier 'Base_Statistiques.xlsx' généré avec succès !")
