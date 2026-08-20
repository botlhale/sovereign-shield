-- =====================================================================
-- SovereignShield Triple-Lock Security Architecture
--
-- This script is IDEMPOTENT and NON-DESTRUCTIVE. It runs as the first task of
-- every pipeline execution, so it must never drop the historical tables:
-- doing so silently erases the entire SCD2 lineage and leaves the platform
-- unable to protect a published record from a quarantined revision.
--
-- Statements annotated with "-- @tolerate-failure" are expected to fail on one
-- of the two lifecycle paths (fresh create vs. re-apply) and are skipped by
-- apply_security.py rather than aborting the deployment.
-- =====================================================================

USE CATALOG dbw_sovereignshield;
USE SCHEMA sovereign_shield;

-- =====================================================================
-- 1. DETACH POLICIES SO THE UDFs CAN BE REPLACED
-- Unity Catalog refuses to replace a function bound to a live row filter or
-- column mask. Fails harmlessly on the very first deployment.
-- =====================================================================
-- @tolerate-failure
ALTER TABLE lbs_sdmx_history DROP ROW FILTER;
-- @tolerate-failure
ALTER TABLE lbs_sdmx_history ALTER COLUMN OBS_VALUE DROP MASK;
-- @tolerate-failure
ALTER TABLE lbs_micro_transactions DROP ROW FILTER;

-- The single-column filter is superseded by fn_rls_lbs_multi_persona_lock.
-- Dropping it keeps the metastore free of an unbound policy that still
-- compiles and could be re-attached by mistake.
-- @tolerate-failure
DROP FUNCTION IF EXISTS fn_rls_lbs_country_lock;

-- =====================================================================
-- 2. DYNAMIC DATA MASKING (DDM) FUNCTION
--
-- Confidential observations (OBS_CONF 'C' = confidential, 'N' = not for
-- publication) are nulled for everyone except the platform administrators and
-- the sovereign that reported them.
--
-- TIME_SERIES_CODE is a mask input, not decoration: without it the function
-- cannot tell whose confidential value it is holding, so any submitter would
-- unmask every other jurisdiction's restricted cells. Segment 9 is L_REP_CTY.
-- =====================================================================
CREATE OR REPLACE FUNCTION fn_ddm_obs_conf_mask(
  obs_val DOUBLE,
  obs_conf STRING,
  time_series_code STRING
)
RETURNS DOUBLE
RETURN CASE
  WHEN is_account_group_member('sg-sovereignshield-admin') THEN obs_val
  WHEN is_account_group_member('sg-sovereignshield-submitter-ca')
    AND coalesce(try_element_at(split(time_series_code, '\\.'), 9) = 'CA', FALSE) THEN obs_val
  WHEN is_account_group_member('sg-sovereignshield-submitter-us')
    AND coalesce(try_element_at(split(time_series_code, '\\.'), 9) = 'US', FALSE) THEN obs_val
  WHEN upper(coalesce(obs_conf, '')) IN ('C', 'N') THEN NULL
  ELSE obs_val
END;

-- =====================================================================
-- 3. MULTI-COLUMN ROW-LEVEL SECURITY (RLS) - MACRO HISTORY
--
-- Entitlement is evaluated from three columns at once - the SDMx key, the
-- batch lifecycle state and the confidentiality flag - so a quarantined or
-- restricted record can never leak through a persona entitled only to clean
-- published data.
--
-- The tiers are composed with OR rather than CASE/WHEN so that privileges are
-- ADDITIVE. A principal holding two memberships (e.g. a Bank of Canada analyst
-- who is also a researcher) receives the union of both entitlements instead of
-- whichever branch happens to be evaluated first.
--
-- Persona matrix:
--   sg-sovereignshield-admin        1 = 1 (every jurisdiction and state)
--   sg-sovereignshield-researchers  BATCH_STATUS = 'PUBLISHED' (values masked by DDM)
--   sg-sovereignshield-submitter-xx own segment-9 rows in full, plus every other
--                                   sovereign's PUBLISHED + free-to-publish rows
--   sg-sovereignshield-public       BATCH_STATUS = 'PUBLISHED' AND OBS_CONF = 'F'
--   (no recognised membership)      FALSE - fails closed, zero rows
--
-- try_element_at is used instead of element_at: under ANSI mode an
-- out-of-range index raises INVALID_ARRAY_INDEX, which would abort every query
-- against the table if a malformed key were ever persisted. It returns NULL
-- instead, and the coalesce turns that NULL into FALSE so a malformed row is
-- invisible rather than universally visible.
--
-- The pipeline service principal (spn-sovereignshield-cicd) MUST be a member of
-- sg-sovereignshield-admin. The SCD2 engine reads this table to find records to
-- expire; if the filter hid those rows the merge would treat every row as new,
-- silently duplicating history and never closing prior versions.
-- =====================================================================
CREATE OR REPLACE FUNCTION fn_rls_lbs_multi_persona_lock(
  time_series_code STRING,
  batch_status STRING,
  obs_conf STRING
)
RETURNS BOOLEAN
RETURN
  is_account_group_member('sg-sovereignshield-admin')
  OR (
    is_account_group_member('sg-sovereignshield-researchers')
    AND upper(coalesce(batch_status, '')) = 'PUBLISHED'
  )
  OR (
    (
      is_account_group_member('sg-sovereignshield-public')
      OR is_account_group_member('sg-sovereignshield-submitter-ca')
      OR is_account_group_member('sg-sovereignshield-submitter-us')
    )
    AND upper(coalesce(batch_status, '')) = 'PUBLISHED'
    AND upper(coalesce(obs_conf, '')) = 'F'
  )
  OR (
    is_account_group_member('sg-sovereignshield-submitter-ca')
    AND coalesce(try_element_at(split(time_series_code, '\\.'), 9) = 'CA', FALSE)
  )
  OR (
    is_account_group_member('sg-sovereignshield-submitter-us')
    AND coalesce(try_element_at(split(time_series_code, '\\.'), 9) = 'US', FALSE)
  );

-- =====================================================================
-- 4. ROW-LEVEL SECURITY (RLS) FUNCTION - MICRO LEDGER
-- Defense in depth: the raw ledger carries bank-identifying detail, so
-- sovereign isolation is enforced at the source table rather than relying
-- solely on table-level grants. Researchers and the public portal principal
-- are deliberately absent - no persona reaches institution-level rows.
-- =====================================================================
CREATE OR REPLACE FUNCTION fn_rls_micro_country_lock(reporting_country STRING)
RETURNS BOOLEAN
RETURN CASE
  WHEN is_account_group_member('sg-sovereignshield-admin') THEN TRUE
  WHEN is_account_group_member('sg-sovereignshield-submitter-ca')
    AND upper(coalesce(reporting_country, '')) = 'CA' THEN TRUE
  WHEN is_account_group_member('sg-sovereignshield-submitter-us')
    AND upper(coalesce(reporting_country, '')) = 'US' THEN TRUE
  ELSE FALSE
END;

-- =====================================================================
-- 5. APPEND-ONLY MICRO TRANSACTIONS LEDGER
-- =====================================================================
CREATE TABLE IF NOT EXISTS lbs_micro_transactions (
  transaction_id STRING,
  reporting_country STRING,
  reporting_institution STRING,
  position_type STRING,
  instrument STRING,
  currency STRING,
  currency_type STRING,
  parent_country STRING,
  bank_type STRING,
  counterpart_country STRING,
  sector_code STRING,
  transaction_amount DOUBLE,
  obs_conf STRING,
  ibs_agg_scope STRING,
  date_scope STRING,
  transaction_timestamp TIMESTAMP
)
WITH ROW FILTER fn_rls_micro_country_lock ON (reporting_country);

-- =====================================================================
-- 6. MACRO SDMX HISTORY TABLE (SCD2, WITH RLS & DDM APPLIED)
-- OBS_VALUE may legitimately be negative: LBS positions record both asset and
-- liability directions. Zero-valued observations are not reported at all under
-- SDMx convention and are filtered upstream.
-- =====================================================================
CREATE TABLE IF NOT EXISTS lbs_sdmx_history (
  TIME_SERIES_CODE STRING,
  DATE STRING,
  IBS_AGG STRING,
  OBS_VALUE DOUBLE MASK fn_ddm_obs_conf_mask USING COLUMNS (OBS_CONF, TIME_SERIES_CODE),
  OBS_STATUS STRING,
  OBS_CONF STRING,
  QUALITY_STATUS STRING,
  FAILED_RULE_ID STRING,
  BATCH_STATUS STRING,
  version_hash STRING,
  VALID_FROM TIMESTAMP,
  VALID_TO TIMESTAMP,
  IS_CURRENT BOOLEAN
)
WITH ROW FILTER fn_rls_lbs_multi_persona_lock ON (TIME_SERIES_CODE, BATCH_STATUS, OBS_CONF);

-- =====================================================================
-- 7. RE-ATTACH POLICIES ON PRE-EXISTING TABLES
-- No-ops (hence tolerated failures) when the CREATE TABLE statements above
-- just built the tables with their policies already inline.
-- =====================================================================
-- @tolerate-failure
ALTER TABLE lbs_sdmx_history ALTER COLUMN OBS_VALUE SET MASK fn_ddm_obs_conf_mask USING COLUMNS (OBS_CONF, TIME_SERIES_CODE);
-- @tolerate-failure
ALTER TABLE lbs_sdmx_history SET ROW FILTER fn_rls_lbs_multi_persona_lock ON (TIME_SERIES_CODE, BATCH_STATUS, OBS_CONF);
-- @tolerate-failure
ALTER TABLE lbs_micro_transactions SET ROW FILTER fn_rls_micro_country_lock ON (reporting_country);

-- =====================================================================
-- 8. QUARANTINE VIEW ISOLATION
-- Serves only the last valid published state. A quarantined revision is
-- written to lbs_sdmx_history with IS_CURRENT = false, so it can never surface
-- here and never interrupts consumers of the prior published value.
--
-- The portal and API deliberately query the base table instead of this view: a
-- Unity Catalog view resolves group membership against the view owner, so the
-- per-caller persona filter only means something when the table is read directly.
-- =====================================================================
CREATE OR REPLACE VIEW v_lbs_sdmx_published AS
SELECT 
  TIME_SERIES_CODE,
  DATE,
  IBS_AGG,
  OBS_VALUE,
  OBS_STATUS,
  OBS_CONF
FROM lbs_sdmx_history
WHERE BATCH_STATUS = 'PUBLISHED' 
  AND IS_CURRENT = true;

-- =====================================================================
-- 9. UNITY CATALOG GRANTS FOR SYNCHRONIZED GROUPS
-- One principal per statement: Unity Catalog rejects multiple principals in a
-- single TO clause.
-- =====================================================================

-- Catalog USAGE Grants
GRANT USAGE ON CATALOG dbw_sovereignshield TO `sg-sovereignshield-admin`;
GRANT USAGE ON CATALOG dbw_sovereignshield TO `sg-sovereignshield-submitter-ca`;
GRANT USAGE ON CATALOG dbw_sovereignshield TO `sg-sovereignshield-submitter-us`;
GRANT USAGE ON CATALOG dbw_sovereignshield TO `sg-sovereignshield-researchers`;
GRANT USAGE ON CATALOG dbw_sovereignshield TO `sg-sovereignshield-public`;

-- Schema USAGE Grants
GRANT USAGE ON SCHEMA dbw_sovereignshield.sovereign_shield TO `sg-sovereignshield-admin`;
GRANT USAGE ON SCHEMA dbw_sovereignshield.sovereign_shield TO `sg-sovereignshield-submitter-ca`;
GRANT USAGE ON SCHEMA dbw_sovereignshield.sovereign_shield TO `sg-sovereignshield-submitter-us`;
GRANT USAGE ON SCHEMA dbw_sovereignshield.sovereign_shield TO `sg-sovereignshield-researchers`;
GRANT USAGE ON SCHEMA dbw_sovereignshield.sovereign_shield TO `sg-sovereignshield-public`;

-- Admins: Full permissions on underlying tables
GRANT ALL PRIVILEGES ON TABLE lbs_micro_transactions TO `sg-sovereignshield-admin`;
GRANT ALL PRIVILEGES ON TABLE lbs_sdmx_history TO `sg-sovereignshield-admin`;

-- Submitters: Select access to history table (RLS filter active)
GRANT SELECT ON TABLE lbs_sdmx_history TO `sg-sovereignshield-submitter-ca`;
GRANT SELECT ON TABLE lbs_sdmx_history TO `sg-sovereignshield-submitter-us`;

-- Submitters: Select access to their own micro ledger rows (RLS filter active)
GRANT SELECT ON TABLE lbs_micro_transactions TO `sg-sovereignshield-submitter-ca`;
GRANT SELECT ON TABLE lbs_micro_transactions TO `sg-sovereignshield-submitter-us`;

-- Researchers and the public portal principal: the SELECT grant is deliberately
-- broad because the row filter, not the grant, is what narrows the result set.
-- Neither persona is granted anything on the institution-level micro ledger.
GRANT SELECT ON TABLE lbs_sdmx_history TO `sg-sovereignshield-researchers`;
GRANT SELECT ON TABLE lbs_sdmx_history TO `sg-sovereignshield-public`;

-- Curated published view (Quarantine filter active)
GRANT SELECT ON VIEW v_lbs_sdmx_published TO `sg-sovereignshield-researchers`;
GRANT SELECT ON VIEW v_lbs_sdmx_published TO `sg-sovereignshield-public`;