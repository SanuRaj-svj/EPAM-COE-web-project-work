# Database schema

Core relationships are specialties → packages → procedures and diagnoses →
diagnosis-package mappings → packages.

Package requirements are stored in `package_eligibility`,
`package_preauth_rules`, `package_investigations`, and `package_documents`.
Catalog tables `investigations` and `documents` support normalized lookup values.
Foreign keys and unique constraints enforce relationship integrity.
