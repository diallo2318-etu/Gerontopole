"""Table de référence des professionnels et structures, avec leur RÔLE dans le parcours ICOPE.

Crée la table  ref_professionnel_role  (une ligne = un professionnel ou une structure dans un rôle) :

  role = levee_de_doute     : où confirmer une alerte du Step 1 (centres Agirc-Arrco + professionnels du référentiel
                              d'alertes dont le rôle est une levée de doute)
  role = bilan_prevention   : professionnels / pharmacies inscrits à l'annuaire « Mon bilan prévention »
  role = etape2             : professionnels du Step 2, par domaine (vision, audition, cognition...)

La colonne sert_levee_de_doute vaut VRAI pour les centres Agirc-Arrco et les bilans de prévention
(les deux lieux de levée de doute que l'on connaît), FAUX pour l'étape 2.

Chaque ligne garde : le numéro (RPPS ou FINESS), le nom, la profession, la commune (code INSEE) et
forme_icope (VRAI si la personne a été retrouvée dans la liste des professionnels formés ICOPE).
Aucune ligne n'est supprimée : une ligne sans commune garde code_insee vide.

À lancer APRÈS construire_entrepot.py (la table est effacée à chaque reconstruction de l'entrepôt) :
    python3 entrepot/construire_table_roles.py
"""
import duckdb

from construire_entrepot import ENTREPOT


def construire(con):
    con.execute("""
        CREATE OR REPLACE TABLE ref_professionnel_role AS
        WITH r1 AS (
            SELECT id_rpps, any_value(profession) AS profession, any_value(nom) AS nom, any_value(prenom) AS prenom
            FROM offre_rpps GROUP BY id_rpps),
        f1 AS (
            SELECT finess, any_value(nom) AS nom, any_value(categorie) AS categorie
            FROM offre_finess GROUP BY finess),
        formes AS (
            SELECT DISTINCT id_rpps_apparie AS id_rpps FROM offre_pro_forme_icope WHERE id_rpps_apparie IS NOT NULL),
        m1 AS (
            SELECT NULLIF(trim(CAST(identifiant_rpps AS VARCHAR)), '') AS rpps,
                   NULLIF(trim(CAST(identifiant_finess AS VARCHAR)), '') AS finess,
                   code_insee, qualite_localisation
            FROM offre_mon_bilan_prevention)

        -- Rôle « bilan de prévention » : les inscrits à l'annuaire Mon Bilan Prévention
        SELECT 'bilan_prevention' AS role, CAST(NULL AS VARCHAR) AS domaine,
               CASE WHEN m.rpps IS NOT NULL THEN 'rpps' WHEN m.finess IS NOT NULL THEN 'finess' ELSE 'sans_numero' END AS type_identifiant,
               coalesce(m.rpps, m.finess) AS identifiant,
               coalesce(r.nom || ' ' || r.prenom, f.nom) AS nom,
               coalesce(r.profession, f.categorie) AS profession,
               m.code_insee, m.qualite_localisation,
               coalesce(m.rpps IN (SELECT id_rpps FROM formes), FALSE) AS forme_icope,
               'offre_mon_bilan_prevention' AS table_origine
        FROM m1 m
        LEFT JOIN r1 r ON r.id_rpps = m.rpps
        LEFT JOIN f1 f ON f.finess = m.finess

        UNION ALL
        -- Rôle « levée de doute » : les centres Agirc-Arrco
        SELECT 'levee_de_doute', CAST(NULL AS VARCHAR), 'centre', CAST(id_centre AS VARCHAR),
               'Agirc-Arrco - ' || nom, 'Centre de prévention Agirc-Arrco (' || type || ')',
               code_insee, qualite_localisation, FALSE, 'offre_centre_agirc_arrco'
        FROM offre_centre_agirc_arrco

        UNION ALL
        -- Rôles issus du référentiel d'alertes (levée de doute ou Step 2, par domaine)
        SELECT CASE WHEN lower(v.role) LIKE '%doute%' THEN 'levee_de_doute' ELSE 'etape2' END,
               v.domaine, v.source, v.identifiant, v.nom, v.profession,
               v.code_insee, CAST(NULL AS VARCHAR),
               coalesce(v.identifiant IN (SELECT id_rpps FROM formes), FALSE),
               'v_offre_par_domaine'
        FROM v_offre_par_domaine v
    """)
    # Les centres Agirc-Arrco ET les bilans de prévention servent à la levée de doute (organigramme)
    con.execute("ALTER TABLE ref_professionnel_role ADD COLUMN sert_levee_de_doute BOOLEAN")
    con.execute("UPDATE ref_professionnel_role SET sert_levee_de_doute = role IN ('levee_de_doute', 'bilan_prevention')")


def main():
    con = duckdb.connect(str(ENTREPOT))
    print("Rôles trouvés dans le référentiel d'alertes (à vérifier) :")
    for role, n in con.execute("SELECT role, count(*) FROM v_offre_par_domaine GROUP BY 1 ORDER BY 1").fetchall():
        classe = "levee_de_doute" if "doute" in str(role).lower() else "etape2"
        print(f"  « {role} »  ->  {classe}  ({n} lignes)")
    construire(con)
    print("\nTable ref_professionnel_role créée :")
    print(con.execute("""
        SELECT role, type_identifiant, count(*) AS lignes,
               count(*) FILTER (WHERE code_insee IS NULL) AS sans_commune,
               count(*) FILTER (WHERE forme_icope) AS formes_icope
        FROM ref_professionnel_role GROUP BY 1, 2 ORDER BY 1, 2""").df().to_string(index=False))
    print("\nEtape 2, par domaine :")
    print(con.execute("""
        SELECT domaine, count(*) AS lignes FROM ref_professionnel_role
        WHERE role = 'etape2' GROUP BY 1 ORDER BY 1""").df().to_string(index=False))
    con.close()


if __name__ == "__main__":
    main()