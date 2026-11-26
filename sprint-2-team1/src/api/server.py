import argparse
import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


DATABASE = Path("data/final/nha_packages.sqlite3")


def query_rows(connection, sql, parameters=()):
    connection.row_factory = sqlite3.Row
    return [dict(row) for row in connection.execute(sql, parameters).fetchall()]


def package_detail(connection, package_id):
    package = connection.execute(
        """
        SELECT p.package_id, p.package_code, p.package_name,
               s.specialty_code, s.specialty_name
        FROM packages p JOIN specialties s ON s.specialty_id = p.specialty_id
        WHERE p.package_id = ?
        """,
        (package_id,),
    ).fetchone()
    if not package:
        return None
    pid = package["package_id"]
    preauth = connection.execute(
        "SELECT * FROM package_preauth_rules WHERE package_id = ?", (pid,)
    ).fetchone()
    return {
        "package_code": package["package_code"],
        "package_name": package["package_name"],
        "specialty": {
            "code": package["specialty_code"],
            "name": package["specialty_name"],
        },
        "procedures": query_rows(connection, """
            SELECT procedure_code, procedure_name, tier3_price, tier2_price,
                   tier1_price, stratification_remarks, implant_mapped, implant_cost
            FROM procedures WHERE package_id = ? ORDER BY procedure_code
        """, (pid,)),
        "diagnosis_mappings": query_rows(connection, """
            SELECT d.diagnosis_id, d.icd10_code, d.diagnosis_name,
                   m.validation_status
            FROM diagnosis_package_mapping m
            JOIN diagnoses d ON d.diagnosis_id = m.diagnosis_id
            WHERE m.package_id = ?
        """, (pid,)),
        "eligibility": query_rows(connection,
            "SELECT rule_type, rule_text, required, source_document, source_page, notes "
            "FROM package_eligibility WHERE package_id = ? ORDER BY id", (pid,)),
        "preauthorization": dict(preauth) if preauth else {"preauth_required": "unknown"},
        "investigations": query_rows(connection,
            "SELECT * FROM package_investigations WHERE package_id = ?", (pid,)),
        "documents": query_rows(connection,
            "SELECT * FROM package_documents WHERE package_id = ?", (pid,)),
    }


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        params = parse_qs(parsed.query)
        with sqlite3.connect(DATABASE) as connection:
            connection.row_factory = sqlite3.Row
            if parts == ["api", "packages"]:
                query = (params.get("q", [""])[0] or "").strip()
                sql = """
                    SELECT p.package_id, p.package_code, p.package_name,
                           s.specialty_code, s.specialty_name
                    FROM packages p JOIN specialties s ON s.specialty_id = p.specialty_id
                    WHERE (? = '' OR p.package_code LIKE ? OR p.package_name LIKE ?)
                    ORDER BY p.package_code LIMIT 100
                """
                like = f"%{query}%"
                self.send_json(200, query_rows(connection, sql, ("", "", "") if not query else (query, like, like)))
            elif parts == ["api", "packages", "search"]:
                query = (params.get("q", [""])[0] or "").strip()
                sql = """
                    SELECT p.package_id, p.package_code, p.package_name,
                           s.specialty_code, s.specialty_name
                    FROM packages p JOIN specialties s ON s.specialty_id = p.specialty_id
                    WHERE p.package_code LIKE ? OR p.package_name LIKE ?
                    ORDER BY p.package_code LIMIT 100
                """
                like = f"%{query}%"
                self.send_json(200, query_rows(connection, sql, (like, like)))
            elif len(parts) == 3 and parts[:2] == ["api", "packages"]:
                code = parts[2]
                row = connection.execute(
                    "SELECT package_id FROM packages WHERE package_code = ? LIMIT 1",
                    (code,),
                ).fetchone()
                if not row:
                    self.send_json(404, {"error": "Package not found"})
                else:
                    self.send_json(200, package_detail(connection, row["package_id"]))
            elif parts == ["api", "procedures", "search"]:
                query = (params.get("q", [""])[0] or "").strip()
                like = f"%{query}%"
                rows = query_rows(connection, """
                    SELECT pr.procedure_id, pr.procedure_code, pr.procedure_name,
                           p.package_code, p.package_name
                    FROM procedures pr JOIN packages p ON p.package_id = pr.package_id
                    WHERE pr.procedure_code LIKE ? OR pr.procedure_name LIKE ?
                    ORDER BY pr.procedure_code LIMIT 100
                """, (like, like))
                self.send_json(200, rows)
            elif parts == ["api", "diagnoses", "search"]:
                query = (params.get("q", [""])[0] or "").strip()
                like = f"%{query}%"
                rows = query_rows(connection, """
                    SELECT d.diagnosis_id, d.icd10_code, d.diagnosis_name,
                           ds.synonym_text
                    FROM diagnoses d
                    LEFT JOIN diagnosis_synonyms ds ON ds.diagnosis_id = d.diagnosis_id
                    WHERE d.diagnosis_name LIKE ? OR d.icd10_code LIKE ?
                       OR ds.synonym_text LIKE ?
                    ORDER BY d.diagnosis_name LIMIT 100
                """, (like, like, like))
                self.send_json(200, rows)
            elif len(parts) == 5 and parts[:3] == ["api", "diagnoses"] and parts[4] == "packages":
                diagnosis_id = parts[3]
                rows = query_rows(connection, """
                    SELECT p.package_id, p.package_code, p.package_name,
                           pr.procedure_code, pr.procedure_name,
                           m.validation_status
                    FROM diagnosis_package_mapping m
                    JOIN packages p ON p.package_id = m.package_id
                    JOIN procedures pr ON pr.procedure_id = m.procedure_id
                    WHERE m.diagnosis_id = ?
                """, (diagnosis_id,))
                self.send_json(200, rows)
            else:
                self.send_json(404, {"error": "Not found"})


def main():
    global DATABASE
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=DATABASE)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    DATABASE = args.database
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"NHA Package API listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
