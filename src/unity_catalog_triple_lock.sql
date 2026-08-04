USE CATALOG dbw_sovereignshield;
USE SCHEMA sovereign_shield;

-- =====================================================================
-- 1. CLEANUP EXISTING ASSETS
-- =====================================================================
DROP VIEW IF EXISTS v_lbs_sdmx_published;
DROP TABLE IF EXISTS lbs_sdmx_history;
DROP TABLE IF EXISTS lbs_micro_transactions;
DROP FUNCTION IF EXISTS fn_rls_lbs_country_lock;
DROP FUNCTION IF EXISTS fn_ddm_obs_conf_mask;

-- =====================================================================
-- 2. APPEND-ONLY MICRO TRANSACTIONS LEDGER
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
);

-- =====================================================================
-- 3. DYNAMIC DATA MASKING (DDM) FUNCTION
-- =====================================================================
-- Mask OBS_VALUE to NULL for confidential ('C' or 'N') records unless 
-- the user belongs to Admin or Submitter groups.
CREATE OR REPLACE FUNCTION fn_ddm_obs_conf_mask(obs_val DOUBLE, obs_conf STRING)
RETURNS DOUBLE
RETURN CASE
  WHEN is_account_group_member('sg-sovereignshield-admin') 
    OR is_account_group_member('sg-sovereignshield-submitter-ca') 
    OR is_account_group_member('sg-sovereignshield-submitter-us') THEN obs_val
  WHEN obs_conf IN ('C', 'N') THEN NULL
  ELSE obs_val
END;

-- =====================================================================
-- 4. ROW-LEVEL SECURITY (RLS) FUNCTION
-- =====================================================================
-- Evaluates Segment 9 of TIME_SERIES_CODE against uppercase ISO country codes (e.g., 'CA', 'US').
CREATE OR REPLACE FUNCTION fn_rls_lbs_country_lock(time_series_code STRING)
RETURNS BOOLEAN
RETURN CASE
  WHEN is_account_group_member('sg-sovereignshield-admin') 
    OR is_account_group_member('sg-sovereignshield-researchers') THEN TRUE
  WHEN is_account_group_member('sg-sovereignshield-submitter-ca') 
    AND element_at(split(time_series_code, '\\.'), 9) = 'CA' THEN TRUE
  WHEN is_account_group_member('sg-sovereignshield-submitter-us') 
    AND element_at(split(time_series_code, '\\.'), 9) = 'US' THEN TRUE
  ELSE FALSE
END;

-- =====================================================================
-- 5. MACRO SDMX HISTORY TABLE (WITH RLS & DDM APPLIED)
-- =====================================================================
CREATE TABLE IF NOT EXISTS lbs_sdmx_history (
  TIME_SERIES_CODE STRING,
  DATE STRING,
  IBS_AGG STRING,
  OBS_VALUE DOUBLE MASK fn_ddm_obs_conf_mask(OBS_CONF),
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
-- 6. QUARANTINE PUBLISHED VIEW
-- =====================================================================
-- Only exposes non-quarantined (PUBLISHED) and current SCD2 records.
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
-- 7. UNITY CATALOG GRANTS FOR SYNCHRONIZED GROUPS
-- =====================================================================
GRANT USAGE ON CATALOG dbw_sovereignshield TO `sg-sovereignshield-admin`, `sg-sovereignshield-submitter-ca`, `sg-sovereignshield-submitter-us`, `sg-sovereignshield-researchers`;
GRANT USAGE ON SCHEMA dbw_sovereignshield.sovereign_shield TO `sg-sovereignshield-admin`, `sg-sovereignshield-submitter-ca`, `sg-sovereignshield-submitter-us`, `sg-sovereignshield-researchers`;

-- Admins: Full permissions
GRANT ALL PRIVILEGES ON TABLE lbs_micro_transactions TO `sg-sovereignshield-admin`;
GRANT ALL PRIVILEGES ON TABLE lbs_sdmx_history TO `sg-sovereignshield-admin`;

-- Submitters: Select access to history table (RLS filter active)
GRANT SELECT ON TABLE lbs_sdmx_history TO `sg-sovereignshield-submitter-ca`, `sg-sovereignshield-submitter-us`;

-- Researchers: Select access ONLY to the published view (Quarantine filter active)
GRANT SELECT ON VIEW v_lbs_sdmx_published TO `sg-sovereignshield-researchers`;