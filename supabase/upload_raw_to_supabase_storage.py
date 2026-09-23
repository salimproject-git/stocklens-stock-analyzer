# uploader
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

DEFAULT_RAW_ROOT = Path(r'D:\Stock Analyzer\Data\Raw')
BUCKET = 'stocklens_raw'

def required_env(name: str) -> str:
    value = os.getenv(name, '').strip()
    if not value:
        raise RuntimeError(f'Environment variable belum di-set: {name}')
    return value

def parse_date(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        date.fromisoformat(value)
    except ValueError:
        return None
    return value

def collect_dates(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in {'date', 'report_date', 'period_end', 'available_date'}:
                parsed = parse_date(child)
                if parsed:
                    found.append(parsed)
            found.extend(collect_dates(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(collect_dates(child))
    return found

def category_for(relative: Path) -> tuple[str, str]:
    if len(relative.parts) > 1:
        return relative.parts[0].lower(), '/'.join(relative.parts[1:])
    name = relative.name.lower()
    for prefix, category in {'company_report_info': 'info', 'company_report_annual': 'annual', 'company_report_dividend': 'dividend', 'quarterly_financial_dates': 'quarterly', 'manifest': 'manifest'}.items():
        if name.startswith(prefix):
            return category, relative.name
    return 'root', relative.name

def discover_files(raw_root: Path, ticker: str) -> list[dict[str, Any]]:
    ticker_root = raw_root / ticker
    files = sorted(ticker_root.rglob('*.json')) if ticker_root.is_dir() else []
    if not files:
        raise RuntimeError(f'No JSON files found under: {ticker_root}')
    result = []
    for path in files:
        content = path.read_bytes()
        payload = json.loads(content.decode('utf-8'))
        category, logical_name = category_for(path.relative_to(ticker_root))
        dates = collect_dates(payload) if category in {'daily', 'quarterly'} else []
        logical_path = logical_name.replace(chr(92), '/')
        result.append({'path': path, 'storage_path': f'sectors/{ticker}/{category}/{logical_path}', 'source_file_type': category, 'content': content, 'checksum': hashlib.sha256(content).hexdigest(), 'record_count': len(payload) if isinstance(payload, list) else 1, 'first_record_date': min(dates) if dates else None, 'last_record_date': max(dates) if dates else None})
    return result

class Supabase:
    def __init__(self, url: str, key: str):
        self.rest_url = url.rstrip('/') + '/rest/v1'
        self.storage_url = url.rstrip('/') + '/storage/v1'
        self.session = requests.Session()
        self.session.headers.update({'apikey': key, 'Authorization': 'Bearer ' + key})

    def rest(self, method: str, resource: str, params=None, body=None, prefer=None):
        headers = {'Content-Type': 'application/json'}
        if prefer: headers['Prefer'] = prefer
        response = self.session.request(method, self.rest_url + '/' + resource, params=params, json=body, headers=headers, timeout=60)
        if not response.ok: raise RuntimeError('REST failed (%s): %s' % (response.status_code, response.text[:1000]))
        return response.json() if response.text else None

    def storage_exists(self, path: str) -> bool:
        response = self.session.get(self.storage_url + '/object/info/' + BUCKET + '/' + quote(path, safe='/'), timeout=60)
        if response.ok:
            return True
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        error_code = payload.get('code')
        internal_status = str(payload.get('statusCode', ''))
        if error_code == 'NoSuchBucket':
            raise RuntimeError('Storage bucket missing: ' + BUCKET)
        if response.status_code in {401, 403} or internal_status in {'401', '403'}:
            raise RuntimeError('Storage permission/authentication failure (%s): %s' % (response.status_code, response.text[:1000]))
        if response.status_code == 404 or internal_status == '404' or error_code == 'NoSuchKey':
            return False
        raise RuntimeError('Storage info failed (%s): %s' % (response.status_code, response.text[:1000]))
        return True

    def upload(self, path: str, content: bytes) -> None:
        response = self.session.post(self.storage_url + '/object/' + BUCKET + '/' + quote(path, safe='/'), headers={'Content-Type': 'application/json', 'x-upsert': 'false'}, data=content, timeout=120)
        if not response.ok: raise RuntimeError('Storage upload failed (%s): %s' % (response.status_code, response.text[:1000]))

    def metadata(self, path: str):
        return self.rest('GET', 'ingestion_files', {'storage_path': 'eq.' + path, 'select': 'checksum_sha256', 'order': 'created_at.desc', 'limit': '1'})

    def save_metadata(self, run_id: str, item: dict[str, Any], status: str) -> None:
        self.rest('POST', 'ingestion_files', params={'on_conflict': 'ingestion_run_id,storage_path'}, body={'ingestion_run_id': run_id, 'source_file_type': item['source_file_type'], 'storage_bucket': BUCKET, 'storage_path': item['storage_path'], 'checksum_sha256': item['checksum'], 'record_count': item['record_count'], 'first_record_date': item['first_record_date'], 'last_record_date': item['last_record_date'], 'status': status}, prefer='resolution=merge-duplicates,return=minimal')

    def update_run(self, run_id: str, status: str, error: str | None = None) -> None:
        body = {'status': status, 'completed_at': datetime.now(timezone.utc).isoformat()}
        if error: body['error_message'] = error[:2000]
        self.rest('PATCH', 'ingestion_runs', {'id': 'eq.' + run_id}, body, 'return=minimal')

def get_run(db: Supabase, ticker: str, run_id: str | None) -> tuple[str, bool]:
    if run_id:
        rows = db.rest('GET', 'ingestion_runs', {'id': 'eq.' + run_id, 'select': 'id,symbol'})
        if not rows or rows[0]['symbol'].upper() != ticker:
            raise RuntimeError('ingestion_run_id not found or ticker mismatch')
        return run_id, False
    sources = db.rest('GET', 'data_sources', {'source_code': 'eq.SECTORS_APP', 'select': 'id', 'limit': '1'})
    if not sources: raise RuntimeError('SECTORS_APP missing from data_sources')
    rows = db.rest('POST', 'ingestion_runs', body={'source_id': sources[0]['id'], 'symbol': ticker, 'status': 'RUNNING', 'collector_version': 'raw-storage-uploader-0.1'}, prefer='return=representation')
    return rows[0]['id'], True

def handle_file(db: Supabase, run_id: str, item: dict[str, Any]) -> str:
    object_exists = db.storage_exists(item['storage_path'])
    metadata = db.metadata(item['storage_path'])
    if not object_exists:
        db.upload(item['storage_path'], item['content'])
        db.save_metadata(run_id, item, 'UPLOADED')
        return 'UPLOAD'
    if metadata:
        if metadata[0]['checksum_sha256'] == item['checksum']:
            db.save_metadata(run_id, item, 'SKIPPED')
            return 'SKIP'
        raise RuntimeError('Checksum conflict; refusing to overwrite ' + item['storage_path'])
    raise RuntimeError('Storage object exists without metadata; refusing overwrite ' + item['storage_path'])

def main() -> None:
    parser = argparse.ArgumentParser(description='Upload local Data/Raw JSON to private Supabase Storage')
    parser.add_argument('ticker')
    parser.add_argument('--ingestion-run-id')
    parser.add_argument('--raw-root', default=str(DEFAULT_RAW_ROOT))
    args = parser.parse_args()
    ticker = args.ticker.upper().replace('.JK', '')
    items = discover_files(Path(args.raw_root), ticker)
    db = Supabase(required_env('SUPABASE_URL'), required_env('SUPABASE_SERVICE_ROLE_KEY'))
    run_id, created = get_run(db, ticker, args.ingestion_run_id)
    counts = {'UPLOAD': 0, 'SKIP': 0}
    try:
        for item in items:
            result = handle_file(db, run_id, item)
            counts[result] += 1
            print(result + ': ' + item['storage_path'])
        db.update_run(run_id, 'SUCCESS')
        print('DONE: ticker=%s run_id=%s uploaded=%s skipped=%s total=%s' % (ticker, run_id, counts['UPLOAD'], counts['SKIP'], len(items)))
    except Exception as error:
        db.update_run(run_id, 'FAILED', str(error))
        print('FAILED: ' + str(error))
        raise SystemExit(1) from error

if __name__ == '__main__':
    main()
