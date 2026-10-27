"""Scoped P03 public-source recheck; preserves original P03/A01 artifacts."""
import json, re, time, hashlib, argparse, urllib.request, urllib.parse, http.cookiejar
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"runs/issues/P03/neeq_recheck_20261027"; RAW=ROOT/"sources/p03_neeq_recheck_20261027"
OUT.mkdir(parents=True,exist_ok=True); RAW.mkdir(parents=True,exist_ok=True)
UA={"User-Agent":"Mozilla/5.0","Accept-Language":"zh-CN,zh;q=0.9"}
op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
records=[]
def request(label,url,params=None,headers=None):
    time.sleep(1.2); started=datetime.now(timezone.utc).isoformat()
    data=urllib.parse.urlencode(params,doseq=True).encode() if params is not None else None
    h=dict(UA); h.update(headers or {})
    if data is not None:h["Content-Type"]="application/x-www-form-urlencoded; charset=UTF-8"
    req=urllib.request.Request(url,data=data,headers=h)
    rec={"label":label,"url":url,"params":params,"requested_at":started}
    try:
        with op.open(req,timeout=25) as r:
            b=r.read(); rec.update(http_status=r.status,response_url=r.url,bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
        txt=b.decode("utf-8","replace"); (RAW/(label+".txt")).write_text(txt,encoding="utf-8")
        rec["raw_cache"]="sources/p03_neeq_recheck_20261027/"+label+".txt"
        try:
            obj=json.loads(txt);rec["total"]=obj.get("totalAnnouncement") if isinstance(obj,dict) else None
            rows=obj.get("announcements") or [] if isinstance(obj,dict) else []
            rec["sample"]=[{k:x.get(k) for k in ["secCode","secName","announcementTitle","announcementTime","adjunctUrl"]} for x in rows[:3]]
        except ValueError: pass
    except Exception as e: txt="";rec["error"]=type(e).__name__+": "+str(e)
    records.append(rec);(OUT/"initial_probes.json").write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(rec,ensure_ascii=True),flush=True);return txt
def cn(stock,key=""):
    p={"pageNum":1,"pageSize":30,"column":"szse","tabName":"fulltext","plate":"","stock":stock,"searchkey":key,"secid":"","category":"","trade":"","seDate":"2023-01-01~2026-10-25","sortName":"","sortType":"","isHLtitle":"true"}
    return p
if __name__=="__main__":
    request("cn_current","https://www.cninfo.com.cn/new/hisAnnouncement/query",cn("920011,gfbj0874468"),{"Referer":"https://www.cninfo.com.cn/","X-Requested-With":"XMLHttpRequest"})
    request("cn_old","https://www.cninfo.com.cn/new/hisAnnouncement/query",cn("874468,gfbj0874468"),{"Referer":"https://www.cninfo.com.cn/","X-Requested-With":"XMLHttpRequest"})
    request("cn_keyword","https://www.cninfo.com.cn/new/hisAnnouncement/query",cn("","晨光电机"),{"Referer":"https://www.cninfo.com.cn/","X-Requested-With":"XMLHttpRequest"})
    txt=request("neeq_home","http://www.neeq.com.cn/")
    m=re.search(r"C3VK=([0-9a-f]+)",txt)
    hdr={"Cookie":"C3VK="+m.group(1)} if m else {}
    if m: request("neeq_home_session","http://www.neeq.com.cn/",headers=hdr)
    html=request("neeq_announcement","http://www.neeq.com.cn/disclosure/announcement.html",headers=hdr)
    scripts=re.findall(r'<script[^>]+src=["\x27]([^"\x27]+)',html)
    (OUT/"script_refs.json").write_text(json.dumps(scripts,ensure_ascii=False,indent=2),encoding="utf-8")
    print("SCRIPT_REFS",json.dumps(scripts),flush=True)

