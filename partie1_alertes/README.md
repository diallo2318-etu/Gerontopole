# Partie 1 – Alertes et profils patients

Ces scripts analysent les alertes ICOPE : leur fréquence, le profil des personnes, ce que deviennent les alertes, la levée de doute, les professionnels, le Step 2 et les profils types.

Ils lisent tous **l'entrepôt de données ICOPE**, qu'on construit une fois avec `entrepot/construire_entrepot.py`. Ils produisent chacun un fichier Excel.

---

## 1. Installer (une seule fois)

Ouvrez un terminal dans le dossier du projet `Gerontopole` :

```bash
python3 -m venv mon_env
source mon_env/bin/activate
pip install -r requirements.txt
```

## 2. Ranger les exports ICOPE (une seule fois)

Créez le dossier `donnees_icope` dans votre dossier personnel (`~/donnees_icope/`), **en dehors du projet**. Mettez-y les exports ICOPE Monitor envoyés par Marine :

| Fichier | Contenu |
|---|---|
| `bdi_etape1_2026-10-09_….xlsx` | les tests (étape 1) |
| `bdi_etape2_2026-10-09_….xlsx` | les évaluations Step 2 |
| `bdi_professionnels_2026-10-09_….xlsx` | la liste des professionnels |
| `bdi_alertes_2026-10-17_….xlsx` | les alertes |
| `bdi_traitements_alertes_2026-10-17_….xlsx` | les actions sur les alertes |

⚠️ Ces fichiers contiennent des données de santé. **Ils ne vont jamais dans le projet ni sur GitHub.**

Pour utiliser un autre dossier : `export DONNEES_ICOPE=/chemin/vers/le/dossier`.

## 3. Construire l'entrepôt (une fois, puis à chaque nouvel export)

```bash
python3 entrepot/construire_entrepot.py
```

Le fichier `~/donnees_icope/entrepot_icope.duckdb` est créé. Il réunit les exports ICOPE, les bases publiques de Normandie (`bases/`) et les règles de nettoyage décidées le 16/10. Il contient des données de patients : il reste dans `~/donnees_icope/`.

## 4. Lancer les scripts

Toujours depuis le dossier du projet, avec l'environnement activé (`source mon_env/bin/activate`).

Un script :
```bash
python3 partie1_alertes/alertes_A_frequence.py
```

Tous les scripts d'un coup :
```bash
for f in partie1_alertes/alertes_*.py; do python3 "$f"; done
```

Chaque script affiche ses résultats dans le terminal et écrit son fichier Excel dans `~/donnees_icope/`. Les scripts sont indépendants : on peut les lancer dans n'importe quel ordre.

| Script | Question | Fichier produit |
|---|---|---|
| `alertes_A_frequence.py` | Quelles alertes sont les plus fréquentes, et ensemble ? | `Partie1_A_Frequence_Alertes.xlsx` |
| `alertes_B_profils.py` | Qui est en alerte (âge, sexe, modalité, territoire) ? | `Partie1_B_Profils_Alertes.xlsx` |
| `alertes_C_devenir.py` | Que deviennent les alertes, et en combien de temps ? | `Partie1_C_Devenir_Alertes.xlsx` |
| `alertes_D_levee_doute.py` | Levée de doute, alertes confirmées, orientations | `Partie1_D_Levee_Doute_Orientation.xlsx` |
| `alertes_E_qualite_fichiers.py` | Cases vides et données sensibles des exports alertes | `Partie1_E_Qualite_Fichiers.xlsx` |
| `alertes_F_professionnels.py` | Quels professionnels traitent les alertes ? | `Partie1_F_Professionnels.xlsx` |
| `alertes_G_evolution.py` | Évolution par mois et par trimestre | `Partie1_G_Evolution.xlsx` |
| `alertes_H_step2.py` | Le Step 2 : où, par qui, pour qui ? | `Partie1_H_Step2.xlsx` |
| `alertes_I_profils_types.py` | Profils patients types et format d'entrée du modèle | `Partie1_I_Profils_Types.xlsx` |
| `alertes_J_age_territoires.py` | Âge des personnes selon le territoire | `Partie1_J_Age_Territoires.xlsx` |

## 5. Règles communes à tous les scripts

- On garde **un test par personne et par jour** (le dernier), et on retire les **essais probables** (moins de 50 ans) : 2 834 tests, 2 342 alertes.
- Les **moins de 60 ans sont gardés** dans l'analyse (ils sont seulement exclus du parcours).
- Les pourcentages par domaine sont calculés sur les tests où la question a été posée.
- Les cases calculées sur **moins de 30 tests** restent vides (trop peu pour être fiables).
- Les **professionnels et les équipes sont anonymisés** dans les fichiers Excel (« Professionnel 1 », « Équipe A »…).

## En cas de problème

- `Fichier introuvable : …/bdi_etape1_*.xlsx` → les exports ne sont pas dans `~/donnees_icope/` (étape 2).
- `IO Error: … entrepot_icope.duckdb` → l'entrepôt n'est pas construit (étape 3).
- `ModuleNotFoundError` → l'environnement n'est pas activé ou les bibliothèques ne sont pas installées (étape 1).
