"""Interface du parcours ICOPE (bloc 2).

On entre la commune (ou le code postal), l'âge et les alertes de la personne. La page affiche :
qui peut faire la levée de doute, puis les professionnels proposés pour chaque alerte (plan A / B / C)
avec la distance, l'évaluation approfondie (Step 2), et les actions de prévention proches.

Lancement (depuis la racine du projet, environnement activé, après construire_entrepot.py) :
    streamlit run interface/app.py
"""
import pandas as pd
import streamlit as st

from moteur_parcours import CAPACITES, connecter, parcours_personne, trouver_communes

st.set_page_config(page_title="Parcours ICOPE Normandie", page_icon="🧭", layout="wide")

# 5 profils types de la partie 1 (partie1_alertes/1_personnes_en_alerte.py), avec une commune d'exemple
PROFILS = {
    "Saisie libre": None,
    "1. Vision seule, 65 ans, hors sites": ("Vire Normandie", 65, ["vision"]),
    "2. Cognition + mobilité, 84 ans, Manche": ("50000", 84, ["cognition", "mobilite"]),
    "3. Psychologie, moins de 60 ans": ("76000", 55, ["psychologie"]),
    "4. Nutrition + mobilité, Calvados": ("14100", 75, ["nutrition", "mobilite"]),
    "5. Audition + vision, 74 ans": ("61000", 74, ["audition", "vision"]),
}
COLONNES = {"nom": "Nom", "detail": "Profession", "adresse": "Adresse", "code_postal": "Code postal",
            "commune": "Commune", "distance_km": "Distance (km)", "telephone": "Téléphone"}
NOMS_SOURCES = {"rpps_profession": "Annuaire Santé (RPPS)", "finess_categorie": "FINESS", "ipa": "IPA",
                "mon_bilan_prevention": "Mon bilan prévention", "agirc_arrco": "Agirc-Arrco",
                "pro_forme_icope": "Professionnels formés ICOPE", "maison_sport_sante": "Sport Santé Normandie",
                "conseil": "Conseil", "a_obtenir": "Liste à obtenir"}


@st.cache_resource
def connexion():
    return connecter()


def appliquer_profil():
    profil = PROFILS[st.session_state["profil"]]
    if profil is None:
        return
    commune, age, alertes = profil
    st.session_state["commune"] = commune
    st.session_state["age"] = age
    for d in CAPACITES:
        st.session_state[f"alerte_{d}"] = d in alertes


def afficher_plan(plan):
    for prop in plan.propositions:
        if prop.source == "conseil":
            st.info(f"💬 **{prop.valeur}**" + (f"\n\n{prop.remarque}" if prop.remarque else ""))
        elif prop.source == "a_obtenir":
            st.caption(f"⏳ {prop.valeur} : liste pas encore disponible.")
        elif prop.disponible:
            st.dataframe(prop.offres.rename(columns=COLONNES), hide_index=True, width="stretch")
            if prop.remarque:
                st.caption(prop.remarque)


def tableau_plans(etape):
    lignes = []
    for plan in etape.plans:
        for prop in plan.propositions:
            lignes.append({
                "Plan": plan.plan, "Qui": prop.valeur, "Source": NOMS_SOURCES.get(prop.source, prop.source),
                "Distance max (km)": prop.distance_max_km,
                "Le plus proche (km)": prop.plus_proche_km,
                "Disponible": "oui" if prop.disponible else ("à obtenir" if prop.source == "a_obtenir" else "non"),
            })
    return pd.DataFrame(lignes)


# ---------------------------------------------------------------- Saisie
st.title("🧭 Parcours ICOPE Normandie")
st.write("Après un test ICOPE : qui peut vérifier l'alerte, vers qui orienter la personne près de chez elle, "
         "et quelles actions de prévention lui proposer.")

with st.sidebar:
    st.header("Profils types")
    st.radio("Tester un profil de la partie 1", list(PROFILS), key="profil", on_change=appliquer_profil)
    st.caption("Profils de la partie 1, avec une commune d'exemple.")

st.session_state.setdefault("commune", "")
st.session_state.setdefault("age", 70)

col1, col2 = st.columns([2, 1])
texte_commune = col1.text_input("Commune ou code postal", key="commune", placeholder="ex. 50000 ou Saint-Lô")
age = col2.number_input("Âge", min_value=18, max_value=110, step=1, key="age")

st.write("**Alertes du test (Step 1)**")
cases = st.columns(3)
alertes = [d for i, (d, nom) in enumerate(CAPACITES.items()) if cases[i % 3].checkbox(nom, key=f"alerte_{d}")]

con = connexion().cursor()
if not texte_commune.strip():
    st.stop()
communes = trouver_communes(con, texte_commune)
if not communes:
    st.error(f"Commune introuvable en Normandie : « {texte_commune} »")
    st.stop()
commune = communes[0]
if len(communes) > 1:
    choix = st.selectbox("Plusieurs communes correspondent :", range(len(communes)),
                         format_func=lambda i: f"{communes[i].nom} ({communes[i].code_insee})")
    commune = communes[choix]

# ---------------------------------------------------------------- Résultat
st.divider()
st.subheader(f"{commune.nom}, {int(age)} ans, "
             + (f"alertes : {', '.join(CAPACITES[d].lower() for d in alertes)}" if alertes else "aucune alerte"))

etapes, prevention = parcours_personne(con, commune, int(age), alertes)

for etape in etapes:
    st.markdown(f"### {etape.titre}")
    if etape.note:
        st.caption(etape.note)
    retenu = etape.retenu
    if retenu is None:
        st.warning("Aucune offre trouvée dans les distances prévues.")
    else:
        if retenu.plan != "–":
            st.success(f"Plan {retenu.plan} retenu" + (" (le plan A est trop loin ou absent)" if retenu.plan != "A" else ""))
        afficher_plan(retenu)
    if retenu is None or retenu.plan != "–":
        with st.expander("Voir tous les plans (A, B, C) et les distances"):
            st.dataframe(tableau_plans(etape), hide_index=True, width="stretch")

if int(age) >= 60:
    st.markdown("### Actions de prévention près de chez la personne")
    st.caption("Pour les capacités sans alerte. Les actions qui couvrent le plus petit territoire sont proposées en premier.")
    if not prevention:
        st.write("Aucune action de prévention trouvée pour cette commune.")
    for d, plan, actions in prevention:
        st.markdown(f"**{CAPACITES[d]}**" + (" (actions générales, aucune action propre à cette capacité)" if plan != "A" else ""))
        st.dataframe(actions.rename(columns={"action": "Action", "porteur": "Porteur", "lieu": "Lieu", "date_fin": "Fin"}),
                     hide_index=True, width="stretch")

st.divider()
st.caption("Distances à vol d'oiseau entre les centres des communes. Sources : Annuaire Santé (RPPS), FINESS, "
           "Mon bilan prévention, Agirc-Arrco, Sport Santé Normandie, actions collectives des 5 départements. "
           "Les professionnels formés à ICOPE sont affichés sans nom (liste privée).")
