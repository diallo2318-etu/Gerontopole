"""Colonne « tags » : les tests orientés par les CFPPA (tag « la Poste CFPPA France »).

À lancer après nettoyage.py (lit Base_Nettoyee.xlsx).
Produit : Analyse_Tags_CFPPA.xlsx
"""
import pandas as pd

df = pd.read_excel("Base_Nettoyee.xlsx", sheet_name='Donnees')
bilan_nettoyage = pd.read_excel("Base_Nettoyee.xlsx", sheet_name='Bilan').set_index('Indicateur')['Valeur']
# Nombre de tests CFPPA dans l'export brut (avant la suppression des doublons du même jour)
brut = pd.read_excel(bilan_nettoyage["Fichier source"], dtype=str, usecols=['participant', 'tags'])
cfppa_brut = int(brut['tags'].str.contains('cfppa', case=False, na=False).sum())
df['date_etape1'] = pd.to_datetime(df['date_etape1'], errors='coerce', format='mixed')
df['age_etape1'] = pd.to_numeric(df['age_etape1'], errors='coerce')
df['tags'] = df['tags'].astype('string').str.strip()

# 1. Tous les tags rencontrés
tags = df['tags'].fillna('(aucun tag)').value_counts().rename_axis('Tag').reset_index(name='Nombre de tests')

# 2. Les tests CFPPA
df['cfppa'] = df['tags'].str.contains('cfppa', case=False, na=False)
cfppa = df[df['cfppa']].copy()
ecart = cfppa_brut - len(cfppa)
print(f"Tests avec un tag CFPPA : {cfppa_brut} dans l'export brut, {len(cfppa)} après le nettoyage"
      + (f" ({ecart} retiré{'s' if ecart > 1 else ''} : doublon du même jour, le test gardé est le dernier, sans le tag)" if ecart else ""))
comptage = pd.DataFrame({'Indicateur': ["Tests CFPPA dans l'export brut", "Tests CFPPA après nettoyage",
                                        "Écart (doublons du même jour : le test gardé est le dernier du jour)"],
                         'Nombre': [cfppa_brut, len(cfppa), ecart]})

# 3. Description des tests CFPPA, comparés aux autres
def decrire(g, nom):
    alertes = pd.to_numeric(g.get('nb_alertes'), errors='coerce') if 'nb_alertes' in g else pd.Series(dtype=float)
    return {'Groupe': nom, 'Tests': len(g), 'Personnes': g['participant'].nunique(),
            'Âge moyen': round(g['age_etape1'].mean(), 1), 'Âge médian': g['age_etape1'].median(),
            'Femmes (%)': round((g['sexe'] == 'feminin').mean() * 100, 1),
            'Auto-évaluation (%)': round((g['saisie'] == 'participant').mean() * 100, 1),
            'Par un professionnel (%)': round((g['saisie'] == 'professionnel').mean() * 100, 1),
            "Nombre moyen d'alertes": round(alertes.mean(), 2) if len(alertes) else None,
            'Premier test': g['date_etape1'].min(), 'Dernier test': g['date_etape1'].max()}

comparaison = pd.DataFrame([decrire(cfppa, 'Tests CFPPA'), decrire(df[~df['cfppa']], 'Autres tests')])

# 4. Quand et où
par_mois = cfppa['date_etape1'].dt.to_period('M').astype(str).value_counts().sort_index()
par_mois = par_mois.rename_axis('Mois').reset_index(name='Tests CFPPA')
par_dep = cfppa['cp'].astype(str).str[:2].value_counts().rename_axis('Département').reset_index(name='Tests CFPPA')

with pd.ExcelWriter("Analyse_Tags_CFPPA.xlsx", engine='openpyxl') as writer:
    comptage.to_excel(writer, sheet_name='0_Comptage', index=False)
    tags.to_excel(writer, sheet_name='1_Tous_les_tags', index=False)
    comparaison.to_excel(writer, sheet_name='2_CFPPA_vs_autres', index=False)
    par_mois.to_excel(writer, sheet_name='3_Par_mois', index=False)
    par_dep.to_excel(writer, sheet_name='4_Par_departement', index=False)

print("\n--- Tags ---\n" + tags.to_string(index=False))
print("\n--- CFPPA comparés aux autres tests ---\n" + comparaison.to_string(index=False))
print("\n✅ Fichier 'Analyse_Tags_CFPPA.xlsx' généré avec succès !")
