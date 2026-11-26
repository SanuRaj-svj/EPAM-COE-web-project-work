# NHA Package Database

> This shared copy excludes the HBP source PDF and generated manual-review CSVs,
> which can contain source excerpts. To reproduce extraction or generate review
> candidates, obtain an authorized source PDF and place it at
> `data/raw/HBP_2022.pdf`. Do not commit the PDF or manual-review CSV exports.

This project can extract HBP-2022 package and procedure tables into CSV and
Excel for review, then clean and validate a JSON dataset. Diagnosis mapping is
intentionally out of scope.

## Official sources and raw document

- [NHA HBP 2.2 Manual](https://nha.gov.in/img/resources/HBP-2.2-manual.pdf)
- [NHA Operation Manual for AB PM-JAY](https://nha.gov.in/img/resources/Operation%20Manual%20for%20AB%20PM-JAY.pdf)

When using an authorized source copy, keep it unchanged at
`data/raw/HBP_2022.pdf`. Its first page identifies it as “Package Master -
HBP-2022.” The HBP 2.2 link currently responds with an HTML portal page rather
than a PDF; do not overwrite the preserved raw document with that response.
Check the NHA site for an updated official download before replacing the source.

## Project structure

```text
nha-package-database/
├── data/
│   ├── raw/
│   │   └── HBP_2022.pdf
│   ├── extracted/
│   │   ├── packages.csv
│   │   └── packages.xlsx
│   └── final/
│       ├── nha_packages.json
│       └── nha_packages.sqlite3
├── scripts/
│   ├── package_schema.py
│   ├── extract_data.py
│   ├── clean_data.py
│   ├── validate_data.py
│   ├── database_schema.sql
│   ├── build_database.py
│   └── validate_mappings.py
├── requirements.txt
└── README.md
```

## Package master fields

The PDF contains searchable text tables, so table extraction is used; OCR is not
needed for this source. The extractor reads all table pages and retains repeated
procedure rows rather than deduplicating them.

The structured output includes:

- `specialty_code`, `specialty_name`
- `package_code`, `package_name`
- `procedure_code`, `procedure_name`
- `tier3_price`, `tier2_price`, `tier1_price`
- `stratification_remarks`
- `implant_mapped`, `implant_cost`
- `source_page` for manual verification against the PDF

The PDF provides three tier-specific price columns, not a single
`procedure_price` or `total_package_price` column. The project keeps the
published Tier 3/2/1 values separately instead of deriving or inventing a total.
Blank implant fields remain blank/null, and source values such as `NA` are
preserved.

## Setup and usage

Run commands from the `nha-package-database` directory:

```powershell
python -m pip install -r requirements.txt
python scripts/extract_data.py
python scripts/clean_data.py
python scripts/validate_data.py
python scripts/build_database.py
python scripts/validate_mappings.py
```

Extraction writes both `data/extracted/packages.csv` and
`data/extracted/packages.xlsx`. The workbook has filters and a frozen header row
to support manual review. Each script accepts `--input` and `--output` options;
the extractor also accepts `--xlsx-output`.

The validator reports specialty, package, procedure-code, and rate counts;
per-field missing values; repeated procedure codes; and identical records
(ignoring source page). Repeated codes and optional blank implant fields are
reported for review, not silently removed.

Review the workbook against the PDF before using the data for operational or
claims decisions.

## Phase 6: ICD-10 diagnosis mapping

`data/final/nha_packages.sqlite3` stores a normalized specialty → package →
procedure catalog, an ICD-10 `diagnoses` table, and a
`diagnosis_package_mapping` table linking each diagnosis to a specific procedure
and its package. The mapping table enforces that the selected procedure belongs
to the selected package.

The database contains the package catalog, but the diagnosis and mapping tables
are intentionally empty. No diagnosis-to-package relationship is inferred from
the HBP PDF or added from the conceptual Cataract example. Add mappings only
after separately curating and validating an authoritative clinical source.
Mappings default to `pending`; setting one to `approved` requires an evidence
source, rationale, reviewer, and review timestamp. Run
`python scripts/validate_mappings.py` to check ICD-10 codes and relationship
integrity.

## Phases 7–20: Requirements, API, and validation

The database now also contains package eligibility rules extracted only from
source procedure text, package-level preauthorization records marked `unknown`
when the HBP package master does not establish a requirement, and normalized
schema areas for investigations and supporting documents.

No unsupported mandatory investigation or document requirement is inferred.
Diagnosis mappings remain curated data, not PDF-derived guesses.

Run the repeatable pipeline:

```powershell
python scripts/import_pipeline.py
python scripts/generate_json.py
python scripts/data_quality_report.py
python -m unittest discover -s tests -v
python src/api/server.py
```

API endpoints:

- `GET /api/packages?q=...`
- `GET /api/packages/search?q=...`
- `GET /api/packages/{package_code}`
- `GET /api/procedures/search?q=...`
- `GET /api/diagnoses/search?q=...`
- `GET /api/diagnoses/{diagnosis_id}/packages`

Copy `.env.example` to `.env` for Supabase configuration. Supabase credentials
are never embedded in source files. After generating
`data/final/nha_packages_complete.json`, run:

```powershell
python scripts/supabase_import.py
```

The source-backed investigation review queue is stored separately from the
production package catalog. Run `scripts/supabase_investigation_review_schema.sql`
in the Supabase SQL Editor, then set `SUPABASE_URL` and
`SUPABASE_SERVICE_ROLE_KEY` in the process environment and run:

```powershell
python scripts/supabase_import_investigations.py
```

This imports `data/manual_review/investigation_review.csv` into
`public.investigation_review_queue`. Duplicate candidates are ignored so a
re-import does not overwrite existing review decisions. The queue is not the
approved production investigations catalog. The generated review CSV is not
included in this shared copy; obtain the authorized source PDF, then run
`python scripts/generate_manual_review.py --investigations-only` before importing.

## Manual review workflow

Generate candidate review files:

```powershell
python scripts/generate_manual_review.py
```

Refresh only the investigation queue without rewriting the other review files:

```powershell
python scripts/generate_manual_review.py --investigations-only
```

The investigation queue contains only source-text candidates mentioning tests,
screening, work-up, or related terms. Each row includes the extracted source
text and PDF excerpt; `mandatory` remains `unknown` until verified by a reviewer.
Generating the queue does not change the production catalog.

Review the next procedure or preauthorization item, then save a decision:

```powershell
python scripts/review_procedure_codes.py
python scripts/review_procedure_codes.py ID001A --decision verified_different_context --reviewer "Reviewer Name" --notes "Confirmed across source contexts."
python scripts/review_preauth.py
python scripts/review_preauth.py --package-code BM001 --decision not_required --reviewer "Reviewer Name" --notes "Explicitly verified."
```

Only after human review and source verification:

```powershell
python scripts/approve_review.py --area preauthorization --item-key BM001 --reviewer "Reviewer Name"
python scripts/manual_review_progress.py
```

Approved preauthorization decisions are the only review decisions applied to
the production SQLite catalog. Procedure classifications remain review metadata
and do not alter source records. Investigation, document, and ICD-10 records
remain pending unless separately sourced and approved.

## Final verification status

Completed:
- 1,433 packages and 2,415 procedures are imported.
- 78 source-derived eligibility rules are stored.
- The SQLite schema, complete JSON, repeatable pipeline, API, validation suite,
  Supabase import script, and documentation are implemented.

Pending manual verification:
- 454 repeated procedure-code groups.
- 1,433 preauthorization records remain `unknown`.
- Investigation candidates are source-backed; mandatory status remains unknown
  until reviewed.
- Supporting-document requirements remain unresolved.
- 0 ICD-10 mappings are stored; mappings require separate authoritative review.

## Verification commands

```powershell
python scripts/validate_data.py
python scripts/validate_mappings.py
python scripts/generate_json.py
python scripts/data_quality_report.py
python scripts/generate_manual_review.py
python scripts/review_procedure_codes.py BM001A
python -m unittest discover -s tests -v
python src/api/server.py
python scripts/supabase_import.py
```
