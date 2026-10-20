# Azure Blob Storage extension

**LOCAL EMULATOR VERIFIED — Tested locally using Azurite.**

**ONE CONTROLLED REAL-AZURE ROUND TRIP VERIFIED — October 19, 2026 (Pacific time).**

One controlled real-Azure Blob Storage round trip was verified using Microsoft Entra authentication. Three derived artifacts were uploaded, downloaded, and validated by SHA-256 and exact byte equality. Temporary cloud resources were subsequently deleted.

The [sanitized real-Azure record](../results/azure_storage_verification_real.json) is separate from the [historical Azurite record](../results/azure_storage_verification.json). No cloud model training occurred, no production model was deployed, and no persistent Azure application or storage service remains. Original statistical results are unchanged. Final billing is pending.

## Purpose and boundaries

Object storage provides named, durable objects for sharing analysis outputs independently of a compute environment. Azure Blob Storage stores objects (blobs) inside containers within a storage account. This extension demonstrates a small result-artifact transfer and integrity check. It does not change the FD001 model experiment or demonstrate cloud training.

Microsoft's official Azurite emulator implements a local subset of the Azure Storage APIs. The same Python `BlobServiceClient` performs the local create, upload, list, and download requests. The one-time Azure check below independently exercised Entra authentication, private-container access, and transfer integrity; it did not measure durability, availability, or production reliability.

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

In local Azurite mode, the script creates **`fd001-model-results`** with no public access, or verifies an existing container is private before uploading. In real Azure mode, the container must already exist: the script only reads its properties, verifies privacy, and fails clearly if it is absent or inaccessible. It never requests real-Azure container creation. It lists the blobs, downloads the three selected artifacts, compares their SHA-256 digests **and actual bytes**, and records non-secret verification data at the mode-specific destination. It does not change the original metrics, figures, or notebook. Local reports retain `results/azure_storage_verification.json`; successful real-Azure reports go separately to gitignored `.cache/azure_storage_verification_real.json`, pending review. A failed round trip writes no success report. Reports contain artifact hashes and verification metadata, not account URLs, tenant/subscription identifiers, keys, or tokens.

Stop Azurite using Ctrl+C in Terminal 1. Downloads, emulator state, npm packages, and generated credentials remain local and gitignored. Do not commit or share `.cache/azurite.env`.

## Tests and measured evidence

Historical original-extension verification: **16 existing tests passed** before the extension, and **34 tests passed: 16 existing + 18 new** afterward, including **three actual Azurite integration tests**. None were skipped in that verification run.

October 19 readiness preparation ran **29 focused storage tests**, including **four actual Azurite tests**, with no failures or skips. The additional local-server check pre-creates a container, then verifies a full hash/byte-matched round trip while forbidding creation calls in the workflow. Unit checks also cover absent/inaccessible containers and separate report destinations. The NASA experiment was not rerun. At that readiness stage, acquiring a Storage-scoped token alone did not establish Blob data permissions; the later controlled cloud round trip supplied that separate evidence.

New unit checks cover configuration, secret redaction, artifact allowlisting, symlink rejection, hash mismatch, original-path protection, and Entra client construction. The Entra construction check uses test doubles and does **not** establish real Azure authentication.

The **four** live Azurite integration tests verify:

1. Private-container creation, real uploads/listing/downloads, all hashes and bytes matching, repeatable overwrite behavior, unchanged local originals, and rejection of an anonymous Blob request.
2. A deliberately corrupted uploaded blob is downloaded and fails hash/byte verification.
3. An incorrect local credential is rejected by the emulator with HTTP 403.
4. A pre-created private container supports a complete round trip while creation calls are forbidden in the workflow.

Without `FD001_AZURITE_TESTS=1`, the four integration tests explicitly skip. With it enabled, unavailable Azurite or incorrect configuration causes failure, not a mocked success. These tests assert local-emulator mode and cannot target a real Azure account.

The historical Azurite CLI round trip transferred **three blobs**: 912-byte metrics JSON, 242-byte comparison CSV, and 71,792-byte prediction plot. All three SHA-256 pairs match. See [storage verification](../results/azure_storage_verification.json) and [extension QA](../results/azure_storage_qa.json).

Original model code, methodology, notebook outputs, metrics, figures, and research artifacts remain byte-for-byte unchanged. Storage code and storage tests were extended separately. Existing test MAE **19.64**, RMSE **27.08**, and mean signed error **+11.48 cycles** are preserved. Existing tests exercise synthetic model fixtures; the completed FD001 experiment was not retrained or retuned.

## Controlled real-Azure verification

On **October 19, 2026 (America/Vancouver)**, one controlled transfer used **North Central US**, **StorageV2 / Standard_LRS / Hot**, and the private **`fd001-model-results`** container. HTTPS-only access, minimum TLS 1.2, disabled Shared Key authorization, and disabled anonymous Blob access were verified. The client used **Microsoft Entra / `DefaultAzureCredential`** with a temporary **Storage Blob Data Contributor role scoped only to the container**. Subscription Owner alone is not evidence of Blob data access.

The account and private container were pre-created through Azure Resource Manager. The transfer client accessed the existing container without requesting creation or broadening permissions. Local Azurite settings were cleared for this run.

Measured results:

- **3 uploads and 3 downloads**, totaling **72,946 bytes** across the fixed allowlist.
- **3/3 SHA-256 pairs matched; 3/3 exact byte comparisons matched.** The public record includes each artifact's size and both hashes.
- An unauthenticated GET with supported service API **2023-11-03** was rejected with **HTTP 401 / `NoAuthenticationInformation`**.
- **45 local tests passed**, including **four live Azurite tests**, with no failures or skips. These local tests did not contact real Azure or rerun the NASA experiment; model tests use synthetic fixtures.
- After local evidence was saved, the temporary container-scoped role was removed and the dedicated resource group/account/container were deleted. Azure Resource Manager confirmed the group was absent and **zero subscription resources remained**. Only `Microsoft.Storage` was registered and was left registered; no subscription policy was changed.

The public [verification record](../results/azure_storage_verification_real.json) was selected from the retained local JSON. Raw local verification JSON and pytest XML remain gitignored; they are not published. This publication's QA reruns the local suite only, without repeating the cloud transfer or creating resources.

### Cost and interpretation

At verification, North Central US Hot LRS rates were **US$0.0208/GB-month**, **US$0.05/10,000 write or list/create operations**, and **US$0.004/10,000 read or other operations**, queried through the [Azure Retail Prices API](https://prices.azure.com/api/retail/prices). Estimated test usage was **below US$0.001 before free allowances**, within an approved **US$0.01 estimated allowance**. This was not an enforced spending cap. **Actual final billing remains pending** and may be delayed; the estimate is not a measured bill. Dedicated test resources were deleted, so no ongoing test-resource exposure remains.

The test establishes one successful authenticated storage round trip and cleanup. It does not establish cloud model training, production deployment, sustained service operation, reliability improvements, or maintenance benefits. OpenAI Codex assisted with code, verification orchestration, and documentation; the executed evidence and Git history are retained.

### Future authorized use

Any future cloud use requires separate resource, identity, policy, region, and cost checks. During initial readiness, Canada Central appeared in the Storage catalogue but was excluded by subscription policy; the approved test used North Central US. The transfer script does not provision resource groups, accounts, containers in Azure mode, or roles. An administrator must pre-create the private container and grant the required container-scoped data role. Missing/inaccessible or public containers fail before upload.

For a separately authorized run against an existing account:

```bash
unset AZURE_STORAGE_CONNECTION_STRING AZURITE_ACCOUNT_NAME AZURITE_ACCOUNT_KEY
export AZURE_STORAGE_ACCOUNT_URL='https://<account-name>.blob.core.windows.net'
az login
python scripts/upload_results_azure.py
```

Replace the placeholder with the intended account. `DefaultAzureCredential` can use an Azure CLI login during development or a managed identity in an Azure-hosted environment; only the CLI-backed development scenario was exercised here. No access key is requested or stored in source. Azure CLI is not required for local Azurite tests. The client accepts public-Azure account URLs; sovereign-cloud/custom endpoints would require an explicit extension. Successful Azure reports go to `.cache/azure_storage_verification_real.json`, preserving the committed Azurite evidence; review and sanitize them before publication. Future operations may incur charges and are not authorized by reproducing the local tests.

## Emulation limits and references

Azurite does not establish production durability, availability, real Entra/RBAC enforcement, cloud network policies, scale, or cost. Loopback HTTP and a custom shared local key are development settings. The client pins service API **2023-11-03** for compatibility, and API-version checks remain enabled; no `--skipApiVersionCheck` workaround is used. Only Blob Storage is started, not Queue or Table services.

- [Microsoft: Install and run Azurite](https://learn.microsoft.com/en-us/azure/storage/common/storage-install-azurite)
- [Official Azurite project: custom storage accounts and keys](https://github.com/Azure/Azurite#customized-storage-accounts--keys)
- [Microsoft: Azure Storage Blobs Python SDK](https://learn.microsoft.com/en-us/python/api/overview/azure/storage-blob-readme?view=azure-python)
- [Microsoft: Authorize Blob data access with Microsoft Entra ID](https://learn.microsoft.com/en-us/azure/storage/blobs/authorize-access-azure-active-directory)
