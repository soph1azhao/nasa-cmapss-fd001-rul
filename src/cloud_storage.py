"""Environment configuration and an allowlisted Blob Storage byte round trip."""
import base64
from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path
import re

from azure.core.credentials import AzureNamedKeyCredential
from azure.core.exceptions import ResourceExistsError
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

ARTIFACTS = ("results/metrics.json", "results/model_comparison.csv", "figures/prediction_vs_actual.png")
CONTAINER = "fd001-model-results"
# Explicit, supported service version shared by the emulator and real Azure.
API_VERSION = "2023-11-03"


@dataclass(frozen=True)
class StorageConfig:
    mode: str
    account_url: str
    account_name: str = ""
    account_key: str = field(default="", repr=False)

    @classmethod
    def from_environment(cls, environ=None):
        env = os.environ if environ is None else environ
        connection = env.get("AZURE_STORAGE_CONNECTION_STRING", "").strip()
        account_url = env.get("AZURE_STORAGE_ACCOUNT_URL", "").strip()
        if connection and account_url:
            raise ValueError("Choose either local development storage or an Azure account URL, not both")
        if connection:
            if connection.rstrip(";") != "UseDevelopmentStorage=true":
                raise ValueError("Only UseDevelopmentStorage=true is accepted; real Azure uses an Entra account URL")
            account = env.get("AZURITE_ACCOUNT_NAME", "")
            key = env.get("AZURITE_ACCOUNT_KEY", "")
            if not re.fullmatch(r"[a-z0-9]{3,24}", account):
                raise ValueError("Set AZURITE_ACCOUNT_NAME; start the local emulator and source .cache/azurite.env")
            try:
                if len(base64.b64decode(key, validate=True)) < 32:
                    raise ValueError
            except (ValueError, TypeError):
                raise ValueError("Set a valid AZURITE_ACCOUNT_KEY from .cache/azurite.env") from None
            try:
                port = int(env.get("AZURITE_BLOB_PORT", "10000"))
                if not 1 <= port <= 65535:
                    raise ValueError
            except ValueError:
                raise ValueError("AZURITE_BLOB_PORT must be an integer from 1 to 65535") from None
            return cls("azurite", f"http://127.0.0.1:{port}/{account}", account, key)
        if not re.fullmatch(r"https://[a-z0-9]{3,24}\.blob\.core\.windows\.net/?", account_url):
            raise ValueError("Set UseDevelopmentStorage=true, or AZURE_STORAGE_ACCOUNT_URL to an HTTPS Azure Blob account URL without tokens")
        return cls("azure", account_url.rstrip("/"))


@contextmanager
def connect_storage(config):
    credential = (AzureNamedKeyCredential(config.account_name, config.account_key)
                  if config.mode == "azurite" else DefaultAzureCredential())
    try:
        with BlobServiceClient(config.account_url, credential=credential, api_version=API_VERSION,
                               retry_total=0, connection_timeout=5, read_timeout=10) as service:
            yield service
    finally:
        if config.mode == "azure":
            credential.close()


def private_container(service, name=CONTAINER):
    container = service.get_container_client(name)
    try:
        container.create_container(public_access=None)
    except ResourceExistsError:
        pass
    if container.get_container_properties().get("public_access") not in (None, ""):
        raise ValueError("The selected container permits public access; use a private container")
    return container


def upload_artifacts(container, root):
    root = Path(root)
    # Read the complete allowlist before creating any uploads; never discover raw data.
    originals = {}
    for name in ARTIFACTS:
        path = root / name
        if path.is_symlink():
            raise ValueError("Artifact symlinks are not allowed")
        originals[name] = path.read_bytes()
    for name, data in originals.items():
        container.upload_blob(name=name, data=data, overwrite=True)
    return originals


def download_artifacts(container, output):
    output = Path(output)
    downloaded = {}
    for name in ARTIFACTS:
        data = container.download_blob(name).readall()
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        downloaded[name] = destination.read_bytes()
    return downloaded


def verify_bytes(original, downloaded):
    source_hash = hashlib.sha256(original).hexdigest()
    download_hash = hashlib.sha256(downloaded).hexdigest()
    if source_hash != download_hash or original != downloaded:
        raise ValueError("SHA-256 or byte equality verification failed")
    return {"bytes": len(original), "source_sha256": source_hash,
            "download_sha256": download_hash, "bytes_equal": True}


def round_trip(service, root, output, container_name=CONTAINER):
    root, output = Path(root).resolve(), Path(output).resolve()
    # Download destinations must not overwrite any original artifact.
    if any((output / name).resolve() == (root / name).resolve() for name in ARTIFACTS):
        raise ValueError("Download directory must differ from the original artifact location")
    container = private_container(service, container_name)
    originals = upload_artifacts(container, root)
    listed = sorted(blob.name for blob in container.list_blobs())
    if not set(ARTIFACTS).issubset(listed):
        raise ValueError("Uploaded artifacts are missing from blob listing")
    downloaded = download_artifacts(container, output)
    checks = [{"blob": name, **verify_bytes(originals[name], downloaded[name])} for name in ARTIFACTS]
    return {"container": container_name, "container_private": True, "listed_blobs": listed, "artifacts": checks}
