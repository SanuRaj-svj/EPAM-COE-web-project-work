import csv
import json
import re
import sqlite3
import subprocess
import sys
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "data" / "final" / "nha_packages.json"
DATABASE_PATH = ROOT / "data" / "final" / "nha_packages.sqlite3"
OUTPUT_DIR = ROOT / "data" / "manual_review"
SOURCE_PDF = ROOT / "data" / "raw" / "HBP_2022.pdf"

INVESTIGATION_TERMS = re.compile(
    r"\b(?:investigations?|work[\s/-]*ups?|tests?|screening|cultures?|"
    r"ultrasounds?|imaging|serology|biops(?:y|ies)|PCR|VEEG|EEG|ECG|"
    r"MRI|CT|RGU|MCU|X[\s-]?rays?|scans?|angiograms?|venography|"
    r"diagnostic|monitoring|urinalysis|endoscopy|cystoscopy)\b",
    re.IGNORECASE,
)
INVESTIGATION_SEGMENTS = re.compile(r"[,;:.\n+/]|\b(?:and|or)\b", re.IGNORECASE)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


@lru_cache(maxsize=1)
def source_pdf_pages() -> tuple[str, ...]:
    if pdfplumber is None:
        raise RuntimeError(
            "PDF extraction requires pdfplumber in the active Python environment."
        )
    if not SOURCE_PDF.is_file():
        raise FileNotFoundError(f"Source PDF not found: {SOURCE_PDF}")
    with pdfplumber.open(SOURCE_PDF) as pdf:
        return tuple(page.extract_text() or "" for page in pdf.pages)


def page_context(source_page: int) -> str:
    pages = source_pdf_pages()
    if source_page < 1 or source_page > len(pages):
        raise ValueError(f"Source page is outside the PDF: {source_page}")
    return pages[source_page - 1][:3000]


def investigation_mentions(source_text: str) -> list[tuple[str, str]]:
    mentions: dict[str, tuple[str, str]] = {}
    for match in INVESTIGATION_TERMS.finditer(source_text):
        left_boundaries = [
            boundary.end()
            for boundary in INVESTIGATION_SEGMENTS.finditer(
                source_text, 0, match.start()
            )
        ]
        right_boundary = INVESTIGATION_SEGMENTS.search(source_text, match.end())
        left = max(left_boundaries, default=0)
        right = right_boundary.start() if right_boundary else len(source_text)
        raw_phrase = source_text[left:right]
        phrase = re.sub(r"\s+", " ", raw_phrase).strip(" .")
        phrase = re.sub(
            r"^(?:includes?|including|and|or)\s+",
            "",
            phrase,
            flags=re.IGNORECASE,
        )
        if len(phrase) > 120:
            words = list(re.finditer(r"\S+", raw_phrase))
            match_offset = match.start() - left
            match_word = next(
                (index for index, word in enumerate(words)
                 if word.start() <= match_offset < word.end()),
                None,
            )
            if match_word is not None:
                start = max(0, match_word - 3)
                end = min(len(words), match_word + 5)
                phrase = re.sub(
                    r"\s+", " ",
                    raw_phrase[words[start].start():words[end - 1].end()],
                ).strip(" .")
        if phrase:
            mentions.setdefault(phrase.casefold(), (phrase, match.group(0)))
    return list(mentions.values())


def pdf_evidence_excerpt(source_page: int, package_code: str, term: str) -> str:
    page_text = re.sub(r"\s+", " ", source_pdf_pages()[source_page - 1])
    term_matches = list(re.finditer(re.escape(term), page_text, re.IGNORECASE))
    code_matches = list(re.finditer(re.escape(package_code), page_text, re.IGNORECASE))
    if not term_matches:
        return page_context(source_page)

    term_match = min(
        term_matches,
        key=lambda item: min(
            (abs(item.start() - code.start()) for code in code_matches),
            default=0,
        ),
    )
    start = max(0, term_match.start() - 180)
    end = min(len(page_text), term_match.end() + 220)
    prefix = "..." if start else ""
    suffix = "..." if end < len(page_text) else ""
    return f"{prefix}{page_text[start:end]}{suffix}"


def generate_investigation_review() -> int:
    with sqlite3.connect(DATABASE_PATH) as connection:
        source_rows = connection.execute(
            """
            SELECT p.package_id, p.package_code, p.package_name,
                   s.specialty_code, s.specialty_name, e.source_page,
                   'eligibility' AS source_field, e.rule_text AS source_text
            FROM package_eligibility e
            JOIN packages p ON p.package_id = e.package_id
            JOIN specialties s ON s.specialty_id = p.specialty_id
            UNION ALL
            SELECT p.package_id, p.package_code, p.package_name,
                   s.specialty_code, s.specialty_name, occurrence.source_page,
                   'procedure_name', pr.procedure_name
            FROM procedures pr
            JOIN packages p ON p.package_id = pr.package_id
            JOIN specialties s ON s.specialty_id = p.specialty_id
            JOIN procedure_source_occurrences occurrence
              ON occurrence.procedure_id = pr.procedure_id
            UNION ALL
            SELECT p.package_id, p.package_code, p.package_name,
                   s.specialty_code, s.specialty_name, occurrence.source_page,
                   'stratification_remarks', pr.stratification_remarks
            FROM procedures pr
            JOIN packages p ON p.package_id = pr.package_id
            JOIN specialties s ON s.specialty_id = p.specialty_id
            JOIN procedure_source_occurrences occurrence
              ON occurrence.procedure_id = pr.procedure_id
            WHERE trim(pr.stratification_remarks) NOT IN ('', 'NA')
            ORDER BY 2, 4, 6
            """
        ).fetchall()

    existing_path = OUTPUT_DIR / "investigation_review.csv"
    prior_reviews: dict[tuple[str, str, str, str], dict] = {}
    if existing_path.is_file():
        with existing_path.open("r", newline="", encoding="utf-8") as existing_file:
            for row in csv.DictReader(existing_file):
                key = (
                    row.get("specialty_code", ""),
                    row.get("package_code", ""),
                    row.get("investigation_name", "").casefold(),
                    row.get("source_page", ""),
                )
                prior_reviews[key] = row

    rows_by_key: dict[tuple[int, str, int], dict] = {}
    missing_source_pages = 0
    for (package_id, package_code, package_name, specialty_code, specialty_name,
         source_page, source_field, source_text) in source_rows:
        if source_page is None:
            missing_source_pages += len(investigation_mentions(source_text))
            continue
        for investigation_name, term in investigation_mentions(source_text):
            key = (package_id, investigation_name.casefold(), source_page)
            if key in rows_by_key:
                continue
            prior_key = (
                specialty_code, package_code, investigation_name.casefold(),
                str(source_page),
            )
            prior = prior_reviews.get(prior_key, {})
            rows_by_key[key] = {
                "package_code": package_code,
                "package_name": package_name,
                "specialty_code": specialty_code,
                "specialty_name": specialty_name,
                "investigation_name": investigation_name,
                "mandatory": prior.get("mandatory") or "unknown",
                "source_document": "HBP_2022.pdf",
                "source_page": source_page,
                "source_field": source_field,
                "source_text": source_text,
                "source_context": pdf_evidence_excerpt(
                    source_page, package_code, term
                ),
                "review_status": prior.get("review_status") or "pending",
                "review_notes": prior.get("review_notes", ""),
            }

    fields = [
        "package_code", "package_name", "specialty_code", "specialty_name",
        "investigation_name", "mandatory", "source_document", "source_page",
        "source_field", "source_text", "source_context", "review_status",
        "review_notes",
    ]
    rows = sorted(
        rows_by_key.values(),
        key=lambda row: (
            row["package_code"], row["specialty_code"], row["source_page"],
            row["investigation_name"].casefold(),
        ),
    )
    write_csv(existing_path, fields, rows)
    print(f"Investigation candidates: {len(rows)}")
    if missing_source_pages:
        print(f"Skipped candidates without source-page references: {missing_source_pages}")
    return len(rows)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Generate manual-review CSV files.")
    parser.add_argument(
        "--investigations-only",
        action="store_true",
        help="Refresh only the source-backed investigation review queue.",
    )
    args = parser.parse_args()
    if args.investigations_only:
        generate_investigation_review()
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "manual_review_progress.py")],
            check=True,
        )
        return

    records = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    occurrences = defaultdict(list)
    for record in records:
        occurrences[str(record["procedure_code"]).strip()].append(record)

    repeated_rows = []
    for code in sorted(occurrences):
        rows = occurrences[code]
        if len(rows) < 2:
            continue
        repeated_rows.append({
            "procedure_code": code,
            "occurrence_count": len(rows),
            "package_codes": " | ".join(sorted({str(r["package_code"]) for r in rows})),
            "package_names": " | ".join(sorted({str(r["package_name"]) for r in rows})),
            "specialties": " | ".join(sorted({
                f'{r["specialty_code"]} - {r["specialty_name"]}' for r in rows
            })),
            "procedure_names": " | ".join(sorted({str(r["procedure_name"]) for r in rows})),
            "source_pages": " | ".join(sorted({
                str(r["source_page"]) for r in rows
            }, key=lambda value: int(value))),
            "review_status": "pending",
            "review_notes": "Repeated code requires source-context comparison; no duplicate has been removed.",
        })

    write_csv(
        OUTPUT_DIR / "repeated_procedure_codes_review.csv",
        ["procedure_code", "occurrence_count", "package_codes", "package_names",
         "specialties", "procedure_names", "source_pages", "review_status", "review_notes"],
        repeated_rows,
    )

    procedure_code_rows = []
    for code in sorted(occurrences):
        rows = occurrences[code]
        if len(rows) < 2:
            continue
        pages = sorted({int(row["source_page"]) for row in rows})
        procedure_code_rows.append({
            "procedure_code": code,
            "occurrence_count": len(rows),
            "package_code": " | ".join(sorted({str(row["package_code"]) for row in rows})),
            "package_name": " | ".join(sorted({str(row["package_name"]) for row in rows})),
            "specialty": " | ".join(sorted({
                f'{row["specialty_code"]} - {row["specialty_name"]}' for row in rows
            })),
            "procedure_name": " | ".join(sorted({str(row["procedure_name"]) for row in rows})),
            "source_document": "HBP_2022.pdf",
            "source_page": " | ".join(str(page) for page in pages),
            "source_context": page_context(pages[0]),
            "review_status": "pending",
            "review_notes": "",
        })
    write_csv(
        OUTPUT_DIR / "procedure_code_review.csv",
        ["procedure_code", "occurrence_count", "package_code", "package_name",
         "specialty", "procedure_name", "source_document", "source_page",
         "source_context", "review_status", "review_notes"],
        procedure_code_rows,
    )

    with sqlite3.connect(DATABASE_PATH) as connection:
        package_rows = connection.execute(
            """
            SELECT p.package_code, p.package_name,
                   MIN(pso.source_page)
            FROM packages p
            JOIN procedures pr ON pr.package_id = p.package_id
            JOIN procedure_source_occurrences pso
              ON pso.procedure_id = pr.procedure_id
            GROUP BY p.package_id, p.package_code, p.package_name
            ORDER BY p.package_code
            """
        ).fetchall()

    preauth_rows = [{
        "package_code": code,
        "package_name": name,
        "preauth_status": "unknown",
        "current_status": "unknown",
        "candidate_status": "unknown",
        "source_document": "HBP_2022.pdf",
        "source_page": page,
        "source_context": page_context(int(page)) if isinstance(page, int) else "Manual source review required.",
        "source_text": "No explicit preauthorization statement was found in the extracted package master.",
        "review_status": "pending",
        "reviewer_notes": "",
        "review_notes": "",
    } for code, name, page in package_rows]
    write_csv(
        OUTPUT_DIR / "preauthorization_review.csv",
        ["package_code", "package_name", "preauth_status", "current_status",
         "candidate_status", "source_document", "source_page", "source_context",
         "source_text", "review_status", "reviewer_notes", "review_notes"],
        preauth_rows,
    )

    generate_investigation_review()
    unresolved_documents = [{
        "package_code": code,
        "package_name": name,
        "document_name": "requires source review",
        "mandatory": "unknown",
        "source_document": "HBP_2022.pdf",
        "source_page": page,
        "source_context": page_context(int(page)) if isinstance(page, int) else "Manual source review required.",
        "review_status": "pending",
        "review_notes": "No supporting document has been inferred.",
    } for code, name, page in package_rows]
    write_csv(
        OUTPUT_DIR / "document_review.csv",
        ["package_code", "package_name", "document_name", "mandatory",
         "source_document", "source_page", "source_context", "review_status", "review_notes"],
        unresolved_documents,
    )
    write_csv(
        OUTPUT_DIR / "icd10_review.csv",
        ["diagnosis_name", "candidate_icd10_code", "candidate_description",
         "source", "review_status", "review_notes"],
        [],
    )

    issues = [
        ["VALIDATION-001", "CRITICAL", "ICD-10 diagnosis mappings",
         "0 mappings are currently stored", "requires source-supported clinical/ICD review"],
        ["VALIDATION-002", "HIGH", "Repeated procedure codes",
         f"{len(repeated_rows)} groups require source-context review", "compare each code against PDF pages"],
        ["VALIDATION-003", "HIGH", "Preauthorization requirements",
         "1433 package records are unknown", "verify explicit requirements from authoritative source"],
        ["VALIDATION-004", "HIGH", "Investigation requirements",
         "0 verified investigations", "no automatic population; manual source review required"],
        ["VALIDATION-005", "HIGH", "Supporting documents",
         "0 verified documents", "no automatic population; manual source review required"],
        ["VALIDATION-006", "MEDIUM", "Repeated package codes",
         "300 package-code groups appear more than once", "determine whether specialty/package context is legitimate"],
        ["VALIDATION-007", "MEDIUM", "Identical source rows",
         "19 extra identical records excluding source_page", "review page/context differences"],
        ["VALIDATION-008", "MEDIUM", "Missing optional implant values",
         "24 implant_mapped and 25 implant_cost values missing", "retained as blank; verify extraction omissions"],
        ["VALIDATION-009", "LOW", "Foreign keys",
         "0 violations found", "continue running integrity validation"],
        ["VALIDATION-010", "LOW", "Missing package names",
         "0 missing package names", "no immediate action"],
    ]
    write_csv(
        OUTPUT_DIR / "validation_manual_review.csv",
        ["issue_id", "severity", "issue", "current_state", "required_action"],
        [dict(zip(["issue_id", "severity", "issue", "current_state", "required_action"], row))
         for row in issues],
    )
    print(f"Repeated procedure groups: {len(repeated_rows)}")
    print(f"Preauthorization review rows: {len(preauth_rows)}")
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "manual_review_progress.py")],
        check=False,
    )


if __name__ == "__main__":
    main()
