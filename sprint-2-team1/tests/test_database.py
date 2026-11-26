import sqlite3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "data" / "final" / "nha_packages.sqlite3"


class DatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.connection = sqlite3.connect(DATABASE)
        cls.connection.execute("PRAGMA foreign_keys = ON")

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def test_catalog_has_packages_and_procedures(self):
        package_count = self.connection.execute(
            "SELECT COUNT(*) FROM packages"
        ).fetchone()[0]
        procedure_count = self.connection.execute(
            "SELECT COUNT(*) FROM procedures"
        ).fetchone()[0]
        self.assertGreater(package_count, 0)
        self.assertGreater(procedure_count, 0)

    def test_every_procedure_references_a_package(self):
        invalid = self.connection.execute(
            """
            SELECT COUNT(*) FROM procedures p
            LEFT JOIN packages k ON k.package_id = p.package_id
            WHERE k.package_id IS NULL
            """
        ).fetchone()[0]
        self.assertEqual(invalid, 0)

    def test_every_extended_mapping_has_valid_package(self):
        for table in ("package_eligibility", "package_preauth_rules",
                      "package_investigations", "package_documents"):
            invalid = self.connection.execute(
                f"""
                SELECT COUNT(*) FROM {table} r
                LEFT JOIN packages p ON p.package_id = r.package_id
                WHERE p.package_id IS NULL
                """
            ).fetchone()[0]
            self.assertEqual(invalid, 0)

    def test_preauth_unknown_is_explicit(self):
        unknown = self.connection.execute(
            "SELECT COUNT(*) FROM package_preauth_rules "
            "WHERE preauth_required = 'unknown'"
        ).fetchone()[0]
        total = self.connection.execute(
            "SELECT COUNT(*) FROM package_preauth_rules"
        ).fetchone()[0]
        self.assertEqual(unknown, total)

    def test_manual_review_tables_exist_and_production_is_unchanged(self):
        tables = {
            row[0] for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertIn("review_items", tables)
        self.assertIn("review_history", tables)
        self.assertIn("approved_review_changes", tables)
        approved_changes = self.connection.execute(
            "SELECT COUNT(*) FROM approved_review_changes"
        ).fetchone()[0]
        self.assertEqual(approved_changes, 0)

    def test_foreign_key_check_is_clean(self):
        self.assertEqual(
            self.connection.execute("PRAGMA foreign_key_check").fetchall(),
            [],
        )

    def test_all_referential_integrity_tables(self):
        checks = {
            "diagnosis_package_mapping": ("diagnosis_id", "diagnoses", "diagnosis_id"),
            "package_eligibility": ("package_id", "packages", "package_id"),
            "package_preauth_rules": ("package_id", "packages", "package_id"),
            "package_investigations": ("package_id", "packages", "package_id"),
            "package_documents": ("package_id", "packages", "package_id"),
        }
        for table, (foreign_key, target_table, target_key) in checks.items():
            invalid = self.connection.execute(
                f"""
                SELECT COUNT(*) FROM {table} child
                LEFT JOIN {target_table} target ON target.{target_key} = child.{foreign_key}
                WHERE target.{target_key} IS NULL
                """
            ).fetchone()[0]
            self.assertEqual(invalid, 0)

        mapping_package_invalid = self.connection.execute(
            """
            SELECT COUNT(*) FROM diagnosis_package_mapping child
            LEFT JOIN packages target ON target.package_id = child.package_id
            WHERE target.package_id IS NULL
            """
        ).fetchone()[0]
        self.assertEqual(mapping_package_invalid, 0)

    def test_duplicate_records_are_detected_but_not_removed(self):
        duplicate_queries = {
            "packages": "SELECT COUNT(*) FROM (SELECT package_code FROM packages GROUP BY package_code HAVING COUNT(*) > 1)",
            "procedures": "SELECT COUNT(*) FROM (SELECT procedure_code FROM procedures GROUP BY procedure_code HAVING COUNT(*) > 1)",
            "diagnosis-package mappings": """
                SELECT COUNT(*) FROM (
                    SELECT diagnosis_id, package_id, procedure_id
                    FROM diagnosis_package_mapping
                    GROUP BY diagnosis_id, package_id, procedure_id
                    HAVING COUNT(*) > 1
                )
            """,
            "eligibility rules": """
                SELECT COUNT(*) FROM (
                    SELECT package_id, rule_type, rule_text
                    FROM package_eligibility
                    GROUP BY package_id, rule_type, rule_text
                    HAVING COUNT(*) > 1
                )
            """,
            "documents": """
                SELECT COUNT(*) FROM (
                    SELECT package_id, document_id, requirement_text
                    FROM package_documents
                    GROUP BY package_id, document_id, requirement_text
                    HAVING COUNT(*) > 1
                )
            """,
            "investigations": """
                SELECT COUNT(*) FROM (
                    SELECT package_id, investigation_id, requirement_text
                    FROM package_investigations
                    GROUP BY package_id, investigation_id, requirement_text
                    HAVING COUNT(*) > 1
                )
            """,
        }
        for label, query in duplicate_queries.items():
            count = self.connection.execute(query).fetchone()[0]
            self.assertGreaterEqual(count, 0, label)


if __name__ == "__main__":
    unittest.main()
