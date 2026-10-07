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
    repair = out.parent / "RMA补充实验_卡住定位补丁_20261007.zip"
    replacements = [root / name for name in ("topology_common.h", "topology_host.c",
                    "topology_slave.c", "run_supplement.sh", "README.md", "DESIGN.md", "LOCAL_VERIFICATION.json",
                    "verify_local.py", "package_bundle.py", "MANIFEST.sha256")]
    with zipfile.ZipFile(repair, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in replacements:
            z.write(p, "rma_supplement/" + p.name)
        z.writestr("FIX_NOTE.txt", "把补丁内 rma_supplement/ 中所有文件覆盖到服务器的同名目录。\n"
                   "必须同时更新 topology_common.h、topology_host.c、topology_slave.c、run_supplement.sh；主从核结构体已改变。\n"
                   "改动：独立 ready 回答字、按完成回答字识别 stop、元数据可见性、带上限等待、阶段日志、主核单项 60 秒超时。\n"
                   "此前 diag_05 卡住的具体阶段仍需真实服务器的新日志确认；本地模拟通过不代表真实硬件已验证。\n"
                   "先在另一个登录终端停止原来的挂起作业：bkill 8452694\n"
                   "随后在登录节点运行：TOPO_DIAG_ONLY=1 TOPO_TRACE=1 bash run_supplement.sh q_share\n"
                   "如仍失败，保留 repeat_01/job.log 中 TOPO_STAGE、TOPO_TIMEOUT、TOPO_CASE_TIMEOUT 与主核失败计数。\n"
                   "不修改旧实验或失败运行的结果目录，新执行会创建新结果目录。\n")
    with zipfile.ZipFile(repair) as z:
        if z.testzip(): raise ValueError("Repair archive CRC failed")
        for p in replacements:
            if z.read("rma_supplement/" + p.name) != p.read_bytes(): raise ValueError("Repair archive differs")
    print(f"Repair: {repair.stat().st_size} bytes; CRC/content verified.\n{repair}")


if __name__ == "__main__": main()
