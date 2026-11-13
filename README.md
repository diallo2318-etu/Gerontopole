# Projet ICOPE Normandie – Gérontopôle

Entrepôt de données régional et outil d'orientation du programme ICOPE (OMS) : proposer à une personne âgée les professionnels et actions de prévention les plus proches.

| Partie | Sujet | Emplacement |
|---|---|---|
| 1 | Alertes et profils des personnes | `partie1_alertes/` |
| 2 | Nettoyage, statistiques, cohortes | `scripts_aissatou/` |
| 3 | Offre de prévention et professionnels | `entrepot/` |

## Installation

```bash
python3 -m venv mon_env
source mon_env/bin/activate
pip install -r requirements.txt
```

## Données

⚠️ Données de santé : **jamais dans le projet ni sur GitHub** (`mon_env/` et les `.xlsx` sources sont dans le `.gitignore`).

| Fichiers | Où | Partie |
|---|---|---|
| Exports ICOPE Monitor (`bdi_etape1`, `bdi_etape2`, `bdi_professionnels`, `bdi_alertes`, `bdi_traitements_alertes`) | à mettre dans votre dossier personnel `~/donnees_icope/` | 1, 3 |
| 5 fichiers « Actions collectives », liste des professionnels formés, « complet bdi_professionnels » | `~/donnees_icope/` | 3 |
| `liste_INFIRMIER_IPA_NORMANDIE.xlsx` (infirmiers en pratique avancée, reçus le 11/11/2026, facultatif) | `~/donnees_icope/` | 3 |
| `bdi_etape1_2026-10-09_12-10_969191.xlsx` | racine du projet | 2 |

S'il y a plusieurs exports d'un même fichier dans `~/donnees_icope/`, l'entrepôt prend le plus récent.

Fichiers de référence versionnés dans `entrepot/` (nécessaires à la reconstruction) :

| Fichier | Contenu |
|---|---|
| `communes_experimentation.csv` | 162 communes du Centre Manche (reçues du Gérontopôle le 06/11/2026) et 178 communes du GHT d'Elbeuf (reçues le 11/11/2026) |
| `territoires_experimentation.csv` | code postal de Lisieux, en attendant sa liste de communes |

Autre dossier de données : `export DONNEES_ICOPE=/chemin/vers/le/dossier`.

## Lancement

Depuis la racine du projet, environnement activé.

### 1. Entrepôt (à relancer à chaque nouvel export)

```bash
python3 entrepot/construire_entrepot.py
```

Crée `~/donnees_icope/entrepot_icope.duckdb`.

### 2. Partie 1 – Alertes

```bash
for f in partie1_alertes/[1-5]_*.py; do python3 "$f"; done
```

| Script | Fichier produit |
|---|---|
| `1_personnes_en_alerte.py` | `Partie1_1_Personnes_en_alerte.xlsx` |
| `2_devenir_des_alertes.py` | `Partie1_2_Devenir_des_alertes.xlsx` |
| `3_professionnels.py` | `Partie1_3_Professionnels.xlsx` |
| `4_step2_et_evolution.py` | `Partie1_4_Step2_et_evolution.xlsx` |
| `5_carte_alertes.py` | `Partie1_5_Carte_alertes_traitees.png` (télécharge une fois les contours des communes, 20 Mo, depuis geo.api.gouv.fr) |

Les scripts sont indépendants. Fichiers écrits dans `~/donnees_icope/`.

### 3. Partie 2 – Nettoyage et suivi

À lancer **dans cet ordre** :

```bash
python3 scripts_aissatou/mon_script.py             # Rapport_Audit_Qualite.xlsx
python3 scripts_aissatou/nettoyage.py              # Base_Nettoyee.xlsx
python3 scripts_aissatou/statistiques.py           # Base_Statistiques.xlsx
python3 scripts_aissatou/statistiques_completes.py # Base_Statistiques_Completes.xlsx
python3 scripts_aissatou/cohortes.py               # Resultats_Cohortes.xlsx
python3 scripts_aissatou/avant_apres_2025.py       # Analyse_Avant_Apres_2025.xlsx
python3 scripts_aissatou/tags_cfppa.py             # Analyse_Tags_CFPPA.xlsx
```

`nettoyage.py` prend l'export le plus récent et écrit `Base_Nettoyee.xlsx` avec deux onglets : `Donnees` (la base) et `Bilan` (lignes au départ, date de l'export), lus par les scripts suivants.

| Script | Contenu |
|---|---|
| `cohortes.py` | Toutes les personnes de 60 ans et plus, en 3 cohortes ; description (sexe, âge) ; suivi calculé seulement chez celles qui auraient déjà dû refaire le test (premier test il y a plus de 6 mois, ou plus d'un an, à la date de l'export) |
| `avant_apres_2025.py` | Âge (Mann-Whitney) et modalité du test (khi-deux) avant / après 2025 ; tests par mois ; mentions de la Carsat (colonnes `source`, `tags`, `centre`). Renseigner `DATE_CAMPAGNE_CARSAT` en haut du script pour comparer avant / après la campagne |
| `tags_cfppa.py` | Tests orientés par les CFPPA (tag « la Poste CFPPA France ») comparés aux autres tests |

Règles de nettoyage (validées par Marine Le Roux, 22/10/2026) :

| Règle | Effet |
|---|---|
| Un test par personne et par jour | on garde le dernier |
| Tests « one-shot » de professionnels | colonne `one_shot_pro` |
| Moins de 60 ans | colonne `moins_60_ans` |
| Cohortes | toutes les personnes sont gardées, même entrées depuis moins d'un an |
| Suivi | % calculé seulement chez les personnes dont le premier test date de plus de 6 mois (ou 1 an) |

### 4. Partie 3 – Offre de prévention

À lancer **après** l'entrepôt, dans cet ordre :

```bash
python3 entrepot/construire_table_roles.py     # table ref_professionnel_role
python3 entrepot/bilans_par_territoire.py      # bilans_prevention_par_departement.csv, bilans_prevention_par_epci.csv
python3 entrepot/exporter_excel.py             # entrepot_icope.xlsx (facultatif)
```

`construire_entrepot.py` charge déjà les fichiers de prévention (`charger_prevention.py`). Chaque reconstruction de l'entrepôt efface `ref_professionnel_role` : relancer `construire_table_roles.py`.

| Table | Contenu |
|---|---|
| `offre_action_collective` | actions de prévention |
| `v_action_commune` | communes où chaque action est accessible |
| `offre_pro_forme_icope` | professionnels formés à ICOPE |
| `offre_centre_agirc_arrco` | centres Agirc-Arrco |
| `offre_ipa` | infirmiers en pratique avancée (colonne `pathologies_chroniques` : levée de doute et Step 2) |
| `ref_professionnel_role` | professionnels classés par rôle : `levee_de_doute`, `bilan_prevention`, `etape2` |

Test du calcul de distance (commune, domaine) :

```bash
python3 entrepot/orientation.py "Vire Normandie" vision
```

Domaines : `vision`, `audition`, `cognition`, `nutrition`, `psychologie`, `mobilite`, `social`, `aidant`, `incontinence`.

Rattachement des actions aux zones : `python3 entrepot/rattacher_territoires.py` écrit `~/donnees_icope/ref_territoire_action.csv` pour les UTAS de Seine-Maritime (`bases/utas_seine_maritime.csv`) et les territoires d'action sociale du Calvados (`bases/territoires_action_sociale_calvados.csv`, construit depuis les contours publiés sur data.calvados.fr : une commune appartient au territoire qui contient son centre), puis reconstruire l'entrepôt.

Sans `liste_INFIRMIER_IPA_NORMANDIE.xlsx`, la table `offre_ipa` est construite depuis l'Annuaire Santé (savoir-faire « Exercice infirmier en pratique avancée… », colonne `source`).

Pour les autres zones (secteurs de la Manche), remplir `~/donnees_icope/territoires_a_rattacher.csv` (colonne `codes_insee`, séparateur `|`), l'enregistrer sous `ref_territoire_action.csv`, puis reconstruire l'entrepôt. Pour la Seine-Maritime, `bases/utas_seine_maritime.csv` donne l'UTAS de chaque commune (open data du Département 76, 2022).

### 5. Parcours (travail commun)

Le parcours de chaque capacité est décrit dans `entrepot/parcours_capacites.csv` (une ligne par proposition) :

| Colonne | Contenu |
|---|---|
| `domaine` | `vision`, `audition`, `cognition`… ou `tous` (levée de doute, Step 2, moins de 60 ans) |
| `etape` | `levee_de_doute`, `etape2`, `orientation` (alerte confirmée), `sans_alerte`, `moins_60` |
| `plan` | `A` (le plus adapté), `B` si le plan A est trop loin ou absent, puis `C` |
| `source` | où chercher : `rpps_profession`, `finess_categorie`, `ipa`, `mon_bilan_prevention`, `agirc_arrco`, `pro_forme_icope`, `action_collective` (mots-clés séparés par `\|`), `action_domaine` (actions classées dans cette capacité par l'entrepôt, colonne `domaine_icope` : `mobilite`, `nutrition`, `psychologie`, `social`…), `conseil`, `a_obtenir` |
| `valeur` | le métier (écrit comme dans `referentiel_alertes.csv`), les mots-clés ou le texte du conseil |
| `distance_max_km` | au-delà, on passe au plan suivant (vide : pas de limite) |
| `age_min`, `age_max` | si la proposition dépend de l'âge (ex. Mon bilan prévention : 60-65 et 70-75 ans) |
| `remarque` | ce qu'on dit à la personne ou pourquoi ce choix |

Vérifier le fichier (métiers bien écrits, plan proposé selon la commune) :

```bash
python3 entrepot/verifier_parcours.py
python3 entrepot/verifier_parcours.py --domaine vision
```

### 6. Boussole ICOPE : l'interface du parcours (bloc 2)

Après l'entrepôt et `construire_table_roles.py` :

```bash
python3 interface/serveur.py      # puis ouvrir http://localhost:8000
```

On choisit la commune (suggestions pendant la frappe : nom, code postal ou code INSEE), l'âge et les alertes, puis **Construire le parcours** (ou un des 5 profils types de la partie 1). La page affiche :

- une frise des étapes : levée de doute, orientation pour chaque alerte, Step 2, avec le plan retenu (A / B / C), les 3 professionnels les plus proches (adresse, distance, téléphone) et **« Pourquoi ce plan ? »** (chaque plan essayé : trouvé, trop loin, absent, liste à obtenir) ;
- une carte (la personne, les professionnels proposés, le rayon de recherche au survol d'une étape) ;
- les indicateurs du parcours et les actions de prévention proches pour les capacités sans alerte ;
- une fiche imprimable (bouton **Imprimer la fiche**). L'adresse de la page (`#50502/84/cognition,mobilite`) permet de rouvrir ou partager un parcours.

| Fichier | Rôle |
|---|---|
| `interface/moteur_parcours.py` | calcul du parcours (utilisable seul : `python3 interface/moteur_parcours.py "Vire Normandie" 72 vision`) |
| `interface/serveur.py` | API FastAPI : `/api/meta`, `/api/communes`, `/api/parcours` (documentation : http://localhost:8000/api/docs) |
| `interface/static/` | la page (HTML, CSS, JavaScript) ; Leaflet 1.9.4 est inclus, seul le fond de carte OpenStreetMap demande internet |
| `tests/test_interface.py` | tests de l'API : `python3 -m pytest tests/` |

- Le serveur n'écoute que sur l'ordinateur (127.0.0.1) : l'entrepôt contient des données de santé, même si la page n'affiche que l'offre (annuaires publics).
- Une capacité sans parcours écrit dans `parcours_capacites.csv` affiche les métiers du référentiel d'alertes (« Parcours à venir »).
- Les professionnels formés à ICOPE (liste privée) sont affichés sans nom ni coordonnées.
- Maisons sport-santé : `bases/maisons_sport_sante_normandie.csv` (Sport Santé Normandie, consulté le 13/11/2026), table `offre_maison_sport_sante`, source `maison_sport_sante` dans le parcours.

## Règles

**Communes**
- Aucune ligne n'est supprimée : les lignes problématiques sont repérées par une colonne.
- Moins de 60 ans conservés dans les analyses, exclus du parcours de soins.

**Partie 1 – tests analysés**
- Un test par personne et par jour (le dernier) ; essais probables (moins de 50 ans) retirés.
- Seulement les tests faits avant le dernier export des alertes (colonne `couvert_par_alertes`), pour que tests et alertes s'arrêtent à la même date. La limite avance seule quand on ajoute un nouvel export des alertes.
- Avec les exports actuels (tests du 06/11, alertes du 17/10) : 2 911 tests, 2 413 alertes.
- Pourcentages par domaine calculés sur les tests où la question a été posée.
- Cases calculées sur moins de 30 tests laissées vides.

**Confidentialité**
- Professionnels et équipes anonymisés dans les fichiers Excel (« Professionnel 1 », « Équipe A »…), sauf l'onglet `OQQ_Qui` (fichier 2) : ce fichier ne circule qu'avec le Gérontopôle.
- Le `.gitignore` ignore les fichiers dont le nom contient « professionnels ».

## Erreurs fréquentes

| Message | Solution |
|---|---|
| `Fichier introuvable : …/bdi_etape1_*.xlsx` | placer les exports dans `~/donnees_icope/` |
| `IO Error: … entrepot_icope.duckdb` | lancer `construire_entrepot.py` |
| `ModuleNotFoundError` | activer `mon_env` et installer les bibliothèques |
| `Table … ref_professionnel_role does not exist` | lancer `construire_table_roles.py` |
