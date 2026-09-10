-- Catalog serving views over the harvester's records table.
-- Flattens payload jsonb into typed, queryable columns for the pygeoapi
-- PostgreSQL record provider. Idempotent: safe to re-run after every harvest.

CREATE OR REPLACE VIEW public.arc_records AS
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
FROM public.records;

-- One row per extracted or derived location point. Teosinte's 276 collection
-- sites become 276 rows here, which is what /collections/arc-locations serves.
--
-- Records whose payload has an empty locations array contribute no rows: the
-- LATERAL join over jsonb_array_elements yields nothing, which is the intended
-- behaviour for the ~23% of ARCs with no location at all.
--
-- payload point is [longitude, latitude], matching GeoJSON. ST_MakePoint takes
-- (x, y) = (longitude, latitude), so element 0 comes first.
CREATE OR REPLACE VIEW public.arc_locations AS
SELECT
  r.id                                                             AS record_id,
  loc->>'role'                                                     AS role,
  loc->>'label'                                                    AS label,
  loc->>'precision'                                                AS precision,
  (loc->>'n_rows')::int                                            AS n_rows,
  loc->>'source'                                                   AS source,
  ST_SetSRID(
    ST_MakePoint(
      (loc->'point'->>0)::double precision,
      (loc->'point'->>1)::double precision
    ),
    4326
  )                                                                AS geom
FROM public.records r
CROSS JOIN LATERAL jsonb_array_elements(
  COALESCE(r.payload->'properties'->'locations', '[]'::jsonb)
) AS loc
WHERE loc->'point' IS NOT NULL;
