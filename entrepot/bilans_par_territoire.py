"""Bilans de prévention par territoire : qui pourrait les proposer, et qui les propose (est inscrit à l'annuaire).

Pour chaque département et chaque profession, compare :
  - les professionnels « habilités » : médecins généralistes, infirmiers, sages-femmes, masseurs-kinésithérapeutes
    (liste donnée par la page « bilan prévention aux âges clés » de l'Assurance maladie), pris dans
    l'annuaire RPPS (offre_rpps) ;
  - les professionnels « inscrits » à l'annuaire Mon Bilan Prévention (offre_mon_bilan_prevention).
Puis les pharmacies (qui sont inscrites par leur numéro FINESS, pas par un numéro RPPS).

ATTENTION : « inscrit à l'annuaire » ne veut pas dire « fait des bilans » : on n'a pas le nombre de bilans réalisés.
L'inscription n'est pas obligatoire : un professionnel non inscrit peut faire des bilans.

Par défaut seuls les professionnels libéraux sont comptés (un infirmier d'hôpital ne propose pas de bilan en ville).
Utiliser --tous pour compter tous les modes d'exercice, --tous-medecins pour inclure les médecins spécialistes.

Utilisation :  python3 entrepot/bilans_par_territoire.py
Écrit deux fichiers CSV agrégés (aucune donnée nominative) dans DONNEES_ICOPE.
"""
import argparse

import duckdb

from construire_entrepot import DONNEES, ENTREPOT

PROFESSIONS = ("Infirmier", "Médecin", "Masseur-Kinésithérapeute", "Sage-Femme")


def calculer(con, liberal=True, generalistes=True):
    filtre = "AND o.mode_exercice = 'liberal'" if liberal else ""
    # Les inscrits à l'annuaire sont presque tous des généralistes : on compare avec les généralistes
    med = "AND (o.profession <> 'Médecin' OR o.savoir_faire LIKE '%Médecine Générale%')" if generalistes else ""
    prof = ", ".join(f"'{p}'" for p in PROFESSIONS)
    con.execute(f"""
        CREATE TEMP TABLE hab AS
        SELECT DISTINCT c.departement, c.code_epci, o.id_rpps,
               CASE WHEN o.profession = 'Médecin' AND {str(generalistes).upper()} THEN 'Médecin généraliste' ELSE o.profession END AS profession
        FROM offre_rpps o JOIN ref_commune c ON c.code_insee = o.code_insee
        WHERE o.profession IN ({prof}) {filtre} {med}""")
    con.execute("""
        CREATE TEMP TABLE ins AS
        SELECT DISTINCT identifiant_rpps AS id_rpps FROM offre_mon_bilan_prevention WHERE identifiant_rpps IS NOT NULL""")
    dep = con.execute("""
        WITH h AS (SELECT DISTINCT departement, id_rpps, profession FROM hab)
        SELECT h.departement, h.profession, count(*) AS habilites, count(i.id_rpps) AS inscrits,
               round(100.0 * count(i.id_rpps) / count(*), 1) AS pct_inscrits
        FROM h LEFT JOIN ins i USING (id_rpps)
        GROUP BY ALL ORDER BY 1, 2""").df()
    epci = con.execute("""
        WITH h AS (SELECT DISTINCT departement, code_epci, id_rpps FROM hab)
        SELECT h.departement, h.code_epci, e.nom_epci, count(*) AS habilites, count(i.id_rpps) AS inscrits
        FROM h LEFT JOIN ins i USING (id_rpps)
        LEFT JOIN (SELECT DISTINCT code_epci, nom_epci FROM ref_commune) e USING (code_epci)
        GROUP BY ALL ORDER BY inscrits, habilites DESC""").df()
    pharm = con.execute("""
        WITH p AS (SELECT c.departement, f.finess FROM offre_finess f JOIN ref_commune c ON c.code_insee = f.code_insee
                   WHERE lower(f.categorie) LIKE '%pharmacie%'),
             i AS (SELECT DISTINCT identifiant_finess AS finess FROM offre_mon_bilan_prevention WHERE identifiant_finess IS NOT NULL)
        SELECT p.departement, count(*) AS pharmacies, count(i.finess) AS inscrites
        FROM p LEFT JOIN i USING (finess) GROUP BY ALL ORDER BY 1""").df()
    return dep, epci, pharm


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--tous", action="store_true", help="compter tous les modes d'exercice, pas seulement les libéraux")
    a.add_argument("--tous-medecins", action="store_true", help="compter tous les médecins, pas seulement les généralistes")
    args = a.parse_args()
    con = duckdb.connect(str(ENTREPOT), read_only=True)
    dep, epci, pharm = calculer(con, liberal=not args.tous, generalistes=not args.tous_medecins)
    print("== Par département et profession (habilités = dans l'annuaire RPPS ; inscrits = dans l'annuaire Mon Bilan Prévention)")
    print(dep.to_string(index=False))
    print("\n== Pharmacies (FINESS) inscrites à l'annuaire")
    print(pharm.to_string(index=False) if len(pharm) else "  aucune pharmacie trouvée dans offre_finess (vérifier les catégories)")
    print("\n== Intercommunalités sans aucun inscrit, parmi les plus dotées en professionnels habilités ")
    sans = epci[epci["inscrits"] == 0].sort_values("habilites", ascending=False)
    print(sans.head(15).to_string(index=False))
    print(f"\n{len(sans)} intercommunalités sur {len(epci)} n'ont aucun professionnel inscrit.")
    dep.to_csv(DONNEES / "bilans_prevention_par_departement.csv", sep=";", index=False)
    epci.to_csv(DONNEES / "bilans_prevention_par_epci.csv", sep=";", index=False)
    print(f"\nFichiers écrits dans {DONNEES}")
    con.close()


if __name__ == "__main__":
    main()