"""Partie 1 - 2. Le devenir des alertes : sont-elles prises en charge ? Levée de doute, orientation ?
Où, par qui et quand ? Les fichiers d'alertes sont-ils fiables ?

Demandé : liste des tâches du 20/10 (alertes traitées / non traitées, 3 sites / hors sites),
réunion du 16/10 et mails de Marine (17/10, novembre : où, par qui, quand, l'orientation est-elle précisée ?).
Produit : ~/donnees_icope/Partie1_2_Devenir_des_alertes.xlsx
Attention : l'onglet OQQ_Qui contient le nom des professionnels (demandé par Marine) ; ce fichier ne doit
circuler qu'avec le Gérontopôle, jamais sur GitHub.
"""
import glob
import os

import pandas as pd

from commun import (DOMAINES, DOSSIER, actions_analysees, alertes_analysees, classe_age, connecter,
                    departement_lisible, ecrire_excel, khi2, lire, pct, site_lisible)

ALERTES_DU_TEST = ", ".join(f"d.alerte_{d}" for d in DOMAINES)
ORIENTATIONS_PRECISES = ['orientation_rdv_medecin', 'orientation_contact_medecin', 'orientation_oriente_etape2',
                         'orientation_fait_etape2', 'orientation_structure_hospitaliere']


def dernier_export(motif):
    return sorted(glob.glob(os.path.join(DOSSIER, motif)))[-1]


def devenir(con):
    """Que deviennent les alertes, et en combien de temps ?"""
    toutes = lire(con, f"""SELECT v.*, d.retenu, d.test_probable, d.modalite, {ALERTES_DU_TEST}
                           FROM v_alerte_issue v LEFT JOIN icope_depistage d USING (id_depistage)""")
    alertes = toutes[(toutes['retenu'] == True) & (toutes['test_probable'] == False)].copy()
    perimetre = pd.DataFrame({
        "Indicateur": ["Alertes au départ",
                       "Alertes sans test dans l'export étape 1",
                       "Alertes sur un test en doublon le même jour",
                       "Alertes sur un essai probable (moins de 50 ans)", "Alertes analysées", "Personnes concernées"],
        "Valeur": [len(toutes), toutes['retenu'].isna().sum(), (toutes['retenu'] == False).sum(),
                   ((toutes['retenu'] == True) & (toutes['test_probable'] == True)).sum(),
                   len(alertes), alertes['participant'].nunique()]})

    alertes['prise_en_charge'] = alertes['statut_alerte'] != 'non_traitee'
    alertes['orientee'] = alertes['issue'].str.startswith('1.')
    alertes['annee'] = pd.to_datetime(alertes['date_alerte']).dt.year
    alertes['classe_age'] = classe_age(alertes['age'])
    alertes['sexe'] = alertes['sexe'].map({'F': 'Femme', 'M': 'Homme'}).fillna('Non renseigné')
    alertes['modalite'] = alertes['modalite'].fillna('Non renseigné')
    alertes['departement'] = departement_lisible(alertes['departement'])
    alertes['site'] = site_lisible(alertes['experimentation'])

    statut = (alertes['statut_alerte'].map({'non_traitee': 'Non traitée', 'en_cours': 'En cours', 'traitee': 'Traitée'})
              .value_counts().reset_index())
    statut.columns = ['Statut', "Nombre d'alertes"]
    statut['Pourcentage (%)'] = pct(statut["Nombre d'alertes"], len(alertes))

    issue = alertes['issue'].value_counts().sort_index().reset_index()
    issue.columns = ['Issue', "Nombre d'alertes"]
    issue['Pourcentage de toutes les alertes (%)'] = pct(issue["Nombre d'alertes"], len(alertes))
    issue['Pourcentage des alertes prises en charge (%)'] = pct(issue["Nombre d'alertes"],
                                                                alertes['prise_en_charge'].sum())
    issue.loc[issue['Issue'].str.startswith('0.'), 'Pourcentage des alertes prises en charge (%)'] = None

    # Une alerte avec plusieurs domaines compte dans chacun de ses domaines
    par_domaine = pd.DataFrame([{
        'Domaine': nom, "Alertes contenant ce domaine": len(a),
        'Prises en charge (%)': round(a['prise_en_charge'].mean() * 100, 1),
        'Orientées vers un professionnel (%)': round(a['orientee'].mean() * 100, 1)}
        for code, nom in DOMAINES.items() for a in [alertes[alertes['alerte_' + code] == True]]
    ]).sort_values("Alertes contenant ce domaine", ascending=False)

    variables = {'annee': "Année de l'alerte", 'modalite': 'Modalité du test', 'classe_age': "Classe d'âge",
                 'sexe': 'Sexe', 'departement': 'Département', 'site': "Site d'expérimentation"}
    lignes, tests_khi2 = [], []
    for col, nom in variables.items():
        g = alertes.groupby(col).agg(n=('prise_en_charge', 'size'), prises=('prise_en_charge', 'sum'),
                                     orientees=('orientee', 'sum')).reset_index()
        lignes += [{'Caractéristique': nom, 'Valeur': r[col], "Nombre d'alertes": r['n'],
                    'Prises en charge': r['prises'], 'Prises en charge (%)': round(r['prises'] / r['n'] * 100, 1),
                    'Orientées vers un professionnel': r['orientees'],
                    'Orientées (%)': round(r['orientees'] / r['n'] * 100, 1)} for _, r in g.iterrows()]
        sous = alertes[~alertes[col].isin(['Non renseigné', 'Hors Normandie'])]
        if col == 'annee':
            sous = sous[sous['annee'] >= 2022]   # 2020-2021 : trop peu d'alertes
        tests_khi2.append(khi2(sous, col, 'prise_en_charge', nom))

    # Délai entre l'alerte et la première action
    avec_action = alertes[alertes['premiere_action'].notna()].copy()
    avec_action['delai'] = (pd.to_datetime(avec_action['premiere_action'])
                            - pd.to_datetime(avec_action['date_alerte'])).dt.days
    delais = avec_action['delai'].describe(percentiles=[0.25, 0.5, 0.75]).reset_index()
    delais.columns = ['Statistique', 'Délai en jours']
    delais['Statistique'] = delais['Statistique'].map({
        'count': "Alertes avec au moins une action", 'mean': 'Délai moyen', 'std': 'Écart-type',
        'min': 'Délai minimum', '25%': '1er quartile', '50%': 'Délai médian', '75%': '3e quartile',
        'max': 'Délai maximum'})
    delais['Délai en jours'] = delais['Délai en jours'].round(1)
    classes = pd.cut(avec_action['delai'], bins=[-1000, 0, 7, 30, 90, 100000],
                     labels=['Le jour même', '1 à 7 jours', '8 à 30 jours', '31 à 90 jours', 'Plus de 90 jours'])
    classes = classes.value_counts().sort_index().reset_index()
    classes.columns = ['Délai', "Nombre d'alertes"]
    classes['Pourcentage (%)'] = pct(classes["Nombre d'alertes"], len(avec_action))

    return [('Devenir_Perimetre', perimetre), ('Devenir_Statut', statut), ('Devenir_Issue', issue),
            ('Devenir_Par_domaine', par_domaine), ('Devenir_Par_profil', pd.DataFrame(lignes)),
            ('Devenir_Khi2', pd.DataFrame(tests_khi2)), ('Devenir_Delais', delais), ('Devenir_Classes_delai', classes)]


def levee_de_doute(con):
    """Comment se passent la levée de doute et l'orientation ?"""
    actions = actions_analysees(con, f"t.* EXCLUDE ({ALERTES_DU_TEST.replace('d.', '')}), {ALERTES_DU_TEST}")
    nb_alertes = len(alertes_analysees(con, "v.id_alerte"))

    # Une alerte peut avoir plusieurs actions : une case est « oui » si au moins une action l'a cochée
    # (une case vide compte comme « non »)
    cases = [c for c in actions.columns if c.startswith(('veracite_', 'prise_en_charge_', 'orientation_',
                                                         'pas_orientation_', 'fausse_alerte_', 'distance_'))]
    cases += ['orientations_proposees'] + [f'alerte_{d}' for d in DOMAINES]
    for c in cases:
        actions[c] = actions[c] == True
    par_alerte = actions.groupby('id_alerte').agg(
        nb_actions=('id_traitement', 'size'), **{c: (c, 'max') for c in cases},
        vraie=('veracite', lambda x: (x == 'alerte_vraie').any()),
        fausse=('veracite', lambda x: (x == 'alerte_fausse').any()),
        non_verifiable=('veracite', lambda x: (x == 'alerte_non_verifiable').any())).reset_index()
    par_alerte['levee_doute'] = 'Levée de doute non renseignée'
    for colonne, resultat in [('non_verifiable', 'Alerte non vérifiable'), ('fausse', 'Fausse alerte'),
                              ('vraie', 'Alerte vraie (confirmée)')]:   # le dernier l'emporte
        par_alerte.loc[par_alerte[colonne], 'levee_doute'] = resultat

    perimetre = pd.DataFrame({
        "Indicateur": ["Alertes analysées (tâche C)", "Alertes avec au moins une action", "Actions au total",
                       "Professionnels ayant fait au moins une action"],
        "Valeur": [nb_alertes, len(par_alerte), len(actions), actions['id_auteur'].nunique()]})

    def repartition(serie, titre, colonne_n, total):
        t = serie.value_counts().reset_index()
        t.columns = [titre, colonne_n]
        t['Pourcentage (%)'] = pct(t[colonne_n], total)
        return t

    nb_actions = repartition(par_alerte['nb_actions'], "Nombre d'actions sur l'alerte", "Nombre d'alertes",
                             len(par_alerte)).sort_values("Nombre d'actions sur l'alerte")
    levee = repartition(par_alerte['levee_doute'], 'Résultat de la levée de doute', "Nombre d'alertes", len(par_alerte))
    moment = repartition(actions['modalites_orientation'].map(
        {'a-distance': 'À distance (plus tard)', 'de-suite': 'Tout de suite (pendant le test)'}).fillna('Non renseigné'),
        "Moment de l'action", "Nombre d'actions", len(actions))

    def par_domaine(groupe, colonne, titre_n, titre_oui, avec_hors_alerte=False):
        """Pour chaque domaine en alerte au test : combien sont cochés dans « colonne_domaine » ?"""
        lignes = []
        for code, nom in DOMAINES.items():
            en_alerte = groupe[groupe['alerte_' + code]]
            oui = en_alerte[colonne + code].sum()
            ligne = {'Domaine': nom, titre_n: len(en_alerte), titre_oui: oui,
                     titre_oui + ' (%)': round(oui / len(en_alerte) * 100, 1) if len(en_alerte) >= 30 else None}
            if avec_hors_alerte:
                ligne["Domaine confirmé alors qu'il n'était pas en alerte au test"] = \
                    groupe[~groupe['alerte_' + code]][colonne + code].sum()
            lignes.append(ligne)
        return pd.DataFrame(lignes).sort_values(titre_n, ascending=False)

    confirmation = par_domaine(par_alerte[par_alerte['vraie']], 'veracite_',
                               'Alertes vraies avec ce domaine au test', 'Domaine confirmé', avec_hors_alerte=True)
    deja_pris = par_domaine(par_alerte[par_alerte['prise_en_charge_connue']], 'prise_en_charge_',
                            'Alertes avec ce domaine au test', 'Déjà pris en charge')

    contacts = pd.DataFrame({'Moyen utilisé (action à distance)': [
        'Contact avec la personne', 'Contact avec le médecin', 'Contact avec une autre personne',
        'Recherche dans le dossier', 'Autre', 'Personne non joignable'], "Nombre d'actions": [
        actions[c].sum() for c in ['distance_contact_participant', 'distance_contact_medecin', 'distance_contact_autre',
                                   'distance_recherche_dossier', 'distance_autre', 'distance_participant_non_joignable']]
    }).sort_values("Nombre d'actions", ascending=False)

    def compter(noms, titre):
        t = pd.DataFrame({titre: list(noms.values()), "Nombre d'alertes": [par_alerte[c].sum() for c in noms]})
        t = t.sort_values("Nombre d'alertes", ascending=False)
        t['Pourcentage des alertes avec action (%)'] = pct(t["Nombre d'alertes"], len(par_alerte))
        return t

    orientations = compter({
        'orientation_rdv_medecin': 'Rendez-vous chez le médecin', 'orientation_contact_medecin': 'Contact avec le médecin',
        'orientation_oriente_etape2': "Orientée vers l'étape 2", 'orientation_fait_etape2': 'Étape 2 faite',
        'orientation_structure_hospitaliere': 'Structure hospitalière', 'orientation_infos': 'Informations données',
        'orientation_autre': 'Autre'}, 'Orientation proposée')
    pas_orientation = compter({
        'pas_orientation_domaines_deja_pris_en_charge': 'Déjà prise en charge',
        'pas_orientation_pas_necessaire': 'Pas nécessaire', 'pas_orientation_refus': 'Refus de la personne',
        'pas_orientation_autres': 'Autre raison'}, 'Raison de non-orientation')
    fausses = compter({
        'fausse_alerte_erreur_test': 'Erreur pendant le test', 'fausse_alerte_erreur_saisie': 'Erreur de saisie',
        'fausse_alerte_pb_info': "Problème d'information", 'fausse_alerte_autres': 'Autre'},
        'Raison de la fausse alerte')

    # Répartition des actions entre professionnels (anonymes)
    par_pro = (actions.groupby('id_auteur').agg(actions=('id_traitement', 'size'), alertes=('id_alerte', 'nunique'))
               .sort_values('actions', ascending=False).reset_index(drop=True))
    par_pro.insert(0, 'Professionnel', [f'Professionnel {i + 1}' for i in range(len(par_pro))])
    par_pro['part'] = pct(par_pro['actions'], par_pro['actions'].sum())
    par_pro['cumul'] = par_pro['part'].cumsum().round(1)
    par_pro.columns = ['Professionnel', "Nombre d'actions", "Nombre d'alertes", 'Part des actions (%)',
                       'Part cumulée (%)']

    return [('Levee_Perimetre', perimetre), ('Levee_Nb_actions', nb_actions), ('Levee_Resultat', levee),
            ('Levee_Confirmation_domaine', confirmation), ('Levee_Moment', moment), ('Levee_Contacts', contacts),
            ('Levee_Orientations', orientations), ('Levee_Pas_orientation', pas_orientation),
            ('Levee_Fausses_alertes', fausses), ('Levee_Deja_pris_en_charge', deja_pris),
            ('Levee_Professionnels', par_pro)]


def ou_qui_quand(con):
    """Où, par qui et quand les alertes sont-elles traitées ? L'orientation est-elle précisée ?"""
    alertes = alertes_analysees(con, "v.id_alerte, v.departement, v.experimentation, v.date_alerte")
    actions = actions_analysees(con, f"""
        t.id_alerte, t.id_traitement, t.id_auteur, t.date_prise_en_charge AS date_action,
        t.veracite IS NOT NULL AS levee_doute, t.veracite = 'alerte_vraie' AS confirmee,
        coalesce({' OR '.join('t.' + c for c in ORIENTATIONS_PRECISES)}, false) AS orientee,
        {', '.join('t.' + c for c in ORIENTATIONS_PRECISES)}, t.orientation_autre, t.orientation_infos""")
    actions['action'] = True
    pros = lire(con, """SELECT id_professionnel AS id_auteur, profession, type_activite, type_etablissement,
                               departement AS departement_pro FROM icope_professionnel""")
    toutes = con.sql("""SELECT count(*), count(*) FILTER (WHERE nb_actions > 0), count(*) FILTER (WHERE levee_doute_faite),
                               count(*) FILTER (WHERE alerte_confirmee), count(*) FILTER (WHERE oriente)
                        FROM v_alerte_issue""").fetchone()

    # Territoire : le site d'expérimentation s'il y en a un, sinon « Hors site - département »
    alertes['site'] = site_lisible(alertes['experimentation']).replace('Hors sites', 'Hors site')
    alertes['departement'] = departement_lisible(alertes['departement'])
    alertes['territoire'] = alertes['site'].where(alertes['site'] != 'Hors site', 'Hors site - ' + alertes['departement'])
    alertes['annee_alerte'] = pd.to_datetime(alertes['date_alerte']).dt.year
    pros['departement_pro'] = departement_lisible(pros['departement_pro'])
    for c in ['profession', 'type_activite', 'type_etablissement']:
        pros[c] = pros[c].fillna('Non renseigné')

    # Nom des professionnels (demandé par Marine) : lu dans l'export des traitements, pas dans l'entrepôt
    noms = (pd.read_excel(dernier_export("bdi_traitements_alertes_*.xlsx"), dtype=str,
                          usecols=['id_auteur_prise_en_charge', 'nom_auteur_prise_en_charge'])
            .drop_duplicates('id_auteur_prise_en_charge')
            .set_index('id_auteur_prise_en_charge')['nom_auteur_prise_en_charge'])
    nb = actions.groupby('id_auteur').size().sort_values(ascending=False)
    codes = {a: f"Pro {i:02d} - {noms.get(a, 'nom inconnu')}" for i, a in enumerate(nb.index, 1)}
    actions['pro'] = actions['id_auteur'].map(codes)

    # Pour chaque alerte et chaque étape, la première action qui l'a faite : qui et quand
    etapes = {'action': 'Au moins une action', 'levee_doute': 'Levée de doute faite',
              'confirmee': 'Alerte confirmée', 'orientee': 'Orientée vers un professionnel ou une structure'}
    premieres = []
    for col, nom in etapes.items():
        faites = actions[actions[col] == True].sort_values(['date_action', 'id_traitement'])
        p = faites.groupby('id_alerte').first().reset_index()[['id_alerte', 'id_auteur', 'pro', 'date_action']]
        premieres.append(p.assign(etape=nom))
    premieres = pd.concat(premieres).merge(alertes, on='id_alerte').merge(pros, on='id_auteur', how='left')
    premieres['annee'] = pd.to_datetime(premieres['date_action']).dt.year
    for c in ['profession', 'type_activite', 'type_etablissement', 'departement_pro']:
        premieres[c] = premieres[c].fillna('Non retrouvé dans la liste des professionnels')
    ordre = list(etapes.values())

    def par_etape(cle):
        return [premieres[premieres['etape'] == e].groupby(cle).size().rename(e) for e in ordre]

    perimetre = pd.DataFrame({
        "Indicateur": ["Alertes analysées"] + ordre + ["Professionnels ayant fait au moins une action"],
        "Partie 1 (tests retenus, sans essais probables)":
            [len(alertes)] + [int((premieres['etape'] == e).sum()) for e in ordre] + [actions['id_auteur'].nunique()],
        "Toutes les alertes (chiffres du mail)": list(toutes) + [None]})

    ou = pd.concat([alertes.groupby('territoire').size().rename('Alertes')] + par_etape('territoire'),
                   axis=1).fillna(0).astype(int)
    for e in ordre:
        ou[e + ' (%)'] = pct(ou[e], ou['Alertes'])
    ou = ou.sort_values('Alertes', ascending=False).rename_axis('Territoire').reset_index()
    ou.insert(1, "Site d'expérimentation", ~ou['Territoire'].str.startswith('Hors site'))

    qui = (premieres.pivot_table(index='pro', columns='etape', values='id_alerte', aggfunc='count', fill_value=0)
           .reindex(columns=ordre, fill_value=0))
    infos = premieres.sort_values('date_action').groupby('pro').agg(
        **{'Profession': ('profession', 'first'), 'Activité': ('type_activite', 'first'),
           "Lieu d'exercice": ('type_etablissement', 'first'), 'Département du pro': ('departement_pro', 'first'),
           'Territoire principal des personnes': ('territoire', lambda x: x.value_counts().index[0]),
           'Première action': ('date_action', 'min'), 'Dernière action': ('date_action', 'max')})
    qui = infos.join(qui)
    qui.insert(0, 'Actions', nb.rename(index=codes))
    qui['Part des alertes avec action (%)'] = pct(qui[ordre[0]], qui[ordre[0]].sum())
    qui = qui.sort_values('Actions', ascending=False).reset_index().rename(columns={'pro': 'Professionnel'})

    concentration = []
    for e in ordre:
        parts = premieres[premieres['etape'] == e]['pro'].value_counts()
        concentration.append({'Étape': e, 'Alertes': int(parts.sum()), 'Professionnels': len(parts),
                              **{f'Part des {k} premiers (%)': round(parts.head(k).sum() / parts.sum() * 100, 1)
                                 for k in [1, 2, 5]}})

    quand = (pd.concat([alertes.groupby('annee_alerte').size().rename('Alertes émises')] + par_etape('annee'),
                       axis=1).fillna(0).astype(int).sort_index().rename_axis('Année').reset_index())

    avec_action = premieres[premieres['etape'] == ordre[0]]

    def croiser(colonne):
        t = pd.crosstab(avec_action['pro'], avec_action[colonne], margins=True, margins_name='Total')
        return t.sort_values('Total', ascending=False).reset_index().rename(columns={'pro': 'Professionnel'})

    # L'orientation est-elle précisée, ou seulement « autre » ?
    types = {'orientation_rdv_medecin': 'Conseil de prendre rendez-vous avec le médecin',
             'orientation_contact_medecin': 'Contact direct du médecin traitant',
             'orientation_fait_etape2': 'Step 2 réalisé',
             'orientation_oriente_etape2': 'Orientée vers un professionnel pour le Step 2',
             'orientation_structure_hospitaliere': 'Orientée vers une structure hospitalière',
             'orientation_autre': 'Autre (sans précision)', 'orientation_infos': 'Informations et conseils seulement'}
    cases = actions.groupby('id_alerte')[list(types)].max().astype('boolean').fillna(False).astype(bool)
    concernees = cases[cases[ORIENTATIONS_PRECISES + ['orientation_autre']].any(axis=1)]
    precise = concernees[ORIENTATIONS_PRECISES].any(axis=1)
    resume = pd.DataFrame({
        'Indicateur': ["Alertes avec une orientation (précise ou « autre »)", "dont au moins une orientation précise",
                       "dont « autre » seulement (destination non précisée)"],
        'Alertes': [len(concernees), int(precise.sum()), int((~precise).sum())]})
    resume['%'] = pct(resume['Alertes'], max(len(concernees), 1))
    detail = pd.DataFrame({"Type d'orientation": list(types.values()),
                           'Alertes': [int(cases[c].sum()) for c in types]}).sort_values('Alertes', ascending=False)

    return [('OQQ_Perimetre', perimetre), ('OQQ_Ou', ou), ('OQQ_Qui', qui),
            ('OQQ_Concentration', pd.DataFrame(concentration)), ('OQQ_Quand', quand),
            ('OQQ_Pro_x_territoire', croiser('territoire')), ('OQQ_Pro_x_annee', croiser('annee')),
            ('OQQ_Orientation_precisee', [resume, detail])]


# Qualité des fichiers : vides « normaux », quand la question ne concerne pas tout le monde
EXPLICATIONS = {
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
EXPLICATIONS_PREFIXE = {
    'distance_': "Rempli seulement pour une action à distance",
    'veracite_': "Rempli seulement si l'alerte est vraie (domaines confirmés)",
    'prise_en_charge_': "Rempli seulement si une prise en charge existante est signalée",
    'orientation_': "Rempli seulement si des orientations sont proposées",
    'pas_orientation_': "Rempli seulement s'il n'y a pas d'orientation",
    'fausse_alerte_': "Rempli seulement si c'est une fausse alerte",
}
SENSIBLES = ['ddn', 'mt_nom', 'mt_ville', 'commentaires', 'nom_auteur_prise_en_charge', 'centre']


def qualite_fichiers(con):
    """Les fichiers alertes et traitements sont-ils complets ? (lit les exports bruts, ne fait que compter)"""
    def expliquer(colonne):
        if colonne in EXPLICATIONS:
            return EXPLICATIONS[colonne]
        return next((t for p, t in EXPLICATIONS_PREFIXE.items() if colonne.startswith(p)), '')

    def audit(fichier):
        df = pd.read_excel(fichier)
        lignes = []
        for col in df.columns:
            vides = df[col].isna().sum()
            dm = (df[col].astype(str).str.strip().str.lower() == 'dm').sum()   # « dm » = donnée manquante
            manquants = vides + dm
            lignes.append({'Colonne': col, 'Cases vides': vides, 'Code « dm »': dm, 'Total manquant': manquants,
                           'Pourcentage manquant (%)': round(manquants / len(df) * 100, 1),
                           'Explication du manque': expliquer(col) if manquants > 0 else '',
                           "Sensible (pas dans l'entrepôt)": 'OUI' if col in SENSIBLES else ''})
        tableau = pd.DataFrame(lignes)
        manque = tableau['Total manquant'] > 0
        resume = {'Fichier': os.path.basename(fichier), 'Lignes': len(df), 'Colonnes': len(df.columns),
                  'Colonnes complètes': (~manque).sum(), 'Colonnes avec des manques': manque.sum(),
                  'Dont manques expliqués (question non concernée)': (manque & (tableau['Explication du manque'] != '')).sum(),
                  'Colonnes sensibles': (tableau["Sensible (pas dans l'entrepôt)"] == 'OUI').sum()}
        return resume, tableau

    resume_alertes, alertes = audit(dernier_export("bdi_alertes_*.xlsx"))
    resume_traitements, traitements = audit(dernier_export("bdi_traitements_alertes_*.xlsx"))
    return [('Qualite_Resume', pd.DataFrame([resume_alertes, resume_traitements])),
            ('Qualite_Fichier_alertes', alertes), ('Qualite_Fichier_traitements', traitements)]


if __name__ == "__main__":
    con = connecter()
    ecrire_excel("Partie1_2_Devenir_des_alertes.xlsx", "2. Le devenir des alertes", [
        ("Que deviennent les alertes, et en combien de temps ?", devenir(con)),
        ("Comment se passent la levée de doute et l'orientation ?", levee_de_doute(con)),
        ("Où, par qui et quand les alertes sont-elles traitées ? L'orientation est-elle précisée ?", ou_qui_quand(con)),
        ("Les fichiers d'alertes sont-ils complets ?", qualite_fichiers(con)),
    ])
