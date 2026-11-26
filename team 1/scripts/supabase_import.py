import argparse
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description="Import package JSON into Supabase.")
    parser.add_argument("--input", type=Path, default=Path("data/final/nha_packages_complete.json"))
    args = parser.parse_args()

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit(
            "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY before Supabase import."
        )
    if not args.input.is_file():
        raise SystemExit(f"Input file not found: {args.input}")

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    request = Request(
        f"{url.rstrip('/')}/rest/v1/nha_packages",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        },
    )
    with urlopen(request) as response:
        print(f"Supabase import HTTP status: {response.status}")


if __name__ == "__main__":
    main()
