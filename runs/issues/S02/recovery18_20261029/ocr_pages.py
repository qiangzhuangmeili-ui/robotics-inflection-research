"""Local OCR sidecar only. The original PDF is never rewritten."""
import argparse,csv,hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).parent/'ocr2'
sys.path.insert(0,str(Path(__file__).parent/'ocr_runtime'))
from rapidocr_onnxruntime import RapidOCR
import numpy as np
import pypdfium2 as pdfium
def row_text(result):
 groups=[]
 for box,text,score in sorted(result or [],key=lambda r:((r[0][0][1]+r[0][2][1])/2,r[0][0][0])):
  y=(box[0][1]+box[2][1])/2;h=abs(box[2][1]-box[0][1])
  hit=next((g for g in reversed(groups[-5:]) if abs(g[0]-y)<max(7,min(g[1],h)*.5)),None)
  if hit is None:groups.append([y,h,[(box[0][0],text)]])
  else:hit[2].append((box[0][0],text))
 return '\n'.join(' '.join(t for _,t in sorted(g[2])) for g in groups)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('document_id');ap.add_argument('pages',help='1-based inclusive e.g. 1-7,31-40');args=ap.parse_args()
 r=next(x for x in csv.DictReader((ROOT/'runs/collection/collection_index.csv').open(encoding='utf-8-sig')) if x['document_id']==args.document_id)
 p=ROOT/r['local_file'];assert hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256']
 inds=[]
 for token in args.pages.split(','):
  parts=token.split('-');a=int(parts[0]);b=int(parts[-1]);inds+=list(range(a,b+1))
 dest=OUT/r['document_id'];dest.mkdir(exist_ok=True);engine=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=1)
 d=pdfium.PdfDocument(p)
 for n in inds:
  out=dest/f'p{n:03}.json'
  if out.exists():continue
  pg=d[n-1];im=pg.render(scale=2).to_pil().convert('RGB');im.save(dest/f'p{n:03}.png');pg.close()
  tic=time.time();res,elapsed=engine(np.array(im))
  obj=dict(document_id=r['document_id'],security_id=r['security_id'],slot_id=r['slot_id'],source_sha256=r['sha256'],pdf_page=n,image_scale=2,ocr_engine='rapidocr_onnxruntime 1.4.4',text=row_text(res),boxes=res or [],seconds=round(time.time()-tic,2))
  out.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8');print(f'{r["document_id"]} page {n} {obj["seconds"]}s lines {len(res or [])}',flush=True)
 d.close()
if __name__=='__main__':main()
