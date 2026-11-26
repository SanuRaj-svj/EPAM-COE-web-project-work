import csv
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with path.open("r", newline="", encoding="utf-8") as input_file:
        reader = csv.DictReader(input_file)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def save_review(
    database: Path,
    area: str,
    item_key: str,
    source_document: str,
    source_page: str,
    source_context: str,
    candidate_status: str,
    new_status: str,
    reviewer: str,
    notes: str,
) -> None:
    page = int(source_page) if str(source_page).isdigit() else None
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        row = connection.execute(
            "SELECT review_id, review_status FROM review_items WHERE area = ? AND item_key = ?",
            (area, item_key),
        ).fetchone()
        if row:
            review_id, previous_status = row
            connection.execute(
                """
                UPDATE review_items
                SET source_document = ?, source_page = ?, source_context = ?,
                    candidate_status = ?, review_status = ?, reviewer = ?,
                    reviewed_at = ?, review_notes = ?
                WHERE review_id = ?
                """,
                (source_document, page, source_context, candidate_status,
                 new_status, reviewer, utc_now(), notes, review_id),
            )
        else:
            cursor = connection.execute(
                """
                INSERT INTO review_items (
                    area, item_key, source_document, source_page, source_context,
                    candidate_status, review_status, reviewer, reviewed_at, review_notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (area, item_key, source_document, page, source_context,
                 candidate_status, new_status, reviewer, utc_now(), notes),
            )
            review_id = cursor.lastrowid
            previous_status = "pending"

        connection.execute(
            """
            INSERT INTO review_history (
                review_id, previous_status, new_status, reviewer, reviewed_at,
                review_notes, source_document, source_page
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (review_id, previous_status, new_status, reviewer, utc_now(),
             notes, source_document, page),
        )
    project_root = Path(database).resolve().parents[2]
    progress = project_root / "scripts" / "manual_review_progress.py"
    subprocess.run([sys.executable, str(progress)], check=False)
