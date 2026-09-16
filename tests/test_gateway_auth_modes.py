import pytest
from uuid import uuid4

from uc_query import DatabricksBackend


@pytest.mark.parametrize("tenant, expected_mode", [("tenant-id", "azure-client-secret"), (None, "oauth-m2m")])
def test_public_credentials_use_the_hosting_platform_auth_mode(monkeypatch, tenant, expected_mode):
    import databricks.sdk.core as core
    from databricks import sql

    monkeypatch.delenv("ARM_TENANT_ID", raising=False)
    monkeypatch.delenv("DATABRICKS_AZURE_TENANT_ID", raising=False)
    if tenant:
        monkeypatch.setenv("DATABRICKS_AZURE_TENANT_ID", tenant)
    configurations = []

    def config(**values):
        configurations.append(values)
        return values

    monkeypatch.setattr(core, "Config", config)
    monkeypatch.setattr(core, "azure_service_principal", lambda config: config["auth_type"])
    monkeypatch.setattr(core, "oauth_service_principal", lambda config: config["auth_type"])
    monkeypatch.setattr(sql, "connect", lambda **values: values["credentials_provider"]())
    backend = DatabricksBackend()
    backend.hostname = "workspace.example.test"
    backend.http_path = "/sql/1.0/warehouses/test"
    backend.client_id = "configured-client"
    backend.client_secret = uuid4().hex
    assert backend._connect(None) == expected_mode
    assert configurations[0]["auth_type"] == expected_mode