"""Atomic writes and validated cache reads; no application/database imports."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def atomic_write(path, raw):
    path=Path(path)
    if isinstance(raw,str):raw=raw.encode('utf-8')
    path.parent.mkdir(parents=True,exist_ok=True)
    descriptor, temporary=tempfile.mkstemp(prefix='.'+path.name+'.',suffix='.partial',dir=path.parent)
    try:
        with os.fdopen(descriptor,'wb') as out:
            out.write(raw);out.flush();os.fsync(out.fileno())
        if Path(temporary).read_bytes()!=raw:raise OSError('Temporary-file verification failed')
        os.replace(temporary,path)
    finally:
        if Path(temporary).exists():Path(temporary).unlink()


def validate_payload(key, raw):
    if not raw or not raw.strip():raise ValueError('Empty source/cache payload')
    if key.endswith('.xml'):
        root=ET.fromstring(raw)
        if key.endswith('_oai.xml'):
            errors=[n for n in root.iter() if n.tag.split('}')[-1]=='error']
            if errors:raise ValueError('OAI error: '+'; '.join(''.join(n.itertext()) for n in errors))
    elif key.endswith('.json'):json.loads(raw)
    elif key.endswith('.pdf'):
        if not raw.startswith(b'%PDF-') or b'%%EOF' not in raw[-4096:]:raise ValueError('Incomplete PDF payload')
    elif key.endswith('.html'):
        snippet=raw[:8000].lower()
        if any(marker in snippet for marker in (b'access denied',b'just a moment',b'<title>request rejected',b'checking your browser',b'captcha')):raise ValueError('Access-denied page is not source content')


def successful_downloads(report):
    result={}
    log=Path(report)/'fetch_log.jsonl'
    if log.exists():
        for line in log.read_text(encoding='utf-8').splitlines():
            if not line.strip():continue
            row=json.loads(line)
            if row.get('status')==200 and row.get('sha256'):result[row['key']]=row
    return result


def audit_cache(report):
    report=Path(report);success=successful_downloads(report)
    checks=[]
    for file in sorted((report/'cache').iterdir()):
        if not file.is_file() or file.name.endswith('.partial'):continue
        row={'name':file.name,'bytes':file.stat().st_size,'status':'verified'}
        try:
            raw=file.read_bytes();validate_payload(file.name,raw)
            expected=success.get(file.name)
            if expected and sha256(raw)!=expected['sha256']:raise ValueError('Hash differs from successful fetch log')
            row['sha256']=sha256(raw)
            if not expected:row['provenance']='local_browser_capture_or_unlogged_input'
        except (ValueError,ET.ParseError) as exc:row.update(status='invalid',reason=str(exc))
        checks.append(row)
    return checks
