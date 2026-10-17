"""Run project-local Azurite with a generated, uncommitted emulator credential."""
import base64
import os
from pathlib import Path
import secrets
import signal
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    executable = ROOT / "node_modules/.bin/azurite-blob"
    if not executable.exists():
        raise SystemExit("Install project-local Azurite first: npm ci")
    cache = ROOT / ".cache"
    cache.mkdir(exist_ok=True)
    account = "fd001dev"
    key = base64.b64encode(secrets.token_bytes(64)).decode("ascii")
    port = int(os.environ.get("AZURITE_BLOB_PORT", "10000"))
    if not 1 <= port <= 65535:
        raise SystemExit("AZURITE_BLOB_PORT must be from 1 to 65535")
    env_file = cache / "azurite.env"
    descriptor = os.open(env_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.chmod(env_file, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write("export AZURE_STORAGE_CONNECTION_STRING='UseDevelopmentStorage=true'\n")
        stream.write("unset AZURE_STORAGE_ACCOUNT_URL\n")
        stream.write(f"export AZURITE_ACCOUNT_NAME='{account}'\n")
        stream.write(f"export AZURITE_ACCOUNT_KEY='{key}'\n")
        stream.write(f"export AZURITE_BLOB_PORT='{port}'\n")
    env = dict(os.environ, AZURITE_ACCOUNTS=f"{account}:{key}")
    command = [str(executable), "--blobHost", "127.0.0.1", "--blobPort", str(port),
               "--location", str(cache / "azurite"), "--silent", "--disableTelemetry"]
    process = subprocess.Popen(command, env=env)
    # Forward termination to the emulator, including automated test cleanup.
    def terminate(signum, frame):
        process.terminate()
    signal.signal(signal.SIGTERM, terminate)
    print("Local credentials written to .cache/azurite.env (mode 0600).", flush=True)
    print("After Azurite reports ready, source this file in a second terminal.", flush=True)
    try:
        return_code = process.wait()
    except KeyboardInterrupt:
        process.terminate()
        return_code = process.wait(timeout=10)
    raise SystemExit(return_code)


if __name__ == "__main__":
    main()
