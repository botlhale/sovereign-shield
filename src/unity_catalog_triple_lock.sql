-- =====================================================================
-- SovereignShield Triple-Lock Security Architecture
--
-- This script is IDEMPOTENT and NON-DESTRUCTIVE. It runs as the first task of
-- every pipeline execution, so it must never drop the historical tables:
-- doing so silently erases the entire SCD2 lineage and leaves the platform
-- unable to protect a published record from a quarantined revision.
--
-- apply_security.py assigns content-addressed names to immutable policy functions.
-- =====================================================================

USE CATALOG dbw_sovereignshield;

-- The catalog is the workspace default catalog, created with the workspace.
-- The schema is not, so a rebuilt workspace would otherwise abort here.
CREATE SCHEMA IF NOT EXISTS sovereign_shield;

-- The bank-level ledger lives apart from the published history: it is what a
-- reporting country holds before it aggregates and applies confidentiality, and
-- in practice it never leaves the jurisdiction. Terraform owns both schemas; these
-- statements exist so the script still runs against a hand-made workspace.
CREATE SCHEMA IF NOT EXISTS sovereign_intake;

USE SCHEMA sovereign_shield;

-- =====================================================================
-- 2. DYNAMIC DATA MASKING (DDM) FUNCTION
--
-- Any observation not explicitly free (OBS_CONF 'F') is nulled for everyone
-- except the platform administrators and the sovereign that reported it:
-- C, N and the secondary-confidentiality codes D/S, plus unknown or missing.
--
-- L_REP_CTY is a mask input, not decoration: without it the function cannot
-- tell whose confidential value it is holding, so any submitter would unmask
-- every other jurisdiction's restricted cells. It stores segment 9 of
-- TIME_SERIES_CODE as a separate, unmasked column because Unity Catalog rejects
-- a masked column as the input of another policy, and the key itself is masked.
-- =====================================================================
CREATE OR REPLACE FUNCTION fn_ddm_obs_conf_mask(
  obs_val DECIMAL(38,3),
  obs_conf STRING,
  l_rep_cty STRING
)
RETURNS DECIMAL(38,3)
RETURN CASE
  WHEN is_account_group_member('sg-sovereignshield-admin') THEN obs_val
  WHEN is_account_group_member('sg-sovereignshield-submitter-ca')
    AND coalesce(l_rep_cty = 'CA', FALSE) THEN obs_val
  WHEN is_account_group_member('sg-sovereignshield-submitter-us')
    AND coalesce(l_rep_cty = 'US', FALSE) THEN obs_val
  WHEN upper(trim(coalesce(obs_conf, ''))) = 'F' THEN obs_val
  ELSE NULL
END;

-- =====================================================================
-- 2a. DISCOVERY GATEWAY COORDINATE MASK
--
-- A withheld value must not carry its exact coordinates. For callers who are
-- not entitled to the measure, segments 10-11 (L_CP_SECTOR, L_CP_COUNTRY)
-- become 'xx': Q.S.C.A.USD.D.5J.A.US.A.5J -> Q.S.C.A.USD.D.5J.A.US.xx.xx.
-- The reveal rule is identical to fn_ddm_obs_conf_mask.
--
-- Segments 1-9 are preserved, so segment 9 still matches L_REP_CTY, the
-- unmasked sovereignty anchor every policy reads.
-- Masks resolve before query predicates, so filtering on segments 10-11
-- cannot probe a masked row. Keys without exactly 11 segments fail closed.
-- =====================================================================
CREATE OR REPLACE FUNCTION fn_ddm_series_key_mask(
  time_series_code STRING,
  obs_conf STRING,
  l_rep_cty STRING
)
RETURNS STRING
RETURN CASE
  WHEN is_account_group_member('sg-sovereignshield-admin') THEN time_series_code
  WHEN is_account_group_member('sg-sovereignshield-submitter-ca')
    AND coalesce(l_rep_cty = 'CA', FALSE) THEN time_series_code
  WHEN is_account_group_member('sg-sovereignshield-submitter-us')
    AND coalesce(l_rep_cty = 'US', FALSE) THEN time_series_code
  WHEN upper(trim(coalesce(obs_conf, ''))) = 'F' THEN time_series_code
  WHEN coalesce(size(split(time_series_code, '\\.')) = 11, FALSE)
    THEN concat(substring_index(time_series_code, '.', 9), '.xx.xx')
  ELSE NULL
END;

-- =====================================================================
-- 2b. LINEAGE MASK
--
-- RECORD_ID hashes the full observation key with a visible SUBMISSION_ID, so
-- the masked coordinates could be recovered by enumerating segments 10-11.
-- version_hash hashes the measure with otherwise visible attributes, which
-- would confirm a guessed value. VALIDATION_NOTES lists the rules a row takes
-- part in, which depends on its coordinates. All three follow the same reveal
-- rule as the measure and are otherwise NULL.
-- =====================================================================
CREATE OR REPLACE FUNCTION fn_ddm_lineage_mask(
  lineage STRING,
  obs_conf STRING,
  l_rep_cty STRING
)
RETURNS STRING
RETURN CASE
  WHEN is_account_group_member('sg-sovereignshield-admin') THEN lineage
  WHEN is_account_group_member('sg-sovereignshield-submitter-ca')
    AND coalesce(l_rep_cty = 'CA', FALSE) THEN lineage
  WHEN is_account_group_member('sg-sovereignshield-submitter-us')
    AND coalesce(l_rep_cty = 'US', FALSE) THEN lineage
  WHEN upper(trim(coalesce(obs_conf, ''))) = 'F' THEN lineage
  ELSE NULL
END;

-- =====================================================================
-- 3. MULTI-COLUMN ROW-LEVEL SECURITY (RLS) - MACRO HISTORY
--
-- Entitlement is evaluated from three columns at once - the reporting country
-- (L_REP_CTY, segment 9 of the SDMx key), the batch lifecycle state and the
-- confidentiality flag - so a quarantined or restricted record can never leak
-- through a persona entitled only to clean published data.
--
-- The tiers are composed with OR rather than CASE/WHEN so that privileges are
-- ADDITIVE. A principal holding two memberships (e.g. a Canadian regional submitter
-- who is also a researcher) receives the union of both entitlements instead of
-- whichever branch happens to be evaluated first.
--
-- Persona matrix:
--   sg-sovereignshield-admin        1 = 1 (every jurisdiction and state)
--   sg-sovereignshield-researchers  BATCH_STATUS = 'PUBLISHED' (values, coordinates
--                                   and lineage of restricted rows masked)
--   sg-sovereignshield-submitter-xx own segment-9 rows in full, plus every other
--                                   sovereign's PUBLISHED + free-to-publish rows
--   sg-sovereignshield-public       BATCH_STATUS = 'PUBLISHED' AND OBS_CONF = 'F'
--   (no recognised membership)      FALSE - fails closed, zero rows
--
-- A NULL anchor compares to NULL, and the coalesce turns that NULL into FALSE,
-- so a row without a reporting country is invisible rather than universally
-- visible.
--
-- The pipeline service principal (spn-sovereignshield-cicd) MUST be a member of
-- sg-sovereignshield-admin. The SCD2 engine reads this table to find records to
-- expire; if the filter hid those rows the merge would treat every row as new,
-- silently duplicating history and never closing prior versions.
-- =====================================================================
CREATE OR REPLACE FUNCTION fn_rls_multi_persona_lock(
  l_rep_cty STRING,
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
    AND upper(trim(coalesce(obs_conf, ''))) = 'F'
  )
  OR (
    is_account_group_member('sg-sovereignshield-submitter-ca')
    AND coalesce(l_rep_cty = 'CA', FALSE)
  )
  OR (
    is_account_group_member('sg-sovereignshield-submitter-us')
    AND coalesce(l_rep_cty = 'US', FALSE)
  );

-- =====================================================================
-- 4. ROW-LEVEL SECURITY (RLS) FUNCTION - MICRO LEDGER
-- Defense in depth: the raw ledger carries bank-identifying detail, so
-- sovereign isolation is enforced at the source table rather than relying
-- solely on table-level grants. Researchers and the public portal principal
-- are deliberately absent - no persona reaches institution-level rows.
-- =====================================================================
CREATE OR REPLACE FUNCTION sovereign_intake.fn_rls_micro_country_lock(reporting_country STRING)
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
--
-- In sovereign_intake, not alongside the published history. This is what a
-- reporting country holds before it aggregates and decides confidentiality; only
-- the aggregate is ever filed. The filter function is co-located with the table it
-- protects rather than referenced across schemas.
-- =====================================================================
CREATE TABLE IF NOT EXISTS sovereign_intake.lbs_micro_transactions (
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
  transaction_amount DECIMAL(38,3),
  obs_conf STRING,
  agg_scope STRING,
  date_scope STRING,
  transaction_timestamp TIMESTAMP
)
WITH ROW FILTER sovereign_intake.fn_rls_micro_country_lock ON (reporting_country)
TBLPROPERTIES ('delta.isolationLevel' = 'Serializable');

-- =====================================================================
-- 6. MACRO SDMX HISTORY TABLE (SCD2, WITH RLS & DDM APPLIED)
--
-- Named for the aggregation grain rather than a collection: the engine is
-- domain-agnostic and this table holds whatever statistical aggregate a
-- reporting body submits. AGG_CODE carries the framework code ('LBSR' for the
-- BIS Locational Banking Statistics example used to validate the model).
--
-- OBS_VALUE may legitimately be negative: LBS positions record both asset and
-- liability directions. Zero-valued observations are not reported at all under
-- SDMx convention and are filtered upstream.
--
-- L_REP_CTY is written from segment 9 of TIME_SERIES_CODE with every row and
-- stays unmasked: it is the only key-derived policy input, because a masked
-- column cannot be referenced by another policy.
-- =====================================================================
CREATE TABLE IF NOT EXISTS agg_sdmx_history (
  TIME_SERIES_CODE STRING MASK fn_ddm_series_key_mask USING COLUMNS (OBS_CONF, L_REP_CTY),
  L_REP_CTY STRING,
  DATE STRING,
  AGG_CODE STRING,
  OBS_VALUE DECIMAL(38,3) MASK fn_ddm_obs_conf_mask USING COLUMNS (OBS_CONF, L_REP_CTY),
  OBS_STATUS STRING,
  OBS_CONF STRING,
  QUALITY_STATUS STRING,
  FAILED_RULE_ID STRING,
  BATCH_STATUS STRING,
  BATCH_FAILED_RULE_ID STRING,
  VALIDATION_NOTES STRING MASK fn_ddm_lineage_mask USING COLUMNS (OBS_CONF, L_REP_CTY),
  SUBMISSION_ID STRING,
  SOURCE_SHA256 STRING,
  RECORD_ID STRING MASK fn_ddm_lineage_mask USING COLUMNS (OBS_CONF, L_REP_CTY),
  SUBMITTED_AT TIMESTAMP,
  RECEIVED_AT TIMESTAMP,
  version_hash STRING MASK fn_ddm_lineage_mask USING COLUMNS (OBS_CONF, L_REP_CTY),
  VALID_FROM TIMESTAMP,
  VALID_TO TIMESTAMP,
  IS_CURRENT BOOLEAN
)
WITH ROW FILTER fn_rls_multi_persona_lock ON (L_REP_CTY, BATCH_STATUS, OBS_CONF)
TBLPROPERTIES ('delta.isolationLevel' = 'Serializable');

-- =====================================================================
-- 7. REPLACE BINDINGS WITHOUT DETACHING THE PREVIOUS POLICY
-- =====================================================================
ALTER TABLE agg_sdmx_history ALTER COLUMN OBS_VALUE SET MASK fn_ddm_obs_conf_mask USING COLUMNS (OBS_CONF, L_REP_CTY);
ALTER TABLE agg_sdmx_history ALTER COLUMN TIME_SERIES_CODE SET MASK fn_ddm_series_key_mask USING COLUMNS (OBS_CONF, L_REP_CTY);
ALTER TABLE agg_sdmx_history ALTER COLUMN RECORD_ID SET MASK fn_ddm_lineage_mask USING COLUMNS (OBS_CONF, L_REP_CTY);
ALTER TABLE agg_sdmx_history ALTER COLUMN version_hash SET MASK fn_ddm_lineage_mask USING COLUMNS (OBS_CONF, L_REP_CTY);
ALTER TABLE agg_sdmx_history ALTER COLUMN VALIDATION_NOTES SET MASK fn_ddm_lineage_mask USING COLUMNS (OBS_CONF, L_REP_CTY);
ALTER TABLE agg_sdmx_history SET ROW FILTER fn_rls_multi_persona_lock ON (L_REP_CTY, BATCH_STATUS, OBS_CONF);
ALTER TABLE sovereign_intake.lbs_micro_transactions SET ROW FILTER sovereign_intake.fn_rls_micro_country_lock ON (reporting_country);

-- =====================================================================
-- 8. QUARANTINE VIEW ISOLATION
-- Serves only the last valid published state. A quarantined revision is
-- written to agg_sdmx_history with IS_CURRENT = false, so it can never surface
-- here and never interrupts consumers of the prior published value.
--
-- The portal queries the base table to support both current and audit views.
-- Unity Catalog dynamic views also support caller-aware group membership.
-- =====================================================================
CREATE OR REPLACE VIEW v_agg_sdmx_published AS
SELECT 
  TIME_SERIES_CODE,
  DATE,
  AGG_CODE,
  OBS_VALUE,
  OBS_STATUS,
  OBS_CONF
FROM agg_sdmx_history
WHERE BATCH_STATUS = 'PUBLISHED' 
  AND IS_CURRENT = true;

-- =====================================================================
-- 9. ACCESS-CONTROL PLANE
-- Grants live in unity_catalog_grants.sql, applied immediately after this
-- script by apply_security.py. They are the access-control plane, owned by
-- Terraform in the IaC deployment path; this file owns only the data and
-- policy plane, so exactly one system writes each object.
-- =====================================================================

-- (no GRANT statements below this line by design)