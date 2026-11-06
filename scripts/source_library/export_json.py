"""Export verified whole source documents to a readable UTF-8 JSON file.

No network, embeddings, application imports or database access.
Run: python -B scripts/source_library/export_json.py [--check]
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from storage import atomic_write

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / 'knowledge/rag/source_library'
MARKER = '<!-- ORIGINAL_DOCUMENT_BODY -->\n'


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def load_jsonl(raw):
    return [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]


def source_path(relative):
    candidate = (ROOT / relative).resolve()
    if not candidate.is_relative_to(LIBRARY.resolve()):
        raise ValueError('Source path must remain inside source_library')
    return candidate


def publisher_name(record, original):
    if record.get('organization'):
        return record['organization']
    # Read an explicit source label; do not invent a publisher from a DOI hostname.
    if record.get('original_format') == 'xml':
        tree = ET.fromstring(original)
        names = [n for n in tree.iter() if n.tag.split('}')[-1] == 'journal-title']
        for node in names:
            value = ''.join(node.itertext()).strip()
            if value:
                return value
    return None


def build_export(*, expected_catalog_sha256=None):
    catalog_raw = (LIBRARY / 'catalog.jsonl').read_bytes()
    status = json.loads((LIBRARY / 'BUILD_STATUS.json').read_text(encoding='utf-8'))
    if expected_catalog_sha256 is None:
        if status.get('status') != 'verified' or not status.get('usable'):
            raise ValueError('Library is not verified; JSON export refused')
        expected_catalog_sha256=status.get('catalog_sha256')
    # The offline builder supplies the hash it has just verified, while the
    # public CLI requires a fully published BUILD_STATUS. No stale JSON window.
    if sha256(catalog_raw) != expected_catalog_sha256:
        raise ValueError('Catalog hash differs from verified build')
    catalog = load_jsonl(catalog_raw)
    core_raw = (LIBRARY / 'core_catalog.jsonl').read_bytes()
    core = load_jsonl(core_raw)
    expected = [r for r in catalog if r.get('coverage_eligible')]
    if not core or sorted(core, key=lambda r:r['source_id']) != sorted(expected, key=lambda r:r['source_id']):
        raise ValueError('Core catalog does not match the verified full catalog')
    documents = []
    ids = set()
    for row in core:
        sid = row['source_id']
        if sid in ids:
            raise ValueError('Duplicate source ID: ' + sid)
        ids.add(sid)
        conversion = row.get('conversion', {})
        rights = row.get('rights', {})
        if row.get('status') != 'accepted_complete_text' or conversion.get('status') != 'complete_text' or conversion.get('gaps'):
            raise ValueError('Incomplete document: ' + sid)
        if not str(rights.get('status', '')).startswith('verified'):
            raise ValueError('Unverified reuse permission: ' + sid)
        if not row.get('title') or not row.get('source_url'):
            raise ValueError('Missing document title or source URL: ' + sid)
        path = source_path(row['document_path'])
        if path.parent != (LIBRARY / 'documents').resolve():
            raise ValueError('Non-core document path: ' + sid)
        raw = path.read_bytes()
        if sha256(raw) != row['document_sha256']:
            raise ValueError('Markdown hash mismatch: ' + sid)
        text = raw.decode('utf-8')
        if text.count(MARKER) != 1:
            raise ValueError('Missing or ambiguous original-body marker: ' + sid)
        body = text.split(MARKER, 1)[1]
        if not body.strip() or sha256(body.encode('utf-8')) != row['content_sha256']:
            raise ValueError('Body hash mismatch or empty content: ' + sid)
        original = source_path(row['original_path']).read_bytes()
        if sha256(original) != row['original_sha256']:
            raise ValueError('Original source hash mismatch: ' + sid)
        for asset in row.get('source_assets', []):
            if sha256(source_path(asset['archived_path']).read_bytes()) != asset['asset_sha256']:
                raise ValueError('Original asset hash mismatch: ' + sid)
        documents.append({
            'id': sid,
            'ten_tai_lieu': row['title'],
            'nguon': {
                'ten_nguon': publisher_name(row, original),
                'link_nguon': row['source_url'],
                'link_toan_van': row.get('full_text_url'),
                'tac_gia': row.get('authors') or [],
                'to_chuc': row.get('organization'),
                'loai_nguon': row.get('source_type'),
            },
            'noi_dung': body,
            'ngay_thang': {
                'ngay_xuat_ban': row.get('publication_date'),
                'ngay_cap_nhat': row.get('updated_date'),
                'ngay_doi_chieu_nguon': row.get('checked_at'),
            },
            'doi_chieu': {
                'ngon_ngu': row.get('language'),
                'phien_ban': row.get('version'),
                'phien_ban_chuyen_doi': conversion.get('conversion_revision'),
                'pham_vi_tuoi_goc': row.get('original_age_scope'),
                'gioi_han': row.get('limits', []),
                'quyen_su_dung': rights,
                'da_tham_dinh_lam_sang_doc_lap': bool(row.get('clinical_reviewed')),
                'tep_markdown': row['document_path'],
                'tep_nguon_goc': row['original_path'],
                'tai_san_nguon': row.get('source_assets', []),
                'sha256_noi_dung': row['content_sha256'],
                'sha256_markdown': row['document_sha256'],
                'sha256_nguon_goc': row['original_sha256'],
                'ho_so_day_du': 'knowledge/rag/source_library/catalog.jsonl#' + sid,
            },
        })
    return {
        'thong_tin_bo_du_lieu': {
            'phien_ban_cau_truc': 'carobud.full-documents.vi.v1',
            'so_tai_lieu': len(documents),
            'tong_ky_tu_noi_dung': sum(len(d['noi_dung']) for d in documents),
            'dinh_dang_noi_dung': 'Markdown nguyen van tu ban chuyen doi da doi chieu; co the chua HTML/MathML.',
            'ngay_xuat_json': datetime.now(timezone(timedelta(hours=7))).date().isoformat(),
            'ngay_doi_chieu_kho': status.get('checked_at'),
            'sha256_danh_muc': sha256(catalog_raw),
            'sha256_danh_muc_chinh': sha256(core_raw),
            'pham_vi_su_dung': 'Kho nguon phuc vu nghien cuu; chua co tham dinh lam sang doc lap.',
            'san_sang_embedding': False,
            'duoc_duyet_production': False,
        },
        'tai_lieu': documents,
    }


def verify_roundtrip(payload, expected):
    # All document fields and every content character must survive JSON encoding.
    if payload.get('tai_lieu') != expected['tai_lieu']:
        raise ValueError('JSON round-trip changed documents or metadata')
    actual = dict(payload.get('thong_tin_bo_du_lieu', {}))
    reference = dict(expected['thong_tin_bo_du_lieu'])
    actual.pop('ngay_xuat_json', None)
    reference.pop('ngay_xuat_json', None)
    if actual != reference:
        raise ValueError('Export metadata is stale or incorrect')
    for row in payload['tai_lieu']:
        if sha256(row['noi_dung'].encode('utf-8')) != row['doi_chieu']['sha256_noi_dung']:
            raise ValueError('Export body hash mismatch: ' + row['id'])


def export_documents(*, check=False, expected_catalog_sha256=None):
    expected = build_export(expected_catalog_sha256=expected_catalog_sha256)
    path = LIBRARY / 'documents.json'
    if not check:
        encoded = (json.dumps(expected, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        verify_roundtrip(json.loads(encoded), expected)
        atomic_write(path, encoded)
    verify_roundtrip(json.loads(path.read_bytes()), expected)
    return {'ok': True, 'mode': 'check' if check else 'export',
            'file': str(path), 'documents': len(expected['tai_lieu']),
            'body_characters': expected['thong_tin_bo_du_lieu']['tong_ky_tu_noi_dung'],
            'all_bodies_match_markdown': True, 'database_changed': False,
            'embedding_called': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Verify existing JSON without writing')
    args = parser.parse_args()
    print(json.dumps(export_documents(check=args.check), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
