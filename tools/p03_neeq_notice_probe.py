import sys,json,re
sys.path.insert(0,"tools")
import p03_neeq_recheck as p
p.records=json.loads((p.OUT/"initial_probes.json").read_text(encoding="utf-8"))
t=p.request("session3","http://www.neeq.com.cn/");m=re.search(r"C3VK=([0-9a-f]+)",t)
h={"Cookie":"C3VK="+m.group(1),"Referer":"https://www.neeq.com.cn/disclosure/announcement.html","X-Requested-With":"XMLHttpRequest"} if m else {}
fields=["companyCd","companyName","disclosureTitle","disclosurePostTitle","destFilePath","publishDate","xxfcbj","fileExt","xxzrlx"]
base={"page":0,"companyCd":"835912","isNewThree":1,"startTime":"2026-01-01","endTime":"2026-10-25","keyword":"","hyType":"","xxfcbj[]":["3"],"needFields[]":fields,"siteId":1}
for label,changes in [
 ("search_notice_bracket",{"noticeType[]":["5"]}),
 ("search_notice_plain",{"noticeType":["5"],"xxfcbj":["3"]}),
 ("search_notice_old",{"noticeType[]":["5"],"companyCd":"874468","startTime":"2023-01-01"}),
 ("search_types_old",{"noticeType[]":["9503"],"disclosureType[]":["9503"],"companyCd":"874468","startTime":"2023-01-01"})]:
    params=dict(base);params.update(changes)
    txt=p.request(label,"https://www.neeq.com.cn/disclosureInfoController/companyAnnouncement.do",params,h)
    print(label,"BODY_PREFIX",txt[:350].encode("unicode_escape").decode(),flush=True)

