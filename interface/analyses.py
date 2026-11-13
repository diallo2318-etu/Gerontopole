"""Analyses des onglets « Couverture » et « Statistiques » de Boussole ICOPE.

couverture()    : pour chaque commune de Normandie, le plan obtenu (A, B, C ou aucun) pour une étape du
                  parcours, d'après parcours_capacites.csv et l'offre de l'entrepôt (données publiques).
statistiques()  : chiffres agrégés des tests ICOPE (partie 2) et du devenir des alertes (partie 1).
                  Aucune donnée individuelle ; un pourcentage calculé sur moins de 30 tests reste vide.
"""
from functools import lru_cache

import numpy as np
import pandas as pd

from moteur_parcours import CAPACITES, charger_parcours, filtre_age
from verifier_parcours import distances_au_plus_proche

SEUIL = 30  # en dessous, pas de pourcentage (règle de la partie 1)
TESTS = "d.retenu AND NOT d.test_probable"                       # partie 2 : tests analysés
TESTS_ALERTES = TESTS + " AND d.couvert_par_alertes"             # partie 1 : tests couverts par l'export des alertes
MODALITES = {"auto-évaluation": "Auto-évaluation", "avec un aidant": "Avec un aidant", "par un professionnel": "Par un professionnel"}


def pct(n, total):
    return None if not total or total < SEUIL else round(100 * n / total, 1)


# ---------------------------------------------------------------------------- Couverture
def options_couverture():
    p = charger_parcours()
    options = [{"cle": "levee_de_doute", "nom": "Levée de doute", "age": True},
               {"cle": "etape2", "nom": "Step 2 (évaluation approfondie)", "age": False}]
    for d in CAPACITES:
        if len(p[(p.domaine == d) & (p.etape == "orientation")]):
            options.append({"cle": f"orientation:{d}", "nom": f"Orientation · {CAPACITES[d]}", "age": False, "domaine": d})
    return options


def _communes(con):
    c = con.execute("""SELECT code_insee, nom, departement, latitude, longitude,
                              coalesce(TRY_CAST(population AS DOUBLE), 0) AS population
                       FROM ref_commune WHERE latitude IS NOT NULL ORDER BY code_insee""").df()
    return c


@lru_cache(maxsize=64)
def _couverture(con, cle, age):
    p = charger_parcours()
    if cle.startswith("orientation:"):
        lignes = p[(p.domaine == cle.split(":", 1)[1]) & (p.etape == "orientation")]
    else:
        lignes = p[p.etape == cle]
    lignes = filtre_age(lignes, age)
    communes = _communes(con)
    n = len(communes)
    plan = np.full(n, "aucun", dtype=object)
    distance_a = np.full(n, np.nan)
    for nom_plan in sorted(lignes["plan"].unique()):
        possible = np.zeros(n, dtype=bool)
        for l in lignes[lignes.plan == nom_plan].itertuples():
            if l.source == "conseil":
                continue  # un conseil n'est pas une offre : on le signale à part
            d = distances_au_plus_proche(con, communes, l.source, l.valeur)
            if d is None:
                continue
            if nom_plan == "A":
                distance_a = np.fmin(distance_a, d)
            limite = l.distance_max_km if pd.notna(l.distance_max_km) else np.inf
            possible |= d <= limite
        plan = np.where((plan == "aucun") & possible, nom_plan, plan)
    communes["plan"] = plan
    communes["distance_plan_a"] = np.round(distance_a, 1)
    a_conseil = bool((lignes.source == "conseil").any())
    return communes, a_conseil, lignes


def couverture(con, cle, age=72):
    communes, a_conseil, lignes = _couverture(con, cle, int(age))
    pop = communes["population"].sum()
    resume = [{"plan": pl, "communes": int((communes.plan == pl).sum()),
               "population_pct": round(100 * communes.loc[communes.plan == pl, "population"].sum() / pop, 1)}
              for pl in ["A", "B", "C", "aucun"]]
    sans_a = communes[communes.plan != "A"].sort_values("population", ascending=False).head(10)
    plans = [{"plan": pl, "propositions": [{"source": l.source, "valeur": l.valeur,
                                            "distance_max_km": None if pd.isna(l.distance_max_km) else l.distance_max_km}
                                           for l in lignes[lignes.plan == pl].itertuples()]}
             for pl in sorted(lignes["plan"].unique())]
    return {
        "resume": resume,
        "conseil_toujours_possible": a_conseil,
        "plans": plans,
        "sans_plan_a": [{"commune": r.nom, "departement": r.departement, "population": int(r.population), "plan": r.plan,
                         "distance_plan_a": None if np.isnan(r.distance_plan_a) else float(r.distance_plan_a)}
                        for r in sans_a.itertuples()],
        "communes": [[r.code_insee, r.nom, round(r.latitude, 4), round(r.longitude, 4), int(r.population), r.plan]
                     for r in communes.itertuples()],
    }


# ---------------------------------------------------------------------------- Statistiques
@lru_cache(maxsize=1)
def statistiques(con):
    q = lambda sql: con.execute(sql).df()

    # --- Partie 2 : les tests et les personnes
    tests = q(f"""SELECT d.participant, d.numero, d.date_depistage, d.modalite, d.age, d.hors_cible_moins_60
                  FROM icope_depistage d WHERE {TESTS}""")
    tests["date_depistage"] = pd.to_datetime(tests["date_depistage"])
    reference = tests["date_depistage"].max()
    depuis_2025 = tests[tests.date_depistage.dt.year >= 2025]

    par_mois = (tests[tests.date_depistage >= "2022-01-01"]
                .assign(mois=lambda t: t.date_depistage.dt.to_period("M").astype(str),
                        modalite=lambda t: t.modalite.map(MODALITES).fillna("Non renseigné"))
                .pivot_table(index="mois", columns="modalite", values="numero", aggfunc="count", fill_value=0))
    mois = pd.period_range("2022-01", reference.to_period("M"), freq="M").astype(str)
    par_mois = par_mois.reindex(mois, fill_value=0)

    periodes = []
    for nom, t in [("Avant 2025", tests[tests.date_depistage.dt.year < 2025]), ("2025 et après", depuis_2025)]:
        periodes.append({"periode": nom, "tests": len(t), "age_median": float(t.age.median()),
                         "modalites": {MODALITES[m]: pct((t.modalite == m).sum(), len(t)) for m in MODALITES}})

    # Cohortes : personnes de 60 ans et plus, selon leur premier test
    cibles = tests[~tests.hors_cible_moins_60.fillna(False).astype(bool)].sort_values(["participant", "date_depistage", "numero"])
    pers = cibles.groupby("participant").agg(premier=("date_depistage", "first"), modalite=("modalite", "first"),
                                             nb=("numero", "count")).reset_index()
    pers["cohorte"] = np.where(pers.modalite == "par un professionnel", "Premier test par un professionnel",
                               np.where(pers.nb == 1, "Auto-évaluation isolée", "Autonome avec suivi"))
    cohortes = [{"cohorte": c, "personnes": int((pers.cohorte == c).sum()), "pct": pct((pers.cohorte == c).sum(), len(pers))}
                for c in ["Premier test par un professionnel", "Auto-évaluation isolée", "Autonome avec suivi"]]
    eligibles = pers[(reference - pers.premier).dt.days >= 365]
    suivi = [{"modalite": MODALITES[m], "personnes": int((eligibles.modalite == m).sum()),
              "suivi_pct": pct(((eligibles.modalite == m) & (eligibles.nb >= 2)).sum(), (eligibles.modalite == m).sum())}
             for m in MODALITES]

    # --- Partie 1 : le devenir des alertes
    al = q(f"""SELECT v.statut_alerte, v.issue, v.date_alerte, v.premiere_action,
                      {", ".join(f"d.alerte_{c}" for c in CAPACITES)}
               FROM v_alerte_issue v JOIN icope_depistage d USING (id_depistage) WHERE {TESTS_ALERTES}""")
    al["prise"] = al.statut_alerte != "non_traitee"
    al["orientee"] = al.issue.str.startswith("1.")
    delai = (pd.to_datetime(al.premiere_action) - pd.to_datetime(al.date_alerte)).dt.days.dropna()
    par_domaine = []
    for c, nom in CAPACITES.items():
        a = al[al[f"alerte_{c}"] == True]  # noqa: E712
        par_domaine.append({"domaine": c, "nom": nom, "alertes": len(a), "prise_pct": pct(a.prise.sum(), len(a)),
                            "orientee_pct": pct(a.orientee.sum(), len(a))})
    issues = al.issue.value_counts().sort_index()

    return {
        "reference": reference.date().isoformat(),
        "chiffres": {
            "tests": len(tests), "personnes": int(tests.participant.nunique()),
            "auto_2025_pct": pct((depuis_2025.modalite == "auto-évaluation").sum(), len(depuis_2025)),
            "suivi_1an_pct": pct((eligibles.nb >= 2).sum(), len(eligibles)),
            "alertes": len(al), "alertes_prises_pct": pct(al.prise.sum(), len(al)),
            "alertes_orientees_pct": pct(al.orientee.sum(), len(al)),
            "delai_median_jours": None if delai.empty else float(delai.median()),
        },
        "par_mois": {"mois": list(par_mois.index), "series": {c: par_mois[c].astype(int).tolist() for c in par_mois.columns}},
        "periodes": periodes,
        "cohortes": cohortes,
        "suivi": suivi,
        "suivi_eligibles": len(eligibles),
        "par_domaine": sorted(par_domaine, key=lambda x: -x["alertes"]),
        "issues": [{"issue": i, "alertes": int(n), "pct": pct(n, len(al))} for i, n in issues.items()],
    }
