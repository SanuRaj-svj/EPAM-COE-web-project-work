CREATE TABLE IF NOT EXISTS public.investigation_review_queue (
    package_code TEXT NOT NULL,
    package_name TEXT NOT NULL,
    specialty_code TEXT NOT NULL,
    specialty_name TEXT NOT NULL,
    investigation_name TEXT NOT NULL,
    mandatory TEXT NOT NULL DEFAULT 'unknown'
        CHECK (mandatory IN ('unknown', 'mandatory', 'conditional', 'not_required')),
    source_document TEXT NOT NULL,
    source_page INTEGER NOT NULL CHECK (source_page > 0),
    source_field TEXT NOT NULL,
    source_text TEXT NOT NULL,
    source_context TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (review_status IN ('pending', 'reviewed', 'approved', 'rejected')),
    review_notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (
        package_code, package_name, specialty_code,
        investigation_name, source_page
    )
);

ALTER TABLE public.investigation_review_queue ENABLE ROW LEVEL SECURITY;

GRANT SELECT ON TABLE public.investigation_review_queue TO authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE public.investigation_review_queue TO service_role;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'investigation_review_queue'
          AND policyname = 'Authenticated users can view investigation review queue'
    ) THEN
        CREATE POLICY "Authenticated users can view investigation review queue"
            ON public.investigation_review_queue
            FOR SELECT TO authenticated
            USING (true);
    END IF;
END
$$;

NOTIFY pgrst, 'reload schema';
