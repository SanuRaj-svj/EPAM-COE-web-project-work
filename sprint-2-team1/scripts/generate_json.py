import argparse
import json
import sqlite3
from pathlib import Path


def complete_package(connection: sqlite3.Connection, package_id: int) -> dict:
    package = connection.execute(
        """
        SELECT p.package_code, p.package_name, s.specialty_code, s.specialty_name
        FROM packages p
        JOIN specialties s ON s.specialty_id = p.specialty_id
        WHERE p.package_id = ?
        """,
        (package_id,),
    ).fetchone()

    procedures = [
        {
            "procedure_code": row[0],
            "procedure_name": row[1],
            "tier3_price": row[2],
            "tier2_price": row[3],
            "tier1_price": row[4],
            "stratification_remarks": row[5],
            "implant_mapped": row[6],
            "implant_cost": row[7],
        }
        for row in connection.execute(
            """
            SELECT procedure_code, procedure_name, tier3_price, tier2_price,
                   tier1_price, stratification_remarks, implant_mapped, implant_cost
            FROM procedures WHERE package_id = ?
            ORDER BY procedure_code
            """,
            (package_id,),
        )
    ]
    eligibility = [
        {
            "rule_type": row[0],
            "rule_text": row[1],
            "required": bool(row[2]),
            "source_document": row[3],
            "source_page": row[4],
            "notes": row[5],
        }
        for row in connection.execute(
            """
            SELECT rule_type, rule_text, required, source_document, source_page, notes
            FROM package_eligibility WHERE package_id = ? ORDER BY id
            """,
            (package_id,),
        )
    ]
    preauth_row = connection.execute(
        """
        SELECT preauth_required, preauth_type, requirement_text,
               required_documents, source_document, source_page, notes
        FROM package_preauth_rules WHERE package_id = ?
        """,
        (package_id,),
    ).fetchone()
    preauthorization = {
        "status": preauth_row[0] if preauth_row else "unknown",
        "required": preauth_row[0] if preauth_row else "unknown",
        "type": preauth_row[1] if preauth_row else "unknown",
        "rules": [] if not preauth_row else [preauth_row[2]],
        "required_documents": preauth_row[3] if preauth_row else "",
        "source": {
            "document": preauth_row[4] if preauth_row else "HBP_2022.pdf",
            "page": preauth_row[5] if preauth_row else None,
        },
        "notes": preauth_row[6] if preauth_row else "",
    }

    mappings = [
        {"diagnosis_id": row[0], "diagnosis_name": row[1], "icd10_code": row[2],
         "validation_status": row[3]}
        for row in connection.execute(
            """
            SELECT d.diagnosis_id, d.diagnosis_name, d.icd10_code, m.validation_status
            FROM diagnosis_package_mapping m
            JOIN diagnoses d ON d.diagnosis_id = m.diagnosis_id
            WHERE m.package_id = ?
            """,
            (package_id,),
        )
    ]

    return {
        "package_code": package[0],
        "package_name": package[1],
        "specialty": {"code": package[2], "name": package[3]},
        "procedures": procedures,
        "diagnosis_mappings": mappings,
        "eligibility": eligibility,
        "preauthorization": preauthorization,
        "investigations": [],
        "documents": [],
        "source": {"document": "HBP_2022.pdf", "page": min(
            (row[0] for row in connection.execute(
                """
                SELECT pso.source_page
                FROM procedure_source_occurrences pso
                JOIN procedures pr ON pr.procedure_id = pso.procedure_id
                WHERE pr.package_id = ?
                """,
                (package_id,),
            )),
            default=None,
        )},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate complete package JSON from SQLite.")
    parser.add_argument("--database", type=Path, default=Path("data/final/nha_packages.sqlite3"))
    parser.add_argument("--output", type=Path, default=Path("data/final/nha_packages_complete.json"))
    args = parser.parse_args()

    with sqlite3.connect(args.database) as connection:
        connection.row_factory = sqlite3.Row
        package_ids = [
            row[0] for row in connection.execute(
                "SELECT DISTINCT package_id FROM packages ORDER BY package_id"
            )
        ]
        packages = [complete_package(connection, package_id) for package_id in package_ids]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as output:
        json.dump(packages, output, ensure_ascii=False, indent=2)
    print(f"Generated {len(packages)} complete packages at {args.output}")


if __name__ == "__main__":
    main()
