import argparse
import json
import sqlite3
from pathlib import Path

from manual_review_common import read_csv, save_review, write_csv

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


def get_context(pdf_path: Path, page_number: int, procedure_code: str) -> str:
    if pdfplumber is None or not pdf_path.is_file():
        return (
            f"HBP_2022.pdf page {page_number}: "
            "source extraction dependency unavailable in the active interpreter; "
            "use the original PDF for manual context review."
        )
    with pdfplumber.open(pdf_path) as pdf:
        start = max(0, page_number - 2)
        end = min(len(pdf.pages), page_number + 1)
        matches = []
        for index in range(start, end):
            text = pdf.pages[index].extract_text() or ""
            lower_text = text.lower()
            search_from = 0
            while True:
                match_at = lower_text.find(procedure_code.lower(), search_from)
                if match_at < 0:
                    break
                context_start = max(0, match_at - 350)
                context_end = min(len(text), match_at + len(procedure_code) + 600)
                matches.append(
                    f"Page {index + 1}: ...{text[context_start:context_end]}..."
                )
                search_from = match_at + len(procedure_code)
        return "\n\n".join(matches) if matches else (
            f"No nearby extracted text matched {procedure_code} on pages "
            f"{start + 1}-{end}."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Review a procedure code against extracted database and PDF context."
    )
    parser.add_argument("procedure_code", nargs="?")
    parser.add_argument("--decision", choices=[
        "pending", "verified_same_procedure", "verified_different_context",
        "duplicate", "requires_review",
    ])
    parser.add_argument("--notes", default="")
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--database", type=Path, default=Path("data/final/nha_packages.sqlite3"))
    parser.add_argument("--pdf", type=Path, default=Path("data/raw/HBP_2022.pdf"))
    parser.add_argument("--json", type=Path, default=Path("data/final/nha_packages.json"))
    args = parser.parse_args()
    if not args.procedure_code:
        csv_path = Path(__file__).resolve().parents[1] / "data" / "manual_review" / "procedure_code_review.csv"
        if csv_path.is_file():
            _, rows = read_csv(csv_path)
            pending = next((row for row in rows if row["review_status"] == "pending"), None)
            if pending:
                page_numbers = [
                    int(page.strip())
                    for page in pending["source_page"].split("|")
                    if page.strip().isdigit()
                ]
                context = "\n\n".join(
                    get_context(args.pdf, page, pending["procedure_code"])
                    for page in page_numbers
                )
                print(f"Next pending procedure code: {pending['procedure_code']}")
                print(f"Source: {pending['source_document']} page {pending['source_page']}")
                print(f"Source context:\n{context or pending['source_context']}")
                print("Run with PROCEDURE_CODE --decision STATUS --notes TEXT")
                return
        print("No pending procedure-code review items.")
        return

    with sqlite3.connect(args.database) as connection:
        rows = connection.execute(
            """
            SELECT p.package_code, p.package_name, s.specialty_code,
                   s.specialty_name, pr.procedure_name,
                   pso.source_page
            FROM procedures pr
            JOIN packages p ON p.package_id = pr.package_id
            JOIN specialties s ON s.specialty_id = p.specialty_id
            JOIN procedure_source_occurrences pso
              ON pso.procedure_id = pr.procedure_id
            WHERE pr.procedure_code = ?
            ORDER BY pso.source_page, p.package_code
            """,
            (args.procedure_code,),
        ).fetchall()

    if not rows:
        print(f"No record found for procedure code: {args.procedure_code}")
        return

    if args.decision:
        csv_path = Path(__file__).resolve().parents[1] / "data" / "manual_review" / "procedure_code_review.csv"
        fieldnames, csv_rows = read_csv(csv_path)
        matched = False
        pages = sorted({row[5] for row in rows})
        source_context = "\n\n".join(
            get_context(args.pdf, page, args.procedure_code) for page in pages
        )
        for csv_row in csv_rows:
            if csv_row["procedure_code"] == args.procedure_code:
                csv_row["review_status"] = args.decision
                csv_row["review_notes"] = args.notes
                csv_row["source_context"] = source_context
                matched = True
        if not matched:
            raise SystemExit(f"No procedure review row found: {args.procedure_code}")
        write_csv(csv_path, fieldnames, csv_rows)
        save_review(
            args.database, "procedure_code", args.procedure_code,
            "HBP_2022.pdf", str(pages[0]),
            source_context,
            args.decision, args.decision, args.reviewer, args.notes,
        )
        print(f"Saved review for {args.procedure_code}: {args.decision}")
        return

    for package_code, package_name, specialty_code, specialty_name, procedure_name, page in rows:
        print(f"Procedure code: {args.procedure_code}")
        print(f"Package code: {package_code}")
        print(f"Package name: {package_name}")
        print(f"Specialty: {specialty_code} - {specialty_name}")
        print(f"Procedure name: {procedure_name}")
        print(f"Relevant source page: {page}")
        print("Nearby extracted source context:")
        print(get_context(args.pdf, page, args.procedure_code))
        print("-" * 80)


if __name__ == "__main__":
    main()
