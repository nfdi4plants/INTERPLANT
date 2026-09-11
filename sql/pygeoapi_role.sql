-- Grants for the pygeoapi_ro role. Applied by deploy/install.sh via
-- harvester.db.apply_pygeoapi_role after the role exists: the creation and
-- the session timeouts live in sql/pygeoapi_role_lifecycle.sql, which runs as
-- a superuser. This file is grants-only because interplant can apply these as
-- owner of the database, schema and views without CREATEROLE.
--
-- pygeoapi is public and unauthenticated, so its credential is enforced
-- read-only by the database rather than by the application's good behaviour.
-- It reads the views only, never public.records: the views are exactly what
-- the API exposes, so granting the base table would hand a public service
-- more than it can ever serve.
--
-- The role's statement_timeout (3s) and idle_in_transaction_session_timeout
-- (3s) are load-bearing against the swap's 5s lock_timeout; see
-- sql/pygeoapi_role_lifecycle.sql for the rationale and tests/stack/
-- test_swap_survives_slow_reader.py for the measurements.

-- CONNECT is granted explicitly rather than relied on from PUBLIC's default,
-- so a future lock-down of the default fails loudly here instead of as a
-- mystery connect error. The database name is fixed: the API serves exactly
-- the interplant catalog, and install.sh provisions this role on that
-- database by name.
GRANT CONNECT ON DATABASE interplant TO pygeoapi_ro;
GRANT USAGE ON SCHEMA public TO pygeoapi_ro;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM pygeoapi_ro;
GRANT SELECT ON public.arc_records TO pygeoapi_ro;
GRANT SELECT ON public.arc_locations TO pygeoapi_ro;
GRANT SELECT ON public.arc_records_genomics TO pygeoapi_ro;
GRANT SELECT ON public.arc_records_imaging TO pygeoapi_ro;
GRANT SELECT ON public.arc_records_metabolomics TO pygeoapi_ro;
GRANT SELECT ON public.arc_records_microbiome TO pygeoapi_ro;
GRANT SELECT ON public.arc_records_phenotyping TO pygeoapi_ro;
GRANT SELECT ON public.arc_records_proteomics TO pygeoapi_ro;
GRANT SELECT ON public.arc_records_transcriptomics TO pygeoapi_ro;
