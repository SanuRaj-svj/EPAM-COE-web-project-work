# Data pipeline

The repeatable pipeline runs cleaning, validation, database insertion, mapping
validation, and complete JSON generation. Re-running it preserves existing
catalog and requirement records where unique constraints apply.

Raw PDF data is never overwritten. Extracted CSV/Excel is source data and final
JSON/SQLite are generated outputs.
