import pandas as pd
import glob

# 1. On cherche automatiquement le fichier Excel qui commence par "bdi_etape1"
fichiers = glob.glob("bdi_etape1_*.xlsx")
if not fichiers:
    print("ERREUR : Je ne trouve pas le fichier Excel dans le dossier.")
else:
    fichier_source = fichiers[0]
    print(f"--- Analyse du fichier : {fichier_source} ---")

    # 2. On lit le fichier Excel
    df = pd.read_excel(fichier_source)
    
    # 3. On prépare le rapport
    resultats = []
    for col in df.columns:
        nb_vides = df[col].isna().sum()
        pct_vides = (nb_vides / len(df)) * 100
        resultats.append({
            "Colonne": col,
            "Valeurs manquantes": nb_vides,
            "Pourcentage manquant": round(pct_vides, 2)
        })

    # 4. On crée et sauvegarde le rapport Excel
    rapport = pd.DataFrame(resultats)
    rapport = rapport.sort_values(by="Pourcentage manquant", ascending=False)
    rapport.to_excel("Rapport_Audit_Qualite.xlsx", index=False)
    
    print("✅ Le fichier 'Rapport_Audit_Qualite.xlsx' a été créé avec succès !")