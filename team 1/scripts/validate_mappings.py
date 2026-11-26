import argparse
import re
import sqlite3
from pathlib import Path


ICD10_PATTERN = re.compile(r"^[A-Z]\d{2}(?:\.[A-Z0-9]{1,4})?$", re.IGNORECASE)


def validate_database(path: Path) -> list[str]:
    if not path.is_file():
        return [f"SQLite database not found: {path}"]

    errors = []
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")

        try:
            diagnoses = connection.execute(
                "SELECT diagnosis_id, icd10_code, diagnosis_name, source_reference "
                "FROM diagnoses"
            ).fetchall()
            mappings = connection.execute(
                """
                SELECT mapping_id, validation_status, evidence_source, rationale,
                       reviewed_by, reviewed_at
                FROM diagnosis_package_mapping
                """
            ).fetchall()
            catalog_counts = {
                table: connection.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]
                for table in ("packages", "procedures", "procedure_source_occurrences")
            }
        except sqlite3.OperationalError as exc:
            return [f"Database schema is incomplete: {exc}"]

        for diagnosis in diagnoses:
            code = diagnosis["icd10_code"] or ""
            if not ICD10_PATTERN.fullmatch(code.strip()):
                errors.append(
                    f"Diagnosis {diagnosis['diagnosis_id']}: invalid ICD-10 code "
                    f"'{code}'"
                )
            if not diagnosis["diagnosis_name"] or not diagnosis["diagnosis_name"].strip():
                errors.append(
                    f"Diagnosis {diagnosis['diagnosis_id']}: diagnosis_name is required"
                )
            if not diagnosis["source_reference"] or not diagnosis[
                "source_reference"
            ].strip():
                errors.append(
                    f"Diagnosis {diagnosis['diagnosis_id']}: source_reference is required"
                )

        invalid_relationships = connection.execute(
            """
            SELECT mapping.mapping_id
            FROM diagnosis_package_mapping AS mapping
            LEFT JOIN diagnoses AS diagnosis
                ON diagnosis.diagnosis_id = mapping.diagnosis_id
            LEFT JOIN packages AS package
                ON package.package_id = mapping.package_id
            LEFT JOIN procedures AS procedure
                ON procedure.procedure_id = mapping.procedure_id
                AND procedure.package_id = mapping.package_id
            WHERE diagnosis.diagnosis_id IS NULL
                OR package.package_id IS NULL
                OR procedure.procedure_id IS NULL
            """
        ).fetchall()
        errors.extend(
            f"Mapping {row['mapping_id']}: diagnosis, package, or procedure link is invalid"
            for row in invalid_relationships
        )

        approved_incomplete = connection.execute(
            """
            SELECT mapping_id
            FROM diagnosis_package_mapping
            WHERE validation_status = 'approved'
                AND (
                    trim(evidence_source) = ''
                    OR trim(rationale) = ''
                    OR trim(reviewed_by) = ''
                    OR trim(reviewed_at) = ''
                )
            """
        ).fetchall()
        errors.extend(
            f"Mapping {row['mapping_id']}: approved mapping lacks evidence/review details"
            for row in approved_incomplete
        )

        foreign_key_violations = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
        errors.extend(
            f"Foreign key violation in table '{row[0]}' row {row[1]}"
            for row in foreign_key_violations
        )

        status_counts = {
            row["validation_status"]: row["count"]
            for row in connection.execute(
                """
                SELECT validation_status, COUNT(*) AS count
                FROM diagnosis_package_mapping
                GROUP BY validation_status
                """
            )
        }

    print("Diagnosis mapping audit:")
    print(f"  Catalog packages: {catalog_counts['packages']}")
    print(f"  Catalog procedures: {catalog_counts['procedures']}")
    print(f"  Source occurrences: {catalog_counts['procedure_source_occurrences']}")
    print(f"  ICD-10 diagnoses: {len(diagnoses)}")
    print(f"  Diagnosis-to-package/procedure mappings: {len(mappings)}")
    print(f"  Mapping statuses: {status_counts or 'none'}")
    if not diagnoses or not mappings:
        print("  Mapping data is empty and awaiting curated, source-supported entries.")

    return errors


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate ICD-10 diagnosis-to-package/procedure mappings."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("data/final/nha_packages.sqlite3"),
        help="SQLite database path",
    )
    args = parser.parse_args()

    errors = validate_database(args.database)
    if errors:
        print("Mapping validation failed:")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    print(f"Mapping validation passed: {args.database}")


if __name__ == "__main__":
    main()
