"""Container-scope and report-routing unit checks; no real Azure requests."""
from contextlib import contextmanager
import json
from unittest.mock import Mock

from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
import pytest
import src.cloud_storage as storage
import scripts.upload_results_azure as upload


@pytest.fixture(autouse=True)
def no_real_clients(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Readiness unit tests must not construct real Azure clients or credentials")
    monkeypatch.setattr(storage, "DefaultAzureCredential", forbidden)
    monkeypatch.setattr(storage, "BlobServiceClient", forbidden)


def test_existing_private_container_requires_no_creation():
    container = Mock()
    container.get_container_properties.return_value = {"public_access": None}
    service = Mock()
    service.get_container_client.return_value = container
    assert storage.private_container(service) is container
    container.get_container_properties.assert_called_once_with()
    container.create_container.assert_not_called()


@pytest.mark.parametrize("error, message", [
    (ResourceNotFoundError("missing"), "does not exist"),
    (HttpResponseError("access denied"), "inaccessible"),
])
def test_absent_or_inaccessible_container_fails_before_any_upload(tmp_path, error, message):
    container = Mock()
    container.get_container_properties.side_effect = error
    service = Mock()
    service.get_container_client.return_value = container
    with pytest.raises(ValueError, match=message):
        storage.round_trip(service, tmp_path, tmp_path / "downloads")
    container.create_container.assert_not_called()
    container.upload_blob.assert_not_called()
    container.list_blobs.assert_not_called()


@pytest.mark.parametrize("access", ["blob", "container"])
def test_public_container_rejected_without_mutating_permissions(access):
    container = Mock()
    container.get_container_properties.return_value = {"public_access": access}
    service = Mock()
    service.get_container_client.return_value = container
    with pytest.raises(ValueError, match="public access"):
        storage.private_container(service)
    container.create_container.assert_not_called()
    container.set_container_access_policy.assert_not_called()


def test_azurite_creation_remains_explicit():
    container = Mock()
    container.get_container_properties.return_value = {"public_access": None}
    service = Mock()
    service.get_container_client.return_value = container
    assert storage.private_container(service, create=True) is container
    container.create_container.assert_called_once_with(public_access=None)


def test_reports_have_distinct_destinations(monkeypatch, tmp_path):
    monkeypatch.setattr(upload, "ROOT", tmp_path)
    assert upload.verification_report_path("azurite") == tmp_path / "results/azure_storage_verification.json"
    assert upload.verification_report_path("azure") == tmp_path / ".cache/azure_storage_verification_real.json"
    with pytest.raises(ValueError, match="Unknown"):
        upload.verification_report_path("unknown")


@pytest.mark.parametrize("mode", ["azurite", "azure"])
def test_cli_routes_creation_and_success_metadata_without_account_details(monkeypatch, tmp_path, mode, capsys):
    monkeypatch.setattr(upload, "ROOT", tmp_path)
    config = storage.StorageConfig(mode, "https://examplestorage.blob.core.windows.net")
    monkeypatch.setattr(upload.StorageConfig, "from_environment", lambda: config)
    @contextmanager
    def connect(config):
        yield object()
    monkeypatch.setattr(upload, "connect_storage", connect)
    called = {}
    def round_trip(service, root, output, *, create_container):
        called["create"] = create_container
        return {"container": storage.CONTAINER, "container_private": True,
                "listed_blobs": list(storage.ARTIFACTS), "artifacts": []}
    monkeypatch.setattr(upload, "round_trip", round_trip)
    old_report = tmp_path / "results/azure_storage_verification.json"
    old_report.parent.mkdir()
    old_report.write_text("original local emulator evidence")
    package = tmp_path / "node_modules/azurite/package.json"
    package.parent.mkdir(parents=True)
    package.write_text(json.dumps({"version": "unit-test"}))
    assert upload.main() == 0
    assert called["create"] is (mode == "azurite")
    report = json.loads(upload.verification_report_path(mode).read_text())
    assert report["real_azure_used"] is (mode == "azure")
    assert report["verification_scope"] == ("LOCAL EMULATOR VERIFIED" if mode == "azurite" else "REAL AZURE STORAGE ROUND TRIP VERIFIED")
    assert set(report) == {"container", "container_private", "listed_blobs", "artifacts", "verification_scope",
                           "real_azure_used", "service_api_version", "azure_storage_blob_version", "azure_identity_version"} | ({"azurite_version"} if mode == "azurite" else set())
    if mode == "azure":
        assert old_report.read_text() == "original local emulator evidence"
        assert "azurite_version" not in report
    assert config.account_url not in capsys.readouterr().out


def test_failed_cloud_round_trip_writes_no_success_report(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(upload, "ROOT", tmp_path)
    monkeypatch.setattr(upload.StorageConfig, "from_environment", lambda: storage.StorageConfig("azure", "https://examplestorage.blob.core.windows.net"))
    @contextmanager
    def connect(config):
        yield object()
    monkeypatch.setattr(upload, "connect_storage", connect)
    def fail(*args, **kwargs):
        raise ValueError("The container is inaccessible")
    monkeypatch.setattr(upload, "round_trip", fail)
    assert upload.main() == 1
    assert not upload.verification_report_path("azure").exists()
    assert not upload.verification_report_path("azurite").exists()
    output = capsys.readouterr()
    assert "VERIFIED" not in output.out
    assert "inaccessible" in output.err
