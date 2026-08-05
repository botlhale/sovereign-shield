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

-- =====================================================================
-- 2. DYNAMIC DATA MASKING (DDM) FUNCTION
-- Privileged groups are evaluated first so an authorized submitter always
-- sees the true value regardless of the confidentiality flag.
-- =====================================================================
CREATE OR REPLACE FUNCTION fn_ddm_obs_conf_mask(obs_val DOUBLE, obs_conf STRING)
RETURNS DOUBLE
RETURN CASE
  WHEN is_account_group_member('sg-sovereignshield-admin')
    OR is_account_group_member('sg-sovereignshield-submitter-ca')
    OR is_account_group_member('sg-sovereignshield-submitter-us') THEN obs_val
  WHEN upper(coalesce(obs_conf, '')) IN ('C', 'N') THEN NULL
  ELSE obs_val
END;

-- =====================================================================
-- 3. ROW-LEVEL SECURITY (RLS) FUNCTION - MACRO HISTORY
-- Segment 9 of the 11-dimension TIME_SERIES_CODE is L_REP_CTY.
--
-- try_element_at is used instead of element_at: under ANSI mode an
-- out-of-range index raises INVALID_ARRAY_INDEX, which would abort every query
-- against the table if a malformed key were ever persisted. Returning NULL
-- instead fails closed, making the malformed row invisible to submitters.
--
-- The pipeline service principal (spn-sovereignshield-cicd) MUST be a member of
-- sg-sovereignshield-admin. The SCD2 engine reads this table to find records to
-- expire; if the filter hid those rows the merge would treat every row as new,
-- silently duplicating history and never closing prior versions.
-- =====================================================================
CREATE OR REPLACE FUNCTION fn_rls_lbs_country_lock(time_series_code STRING)
RETURNS BOOLEAN
RETURN CASE
  WHEN is_account_group_member('sg-sovereignshield-admin')
    OR is_account_group_member('sg-sovereignshield-researchers') THEN TRUE
  WHEN is_account_group_member('sg-sovereignshield-submitter-ca')
    AND try_element_at(split(time_series_code, '\\.'), 9) = 'CA' THEN TRUE
  WHEN is_account_group_member('sg-sovereignshield-submitter-us')
    AND try_element_at(split(time_series_code, '\\.'), 9) = 'US' THEN TRUE
  ELSE FALSE
END;

-- =====================================================================
-- 4. ROW-LEVEL SECURITY (RLS) FUNCTION - MICRO LEDGER
-- Defense in depth: the raw ledger carries bank-identifying detail, so
-- sovereign isolation is enforced at the source table rather than relying
-- solely on table-level grants.
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
  OBS_VALUE DOUBLE MASK fn_ddm_obs_conf_mask USING COLUMNS (OBS_CONF),
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
WITH ROW FILTER fn_rls_lbs_country_lock ON (TIME_SERIES_CODE);

-- =====================================================================
-- 7. RE-ATTACH POLICIES ON PRE-EXISTING TABLES
-- No-ops (hence tolerated failures) when the CREATE TABLE statements above
-- just built the tables with their policies already inline.
-- =====================================================================
-- @tolerate-failure
ALTER TABLE lbs_sdmx_history ALTER COLUMN OBS_VALUE SET MASK fn_ddm_obs_conf_mask USING COLUMNS (OBS_CONF);
-- @tolerate-failure
ALTER TABLE lbs_sdmx_history SET ROW FILTER fn_rls_lbs_country_lock ON (TIME_SERIES_CODE);
-- @tolerate-failure
ALTER TABLE lbs_micro_transactions SET ROW FILTER fn_rls_micro_country_lock ON (reporting_country);

-- =====================================================================
-- 8. QUARANTINE VIEW ISOLATION
-- Serves only the last valid published state. A quarantined revision is
-- written to lbs_sdmx_history with IS_CURRENT = false, so it can never surface
-- here and never interrupts consumers of the prior published value.
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

-- Schema USAGE Grants
GRANT USAGE ON SCHEMA dbw_sovereignshield.sovereign_shield TO `sg-sovereignshield-admin`;
GRANT USAGE ON SCHEMA dbw_sovereignshield.sovereign_shield TO `sg-sovereignshield-submitter-ca`;
GRANT USAGE ON SCHEMA dbw_sovereignshield.sovereign_shield TO `sg-sovereignshield-submitter-us`;
GRANT USAGE ON SCHEMA dbw_sovereignshield.sovereign_shield TO `sg-sovereignshield-researchers`;

-- Admins: Full permissions on underlying tables
GRANT ALL PRIVILEGES ON TABLE lbs_micro_transactions TO `sg-sovereignshield-admin`;
GRANT ALL PRIVILEGES ON TABLE lbs_sdmx_history TO `sg-sovereignshield-admin`;

-- Submitters: Select access to history table (RLS filter active)
GRANT SELECT ON TABLE lbs_sdmx_history TO `sg-sovereignshield-submitter-ca`;
GRANT SELECT ON TABLE lbs_sdmx_history TO `sg-sovereignshield-submitter-us`;

-- Submitters: Select access to their own micro ledger rows (RLS filter active)
GRANT SELECT ON TABLE lbs_micro_transactions TO `sg-sovereignshield-submitter-ca`;
GRANT SELECT ON TABLE lbs_micro_transactions TO `sg-sovereignshield-submitter-us`;

-- Researchers: Select access ONLY to published view (Quarantine filter active)
GRANT SELECT ON VIEW v_lbs_sdmx_published TO `sg-sovereignshield-researchers`;