import csv,json,hashlib
from pathlib import Path
import pypdfium2 as pdfium
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).parent/'ocr2';OUT.mkdir(exist_ok=True)
rows=list(csv.DictReader((ROOT/'runs/collection/collection_index.csv').open(encoding='utf-8-sig')))
items=[r for r in rows if (r['security_id']=='SZ:002083' and r['slot_id'] in ('q3_2026','q3_2025','h1_2026','q1_2026','annual_2025')) or (r['security_id']=='SH:601390' and r['slot_id'] in ('h1_2026','q1_2026','annual_2025','h1_2025'))]
summary=[]
for r in items:
 p=ROOT/r['local_file']; assert hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256']
 d=pdfium.PdfDocument(p);texts=[]
 for i in range(len(d)):
  page=d[i];tp=page.get_textpage();t=tp.get_text_range();texts.append(t);tp.close();page.close()
 (OUT/(r['document_id']+'_text.json')).write_text(json.dumps(texts,ensure_ascii=False),encoding='utf-8')
 summary.append(dict(security_id=r['security_id'],slot_id=r['slot_id'],document_id=r['document_id'],pages=len(d),chars=[len(t) for t in texts]))
 if r['security_id']=='SH:601390' and r['slot_id']=='h1_2026': inds=[0,2,3,4,104,109,110,111,112,113,114,115,116,117,118,119,120,121,122,123]
 elif r['security_id']=='SZ:002083' and r['slot_id'] in ('q3_2026','h1_2026'):inds=list(range(len(d))) if len(d)<10 else [0,1,2,3,4,5,6,7,8,20,21,22,23,24,25,26,27,28,29,30]
 else: d.close();continue
 sheet=Image.new('RGB',(1000,300*((len(inds)+4)//5)), 'white');dr=ImageDraw.Draw(sheet)
 for j,i in enumerate(inds):
  pg=d[i];im=pg.render(scale=.32).to_pil().convert('RGB');im.thumbnail((194,272));sheet.paste(im,((j%5)*200,(j//5)*300+20));dr.text(((j%5)*200,(j//5)*300+2),str(i+1),fill='black');pg.close()
 sheet.save(OUT/(r['document_id']+'_contact.png'));d.close()
(OUT/'source_inventory.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps([{k:v for k,v in x.items() if k!='chars'} for x in summary],ensure_ascii=False))
