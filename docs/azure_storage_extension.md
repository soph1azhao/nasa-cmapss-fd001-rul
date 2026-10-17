# Azure Blob Storage extension

**LOCAL EMULATOR VERIFIED — Tested locally using Azurite.**

**REAL AZURE NOT VERIFIED.** No Azure subscription, paid resource, cloud training, or cloud deployment was used. Azure for Students verification remains blocked.

## Purpose and boundaries

Object storage provides named, durable objects for sharing analysis outputs independently of a compute environment. Azure Blob Storage stores objects (blobs) inside containers within a storage account. This extension demonstrates a small result-artifact transfer and integrity check. It does not change the FD001 model experiment or demonstrate cloud training.

Microsoft's official Azurite emulator implements a local subset of the Azure Storage APIs. The same Python `BlobServiceClient` performs the local create, upload, list, and download requests. Real Azure authentication, networking, service behavior, and durability still require independent verification.

The fixed upload allowlist is:

- `results/metrics.json`
- `results/model_comparison.csv`
- `figures/prediction_vs_actual.png`

No raw NASA data, model-training inputs, notebooks, environment files, or credentials are uploaded. Blob names preserve the repository-relative paths. Repeated runs overwrite only these three blob names. Downloads go under gitignored `.cache/azure-downloads/`; original artifacts are never used as download destinations.

## Local tooling and authentication

Detected on the development machine: Node.js 26.7.0, npm 11.19.0, and Docker CLI 29.7.2. No VS Code Azurite extension was found. Docker daemon access was restricted during inspection; Docker was not used. The least disruptive choice was project-local npm tooling: **Azurite 3.37.0**, pinned in `package.json` and `package-lock.json`, with no global installation. Python SDKs: **azure-storage-blob 12.31.0** and **azure-identity 1.26.0**.

The launcher binds the Blob service to **127.0.0.1:10000**, disables emulator telemetry, and generates a fresh random local account key at each launch. It passes that key to Azurite through its supported `AZURITE_ACCOUNTS` environment setting and writes matching shell configuration to **`.cache/azurite.env` with mode 0600**. The key is not printed, hardcoded, or committed. Emulator state also stays under `.cache/`.

Local configuration uses:

```text
AZURE_STORAGE_CONNECTION_STRING=UseDevelopmentStorage=true
AZURITE_ACCOUNT_NAME=<generated local account name>
AZURITE_ACCOUNT_KEY=<generated locally; never commit>
AZURITE_BLOB_PORT=10000
```

The project resolves `UseDevelopmentStorage=true` to its custom loopback account using these environment variables and authenticates with `AzureNamedKeyCredential`. The generated key is an **emulator-only credential**, not an Azure access key. This custom-account setup avoids embedding even the public default emulator key in project source. Source the newly generated file after each emulator restart. Local configuration cannot direct this credential to a remote hostname.

The real Azure option instead uses `AZURE_STORAGE_ACCOUNT_URL` and `DefaultAzureCredential`. Supplying both modes, a malformed local key/port, an HTTP cloud URL, or a URL containing a token fails clearly. Full access-key connection strings are intentionally not supported.

## Reproduce the local experiment

From the repository root, activate the existing Python environment (or create one and install `requirements.txt`). Run only the storage workflow; rerunning model analysis is unnecessary.

Terminal 1:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
npm ci
npm run azurite
```

Wait for Azurite to report that it is listening. Leave that terminal running. If port 10000 is occupied, choose an unused port with `AZURITE_BLOB_PORT=10010 npm run azurite`; the generated environment file records it.

Terminal 2:

```bash
source .venv/bin/activate
source .cache/azurite.env
python scripts/upload_results_azure.py
FD001_AZURITE_TESTS=1 python -m pytest -q
```

The script creates **`fd001-model-results`** with no public access, or verifies an existing container is private before uploading. It lists the blobs, downloads the three selected artifacts, compares their SHA-256 digests **and actual bytes**, and records only non-secret verification data in [azure_storage_verification.json](../results/azure_storage_verification.json). It does not change the original metrics, figures, or notebook.

Stop Azurite using Ctrl+C in Terminal 1. Downloads, emulator state, npm packages, and generated credentials remain local and gitignored. Do not commit or share `.cache/azurite.env`.

## Tests and measured evidence

Before extension work, **16 existing tests passed**. After implementation, **34 tests passed: 16 existing + 18 new**, including **three actual Azurite integration tests**. All tests ran locally with the emulator enabled; none were skipped in that verification run.

New unit checks cover configuration, secret redaction, artifact allowlisting, symlink rejection, hash mismatch, original-path protection, and Entra client construction. The Entra construction check uses test doubles and does **not** establish real Azure authentication.

The three live integration tests verify:

1. Private-container creation, real uploads/listing/downloads, all hashes and bytes matching, repeatable overwrite behavior, unchanged local originals, and rejection of an anonymous Blob request.
2. A deliberately corrupted uploaded blob is downloaded and fails hash/byte verification.
3. An incorrect local credential is rejected by the emulator with HTTP 403.

Without `FD001_AZURITE_TESTS=1`, the three integration tests explicitly skip. With it enabled, unavailable Azurite or incorrect configuration causes failure, not a mocked success. These tests assert local-emulator mode and cannot target a real Azure account.

The CLI's separate verified round trip transferred **three blobs**: 912-byte metrics JSON, 242-byte comparison CSV, and 71,792-byte prediction plot. All three SHA-256 pairs match. See [storage verification](../results/azure_storage_verification.json) and [extension QA](../results/azure_storage_qa.json).

All original source, experiments, tests, notebook, metrics, and figures remain byte-for-byte unchanged from the pre-extension snapshot. Existing test MAE **19.64**, RMSE **27.08**, and mean signed error **+11.48 cycles** are preserved. Existing tests exercise synthetic model fixtures; the completed FD001 experiment was not retrained or retuned.

## Future real Azure option — not tested

Once subscription access is available, the user needs an Azure Storage account, an approved cost/budget plan, and a Microsoft Entra identity authorized for blob data access. An administrator can grant **Storage Blob Data Contributor** at the appropriate account scope so the workflow can create its private container and read/write blobs. Network and account policies must permit that access. Azure for Students verification must be resolved if that is the subscription route the user chooses.

For a future authorized run against an existing account:

```bash
unset AZURE_STORAGE_CONNECTION_STRING AZURITE_ACCOUNT_NAME AZURITE_ACCOUNT_KEY
export AZURE_STORAGE_ACCOUNT_URL='https://<account-name>.blob.core.windows.net'
az login
python scripts/upload_results_azure.py
```

Replace the account placeholder with the intended account. `DefaultAzureCredential` can use an Azure CLI login during development or a managed identity in an Azure-hosted environment. No access key needs to be requested or stored in source. Azure CLI is needed only if using that login method; it is not needed for local Azurite tests. This project currently accepts public-Azure account URLs; sovereign-cloud/custom endpoints would need an explicit extension.

This command was **not executed against real Azure**. It would create a container if necessary and upload only the allowlisted artifacts to the configured account. The code does not provision subscriptions, resource groups, or storage accounts. Future real-Azure operations may incur charges and need separate authorization; local success establishes neither Entra/RBAC correctness nor cloud deployment.

## Emulation limits and references

Azurite does not establish production durability, availability, real Entra/RBAC enforcement, cloud network policies, scale, or cost. Loopback HTTP and a custom shared local key are development settings. The client pins service API **2023-11-03** for compatibility, and API-version checks remain enabled; no `--skipApiVersionCheck` workaround is used. Only Blob Storage is started, not Queue or Table services.

- [Microsoft: Install and run Azurite](https://learn.microsoft.com/en-us/azure/storage/common/storage-install-azurite)
- [Official Azurite project: custom storage accounts and keys](https://github.com/Azure/Azurite#customized-storage-accounts--keys)
- [Microsoft: Azure Storage Blobs Python SDK](https://learn.microsoft.com/en-us/python/api/overview/azure/storage-blob-readme?view=azure-python)
- [Microsoft: Authorize Blob data access with Microsoft Entra ID](https://learn.microsoft.com/en-us/azure/storage/blobs/authorize-access-azure-active-directory)
