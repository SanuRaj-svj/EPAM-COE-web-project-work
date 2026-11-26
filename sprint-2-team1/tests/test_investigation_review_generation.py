import csv
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generate_manual_review import investigation_mentions
from supabase_import_investigations import load_candidates


class InvestigationReviewGenerationTests(unittest.TestCase):
    def test_extracts_source_named_investigation_candidates(self):
        mentions = investigation_mentions(
            "Includes thyroid screening, universal hearing screening and "
            "screening test for COVID-19 infection."
        )
        names = {name.casefold() for name, _ in mentions}
        self.assertIn("thyroid screening", names)
        self.assertIn("universal hearing screening", names)
        self.assertIn("screening test for covid-19 infection", names)

    def test_extracts_workup_and_named_tests_without_inventing_from_generic_text(self):
        mentions = investigation_mentions(
            "Genetic workup, metabolic work-up and VEEG monitoring test (VEEG). "
            "Follow-up dressings and physiotherapy are included."
        )
        names = {name.casefold() for name, _ in mentions}
        self.assertIn("genetic workup", names)
        self.assertIn("metabolic work-up", names)
        self.assertIn("veeg monitoring test (veeg)", names)
        self.assertFalse(any("physiotherapy" in name for name in names))

    def test_supabase_import_requires_source_evidence_and_parses_page_number(self):
        candidate = {
            "package_code": "HD011",
            "package_name": "Genetic workup",
            "specialty_code": "HD",
            "specialty_name": "High end Diagnostics",
            "investigation_name": "Genetic workup",
            "mandatory": "unknown",
            "source_document": "HBP_2022.pdf",
            "source_page": "6",
            "source_field": "procedure_name",
            "source_text": "Genetic workup",
            "source_context": "HBP_2022.pdf page 6 excerpt",
            "review_status": "pending",
            "review_notes": "",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "investigation_review.csv"
            with path.open("w", newline="", encoding="utf-8") as output:
                writer = csv.DictWriter(output, fieldnames=candidate.keys())
                writer.writeheader()
                writer.writerow(candidate)

            rows = load_candidates(path)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_page"], 6)
        self.assertEqual(rows[0]["mandatory"], "unknown")


if __name__ == "__main__":
    unittest.main()
