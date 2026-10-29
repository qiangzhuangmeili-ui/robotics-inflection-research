"""Read-only crop panels from original rendered pages, for amount/column QA."""
import csv,json,re
from collections import defaultdict
from pathlib import Path
from PIL import Image,ImageDraw
OUT=Path(__file__).parent
def compact(s):return re.sub(r'\s+','',s).replace('，',',')
rows=list(csv.DictReader((OUT/'source_corrections.csv').open(encoding='utf-8-sig')))
bydoc=defaultdict(list)
for r in rows:bydoc[r['document_id']].append(r)
for doc,rs in bydoc.items():
 strips=[];seen=set()
 for r in rs:
  k=(r['page'],r['field_id'])
  if k in seen:continue
  seen.add(k);p=OUT/doc/f'p{int(r["page"]):03}'
  o=json.loads(p.with_suffix('.json').read_text(encoding='utf-8'));im=Image.open(p.with_suffix('.png'))
  boxes=[box for box,t,score in o['boxes'] if compact(r['value_raw']).strip('-()') in compact(t).strip('-()')]
  if not boxes:raise ValueError((doc,r['field_id'],r['value_raw']))
  box=boxes[0];y0=max(0,int(min(v[1] for v in box))-28);y1=min(im.height,int(max(v[1] for v in box))+28)
  strip=Image.new('RGB',(im.width,y1-y0+24),'white');ImageDraw.Draw(strip).text((8,4),f'{doc} p{r["page"]} {r["field_id"]} {r["unit"]} selected: {r["value_raw"]}',fill='black');strip.paste(im.crop((0,y0,im.width,y1)),(0,24));strips.append(strip)
 # Source table headers appear as their own unaltered crops.
 for n in sorted(set(int(r['page']) for r in rs)):
  im=Image.open(OUT/doc/f'p{n:03}.png');s=im.crop((0,0,im.width,330));strips.append(s)
 width=max(s.width for s in strips);panel=Image.new('RGB',(width,sum(s.height for s in strips)),'white');y=0
 for s in strips:panel.paste(s,(0,y));y+=s.height
 panel.save(OUT/(doc+'_selection_panel.png'))
 print(doc,len(strips),panel.size)
