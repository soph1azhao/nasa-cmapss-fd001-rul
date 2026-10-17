"""Download only official NASA data; extract FD001 without distributing raw data."""
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
URL = "https://phm-datasets.s3.amazonaws.com/NASA/6.+Turbofan+Engine+Degradation+Simulation+Data+Set.zip"
REQUIRED = ("train_FD001.txt", "test_FD001.txt", "RUL_FD001.txt")


def extract_fd001(blob, destination):
    found = {}
    def visit(data):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for name in archive.namelist():
                base = Path(name).name
                if base in REQUIRED:
                    if base in found:
                        raise ValueError("Duplicate FD001 member: " + base)
                    found[base] = archive.read(name)
                elif name.lower().endswith(".zip"):
                    visit(archive.read(name))
    visit(blob)
    if set(found) != set(REQUIRED):
        raise ValueError("Official archive is missing FD001 files")
    destination.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name, data in found.items():
        (destination / name).write_bytes(data)
        hashes[name] = hashlib.sha256(data).hexdigest()
    return hashes


def main():
    with urllib.request.urlopen(URL, timeout=120) as response:
        blob = response.read()
    hashes = extract_fd001(blob, ROOT / "data/raw")
    provenance = {"source_url": URL, "archive_sha256": hashlib.sha256(blob).hexdigest(), "files_sha256": hashes}
    (ROOT / "results/data_provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    main()
