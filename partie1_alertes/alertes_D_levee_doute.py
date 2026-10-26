import os
import duckdb
import pandas as pd

# Partie 1 - Tâche D : la levée de doute et l'orientation

# 1. Ouvrir l'entrepôt (dans le dossier privé des données, jamais dans le dépôt)
dossier = os.path.expanduser(os.environ.get("DONNEES_ICOPE", "~/donnees_icope"))
con = duckdb.connect(os.path.join(dossier, "entrepot_icope.duckdb"), read_only=True)

# 2. Charger les actions menées sur les alertes (ICOPE parle de « traitements »)
#    Mêmes règles que les tâches A, B, C : tests retenus, sans les essais probables.
#    Les alertes du test (alerte_vision...) viennent de icope_depistage.
actions = con.sql("""
    SELECT t.* EXCLUDE (alerte_cognition, alerte_nutrition, alerte_vision, alerte_audition,
                        alerte_psychologie, alerte_mobilite, alerte_social, alerte_aidant,
                        alerte_incontinence),
           d.alerte_cognition, d.alerte_nutrition, d.alerte_vision, d.alerte_audition,
           d.alerte_psychologie, d.alerte_mobilite, d.alerte_social, d.alerte_aidant,
           d.alerte_incontinence
    FROM icope_traitement t
    JOIN icope_depistage d USING (id_depistage)
    WHERE d.retenu AND NOT d.test_probable
""").df()

nb_alertes_analysees = con.sql("""
    SELECT count(*) FROM v_alerte_issue v JOIN icope_depistage d USING (id_depistage)
    WHERE d.retenu AND NOT d.test_probable
""").fetchone()[0]

noms_domaines = {
    'cognition': 'Cognition', 'nutrition': 'Nutrition', 'vision': 'Vision',
    'audition': 'Audition', 'psychologie': 'Psychologie', 'mobilite': 'Mobilité',
    'social': 'Social', 'aidant': 'Aidant', 'incontinence': 'Incontinence'
}

# 3. Résumer par alerte : une alerte peut avoir plusieurs actions.
#    Une case est « oui » pour l'alerte si au moins une de ses actions l'a cochée.
cases = [c for c in actions.columns if c.startswith(('veracite_', 'prise_en_charge_', 'orientation_',
                                                     'pas_orientation_', 'fausse_alerte_', 'distance_'))]
cases += ['orientations_proposees']
#    Une case vide compte comme « non ».
for c in cases:
    actions[c] = actions[c] == True
for code in noms_domaines:
    actions['alerte_' + code] = actions['alerte_' + code] == True

par_alerte = actions.groupby('id_alerte').agg(
    nb_actions=('id_traitement', 'size'),
    **{c: (c, 'max') for c in cases},
    **{'alerte_' + code: ('alerte_' + code, 'max') for code in noms_domaines},
    vraie=('veracite', lambda x: (x == 'alerte_vraie').any()),
    fausse=('veracite', lambda x: (x == 'alerte_fausse').any()),
    non_verifiable=('veracite', lambda x: (x == 'alerte_non_verifiable').any())
).reset_index()

def resultat_levee(row):
    if row['vraie']:
        return 'Alerte vraie (confirmée)'
    elif row['fausse']:
        return 'Fausse alerte'
    elif row['non_verifiable']:
        return 'Alerte non vérifiable'
    else:
        return 'Levée de doute non renseignée'

par_alerte['levee_doute'] = par_alerte.apply(resultat_levee, axis=1)

# 4. Périmètre
perimetre = pd.DataFrame({
    "Indicateur": ["Alertes analysées (tâche C)", "Alertes avec au moins une action",
                   "Actions au total", "Professionnels ayant fait au moins une action"],
    "Valeur": [nb_alertes_analysees, len(par_alerte), len(actions), actions['id_auteur'].nunique()]
})

nb_actions = par_alerte['nb_actions'].value_counts().sort_index().reset_index()
nb_actions.columns = ["Nombre d'actions sur l'alerte", "Nombre d'alertes"]
nb_actions['Pourcentage (%)'] = (nb_actions["Nombre d'alertes"] / len(par_alerte) * 100).round(1)

# 5. Résultat de la levée de doute
levee = par_alerte['levee_doute'].value_counts().reset_index()
levee.columns = ['Résultat de la levée de doute', "Nombre d'alertes"]
levee['Pourcentage (%)'] = (levee["Nombre d'alertes"] / len(par_alerte) * 100).round(1)

# 6. Confirmation domaine par domaine
#    Parmi les alertes confirmées vraies : chaque domaine en alerte au test a-t-il été confirmé ?
vraies = par_alerte[par_alerte['vraie']]
lignes = []
for code, nom in noms_domaines.items():
    en_alerte = vraies[vraies['alerte_' + code]]
    confirmes = en_alerte['veracite_' + code].sum()
    lignes.append({
        'Domaine': nom,
        'Alertes vraies avec ce domaine au test': len(en_alerte),
        'Domaine confirmé': confirmes,
        'Domaine confirmé (%)': round(confirmes / len(en_alerte) * 100, 1) if len(en_alerte) >= 30 else None,
        'Domaine confirmé alors qu\'il n\'était pas en alerte au test':
            vraies[~vraies['alerte_' + code]]['veracite_' + code].sum()
    })
confirmation = pd.DataFrame(lignes).sort_values('Alertes vraies avec ce domaine au test', ascending=False)

# 7. Comment la personne a été contactée (par action)
noms_contacts = {
    'distance_contact_participant': 'Contact avec la personne',
    'distance_contact_medecin': 'Contact avec le médecin',
    'distance_contact_autre': 'Contact avec une autre personne',
    'distance_recherche_dossier': 'Recherche dans le dossier',
    'distance_autre': 'Autre',
    'distance_participant_non_joignable': 'Personne non joignable'
}
moment = actions['modalites_orientation'].map({'a-distance': 'À distance (plus tard)',
                                               'de-suite': 'Tout de suite (pendant le test)'})
moment = moment.fillna('Non renseigné').value_counts().reset_index()
moment.columns = ["Moment de l'action", "Nombre d'actions"]
moment['Pourcentage (%)'] = (moment["Nombre d'actions"] / len(actions) * 100).round(1)

contacts = pd.DataFrame({
    'Moyen utilisé (action à distance)': list(noms_contacts.values()),
    "Nombre d'actions": [actions[c].sum() for c in noms_contacts]
}).sort_values("Nombre d'actions", ascending=False)

# 8. Orientations, raisons de non-orientation, fausses alertes (par alerte)
def compter(noms, titre):
    tableau = pd.DataFrame({
        titre: list(noms.values()),
        "Nombre d'alertes": [par_alerte[c].sum() for c in noms]
    }).sort_values("Nombre d'alertes", ascending=False)
    tableau['Pourcentage des alertes avec action (%)'] = (
        tableau["Nombre d'alertes"] / len(par_alerte) * 100).round(1)
    return tableau

orientations = compter({
    'orientation_rdv_medecin': 'Rendez-vous chez le médecin',
    'orientation_contact_medecin': 'Contact avec le médecin',
    'orientation_oriente_etape2': "Orientée vers l'étape 2",
    'orientation_fait_etape2': 'Étape 2 faite',
    'orientation_structure_hospitaliere': 'Structure hospitalière',
    'orientation_infos': 'Informations données',
    'orientation_autre': 'Autre'
}, 'Orientation proposée')

pas_orientation = compter({
    'pas_orientation_domaines_deja_pris_en_charge': 'Déjà prise en charge',
    'pas_orientation_pas_necessaire': 'Pas nécessaire',
    'pas_orientation_refus': 'Refus de la personne',
    'pas_orientation_autres': 'Autre raison'
}, 'Raison de non-orientation')

fausses = compter({
    'fausse_alerte_erreur_test': 'Erreur pendant le test',
    'fausse_alerte_erreur_saisie': 'Erreur de saisie',
    'fausse_alerte_pb_info': "Problème d'information",
    'fausse_alerte_autres': 'Autre'
}, 'Raison de la fausse alerte')

# 9. Domaines déjà pris en charge
#    Parmi les alertes où une prise en charge existante est signalée
connues = par_alerte[par_alerte['prise_en_charge_connue']]
lignes = []
for code, nom in noms_domaines.items():
    en_alerte = connues[connues['alerte_' + code]]
    deja = en_alerte['prise_en_charge_' + code].sum()
    lignes.append({
        'Domaine': nom,
        'Alertes avec ce domaine au test': len(en_alerte),
        'Déjà pris en charge': deja,
        'Déjà pris en charge (%)': round(deja / len(en_alerte) * 100, 1) if len(en_alerte) >= 30 else None
    })
deja_pris = pd.DataFrame(lignes).sort_values('Alertes avec ce domaine au test', ascending=False)

# 10. Qui fait les actions : répartition entre professionnels (anonymes)
par_pro = actions.groupby('id_auteur').agg(
    actions=('id_traitement', 'size'),
    alertes=('id_alerte', 'nunique')
).sort_values('actions', ascending=False).reset_index(drop=True)
par_pro.insert(0, 'Professionnel', ['Professionnel ' + str(i + 1) for i in range(len(par_pro))])
par_pro['Part des actions (%)'] = (par_pro['actions'] / par_pro['actions'].sum() * 100).round(1)
par_pro['Part cumulée (%)'] = par_pro['Part des actions (%)'].cumsum().round(1)
par_pro.columns = ['Professionnel', "Nombre d'actions", "Nombre d'alertes", 'Part des actions (%)',
                   'Part cumulée (%)']

# 11. Sauvegarder (dans le dossier des données)
fichier_sortie = os.path.join(dossier, "Partie1_D_Levee_Doute_Orientation.xlsx")
with pd.ExcelWriter(fichier_sortie, engine='openpyxl') as writer:
    perimetre.to_excel(writer, sheet_name='1_Perimetre', index=False)
    nb_actions.to_excel(writer, sheet_name='2_Nb_actions', index=False)
    levee.to_excel(writer, sheet_name='3_Levee_doute', index=False)
    confirmation.to_excel(writer, sheet_name='4_Confirmation_domaine', index=False)
    moment.to_excel(writer, sheet_name='5_Moment', index=False)
    contacts.to_excel(writer, sheet_name='6_Contacts', index=False)
    orientations.to_excel(writer, sheet_name='7_Orientations', index=False)
    pas_orientation.to_excel(writer, sheet_name='8_Pas_orientation', index=False)
    fausses.to_excel(writer, sheet_name='9_Fausses_alertes', index=False)
    deja_pris.to_excel(writer, sheet_name='10_Deja_pris_en_charge', index=False)
    par_pro.to_excel(writer, sheet_name='11_Professionnels', index=False)

for titre, tableau in [('PÉRIMÈTRE', perimetre), ("NOMBRE D'ACTIONS", nb_actions),
                       ('LEVÉE DE DOUTE', levee), ('CONFIRMATION PAR DOMAINE', confirmation),
                       ('MOMENT', moment), ('CONTACTS', contacts), ('ORIENTATIONS', orientations),
                       ('PAS ORIENTATION', pas_orientation), ('FAUSSES ALERTES', fausses),
                       ('DÉJÀ PRIS EN CHARGE', deja_pris), ('PROFESSIONNELS (top 10)', par_pro.head(10))]:
    print(f"\n--- {titre} ---")
    print(tableau.to_string(index=False))
print(f"\n✅ Fichier '{fichier_sortie}' généré avec succès !")
