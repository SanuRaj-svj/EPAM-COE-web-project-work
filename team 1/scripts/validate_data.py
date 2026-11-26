import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

try:
    from .package_schema import FIELDS, PRICE_FIELDS, REQUIRED_TEXT_FIELDS
except ImportError:
    from package_schema import FIELDS, PRICE_FIELDS, REQUIRED_TEXT_FIELDS


OPTIONAL_FIELDS = {"implant_mapped", "implant_cost"}


def is_missing(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def load_data(path: Path) -> tuple[object | None, list[str]]:
    if not path.is_file():
        return None, [f"Data file not found: {path}"]

    try:
        with path.open("r", encoding="utf-8") as input_file:
            data = json.load(input_file)
    except json.JSONDecodeError as exc:
        return None, [f"Invalid JSON: {exc}"]

    if not isinstance(data, list):
        return None, ["Top-level JSON value must be an array"]
    return data, []


def validate_records(data: list[object]) -> list[str]:
    if not data:
        return ["Package data must contain at least one row"]

    errors = []
    for index, record in enumerate(data):
        if not isinstance(record, dict):
            errors.append(f"Record {index}: expected an object")
            continue

        missing_fields = set(FIELDS) - record.keys()
        if missing_fields:
            errors.append(
                f"Record {index}: missing fields: "
                f"{', '.join(sorted(missing_fields))}"
            )
            continue

        for field in REQUIRED_TEXT_FIELDS:
            value = record[field]
            if not isinstance(value, str) or not value.strip():
                errors.append(f"Record {index}: {field} is required")

        for field in PRICE_FIELDS:
            value = record[field]
            if is_missing(value):
                if field not in OPTIONAL_FIELDS:
                    errors.append(f"Record {index}: {field} is required")
            elif isinstance(value, bool) or not isinstance(value, (int, float, str)):
                errors.append(
                    f"Record {index}: {field} must be a price or source value"
                )

        implant_mapped = record["implant_mapped"]
        if implant_mapped is not None and not isinstance(implant_mapped, str):
            errors.append(f"Record {index}: implant_mapped must be text or null")

        source_page = record["source_page"]
        if (
            isinstance(source_page, bool)
            or not isinstance(source_page, int)
            or source_page < 1
        ):
            errors.append(f"Record {index}: source_page must be a positive integer")

    return errors


def validate(path: Path) -> list[str]:
    data, errors = load_data(path)
    if errors:
        return errors
    return validate_records(data)


def _key_value(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def print_audit(data: list[object]) -> None:
    rows = [record for record in data if isinstance(record, dict)]
    specialty_codes = {
        _key_value(record.get("specialty_code"))
        for record in rows
        if not is_missing(record.get("specialty_code"))
    }
    specialty_labels = {
        (
            _key_value(record.get("specialty_code")),
            _key_value(record.get("specialty_name")),
        )
        for record in rows
        if not is_missing(record.get("specialty_code"))
        and not is_missing(record.get("specialty_name"))
    }
    package_codes = {
        _key_value(record.get("package_code"))
        for record in rows
        if not is_missing(record.get("package_code"))
    }
    specialty_packages = {
        (
            _key_value(record.get("specialty_code")),
            _key_value(record.get("package_code")),
        )
        for record in rows
        if not is_missing(record.get("specialty_code"))
        and not is_missing(record.get("package_code"))
    }

    procedure_counts = Counter()
    procedure_contexts = defaultdict(set)
    exact_record_groups = defaultdict(list)

    for record in rows:
        procedure_code = record.get("procedure_code")
        if not is_missing(procedure_code):
            procedure_key = str(procedure_code).strip()
            procedure_counts[procedure_key] += 1
            procedure_contexts[procedure_key].add(
                (
                    _key_value(record.get("specialty_code")),
                    _key_value(record.get("package_code")),
                )
            )

        signature = tuple(
            _key_value(record.get(field))
            for field in FIELDS
            if field != "source_page"
        )
        exact_record_groups[signature].append(record)

    repeated_procedures = {
        code: count for code, count in procedure_counts.items() if count > 1
    }
    repeated_contexts = sum(
        len(procedure_contexts[code]) > 1 for code in repeated_procedures
    )
    exact_duplicate_groups = [
        group for group in exact_record_groups.values() if len(group) > 1
    ]
    exact_duplicate_extra_rows = sum(len(group) - 1 for group in exact_duplicate_groups)
    exact_duplicate_examples = []
    for group in exact_duplicate_groups:
        code = (
            group[0].get("procedure_code")
            or group[0].get("package_code")
            or "unknown"
        )
        pages = sorted(
            {
                record["source_page"]
                for record in group
                if isinstance(record.get("source_page"), int)
            }
        )
        exact_duplicate_examples.append(
            f"{code} (pages {', '.join(str(page) for page in pages) or 'unknown'})"
        )

    print("Audit summary:")
    print(f"  Package/procedure rows: {len(rows)}")
    print(
        f"  Specialties: {len(specialty_codes)} codes; "
        f"{len(specialty_labels)} code/name pairs"
    )
    print(
        f"  Packages: {len(package_codes)} package codes; "
        f"{len(specialty_packages)} specialty/package pairs"
    )
    print(f"  Unique procedure codes: {len(procedure_counts)}")
    print(
        f"  Repeated procedure codes: {len(repeated_procedures)} groups; "
        f"{sum(count - 1 for count in repeated_procedures.values())} extra rows"
    )
    print(
        f"  Repeated codes used in multiple specialty/package contexts: "
        f"{repeated_contexts}"
    )
    print(
        f"  Identical records excluding source_page: "
        f"{exact_duplicate_extra_rows} extra rows"
    )

    print("Rate availability:")
    for field in sorted(PRICE_FIELDS):
        missing = sum(is_missing(record.get(field)) for record in rows)
        not_applicable = sum(
            isinstance(record.get(field), str)
            and record[field].strip().upper() in {"NA", "N/A"}
            for record in rows
        )
        available = len(rows) - missing - not_applicable
        print(
            f"  {field}: {available} valued, {not_applicable} marked NA, "
            f"{missing} blank"
        )

    print("Missing values by field:")
    for field in FIELDS:
        missing = sum(is_missing(record.get(field)) for record in rows)
        print(f"  {field}: {missing}")

    if repeated_procedures:
        samples = ", ".join(sorted(repeated_procedures)[:10])
        print(
            "Review note: repeated procedure codes are retained; they may occur "
            "across specialty/package contexts."
        )
        print(f"  Repeated-code examples: {samples}")
    if exact_duplicate_extra_rows:
        print(
            "Review note: identical source rows (excluding page number) were "
            "found; inspect them before removing any."
        )
        print(
            "  Identical-row examples: "
            + "; ".join(exact_duplicate_examples[:10])
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate and audit the cleaned NHA package/procedure JSON."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/final/nha_packages.json"),
        help="Final JSON path",
    )
    args = parser.parse_args()

    data, errors = load_data(args.input)
    if errors:
        print("Validation failed:")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    errors = validate_records(data)
    print_audit(data)

    if errors:
        print("Validation failed:")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    print(f"Validation passed: {args.input}")


if __name__ == "__main__":
    main()
