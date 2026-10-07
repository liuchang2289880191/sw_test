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
    repair = out.parent / "RMA补充实验_修复补丁_20261007.zip"
    replacements = [root / "run_supplement.sh", root / "topology_slave.c"]
    with zipfile.ZipFile(repair, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in replacements:
            z.write(p, "rma_supplement/" + p.name)
        z.writestr("FIX_NOTE.txt", "覆盖服务器 rma_supplement/ 中的 run_supplement.sh 和 topology_slave.c。\n"
                   "修复：登录节点不执行目标二进制；volatile 回答字逐项清零。\n"
                   "随后在登录节点运行：TOPO_DIAG_ONLY=1 bash run_supplement.sh q_share\n"
                   "不修改旧实验或失败运行的结果目录，新执行会创建新结果目录。\n")
    with zipfile.ZipFile(repair) as z:
        if z.testzip(): raise ValueError("Repair archive CRC failed")
        for p in replacements:
            if z.read("rma_supplement/" + p.name) != p.read_bytes(): raise ValueError("Repair archive differs")
    print(f"Repair: {repair.stat().st_size} bytes; CRC/content verified.\n{repair}")


if __name__ == "__main__": main()
