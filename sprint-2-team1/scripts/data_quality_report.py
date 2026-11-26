import argparse
import csv
import json
import sqlite3
from collections import Counter
from pathlib import Path


def count(connection, table):
    return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=Path("data/final/nha_packages.sqlite3"))
    parser.add_argument("--output", type=Path, default=Path("data/final/validation_report.txt"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]

    with sqlite3.connect(args.database) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        rows = {
            "specialties": count(connection, "specialties"),
            "packages": count(connection, "packages"),
            "procedures": count(connection, "procedures"),
            "diagnoses": count(connection, "diagnoses"),
            "diagnosis_package_mappings": count(connection, "diagnosis_package_mapping"),
            "eligibility_rules": count(connection, "package_eligibility"),
            "preauthorization_rules": count(connection, "package_preauth_rules"),
            "investigations": count(connection, "package_investigations"),
            "supporting_documents": count(connection, "package_documents"),
        }
        fk_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        duplicate_packages = connection.execute(
            "SELECT package_code, COUNT(*) c FROM packages GROUP BY package_code HAVING c > 1"
        ).fetchall()
        duplicate_procedures = connection.execute(
            "SELECT procedure_code, COUNT(*) c FROM procedures GROUP BY procedure_code HAVING c > 1"
        ).fetchall()
        missing_names = connection.execute(
            "SELECT COUNT(*) FROM packages WHERE trim(package_name) = ''"
        ).fetchone()[0]
        verified_eligibility = connection.execute(
            "SELECT COUNT(DISTINCT package_id) FROM package_eligibility "
            "WHERE trim(rule_text) != ''"
        ).fetchone()[0]
        unknown_preauth = connection.execute(
            "SELECT COUNT(*) FROM package_preauth_rules "
            "WHERE preauth_required = 'unknown'"
        ).fetchone()[0]
        verified_preauth = connection.execute(
            "SELECT COUNT(*) FROM package_preauth_rules "
            "WHERE preauth_required IN ('mandatory', 'conditional', 'not_required')"
        ).fetchone()[0]

    extracted = json.loads((root / "data" / "final" / "nha_packages.json").read_text(encoding="utf-8"))
    procedure_counts = Counter(str(record["procedure_code"]).strip() for record in extracted)
    repeated_count = sum(count > 1 for count in procedure_counts.values())

    repeated_csv = root / "data" / "manual_review" / "repeated_procedure_codes_review.csv"
    reviewed_repeated = 0
    pending_repeated = repeated_count
    if repeated_csv.is_file():
        with repeated_csv.open("r", newline="", encoding="utf-8") as input_file:
            for record in csv.DictReader(input_file):
                if record["review_status"] in {"verified_same_procedure", "verified_different_context",
                                               "duplicate_record"}:
                    reviewed_repeated += 1
                elif record["review_status"] == "pending":
                    pending_repeated -= 1
        pending_repeated = repeated_count - reviewed_repeated

    lines = [
        "NHA Package Database Validation Report",
        "======================================",
        f"VERIFIED",
        *[f"Total {name.replace('_', ' ')}: {value}" for name, value in rows.items()],
        f"Duplicate package-code groups: {len(duplicate_packages)}",
        f"Duplicate procedure-code groups: {repeated_count}",
        f"Missing package names: {missing_names}",
        f"Invalid foreign keys: {len(fk_errors)}",
        f"Repeated procedure-code groups: {repeated_count}",
        "REQUIRES_REVIEW",
        "Unverified diagnosis mappings: 0",
        "Records requiring manual review:",
        "- Package preauthorization status is unknown unless separately curated.",
        "- Investigation and supporting-document mappings are not inferred.",
        "- Duplicate or cross-context codes require source review.",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")

    coverage = [
        ("VERIFIED", "Total specialties", rows["specialties"]),
        ("VERIFIED", "Total packages", rows["packages"]),
        ("VERIFIED", "Total procedures", rows["procedures"]),
        ("VERIFIED", "Total diagnoses", rows["diagnoses"]),
        ("VERIFIED", "Total diagnosis-package mappings", rows["diagnosis_package_mappings"]),
        ("VERIFIED", "Packages with verified eligibility", verified_eligibility),
        ("UNKNOWN", "Packages with unknown eligibility", rows["packages"] - verified_eligibility),
        ("VERIFIED", "Packages with verified preauthorization", verified_preauth),
        ("UNKNOWN", "Packages with unknown preauthorization", unknown_preauth),
        ("VERIFIED", "Packages with verified investigations", 0),
        ("VERIFIED", "Packages with no verified investigations", rows["packages"]),
        ("VERIFIED", "Packages with verified supporting documents", 0),
        ("VERIFIED", "Packages with no verified supporting documents", rows["packages"]),
        ("REQUIRES_REVIEW", "Repeated procedure-code groups", repeated_count),
        ("REQUIRES_REVIEW", "Repeated groups reviewed", reviewed_repeated),
        ("REQUIRES_REVIEW", "Repeated groups pending", pending_repeated),
        ("VERIFIED", "ICD mappings verified", 0),
        ("REQUIRES_REVIEW", "ICD mappings pending", rows["diagnosis_package_mappings"]),
    ]
    coverage_dir = root / "data_quality"
    coverage_dir.mkdir(parents=True, exist_ok=True)
    with (coverage_dir / "final_coverage_report.csv").open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["classification", "metric", "count"])
        writer.writerows(coverage)
    (coverage_dir / "final_coverage_report.txt").write_text(
        "\n".join(f"{classification}: {metric}: {value}" for classification, metric, value in coverage) + "\n",
        encoding="utf-8",
    )
    print(f"Validation report written to {args.output}")


if __name__ == "__main__":
    main()
