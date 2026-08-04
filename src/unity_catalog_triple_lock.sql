-- =================================================================================
-- PROJECT SOVEREIGNSHIELD: TRIPLE-LOCK SECURITY DEPLOYMENT (UNITY CATALOG)
-- Execution Identity: Azure Service Principal (via CI/CD)
-- Target Catalog: dbw_sovereignshield.sovereign_shield
-- =================================================================================

USE CATALOG dbw_sovereignshield;
CREATE SCHEMA IF NOT EXISTS sovereign_shield;
USE SCHEMA sovereign_shield;

-- 1. Micro-Level Transaction Table (Simulating Multi-Country Submissions)
CREATE TABLE IF NOT EXISTS lbs_micro_transactions (
    transaction_id STRING,
    reporting_country STRING,      -- e.g., 'ca', 'us', 'gb', 'de'
    reporting_institution STRING, -- e.g., 'BOC_INST_01', 'FED_INST_04'
    counterpart_country STRING,   -- e.g., 'us', 'ca', 'jp'
    sector_code STRING,           -- e.g., 'NFC' (Non-Financial Corps), 'FC' (Financial Corps)
    currency STRING,              -- e.g., 'CAD', 'USD', 'EUR'
    transaction_amount DOUBLE,
    obs_conf STRING,              -- 'F' (Free), 'N' (Non-publishable), 'C' (Confidential)
    ibs_agg_scope STRING,         -- e.g., 'LBSR' (Locational Banking Statistics)
    date_scope STRING,            -- e.g., '2026-Q1'
    transaction_timestamp TIMESTAMP
) USING DELTA;

-- 2. Target Macro SDMX History Table
CREATE TABLE IF NOT EXISTS lbs_sdmx_history (
    TIME_SERIES_CODE STRING,      
    DATE STRING,                  -- Added missing column
    IBS_AGG STRING,               -- Added missing column
    OBS_VALUE DOUBLE,
    OBS_STATUS STRING,            -- Added missing column
    OBS_CONF STRING,
    BATCH_STATUS STRING,          -- Added missing column for the quarantine filter
    VALID_FROM TIMESTAMP,
    VALID_TO TIMESTAMP,
    IS_CURRENT BOOLEAN
) USING DELTA;

-- =================================================================================
-- LOCK 1: ROW-LEVEL SECURITY (RLS)
-- Dynamic Entra ID group matching via 11-dimension SDMx composite keys.
-- extracts L_REP_CTY (9th dimension, index 8 in Spark SQL split array).
-- =================================================================================

CREATE OR REPLACE FUNCTION fn_rls_country_access(time_series_code STRING)
RETURNS BOOLEAN
RETURN
  -- 1. Internal Admins bypass all row-level filters
  is_account_group_member('sg-sovereignshield-admin')
  
  -- 2. National analysts only see their sovereign data (e.g., matching 'ca' to 'sg-sovereignshield-submitter-ca')
  OR is_account_group_member(
      concat('sg-sovereignshield-submitter-', lower(split(time_series_code, '\\.')[8]))
  );

-- Apply RLS to the Central Macro History Table
ALTER TABLE lbs_sdmx_history
SET ROW FILTER fn_rls_country_access ON (TIME_SERIES_CODE);


-- =================================================================================
-- LOCK 2: DYNAMIC DATA MASKING (DDM)
-- Evaluates OBS_CONF. Masks restricted values to 'xxx' to preserve dimensional 
-- density for researchers without corrupting downstream numeric aggregations.
-- =================================================================================

CREATE OR REPLACE FUNCTION fn_ddm_confidential_value(
    obs_value DOUBLE, 
    obs_conf STRING, 
    time_series_code STRING
)
RETURNS STRING
RETURN
  CASE
    -- 1. Admins see all raw numerical values
    WHEN is_account_group_member('sg-sovereignshield-admin') THEN cast(obs_value AS STRING)
    
    -- 2. Sovereign submitters see their own raw numerical values, even if flagged 'N'
    WHEN is_account_group_member(concat('sg-sovereignshield-submitter-', lower(split(time_series_code, '\\.')[8]))) THEN cast(obs_value AS STRING)
    
    -- 3. Mask market-dominant/confidential records for external researchers & cross-regional users
    WHEN obs_conf IN ('N', 'C') THEN 'xxx'
    
    -- 4. Free for publication ('F') data remains visible as string-cast numbers
    ELSE cast(obs_value AS STRING)
  END;

-- Apply DDM to the Central Macro History Table
ALTER TABLE lbs_sdmx_history
ALTER COLUMN OBS_VALUE SET MASK fn_ddm_confidential_value USING COLUMNS (OBS_CONF, TIME_SERIES_CODE);


-- =================================================================================
-- PUBLIC RESEARCHER INTEGRITY GATE
-- Secures the "Quarterly Quarantine". Masks quarantined batches from public views.
-- =================================================================================

CREATE OR REPLACE VIEW v_lbs_sdmx_published AS
SELECT 
    TIME_SERIES_CODE,
    DATE,
    IBS_AGG,
    OBS_VALUE,  -- (Masked to 'xxx' for N/C records via DDM policy above)
    OBS_STATUS,
    OBS_CONF
FROM lbs_sdmx_history
WHERE BATCH_STATUS = 'PUBLISHED';