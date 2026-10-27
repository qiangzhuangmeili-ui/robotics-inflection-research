"""Read-only PDF identity/listing evidence for the 15 scoped historical issuers."""
from pathlib import Path
import sys,json,re,hashlib,urllib.request,time
from datetime import datetime,timezone
from pypdf import PdfReader
sys.path.insert(0,str(Path(__file__).resolve().parent))
import p03_neeq_recheck as p
from p03_neeq_inventory import slot_of
OUT=p.OUT; BASE=p.ROOT/"sources/collection/p03_neeq_samples";BASE.mkdir(parents=True,exist_ok=True)
p.records=json.loads((OUT/"initial_probes.json").read_text(encoding="utf-8"))
t=p.request("session_pdf","http://www.neeq.com.cn/");m=re.search(r"C3VK=([0-9a-f]+)",t)
headers=dict(p.UA,Referer="https://www.neeq.com.cn/disclosure/announcement.html")
if m:headers["Cookie"]="C3VK="+m.group(1)
idx=json.loads((OUT/"neeq_indexes.json").read_text(encoding="utf-8"))
results=[]
consecutive_failures=0
for company in idx:
    candidates=[x for x in company["rows"] if (slot_of(x["disclosureTitle"]) or "").startswith("annual_") and "摘要" not in x["disclosureTitle"] and "已取消" not in x.get("disclosurePostTitle","")]
    if not candidates:candidates=[x for x in company["rows"] if "摘要" not in x["disclosureTitle"] and "已取消" not in x.get("disclosurePostTitle","")]
    selected=sorted(candidates,key=lambda x:x["publishDate"],reverse=True)[0]
    url="https://www.neeq.com.cn"+selected["destFilePath"]
    folder=BASE/company["old_neeq_code"];folder.mkdir(exist_ok=True)
    pdf=folder/(hashlib.sha256(url.encode()).hexdigest()[:16]+".pdf")
    if not pdf.exists() and consecutive_failures>=3:
        results.append({"security_id":"BJ:"+company["stock_code"],"official_pdf_url":url,"download_error":"CIRCUIT_OPEN_AFTER_THREE_CONSECUTIVE_FILE_FAILURES"})
        continue
    if not pdf.exists():
        failure=None
        for actual_url in [url,url.replace("www.neeq.com.cn","www.neeq.cc")]:
            try:
                time.sleep(1.2)
                with p.op.open(urllib.request.Request(actual_url,headers=headers),timeout=30) as resp:
                    b=resp.read(125829121)
                    if len(b)>125829120:raise RuntimeError("SIZE_OVER_LIMIT")
                    if not b.startswith(b"%PDF-"):raise RuntimeError("NOT_PDF "+actual_url)
                pdf.write_bytes(b);break
            except Exception as exc: failure=type(exc).__name__+": "+str(exc)
        if not pdf.exists():
            consecutive_failures+=1
            results.append({"security_id":"BJ:"+company["stock_code"],"old_neeq_code":company["old_neeq_code"],"official_pdf_url":url,"download_error":failure})
            (OUT/"sample_pdf_checks.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
            print(json.dumps(results[-1],ensure_ascii=True),flush=True);continue
    consecutive_failures=0
    reader=PdfReader(pdf)
    texts=[(i+1,page.extract_text() or "") for i,page in enumerate(reader.pages[:12])]
    compact="".join(re.sub(r"\s+","",t) for _,t in texts)
    listing=[]
    for page,text in texts:
        tx=re.sub(r"\s+","",text)
        for match in re.finditer(r"挂牌(?:时间|日期)[：:]?(.{0,45}?)(20\d{2})年(\d{1,2})月(\d{1,2})日",tx):
            y,mo,d=match.group(2,3,4)
            listing.append({"physical_page":page,"date":f"{int(y):04d}-{int(mo):02d}-{int(d):02d}","quote":match.group(0)})
    rec={"security_id":"BJ:"+company["stock_code"],"stock_name":company["stock_name"],"old_neeq_code":company["old_neeq_code"],
         "official_pdf_url":url,"title":selected["disclosureTitle"],"published_on":selected["publishDate"],
         "local_file":pdf.relative_to(p.ROOT).as_posix(),"bytes":pdf.stat().st_size,"sha256":hashlib.sha256(pdf.read_bytes()).hexdigest(),
         "pages":len(reader.pages),"text_pages_checked":len(texts),
         "name_in_text":company["stock_name"] in compact,"old_code_in_text":company["old_neeq_code"] in compact,
         "listing_evidence":listing,"read_at":datetime.now(timezone.utc).isoformat(),"scope":"identity, codes and listing chronology only; no business or financial adoption"}
    (folder/"identity_excerpt.txt").write_text("\n\n".join("PHYSICAL_PAGE "+str(pg)+"\n"+text for pg,text in texts),encoding="utf-8")
    results.append(rec)
    (OUT/"sample_pdf_checks.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:rec[k] for k in ["security_id","old_neeq_code","bytes","pages","name_in_text","old_code_in_text","listing_evidence"]},ensure_ascii=True),flush=True)

(OUT/"sample_pdf_checks.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")


