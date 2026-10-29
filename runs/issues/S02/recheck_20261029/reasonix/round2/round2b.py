"""Round2 复审临时脚本 B：新manifest字段、P06/L0源码、Q05 helper、少量内联负面测试。只写 round2/。"""
import glob
import importlib.util
import inspect
import json
import os
import re
import subprocess
import sys

ROOT = r"C:\Users\zhangjianmei\Documents\ChatGPT\机器人企业行业拐点研究\robotics-inflection-research"
PY = r"C:\Users\zhangjianmei\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
R2 = os.path.join(ROOT, r"runs/issues/S02/recheck_20261029/reasonix/round2")
out = {}

# A. 我这两次运行生成的新 manifest：inputs / checks
man = {}
for mode in ("recalc_copy", "recalc_gzip"):
    p = os.path.join(R2, mode, "calculation_manifest.json")
    m = json.load(open(p, encoding="utf-8"))
    man[mode] = {
        "keys": sorted(m.keys()),
        "inputs": m.get("inputs"),
        "counts": m.get("counts"),
        "l0_distribution": m.get("l0_distribution"),
        "outputs": m.get("outputs"),
        "execution_sources": m.get("execution_sources"),
        "checks_P05_P06": [c for c in m.get("checks", []) if c.get("id") in ("P05", "P06")],
        "known_limits": m.get("known_limits"),
    }
    if not man[mode]["checks_P05_P06"]:
        man[mode]["checks_keys_sample"] = list(m.keys())
out["my_manifests"] = man

# A2. 作者提交的 execution manifest（reproduction/csv_copy, gzip）
auth = {}
for p in glob.glob(os.path.join(ROOT, r"runs/issues/S02/recheck_20261029/reproduction/*/calculation_manifest.json")):
    m = json.load(open(p, encoding="utf-8"))
    auth[os.path.relpath(p, ROOT)] = {"inputs": m.get("inputs"), "outputs": m.get("outputs"),
                                     "l0_distribution": m.get("l0_distribution")}
out["author_manifests"] = auth

# B. 源码关键段落
lines = open(os.path.join(ROOT, "tools/s02_calculate.py"), encoding="utf-8").read().splitlines()
out["src_200_275"] = ["%4d| %s" % (i, lines[i - 1]) for i in range(200, min(276, len(lines) + 1))]
out["src_430_510"] = ["%4d| %s" % (i, lines[i - 1]) for i in range(430, min(511, len(lines) + 1))]

# C. 找 low_base_confirmed 所在文件并测试
found = []
for p in glob.glob(os.path.join(ROOT, "tools/*.py")) + glob.glob(os.path.join(ROOT, "tools/**/*.py"), recursive=True):
    t = open(p, encoding="utf-8", errors="replace").read()
    if "low_base_confirmed" in t:
        found.append((os.path.relpath(p, ROOT), [l for l in t.splitlines() if "low_base_confirmed" in l]))
out["low_base_confirmed_files"] = found

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

# D. 负面测试 1：篡改 payload
base_in = os.path.join(R2, "recalc_input", "financial_normalized.csv")
tamper_dir = os.path.join(R2, "neg_tamper")
os.makedirs(tamper_dir, exist_ok=True)
data = bytearray(open(base_in, "rb").read())
# 改动一个数字字节（保持 UTF-8 合法）
idx = data.find(b"1054")
for j in range(len(data) - 10):
    if 0x30 <= data[j] <= 0x39 and data[j:j + 3] == b"105":
        data[j + 2] = ord("9")
        break
tamper_csv = os.path.join(tamper_dir, "financial_normalized_tampered.csv")
open(tamper_csv, "wb").write(bytes(data))
outdir = os.path.join(tamper_dir, "out")
os.makedirs(outdir, exist_ok=True)
p = subprocess.run([PY, os.path.join(ROOT, "tools/s02_calculate.py"),
                    "--normalized", tamper_csv,
                    "--rules", os.path.join(ROOT, r"runs/issues/S02/remediation_20261029/rules_recalculation_inputs.json"),
                    "--out-dir", outdir], capture_output=True, text=True, cwd=ROOT, encoding="utf-8", errors="replace")
out["neg_tamper"] = {
    "returncode": p.returncode,
    "stdout_tail": p.stdout[-2000:],
    "outputs_written": sorted(os.listdir(outdir)),
    "all_pool_metrics_exists": os.path.isfile(os.path.join(outdir, "all_pool_metrics.csv")),
}

# E. 找 v1/历史基线 rules 文件（input_version != v2）
cands = []
for p in glob.glob(os.path.join(ROOT, "runs/**/rules*.json"), recursive=True) + glob.glob(os.path.join(ROOT, "runs/**/*rules*.json"), recursive=True):
    try:
        m = json.load(open(p, encoding="utf-8"))
    except Exception:
        continue
    if isinstance(m, dict) and ("input_version" in m or "l0_addendum" in m or "metric_rules" in m):
        cands.append({"path": os.path.relpath(p, ROOT), "input_version": m.get("input_version"),
                      "has_l0": "l0_addendum" in m or "l0_addendum_path" in m})
seen = set()
uniq = []
for c in cands:
    if c["path"] in seen:
        continue
    seen.add(c["path"])
    uniq.append(c)
out["rules_candidates"] = uniq

json.dump(out, open(os.path.join(R2, "round2b.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print("=== MY MANIFESTS ===")
print(json.dumps(man, ensure_ascii=False, indent=1)[:6000])
print("=== AUTHOR MANIFESTS ===")
print(json.dumps(auth, ensure_ascii=False, indent=1)[:2500])
print("=== SRC 200-275 ===")
print("\n".join(out["src_200_275"]))
print("=== SRC 430-510 ===")
print("\n".join(out["src_430_510"]))
print("=== LOW_BASE_CONFIRMED FILES ===")
print(json.dumps(found, ensure_ascii=False, indent=1)[:3000])
print("=== NEG TAMPER ===")
print(json.dumps(out["neg_tamper"], ensure_ascii=False, indent=1))
print("=== RULES CANDIDATES ===")
print(json.dumps(uniq, ensure_ascii=False, indent=1)[:3000])
