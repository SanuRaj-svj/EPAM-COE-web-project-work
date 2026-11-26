import csv
import sqlite3
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "data" / "final" / "nha_packages.sqlite3"
OUTPUT = ROOT / "data_quality" / "manual_review_progress.txt"
MANUAL_DIR = ROOT / "data" / "manual_review"


def csv_counts(path: Path) -> tuple[int, Counter]:
    if not path.is_file():
        return 0, Counter()
    with path.open("r", newline="", encoding="utf-8") as input_file:
        rows = list(csv.DictReader(input_file))
    status_field = "review_status"
    return len(rows), Counter(row[status_field] for row in rows)


def main() -> None:
    procedure_total, procedure_status = csv_counts(
        MANUAL_DIR / "procedure_code_review.csv"
    )
    preauth_total, preauth_status = csv_counts(
        MANUAL_DIR / "preauthorization_review.csv"
    )
    investigation_total, investigation_status = csv_counts(
        MANUAL_DIR / "investigation_review.csv"
    )
    document_total, document_status = csv_counts(
        MANUAL_DIR / "document_review.csv"
    )
    icd_total, icd_status = csv_counts(MANUAL_DIR / "icd10_review.csv")

    with sqlite3.connect(DATABASE) as connection:
        approved = Counter({
            row[0]: row[1]
            for row in connection.execute(
                "SELECT area, COUNT(*) FROM review_items "
                "WHERE review_status = 'approved' GROUP BY area"
            )
        })

    lines = [
        "NHA Manual Review Progress",
        "==========================",
        "Procedure-code review:",
        f"Total: {procedure_total}",
        f"Reviewed: {sum(procedure_status[k] for k in procedure_status if k not in {'pending', 'requires_review'})}",
        f"Approved: {approved['procedure_code']}",
        f"Rejected: {procedure_status['duplicate']}",
        f"Requires review: {procedure_status['requires_review']}",
        f"Pending: {procedure_status['pending']}",
        "",
        "Preauthorization:",
        f"Total: {preauth_total}",
        f"Verified: {approved['preauthorization']}",
        f"Pending: {preauth_status['pending']}",
        "",
        "Investigations:",
        f"Verified: {approved['investigation']}",
        f"Pending: {investigation_total}",
        "",
        "Documents:",
        f"Verified: {approved['supporting_document']}",
        f"Pending: {document_total}",
        "",
        "ICD-10:",
        f"Verified: {approved['icd10']}",
        f"Pending: {icd_status['pending']}",
        "",
    ]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Manual review progress written to {OUTPUT}")


if __name__ == "__main__":
    main()
