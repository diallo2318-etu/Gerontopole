"""Avant / après 2025 : l'âge et la modalité des tests ont-ils changé ? Voit-on l'effet de la campagne Carsat ?

À lancer après nettoyage.py (lit Base_Nettoyee.xlsx).
Produit : Analyse_Avant_Apres_2025.xlsx
"""
import pandas as pd
from scipy.stats import chi2_contingency, mannwhitneyu

# Date de la campagne Carsat, si on la connaît (ex. "2025-03-01") : les tests sont alors comparés
# avant / après cette date. Laisser None tant qu'on ne l'a pas.
DATE_CAMPAGNE_CARSAT = None

df = pd.read_excel("Base_Nettoyee.xlsx", sheet_name='Donnees')
# Les essais probables (moins de 50 ans) sont exclus, comme dans la partie 1
total_tests = len(df)
if 'essai_probable' in df:
    df = df[df['essai_probable'] != 'OUI'].copy()
perimetre = pd.DataFrame({'Indicateur': ["Tests de la base nettoyée", "Essais probables exclus (moins de 50 ans)", "Tests analysés"],
                          'Valeur': [total_tests, total_tests - len(df), len(df)]})
print(f"Tests analysés : {len(df)} (sur {total_tests}, essais probables de moins de 50 ans exclus)")
df['date_etape1'] = pd.to_datetime(df['date_etape1'], errors='coerce', format='mixed')
df['age_etape1'] = pd.to_numeric(df['age_etape1'], errors='coerce')
df['periode'] = df['date_etape1'].dt.year.map(lambda a: 'Avant 2025' if a < 2025 else '2025 et après')
df.loc[df['date_etape1'].isna(), 'periode'] = 'Date inconnue'
df['modalite'] = df['saisie'].map({'participant': 'Auto-évaluation', 'aide': 'Avec un aidant',
                                   'professionnel': 'Par un professionnel'}).fillna('Non renseigné')
comparables = df[df['periode'] != 'Date inconnue']
avant = comparables[comparables['periode'] == 'Avant 2025']
apres = comparables[comparables['periode'] == '2025 et après']

# 1. Âge
age = comparables.groupby('periode')['age_etape1'].agg(['count', 'mean', 'std', 'median', 'min', 'max']).round(1)
age = age.reindex(['Avant 2025', '2025 et après']).reset_index()
age.columns = ['Période', 'Tests', 'Âge moyen', 'Écart-type', 'Âge médian', 'Âge minimum', 'Âge maximum']
a, b = avant['age_etape1'].dropna(), apres['age_etape1'].dropna()
p_age = mannwhitneyu(a, b).pvalue if len(a) and len(b) else None
age_test = pd.DataFrame({'Test': ["Mann-Whitney (l'âge est-il différent ?)"],
                         'p-valeur': [round(p_age, 4) if p_age is not None else None],
                         'Différence significative (p < 0,05)': ['OUI' if p_age is not None and p_age < 0.05 else 'NON']})

# 2. Qui fait le test : seul, avec un aidant, ou un professionnel
tableau = pd.crosstab(comparables['modalite'], comparables['periode'])
tableau = tableau.reindex(columns=['Avant 2025', '2025 et après'], fill_value=0)
modalite = tableau.copy()
for col in tableau.columns:
    modalite[f'{col} (%)'] = (tableau[col] / tableau[col].sum() * 100).round(1)
modalite = modalite.rename_axis('Modalité').reset_index()
p_mod = chi2_contingency(tableau)[1] if tableau.shape[0] > 1 and (tableau.sum() > 0).all() else None
modalite_test = pd.DataFrame({'Test': ['Khi-deux (la modalité est-elle différente ?)'],
                              'p-valeur': [round(p_mod, 4) if p_mod is not None else None],
                              'Différence significative (p < 0,05)': ['OUI' if p_mod is not None and p_mod < 0.05 else 'NON']})

# 3. Tests mois par mois, par modalité : un pic peut montrer l'effet d'une campagne
df['mois'] = df['date_etape1'].dt.to_period('M').astype(str)
par_mois = pd.crosstab(df.loc[df['date_etape1'].notna(), 'mois'], df.loc[df['date_etape1'].notna(), 'modalite'])
par_mois['Total'] = par_mois.sum(axis=1)
par_mois = par_mois.rename_axis('Mois').reset_index()

# 4. Carsat : tests où « carsat » apparaît dans la source, les tags ou le centre
colonnes = [c for c in ['source', 'tags', 'centre'] if c in df.columns]
df['mention_carsat'] = False
for c in colonnes:
    df['mention_carsat'] |= df[c].astype(str).str.contains('carsat', case=False, na=False)
carsat = df.groupby('periode').agg(tests=('mention_carsat', 'size'), mention_carsat=('mention_carsat', 'sum')).reset_index()
carsat['Mention Carsat (%)'] = (carsat['mention_carsat'] / carsat['tests'] * 100).round(1)
carsat.columns = ['Période', 'Tests', 'Tests mentionnant la Carsat', 'Mention Carsat (%)']
valeurs_carsat = pd.concat([df.loc[df[c].astype(str).str.contains('carsat', case=False, na=False), c]
                            .value_counts().rename_axis('Valeur').reset_index(name='Tests').assign(Colonne=c)
                            for c in colonnes], ignore_index=True)

# 5. Avant / après la campagne Carsat, si sa date est connue
feuilles = [('0_Perimetre', [perimetre]), ('1_Age', [age, age_test]), ('2_Modalite', [modalite, modalite_test]), ('3_Par_mois', [par_mois]),
            ('4_Carsat', [carsat, valeurs_carsat])]
if DATE_CAMPAGNE_CARSAT:
    debut = pd.Timestamp(DATE_CAMPAGNE_CARSAT)
    df['campagne'] = df['date_etape1'].map(lambda d: 'Avant la campagne' if d < debut else 'Après la campagne')
    campagne = df[df['date_etape1'].notna()].groupby('campagne').agg(
        tests=('participant', 'size'), age_moyen=('age_etape1', 'mean'),
        auto_evaluation=('modalite', lambda m: (m == 'Auto-évaluation').mean() * 100)).round(1).reset_index()
    campagne.columns = ['Période', 'Tests', 'Âge moyen', 'Auto-évaluation (%)']
    feuilles.append(('5_Campagne_Carsat', [campagne]))

with pd.ExcelWriter("Analyse_Avant_Apres_2025.xlsx", engine='openpyxl') as writer:
    for onglet, tableaux in feuilles:
        ligne = 0
        for t in tableaux:
            t.to_excel(writer, sheet_name=onglet, index=False, startrow=ligne)
            ligne += len(t) + 2
        print(f"\n--- {onglet} ---")
        for t in tableaux:
            print(t.to_string(index=False))

if not DATE_CAMPAGNE_CARSAT:
    print("\n(Date de la campagne Carsat inconnue : regarder l'onglet 3_Par_mois pour repérer un pic, "
          "puis renseigner DATE_CAMPAGNE_CARSAT en haut du script.)")
print("\n✅ Fichier 'Analyse_Avant_Apres_2025.xlsx' généré avec succès !")
