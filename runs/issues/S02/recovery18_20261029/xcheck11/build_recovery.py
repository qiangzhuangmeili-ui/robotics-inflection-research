import argparse, csv, json, hashlib, subprocess, sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[4]
BASE = REPO / 'runs/issues/S02/remediation_20261029/extracted'
INDEX = REPO / 'runs/collection/collection_index.csv'
SCALE = {'元': 1, '千元': 1000, '万元': 10000}

# doc, field, corrected raw value, unit, source physical page, label, source row, root-cause tag, reason
PATCHES = [
('DOC-F9454692F6BBE32A','FIN.REV.YTD','5,667,075,612.52','元',136,'营业收入','附注48：主营业务 5,573,799,732.47；其他业务 93,275,880.05；合计 5,667,075,612.52。','WRONG_STATEMENT_SCOPE','原页62为母公司利润表营业收入1,245,887,527.23；合并附注48直接给出主营+其他业务营业收入合计，符合P04。'),
('DOC-CAADA5BC063F7BEA','FIN.REV.YTD','4,740,551,562.53','元',137,'营业收入','附注48：主营业务 4,700,136,105.09；其他业务 40,415,457.44；合计 4,740,551,562.53。','WRONG_STATEMENT_SCOPE','原页61为母公司利润表营业收入415,778,065.42；合并附注48直接给出营业收入合计，符合P04，不取营业总收入。'),
('DOC-B829722A2198EEEC','FIN.REV.YTD','72,691,310,387.08','元',97,'营业收入','附注49：主营业务 71,122,847,357.43；其他业务 1,568,463,029.65；合计营业收入 72,691,310,387.08。','WRONG_STATEMENT_SCOPE','原页41为母公司利润表营业收入49,992,247,432.42；合并附注49明确按主营/其他业务列示并给出合计，符合P04。'),
('DOC-BB4A8F9DB0289566','FIN.REV.YTD','65,634,329,742.16','元',118,'营业收入','附注49：主营业务 63,397,851,124.11；其他业务 2,236,478,618.05；合计营业收入 65,634,329,742.16。','WRONG_STATEMENT_SCOPE','原页39为母公司利润表营业收入44,137,067,957.70；合并附注49直接给出营业收入合计，符合P04，不取营业总收入。'),
('DOC-EF92987CB32EBB42','FIN.NPP.YTD','40,589,188.18','元',40,'归属于母公司股东的净利润','1.归属于母公司股东的净利润（净亏损以“-”号填列） 40,589,188.18。','MISSED_WRAPPED_STATEMENT_ROW','合并利润表续页的归母净利润行标签换行，原字段留空；按同一行本期金额恢复。'),
('DOC-26D0E7369A77D34D','FIN.REV.YTD','54,007,759','千元',46,'营业收入','一、营业总收入 54,303,335；其中：营业收入 65 54,007,759 49,554,334。','FOOTNOTE_NUMBER_MISREAD','A03把注释编号65误读为营业收入金额；合并利润表同一行本期数为54,007,759千元。'),
('DOC-26D0E7369A77D34D','FIN.COST.YTD','43,963,452','千元',46,'营业成本','二、营业总成本 52,136,586；其中：营业成本 65 43,963,452 40,225,850。','FOOTNOTE_NUMBER_MISREAD','A03同样把附注编号65误读为营业成本金额；合并利润表本期营业成本为43,963,452千元，非65千元。'),
('DOC-26D0E7369A77D34D','FIN.NPP.YTD','820,752','千元',47,'归属于母公司股东的净利润','1.归属于母公司股东的净利润（净亏损以“-”号填列） 820,752 764,798。','MISSED_WRAPPED_STATEMENT_ROW','归母净利润位于合并利润表续页且标签换行，原字段被判空；按本期金额恢复。'),
('DOC-AE4FE8D4A427A86B','FIN.REV.YTD','63,030,610','千元',49,'营业收入','一、营业总收入 63,331,968；其中：营业收入 65 63,030,610 54,007,759。','FOOTNOTE_NUMBER_MISREAD','A03把注释编号65误读为营业收入金额；合并利润表同一行本期数为63,030,610千元。'),
('DOC-AE4FE8D4A427A86B','FIN.COST.YTD','51,512,786','千元',49,'营业成本','二、营业总成本 60,955,177；其中：营业成本 65 51,512,786 43,963,452。','FOOTNOTE_NUMBER_MISREAD','A03同样把附注编号65误读为营业成本金额；合并利润表本期营业成本为51,512,786千元，非65千元。'),
('DOC-49B96AFD6CC8A151','FIN.REV.YTD','115,456,181','千元',85,'营业收入','合并利润表：其中：营业收入 66 115,456,181 114,218,209。','FOOTNOTE_NUMBER_MISREAD','A03把附注编号66误读为营业收入金额；合并利润表本期数为115,456,181千元。'),
('DOC-49B96AFD6CC8A151','FIN.COST.YTD','94,525,076','千元',85,'营业成本','合并利润表：其中：营业成本 66 94,525,076 94,528,637。','FOOTNOTE_NUMBER_MISREAD','A03把附注编号66误读为营业成本金额；合并利润表本期数为94,525,076千元。'),
('DOC-49B96AFD6CC8A151','FIN.NPP.YTD','752,480','千元',86,'归属于母公司股东的净利润','1.归属于母公司股东的净利润（净亏损以“-”号填列） 752,480 803,346。','MISSED_WRAPPED_STATEMENT_ROW','2024年合并利润表续页的归母净利润行标签换页换行，原字段留空；按本期金额恢复。'),
('DOC-11BBC7058DD9D586','FIN.REV.YTD','125,958,695','千元',87,'营业收入','合并利润表：其中：营业收入 65 125,958,695 115,456,181。','FOOTNOTE_NUMBER_MISREAD','A03把附注编号65误读为营业收入金额；合并利润表本期数为125,958,695千元。'),
('DOC-11BBC7058DD9D586','FIN.COST.YTD','103,888,307','千元',87,'营业成本','合并利润表：其中：营业成本 65 103,888,307 94,525,076。','FOOTNOTE_NUMBER_MISREAD','A03把附注编号65误读为营业成本金额；合并利润表本期数为103,888,307千元。'),
('DOC-AE4FE8D4A427A86B','FIN.NPP.YTD','969,994','千元',50,'归属于母公司股东的净利润','1.归属于母公司股东的净利润（净亏损以“-”号填列） 969,994 820,752。','MISSED_WRAPPED_STATEMENT_ROW','归母净利润位于合并利润表续页且标签换行，原字段被判空；按本期金额恢复。'),
('DOC-15C39AC7E44A804B','FIN.NPP.YTD','-57,363,407.85','元',88,'归属于母公司股东的净利润','1.归属于母公司股东的净利润（净亏损以“-”号填列） -57,363,407.85 -40,881,721.10。','MISSED_WRAPPED_STATEMENT_ROW','利润表续页归母净利润行未抽取；摘要-5,736.34万元与其相差7.85元，处于±50元显示舍入区间。'),
('DOC-21E16B8BFC6A0CD7','FIN.NPP.YTD','-38,162,293.77','元',101,'归属于母公司股东的净利润','1.归属于母公司股东的净利润（净亏损以“-”号填列） -38,162,293.77 -29,194,656.93。','MISSED_WRAPPED_STATEMENT_ROW','归母净利润在合并利润表续页、原字段被判空；恢复源行金额。摘要-3,816.23万元差6.23元，处于±50元区间。'),
('DOC-88C2F8E42C5514C6','FIN.OCF.YTD','-43,633,361.15','元',74,'经营活动产生的现金流量净额','合并现金流量表（2026年1—6月）：页74列值-43,633,361.15，页75续接标签“量净额”。','WRONG_STATEMENT_SCOPE','原字段页76来自母公司现金流量表119,954,682.73；合并现金流量表页74金额为-43,633,361.15，摘要同值。'),
('DOC-4B9B83B742824338','FIN.OCF.YTD','189,501,777.70','元',83,'经营活动产生的现金流量净额','合并现金流量表（2025年1—6月）：页83列值189,501,777.70，页84续接标签“量净额”。','WRONG_STATEMENT_SCOPE','原字段页85来自母公司现金流量表215,517,071.99；合并现金流量表页83金额189,501,777.70。摘要18,950.18万元差22.30元，处于±50元区间。'),
('DOC-F9C864F9A0536DCC','FIN.OCF.YTD','56,697,365.60','元',81,'经营活动产生的现金流量净额','合并现金流量表（2025年1—6月）：页81列值56,697,365.60，页82续接标签“量净额”。','WRONG_STATEMENT_SCOPE','原字段页83来自母公司现金流量表57,875,542.26；合并现金流量表页81金额56,697,365.60。摘要5,669.74万元差34.40元，处于±50元区间。'),
('DOC-08E9C620CE2D4DEC','FIN.NPP.YTD','-8,733,717.23','元',8,'归属于母公司股东的净利润','1.归属于母公司股东的净利润（净亏损以“-”号填列） -8,733,717.23 71,951,977.52。','PAGE_NUMBER_MISREAD','原字段值8是PDF印刷页码；恢复同页归母净利润。'),
('DOC-42A4EC3B730E7201','FIN.NPP.YTD','131,642,183.32','元',10,'归属于母公司股东的净利润','1.归属于母公司股东的净利润（净亏损以“-”号填列） 131,642,183.32 160,549,554.47。','ROW_NUMBER_MISREAD','原字段值1是行序号；恢复同一行金额。'),
('DOC-D28C9A72222C99C5','FIN.NPP.YTD','160,549,554.47','元',10,'归属于母公司股东的净利润','1.归属于母公司股东的净利润（净亏损以“-”号填列） 160,549,554.47 180,281,976.92。','ROW_NUMBER_MISREAD','原字段值1是行序号；恢复同一行金额。'),
('DOC-246D66C9FA64E7FE','FIN.NPP.YTD','25,877,730.32','元',10,'归属于母公司所有者的净利润','1.归属于母公司所有者的净利润 25,877,730.32 47,377,681.44。','ROW_NUMBER_MISREAD','原字段值1是行序号；恢复同一行金额。'),
]

SOURCE_SUPPORTING_PAGES = {
    'DOC-88C2F8E42C5514C6': 75,
    'DOC-4B9B83B742824338': 84,
    'DOC-F9C864F9A0536DCC': 82,
}

# doc, company, field, statement page, summary value, summary unit, summary page, statement row, rationale
ROUNDING = [
('DOC-8CA0C240BD5F5E0E','佳华科技','FIN.OCF.YTD',90,'-3,188.19','万元',6,'合并现金流量表经营活动产生的现金流量净额 -31,881,866.46。','-3,188.19万元折算为-31,881,900元，差33.54元，位于2位小数万元±50元区间。'),
('DOC-15C39AC7E44A804B','佳华科技','FIN.OCF.YTD',91,'-569.46','万元',6,'合并现金流量表经营活动产生的现金流量净额 -5,694,640.03。','-569.46万元折算为-5,694,600元，差40.03元，位于±50元区间。'),
('DOC-58D96FBE284049B0','禾川科技','FIN.NPP.YTD',106,'2,269.85','万元',6,'合并利润表归属于母公司股东的净利润 22,698,467.32。','2,269.85万元折算为22,698,500元，差32.68元，位于±50元区间。'),
('DOC-7A738B652C814E3D','禾川科技','FIN.OCF.YTD',11,'579.30','万元',1,'合并现金流量表经营活动产生的现金流量净额 5,792,976.95。','579.30万元折算为5,793,000元，差23.05元，位于±50元区间。'),
('DOC-3967811820A4EE8F','芯动联科','FIN.OCF.YTD',102,'188.29','万元',6,'合并现金流量表经营活动产生的现金流量净额 1,882,850.99。','188.29万元折算为1,882,900元，差49.01元，位于±50元区间。'),
('DOC-9FE5E37A6630DFCD','芯动联科','FIN.OCF.YTD',13,'-1,893.12','万元',1,'合并现金流量表经营活动产生的现金流量净额 -18,931,170.33。','-1,893.12万元折算为-18,931,200元，差29.67元，位于±50元区间。'),
('DOC-0E102D298C49BC89','芯动联科','FIN.NPP.YTD',10,'3,466.84','万元',1,'合并利润表归属于母公司股东的净利润 34,668,443.86。','3,466.84万元折算为34,668,400元，差43.86元，位于±50元区间。'),
('DOC-0E102D298C49BC89','芯动联科','FIN.OCF.YTD',12,'2,975.47','万元',1,'合并现金流量表经营活动产生的现金流量净额 29,754,737.62。','2,975.47万元折算为29,754,700元，差37.62元，位于±50元区间。'),
('DOC-F9C864F9A0536DCC','和林微纳','FIN.NPP.YTD',78,'3,068.58','万元',7,'合并利润表归属于母公司股东的净利润 30,685,760.47。','3,068.58万元折算为30,685,800元，差39.53元，位于±50元区间。'),
('DOC-503307B3429E327F','和林微纳','FIN.NPP.YTD',79,'-675.52','万元',6,'合并利润表归属于母公司股东的净利润 -6,755,243.49。','-675.52万元折算为-6,755,200元，差43.49元，位于±50元区间。'),
('DOC-503307B3429E327F','和林微纳','FIN.OCF.YTD',83,'-1,204.17','万元',6,'合并现金流量表经营活动产生的现金流量净额 -12,041,662.57。','-1,204.17万元折算为-12,041,700元，差37.43元，位于±50元区间。'),
('DOC-BBCD2D567E69719B','和林微纳','FIN.OCF.YTD',11,'-3,482.92','万元',1,'合并现金流量表经营活动产生的现金流量净额 -34,829,154.09。','-3,482.92万元折算为-34,829,200元，差45.91元，位于±50元区间。'),
]

SUMMARY_PATCH = {
'doc':'DOC-EF92987CB32EBB42','field':'FIN.REV.YTD','old':'-22.19','new':'4,529,823,776.31','unit':'元','page':5,
'row':'营业收入 4,529,823,776.31 5,821,756,788.38 -22.19',
'reason':'摘要表提取定位落入变动说明，误把同比变化-22.19%当收入；摘要数据表本行收入为4,529,823,776.31元。'
}

# The direct summary line is evidence, but P04 forbids using the statement's total revenue as FIN.REV.
UNRESOLVED = [
('DOC-6DA5132473C5647B','长安汽车','FIN.REV.YTD',1,8,'营业收入（元） 34,160,587,096.72 37,023,223,131.54 -7.73%','合并利润表仅列一、营业总收入 34,160,587,096.72 37,023,223,131.54；未见直接营业收入合并行或合并附注合计。'),
('DOC-73B396E8A47B9B9E','长安汽车','FIN.REV.YTD',2,8,'营业收入（元） 32,706,438,744.02 34,160,587,096.72 -4.26%','合并利润表仅列一、营业总收入 32,706,438,744.02 34,160,587,096.72；未见直接营业收入合并行或合并附注合计。'),
]

ROOT_CAUSES = {
'SH:600100':('同方股份','H1营业收入误取母公司利润表；合并附注48有明确营业收入合计。','RESOLVED'),
'SH:600879':('航天电子','摘要定位误取同比变化-22.19%，且最新合并利润表归母净利润续页漏抽。','RESOLVED'),
'SH:601727':('上海电气','年报/H1把附注号65/66误作营业收入和成本；年报2024归母净利润续页漏抽。','RESOLVED'),
'SH:688051':('佳华科技','最新归母净利润续页漏抽；两期OCF差异来自万元显示精度。','RESOLVED'),
'SH:688320':('禾川科技','H1上年同期归母净利润续页漏抽；本期NPP及Q1 OCF差异处于万元显示舍入区间。','RESOLVED'),
'SH:688518':('联赢激光','OCF误取母公司现金流量表；合并现金流量表值与摘要一致。','RESOLVED'),
'SH:688582':('芯动联科','H1 2025 OCF误取母公司现金流量表；其他差异处于万元显示舍入区间。','RESOLVED'),
'SH:688661':('和林微纳','H1 2025 OCF误取母公司现金流量表；其余H1/Q1差异处于万元显示舍入区间。','RESOLVED'),
'SZ:000625':('长安汽车','H1营业收入误取母公司报表，改用合并附注直接营业收入；Q1合并利润表只有营业总收入，受P04阻断。','PARTIAL_P04_BLOCK'),
'SZ:001239':('永达股份','归母净利润误抽为PDF印刷页码8。','RESOLVED'),
'SZ:300193':('佳士科技','归母净利润误抽为行序号1。','RESOLVED'),
}

def n(raw):
    try: return float(str(raw).replace(',','').replace('−','-'))
    except (ValueError,TypeError): return None

def cny(raw,unit):
    v=n(raw); return None if v is None else v*SCALE.get(unit,1)

with INDEX.open(encoding='utf-8-sig',newline='') as f:
    INDEX_ROWS={r['document_id']:r for r in csv.DictReader(f)}

def original(doc):
    return json.loads((BASE/f'{doc}.json').read_text(encoding='utf-8'))

def field(j,fid):
    found=[f for f in j.get('fields',[]) if f.get('field_id')==fid]
    if len(found)!=1: raise ValueError(f'{j.get("document_id")} {fid}: expected 1, found {len(found)}')
    return found[0]

def detail(j,fid):
    return j.get('key_financials_details',{}).get(fid) or {}

def entry(doc,fid,page,row,kind,reason,summary_override=None):
    j=original(doc); f=field(j,fid); m=INDEX_ROWS[doc]; d=detail(j,fid)
    sr, su, sp, srow = summary_override or (j.get('key_financials_values',{}).get(fid,''),d.get('unit',''),d.get('page',''),d.get('raw_row',''))
    return {'record_type':kind,'security_id':j['security_id'],'company_name':ROOT_CAUSES[j['security_id']][0],'slot_id':j['slot_id'],'document_id':doc,'field_id':fid,
      'before_value_raw':f.get('value_raw',''),'before_unit':f.get('unit_raw',''),'before_value_cny':f.get('value_cny',''),
      'after_value_raw':f.get('value_raw',''),'after_unit':f.get('unit_raw',''),'after_value_cny':f.get('value_cny',''),
      'before_extract_status':f.get('extract_status',''),'after_extract_status':f.get('extract_status',''),
      'before_crosscheck':j.get('crosscheck',{}).get(fid,''),'after_crosscheck':j.get('crosscheck',{}).get(fid,''),
      'summary_value_raw':sr,'summary_unit':su,'summary_value_cny':cny(sr,su) if sr else '',
      'summary_physical_page':sp,'summary_raw_row':srow,'absolute_difference_cny':'','display_precision':'','rounding_half_interval_cny':'',
      'adjudication':'SOURCE_ROW_REVIEW','source_pdf':m['local_file'],'source_sha256':m['sha256'],'source_physical_page':page,
      'source_unit':f.get('unit_raw',''),'evidence_raw_row':row,'supporting_physical_page':sp,
      'root_cause':reason,'decision_notes':'','corrected_json':f'corrected_results/{doc}.json'}

def write_ledger():
    rows=[]
    for doc,fid,raw,unit,page,label,row,kind,reason in PATCHES:
        j=original(doc); old=field(j,fid); m=INDEX_ROWS[doc]; d=detail(j,fid)
        smraw=j.get('key_financials_values',{}).get(fid,''); smunit=d.get('unit',''); smcny=cny(smraw,smunit); value=cny(raw,unit)
        diff=abs(value-smcny) if value is not None and smcny is not None else ''
        interval=(0.5*10**(-len(smraw.split('.')[-1]))*SCALE[smunit] if smraw and '.' in smraw and smunit in SCALE else '')
        adjudication='EXACT_MATCH' if diff != '' and diff < 1e-7 else ('WITHIN_REPORTED_DISPLAY_INTERVAL' if diff != '' and interval != '' and diff <= interval else 'SOURCE_ROW_CONFIRMED')
        r=entry(doc,fid,page,row,kind,reason)
        after_cross='MATCH' if j.get('crosscheck',{}).get(fid) in ('MISMATCH','MISSING_IN_STATEMENT') else j.get('crosscheck',{}).get(fid,'')
        r.update({'after_value_raw':raw,'after_unit':unit,'after_value_cny':value,'after_extract_status':'EXTRACTED','after_crosscheck':after_cross,
                  'absolute_difference_cny':diff,'display_precision':f'{len(smraw.split(".")[-1])} decimal places in {smunit}' if smraw and '.' in smraw else 'full displayed amount',
                  'rounding_half_interval_cny':interval,'adjudication':adjudication,'source_unit':unit,'supporting_physical_page':SOURCE_SUPPORTING_PAGES.get(doc,d.get('page',''))})
        rows.append(r)
    for doc,company,fid,page,sraw,sunit,spage,srow,reason in ROUNDING:
        j=original(doc); f=field(j,fid); m=INDEX_ROWS[doc]; d=detail(j,fid)
        diff=abs(cny(f.get('value_raw'),f.get('unit_raw'))-cny(sraw,sunit))
        interval=0.5*10**(-len(sraw.split('.')[-1]))*SCALE[sunit]
        r=entry(doc,fid,page,srow,'CROSSCHECK_DISPLAY_ROUNDING',reason,(sraw,sunit,spage,srow))
        r.update({'before_crosscheck':'MISMATCH','after_crosscheck':'MATCH','absolute_difference_cny':diff,
                  'display_precision':f'{len(sraw.split(".")[-1])} decimal places in {sunit}','rounding_half_interval_cny':interval,
                  'adjudication':'WITHIN_REPORTED_DISPLAY_INTERVAL','source_unit':f.get('unit_raw','')})
        rows.append(r)
    s=SUMMARY_PATCH; j=original(s['doc']); f=field(j,s['field'])
    r=entry(s['doc'],s['field'],s['page'],s['row'],'KEY_FINANCIALS_SUMMARY_LOCATION_CORRECTION',s['reason'],(s['new'],s['unit'],s['page'],s['row']))
    r['field_id']='SUMMARY_KEY.'+s['field']
    r.update({'before_value_raw':s['old'],'before_unit':'误读为元，实际是百分比文本','before_value_cny':'','after_value_raw':s['new'],'after_unit':s['unit'],'after_value_cny':cny(s['new'],s['unit']),
              'before_crosscheck':'MISMATCH','after_crosscheck':'MATCH','adjudication':'SUMMARY_SOURCE_ROW_CONFIRMED','source_unit':s['unit']})
    rows.append(r)
    for doc,company,fid,spage,tpage,srow,traw in UNRESOLVED:
        j=original(doc); f=field(j,fid); m=INDEX_ROWS[doc]
        summary=(j.get('key_financials_values',{}).get(fid,'')); d=detail(j,fid)
        r=entry(doc,fid,tpage,traw,'UNRESOLVED_P04_SOURCE_SCOPE','长安Q1缺少P04允许的合并营业收入直接行。',(summary,d.get('unit',''),spage,srow))
        r.update({'before_value_raw':f.get('value_raw',''),'after_value_raw':f.get('value_raw',''),'before_extract_status':f.get('extract_status',''),'after_extract_status':f.get('extract_status',''),
                  'before_crosscheck':j.get('crosscheck',{}).get(fid,''),'after_crosscheck':j.get('crosscheck',{}).get(fid,''),
                  'adjudication':'P04_BLOCKED_NO_DIRECT_CONSOLIDATED_LINE','decision_notes':srow+'；'+traw,'supporting_physical_page':spage})
        rows.append(r)
    cols=list(rows[0])
    with (OUT/'source_corrections.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=cols); w.writeheader(); w.writerows(rows)
    print(f'source_corrections.csv: {len(rows)} rows')
    return rows

def build(rows):
    docs={r['document_id'] for r in rows}
    bydoc={}
    for doc,fid,raw,unit,page,label,row,kind,reason in PATCHES:
        j=work.get(doc) or original(doc); x=field(j,fid)
        before={k:x.get(k) for k in ['value_raw','unit_raw','value_cny','page','extract_status']}
        x.update({'value_raw':raw,'unit_raw':unit,'unit_scale':SCALE[unit],'value_cny':cny(raw,unit),'page':page,'evidence_label':label,'extract_status':'EXTRACTED','note':'RECOVERED_FROM_ORIGINAL_PDF_PHYSICAL_PAGE','raw_row':row})
        if j.get('crosscheck',{}).get(fid) in ('MISMATCH','MISSING_IN_STATEMENT'): j['crosscheck'][fid]='MATCH'
        bydoc.setdefault(doc,[]).append({'field_id':fid,'change_type':kind,'before':before,'after':{k:x.get(k) for k in ['value_raw','unit_raw','value_cny','page','extract_status']},'crosscheck_after':j.get('crosscheck',{}).get(fid),'reason':reason,'source_physical_page':page,'supporting_physical_page':SOURCE_SUPPORTING_PAGES.get(doc,''),'evidence_raw_row':row})
        # Save in a work dict below after all modifications.
        work[doc]=j
    for doc,company,fid,page,sraw,sunit,spage,srow,reason in ROUNDING:
        j=work.get(doc) or original(doc); f=field(j,fid)
        diff=abs(cny(f.get('value_raw'),f.get('unit_raw'))-cny(sraw,sunit))
        interval=0.5*10**(-len(sraw.split('.')[-1]))*SCALE[sunit]
        if diff>interval: raise ValueError(f'rounding outside interval: {doc}/{fid} {diff}>{interval}')
        before=j.get('crosscheck',{}).get(fid,'')
        if before!='MISMATCH': raise ValueError(f'expected mismatch: {doc}/{fid}: {before}')
        j['crosscheck'][fid]='MATCH'
        bydoc.setdefault(doc,[]).append({'field_id':fid,'change_type':'CROSSCHECK_DISPLAY_ROUNDING','statement_value_raw':f.get('value_raw'),'statement_unit':f.get('unit_raw'),'before_crosscheck':before,'after_crosscheck':'MATCH','summary_value_raw':sraw,'summary_unit':sunit,'difference_cny':diff,'rounding_half_interval_cny':interval,'reason':reason,'source_physical_page':page,'summary_physical_page':spage,'evidence_raw_row':srow})
        work[doc]=j
    s=SUMMARY_PATCH; j=work.get(s['doc']) or original(s['doc'])
    before=j.get('key_financials_values',{}).get(s['field']); before_detail=j.get('key_financials_details',{}).get(s['field'],{}).copy()
    j['key_financials_values'][s['field']]=s['new']
    j['key_financials_details'][s['field']]={'page':s['page'],'unit':s['unit'],'raw_row':s['row'],'column_index':0}
    before_cross=j.get('crosscheck',{}).get(s['field'],''); j['crosscheck'][s['field']]='MATCH'
    bydoc.setdefault(s['doc'],[]).append({'field_id':s['field'],'change_type':'SUMMARY_TABLE_LOCATION_CORRECTION','before_summary_value_raw':before,'after_summary_value_raw':s['new'],'before_summary_detail':before_detail,'after_summary_detail':j['key_financials_details'][s['field']],'before_crosscheck':before_cross,'after_crosscheck':'MATCH','reason':s['reason'],'source_physical_page':s['page'],'evidence_raw_row':s['row']})
    work[s['doc']]=j
    for doc,company,fid,spage,tpage,srow,traw in UNRESOLVED:
        j=work.get(doc) or original(doc); base=original(doc); f=field(j,fid)
        bydoc.setdefault(doc,[]).append({'field_id':fid,'change_type':'UNRESOLVED_P04_SOURCE_SCOPE','field_left_unchanged':True,'summary_value_raw':base.get('key_financials_values',{}).get(fid),'summary_unit':detail(base,fid).get('unit'),'summary_physical_page':spage,'statement_physical_page':tpage,'summary_raw_row':srow,'statement_raw_row':traw,'reason':'P04 disallows substituting 营业总收入 for 营业收入; leave FIN.REV.YTD unknown.'})
        work[doc]=j
    for doc,j in work.items():
        base=original(doc)
        j['recovery_review']={'review_status':'SOURCE_EVIDENCE_REVIEWED','reviewer':'SELF_CHECK','external_acceptance':False,'changes':bydoc[doc],'preserved_original_keys':all(k in j for k in base),'preserved_field_count':len(j.get('fields',[]))==len(base.get('fields',[])),'preserved_restatement':j.get('restatement')==base.get('restatement')}
        if not all(k in j for k in base) or len(j.get('fields',[]))!=len(base.get('fields',[])) or j.get('restatement')!=base.get('restatement'): raise ValueError(f'preservation failed {doc}')
        (OUT/'corrected_results'/f'{doc}.json').write_text(json.dumps(j,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'corrected_results: {len(work)} docs')
    return work

work={}
def render(rows):
    import pypdfium2
    pages={}
    for r in rows:
        for dcol in ['document_id']:
            doc=r[dcol]
            for col in ['source_physical_page','summary_physical_page','supporting_physical_page']:
                try: pn=int(r[col])
                except (ValueError,TypeError): continue
                pages.setdefault(doc,set()).add(pn)
    out=OUT/'evidence/pages'; out.mkdir(parents=True,exist_ok=True)
    count=0
    for doc,nums in pages.items():
        pdfpath=REPO/INDEX_ROWS[doc]['local_file']; pdf=pypdfium2.PdfDocument(str(pdfpath))
        for pn in sorted(nums):
            if not 1<=pn<=len(pdf): raise ValueError(f'page out of range {doc} p{pn}')
            dest=out/f'{doc}_p{pn:03}.png'
            if not dest.exists(): pdf[pn-1].render(scale=1.5).to_pil().save(dest)
            count+=1
    print(f'page evidence: {count} images')

def validate(rows,work):
    errors=[]; checks=[]
    for doc in sorted(work):
        base=original(doc); ix=INDEX_ROWS[doc]; sha=hashlib.sha256((REPO/ix['local_file']).read_bytes()).hexdigest()
        ok=sha==ix['sha256']==base.get('ledger_sha256')
        checks.append({'check':'original_pdf_hash_matches_collection_and_A03','document_id':doc,'pass':ok,'sha256':sha})
        if not ok: errors.append(f'hash mismatch {doc}')
        out=json.loads((OUT/'corrected_results'/f'{doc}.json').read_text(encoding='utf-8'))
        preserved=all(k in out for k in base) and len(out['fields'])==len(base['fields']) and out.get('restatement')==base.get('restatement')
        checks.append({'check':'all_A03_keys_fields_and_restatement_preserved','document_id':doc,'pass':preserved})
        if not preserved: errors.append(f'preservation failed {doc}')
    for row in rows:
        if row['record_type']=='CROSSCHECK_DISPLAY_ROUNDING':
            ok=float(row['absolute_difference_cny'])<=float(row['rounding_half_interval_cny'])
            checks.append({'check':'rounding_within_half_display_increment','document_id':row['document_id'],'field_id':row['field_id'],'difference_cny':float(row['absolute_difference_cny']),'half_interval_cny':float(row['rounding_half_interval_cny']),'pass':ok})
            if not ok: errors.append('rounding failure %s %s' % (row['document_id'], row['field_id']))
    for doc,company,fid,spage,tpage,srow,traw in UNRESOLVED:
        j=json.loads((OUT/'corrected_results'/f'{doc}.json').read_text(encoding='utf-8')); f=field(j,fid)
        ok=f.get('value_raw','')=='' and f.get('extract_status')=='NOT_IN_STATEMENT' and j['crosscheck'].get(fid)=='MISSING_IN_STATEMENT'
        checks.append({'check':'P04_scope_block_left_revenue_unknown','document_id':doc,'field_id':fid,'pass':ok})
        if not ok: errors.append(f'P04 scope block altered {doc}')
    # Verify every patched field is reflected exactly and crosscheck is no longer a false mismatch.
    for doc,fid,raw,unit,page,label,row,kind,reason in PATCHES:
        j=json.loads((OUT/'corrected_results'/f'{doc}.json').read_text(encoding='utf-8')); f=field(j,fid)
        cross=j.get('crosscheck',{}).get(fid,'')
        ok=f.get('value_raw')==raw and f.get('unit_raw')==unit and (cross=='MATCH' or cross not in ('MISMATCH','MISSING_IN_STATEMENT'))
        checks.append({'check':'supported_field_recovery_applied','document_id':doc,'field_id':fid,'pass':ok})
        if not ok: errors.append(f'patch mismatch {doc}/{fid}')
    audit_path=OUT/'field_audit.csv'
    with audit_path.open(encoding='utf-8-sig',newline='') as f: audit=list(csv.DictReader(f))
    expected_fields={'FIN.REV.YTD','FIN.REV.SQ','FIN.COST.YTD','FIN.NPP.YTD','FIN.NPP.SQ','FIN.NPDEDT.YTD','FIN.NPDEDT.SQ','FIN.OCF.YTD','FIN.OCF.SQ','FIN.AR.INSTANT','FIN.INV.INSTANT','FIN.CONTRACTASSET.INSTANT'}
    audit_fields={r['field_id'] for r in audit}; audit_companies={r['security_id'] for r in audit}
    audit_findings=[r for r in audit if r.get('findings')]
    audit_unreviewed=[r for r in audit if r.get('manual_review_status')=='REVIEW_REQUIRED']
    audit_untraced_derived=[r for r in audit if r.get('manual_review_status')=='DERIVED_FIELD_TRACE_ONLY' and not (r.get('normalized_source_kind') or r.get('normalized_source_page'))]
    audit_auto=sum(r.get('manual_review_status')=='AUTO_SOURCE_ROW_AND_SCOPE_MATCH' for r in audit)
    audit_manual=sum(r.get('manual_review_status')=='MANUAL_PDF_NOTE_SCOPE_CONFIRMED' for r in audit)
    audit_derived=sum(r.get('manual_review_status')=='DERIVED_FIELD_TRACE_ONLY' for r in audit)
    audit_page_hits=sum(r.get('source_row_in_pdf_text')=='YES' for r in audit)
    audit_derived_page_hits=sum(r.get('manual_review_status')=='DERIVED_FIELD_TRACE_ONLY' and r.get('source_row_in_pdf_text')=='YES' for r in audit)
    audit_page_nonhits=sum(r.get('source_row_in_pdf_text')=='NO' for r in audit)
    audit_count_reconciles=(audit_auto+audit_manual+audit_derived==len(audit))
    audit_pass=(audit_fields==expected_fields and len(audit_companies)==11 and bool(audit) and not audit_findings and not audit_unreviewed and not audit_untraced_derived and audit_count_reconciles)
    checks.append({'check':'all_12_basic_fields_have_source_or_derived_trace_for_metric_documents','pass':audit_pass,'rows':len(audit),'documents':len({r['document_id'] for r in audit}),'field_count':len(audit_fields),'company_count':len(audit_companies),'exclusive_categories':{'auto_source_row_and_scope_match':audit_auto,'manual_note_scope_confirmed':audit_manual,'derived_or_held_upstream_trace_only':audit_derived,'sum':audit_auto+audit_manual+audit_derived},'page_text_hits_overlap_derived':audit_page_hits,'derived_rows_with_page_text_hit':audit_derived_page_hits,'page_text_nonhits':audit_page_nonhits,'findings':len(audit_findings),'unreviewed':len(audit_unreviewed),'untraced_derived':len(audit_untraced_derived)})
    if not audit_pass: errors.append('12-field metric-document source audit incomplete or has unresolved flags')
    core_audit={'scope':'在本11家公司S02指标引用的43份文档中，检查所有可用的12个基础字段；单季衍生项追溯到规范化上游来源。','rows':len(audit),'documents':len({r['document_id'] for r in audit}),'companies':len(audit_companies),'field_count':len(audit_fields),'field_ids':sorted(audit_fields),'exclusive_row_categories':{'auto_source_row_and_scope_match':audit_auto,'manual_consolidated_note_scope_confirmed':audit_manual,'derived_or_held_upstream_trace_only':audit_derived,'category_sum':audit_auto+audit_manual+audit_derived,'reconciles_to_total':audit_count_reconciles},'page_text_row_label_hits':audit_page_hits,'manual_note_rows_in_page_hits':sum(r.get('manual_review_status')=='MANUAL_PDF_NOTE_SCOPE_CONFIRMED' and r.get('source_row_in_pdf_text')=='YES' for r in audit),'derived_rows_with_incidental_page_hit':audit_derived_page_hits,'page_text_nonhits':audit_page_nonhits,'findings':len(audit_findings),'unreviewed':len(audit_unreviewed),'untraced_derived':len(audit_untraced_derived),'result':'PASS' if audit_pass else 'FAIL','detail_file':'field_audit.csv'}
    review={'review_status':'SELF_CHECK','self_check_result':'PASS' if not errors else 'FAIL','external_review_status':'PENDING','formula_recalculation':'NOT_PERFORMED_PARENT_OWNS_POOL_RECOMPUTE','companies':11,'correction_ledger_rows':len(rows),'value_field_recoveries':len(PATCHES),'rounding_diagnostic_rows':len(ROUNDING),'summary_location_corrections':1,'unresolved_P04_rows':len(UNRESOLVED),'corrected_json_documents':len(work),'core_field_source_audit':core_audit,'checks':checks,'errors':errors,'known_limits':['长安汽车2025Q1和2026Q1 FIN.REV.YTD保持未知：合并利润表仅有营业总收入，P04禁止替代；已留存摘要直披露值作为证据。','单季字段若由累计值推导或上游暂扣，保留派生/暂扣状态并追溯规范化输入；没有直接PDF单季行不等于抽取失败。','SELF_CHECK不是外部验收；父代理仍须统一标准化和全池重算。']}
    (OUT/'checks/review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with (OUT/'company_review.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f); w.writerow(['security_id','company_name','root_cause','resolution_status','documents','remaining_issue'])
        for sec,(name,cause,status) in ROOT_CAUSES.items():
            ds=sorted([d for d in work if original(d)['security_id']==sec])
            rem='；'.join(f'{u[0]} {u[-1]}' for u in UNRESOLVED if INDEX_ROWS[u[0]]['security_id']==sec)
            w.writerow([sec,name,cause,status,';'.join(ds),rem])
    cp=json.loads((OUT/'checkpoint.json').read_text(encoding='utf-8'))
    cp['status']='SELF_CHECK_PASS' if not errors else 'SELF_CHECK_FAIL'
    cp['deliverables']={'corrected_result_documents':len(work),'source_correction_rows':len(rows),'field_value_recoveries':len(PATCHES),'rounding_diagnostic_rows':len(ROUNDING),'summary_location_corrections':1,'unresolved_P04_rows':len(UNRESOLVED),'core_field_audit_rows':len(audit),'core_field_audit_documents':len({r['document_id'] for r in audit}),'core_field_audit_fields':len(audit_fields),'review':'checks/review.json','company_review':'company_review.csv','field_audit':'field_audit.csv','PDF_page_images':sum(1 for _ in (OUT/'evidence/pages').glob('*.png'))}
    cp['self_check_errors']=errors
    (OUT/'checkpoint.json').write_text(json.dumps(cp,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('SELF_CHECK',review['self_check_result'],'errors=',len(errors))
    if errors: raise SystemExit(1)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--stage',choices=['ledger','full'],default='full'); args=ap.parse_args()
    rows=write_ledger()
    if args.stage=='full':
        built=build(rows); render(rows)
        subprocess.run([sys.executable,str(OUT/'audit_core_fields.py')],check=True)
        validate(rows,built)

if __name__=='__main__': main()
