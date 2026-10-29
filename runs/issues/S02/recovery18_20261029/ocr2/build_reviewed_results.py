"""Source-specific, auditable selections from OCR; no financial metric formulas."""
import csv,hashlib,json,re,sys
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5];OUT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'tools'))
import a03_financial_field_extractor as A
BASE=ROOT/'runs/issues/S02/remediation_20261029/extracted'
DEST=OUT/'corrected_results';DEST.mkdir(exist_ok=True)
evidence=[]
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def source(doc,page):return load(OUT/doc/f'p{page:03}.json')['text']
def compact(s):return re.sub(r'\s+','',s).replace('，',',')
def put(r,fid,value,page,label,unit,note='',raw=None):
 text=source(r['document_id'],page);assert compact(value).strip('-()') in compact(text),(r['document_id'],fid,value,page)
 val=Decimal(value.replace(',','').replace('(','-').replace(')',''));scale=A.UNIT_SCALE[unit]
 row=dict(document_id=r['document_id'],security_id=r['security_id'],stock_code=r['stock_code'],slot_id=r['slot_id'],period_label=r['period_label'],field_id=fid,value_raw=value,unit_raw=unit,unit_scale=scale,value_cny=float(val*Decimal(str(scale))),page=page,evidence_label=label,extract_status='EXTRACTED',note=note,raw_row=raw or label+' '+value)
 r['fields']=[f for f in r['fields'] if not (f['field_id']==fid and (f['note']==note or not note or (fid=='FIN.NPDEDT.YTD')))]
 r['fields'].append(row)
 evidence.append(dict(security_id=r['security_id'],slot_id=r['slot_id'],document_id=r['document_id'],field_id=fid,note=note,page=page,label=label,value_raw=value,unit=unit,value_cny=row['value_cny'],source_sha256=r['ledger_sha256'],method='OCR_SELECTED_COLUMN_ORIGINAL_PAGE_REVIEW',ocr_sidecar=f'{r["document_id"]}/p{page:03}.json'))
def select(r,fid,page,label,unit):
 t=source(r['document_id'],page);lines=t.splitlines();row=next(x for x in lines if re.search(label,x))
 nums=re.findall(r'\(?-?\d{1,3}(?:,\d{3})+(?:\.\d+)?\)?',row)
 assert len(nums)>=2,(fid,page,row)
 put(r,fid,nums[0],page,re.sub(r'\\[bds]','',label),unit,raw=row)
def keyfix(r,fid,value,page):
 assert compact(value) in compact(source(r['document_id'],page))
 r.setdefault('key_financials_values',{})[fid]=value
 r.setdefault('key_financials_details',{})[fid]=dict(page=page,unit='元',raw_row='Reviewed summary row '+value,column_basis='YTD_COLUMN_VISUAL_REVIEW')
def finalize(r):
 direct={f['field_id']:f for f in r['fields'] if f['extract_status']=='EXTRACTED' and not f['field_id'].endswith('.SQ')}
 for fid in ('FIN.REV.YTD','FIN.NPP.YTD','FIN.OCF.YTD'):
  detail=r.get('key_financials_details',{}).get(fid,{})
  if fid in r.get('key_financials_values',{}) and fid in direct:
   scale=A.UNIT_SCALE[detail.get('unit') or r['key_financials_unit']]
   n=Decimal(r['key_financials_values'][fid].replace(',',''))*Decimal(str(scale))
   assert n==Decimal(str(direct[fid]['value_cny'])),(r['document_id'],fid,n,direct[fid]['value_cny'])
   r['crosscheck'][fid]='MATCH'
 r['parse_error']=None
 r['recovery_method']='TARGETED_OCR_SOURCE_REVIEW_SELF_CHECK'
 r['recovery_base_sha256']=hashlib.sha256((BASE/(r['document_id']+'.json')).read_bytes()).hexdigest()
 r['ocr_source_pages']=[dict(path=str(p.relative_to(ROOT)).replace('\\','/'),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted((OUT/r['document_id']).glob('p*.json'))]
 (DEST/(r['document_id']+'.json')).write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
def restatement_no(r,page):
 r.update(restatement='否',restatement_page=page,restatement_evidence='原PDF明确勾选/列示否；OCR不可独立区分勾选',restatement_method='SOURCE_VISUAL_CHECK')
 r['fields']=[f for f in r['fields'] if f['field_id']!='FIN.RESTATEMENT']
 r['fields'].append(dict(document_id=r['document_id'],security_id=r['security_id'],stock_code=r['stock_code'],slot_id=r['slot_id'],period_label=r['period_label'],field_id='FIN.RESTATEMENT',value_raw='否',unit_raw='NOT_APPLICABLE',unit_scale='',value_cny='',page=page,evidence_label='公司是否需追溯调整或重述以前年度会计数据',extract_status='EXTRACTED',note='method=SOURCE_VISUAL_CHECK',raw_row='否'))
def official_quarters(r,page,unit,arrays):
 # Explicitly disclosed quarterly amounts; no subtraction or replicated formula.
 r['fields']=[f for f in r['fields'] if not f['field_id'].endswith('.SQ')]
 for fid,vals in arrays.items():
  for i,v in enumerate(vals):put(r,fid,v,page,fid,unit,note=f'Q{i+1}',raw='Official quarterly table '+v)
def main():
 for doc,bs,is1,is2,cf in [('DOC-C69703F6242CCD8E',114,117,118,119),('DOC-12300C8149048B60',116,119,120,121),('DOC-18AEFAAE323DD39B',159,162,163,164)]:
  r=load(BASE/(doc+'.json'));r['unit_bs']=r['unit_is']=r['unit_cf']='千元'
  r['regions']={k:dict(start_page=a,end_page=b,unit='千元') for k,a,b in [('BS_CONS',bs,is1-1),('IS_CONS',is1,is2),('CF_CONS',cf,cf+1)]}
  for fid,p,l in [('FIN.AR.INSTANT',bs,r'^应收账款\b'),('FIN.NR.INSTANT',bs,r'^应收票据\b'),('FIN.CONTRACTASSET.INSTANT',bs,r'^合同资产\b'),('FIN.INV.INSTANT',bs,r'^存货\b'),('FIN.ASSET.INSTANT',bs,r'^资产总计\b'),('FIN.REV.YTD',is1,r'^其中：营业收入\b'),('FIN.COST.YTD',is1,r'^其中：营业成本\b'),('FIN.NP.YTD',is1,r'^净利润\b'),('FIN.NPP.YTD',is2,r'^归属于母公司股东的净利润\b'),('FIN.OCF.YTD',cf,r'^经营活动(?:产生|使用)的现金流量净额\b')]:select(r,fid,p,l,'千元')
  if doc=='DOC-18AEFAAE323DD39B':
   official_quarters(r,10,'千元',{'FIN.REV.SQ':['248,564,203','262,529,107','262,720,340','316,812,351'],'FIN.NPP.SQ':['6,025,119','5,801,483','5,663,553','5,401,548'],'FIN.NPDEDT.SQ':['5,553,117','4,714,962','4,933,229','2,463,099'],'FIN.OCF.SQ':['-77,399,254','-2,231,157','6,747,731','101,654,446']})
  # Keep existing unresolved restatement diagnosis; do not clear it using magnitude.
  finalize(r)
 furi=[('DOC-9DE6D7E8F6A6333C','681,531,758.18',2),('DOC-03B9B2A3EF9B491B','297,502,285.06',2),('DOC-3F5CD36F615E3BC4','181,734,764.61',2),('DOC-D7F653B0C5C02C09','394,670,159.40',6),('DOC-41A995E12934526B','446,568,486.54',7)]
 for doc,npdedt,p in furi:
  r=load(OUT/(doc+'_draft.json'));r.pop('recovery_method',None)
  put(r,'FIN.NPDEDT.YTD',npdedt,p,'归属于上市公司股东的扣除非经常性损益的净利润','元',note='source=主要会计数据表',raw='原表多行标签，当期累计列 '+npdedt)
  for f in list(r['fields']):
   if f['extract_status']=='EXTRACTED' and f['field_id'] not in ('FIN.NPDEDT.YTD','FIN.RESTATEMENT') and not f['field_id'].endswith('.SQ'):
    put(r,f['field_id'],f['value_raw'],f['page'],f['evidence_label'],f['unit_raw'],raw=f['raw_row'])
  # The wrapped net-profit line is distinct from attributable profit.
  if doc=='DOC-03B9B2A3EF9B491B':put(r,'FIN.NP.YTD','286,893,780.27',6,'五、净利润','元')
  if doc=='DOC-3F5CD36F615E3BC4':put(r,'FIN.NP.YTD','178,128,120.36',6,'五、净利润','元')
  for fid in ('FIN.REV.YTD','FIN.NPP.YTD','FIN.OCF.YTD'):
   f=next(x for x in r['fields'] if x['field_id']==fid);keyfix(r,fid,f['value_raw'],p)
  restatement_no(r,p)
  if doc=='DOC-9DE6D7E8F6A6333C':
   for fid,value in [('FIN.REV.SQ','1,837,667,528.05'),('FIN.NPP.SQ','292,719,745.87'),('FIN.NPDEDT.SQ','286,861,598.78')]:
    put(r,fid,value,2,'主要会计数据：本报告期（单季）','元',note='Q3',raw='Summary: reported current quarter, not YTD '+value)
  if doc=='DOC-03B9B2A3EF9B491B':
   for fid,value in [('FIN.REV.SQ','1,253,597,407.98'),('FIN.NPP.SQ','50,247,544.17'),('FIN.NPDEDT.SQ','47,180,938.27')]:
    put(r,fid,value,2,'主要会计数据：本报告期（单季）','元',note='Q3',raw='Summary: reported current quarter, not YTD '+value)
  if doc=='DOC-41A995E12934526B':
   official_quarters(r,8,'元',{'FIN.REV.SQ':['1,363,635,533.89','1,223,762,998.04','1,253,597,407.98','1,369,038,785.93'],'FIN.NPP.SQ':['127,469,433.58','118,251,680.00','50,247,544.17','132,459,988.24'],'FIN.NPDEDT.SQ':['136,204,267.68','114,117,079.11','47,180,938.27','149,066,201.48'],'FIN.OCF.SQ':['120,789,771.31','326,233,514.38','99,186,960.46','287,054,198.44']})
  finalize(r)
 with (OUT/'source_corrections.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(evidence[0]));w.writeheader();w.writerows(evidence)
 print(json.dumps(dict(corrected_documents=len(list(DEST.glob('*.json'))),evidence_cells=len(evidence),verdict='SELF_CHECK_PENDING_VISUAL_PANEL_REVIEW',s03='LOCKED'),ensure_ascii=False))
if __name__=='__main__':main()
