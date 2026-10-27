import sys,json,re
sys.path.insert(0,"tools")
import p03_neeq_recheck as p
from p03_neeq_inventory import params,parse_response,CODES,slot_of
p.records=json.loads((p.OUT/"initial_probes.json").read_text(encoding="utf-8"))
t=p.request("session_quarter","http://www.neeq.com.cn/");m=re.search(r"C3VK=([0-9a-f]+)",t)
h={"Referer":"https://www.neeq.com.cn/disclosure/announcement.html","X-Requested-With":"XMLHttpRequest"}
if m:h["Cookie"]="C3VK="+m.group(1)
out=[]
for label,body in [
    ("type9503_without_notice",{k:v for k,v in params("874468").items() if k!="noticeType[]"}),
    ("type9503_plain",{("xxfcbj" if k=="xxfcbj[]" else "needFields" if k=="needFields[]" else "disclosureType" if k=="disclosureType[]" else "noticeType" if k=="noticeType[]" else k):v for k,v in params("874468").items()})]:
    txt=p.request(label,"https://www.neeq.com.cn/disclosureInfoController/companyAnnouncement.do",body,h)
    o=parse_response(txt);out.append({"label":label,"total":o["totalElements"]})
for code in ["920022","920096","920211","920220","920238"]:
    body=params(CODES[code]);body.pop("disclosureType[]");body["noticeType[]"]=["9503-1003","9504-8001"];body["disclosureSubtype[]"]=["9503-1003","9504-8001"]
    body["startTime"]="2026-01-01"
    txt=p.request("quarter_"+CODES[code],"https://www.neeq.com.cn/disclosureInfoController/companyAnnouncement.do",body,h)
    o=parse_response(txt)
    if int(o["totalElements"])!=len(o["content"]):raise RuntimeError("Quarter pagination required")
    out.append({"security_id":"BJ:"+code,"old_code":CODES[code],"total":o["totalElements"],"rows":o["content"],
       "q1_hits":[x for x in o["content"] if slot_of(x["disclosureTitle"])=="q1_2026"]})
    (p.OUT/"quarter_and_parameter_controls.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"code":code,"total":o["totalElements"],"q1_hits":len(out[-1]["q1_hits"])},ensure_ascii=True),flush=True)

