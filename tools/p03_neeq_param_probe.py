import sys,json,re
sys.path.insert(0,"tools")
import p03_neeq_recheck as p
p.records=json.loads((p.OUT/"initial_probes.json").read_text(encoding="utf-8"))
t=p.request("session2","http://www.neeq.com.cn/");m=re.search(r"C3VK=([0-9a-f]+)",t)
h={"Cookie":"C3VK="+m.group(1),"Referer":"https://www.neeq.com.cn/disclosure/announcement.html","X-Requested-With":"XMLHttpRequest"} if m else {}
p.request("disclosure_types","https://www.neeq.com.cn/disclosureInfoController/disclosure_type.do?type=1",headers=h)
fields=["companyCd","companyName","disclosureTitle","disclosurePostTitle","destFilePath","publishDate","xxfcbj","fileExt","xxzrlx"]
base={"disclosureType":"","page":0,"companyCd":"","isNewThree":1,"startTime":"2026-01-01","endTime":"2026-10-25","keyword":"","hyType":"","xxfcbj[]":["3"],"needFields[]":fields,"siteId":1}
for label,endpoint,changes in [
 ("init_brackets","initDisclosureList.do",{}),
 ("search_brackets","companyAnnouncement.do",{}),
 ("old_company_brackets","companyAnnouncement.do",{"companyCd":"874468","startTime":"2023-01-01"}),
 ("init_old_company","initDisclosureList.do",{"companyCd":"874468","startTime":"2023-01-01"})]:
    params=dict(base);params.update(changes)
    txt=p.request(label,"https://www.neeq.com.cn/disclosureInfoController/"+endpoint,params,h)
    print(label,"BODY_PREFIX",txt[:300].encode("unicode_escape").decode(),flush=True)

