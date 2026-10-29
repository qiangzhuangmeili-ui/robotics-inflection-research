"""Round2 复审临时脚本：只读生产文件，只写入 reasonix/round2/。"""
import hashlib
import json
import os
import shutil
import subprocess
import sys

ROOT = r"C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\robotics-inflection-research"
PY = r"C:\Users\zhangjianmei\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
R2 = os.path.join(ROOT, r"runs/issues/S02/recheck_20261029/reasonix/round2")
GZ = os.path.join(ROOT, r"runs/issues/S02/remediation_20261029/s00/financial_normalized.csv.gz")
RULES = os.path.join(ROOT, r"runs/issues/S02/remediation_20261029/rules_recalculation_inputs.json")
CANON = os.path.join(ROOT, r"runs/issues/S02/remediation_20261029/s02")
CANON_SHA = {
    "all_pool_metrics.csv": "69f82db2896c746ee9e732354708f2d106d32ca115ccada9ee985ba322958425",
    "company_metric_summary.csv": "1dcd40932ec68c4c5d225c56e168906930a1a3b5beda43f3017d33470863bf95",
}
TOOLS = [
    "tools/s02_calculate.py",
    "tools/s03_input_gate.py",
    "tools/s01_rules_check.py",
    "tools/l0_classify.py",
    "tools/a03_financial_field_extractor.py",
]


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_blob(path):
    return subprocess.run(["git", "-C", ROOT, "cat-file", "blob", "d72d4d5:" + path],
                          capture_output=True, check=True).stdout


out = {}
os.makedirs(R2, exist_ok=True)

# --- 1. 源文件：工作区 vs 提交 blob ---
src = {}
for t in TOOLS:
    wb = open(os.path.join(ROOT, t), "rb").read()
    gb = git_blob(t)
    src[t] = {
        "working_sha256": sha_bytes(wb),
        "git_blob_sha256": sha_bytes(gb),
        "exact_bytes": wb == gb,
        "lf_only_equivalent": wb.replace(b"\r\n", b"\n") == gb.replace(b"\r\n", b"\n"),
    }
out["sources"] = src

# --- 2. 解压 gz 到 round2 自己的输入副本 ---
inp_dir = os.path.join(R2, "recalc_input")
os.makedirs(inp_dir, exist_ok=True)
csv_copy = os.path.join(inp_dir, "financial_normalized.csv")
with open(csv_copy, "wb") as fo, open(GZ, "rb") as fi:
    fo.write(__import__("gzip").decompress(fi.read()))
out["inputs"] = {
    "gz_path": os.path.relpath(GZ, ROOT),
    "gz_sha256": sha_file(GZ),
    "payload_path": os.path.relpath(csv_copy, ROOT),
    "payload_sha256": sha_file(csv_copy),
    "payload_bytes": os.path.getsize(csv_copy),
}

# --- 3. 两次重算 ---
def run(mode, normalized, outdir):
    outdir = os.path.join(R2, outdir)
    if os.path.isdir(outdir):
        shutil.rmtree(outdir)
    os.makedirs(outdir, exist_ok=True)
    cmd = [PY, os.path.join(ROOT, "tools/s02_calculate.py"),
           "--normalized", normalized, "--rules", RULES, "--out-dir", outdir]
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    rec = {
        "mode": mode,
        "argv_script": "tools/s02_calculate.py",
        "out_dir": os.path.relpath(outdir, ROOT),
        "returncode": p.returncode,
        "stdout_tail": p.stdout[-3000:],
        "stderr_tail": p.stderr[-3000:],
        "outputs": {},
    }
    for name, want in CANON_SHA.items():
        fp = os.path.join(outdir, name)
        if os.path.isfile(fp):
            got = sha_file(fp)
            rec["outputs"][name] = {"sha256": got, "expected": want, "byte_equal": got == want}
        else:
            rec["outputs"][name] = {"sha256": None, "expected": want, "byte_equal": False}
    mp = os.path.join(outdir, "calculation_manifest.json")
    if os.path.isfile(mp):
        rec["manifest_sha256"] = sha_file(mp)
        m = json.load(open(mp, encoding="utf-8"))
        rec["manifest_keys"] = sorted(m.keys())
        rec["manifest_execution_sources"] = m.get("execution_sources")
        rec["manifest_inputs"] = m.get("inputs")
        rec["manifest_l0"] = {
            k: m.get(k) for k in ("input_version", "l0_addendum_sha256", "base_metric_rules_sha256", "l0_distribution")
        }
    return rec


out["runs"] = [
    run("csv_copy", csv_copy, "recalc_copy"),
    run("gzip_direct", GZ, "recalc_gzip"),
]

# --- 4. canonical 产物未被追改 ---
out["canonical_unchanged"] = {
    n: {"sha256": sha_file(os.path.join(CANON, n)), "expected": w}
    for n, w in CANON_SHA.items()
}

# --- 5. P06 / L0 / 确认类型相关源码摘录（只读） ---
s02 = open(os.path.join(ROOT, "tools/s02_calculate.py"), encoding="utf-8").read().splitlines()
keys = ("P06", "l0_required", "required", "load_l0_addendum", "low_base_confirmed", "execution_sources", "materialize")
hits = []
for i, line in enumerate(s02, 1):
    if any(k in line for k in keys):
        hits.append("%4d| %s" % (i, line))
out["source_hits_s02"] = hits

json.dump(out, open(os.path.join(R2, "recalc_round2.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(json.dumps({k: out[k] for k in ("inputs", "canonical_unchanged")}, ensure_ascii=False, indent=1))
for k, v in out["sources"].items():
    print(k, v)
for r in out["runs"]:
    print("=== RUN", r["mode"], "rc=", r["returncode"])
    print(" outputs:", json.dumps(r["outputs"], ensure_ascii=False))
    print(" manifest_sha256:", r.get("manifest_sha256"))
    print(" exec_sources:", json.dumps(r.get("manifest_execution_sources"), ensure_ascii=False))
    print(" l0:", json.dumps(r.get("manifest_l0"), ensure_ascii=False))
    print(" stdout_tail:", r["stdout_tail"][-1200:])
    print(" stderr_tail:", r["stderr_tail"][-500:])
print("=== SOURCE HITS")
print("\n".join(hits))
