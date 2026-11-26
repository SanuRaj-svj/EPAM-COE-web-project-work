import argparse
import json
import sqlite3
from pathlib import Path

try:
    from .validate_data import validate_records
except ImportError:
    from validate_data import validate_records


PROCEDURE_FIELDS = (
    "procedure_code",
    "procedure_name",
    "tier3_price",
    "tier2_price",
    "tier1_price",
    "stratification_remarks",
    "implant_mapped",
    "implant_cost",
)


def database_text(value: object) -> str:
    return "" if value is None else str(value)


def load_packages(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(f"Package JSON not found: {path}")

    with path.open("r", encoding="utf-8") as input_file:
        records = json.load(input_file)
    if not isinstance(records, list):
        raise ValueError("Package JSON must contain an array of records")

    errors = validate_records(records)
    if errors:
        raise ValueError("Package JSON is invalid: " + "; ".join(errors[:10]))
    return records


def import_records(connection: sqlite3.Connection, records: list[dict]) -> None:
    eligibility_patterns = (
        "criteria",
        "tbsa",
        "% total",
        "adult",
        "child",
        "voltage",
        "pregnan",
        " kg",
        " cm",
        "year",
        "month",
    )
    for row_number, record in enumerate(records, start=1):
        specialty_values = (
            database_text(record["specialty_code"]),
            database_text(record["specialty_name"]),
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO specialties (specialty_code, specialty_name)
            VALUES (?, ?)
            """,
            specialty_values,
        )
        specialty = connection.execute(
            """
            SELECT specialty_id FROM specialties
            WHERE specialty_code = ? AND specialty_name = ?
            """,
            specialty_values,
        ).fetchone()
        specialty_id = specialty[0]

        package_values = (
            specialty_id,
            database_text(record["package_code"]),
            database_text(record["package_name"]),
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO packages
                (specialty_id, package_code, package_name)
            VALUES (?, ?, ?)
            """,
            package_values,
        )
        package = connection.execute(
            """
            SELECT package_id FROM packages
            WHERE specialty_id = ? AND package_code = ? AND package_name = ?
            """,
            package_values,
        ).fetchone()
        package_id = package[0]

        procedure_values = (
            package_id,
            *(database_text(record[field]) for field in PROCEDURE_FIELDS),
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO procedures (
                package_id,
                procedure_code,
                procedure_name,
                tier3_price,
                tier2_price,
                tier1_price,
                stratification_remarks,
                implant_mapped,
                implant_cost
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            procedure_values,
        )
        procedure = connection.execute(
            """
            SELECT procedure_id FROM procedures
            WHERE package_id = ?
                AND procedure_code = ?
                AND procedure_name = ?
                AND tier3_price = ?
                AND tier2_price = ?
                AND tier1_price = ?
                AND stratification_remarks = ?
                AND implant_mapped = ?
                AND implant_cost = ?
            """,
            procedure_values,
        ).fetchone()
        procedure_id = procedure[0]

        connection.execute(
            """
            INSERT INTO procedure_source_occurrences
                (source_row_number, procedure_id, source_page)
            VALUES (?, ?, ?)
            ON CONFLICT(source_row_number) DO UPDATE SET
                procedure_id = excluded.procedure_id,
                source_page = excluded.source_page
            """,
            (row_number, procedure_id, record["source_page"]),
        )

        rule_text = database_text(record["procedure_name"])
        rule_text_lower = rule_text.lower()
        if any(pattern in rule_text_lower for pattern in eligibility_patterns):
            connection.execute(
                """
                INSERT OR IGNORE INTO package_eligibility (
                    package_id, rule_type, rule_text, required,
                    source_document, source_page, notes
                ) VALUES (?, 'clinical', ?, 1, 'HBP_2022.pdf', ?, '')
                """,
                (package_id, rule_text, record["source_page"]),
            )

    packages = connection.execute(
        "SELECT package_id FROM packages"
    ).fetchall()
    for (package_id,) in packages:
        source_page = connection.execute(
            """
            SELECT MIN(source_page)
            FROM procedure_source_occurrences
            JOIN procedures ON procedures.procedure_id = procedure_source_occurrences.procedure_id
            WHERE procedures.package_id = ?
            """,
            (package_id,),
        ).fetchone()[0]
        connection.execute(
            """
            INSERT OR IGNORE INTO package_preauth_rules (
                package_id, preauth_required, preauth_type,
                requirement_text, required_documents,
                source_document, source_page, notes
            ) VALUES (?, 'unknown', 'unknown', '',
                      '', 'HBP_2022.pdf', ?, 'Pre-authorization status was not established by the extracted package master.')
            """,
            (package_id, source_page),
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the SQLite HBP catalog and ICD-10 mapping schema."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/final/nha_packages.json"),
        help="Validated package/procedure JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/final/nha_packages.sqlite3"),
        help="SQLite database path",
    )
    args = parser.parse_args()

    records = load_packages(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    schema_path = Path(__file__).with_name("database_schema.sql")

    with sqlite3.connect(args.output) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(schema_path.read_text(encoding="utf-8"))
        connection.execute(
            """
            INSERT INTO schema_metadata (metadata_key, metadata_value)
            VALUES ('schema_version', '1')
            ON CONFLICT(metadata_key) DO UPDATE SET
                metadata_value = excluded.metadata_value
            """
        )
        import_records(connection, records)

        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"Database contains foreign key violations: {violations}")

        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "specialties",
                "packages",
                "procedures",
                "procedure_source_occurrences",
                "diagnoses",
                "diagnosis_package_mapping",
                "diagnosis_synonyms",
                "package_eligibility",
                "package_preauth_rules",
                "investigations",
                "package_investigations",
                "documents",
                "package_documents",
            )
        }

    print(f"SQLite database ready: {args.output}")
    for table, count in counts.items():
        print(f"  {table}: {count}")
    print(
        "Diagnosis and mapping records are preserved but not imported from the "
        "package PDF; add curated ICD-10 data separately."
    )


if __name__ == "__main__":
    main()
