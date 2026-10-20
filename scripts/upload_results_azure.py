"""Upload only three derived artifacts, download them, and record verification."""
from importlib.metadata import version
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from azure.core.exceptions import AzureError
from src.cloud_storage import StorageConfig, connect_storage, round_trip, API_VERSION


def verification_report_path(mode):
    # Keep local-emulator evidence intact and cloud evidence private until reviewed.
    destinations = {
        "azurite": ROOT / "results/azure_storage_verification.json",
        "azure": ROOT / ".cache/azure_storage_verification_real.json",
    }
    if mode not in destinations:
        raise ValueError("Unknown storage verification mode")
    return destinations[mode]


def main():
    try:
        config = StorageConfig.from_environment()
        with connect_storage(config) as service:
            report = round_trip(service, ROOT, ROOT / ".cache/azure-downloads",
                                create_container=config.mode == "azurite")
        report.update({"verification_scope": "LOCAL EMULATOR VERIFIED" if config.mode == "azurite" else "REAL AZURE STORAGE ROUND TRIP VERIFIED",
                       "real_azure_used": config.mode == "azure", "service_api_version": API_VERSION,
                       "azure_storage_blob_version": version("azure-storage-blob"),
                       "azure_identity_version": version("azure-identity")})
        if config.mode == "azurite":
            report["azurite_version"] = json.loads((ROOT / "node_modules/azurite/package.json").read_text())["version"]
        destination = verification_report_path(config.mode)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        return 0
    except ValueError as error:
        print(f"Storage configuration or verification error: {error}", file=sys.stderr)
    except (AzureError, OSError) as error:
        # SDK error text may contain URLs or request details; avoid printing credentials.
        print(f"Storage round trip failed ({type(error).__name__}). Check configuration, emulator readiness, and access permissions.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
