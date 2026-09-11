-- Creates and configures the pygeoapi_ro LOGIN role. Runs as a superuser
-- (install.sh executes this as the postgres system user; the dev stack as the
-- bootstrap interplant role): the production interplant role is created via
-- `createuser --pwprompt` with neither CREATEROLE nor the ADMIN option, so it
-- cannot create or configure roles. The password is set separately, never in
-- git. The grants are applied by sql/pygeoapi_role.sql, which interplant can
-- do as owner of the database and the views.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pygeoapi_ro') THEN
    CREATE ROLE pygeoapi_ro LOGIN;
  END IF;
END
$$;

-- statement_timeout is 3s, and it is load-bearing rather than cosmetic.
-- harvester/publish.py sets lock_timeout = '5s' around TRUNCATE public.records,
-- so a reader holding ACCESS SHARE for longer aborts the nightly publish and
-- the corpus goes stale - which matters because AWI's harvest applies a 5-day
-- TTL to records it stops seeing. Measured worst-case query at 100x realistic
-- corpus size was 59ms, so 3s is ample headroom while staying clear of 5s.
-- See tests/stack/test_swap_survives_slow_reader.py.
ALTER ROLE pygeoapi_ro SET statement_timeout = '3s';

-- statement_timeout bounds the STATEMENT, not the transaction. A reader whose
-- query finishes fast but whose transaction stays open still holds ACCESS
-- SHARE on the lock the swap needs, and no statement is running for
-- statement_timeout to cancel. Measured: such a reader blocked the swap at
-- 5.0s with LockNotAvailable despite statement_timeout being set. pygeoapi's
-- pooled sessions sit idle with no open transaction, so this makes the bound
-- structural instead of resting on the client's good manners.
ALTER ROLE pygeoapi_ro SET idle_in_transaction_session_timeout = '3s';
