"""Apply verified Drive readback results to P02 outputs, preserving the original review."""
import csv, hashlib, json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runs/issues/P02'
def get(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def run():
    now=datetime.now(timezone.utc).isoformat()
    checks=get(OUT/'drive_readback_checks.json'); summary=get(OUT/'drive_followup_summary.json')
    assert len(checks)==90 and all(r['status']=='PDF_PARSED' and r['metadata_size_match'] for r in checks)
    assert all(r['hash_comparison']!='MISMATCH' and r['page_count_comparison']!='MISMATCH' for r in checks)
    for name in ['existing_assets.csv','reuse_manifest.json','review.json','manifest.json']:
        backup=OUT/('workbuddy_baseline_'+name)
        if not backup.exists():backup.write_bytes((OUT/name).read_bytes())
    with (OUT/'workbuddy_baseline_existing_assets.csv').open(encoding='utf-8-sig',newline='') as f:assets=list(csv.DictReader(f))
    by_id={r['document_id']:r for r in checks}
    for a in assets:
        r=by_id.get(a['asset_id'].removeprefix('AST-'))
        if not r:continue
        a['location_primary']=r['local_path'];a['location_type']='REPO_LOCAL_CACHE';a['location_secondary']=r['drive_url']
        a['sha256_actual']=r['sha256_actual'];a['sha256_match']=r['hash_comparison'];a['size_bytes']=str(r['size_bytes'])
        a['binary_status']='OBTAINED';a['verification_status']='DRIVE_BINARY_READBACK_CHECKED'
        a['limitations']='Drive元数据、字节大小、PDF可解析性与首页身份要素已核；87条旧哈希匹配、3条无旧哈希。官方源同源性另核；未做完整业务核读，不升级AI_READ_CONFIRMED或业务采用。旧限制见workbuddy_baseline_existing_assets.csv。'
        a['next_action']='REUSE_EXISTING_FILE;OFFICIAL_PROVENANCE_WHEN_USED_FOR_RESEARCH'
        # Keep the original archive/access/evidence states. Identity-token checks are not a provenance audit.
    with (OUT/'existing_assets.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(assets[0]));w.writeheader();w.writerows(assets)
    reuse=get(OUT/'workbuddy_baseline_reuse_manifest.json')
    reuse['drive_followup']=summary;reuse['blocked']=[]
    reuse['historical_blocked']=get(OUT/'workbuddy_baseline_reuse_manifest.json')['blocked']
    reuse['remaining_scope_limits']=['P01迁移未执行，属后续卡','官方源同源性未核；Drive字节回读不能替代官方来源证明','财务缺7类字段留P04/P05','业务独立验收不在P02范围']
    put(OUT/'reuse_manifest.json',reuse)
    review=get(OUT/'workbuddy_baseline_review.json')
    review['drive_followup']={'executor':'Codex','reviewer':'Codex','method':'SELF_CHECK_FILE_VALIDATION_ONLY','reviewed_at':now,'decision':'SELF_CHECK_PASS','results':summary,'checks_file':'runs/issues/P02/drive_readback_checks.json','legacy_review_preserved':'runs/issues/P02/workbuddy_baseline_review.json'}
    put(OUT/'review.json',review)
    text='''\n\n## 2026-10-26 Codex 接续收尾（以本节更新Drive阻断项）\n\n用户明确指定由Codex补完Drive部分。使用已连接的私有Drive工具读取90条登记文件的真实元数据，取得90份原始PDF并保存到仓库忽略的sources/drive_readback_20261026/。90/90可解析且大小匹配；87/87旧SHA-256及87/87旧页数匹配，另3份此前无哈希/页数，本轮实算并保留NO_BASELINE_HASH。51份首页登记标题精确匹配，39份在前6物理页核对主体、年份及报告类型要素。\n\n未精读业务、不新增业务独立验收、不改原登记表或旧归档/AI读取状态。官方源同源性和完整正文/关键页核读仍独立记录。P02原先的Drive访问阻断在Codex当前会话已解除；不能推断WorkBuddy也获得了连接能力。\n\n计数澄清：原登记表73条UPLOADED_UNVERIFIED，另3条UPLOADED_AND_TEXT_READ经P01保守归一后，P02清单计76条。90条Drive记录=73+14+3。旧交接中的87个文件名匹配说法由reuse_manifest的90个唯一文件名匹配口径更正；87为已有内容哈希数，非Drive记录总数。\n\n本卡范围已收尾，技术核验结论SELF_CHECK_PASS。P07仍需其余依赖全部通过，不因P02单卡通过而提前放行。下一步按用户指定转P03 #14；P04仍待办。详情见drive_followup_summary.json、drive_readback_checks.csv/json；旧输出在workbuddy_baseline_*保留。\n'''
    handoff=OUT/'handoff.md'
    if 'Codex 接续收尾' not in handoff.read_text(encoding='utf-8-sig'):handoff.write_text(handoff.read_text(encoding='utf-8-sig')+text,encoding='utf-8')
    paths=[p for p in OUT.iterdir() if p.is_file() and p.name!='manifest.json']+[ROOT/'tools/p02_drive_followup.py',ROOT/'tools/p02_finalize_followup.py',ROOT/'tools/drive_verify_download.py']
    put(OUT/'manifest.json',{'issue_key':'P02','plan_version':'20261026_collection_first_v2','executor':'Codex','generated_at':now,'review_nature':'SELF_CHECK','scope':'Supplement original P02 with authenticated Drive binary readback; preserve original baseline','files':[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]})
    print(json.dumps({'assets':len(assets),'drive_checked':len(checks),'decision':'SELF_CHECK_PASS'},ensure_ascii=False))
if __name__=='__main__':run()
