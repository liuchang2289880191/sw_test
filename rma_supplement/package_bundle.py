"""Package only the standalone supplement; never include old results."""
import hashlib
from pathlib import Path
import zipfile


def main():
    root = Path(__file__).resolve().parent
    files = sorted(p for p in root.rglob("*") if p.is_file()
                   and "__pycache__" not in p.parts
                   and not any(x.startswith("results_") for x in p.relative_to(root).parts)
                   and p.name != "MANIFEST.sha256")
    manifest = root / "MANIFEST.sha256"
    manifest.write_text("".join(hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.relative_to(root).as_posix() + "\n"
                                for p in files), encoding="utf-8")
    out = root.parent / "outputs" / "RMA补充实验_路由与端口_20261007.zip"
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in files + [manifest]:
            z.write(p, "rma_supplement/" + p.relative_to(root).as_posix())
    with zipfile.ZipFile(out) as z:
        if z.testzip(): raise ValueError("Archive CRC failed")
        for p in files:
            if hashlib.sha256(z.read("rma_supplement/" + p.relative_to(root).as_posix())).digest() != hashlib.sha256(p.read_bytes()).digest():
                raise ValueError("Archive contents differ")
    print(f"Packaged {len(files)+1} files; {out.stat().st_size} bytes; CRC and content hashes verified.\n{out}")


if __name__ == "__main__": main()
