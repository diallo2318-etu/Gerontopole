# Projet ICOPE Normandie – Gérontopôle

Entrepôt de données régional et outil d'orientation du programme ICOPE (OMS) : proposer à une personne âgée les professionnels et actions de prévention les plus proches.

| Partie | Sujet | Emplacement |
|---|---|---|
| 1 | Alertes et profils patients | `partie1_alertes/` |
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
| `bdi_etape1_2026-10-09_12-10_969191.xlsx` | racine du projet | 2 |

Fichiers de référence versionnés dans `entrepot/` (nécessaires à la reconstruction) :

| Fichier | Contenu |
|---|---|
| `communes_experimentation.csv` | 162 communes du Centre Manche (reçues du Gérontopôle le 06/11/2026) |
| `territoires_experimentation.csv` | codes postaux d'Elbeuf et Lisieux, en attendant leurs listes de communes |

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
for f in partie1_alertes/[1-4]_*.py; do python3 "$f"; done
```

| Script | Fichier produit |
|---|---|
| `1_personnes_en_alerte.py` | `Partie1_1_Personnes_en_alerte.xlsx` |
| `2_devenir_des_alertes.py` | `Partie1_2_Devenir_des_alertes.xlsx` |
| `3_professionnels.py` | `Partie1_3_Professionnels.xlsx` |
| `4_step2_et_evolution.py` | `Partie1_4_Step2_et_evolution.xlsx` |

Les scripts sont indépendants. Fichiers écrits dans `~/donnees_icope/`.

### 3. Partie 2 – Nettoyage et suivi

À lancer **dans cet ordre** :

```bash
python3 scripts_aissatou/mon_script.py             # Rapport_Audit_Qualite.xlsx
python3 scripts_aissatou/nettoyage.py              # Base_Nettoyee.xlsx
python3 scripts_aissatou/statistiques.py           # Base_Statistiques.xlsx
python3 scripts_aissatou/statistiques_completes.py # Base_Statistiques_Completes.xlsx
python3 scripts_aissatou/cohortes.py               # Resultats_Cohortes_Filtrees.xlsx
```

Règles de nettoyage (validées par Marine Le Roux, 22/10/2026) :

| Règle | Effet |
|---|---|
| Un test par personne et par jour | on garde le dernier |
| Tests « one-shot » de professionnels | colonne `one_shot_pro` |
| Moins de 60 ans | colonne `moins_60_ans` |
| Fenêtre de suivi (cohortes) | exclusion des premiers tests de moins de 365 jours |

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
| `ref_professionnel_role` | professionnels classés par rôle : `levee_de_doute`, `bilan_prevention`, `etape2` |

Test du calcul de distance (commune, domaine) :

```bash
python3 entrepot/orientation.py "Vire Normandie" vision
```

Domaines : `vision`, `audition`, `cognition`, `nutrition`, `psychologie`, `mobilite`, `social`, `aidant`, `incontinence`.

Rattachement des actions aux zones (UTAS, MDS, secteurs) : remplir `~/donnees_icope/territoires_a_rattacher.csv` (colonne `codes_insee`, séparateur `|`), l'enregistrer sous `ref_territoire_action.csv`, puis reconstruire l'entrepôt.

## Règles

**Communes**
- Aucune ligne n'est supprimée : les lignes problématiques sont repérées par une colonne.
- Moins de 60 ans conservés dans les analyses, exclus du parcours de soins.

**Partie 1 – tests analysés**
- Un test par personne et par jour (le dernier) ; essais probables (moins de 50 ans) retirés : 2 834 tests, 2 342 alertes.
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
