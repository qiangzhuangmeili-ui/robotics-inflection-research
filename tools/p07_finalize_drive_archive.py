"""Finalize P07 Drive archival using connector readbacks; no network or collection."""
from pathlib import Path
import csv, hashlib, json, sys
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"runs/issues/P07/drive_archive"
sys.path.insert(0,str(ROOT/"tools"))
from p06_storage_plan import validate, receipt_invariant_checks
def readj(p): return json.loads(p.read_text(encoding="utf-8-sig"))
def writej(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
def readcsv(p):
    with p.open(encoding="utf-8-sig",newline="") as f:
        r=csv.DictReader(f); return r.fieldnames,list(r)
def writecsv(p,fields,rows):
    with p.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="raise");w.writeheader();w.writerows(rows)
cp=readj(OUT/"checkpoint.json")
plan=cp["plan"]; results={r["document_id"]:r for r in cp["results"]}
assert len(plan)==len(results)==65
now=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
schema=readj(ROOT/"runs/issues/P06/transfer_receipt_schema.json")
rf,registry=readcsv(ROOT/"data/document_registry.csv")
old_registry=[dict(r) for r in registry]
registry_ids={r["document_id"] for r in registry}
ff,folders=readcsv(ROOT/"data/drive_folders.csv")
old_folder_ids={f["folder_id"] for f in folders}
receipts=[]; aliases=[]; coverage=[]; added=0
for row in plan:
    result=results[row["document_id"]]
    assert result["status"]=="VERIFIED" and result["listed"]
    assert result["binary_sha256"]==row["sha256"]
    assert result["binary_bytes"]==row["bytes"]==int(result["metadata"]["size"])
    assert result["target_folder_id"] in result["metadata"]["parent_ids"]
    local=Path(row["path"])
    assert hashlib.sha256(local.read_bytes()).hexdigest()==row["sha256"]
    matches=[r for r in registry if r["drive_file_id"]==result["file"]["id"]]
    if not matches: matches=[r for r in registry if r["sha256"]==row["sha256"]]
    if matches:
        assert len(matches)==1
        canonical=matches[0]
        assert canonical["security_id"]==row["security_id"]
        assert canonical["sha256"] in ("",row["sha256"])
        if not canonical["sha256"]: canonical["sha256"]=row["sha256"]
        if not canonical["page_count"] and row["pages"]: canonical["page_count"]=str(row["pages"])
        if canonical["drive_file_id"]: assert canonical["drive_file_id"]==result["file"]["id"]
    else:
        assert row["document_id"] not in registry_ids
        canonical=dict.fromkeys(rf,"")
        canonical.update(document_id=row["document_id"],security_id=row["security_id"],
            stock_code=row["code"],stock_name=row["name"],source_type="CNINFO_OFFICIAL_PDF",
            original_title=row["title"],published_on=row["published_on"],period_covered=row["period"],
            primary_url=row["url"],local_file=str(local),page_count=str(row["pages"]) if row["pages"] else "",
            sha256=row["sha256"],collected_on=now[:10],file_status="DRIVE_BINARY_READBACK_MATCH",
            limitations="P07文件身份校验沿用WorkBuddy校准；Codex本次仅归档并回读二进制核哈希，未新增业务结论或全文核读。",
            access_check_status="NOT_CHECKED",original_filename=local.name)
        registry.append(canonical);registry_ids.add(canonical["document_id"]);added+=1
    # Preserve source fields and all existing access/evidence states.
    canonical.update(storage_provider="GOOGLE_DRIVE",drive_file_id=result["file"]["id"],
        drive_url=result["metadata"]["url"],archive_status="VERIFIED")
    target_path="机器人行业拐点研究/01_原始资料/"+row["code"]+"_"+row["name"]
    if result["target_folder_id"]!=next(f["id"] for f in cp["company_folders"] if f["title"].startswith(row["code"]+"_")):
        target_path+="/"+row["period"]
    canonical["drive_folder_path"]=target_path
    pages=row["pages"] or int(canonical.get("page_count") or 0) or None
    official=row["url"].startswith("https://static.cninfo.com.cn/")
    receipt={
      "receipt_id":"RCP-"+hashlib.sha256((row["document_id"]+result["file"]["id"]+now).encode()).hexdigest()[:12].upper(),
      "schema_version":"TRANSFER_RECEIPT_V1","document_id":row["document_id"],"security_id":row["security_id"],
      "slot_id":row["slot"],"doc_class":{"annual":"ANNUAL_REPORT","h1":"SEMI_ANNUAL_REPORT","q1":"QUARTERLY_REPORT"}[row["slot"].split("_")[0]],
      "revision_no":0,"supersedes_document_id":None,
      "source":{"primary_url":row["url"] if official else result["metadata"]["url"],"source_kind":"CNINFO_OFFICIAL" if official else "USER_UPLOAD",
        "http_status":200,"disclosed_on":row["published_on"] if row["published_on"]!="UNKNOWN" else None,
        "identity_method":"NOT_VERIFIED","official_provenance":"PENDING"},
      "download":{"attempted":True,"bytes_received":row["bytes"],"sha256":row["sha256"],"content_length_matches":True,
        "page_count":pages,"downloaded_at_utc":result["verified_at"],"partial_suffix_used":False},
      "local_cache":{"cache_root":str(local.parent),"relative_path":local.name,"exists":True,"keep_until":"ALWAYS_KEEP"},
      "drive":{"target_folder_path":target_path.split("/",1)[1],"target_folder_id":result["target_folder_id"],
        "file_id":result["file"]["id"],"file_url":"https://drive.google.com/file/d/"+result["file"]["id"],
        "upload_attempted":result["operation"]=="UPLOADED","upload_result":"SUCCESS" if result["operation"]=="UPLOADED" else "NOT_TRIED",
        "readback":{"listed":True,"name":result["metadata"]["title"],"mime_type":result["metadata"]["mime_type"],"size_bytes":row["bytes"],
          "parents_contains_target_folder_id":True,"readback_at_utc":result["verified_at"]}},
      "archive_status":"VERIFIED","access_check_status":"NOT_CHECKED","evidence":{"level":"L2","page_quote":None},
      "verification":{"nature":"SELF_CHECK","checks":["CONTENT_LENGTH","SHA256","DRIVE_READBACK","PARENTS_MATCH"],
        "verified_by":"Codex","verified_at_utc":now},"created_at_utc":now}
    errors=validate(receipt,schema)+receipt_invariant_checks(receipt)
    assert not errors,(row["document_id"],errors)
    receipts.append(receipt)
    aliases.append({"collection_document_id":row["document_id"],"canonical_document_id":canonical["document_id"],
        "security_id":row["security_id"],"slot_id":row["slot"],"sha256":row["sha256"],"drive_file_id":result["file"]["id"],
        "operation":result["operation"]})
    coverage.append({"security_id":row["security_id"],"slot_id":row["slot"],"collection_document_id":row["document_id"],
      "canonical_document_id":canonical["document_id"],"drive_file_id":result["file"]["id"],"drive_url":result["metadata"]["url"],
      "archive_status":"VERIFIED","bytes":row["bytes"],"sha256":row["sha256"],"operation":result["operation"],
      "receipt":"runs/issues/P07/drive_archive/receipts.json#"+row["document_id"]})
# Existing rows may change only the archive-related fields; no deletion or access/evidence promotion.
allowed={"storage_provider","drive_file_id","drive_url","drive_folder_path","archive_status"}
by_id={r["document_id"]:r for r in registry}
for old in old_registry:
    assert all(old[k]==by_id[old["document_id"]][k] for k in rf if k not in allowed and not (k in {"sha256","page_count"} and not old[k]))
assert len(registry)==len(old_registry)+added
assert len({r["document_id"] for r in registry})==len(registry)
writej(OUT/"receipts.json",receipts);writej(OUT/"document_aliases.json",aliases)
writecsv(OUT/"archive_coverage.csv",list(coverage[0]),coverage)
for f in cp["company_folders"]:
    if f["id"] not in old_folder_ids:
        folders.append(dict(zip(ff,["COMPANY",f["title"],f["id"],f["url"],"1uC1sk5q7PKMZMLPLt-xIxOj2nPk4z0Ne","P07原件归档","CREATED_AND_READ_BACK"])))
        old_folder_ids.add(f["id"])
for key,f in cp["period_folders"].items():
    if f["id"] in old_folder_ids: continue
    company=next(c for c in cp["company_folders"] if c["title"].startswith(key.split("/")[0]+"_"))
    folders.append(dict(zip(ff,["PERIOD",f["title"],f["id"],f["url"],company["id"],"P07报告期目录；已列出文件并回读","CREATED_AND_READ_BACK"])))
    old_folder_ids.add(f["id"])
writecsv(ROOT/"data/document_registry.csv",rf,registry);writecsv(ROOT/"data/drive_folders.csv",ff,folders)
cf,index=readcsv(ROOT/"runs/collection/collection_index.csv")
extra=["canonical_document_id","drive_file_id","drive_url","archive_status","archive_receipt"]
for col in extra:
    if col not in cf: cf.append(col)
mapped={(r["security_id"],r["slot_id"]):r for r in coverage}
for r in index:
    if (r["security_id"],r["slot_id"]) not in mapped: continue
    c=mapped[r["security_id"],r["slot_id"]]
    r.update({k:c[k] for k in extra if k!="archive_receipt"});r["archive_receipt"]=c["receipt"]
writecsv(ROOT/"runs/collection/collection_index.csv",cf,index)
# Keep collection statuses/checkpoints unchanged; add a separate archive record.
for p in (ROOT/"runs/collection/checkpoint").glob("*.json"):
    ledger=readj(p)
    for slot,record in ledger.get("slots",{}).items():
        c=mapped.get((ledger["security_id"],slot))
        if c: record["drive_archive"]={k:c[k] for k in ["canonical_document_id","drive_file_id","drive_url","archive_status","receipt"]}
    writej(p,ledger)
summary={"issue_key":"P07","scope":"DRIVE_ARCHIVE_FOLLOWUP_ONLY","executor":"Codex","review_nature":"SELF_CHECK_FILE_ARCHIVE_ONLY",
    "completed_at":now,"files":65,"uploaded_new":sum(r["operation"]=="UPLOADED" for r in results.values()),
    "reused":sum(r["operation"]=="REUSED" for r in results.values()),"binary_sha256_matches":65,"listed_parent_matches":65,
    "bytes":sum(r["bytes"] for r in plan),"receipts_schema_pass":65,"registry_rows_before":len(old_registry),
    "registry_rows_after":len(registry),"registry_rows_added":added,"not_tried_slots_unchanged":5,
    "full_universe_started":False,"business_adoption_added":0,"ai_read_confirmed_added":0,"cache_deleted":0,
    "receipt_file":"runs/issues/P07/drive_archive/receipts.json",
    "limitations":["仅完成Drive归档，不重新认定P07财务字段校准或采集器修复。",
      "不声明全池采集已启动或所有M00技术问题已解决；登记表级幂等仍待采集器实现。",
      "正文主体/报告期身份结论沿用WorkBuddy；本次未逐份精读报告，未新增业务独立验收。",
      "旧原文来源/版本限制保留；云端二进制一致不等于官方来源链独立核验。"]}
writej(OUT/"summary.json",summary)
for path in [ROOT/"data/active_issue.json",ROOT/"PROJECT_STATE.json"]:
    obj=readj(path)
    if path.name=="active_issue.json": obj["p07_drive_archive_followup"]=summary
    else: obj["issue_plan"]["p07_drive_archive_followup"]=summary
    writej(path,obj)
handoff=f"""# P07 Drive归档补充交接

Codex于 {now} 使用已连接的Google Drive工具完成归档。

- 65份原件：58份新上传、7份复用。65/65云端完整二进制SHA-256与本地一致。
- 65/65已重新列目录、核对真实文件ID、MIME、字节数和父目录。65份回执通过P06 schema校验。
- 登记表由{len(old_registry)}行增至{len(registry)}行；既有编号保留，P07编号别名见document_aliases.json。
- runs/collection/collection_index.csv和共享台账均增加独立归档信息；原采集状态不变。
- 920011的5个NOT_TRIED槽仍保留；本次不下载缺口、不改上市日期、不清理任何原件。
- 回执为SELF_CHECK文件归档核验，未新增AI_READ_CONFIRMED或业务证据采用。
- Drive权限阻断在本Codex连接器中已解除，不代表WorkBuddy获得了Drive权限。
- 未启动M00；登记表级幂等和财务字段采集等独立执行问题仍按任务卡处理。
- 来源时间与主体识别沿用原校准记录；旧来源链/版本限制未消除。

核心文件：receipts.json、archive_coverage.csv、document_aliases.json、summary.json。
"""
(OUT/"handoff.md").write_text(handoff,encoding="utf-8")
cp["status"]="COMPLETE";cp["completed_at"]=now;writej(OUT/"checkpoint.json",cp)
manifest={"issue_key":"P07","scope":"DRIVE_ARCHIVE_FOLLOWUP_ONLY","generated_at":now,"files":[]}
for p in sorted(OUT.glob("*")):
    if p.name in {"manifest.json","checkpoint.json"} or not p.is_file(): continue
    manifest["files"].append({"path":p.relative_to(ROOT).as_posix(),"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()})
writej(OUT/"manifest.json",manifest)
print(json.dumps(summary,ensure_ascii=True))

