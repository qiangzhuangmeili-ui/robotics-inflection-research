import sys,json,re
sys.path.insert(0,"tools")
import p03_neeq_recheck as p
from p03_neeq_inventory import params,parse_response,CODES,slot_of
p.records=json.loads((p.OUT/"initial_probes.json").read_text(encoding="utf-8"))
t=p.request("session_isolation","http://www.neeq.com.cn/");m=re.search(r"C3VK=([0-9a-f]+)",t)
h={"Referer":"https://www.neeq.com.cn/disclosure/announcement.html","X-Requested-With":"XMLHttpRequest"}
if m:h["Cookie"]="C3VK="+m.group(1)
out=[]
for field in ["disclosureType","xxfcbj","needFields"]:
    body=params("874468");body[field]=body.pop(field+"[]")
    txt=p.request("isolate_"+field,"https://www.neeq.com.cn/disclosureInfoController/companyAnnouncement.do",body,h)
    o=parse_response(txt);out.append({"changed_array_field_to_plain":field,"total":o["totalElements"]})
    (p.OUT/"serialization_isolation.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
for code in ["920022","920096","920211","920220","920238"]:
    body=params(CODES[code]);body["disclosureType[]"]=["9503","9504"];body["noticeType[]"]=["9503","9504"];body["keyword"]="季度";body["startTime"]="2026-01-01"
    txt=p.request("quarter_broad_"+CODES[code],"https://www.neeq.com.cn/disclosureInfoController/companyAnnouncement.do",body,h)
    o=parse_response(txt)
    if len(o["content"])!=int(o["totalElements"]):raise RuntimeError("PAGINATION_NEEDED")
    out.append({"security_id":"BJ:"+code,"old_code":CODES[code],"total":o["totalElements"],"rows":o["content"],
        "q1_hits":[x for x in o["content"] if slot_of(x["disclosureTitle"])=="q1_2026"]})
    (p.OUT/"serialization_and_quarter_fallback.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"code":code,"total":o["totalElements"],"q1_hits":len(out[-1]["q1_hits"])},ensure_ascii=True),flush=True)

