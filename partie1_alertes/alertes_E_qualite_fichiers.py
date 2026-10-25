import os
import glob
import pandas as pd

# Partie 1 - Tâche E : qualité des fichiers alertes et traitements (données manquantes par variable)
# On lit ici les fichiers bruts envoyés par Marine, pas l'entrepôt : c'est leur qualité qu'on mesure.
# Le script ne fait que COMPTER : aucun contenu (noms, dates de naissance, commentaires) n'est écrit.

# 1. Trouver les fichiers dans le dossier privé des données
dossier = os.path.expanduser(os.environ.get("DONNEES_ICOPE", "~/donnees_icope"))
fichier_alertes = sorted(glob.glob(os.path.join(dossier, "bdi_alertes_*.xlsx")))[-1]
fichier_traitements = sorted(glob.glob(os.path.join(dossier, "bdi_traitements_alertes_*.xlsx")))[-1]

# 2. Colonnes sensibles : jamais chargées dans l'entrepôt (décision du 16/10)
sensibles = ['ddn', 'mt_nom', 'mt_ville', 'commentaires', 'nom_auteur_prise_en_charge', 'centre']

# 3. Vides « normaux » : la question ne concerne pas tout le monde
explications = {
    'alerte_audition': "Souvent sautée en auto-évaluation (voir tâche A)",
    'alerte_social': "Question ajoutée en mars 2026 (version 4)",
    'alerte_incontinence': "Question ajoutée en mars 2026 (version 4)",
    'alerte_aidant': "Question ajoutée en mars 2026, posée seulement aux aidants",
    'date_prise_en_charge': "Vide quand l'alerte n'est pas prise en charge",
    'modalites_orientation': "Non renseigné par le professionnel",
    'veracite': "Levée de doute non renseignée",
    'prise_en_charge_connue': "Rempli seulement si l'alerte est vraie",
    'orientations_proposees': "Rempli seulement si l'alerte est vraie",
    'commentaires': "Champ libre facultatif",
    'mt_nom': "Vide si pas de médecin traitant ou non renseigné",
    'mt_ville': "Vide si pas de médecin traitant ou non renseigné",
}
prefixes = {
    'distance_': "Rempli seulement pour une action à distance",
    'veracite_': "Rempli seulement si l'alerte est vraie (domaines confirmés)",
    'prise_en_charge_': "Rempli seulement si une prise en charge existante est signalée",
    'orientation_': "Rempli seulement si des orientations sont proposées",
    'pas_orientation_': "Rempli seulement s'il n'y a pas d'orientation",
    'fausse_alerte_': "Rempli seulement si c'est une fausse alerte",
}

def expliquer(colonne):
    if colonne in explications:
        return explications[colonne]
    for prefixe, texte in prefixes.items():
        if colonne.startswith(prefixe):
            return texte
    return ''

# 4. Compter les données manquantes : cases vides + code « dm » (donnée manquante d'ICOPE)
def audit(fichier):
    df = pd.read_excel(fichier)
    lignes = []
    for col in df.columns:
        vides = df[col].isna().sum()
        dm = (df[col].astype(str).str.strip().str.lower() == 'dm').sum()
        manquants = vides + dm
        lignes.append({
            'Colonne': col,
            'Cases vides': vides,
            'Code « dm »': dm,
            'Total manquant': manquants,
            'Pourcentage manquant (%)': round(manquants / len(df) * 100, 1),
            'Explication du manque': expliquer(col) if manquants > 0 else '',
            'Sensible (pas dans l\'entrepôt)': 'OUI' if col in sensibles else ''
        })
    return df, pd.DataFrame(lignes)

alertes, audit_alertes = audit(fichier_alertes)
traitements, audit_traitements = audit(fichier_traitements)

# 5. Résumé
def resume(nom, df, tableau):
    return {
        'Fichier': nom,
        'Lignes': len(df),
        'Colonnes': len(df.columns),
        'Colonnes complètes': (tableau['Total manquant'] == 0).sum(),
        'Colonnes avec des manques': (tableau['Total manquant'] > 0).sum(),
        'Dont manques expliqués (question non concernée)': ((tableau['Total manquant'] > 0)
                                                           & (tableau['Explication du manque'] != '')).sum(),
        'Colonnes sensibles': (tableau["Sensible (pas dans l'entrepôt)"] == 'OUI').sum()
    }

resume_fichiers = pd.DataFrame([
    resume(os.path.basename(fichier_alertes), alertes, audit_alertes),
    resume(os.path.basename(fichier_traitements), traitements, audit_traitements)
])

# 6. Sauvegarder (dans le dossier des données)
fichier_sortie = os.path.join(dossier, "Partie1_E_Qualite_Fichiers.xlsx")
with pd.ExcelWriter(fichier_sortie, engine='openpyxl') as writer:
    resume_fichiers.to_excel(writer, sheet_name='1_Resume', index=False)
    audit_alertes.to_excel(writer, sheet_name='2_Fichier_alertes', index=False)
    audit_traitements.to_excel(writer, sheet_name='3_Fichier_traitements', index=False)

print("--- RÉSUMÉ ---")
print(resume_fichiers.T.to_string(header=False))
print("\n--- FICHIER ALERTES (colonnes avec des manques) ---")
print(audit_alertes[audit_alertes['Total manquant'] > 0].to_string(index=False))
print("\n--- FICHIER TRAITEMENTS (colonnes avec des manques) ---")
print(audit_traitements[audit_traitements['Total manquant'] > 0].to_string(index=False))
print(f"\n✅ Fichier '{fichier_sortie}' généré avec succès !")
