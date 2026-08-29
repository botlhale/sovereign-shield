-- =====================================================================
-- SovereignShield Access-Control Plane Grants
--
-- OWNERSHIP BOUNDARY
-- These statements belong to the *infrastructure and access-control plane*,
-- which Terraform owns in the IaC deployment path
-- (terraform/modules/unity_catalog_governance). This file exists so that the
-- script-only quickstart (`sh/` + Databricks Asset Bundles, no Terraform) can
-- still reach a working state.
--
-- The two paths are equivalent and non-conflicting: Terraform uses the additive
-- `databricks_grant` resource rather than the authoritative `databricks_grants`,
-- so it never revokes a privilege it does not declare. GRANT is idempotent in
-- Unity Catalog, so re-applying either path converges on the same state.
--
-- What is NOT here: table DDL, the policy UDFs, and the SET ROW FILTER / SET
-- MASK bindings. Those are the *data and policy plane*, they evolve with the
-- data model, and they live in unity_catalog_triple_lock.sql. Splitting them
-- keeps one writer per object: Terraform would otherwise report drift after
-- every pipeline run, and an apply could detach a live filter mid-query.
--
-- One principal per statement: Unity Catalog rejects multiple principals in a
-- single TO clause.
-- =====================================================================

USE CATALOG dbw_sovereignshield;
USE SCHEMA sovereign_shield;

-- =====================================================================
-- 1. CATALOG AND SCHEMA TRAVERSAL
-- Traversal alone reveals nothing. Every row returned past this point is still
-- subject to the row filter and column mask.
-- =====================================================================
GRANT USAGE ON CATALOG dbw_sovereignshield TO `sg-sovereignshield-admin`;
GRANT USAGE ON CATALOG dbw_sovereignshield TO `sg-sovereignshield-submitter-ca`;
GRANT USAGE ON CATALOG dbw_sovereignshield TO `sg-sovereignshield-submitter-us`;
GRANT USAGE ON CATALOG dbw_sovereignshield TO `sg-sovereignshield-researchers`;
GRANT USAGE ON CATALOG dbw_sovereignshield TO `sg-sovereignshield-public`;

GRANT USAGE ON SCHEMA dbw_sovereignshield.sovereign_shield TO `sg-sovereignshield-admin`;
GRANT USAGE ON SCHEMA dbw_sovereignshield.sovereign_shield TO `sg-sovereignshield-submitter-ca`;
GRANT USAGE ON SCHEMA dbw_sovereignshield.sovereign_shield TO `sg-sovereignshield-submitter-us`;
GRANT USAGE ON SCHEMA dbw_sovereignshield.sovereign_shield TO `sg-sovereignshield-researchers`;
GRANT USAGE ON SCHEMA dbw_sovereignshield.sovereign_shield TO `sg-sovereignshield-public`;

-- =====================================================================
-- 2. ADMINISTRATORS / CENTRAL AUDITORS
-- =====================================================================
GRANT ALL PRIVILEGES ON TABLE lbs_micro_transactions TO `sg-sovereignshield-admin`;
GRANT ALL PRIVILEGES ON TABLE lbs_sdmx_history TO `sg-sovereignshield-admin`;

-- =====================================================================
-- 3. MACRO HISTORY
-- The SELECT grant is deliberately broad for every persona. The grant decides
-- *reachability*; the row filter decides *visibility*. Attempting to express
-- sovereignty through grants instead would require one securable per
-- jurisdiction and would still not mask a cell.
-- =====================================================================
GRANT SELECT ON TABLE lbs_sdmx_history TO `sg-sovereignshield-submitter-ca`;
GRANT SELECT ON TABLE lbs_sdmx_history TO `sg-sovereignshield-submitter-us`;
GRANT SELECT ON TABLE lbs_sdmx_history TO `sg-sovereignshield-researchers`;
GRANT SELECT ON TABLE lbs_sdmx_history TO `sg-sovereignshield-public`;

-- =====================================================================
-- 4. MICRO LEDGER
-- Institution-identifying detail. Submitters only, filtered to their own
-- jurisdiction. Researchers and the public tier are deliberately absent -
-- protecting the aggregate while leaving the source open is not sovereignty.
-- =====================================================================
GRANT SELECT ON TABLE lbs_micro_transactions TO `sg-sovereignshield-submitter-ca`;
GRANT SELECT ON TABLE lbs_micro_transactions TO `sg-sovereignshield-submitter-us`;

-- =====================================================================
-- 5. CURATED PUBLISHED VIEW
-- A convenience for BI tools with a uniform audience. Note that a Unity Catalog
-- view resolves group membership against the VIEW OWNER, not the caller, which
-- is why the portal queries the base table instead.
-- =====================================================================
GRANT SELECT ON VIEW v_lbs_sdmx_published TO `sg-sovereignshield-researchers`;
GRANT SELECT ON VIEW v_lbs_sdmx_published TO `sg-sovereignshield-public`;
