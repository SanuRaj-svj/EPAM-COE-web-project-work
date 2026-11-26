import argparse
import json
import subprocess
import sys
from pathlib import Path


def run(script: str, *args: str) -> None:
    subprocess.run([sys.executable, script, *args], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Repeatable extracted-data import pipeline.")
    parser.add_argument("--input", type=Path, default=Path("data/extracted/packages.csv"))
    parser.add_argument("--json", type=Path, default=Path("data/final/nha_packages.json"))
    parser.add_argument("--database", type=Path, default=Path("data/final/nha_packages.sqlite3"))
    args = parser.parse_args()

    run("scripts/clean_data.py", "--input", str(args.input), "--output", str(args.json))
    run("scripts/validate_data.py", "--input", str(args.json))
    run("scripts/build_database.py", "--input", str(args.json), "--output", str(args.database))
    run("scripts/validate_mappings.py", "--database", str(args.database))
    run("scripts/generate_json.py", "--database", str(args.database),
        "--output", str(args.database.with_name("nha_packages_complete.json")))

    print("Import pipeline completed.")


if __name__ == "__main__":
    main()
