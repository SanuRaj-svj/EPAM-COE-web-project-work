import argparse
from pathlib import Path

from manual_review_common import read_csv, save_review, write_csv


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "manual_review" / "preauthorization_review.csv"
DATABASE_PATH = ROOT / "data" / "final" / "nha_packages.sqlite3"


def main() -> None:
    parser = argparse.ArgumentParser(description="Review preauthorization candidates.")
    parser.add_argument("--package-code")
    parser.add_argument("--decision", choices=["mandatory", "conditional", "not_required", "unknown", "pending"])
    parser.add_argument("--notes", default="")
    parser.add_argument("--reviewer", default="")
    args = parser.parse_args()

    fieldnames, rows = read_csv(CSV_PATH)
    if args.package_code:
        row = next((item for item in rows if item["package_code"] == args.package_code), None)
        if not row:
            raise SystemExit(f"Package not found in review data: {args.package_code}")
        if not args.decision:
            raise SystemExit("Use --decision to save a review.")
        if args.decision == "pending":
            row["review_status"] = "pending"
            candidate = "unknown"
        else:
            candidate = args.decision
            row["candidate_status"] = candidate
            row["review_status"] = "reviewed"
            row["reviewer_notes"] = args.notes
        save_review(
            DATABASE_PATH, "preauthorization", args.package_code,
            row["source_document"], row["source_page"], row["source_context"],
            candidate, row["review_status"], args.reviewer, args.notes,
        )
        write_csv(CSV_PATH, fieldnames, rows)
        print(f"Saved {args.package_code}: {row['review_status']}")
        return

    pending = next((row for row in rows if row["review_status"] in {"pending", "requires_manual_review"}), None)
    if not pending:
        print("No pending preauthorization items.")
        return
    print(f"Package code: {pending['package_code']}")
    print(f"Package name: {pending['package_name']}")
    print(f"Current status: {pending['current_status']}")
    print(f"Candidate status: {pending['candidate_status']}")
    print(f"Source: {pending['source_document']} page {pending['source_page']}")
    print(f"Source context:\n{pending['source_context']}")
    print("Use --package-code CODE --decision {mandatory|conditional|not_required|unknown} --notes TEXT")


if __name__ == "__main__":
    main()
