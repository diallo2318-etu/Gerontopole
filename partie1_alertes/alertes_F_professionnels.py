import os
import duckdb
import pandas as pd

# Partie 1 - Tâche F : quels professionnels traitent les alertes, et où
# Demandé par Marine (mail du 17/10 et réunion du 16/10) : par quel pro, quel profil,
# où ils travaillent, dispersés ou en collectif, et où il faudrait mettre en place des choses.
# Aucun identifiant ni nom de professionnel n'est écrit dans le fichier.

# 1. Ouvrir l'entrepôt (dans le dossier privé des données, jamais dans le dépôt)
dossier = os.path.expanduser(os.environ.get("DONNEES_ICOPE", "~/donnees_icope"))
con = duckdb.connect(os.path.join(dossier, "entrepot_icope.duckdb"), read_only=True)

# 2. Les actions sur les alertes (mêmes règles que les tâches A à D) et le professionnel qui les a faites
actions = con.sql("""
    SELECT t.id_traitement, t.id_alerte, t.id_auteur, t.departement AS departement_personne,
           p.profession, p.type_activite, p.type_etablissement, p.departement AS departement_pro,
           p.id_professionnel IS NOT NULL AS retrouve
    FROM icope_traitement t
    JOIN icope_depistage d USING (id_depistage)
    LEFT JOIN icope_professionnel p ON p.id_professionnel = t.id_auteur
    WHERE d.retenu AND NOT d.test_probable
""").df()

# Les professionnels inscrits sur ICOPE (export du 09/10/2026)
inscrits = con.sql("SELECT * FROM icope_professionnel").df()

# Les alertes analysées (tâche C), avec le département de la personne
alertes = con.sql("""
    SELECT v.id_alerte, v.departement, v.statut_alerte
    FROM v_alerte_issue v JOIN icope_depistage d USING (id_depistage)
    WHERE d.retenu AND NOT d.test_probable
""").df()

# 3. Valeurs lisibles
actions['profession'] = actions['profession'].fillna('Non retrouvé dans la liste des professionnels')
actions['type_activite'] = actions['type_activite'].fillna('Non retrouvé')
actions['type_etablissement'] = actions['type_etablissement'].fillna('Non retrouvé')
noms_departements = {'14': '14 Calvados', '27': '27 Eure', '50': '50 Manche',
                     '61': '61 Orne', '76': '76 Seine-Maritime'}

def departement_lisible(serie):
    return serie.map(noms_departements).fillna(serie.notna().map({True: 'Hors Normandie',
                                                                   False: 'Non renseigné'}))

actions['departement_pro'] = departement_lisible(actions['departement_pro'])
actions.loc[~actions['retrouve'], 'departement_pro'] = 'Non retrouvé'
alertes['departement'] = departement_lisible(alertes['departement'])
inscrits['departement'] = departement_lisible(inscrits['departement'])

# 4. Périmètre
pros_actifs = actions.groupby('id_auteur')['retrouve'].first()
perimetre = pd.DataFrame({
    "Indicateur": ["Professionnels ayant fait au moins une action",
                   "dont retrouvés dans la liste des professionnels ICOPE",
                   "dont non retrouvés (pas dans l'export du 09/10/2026)",
                   "Actions au total",
                   "Professionnels inscrits sur ICOPE",
                   "dont autorisés à gérer les alertes"],
    "Valeur": [len(pros_actifs), pros_actifs.sum(), (~pros_actifs).sum(), len(actions),
               len(inscrits), inscrits['gestion_alerte'].sum()]
})

# 5. Répartition selon une caractéristique du professionnel
def repartition(colonne, titre):
    tableau = actions.groupby(colonne).agg(
        professionnels=('id_auteur', 'nunique'),
        actions=('id_traitement', 'size'),
        alertes=('id_alerte', 'nunique')
    ).sort_values('actions', ascending=False).reset_index()
    tableau['Part des actions (%)'] = (tableau['actions'] / len(actions) * 100).round(1)
    tableau.columns = [titre, 'Professionnels', 'Actions', 'Alertes traitées', 'Part des actions (%)']
    return tableau

par_profession = repartition('profession', 'Profession')
par_activite = repartition('type_activite', "Type d'activité")
par_etablissement = repartition('type_etablissement', "Lieu d'exercice")
par_departement_pro = repartition('departement_pro', 'Département du professionnel')

# 6. Inscrits autorisés à gérer les alertes, comparés à ceux qui l'ont vraiment fait
autorises = inscrits[inscrits['gestion_alerte'] == True]
actifs = set(actions['id_auteur'])
inscrits_actifs = autorises.groupby('profession').agg(
    autorises=('id_professionnel', 'size'),
    actifs=('id_professionnel', lambda x: x.isin(actifs).sum())
).sort_values('autorises', ascending=False).reset_index()
inscrits_actifs['Part active (%)'] = (inscrits_actifs['actifs'] / inscrits_actifs['autorises'] * 100).round(1)
inscrits_actifs.columns = ['Profession', 'Inscrits autorisés à gérer les alertes',
                           'Ont traité au moins une alerte', 'Part active (%)']

# 7. Par département : alertes, alertes non traitées, professionnels disponibles et actifs
#    Pour repérer où il y a des professionnels qui pourraient traiter les alertes mais ne le font pas.
par_dep = alertes.groupby('departement').agg(
    alertes=('id_alerte', 'size'),
    non_traitees=('statut_alerte', lambda x: (x == 'non_traitee').sum())
)
par_dep['Non traitées (%)'] = (par_dep['non_traitees'] / par_dep['alertes'] * 100).round(1)
par_dep['Professionnels autorisés'] = autorises.groupby('departement').size()
actifs_dep = actions.drop_duplicates('id_auteur').groupby('departement_pro').size()
par_dep['Professionnels actifs'] = actifs_dep
par_dep = par_dep.fillna(0)
par_dep[['Professionnels autorisés', 'Professionnels actifs']] = par_dep[
    ['Professionnels autorisés', 'Professionnels actifs']].astype(int)
par_dep = par_dep.reset_index()
par_dep.columns = ['Département', 'Alertes', 'Alertes non traitées', 'Non traitées (%)',
                   'Professionnels autorisés à gérer les alertes', 'Professionnels ayant traité']
par_dep = par_dep[~par_dep['Département'].isin(['Hors Normandie', 'Non renseigné'])]

# 8. Concentration : le professionnel traite-t-il des personnes de son département ?
retrouves = actions[actions['retrouve']].copy()
retrouves['departement_personne'] = departement_lisible(retrouves['departement_personne'])
retrouves['meme_departement'] = retrouves['departement_personne'] == retrouves['departement_pro']
meme_dep = pd.DataFrame({
    'Indicateur': ["Actions sur une personne du même département que le professionnel",
                   "Actions sur une personne d'un autre département"],
    "Nombre d'actions": [retrouves['meme_departement'].sum(), (~retrouves['meme_departement']).sum()]
})
meme_dep['Pourcentage (%)'] = (meme_dep["Nombre d'actions"] / len(retrouves) * 100).round(1)

# 9. Sauvegarder (dans le dossier des données)
fichier_sortie = os.path.join(dossier, "Partie1_F_Professionnels.xlsx")
with pd.ExcelWriter(fichier_sortie, engine='openpyxl') as writer:
    perimetre.to_excel(writer, sheet_name='1_Perimetre', index=False)
    par_profession.to_excel(writer, sheet_name='2_Profession', index=False)
    par_activite.to_excel(writer, sheet_name='3_Activite', index=False)
    par_etablissement.to_excel(writer, sheet_name='4_Lieu_exercice', index=False)
    par_departement_pro.to_excel(writer, sheet_name='5_Departement_pro', index=False)
    meme_dep.to_excel(writer, sheet_name='6_Meme_departement', index=False)
    inscrits_actifs.to_excel(writer, sheet_name='7_Inscrits_vs_actifs', index=False)
    par_dep.to_excel(writer, sheet_name='8_Territoires', index=False)

for titre, tableau in [('PÉRIMÈTRE', perimetre), ('PROFESSION', par_profession),
                       ("TYPE D'ACTIVITÉ", par_activite), ("LIEU D'EXERCICE", par_etablissement),
                       ('DÉPARTEMENT DU PRO', par_departement_pro), ('MÊME DÉPARTEMENT', meme_dep),
                       ('INSCRITS VS ACTIFS', inscrits_actifs), ('TERRITOIRES', par_dep)]:
    print(f"\n--- {titre} ---")
    print(tableau.to_string(index=False))
print(f"\n✅ Fichier '{fichier_sortie}' généré avec succès !")
