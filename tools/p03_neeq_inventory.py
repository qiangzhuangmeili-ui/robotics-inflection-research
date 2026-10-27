"""NEEQ scoped report-index adapter and P03 15-company technical inventory."""
from pathlib import Path
import sys,json,re,time,csv,hashlib,urllib.parse
sys.path.insert(0,str(Path(__file__).resolve().parent))
import p03_neeq_recheck as p
ROOT=p.ROOT; OUT=p.OUT; RAW=p.RAW
CODES={"920002":"873843","920011":"874468","920022":"873702","920055":"874546","920060":"873718","920066":"873664","920080":"873044","920091":"873739","920096":"874302","920100":"873669","920124":"874643","920211":"874510","920220":"874326","920238":"874396","920289":"874378"}
FIELDS=["companyCd","companyName","disclosureTitle","disclosurePostTitle","destFilePath","publishDate","xxfcbj","fileExt","xxzrlx"]
def parse_response(txt):
    start=txt.find("(")
    if start>=0: txt=txt[start+1:txt.rfind(")")]
    obj=json.loads(txt)
    if not isinstance(obj,list) or not obj or not isinstance(obj[0].get("listInfo"),dict):
        raise ValueError("UNEXPECTED_SCHEMA")
    return obj[0]["listInfo"]
def params(code,page=0):
    return {"noticeType[]":["9503"],"disclosureType[]":["9503"],"page":page,"companyCd":code,
       "isNewThree":1,"startTime":"2023-01-01","endTime":"2026-10-25","keyword":"","hyType":"",
       "xxfcbj[]":["3"],"needFields[]":FIELDS,"siteId":1}
def slot_of(title):
    t=re.sub(r"\s+","",title)
    if "摘要" in t or "更正公告" in t or "提示" in t or "取消" in t:return None
    m=re.search(r"(20\d{2})年?(年度|半年[度]?|第?[一三]季度)报告",t)
    if not m:return None
    y,typ=m.groups()
    prefix="annual" if typ=="年度" else "h1" if typ.startswith("半") else "q1" if "一" in typ else "q3"
    return prefix+"_"+y

def is_current_report(row):
    return bool(slot_of(row["disclosureTitle"])) and "取消" not in (row.get("disclosurePostTitle") or "")
def main():
    p.records=json.loads((OUT/"initial_probes.json").read_text(encoding="utf-8"))
    t=p.request("session_inventory","http://www.neeq.com.cn/");m=re.search(r"C3VK=([0-9a-f]+)",t)
    hdr={"Referer":"https://www.neeq.com.cn/disclosure/announcement.html","X-Requested-With":"XMLHttpRequest"}
    if m:hdr["Cookie"]="C3VK="+m.group(1)
    target=list(csv.DictReader((ROOT/"runs/issues/A01/residual_failures.csv").open(encoding="utf-8-sig")))
    master={x["stock_code"]:x for x in csv.DictReader((ROOT/"data/company_master.csv").open(encoding="utf-8-sig"))}
    all_results=[]; mapping=[]; slot_rows=[]
    for code,old in CODES.items():
        rows=[];total=None;pages=[]
        for page in range(10):
            label="neeq_"+old+"_p"+str(page)
            cache=RAW/(label+".txt")
            txt=cache.read_text(encoding="utf-8") if cache.exists() else p.request(label,"https://www.neeq.com.cn/disclosureInfoController/companyAnnouncement.do",params(old,page),hdr)
            if not txt:raise RuntimeError("SOURCE_ROUTE_STOPPED")
            o=parse_response(txt)
            if total is None:total=int(o["totalElements"])
            if int(o["totalElements"])!=total:raise RuntimeError("TOTAL_CHANGED")
            pages.append({"page":page,"rows":len(o["content"]),"total":total})
            rows.extend(o["content"])
            unique={x["destFilePath"]:x for x in rows}
            if len(unique)==total:break
            if not o["content"]:raise RuntimeError("INCOMPLETE_PAGINATION")
        unique=list({x["destFilePath"]:x for x in rows}.values())
        if len(unique)!=total:raise RuntimeError("INDEX_INCOMPLETE")
        expected=master[code]["stock_name"]
        if not unique:verdict="NO_POSITIVE_IDENTITY"
        elif all(x["companyCd"]==old and x["companyName"]==expected for x in unique):verdict="OFFICIAL_INDEX_NAME_AND_CODE_MATCH"
        else:raise RuntimeError("ISSUER_MISMATCH "+code)
        rec={"stock_code":code,"stock_name":expected,"old_neeq_code":old,"total":total,"rows":unique,
             "pages":pages,"reconciled":len(unique)==total,"mapping_verdict":verdict}
        all_results.append(rec)
        proof=next((x for x in unique if slot_of(x["disclosureTitle"]) and "摘要" not in x["disclosureTitle"]),unique[0] if unique else {})
        mapping.append({"security_id":"BJ:"+code,"stock_name":expected,"old_neeq_code":old,
           "verification":verdict,"official_index":"https://www.neeq.com.cn/disclosureInfoController/companyAnnouncement.do",
           "proof_title":proof.get("disclosureTitle"),"proof_url":"https://www.neeq.com.cn"+proof["destFilePath"] if proof else "",
           "raw_cache":"sources/p03_neeq_recheck_20261027/neeq_"+old+"_p0.txt"})
        for target_row in [x for x in target if x["stock_code"]==code]:
            hits=[x for x in unique if is_current_report(x) and slot_of(x["disclosureTitle"])==target_row["slot_id"]]
            # Preserve each version and explicitly identify cancelled versions.
            hitdata=[{**x,"official_pdf_url":"https://www.neeq.com.cn"+x["destFilePath"]} for x in hits]
            slot_rows.append({"security_id":"BJ:"+code,"stock_name":expected,"old_neeq_code":old,"slot_id":target_row["slot_id"],
              "prior_status":target_row["status"],"lookup_result":"OFFICIAL_FULL_REPORT_LINK_FOUND" if hits else "NO_FULL_REPORT_IN_COMPLETE_INDEX",
              "candidate_count":len(hits),"candidates":hitdata,"collection_status_changed":False})
        (OUT/"neeq_indexes.json").write_text(json.dumps(all_results,ensure_ascii=False,indent=2),encoding="utf-8")
        (OUT/"historical_code_mapping.json").write_text(json.dumps(mapping,ensure_ascii=False,indent=2),encoding="utf-8")
        (OUT/"slot_lookup.json").write_text(json.dumps(slot_rows,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps({"code":code,"old_code":old,"index_total":total,"identity":verdict,"target_slots":len([x for x in slot_rows if x["security_id"]=="BJ:"+code]),
          "linked":len([x for x in slot_rows if x["security_id"]=="BJ:"+code and x["candidate_count"]])},ensure_ascii=True),flush=True)
    print(json.dumps({"companies":len(mapping),"target_slots":len(slot_rows),"linked":sum(bool(x["candidate_count"]) for x in slot_rows)},ensure_ascii=True))
if __name__=="__main__": main()

