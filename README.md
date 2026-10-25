# Projet ICOPE Normandie - Partie d'Aissatou (Nettoyage et suivi)

Ce dossier contient les scripts et les livrables de la **Personne 2** (nettoyage de la base ICOPE, statistiques descriptives et cohortes de suivi).

L'objectif est de permettre à toute l'équipe de récupérer les mêmes données et de relancer les scripts pour obtenir exactement les mêmes résultats.

---

## 1. Les fichiers utilisés

Pour que les scripts fonctionnent, vous devez disposer du fichier source suivant :

- **Nom exact :** `bdi_etape1_2026-10-09_12-10_969191.xlsx`
- **Origine :** Export ICOPE Monitor, transmis par Marine Le Roux (Gérontopôle Normandie).
- **Date de l'export :** 09/10/2026.
- **Nombre de lignes :** 2 971 tests (avant nettoyage).

*Ce fichier contient des données de santé. Il ne doit jamais être poussé sur le dépôt.*

---

## 2. Où ranger les fichiers

Placez le fichier source à la racine du projet `Gerontopole`, à côté du dossier `scripts_aissatou/`.
erontopole/
│
├── bdi_etape1_2026-10-09_12-10_969191.xlsx <-- LE FICHIER SOURCE (à la racine)
│
├── scripts_aissatou/
│ ├── mon_script.py
│ ├── nettoyage.py
│ ├── statistiques.py
│ ├── statistiques_completes.py
│ └── cohortes.py
│
├── mon_env/ <-- L'environnement virtuel
└── README.md

**⚠️ Important :** Le fichier `bdi_etape1_...xlsx` et le dossier `mon_env/` doivent être ajoutés au fichier `.gitignore` pour ne jamais être publiés.

---

## 3. Installation

### 3.1. Créer l'environnement virtuel
Ouvrez un terminal, placez-vous dans le dossier `Gerontopole` et tapez :
```bash
python3 -m venv mon_env
3.2. Activer l'environnement virtuel
source mon_env/bin/activate
ous verrez (mon_env) apparaître au début de votre ligne de commande).
3.3. Installer les bibliothèques nécessaires
bash

pip install pandas openpyxl

4. Ordre de lancement des scripts

Les scripts doivent être lancés dans cet ordre précis, depuis le dossier Gerontopole (où se trouve le fichier source).
Étape 1 : Audit de qualité
bash

python3 scripts_aissatou/mon_script.py

    Ce qu'il fait : Charge la base brute et produit un rapport d'audit (types de colonnes, taux de données manquantes).

    Ce qu'il produit : Rapport_Audit_Qualite.xlsx

Étape 2 : Nettoyage
bash

python3 scripts_aissatou/nettoyage.py

    Ce qu'il fait : Applique les règles de nettoyage (voir section 5) et marque les tests one-shot et les moins de 60 ans.

    Ce qu'il produit : Base_Nettoyee.xlsx (2 909 lignes)

Étape 3 : Statistiques descriptives (version simple)
bash

python3 scripts_aissatou/statistiques.py

    Ce qu'il fait : Calcule les statistiques de base à partir de la base nettoyée.

    Ce qu'il produit : Base_Statistiques.xlsx

Étape 4 : Statistiques descriptives (version complète)
bash

python3 scripts_aissatou/statistiques_completes.py

    Ce qu'il fait : Calcule toutes les statistiques (modalités, suivi, années, sexe, âge, territoires) avec les pourcentages.

    Ce qu'il produit : Base_Statistiques_Completes.xlsx (7 onglets)

Étape 5 : Cohortes de suivi
bash

python3 scripts_aissatou/cohortes.py

    Ce qu'il fait : Définit les 3 cohortes de suivi, en excluant les entrées trop récentes (fenêtre de 1 an).

    Ce qu'il produit : Resultats_Cohortes_Filtrees.xlsx

5. Les règles de nettoyage appliquées

Les règles ci-dessous ont été validées par Marine Le Roux (Gérontopôle) dans ses mails du 22 octobre 2026.
Règle 1 : Un seul test par personne et par jour

    Ce que ça fait : Si une personne a fait plusieurs tests le même jour, on ne garde que le dernier.

    Pourquoi : Éviter les erreurs de double-clic ou de double saisie.

    Impact : 62 doublons supprimés (2 971 -> 2 909 lignes).

Règle 2 : Marquer les tests "one-shot" de professionnels

    Ce que ça fait : On crée une colonne one_shot_pro. Si un professionnel n'a évalué qu'une seule personne, on marque "OUI".

    Pourquoi : Identifier les professionnels qui ont testé l'outil une fois sans s'engager. Conformément à la consigne, ces tests ne sont pas supprimés, mais marqués comme "indicateur de suivi".

    Impact : 72 tests marqués.

Règle 3 : Marquer les personnes de moins de 60 ans

    Ce que ça fait : On crée une colonne moins_60_ans. Si l'âge est inférieur à 60, on marque "OUI".

    Pourquoi : Ces personnes restent dans l'analyse statistique, mais elles sont exclues du parcours de soins (le seuil ICOPE est fixé à 60 ans).

    Impact : 218 personnes marquées.

Règle 4 : Fenêtre de suivi (pour les cohortes)

    Ce que ça fait : On exclut les personnes dont le premier test a moins d'un an (365 jours), car elles n'ont pas encore eu le temps de faire leur suivi.

    Pourquoi : Éviter de fausser l'analyse des cohortes en comptant des personnes qui n'ont pas eu l'occasion de refaire un test.

    Impact : Les effectifs des cohortes sont calculés sur les personnes avec un recul suffisant.

6. Résultats clés (pour le rapport)

    Lignes au départ : 2 971

    Lignes après nettoyage : 2 909

    Tests one-shot marqués : 72

    Personnes < 60 ans marquées : 218

    Répartition par modalité : 73,8 % auto-évaluation, 17,9 % par un professionnel, 8,3 % avec un aidant.

    Répartition par suivi : 83,9 % initial, 16,1 % suivi.

    Âge médian : 67 ans.

    Répartition par sexe : 57,3 % de femmes.

    Territoires : 89,9 % reste de la Normandie, 3,6 % Elbeuf, 3,6 % Centre Manche, 2,9 % Lisieux.

    Cohortes (avec fenêtre de 1 an) : Cohorte 1 (par un pro) = 40,5 %, Cohorte 2 (isolés) = 39,3 %, Cohorte 3 (autonomes avec suivi) = 20,2 %.

