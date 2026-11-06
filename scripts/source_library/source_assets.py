"""Only hash-bound, explicitly reviewed source assets may close a conversion gap."""
from __future__ import annotations
import json
from pathlib import Path

def load_assets(raw_sha256):
    from library import digest
    root=Path(__file__).resolve().parents[2]
    manifest=Path(__file__).with_name('asset_reviews.json')
    if not manifest.exists():return {}
    entries=json.loads(manifest.read_text(encoding='utf-8'))
    result={}
    for entry in entries:
        if entry['source_xml_sha256']!=raw_sha256:continue
        cached=root/entry['cached_path']
        if not cached.resolve().is_relative_to(root) or digest(cached.read_bytes())!=entry['asset_sha256']:
            raise ValueError('Reviewed asset hash/path mismatch')
        if entry['kind']=='docx':
            from docx_source import convert_docx
            value,check=convert_docx(cached.read_bytes())
            if check['gaps']:raise ValueError('Supplement conversion has unresolved gaps')
            if digest(value)!=entry['transcribed_text_sha256']:raise ValueError('Supplement conversion differs from reviewed snapshot')
        else:
            value=entry['verbatim_text']
            if digest(value)!=entry['transcribed_text_sha256']:raise ValueError('Figure transcription hash mismatch')
        result[entry['xml_xpath']]=dict(entry,rendered_text=value)
    return result
