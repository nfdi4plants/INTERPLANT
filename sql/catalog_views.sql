-- Catalog serving views over the harvester's records table.
-- Flattens payload jsonb into typed, queryable columns for the pygeoapi
-- PostgreSQL record provider. Idempotent: safe to re-run after every harvest.

CREATE OR REPLACE VIEW arc_records AS
SELECT
  id,
  payload->'properties'->>'title'                                  AS title,
  payload->'properties'->>'description'                            AS description,
  (payload->'properties'->>'created')::timestamptz                 AS created,
  ARRAY(SELECT jsonb_array_elements_text(payload->'properties'->'omics_domains'))  AS omics_domains,
  payload->'properties'->>'experiment_context'                     AS experiment_context,
  ARRAY(SELECT jsonb_array_elements_text(payload->'properties'->'organism'))       AS organism,
  ARRAY(SELECT jsonb_array_elements_text(payload->'properties'->'keywords'))       AS keywords,
  payload->'properties'->>'arc_source_uri'                         AS arc_source_uri,
  CASE
    WHEN payload->'geometry' = 'null'::jsonb OR payload->'geometry' IS NULL THEN NULL
    ELSE ST_SetSRID(ST_GeomFromGeoJSON(payload->'geometry'), 4326)
  END                                                              AS geom
FROM records;
