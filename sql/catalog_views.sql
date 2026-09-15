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
--
-- id is a synthetic "<record id>:<ordinal>" key, needed because record_id is
-- not unique in this view (one record explodes into many rows) and pygeoapi's
-- PostgreSQL feature provider requires id_field to be unique. It is NOT a
-- durable identifier: the ordinal comes from jsonb_array_elements WITH
-- ORDINALITY over the harvester's emitted order, and the view is rebuilt after
-- every harvest, so a given point's id can change between harvests. Fine for a
-- queryable derived view, not something to cite.
CREATE OR REPLACE VIEW public.arc_locations AS
SELECT
  r.id || ':' || loc.ord                                           AS id,
  r.id                                                             AS record_id,
  loc.loc->>'role'                                                  AS role,
  loc.loc->>'label'                                                 AS label,
  loc.loc->>'precision'                                             AS precision,
  (loc.loc->>'n_rows')::int                                         AS n_rows,
  loc.loc->>'source'                                                AS source,
  ST_SetSRID(
    ST_MakePoint(
      (loc.loc->'point'->>0)::double precision,
      (loc.loc->'point'->>1)::double precision
    ),
    4326
  )                                                                AS geom,
  -- Appended deliberately, and new columns must keep being appended here:
  -- CREATE OR REPLACE VIEW cannot insert a column mid-list or rename one, so
  -- an insertion breaks `apply_catalog_views` against any existing database
  -- ("cannot change name of view column"). A point has no date of its own; it
  -- inherits its ARC's, and this is the collection's time_field, without which
  -- ?datetime= returns HTTP 500.
  (r.payload->'properties'->>'created')::timestamptz               AS created
FROM public.records r
CROSS JOIN LATERAL jsonb_array_elements(
  COALESCE(r.payload->'properties'->'locations', '[]'::jsonb)
) WITH ORDINALITY AS loc(loc, ord)
WHERE loc.loc->'point' IS NOT NULL;
