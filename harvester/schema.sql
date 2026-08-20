-- DDL here is always schema-qualified. harvester/db.py DML is deliberately
-- unqualified so search_path selects staging or public; if this file used bare
-- names it would create tables in whichever schema the caller happened to set.

CREATE TABLE IF NOT EXISTS public.records (
  id          text PRIMARY KEY,
  payload     jsonb       NOT NULL,
  source_etag text,
  ingested_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS records_ingested_at_idx ON public.records (ingested_at);

CREATE SCHEMA IF NOT EXISTS staging;

-- The harvest writes here, never to public.records. A run that dies partway
-- leaves this table inconsistent and the endpoint unaffected. Declared FROM
-- public.records so the two can never drift apart. The swap copies between
-- them, so a column added to one and not the other would be a silent data
-- defect. INCLUDING INDEXES carries the primary key that upsert_record's
-- ON CONFLICT (id) needs.
CREATE TABLE IF NOT EXISTS staging.records (
  LIKE public.records INCLUDING DEFAULTS INCLUDING INDEXES
);

-- The GitLab enumeration as of the last successful publish. Cannot be derived
-- from public.records: collision losers are never written there. Advanced only
-- on a successful swap, so a failed harvest is retried the following night.
CREATE TABLE IF NOT EXISTS public.published_projects (
  project_path     text PRIMARY KEY,
  last_activity_at text        NOT NULL,
  published_at     timestamptz NOT NULL DEFAULT now()
);
