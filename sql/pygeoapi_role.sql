-- Read-only role for pygeoapi. Applied by deploy/install.sh via
-- harvester.db.apply_pygeoapi_role, which substitutes the password.
--
-- pygeoapi is public and unauthenticated, so its credential is enforced
-- read-only by the database rather than by the application's good behaviour.
-- It reads the views only, never public.records: the views are exactly what
-- the API exposes, so granting the base table would hand a public service
-- more than it can ever serve.
--
-- statement_timeout is 3s, and it is load-bearing rather than cosmetic.
-- harvester/publish.py sets lock_timeout = '5s' around TRUNCATE public.records,
-- so a reader holding ACCESS SHARE for longer aborts the nightly publish and
-- the corpus goes stale - which matters because AWI's harvest applies a 5-day
-- TTL to records it stops seeing. Measured worst-case query at 100x realistic
-- corpus size was 59ms, so 3s is ample headroom while staying clear of 5s.
-- See tests/stack/test_swap_survives_slow_reader.py.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pygeoapi_ro') THEN
    CREATE ROLE pygeoapi_ro LOGIN;
  END IF;
END
$$;

ALTER ROLE pygeoapi_ro SET statement_timeout = '3s';

-- statement_timeout bounds the STATEMENT, not the transaction. A reader whose
-- query finishes fast but whose transaction stays open still holds ACCESS
-- SHARE on the lock the swap needs, and no statement is running for
-- statement_timeout to cancel. Measured: such a reader blocked the swap at
-- 5.0s with LockNotAvailable despite statement_timeout being set. pygeoapi's
-- pooled sessions sit idle with no open transaction, so this makes the bound
-- structural instead of resting on the client's good manners.
ALTER ROLE pygeoapi_ro SET idle_in_transaction_session_timeout = '3s';

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
