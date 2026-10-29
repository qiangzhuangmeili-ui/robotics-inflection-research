import csv,gzip,hashlib,json,subprocess,zipfile
from pathlib import Path
from datetime import datetime,timezone,timedelta
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    v=json.loads((OUT/'verification.json').read_text(encoding='utf-8'));assert v['fail_count']==0
    s=json.loads((OUT/'rebuild_summary.json').read_text(encoding='utf-8'))
    c=json.loads((OUT/'coverage_summary.json').read_text(encoding='utf-8'))
    byte_audit=[]
    for rel in ['runs/issues/S01/screen_rules_v2.json','data/active_issue.json','PROJECT_STATE.json']:
        a=(ROOT/rel).read_bytes();b=subprocess.check_output(['git','show','HEAD:'+rel],cwd=ROOT)
        assert a.replace(b'\r\n',b'\n')==b.replace(b'\r\n',b'\n')
        byte_audit.append(dict(path=rel,working_sha256=hashlib.sha256(a).hexdigest(),git_blob_sha256=hashlib.sha256(b).hexdigest(),only_line_endings_differ=a!=b,content_unchanged=True))
    (OUT/'baseline_byte_audit.json').write_text(json.dumps(byte_audit,ensure_ascii=False,indent=2),encoding='utf-8')
    old={r['security_id']:r for r in csv.DictReader((ROOT/'runs/issues/S02/company_metric_summary.csv').open(encoding='utf-8-sig'))}
    new=list(csv.DictReader((OUT/'s02/company_metric_summary.csv').open(encoding='utf-8-sig')))
    anchors=[dict(security_id=r['security_id'],stock_name=r['stock_name'],old_period=old[r['security_id']]['period_key'],new_period=r['period_key'],reason='锚定定义不变；修复字段有效性改变最新有可用营收/扣非字段的期间') for r in new if r['period_key']!=old[r['security_id']]['period_key']]
    (OUT/'anchor_period_changes.json').write_text(json.dumps(anchors,ensure_ascii=False,indent=2),encoding='utf-8')
    mpath=OUT/'s02/calculation_manifest.json';m=json.loads(mpath.read_text(encoding='utf-8'))
    m['l0_addendum_sha256']=sha(OUT/'l0/l0_rules_patch.json')
    m['latest_period_definition'].update(definition_unchanged=True,distribution_same_as_baseline=not anchors,anchor_changes_file=str((OUT/'anchor_period_changes.json').relative_to(ROOT)).replace('\\','/'))
    mpath.write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
    review=dict(issue_key='S02',plan_version='20261026_collection_first_v2',reviewed_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),executor='Codex with bounded luna_worker tasks',review_nature='SELF_CHECK_SOURCE_BACKED_REMEDIATION',decision='REPAIR_SELF_CHECK_PASS_EXTERNAL_RECHECK_REQUIRED',original_S02_disposition='RETURN_FOR_REWORK_ON_INPUT_QUALITY_AND_L0_GAP',release_S03=False,checks_pass=v['pass_count'],checks_fail=0,coverage=c,metric_recalculation=s,formulas_changed=False,thresholds_changed=False,frozen_data_overwritten=False,online_control='ONLINE_READ_NO_REMOTE_CLAIM_OR_UPDATE',limits=['21家最新期仍少于8个可用字段，保留HOLD或未知，不作为无改善淘汰。','本轮只修59家相关360份文件，没有全池逐家业务精读。','旧冻结结果保留；新输入/计算版本需由WorkBuddy或其他复核者验证后采用。','未更改active_issue、PROJECT_STATE或S03状态；没有代发GitHub评论。'])
    (OUT/'review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8')
    handoff=f'''# S02 修复交接（2026-10-29）

本包是在既有 S02 #37 下完成的修复版本；未改旧 S00/S01/S02 冻结数据、未改指标公式或阈值、未开 S03。原执行者 WorkBuddy 保留当前占用，本包不抢占远端卡。

## 已纠正的归因

1. S00 的 `extract_run_summary.json` 已记录全部12槽抽取，不是“只抽了年报”。字段漏取主要来自整数金额、分行表格/编号、报表标题变体、单位识别和口径待核。
2. 赣锋、中科、金百泽、五洋、毅昌五家 Q3 的单位都是元，错在把同比百分比当成累计扣非金额。不能统一乘一万。美的也取错了列，本期为19,595,179千元（195.95179亿元），基期为26,235,399千元（262.35399亿元）；约250亿元不能作为本期替代值。
3. 传智教育16万pp不是低基数数学现象：摘要数据被错误套用了同页后续子表“万元”单位。复星2026H1还把脚注3拼到金额前，广汽有跨页表头错配。这些通用错误已修并重抽。
4. L0改为结构化JSON条件的唯一执行来源，覆盖9种状态/12指标的全部125,970种计数组合，无OK但有PROVISIONAL单列W5，其余混合单列W9，均不得被当成无改善或直接淘汰。

## 完成的工作和结果

- 对59家公司360份报告进行定向重抽；每份抽取前核本地PDF SHA256与采集台账一致。只读原PDF，没有手工改数字。
- 新标准化数据 {s['normalized_rows']:,} 行，逐格数据差异 {s['normalized_changes']:,} 条；全池12,648格中 {s['metric_changes']} 格变化，涉及 {s['companies_changed']} 家。目标范围以外公司指标逐格未变。
- 原53家：32家恢复到至少8个可用字段；其余21家分别为11家三表/摘要待核、5家定位或合并口径待核、3家只有旧来源无当前PDF、1家文本/OCR问题、1家仍部分字段未知。逐家公司见 `coverage_resolution.csv`，不能把21家归为无改善。
- 状态：OK {s['status_counts']['OK']:,}、PROVISIONAL {s['status_counts']['PROVISIONAL']:,}、HOLD {s['status_counts']['HOLD']}、MISSING {s['status_counts']['MISSING']}、NOT_COMPARABLE {s['status_counts']['NOT_COMPARABLE']}、UNDEFINED_BASE {s['status_counts']['UNDEFINED_BASE']}、NOT_APPLICABLE {s['status_counts']['NOT_APPLICABLE']}。PROVISIONAL仍不能当干净OK。
- 新L0：EVALUABLE {s['l0_counts']['EVALUABLE']}，W5 {s['l0_counts']['W5_PROVISIONAL_ONLY']}，W9 {s['l0_counts']['W9_MIXED_NON_EVALUABLE']}。原377/17只是旧输入快照，不能固定数量。
- 自检 {v['pass_count']}/{len(v['checks'])} PASS：含19条独立原页预期、原值×单位换算、缺值/串行/负数/占位等反例、公式文件哈希不变、全部12,648主键、无截止日后披露、53家队列完整和L0穷举。沿用S02的5指标独立算术复算亦通过。
- 两家公司锚期变化详见 `anchor_period_changes.json`。锚定定义没有变；Q13/Q14是与旧S01计数的预期差异，保留WARN，未伪装成相同。

## 给 WorkBuddy 的接手步骤

1. 先在线重读 active_issue/PROJECT_STATE 和当前卡，确认未有新的占用或输入版本；本包基线是本地 `547508d`，不宣称执行过git pull。
2. 将包解压到正式仓库根目录。包只包含本次新增目录、修复后的 `tools/a03_financial_field_extractor.py` 和新增 `tools/l0_classify.py`，不会覆盖旧冻结交付或控制文件。校验 `manifest.json` 后，用Python标准库gzip把本包 `s00/financial_normalized.csv.gz` 解到同目录CSV（若已存在先核SHA，不覆盖不同版本）。
3. 首先复核 `verification.json`、`units/normalized_corrections.csv`、`units/regression/expected.json` 及原页截图；审查 `normalized_delta.csv`、`metric_delta.csv`、`coverage_resolution.csv`。新输出路径是本新增目录的 `s00/` 和 `s02/`，不要直接运行旧脚本覆盖正式冻结文件。
4. 可复跑 `verify.py`；完整重建用 `reextract.py --workers 8 --refresh` → `rebuild.py` → `verify.py` → `tools/l0_classify.py --summary <新company_metric_summary.csv> --out <独立输出目录>`。复跑需要现有原PDF缓存和旧冻结S00输入；云端读不到本机时使用document_id、台账官方URL/Drive ID及包内原页证据，不能把路径当已上传PDF。
5. 新输入采用须另记版本和指纹，并复跑S01技术政策测试与S02核验。复核前S03继续锁定。若复核决定带限制放行，21家及其HOLD/未知必须留在观察/待核分流，不能当作无信号淘汰；不得将PROVISIONAL/HOLD计入干净维度。不新增逐卡用户批准。

## 工程说明

旧Git对象中S01规则及控制JSON仍存在LF/CRLF差异，`.gitattributes`不会追溯修复旧blob；`baseline_byte_audit.json`已核仅换行不同。旧冻结文件没有被改写。L0仅额外接受已核实的同一规则LF字节哈希，不接受其他内容改变。公式仍调用原 `tools/s01_rules_check.py`（SHA256 134d0feeb2aff67f1a6ab9df0a08a8d96c6a64a294df17382e06e5cd4964470f）。

包中没有原始PDF、账号配置或密钥。新标准化全表压缩存放，按项目约定经Drive交接，不把大型财务底表写入GitHub。
'''
    (OUT/'handoff.md').write_text(handoff,encoding='utf-8')
    (OUT/'manifest.json').write_text('{}',encoding='utf-8')
    files=[]
    excluded_prefix=('probe_','summary_probe_','titles_')
    for p in OUT.rglob('*'):
        if not p.is_file() or '__pycache__' in p.parts or p.name.startswith(excluded_prefix):continue
        if p.name.endswith('.log') and p.name not in ['verify.log','reextract_final_verified.log','rebuild.log']:continue
        if p.name in ['financial_normalized.csv','manifest.json','drive_receipt.json','package_receipt.json'] or p.suffix=='.zip':continue
        files.append(p)
    files += [ROOT/'tools/a03_financial_field_extractor.py',ROOT/'tools/l0_classify.py']
    manifest=dict(schema='S02_REPAIR_DELIVERY_V1',review_nature='SELF_CHECK',baseline_commit='547508d',release_S03=False,files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(files)])
    mp=OUT/'manifest.json';mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');files.append(mp)
    zp=ROOT.parent/'S02_修复接手包_20261029.zip'
    with zipfile.ZipFile(zp,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in files:z.write(p,p.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(zp) as z:
        assert z.testzip() is None
        for f in manifest['files']:assert hashlib.sha256(z.read(f['path'])).hexdigest()==f['sha256']
    receipt=dict(local_path=str(zp),sha256=sha(zp),bytes=zp.stat().st_size,entries=len(files),manifest_entries_verified=len(manifest['files']))
    (OUT/'package_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(receipt,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
