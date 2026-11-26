# Validation

Run `python scripts/validate_data.py`, `python scripts/validate_mappings.py`,
and `python -m unittest discover -s tests -v`.

The data-quality report separates verified database counts from manual-review
items. Unconfirmed preauthorization is reported as `unknown`; investigations and
documents are not marked mandatory unless separately supported.

## Final verification state

- 10 database/API tests pass.
- 1,433 packages and 2,415 procedures have referential integrity.
- 78 eligibility rules are source-derived from package procedure text.
- 1,433 preauthorization records remain `unknown`.
- 454 repeated procedure-code groups are pending source-context review.
- ICD-10 mappings remain 0 and pending separate clinical curation.
- Investigation and supporting-document mappings remain empty.

Manual-review CSV files are under `data/manual_review/`; coverage summaries are
under `data_quality/`.

## Manual review workflow

Candidate files are in `data/manual_review/`. Every save creates a
`review_history` entry. Production data changes only when `approve_review.py`
marks a reviewed item `approved` and applies the supported change.
