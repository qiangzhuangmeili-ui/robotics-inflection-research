"""按关键词检索巨潮公告标题（用于找收购/处置公告，公告里通常带标的公司财务数据）。"""
import json
import sys
import urllib.parse
import urllib.request

UA = {'User-Agent': 'Mozilla/5.0',
      'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
      'Referer': 'http://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice'}


def query(code, org, searchkey, se, cat=''):
    data = urllib.parse.urlencode({
        'pageNum': 1, 'pageSize': 30, 'column': 'szse', 'tabName': 'fulltext', 'plate': '',
        'stock': f'{code},{org}', 'searchkey': searchkey, 'secid': '', 'category': cat,
        'trade': '', 'seDate': se, 'sortName': '', 'sortType': '', 'isHLtitle': 'true'}).encode()
    req = urllib.request.Request('http://www.cninfo.com.cn/new/hisAnnouncement/query',
                                 data=data, headers=UA)
    return json.load(urllib.request.urlopen(req, timeout=30))


if __name__ == '__main__':
    code, org, key = sys.argv[1], sys.argv[2], sys.argv[3]
    se = sys.argv[4] if len(sys.argv) > 4 else '2025-01-01~2026-12-31'
    d = query(code, org, key, se)
    print('total', d.get('totalAnnouncement'))
    for a in d.get('announcements') or []:
        print(a['announcementTitle'], '|', a['adjunctUrl'])
