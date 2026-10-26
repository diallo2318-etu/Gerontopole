import os
import duckdb
import pandas as pd

# Partie 1 - Tâche J : l'âge des personnes suivies dans ICOPE, selon le territoire
# Demandé à la réunion du 16/10 : « la moyenne d'âge des personnes qui utilisent ICOPE, avec un écart type,
# et la majorité a entre tel âge et tel âge » ; « les moyennes d'âge des personnes suivies via ICOPE
# en fonction des territoires » (Centre Manche : des gens très âgés ?).

# 1. Ouvrir l'entrepôt (dans le dossier privé des données, jamais dans le dépôt)
dossier = os.path.expanduser(os.environ.get("DONNEES_ICOPE", "~/donnees_icope"))
con = duckdb.connect(os.path.join(dossier, "entrepot_icope.duckdb"), read_only=True)

# 2. Une ligne par personne : son premier test (mêmes règles que les tâches A à I)
#    On compte des personnes, pas des tests : quelqu'un testé 5 fois ne compte qu'une fois.
personnes = con.sql("""
    SELECT * FROM (
        SELECT *, row_number() OVER (PARTITION BY participant ORDER BY date_depistage, numero) AS rang
        FROM icope_depistage WHERE retenu AND NOT test_probable
    ) WHERE rang = 1
""").df()

noms_departements = {'14': '14 Calvados', '27': '27 Eure', '50': '50 Manche',
                     '61': '61 Orne', '76': '76 Seine-Maritime'}
personnes['departement'] = personnes['departement'].map(noms_departements).fillna(
    personnes['departement'].notna().map({True: 'Hors Normandie', False: 'Non renseigné'}))
personnes['site'] = personnes['experimentation'].fillna('Hors sites')
personnes['modalite'] = personnes['modalite'].fillna('Non renseigné')
personnes['en_alerte'] = personnes['nb_alertes'] >= 1

# 3. Décrire l'âge d'un groupe de personnes
#    Moins de 30 personnes : les chiffres restent vides (trop peu pour être fiables, comme en tâche B).
def decrire_age(groupe):
    ligne = {'Personnes': len(groupe)}
    if len(groupe) < 30:
        return ligne
    age = groupe['age']
    ligne.update({
        'Âge moyen': round(age.mean(), 1),
        'Écart type': round(age.std(), 1),
        'Âge médian': age.median(),
        'La moitié a entre (1er quartile)': age.quantile(0.25),
        'et (3e quartile)': age.quantile(0.75),
        '8 sur 10 ont entre (10e centile)': age.quantile(0.10),
        'et (90e centile)': age.quantile(0.90),
        'Moins de 60 ans (%)': round((age < 60).mean() * 100, 1),
        '80 ans et plus (%)': round((age >= 80).mean() * 100, 1)
    })
    return ligne

def par_groupe(colonne, titre, df=personnes):
    lignes = [{titre: valeur, **decrire_age(groupe)} for valeur, groupe in df.groupby(colonne)]
    tableau = pd.DataFrame(lignes).sort_values('Personnes', ascending=False)
    return pd.concat([tableau, pd.DataFrame([{titre: 'Ensemble', **decrire_age(df)}])], ignore_index=True)

# 4. Ensemble des personnes, et personnes en alerte
ensemble = pd.DataFrame([{'Groupe': 'Toutes les personnes', **decrire_age(personnes)},
                         {'Groupe': 'Personnes en alerte au premier test', **decrire_age(personnes[personnes['en_alerte']])}])

# 5. Par département et par site d'expérimentation
par_departement = par_groupe('departement', 'Département')
par_site = par_groupe('site', "Site d'expérimentation")

# 6. Par site et modalité du test : l'âge vient-il du territoire ou de qui fait le test ?
lignes = []
for (site, modalite), groupe in personnes.groupby(['site', 'modalite']):
    lignes.append({"Site d'expérimentation": site, 'Modalité du test': modalite, **decrire_age(groupe)})
site_modalite = pd.DataFrame(lignes).sort_values(["Site d'expérimentation", 'Personnes'], ascending=[True, False])

# 7. Sauvegarder (dans le dossier des données)
fichier_sortie = os.path.join(dossier, "Partie1_J_Age_Territoires.xlsx")
with pd.ExcelWriter(fichier_sortie, engine='openpyxl') as writer:
    ensemble.to_excel(writer, sheet_name='1_Ensemble', index=False)
    par_departement.to_excel(writer, sheet_name='2_Par_departement', index=False)
    par_site.to_excel(writer, sheet_name='3_Par_site', index=False)
    site_modalite.to_excel(writer, sheet_name='4_Site_et_modalite', index=False)

pd.set_option('display.width', 250)
pd.set_option('display.max_columns', 20)
for titre, tableau in [('ENSEMBLE', ensemble), ('PAR DÉPARTEMENT', par_departement),
                       ('PAR SITE', par_site), ('SITE ET MODALITÉ', site_modalite)]:
    print(f"\n--- {titre} ---")
    print(tableau.to_string(index=False))
print(f"\n✅ Fichier '{fichier_sortie}' généré avec succès !")
