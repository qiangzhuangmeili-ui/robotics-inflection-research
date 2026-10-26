"""Materialize an authenticated connector file reference without logging its URL.

Usage: python drive_verify_download.py DOCUMENT_ID FILE_URI_DOWNLOAD_URL
The URL is ephemeral and is deliberately never persisted to the research index.
"""
import hashlib
import json
import sys
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
def download(document_id, download_url):
    if not document_id.replace('-', '').replace('_', '').isalnum():
        raise ValueError('Invalid document ID')
    target = ROOT / 'sources' / 'drive_readback_20261026' / (document_id + '.pdf')
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        response = requests.get(download_url, timeout=(10, 45))
        if response.status_code != 200:
            print(json.dumps({'document_id': document_id, 'status': 'FAILED', 'http_status': response.status_code}))
            return
        data = response.content
        if not data.startswith(b'%PDF-'):
            print(json.dumps({'document_id': document_id, 'status': 'NON_PDF_RESPONSE', 'size': len(data)}))
            return
        target.write_bytes(data)
        print(json.dumps({'document_id': document_id, 'status': 'DOWNLOADED', 'size': len(data), 'sha256_actual': hashlib.sha256(data).hexdigest(), 'local_path': target.relative_to(ROOT).as_posix()}))
    except requests.RequestException as exc:
        # Exception strings may contain a signed URL. Persist only the error class.
        print(json.dumps({'document_id': document_id, 'status': 'FAILED', 'error_class': type(exc).__name__}))
        return

if __name__ == '__main__':
    if sys.argv[1] == '--batch':
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda row: download(row['document_id'], row['url']), json.loads(sys.argv[2])))
    else:
        download(*sys.argv[1:3])
