"""Read-only PDF checks; emit a supplemental P02 asset inventory, no registry migration."""
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'runs/issues/P02'

def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def run():
    registry = read_csv(ROOT / 'data/document_registry.csv')
    metadata = {r['document_id']:r for r in json.loads((OUT/'drive_metadata_readback.json').read_text(encoding='utf-8-sig'))['records']}
    checks = []
    for row in registry:
        if not row['drive_file_id']:
            continue
        p = ROOT/'sources/drive_readback_20261026'/f"{row['document_id']}.pdf"
        meta = metadata[row['document_id']]
        check = {'document_id': row['document_id'], 'drive_file_id': row['drive_file_id'], 'drive_url': row['drive_url'],
                 'local_path':p.relative_to(ROOT).as_posix(), 'recorded_sha256':row['sha256'], 'original_archive_status':row['archive_status'],
                 'evidence_scope':'FILE_IDENTITY_AND_INTEGRITY_ONLY_NOT_BUSINESS_REVIEW', 'checked_at':meta['checked_at']}
        if not p.exists():
            check['status'] = 'DOWNLOAD_FAILED'
            checks.append(check)
            continue
        data = p.read_bytes()
        check.update(size_bytes=len(data), sha256_actual=hashlib.sha256(data).hexdigest())
        check['hash_comparison'] = ('MATCH' if check['sha256_actual'] == row['sha256'].lower() else 'MISMATCH') if row['sha256'] else 'NO_BASELINE_HASH'
        check['metadata_size_match'] = int(meta['metadata'].get('size') or meta['raw_size']) == len(data)
        try:
            pdf = PdfReader(p)
            check['page_count'] = len(pdf.pages)
            expected = row['page_count'].strip()
            check['page_count_comparison'] = 'MATCH' if expected.isdigit() and int(expected)==len(pdf.pages) else ('NOT_RECORDED' if not expected.isdigit() else 'MISMATCH')
            first = '\n'.join((pdf.pages[i].extract_text() or '') for i in range(min(2,len(pdf.pages))))
            normalized = re.sub(r'\s+', '', first)
            title = re.sub(r'\s+', '', row['original_title'])
            # Only an exact registered title match is automatic identity confirmation.
            check['identity_check'] = 'REGISTERED_TITLE_EXACT_IN_FIRST_TWO_PAGES' if title and title in normalized else 'MANUAL_IDENTITY_CHECK_REQUIRED'
            check['first_two_pages_excerpt'] = first[:1200]
            if check['identity_check'] == 'MANUAL_IDENTITY_CHECK_REQUIRED':
                identity_text = '\n'.join((pdf.pages[i].extract_text() or '') for i in range(min(6,len(pdf.pages))))
                flat = re.sub(r'\s+', '', identity_text)
                issuer = re.split(r'20\d{2}',title)[0].rstrip('：:')
                name = row['stock_name'].replace('*','').replace('ST','')
                entity_match = row['stock_code'] in flat or (len(issuer)>3 and issuer in flat) or (len(name)>2 and name in flat)
                year = re.search(r'20\d{2}',row['period_covered'])
                period_match = not year or year.group() in flat
                type_tokens = ['半年度报告'] if 'H1' in row['period_covered'] or '半年度' in row['period_covered'] else (['年度报告'] if row['period_covered']=='2025年度' and '可持续' not in title else [])
                type_match = all(t in flat for t in type_tokens)
                check['identity_components'] = {'entity_token_match':entity_match,'period_year_match':bool(period_match),'report_type_match':type_match,'physical_pages_checked':min(6,len(pdf.pages))}
                check['identity_check'] = 'ENTITY_PERIOD_TYPE_TOKENS_IN_FIRST_SIX_PAGES' if entity_match and period_match and type_match else 'MANUAL_IDENTITY_CHECK_REQUIRED'
                check['identity_pages_excerpt'] = identity_text[:1800]
            check['status'] = 'PDF_PARSED'
        except Exception as exc:
            check.update(status='PDF_PARSE_FAILED', error_class=type(exc).__name__)
        checks.append(check)
    write_json(ROOT/'sources/drive_readback_20261026/identity_excerpts.json', checks)
    for check in checks:
        check['identity_excerpt'] = check.pop('first_two_pages_excerpt', '')[:180]
        check.pop('identity_pages_excerpt', None)
    write_json(OUT/'drive_readback_checks.json',checks)
    fields = [k for r in checks for k in r if k not in ('first_two_pages_excerpt','identity_pages_excerpt')]
    fields = list(dict.fromkeys(fields))
    with (OUT/'drive_readback_checks.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(checks)
    summary = {'checked_at':datetime.now(timezone.utc).isoformat(), 'executor':'Codex','review_nature':'SELF_CHECK_FILE_VALIDATION_ONLY',
               'documents':len(registry),'drive_documents':len(checks), 'downloaded':sum('sha256_actual' in r for r in checks),
               'status':dict(Counter(r['status'] for r in checks)), 'hash_comparison':dict(Counter(r.get('hash_comparison') for r in checks)),
               'identity_check':dict(Counter(r.get('identity_check') for r in checks)),
               'page_count_comparison':dict(Counter(r.get('page_count_comparison') for r in checks)),
               'business_evidence_independently_verified_added':0,
               'registry_unchanged':True,'note':'Homepage-only identity check never upgrades AI_READ_CONFIRMED. Official-source provenance remains separately unverified.'}
    write_json(OUT/'drive_followup_summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':run()
