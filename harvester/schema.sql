CREATE TABLE IF NOT EXISTS records (
  id          text PRIMARY KEY,
  payload     jsonb       NOT NULL,
  source_etag text,
  ingested_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS records_ingested_at_idx ON records (ingested_at);
