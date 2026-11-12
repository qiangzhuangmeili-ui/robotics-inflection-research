import io, contextlib, re
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    import verify_v5 as v
out=[]
row, ent = v._CTRL
out.append("row meta=%s value_B=%r" % (row['meta_field'], row['value_B']))
out.append("ent printed=%r page=%s" % (ent['original_value_text'], ent['original_page']))
pages = v.pdf_pages(row['security_id'], ent['document_id']) or []
ptxt = pages[int(ent['original_page'])-1]
pv_ = ent['original_value_text']
pv_num = v._as_num(pv_)
out.append("pv_num=%r" % pv_num)
n=0
for m in re.finditer(r"-?\d[\d,]*\.\d{2}", ptxt):
    c=m.group(0)
    if c!=pv_ and v._as_num(c)!=pv_num:
        out.append("cand=%r num=%r" % (c, v._as_num(c)))
        n+=1
        if n>=3: break
b = v.D10.get((row['security_id'], row['field_id'], row['period_key'])) or {}
out.append("unit_scale=%r" % b.get('unit_scale'))
open('_dbg3.txt','w',encoding='utf-8').write("\n".join(out))
