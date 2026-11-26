import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file.resolve()) if False else Path(__file__).resolve().parents[1]
DATABASE = ROOT / "data" / "final" / "nha_packages.sqlite3"


def main() -> None:
    parser = argparse.ArgumentParser(description="Approve a reviewed item without source guessing.")
    parser.add_argument("--area", choices=[
        "procedure_code", "preauthorization", "investigation",
        "supporting_document", "icd10",
    ], required=True)
    parser.add_argument("--item-key", required=True)
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--database", type=Path, default=DATABASE)
    args = parser.parse_args()

    with sqlite3.connect(args.database) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        row = connection.execute(
            """
            SELECT review_id, review_status, candidate_status, source_document,
                   source_page, source_context
            FROM review_items WHERE area = ? AND item_key = ?
            """,
            (args.area, args.item_key),
        ).fetchone()
        if not row:
            raise SystemExit("Item has no review decision. Save a reviewed decision first.")
        review_id, status, candidate, document, page, context = row
        if status not in {"reviewed", "verified", "verified_same_procedure",
                          "verified_different_context", "duplicate"}:
            raise SystemExit(f"Item is in '{status}' state; only reviewed/source-verified decisions may be approved.")

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        payload = {
            "area": args.area,
            "item_key": args.item_key,
            "candidate_status": candidate,
            "source_document": document,
            "source_page": page,
            "source_context": context,
        }

        connection.execute(
            "UPDATE review_items SET review_status = 'approved', reviewer = ?, reviewed_at = ?, "
            "review_notes = COALESCE(review_notes, '') WHERE review_id = ?",
            (args.reviewer, now, review_id),
        )
        connection.execute(
            "INSERT OR IGNORE INTO approved_review_changes "
            "(review_id, area, item_key, change_payload, approved_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (review_id, args.area, args.item_key, json.dumps(payload), now),
        )

        if args.area == "preauthorization":
            package = connection.execute(
                "SELECT package_id FROM packages WHERE package_code = ?",
                (args.item_key,),
            ).fetchone()
            if not package:
                raise SystemExit("Approved preauthorization package code is not in the production database.")
            connection.execute(
                """
                UPDATE package_preauth_rules
                SET preauth_required = ?, preauth_type = ?,
                    requirement_text = 'Approved by human review.',
                    source_document = ?, source_page = ?, notes = ?
                WHERE package_id = ?
                """,
                (candidate, candidate, document or "HBP_2022.pdf", page,
                 "Human-approved from documented source context.", package[0]),
            )
            connection.execute(
                "UPDATE approved_review_changes SET applied_at = ? "
                "WHERE review_id = ?",
                (now, review_id),
            )

    print(f"Approved {args.area} item {args.item_key}")
    progress = ROOT / "scripts" / "manual_review_progress.py"
    subprocess.run([sys.executable, str(progress)], check=False)


if __name__ == "__main__":
    main()
