import argparse
import csv
import re
from pathlib import Path

try:
    from .package_schema import FIELDS, SOURCE_COLUMN_INDEX
except ImportError:
    from package_schema import FIELDS, SOURCE_COLUMN_INDEX


def clean_cell(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def is_header(row: list[str | None]) -> bool:
    values = [clean_cell(value).lower() for value in row]
    return any("specialty code" in value for value in values) and any(
        "procedure code" in value for value in values
    )


def extract_packages(pdf_path: Path) -> list[dict[str, str | int]]:
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError(
            "PDF table extraction requires pdfplumber. "
            "Install dependencies with `python -m pip install -r requirements.txt`."
        ) from exc

    records = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables()
            if not tables:
                raise ValueError(f"No table found on PDF page {page_number}")

            for table_number, table in enumerate(tables, start=1):
                for row_number, row in enumerate(table, start=1):
                    if len(row) != len(SOURCE_COLUMN_INDEX):
                        if not any(clean_cell(value) for value in row):
                            continue
                        raise ValueError(
                            f"Unexpected {len(row)}-column row on page "
                            f"{page_number}, table {table_number}, row {row_number}"
                        )

                    cells = [clean_cell(value) for value in row]
                    if not any(cells) or is_header(row):
                        continue

                    if "package master - hbp-2022" in " ".join(cells).lower():
                        continue

                    missing_codes = [
                        field
                        for field in ("specialty_code", "package_code", "procedure_code")
                        if not cells[SOURCE_COLUMN_INDEX[field]]
                    ]
                    if missing_codes:
                        if all(
                            not cell or cell.upper() == "NA"
                            for cell in cells
                        ):
                            continue
                        raise ValueError(
                            f"Missing {', '.join(missing_codes)} on PDF page "
                            f"{page_number}, table {table_number}, row {row_number}"
                        )

                    record = {
                        field: cells[column_index]
                        for field, column_index in SOURCE_COLUMN_INDEX.items()
                    }
                    record["source_page"] = page_number
                    records.append(record)

    if not records:
        raise ValueError(f"No package/procedure rows extracted from {pdf_path}")
    return records


def excel_value(field: str, value: str | int) -> str | int | None:
    if value == "":
        return None
    if field in {
        "tier3_price",
        "tier2_price",
        "tier1_price",
        "implant_cost",
    } and isinstance(value, str):
        normalized_price = value.replace(",", "")
        if normalized_price.isdigit():
            return int(normalized_price)
    return value


def write_excel(path: Path, records: list[dict[str, str | int]]) -> None:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError as exc:
        raise RuntimeError(
            "Excel output requires openpyxl. "
            "Install dependencies with `python -m pip install -r requirements.txt`."
        ) from exc

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Package Master"
    worksheet.append(FIELDS)

    for record in records:
        worksheet.append(
            [excel_value(field, record[field]) for field in FIELDS]
        )

    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions
    for cell in worksheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E78")
        cell.alignment = Alignment(wrap_text=True, vertical="top")

    for column in worksheet.columns:
        column_letter = column[0].column_letter
        max_width = max(
            (len(str(cell.value)) for cell in column if cell.value is not None),
            default=0,
        )
        worksheet.column_dimensions[column_letter].width = min(max_width + 2, 60)

    workbook.save(path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract NHA HBP-2022 package tables from the source PDF."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/raw/HBP_2022.pdf"),
        help="Source PDF path",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/extracted/packages.csv"),
        help="Extracted CSV path",
    )
    parser.add_argument(
        "--xlsx-output",
        type=Path,
        default=Path("data/extracted/packages.xlsx"),
        help="Excel workbook path for manual review",
    )
    args = parser.parse_args()

    if not args.input.is_file():
        raise FileNotFoundError(f"Source PDF not found: {args.input}")

    records = extract_packages(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.xlsx_output.parent.mkdir(parents=True, exist_ok=True)

    with args.output.open("w", newline="", encoding="utf-8-sig") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(records)

    write_excel(args.xlsx_output, records)
    print(
        f"Extracted {len(records)} package/procedure rows from {args.input} "
        f"to {args.output} and {args.xlsx_output}"
    )


if __name__ == "__main__":
    main()
