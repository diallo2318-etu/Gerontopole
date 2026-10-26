"""Aide à l'orientation : après une alerte ICOPE, qui contacter près de chez la personne ?

Pour une commune et un domaine d'alerte, propose les professionnels (Annuaire
Santé) et les structures (FINESS) les plus proches, à partir du référentiel
entrepot/referentiel_alertes.csv. La distance est calculée à vol d'oiseau entre
les centres des communes.

Utilisation :
  python3 entrepot/orientation.py "Vire Normandie" vision
  python3 entrepot/orientation.py 61096 audition --nombre 10
"""
import argparse

import duckdb

from construire_entrepot import DOMAINES, ENTREPOT

DISTANCE_KM = """2 * 6371 * asin(sqrt(
    pow(sin(radians(c.latitude - o.latitude) / 2), 2)
    + cos(radians(o.latitude)) * cos(radians(c.latitude)) * pow(sin(radians(c.longitude - o.longitude) / 2), 2)))"""


def trouver_commune(con, commune):
    """Accepte un code INSEE ou un nom, avec ou sans accents ni tirets (« Saint-Lo », « saint lo »)."""
    if commune.isdigit():
        r = con.execute("SELECT code_insee, nom FROM ref_commune WHERE code_insee = ?", [commune]).fetchall()
    else:
        cle = "regexp_replace(lower(strip_accents({})), '[^a-z0-9]+', ' ', 'g')"
        r = con.execute(f"SELECT code_insee, nom FROM ref_commune WHERE {cle.format('nom')} = {cle.format('?')}",
                        [commune]).fetchall()
        if not r:
            r = con.execute(f"SELECT code_insee, nom FROM ref_commune WHERE {cle.format('nom')} LIKE '%' || {cle.format('?')} || '%'"
                            " ORDER BY population DESC", [commune]).fetchall()
    if not r:
        raise SystemExit(f"Commune introuvable en Normandie : {commune}")
    return r[0]


def proposer(con, code_insee, domaine, nombre=5):
    """Les professionnels et structures les plus proches : `nombre` propositions pour chaque métier
    (ou catégorie d'établissement) utile à la capacité, pour qu'aucun métier n'en masque un autre."""
    return con.execute(f"""
        WITH o AS (
            SELECT v.*, c.latitude, c.longitude,
                   coalesce(v.identifiant IN (
                       SELECT identifiant_rpps FROM offre_mon_bilan_prevention WHERE identifiant_rpps IS NOT NULL
                       UNION SELECT identifiant_finess FROM offre_mon_bilan_prevention WHERE identifiant_finess IS NOT NULL
                   ), false) AS mon_bilan_prevention
            FROM v_offre_par_domaine v JOIN ref_commune c USING (code_insee)
            WHERE v.domaine = ?
        ), d AS (
            -- un professionnel qui exerce sur plusieurs sites n'apparaît qu'une fois : au site le plus proche
            SELECT o.*, round({DISTANCE_KM}, 1) AS distance_km
            FROM o, ref_commune c WHERE c.code_insee = ?
            QUALIFY row_number() OVER (PARTITION BY o.critere, o.identifiant ORDER BY distance_km, o.telephone NULLS LAST) = 1
        )
        SELECT role, ordre, critere, profession, coalesce(savoir_faire, '') AS specialite, nom, coalesce(structure, '') AS structure,
               adresse, code_postal, distance_km, coalesce(telephone, '') AS telephone, mon_bilan_prevention
        FROM d
        QUALIFY row_number() OVER (PARTITION BY critere ORDER BY distance_km, nom) <= ?
        ORDER BY ordre, distance_km
    """, [domaine, code_insee, nombre]).df()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("commune", help="nom ou code INSEE de la commune")
    p.add_argument("domaine", choices=DOMAINES)
    p.add_argument("--nombre", type=int, default=3, help="nombre de propositions par métier")
    a = p.parse_args()
    con = duckdb.connect(str(ENTREPOT), read_only=True)
    code, nom = trouver_commune(con, a.commune)
    df = proposer(con, code, a.domaine, a.nombre)
    print(f"Alerte {a.domaine} - personne domiciliée à {nom} ({code})\n")
    for role, groupe in df.groupby("role", sort=False):
        print(f"== {role.replace('_', ' ')}")
        for r in groupe.itertuples():
            spec = f" ({r.specialite})" if r.specialite else ""
            mbp = "  [Mon Bilan Prévention]" if r.mon_bilan_prevention else ""
            print(f"  {r.distance_km:5.1f} km  {r.profession}{spec} - {r.nom}  {r.adresse}, {r.code_postal}  {r.telephone}{mbp}")
        print()


if __name__ == "__main__":
    main()
