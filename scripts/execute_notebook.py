"""Execute with the current Python interpreter without a global kernel install."""
import json
from pathlib import Path
import sys
import tempfile
import nbformat
from nbclient import NotebookClient
from jupyter_client import KernelManager
from jupyter_client.kernelspec import KernelSpecManager

ROOT = Path(__file__).resolve().parents[1]

def main():
    path = ROOT / "notebooks/01_fd001_analysis.ipynb"
    notebook = nbformat.read(path, as_version=4)
    with tempfile.TemporaryDirectory(prefix="fd001-kernel-") as folder:
        spec = Path(folder) / "fd001"
        spec.mkdir()
        (spec / "kernel.json").write_text(json.dumps({
            "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
            "display_name": "FD001", "language": "python"}))
        manager = KernelManager(kernel_name="fd001", kernel_spec_manager=KernelSpecManager(kernel_dirs=[folder]))
        client = NotebookClient(notebook, km=manager, timeout=600, resources={"metadata": {"path": str(ROOT)}})
        try:
            client.execute()
        finally:
            if manager.has_kernel:
                manager.shutdown_kernel(now=True)
        nbformat.write(notebook, path)
    count = sum(cell.cell_type == "code" and cell.execution_count is not None for cell in notebook.cells)
    print(f"Executed {count} code cells: {path.name}")

if __name__ == "__main__":
    main()
