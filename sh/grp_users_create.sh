#!/bin/bash

# Define your tenant domain and a secure temporary password
TENANT_DOMAIN="13668754CANADAINC.onmicrosoft.com"
TEMP_PASSWORD="Fe301A@Mat5helo"

echo "Creating Microsoft Entra ID Groups..."
ADMIN_GROUP=$(az ad group create --display-name "sg-sovereignshield-admin" --mail-nickname "sg-ss-admin" --query id -o tsv)
CA_GROUP=$(az ad group create --display-name "sg-sovereignshield-submitter-ca" --mail-nickname "sg-ss-sub-ca" --query id -o tsv)
US_GROUP=$(az ad group create --display-name "sg-sovereignshield-submitter-us" --mail-nickname "sg-ss-sub-us" --query id -o tsv)
RESEARCH_GROUP=$(az ad group create --display-name "sg-sovereignshield-researchers" --mail-nickname "sg-ss-research" --query id -o tsv)

# The public tier holds no humans. Its only member is the portal's proxy service
# principal, created by kv_spn_create.sh. Without this group the row filter's
# fail-closed default returns zero rows to every anonymous visitor and the
# portal renders empty.
PUBLIC_GROUP=$(az ad group create --display-name "sg-sovereignshield-public" --mail-nickname "sg-ss-public" --query id -o tsv)
echo "Public tier group: $PUBLIC_GROUP"

echo "Creating Microsoft Entra ID Users..."
ADMIN_USER=$(az ad user create --display-name "Admin Lead" --user-principal-name "admin_lead@$TENANT_DOMAIN" --password "$TEMP_PASSWORD" --query id -o tsv)
CA_USER=$(az ad user create --display-name "BOC Analyst" --user-principal-name "boc_analyst@$TENANT_DOMAIN" --password "$TEMP_PASSWORD" --query id -o tsv)
US_USER=$(az ad user create --display-name "Fed Analyst" --user-principal-name "fed_analyst@$TENANT_DOMAIN" --password "$TEMP_PASSWORD" --query id -o tsv)
RESEARCH_USER=$(az ad user create --display-name "Econ Researcher" --user-principal-name "econ_researcher@$TENANT_DOMAIN" --password "$TEMP_PASSWORD" --query id -o tsv)

echo "Assigning Users to Groups..."
az ad group member add --group "$ADMIN_GROUP" --member-id "$ADMIN_USER"
az ad group member add --group "$CA_GROUP" --member-id "$CA_USER"
az ad group member add --group "$US_GROUP" --member-id "$US_USER"
az ad group member add --group "$RESEARCH_GROUP" --member-id "$RESEARCH_USER"

echo "Zero-Trust Identity Layer Provisioned Successfully."
echo "Remember: these groups must be synchronised to the Databricks account before"
echo "is_account_group_member() can resolve them inside Unity Catalog."