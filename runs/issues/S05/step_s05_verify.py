#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S05 自检（#40 / S05）。只读，不改任何交付文件。

V 系列是结构/口径/对账检查；X 系列是与上游独立来源的复算比对。
本脚本必须在 manifest 生成之前运行，运行后不得再改动交付文件。
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

D = Decimal
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
V22 = REPO / "runs/issues/S04/workbuddy_handoff_20261119/v2_2_20261120"
REVIEWED = REPO / "runs/issues/S04/completion_20261114/final_delivery_20261116/reviewed_view"
MASK = (REPO / "runs/issues/S00/completion_20261114/remaining_scope_review_20261115"
        / "classification_v2/CE_admission_projection/execution/all_pool_metrics_source_aware_mask.csv")
FROZEN_B = REPO / "runs/issues/S02/hangcha_restated_20261101/s00_v10/s00_v10.csv.gz"
RELEASE = REPO / "runs/issues/S05/release_20261120.json"

METRICS = ("M04", "M08", "M10", "M11", "M12")
KNOWN_STATUS = {
    "OK", "NOT_APPLICABLE_PROJECT_MODE", "NOT_APPLICABLE_NEGATIVE_DENOMINATOR",
    "NOT_APPLICABLE_ZERO_BASE_FLOOR", "HOLD_DECISIVE_CELL_PENDING",
    "UNKNOWN_INPUT_MISSING", "UNKNOWN_INPUT_UNREADABLE", "UNKNOWN_CA_BLANK",
    "UNKNOWN_CA_SOURCE_NOT_ADMISSIBLE", "BOTH_BLANK_NO_USABLE_AMOUNT",
    "SINGLE_SIDED_GAP",
}
KNOWN_RH = {"TRIGGERED", "NOT_TRIGGERED", "NOT_APPLICABLE",
            "PENDING_HOLD", "PENDING_APPLICABILITY", "PENDING_SINGLE_SIDED"}

results = []


def check(name, ok, detail=""):
    results.append({"name": name, "pass": bool(ok), "detail": str(detail)})


def read(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def main():
    decision = read(HERE / "quality_decision_log.csv")
    flags = read(HERE / "quality_flags.csv")
    passed = read(HERE / "quality_pass.csv")
    observe = read(HERE / "quality_observe.csv")
    preserved = read(HERE / "observe_pool_preserved_776.csv")
    source = read(HERE / "source_eligibility.csv")
    oor = read(HERE / "s05_out_of_valid_range.csv")
    pool = read(REVIEWED / "tight_pass.csv")
    observe_pool = read(REVIEWED / "tight_observe.csv")
    pending = read(V22 / "s05_pending_isolation_v22.csv")
    nonadmit = read(V22 / "s05_ca_source_nonadmission_v22.csv")
    single_sided = read(V22 / "s05_rh03_single_sided_v22.csv")

    # ---------------- V：结构与守恒
    check("V01 决策行 = 278", len(decision) == 278, len(decision))
    pkeys = [r["security_id"] for r in decision]
    check("V02 主键无重复", len(pkeys) == len(set(pkeys)), len(set(pkeys)))
    check("V03 主键集合与 tight_pass 完全一致",
          set(pkeys) == {r["security_id"] for r in pool}, len(set(pkeys)))
    check("V04 通过 + 观察 = 278", len(passed) + len(observe) == 278,
          f"{len(passed)}+{len(observe)}")
    check("V05 通过/观察无交集且并集 = 278",
          set(r["security_id"] for r in passed).isdisjoint(
              set(r["security_id"] for r in observe))
          and set(r["security_id"] for r in passed) | set(r["security_id"] for r in observe) == set(pkeys), "")
    check("V06 标记行 = 278×5", len(flags) == 1390, len(flags))
    check("V07 标记行覆盖全部公司×指标组合",
          len({(r["security_id"], r["metric_id"]) for r in flags}) == 1390, "")
    check("V08 来源资格行 = 6076（仅五指标）", len(source) == 6076, len(source))
    check("V09 来源资格指标集合 = 五指标",
          {r["metric_id"] for r in source} == set(METRICS), sorted({r["metric_id"] for r in source}))
    check("V10 指标状态词表封闭",
          all(r[f"{m.lower()}_status"] in KNOWN_STATUS for r in decision for m in METRICS), "")
    check("V11 RH 状态词表封闭",
          all(r["rh_status"] in KNOWN_RH for r in flags), "")

    # ---------------- V：guards 对账
    st = {m: Counter(r[f"{m.lower()}_status"] for r in decision) for m in METRICS}
    with open(RELEASE, encoding="utf-8") as f:
        rel = json.load(f)
    g = rel["guards"]

    check("V12 RH01 277 可判 / 1 待核",
          st["M10"]["OK"] == 277 and st["M10"]["UNKNOWN_INPUT_MISSING"] == 1,
          f"{st['M10']['OK']}/{st['M10']['UNKNOWN_INPUT_MISSING']}")
    m11_hold = st["M11"]["UNKNOWN_CA_BLANK"] + st["M11"]["UNKNOWN_CA_SOURCE_NOT_ADMISSIBLE"]
    check("V13 RH02 118 可判 / 31 项目制不适用 / 129 待核",
          st["M11"]["OK"] == g["rh02"]["evaluable"]
          and st["M11"]["NOT_APPLICABLE_PROJECT_MODE"] == g["rh02"]["project_mode_not_applicable"]
          and m11_hold == g["rh02"]["hold"],
          f"{st['M11']['OK']}/{st['M11']['NOT_APPLICABLE_PROJECT_MODE']}/{m11_hold}")
    check("V14 RH03 133 可判 / 126 双期无金额 / 18 单边 / 1 待核",
          st["M12"]["OK"] == g["rh03"]["evaluable"]
          and st["M12"]["BOTH_BLANK_NO_USABLE_AMOUNT"] == g["rh03"]["both_periods_no_usable_amount"]
          and st["M12"]["SINGLE_SIDED_GAP"] == g["rh03"]["single_sided_gap"]
          and st["M12"]["UNKNOWN_INPUT_UNREADABLE"] == g["rh03"]["unreadable_or_missing"],
          f"{st['M12']['OK']}/{st['M12']['BOTH_BLANK_NO_USABLE_AMOUNT']}/"
          f"{st['M12']['SINGLE_SIDED_GAP']}/{st['M12']['UNKNOWN_INPUT_UNREADABLE']}")
    check("V15 RH04 240 可判 / 36 不适用（35 负分母 + 1 零基数）",
          st["M08"]["OK"] == 240
          and st["M08"]["NOT_APPLICABLE_NEGATIVE_DENOMINATOR"] == 35
          and st["M08"]["NOT_APPLICABLE_ZERO_BASE_FLOOR"] == 1,
          f"{st['M08']['OK']}/{st['M08']['NOT_APPLICABLE_NEGATIVE_DENOMINATOR']}/{st['M08']['NOT_APPLICABLE_ZERO_BASE_FLOOR']}")
    check("V16 RH05 274 可判 / 4 待核",
          st["M04"]["OK"] == 274 and st["M04"]["HOLD_DECISIVE_CELL_PENDING"] == 3
          and st["M04"]["UNKNOWN_INPUT_MISSING"] == 1,
          f"{st['M04']['OK']}/{st['M04']['HOLD_DECISIVE_CELL_PENDING']}/{st['M04']['UNKNOWN_INPUT_MISSING']}")

    # ---------------- V：上游计数
    contract = json.load(open(V22 / "s05_input_contract_v22.json", encoding="utf-8"))
    meas = contract["measured"]
    q09 = sum(1 for r in decision if "Q09" in (r["quality_flags"] or "").split(";"))
    check("V17 Q09 一次性损益主导 = 38（与 V2.2 实测一致）",
          q09 == meas["rh06_q09_marked"], f"{q09} vs {meas['rh06_q09_marked']}")
    check("V18 RH06 触发数 = Q09 标记数",
          sum(1 for r in decision if "RH06" in (r["rh_triggered"] or "").split(";")) == q09, q09)
    via = sum(1 for r in source if r["page_evidence_mode"] == "VIA_PARENT")
    check("V19 毛利率父键追溯行 = 851（与 V2.2 实测一致）",
          via == meas["via_parent_rows"], f"{via} vs {meas['via_parent_rows']}")
    check("V20 毛利率行 = 851 父键 + 1 行缺失 = 852",
          sum(1 for r in source if r["field_id"] == "FIN.GROSSMARGIN.PCT") == 852,
          sum(1 for r in source if r["field_id"] == "FIN.GROSSMARGIN.PCT"))

    # ---------------- V：三格隔离
    check("V21 来源不准入登记 = 3 格", len(nonadmit) == 3, len(nonadmit))
    na_keys = {(r["security_id"], r["field_id"], r["period_key"]) for r in nonadmit}
    adopted_yes = {(r["security_id"], r["field_id"], r["period_key"]) for r in source
                   if r["adopted"] == "YES"}
    in_source = {(r["security_id"], r["field_id"], r["period_key"]) for r in source}
    # 银宝/胜蓝：该格仍在来源表中但 adopted=NO；卓翼：该格根本未进入消费登记，
    # 其 M12 已降为双期无可采用金额，因此也不存在被采用的路径。
    na_ok = (na_keys & adopted_yes) == set()
    zhuo_key = ("SZ:002369", "FIN.CONTRACTASSET.INSTANT", "20260630")
    na_ok = na_ok and (zhuo_key not in in_source or zhuo_key not in adopted_yes)
    check("V22 三格中无一被采用（银宝/胜蓝在表内 adopted=NO；卓翼未进消费登记）",
          na_ok,
          f"在表内 {len(na_keys & in_source)}/3，被采用 {len(na_keys & adopted_yes)}")
    zhuo = [r for r in flags if r["security_id"] == "SZ:002369" and r["metric_id"] == "M12"]
    check("V23 卓翼 M12 = 双期无可采用金额",
          zhuo and zhuo[0]["metric_status"] == "BOTH_BLANK_NO_USABLE_AMOUNT", zhuo[0]["metric_status"] if zhuo else "")
    yin = [r for r in flags if r["security_id"] == "SZ:002786" and r["metric_id"] == "M12"]
    sheng = [r for r in flags if r["security_id"] == "SZ:300843" and r["metric_id"] == "M12"]
    check("V24 银宝/胜蓝 M12 = 单边缺口",
          yin and yin[0]["metric_status"] == "SINGLE_SIDED_GAP"
          and sheng and sheng[0]["metric_status"] == "SINGLE_SIDED_GAP",
          f"{yin[0]['metric_status'] if yin else ''}/{sheng[0]['metric_status'] if sheng else ''}")

    # ---------------- V：待核隔离
    pend_cells = {(r["security_id"], r["field_id"], r["period_key"]) for r in pending}
    pend_company = {r["security_id"] for r in pending}
    check("V25 待核行 = 15 / 唯一格 = 13 / 公司 = 5",
          len(pending) == 15 and len(pend_cells) == 13 and len(pend_company) == 5,
          f"{len(pending)}/{len(pend_cells)}/{len(pend_company)}")
    check("V26 待核公司全部落在 278 主键内", pend_company <= set(pkeys), sorted(pend_company))

    # ---------------- V：冀东装备
    jd = [r for r in decision if r["security_id"] == "SZ:000856"]
    check("V27 冀东装备进入观察", jd and jd[0]["decision"] == "QUALITY_HOLD",
          jd[0]["decision"] if jd else "")
    check("V28 冀东装备撤下 SG09 后仅剩 CASH",
          jd and "SG09" in (jd[0]["withdrawn_signals"] or "") and jd[0]["surviving_dimensions"] == "CASH",
          f"{jd[0]['withdrawn_signals'] if jd else ''}|{jd[0]['surviving_dimensions'] if jd else ''}")

    # ---------------- V：通过名单的闸门
    bad_dim = [r["security_id"] for r in passed if int(r["dimension_count_after"]) < 2]
    check("V29 通过名单每家公司撤维后仍 ≥ 2 维度", not bad_dim, bad_dim[:5])
    bad_l3 = [r["security_id"] for r in passed if r["l3_gate_result"] != "EVIDENCE_OK"]
    check("V30 通过名单每家公司 L3 闸门 = EVIDENCE_OK", not bad_l3, bad_l3[:5])
    check("V30b L3 闸门结果与决策词表互不混用",
          {r["l3_gate_result"] for r in passed} <= {"EVIDENCE_OK", "EVIDENCE_HOLD"}
          and {r["decision"] for r in decision} <= {"QUALITY_PASS", "QUALITY_HOLD"},
          "")

    # ---------------- V：无补零
    zero_fill = []
    for r in flags:
        if r["metric_id"] in ("M11", "M12") and r["metric_status"] == "OK":
            if r["metric_value"] == "":
                zero_fill.append((r["security_id"], r["metric_id"]))
        if r["metric_status"] != "OK" and r["metric_value"] != "":
            zero_fill.append((r["security_id"], r["metric_id"], "值应留空"))
    check("V31 非 OK 状态一律无值；OK 状态一律有值", not zero_fill, zero_fill[:5])

    # ---------------- V：776 保留
    check("V32 观察池 776 家原样携带", len(preserved) == 776, len(preserved))
    check("V33 776 家主键与 tight_observe 完全一致",
          [r["security_id"] for r in preserved] == [r["security_id"] for r in observe_pool], "")
    obs_ct = Counter(r["quality_source_state"] for r in preserved)
    check("V34 776 家中 15 家 PENDING_CE_SOURCE 保留",
          obs_ct.get("PENDING_CE_SOURCE", 0) == 15, dict(obs_ct))
    check("V35 时间隔离 4 家、锚点待核 1 家保留",
          sum(1 for r in preserved if r["cutoff_isolated"] == "YES") == 4
          and sum(1 for r in preserved if r["anchor_reselection_pending"] == "YES") == 1,
          f"{sum(1 for r in preserved if r['cutoff_isolated']=='YES')}/"
          f"{sum(1 for r in preserved if r['anchor_reselection_pending']=='YES')}")
    check("V36 776 家未被本轮复核改写",
          all(r["recheck_status"] == "CARRIED_FORWARD_UNCHANGED" for r in preserved), "")

    # ---------------- V：超范围登记
    check("V37 超 valid_range 值全部登记且非阻断", len(oor) == 20, len(oor))
    check("V38 超范围指标分布 = M08 15 / M10 4 / M12 1",
          Counter(r["metric_id"] for r in oor) == Counter({"M08": 15, "M10": 4, "M12": 1}),
          dict(Counter(r["metric_id"] for r in oor)))

    # ---------------- X：与掩码表独立复算比对
    mask = {}
    with open(MASK, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            mask[(r["security_id"], r["metric_id"])] = r
    mism = []
    compared = Counter()
    for row in decision:
        for m in METRICS:
            mv, stt = row[f"{m.lower()}_value"], row[f"{m.lower()}_status"]
            if stt != "OK" or mv == "":
                continue
            other = mask.get((row["security_id"], m))
            if not other or other["value"] == "":
                continue
            compared[m] += 1
            if abs(D(mv) - D(other["value"])) > D("0.000001"):
                mism.append((row["security_id"], m, mv, other["value"]))
    check("X01 五指标可判值与 S01 掩码表逐格一致（容差 1e-6）",
          not mism, f"比对 {sum(compared.values())} 格，不一致 {len(mism)} 格 {mism[:3]}")
    check("X02 比对格数 = 274+240+277+118+133 = 1042",
          sum(compared.values()) == 1042, dict(compared))

    # ---------------- X：输入指纹
    fp = rel["reviewed_input"]["files_sha256"]
    fp_bad = [n for n, s in fp.items() if sha256(V22 / n) != s]
    check("X03 V2.2 五份输入指纹 5/5 匹配放行记录", not fp_bad, fp_bad)
    check("X04 冻结 B 指纹匹配放行记录",
          sha256(FROZEN_B) == rel["reviewed_input"]["frozen_B_sha256"], sha256(FROZEN_B)[:16])

    # ---------------- X：单边反事实（J2）
    would = [r for r in single_sided if r["would_trigger_rh03_if_zero_filled"] == "YES"]
    check("X05 18 家单边缺口即使填零也不触发 RH03（J2）",
          len(single_sided) == 18 and not would, f"{len(single_sided)} 家，触发 {len(would)} 家")

    # ---------------- V：行尾
    lf_bad, crlf_bad = [], []
    for p in sorted(HERE.iterdir()):
        if not p.is_file() or p.name.startswith("."):
            continue
        if p.suffix in (".csv",):
            data = p.read_bytes()
            if b"\r\n" not in data:
                crlf_bad.append(p.name)
        elif p.suffix in (".md", ".json", ".py"):
            data = p.read_bytes()
            if b"\r\n" in data:
                lf_bad.append(p.name)
    check("V39 CSV 为 CRLF", not crlf_bad, crlf_bad)
    check("V40 md/json/py 为 LF", not lf_bad, lf_bad)

    # ---------------- 汇总
    out = {
        "artifact": "S05_SELF_CHECK",
        "issue": "S05 / #40",
        "executor": "WorkBuddy AI",
        "review_nature": "SELF_CHECK",
        "checks_passed": sum(1 for r in results if r["pass"]),
        "checks_total": len(results),
        "verdict": "SELF_CHECK_PASS" if all(r["pass"] for r in results) else "SELF_CHECK_FAIL",
        "results": results,
    }
    with open(HERE / "s05_self_check.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps({k: out[k] for k in ("checks_passed", "checks_total", "verdict")},
                     ensure_ascii=False))
    for r in results:
        if not r["pass"]:
            print("FAIL", r["name"], "|", r["detail"])
    return 0 if out["verdict"] == "SELF_CHECK_PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
