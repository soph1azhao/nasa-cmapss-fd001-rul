"""Unit checks plus opt-in tests that require a real local Azurite process."""
import base64
from dataclasses import replace
import os
from pathlib import Path
import secrets
import uuid

from azure.core.exceptions import HttpResponseError
from azure.storage.blob import BlobClient
import pytest
from src.cloud_storage import (API_VERSION, ARTIFACTS, StorageConfig, connect_storage, private_container,
                               upload_artifacts, download_artifacts, verify_bytes, round_trip)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def local_env():
    return {"AZURE_STORAGE_CONNECTION_STRING": "UseDevelopmentStorage=true",
            "AZURITE_ACCOUNT_NAME": "fd001dev",
            "AZURITE_ACCOUNT_KEY": base64.b64encode(secrets.token_bytes(64)).decode()}


def test_local_configuration_hides_credentials(local_env):
    config = StorageConfig.from_environment(local_env)
    assert config.mode == "azurite"
    assert config.account_url == "http://127.0.0.1:10000/fd001dev"
    assert local_env["AZURITE_ACCOUNT_KEY"] not in repr(config)


@pytest.mark.parametrize("change", [
    {"AZURE_STORAGE_CONNECTION_STRING": "invalid"},
    {"AZURITE_ACCOUNT_KEY": ""},
    {"AZURITE_ACCOUNT_KEY": "invalid-base64"},
    {"AZURITE_ACCOUNT_NAME": "invalid/account"},
    {"AZURITE_BLOB_PORT": "0"},
    {"AZURITE_BLOB_PORT": "65536"},
    {"AZURITE_BLOB_PORT": "not-a-port"},
    {"AZURE_STORAGE_ACCOUNT_URL": "https://examplestorage.blob.core.windows.net"},
])
def test_incorrect_local_configuration_fails_without_echoing_key(local_env, change):
    local_env.update(change)
    with pytest.raises(ValueError) as error:
        StorageConfig.from_environment(local_env)
    if local_env["AZURITE_ACCOUNT_KEY"]:
        assert local_env["AZURITE_ACCOUNT_KEY"] not in str(error.value)


@pytest.mark.parametrize("env", [{}, {"AZURE_STORAGE_ACCOUNT_URL": "http://examplestorage.blob.core.windows.net"},
                                  {"AZURE_STORAGE_ACCOUNT_URL": "https://examplestorage.blob.core.windows.net?sig=token"}])
def test_missing_or_unsafe_cloud_configuration(env):
    with pytest.raises(ValueError): StorageConfig.from_environment(env)


def test_entra_client_wiring_only(monkeypatch):
    # Constructor wiring only: this does NOT verify real Azure authentication.
    import src.cloud_storage as storage
    calls = {}
    class Credential:
        def close(self): calls["closed"] = True
    credential = Credential()
    monkeypatch.setattr(storage, "DefaultAzureCredential", lambda: credential)
    class Client:
        def __init__(self, url, **kwargs): calls.update(url=url, **kwargs)
        def __enter__(self): return self
        def __exit__(self, *args): pass
    monkeypatch.setattr(storage, "BlobServiceClient", Client)
    config = StorageConfig.from_environment({"AZURE_STORAGE_ACCOUNT_URL": "https://examplestorage.blob.core.windows.net"})
    with connect_storage(config): pass
    assert calls["credential"] is credential
    assert calls["closed"]
    assert config.mode == "azure"


def test_hash_mismatch_and_download_location_guard(tmp_path):
    with pytest.raises(ValueError, match="verification failed"):
        verify_bytes(b"original", b"changed")
    with pytest.raises(ValueError, match="Download directory"):
        round_trip(object(), tmp_path, tmp_path)
    assert verify_bytes(b"same", b"same")["bytes_equal"]


def test_artifact_allowlist_and_symlink_rejection(tmp_path):
    assert set(ARTIFACTS) == {"results/metrics.json", "results/model_comparison.csv", "figures/prediction_vs_actual.png"}
    (tmp_path / "results").mkdir()
    other = tmp_path / "not-an-artifact.txt"; other.write_text("do not upload")
    (tmp_path / "results/metrics.json").symlink_to(other)
    with pytest.raises(ValueError, match="symlinks"):
        upload_artifacts(object(), tmp_path)


@pytest.fixture
def azurite_service():
    if os.environ.get("FD001_AZURITE_TESTS") != "1":
        pytest.skip("Opt in with FD001_AZURITE_TESTS=1 after starting and configuring Azurite")
    config = StorageConfig.from_environment()
    assert config.mode == "azurite", "Integration tests must never contact real Azure"
    with connect_storage(config) as service:
        yield service, config


@pytest.mark.azurite
def test_live_azurite_round_trip_private_and_repeatable(azurite_service, tmp_path):
    service, config = azurite_service
    name = "fd001-test-" + uuid.uuid4().hex
    before = {name: (ROOT / name).read_bytes() for name in ARTIFACTS}
    try:
        for _ in range(2):
            report = round_trip(service, ROOT, tmp_path, name, create_container=True)
            assert report["container_private"] is True
            assert report["listed_blobs"] == sorted(ARTIFACTS)
            assert len(report["artifacts"]) == 3
            assert all(r["source_sha256"] == r["download_sha256"] and r["bytes_equal"] for r in report["artifacts"])
        # A real anonymous request must fail for this private container.
        url = f"{config.account_url}/{name}/{ARTIFACTS[0]}"
        with BlobClient.from_blob_url(url, retry_total=0, api_version=API_VERSION) as anonymous:
            with pytest.raises(HttpResponseError) as error:
                anonymous.download_blob().readall()
            assert error.value.status_code in (403, 404)
        assert all((ROOT / name).read_bytes() == data for name, data in before.items())
    finally:
        service.delete_container(name)


@pytest.mark.azurite
def test_live_azurite_corrupt_blob_detected(azurite_service, tmp_path):
    service, _ = azurite_service
    name = "fd001-test-" + uuid.uuid4().hex
    try:
        container = private_container(service, name, create=True)
        originals = upload_artifacts(container, ROOT)
        container.upload_blob(name=ARTIFACTS[0], data=originals[ARTIFACTS[0]] + b"corrupt", overwrite=True)
        downloaded = download_artifacts(container, tmp_path)
        with pytest.raises(ValueError, match="verification failed"):
            verify_bytes(originals[ARTIFACTS[0]], downloaded[ARTIFACTS[0]])
    finally:
        service.delete_container(name)


@pytest.mark.azurite
def test_live_azurite_wrong_credential_fails(azurite_service):
    _, config = azurite_service
    wrong = replace(config, account_key=base64.b64encode(secrets.token_bytes(64)).decode())
    with connect_storage(wrong) as service:
        with pytest.raises(HttpResponseError) as error:
            service.get_account_information()
        assert error.value.status_code == 403


@pytest.mark.azurite
def test_live_azurite_precreated_container_round_trip_without_creation(azurite_service, tmp_path, monkeypatch):
    service, _ = azurite_service
    name = "fd001-test-" + uuid.uuid4().hex
    try:
        service.create_container(name, public_access=None)
        container = service.get_container_client(name)
        monkeypatch.setattr(service, "get_container_client", lambda requested: container)
        def forbidden(*args, **kwargs):
            raise AssertionError("The existing-container path must never request creation")
        monkeypatch.setattr(container, "create_container", forbidden)
        report = round_trip(service, ROOT, tmp_path, name)
        assert report["container_private"]
        assert all(item["bytes_equal"] and item["source_sha256"] == item["download_sha256"] for item in report["artifacts"])
    finally:
        service.delete_container(name)
