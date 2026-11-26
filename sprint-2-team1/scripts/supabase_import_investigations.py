import csv
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "manual_review" / "investigation_review.csv"
TABLE_URL_PATH = "/rest/v1/investigation_review_queue"
BATCH_SIZE = 100
REQUIRED_FIELDS = {
    "package_code",
    "package_name",
    "specialty_code",
    "specialty_name",
    "investigation_name",
    "mandatory",
    "source_document",
    "source_page",
    "source_field",
    "source_text",
    "source_context",
    "review_status",
    "review_notes",
}


def load_candidates(input_path: Path) -> list[dict]:
    with input_path.open("r", newline="", encoding="utf-8") as input_file:
        reader = csv.DictReader(input_file)
        missing_fields = REQUIRED_FIELDS.difference(reader.fieldnames or [])
        if missing_fields:
            raise ValueError(
                "Investigation review CSV is missing required columns: "
                + ", ".join(sorted(missing_fields))
            )

        candidates = []
        for line_number, row in enumerate(reader, start=2):
            if not row["investigation_name"] or row["investigation_name"] == "requires source review":
                raise ValueError(
                    f"Invalid investigation candidate on CSV line {line_number}."
                )
            if row["mandatory"] not in {
                "unknown", "mandatory", "conditional", "not_required"
            }:
                raise ValueError(
                    f"Invalid mandatory status on CSV line {line_number}."
                )
            if not row["source_text"] or not row["source_context"]:
                raise ValueError(
                    f"Missing source evidence on CSV line {line_number}."
                )
            row["source_page"] = int(row["source_page"])
            candidates.append(row)
    return candidates


def post_batch(url: str, key: str, candidates: list[dict]) -> None:
    request = Request(
        f"{url.rstrip('/')}{TABLE_URL_PATH}",
        data=json.dumps(candidates, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=ignore-duplicates,return=minimal",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            if response.status not in (200, 201, 204):
                raise RuntimeError(
                    f"Supabase import returned unexpected HTTP status {response.status}."
                )
    except HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        if error.code == 404 and "PGRST205" in details:
            raise RuntimeError(
                "Supabase cannot find public.investigation_review_queue. "
                "Run scripts/supabase_investigation_review_schema.sql in the "
                "same Supabase project, then retry the import."
            ) from error
        raise RuntimeError(
            f"Supabase import failed with HTTP {error.code}: {details}"
        ) from error


def main() -> None:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit(
            "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the process environment."
        )

    input_path = Path(os.getenv("INVESTIGATION_REVIEW_CSV", str(DEFAULT_INPUT)))
    if not input_path.is_file():
        raise SystemExit(f"Investigation review CSV not found: {input_path}")
    candidates = load_candidates(input_path)
    for offset in range(0, len(candidates), BATCH_SIZE):
        post_batch(url, key, candidates[offset:offset + BATCH_SIZE])
    print(
        f"Imported {len(candidates)} investigation candidates to "
        "public.investigation_review_queue. Existing rows were left unchanged."
    )


if __name__ == "__main__":
    main()
