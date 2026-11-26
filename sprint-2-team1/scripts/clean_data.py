import argparse
import csv
import json
import re
import sys
from pathlib import Path

try:
    from .package_schema import FIELDS, PRICE_FIELDS
except ImportError:
    from package_schema import FIELDS, PRICE_FIELDS


def set_csv_field_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def clean_value(field: str, value: str | None) -> str | int | None:
    text = clean_text(value)
    if not text:
        return None
    if field in PRICE_FIELDS:
        normalized_price = text.replace(",", "")
        if normalized_price.isdigit():
            return int(normalized_price)
    if field == "source_page":
        return int(text)
    return text


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize extracted package rows and write the final JSON."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/extracted/packages.csv"),
        help="Extracted CSV path",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/final/nha_packages.json"),
        help="Cleaned JSON path",
    )
    args = parser.parse_args()

    if not args.input.is_file():
        raise FileNotFoundError(f"Extracted CSV not found: {args.input}")

    set_csv_field_limit()
    records = []
    with args.input.open("r", newline="", encoding="utf-8-sig") as input_file:
        reader = csv.DictReader(input_file)
        missing_fields = set(FIELDS) - set(reader.fieldnames or [])
        if missing_fields:
            raise ValueError(
                f"Extracted CSV is missing fields: {', '.join(sorted(missing_fields))}"
            )

        for row in reader:
            record = {
                field: clean_value(field, row.get(field))
                for field in FIELDS
            }
            records.append(record)

    if not records:
        raise ValueError(f"No package rows found in {args.input}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as output_file:
        json.dump(records, output_file, ensure_ascii=False, indent=2)

    print(f"Cleaned {len(records)} package/procedure rows to {args.output}")


if __name__ == "__main__":
    main()
