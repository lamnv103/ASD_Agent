"""Deterministic rendering of checked answer claims (answer_contract_v0.1).

No model is involved here: the text is assembled from claims that already passed the checks,
fixed templates and source metadata. Same input -> same bytes. The renderer never adds
connectives between claims and never promotes a detail claim to the direct answer.
"""
from __future__ import annotations


def _markers(numbers):
    return "".join(f"[{n}]" for n in numbers)


def number_sources(claims, catalog):
    """Display numbers per SOURCE, by first appearance in claim order."""
    order = []
    for c in claims:
        for eid in c["evidence_ids"]:
            sid = catalog[eid]["source_id"]
            if sid not in order:
                order.append(sid)
    return {sid: i + 1 for i, sid in enumerate(order)}


def source_notes(cfg, numbering, sources, as_of_year):
    notes_cfg = cfg["source_notes"]
    by_country = {}
    old = []
    for sid, n in sorted(numbering.items(), key=lambda kv: kv[1]):
        s = sources[sid]
        if s.get("country"):
            by_country.setdefault(s["country"], []).append(n)
        if s.get("year") and as_of_year - s["year"] > notes_cfg["old_after_years"]:
            old.append((n, s["year"]))
    notes = []
    for country, nums in by_country.items():
        refs = ", ".join(f"[{n}]" for n in nums)
        notes.append(f"Nguồn {refs} được soạn cho bối cảnh {country}.")
    for n, year in old:
        notes.append(f"Nguồn [{n}] có năm tài liệu là {year}; một số thông tin có thể đã được cập nhật.")
    if len(numbering) == 1:
        notes.append(notes_cfg["single_source_note"])
    return notes


def render_answer(cfg, *, status, claims, catalog, sources, gap_topics, generic_gap, as_of_year, dev=True):
    """claims: final passing claims in output order (dicts with text, role, evidence_ids)."""
    lines = []
    if dev:
        lines.append(cfg["dev_banner"])
    opener = cfg["status_openers"].get(status)
    if status == "khong_du":
        claims = []
    if opener:
        lines.append(opener)
    numbering = number_sources(claims, catalog)

    def sentence(c):
        nums = []
        for eid in c["evidence_ids"]:
            n = numbering[catalog[eid]["source_id"]]
            if n not in nums:
                nums.append(n)
        return f"{c['text'].strip()} {_markers(sorted(nums))}"

    direct = [c for c in claims if c["role"] == "tra_loi_truc_tiep"]
    details = [c for c in claims if c["role"] != "tra_loi_truc_tiep"]
    if direct:
        lines.append(sentence(direct[0]))
    if details:
        lines.append(" ".join(sentence(c) for c in details))
    if status == "mot_phan":
        if gap_topics:
            lines.append(cfg["gap_sentence_prefix"] + "; ".join(gap_topics) + ".")
        if generic_gap or not gap_topics:
            lines.append(cfg["gap_sentence_generic"])
    notes = source_notes(cfg, numbering, sources, as_of_year) if claims else []
    if notes:
        lines.append(" ".join(notes))
    lines.append(cfg["disclaimer"]["text"] if claims else cfg["disclaimer_no_content"]["text"])

    used = {}
    for c in claims:
        for eid in c["evidence_ids"]:
            used.setdefault(catalog[eid]["source_id"], [])
            if eid not in used[catalog[eid]["source_id"]]:
                used[catalog[eid]["source_id"]].append(eid)
    source_list = []
    if numbering:
        lines.append("")
        lines.append("Nguồn:")
        for sid, n in sorted(numbering.items(), key=lambda kv: kv[1]):
            s = sources[sid]
            year = str(s["year"]) if s.get("year") else "không ghi năm"
            who = f" — {s['by']}" if s.get("by") else ""
            url = f" {s['url']}" if s.get("url") else ""
            lines.append(f"[{n}] {s['title']}{who} ({year}).{url}")
            eids = sorted(used[sid], key=lambda e: catalog[e]["start"])
            for eid in eids:
                lines.append(f'    Đoạn được dùng: "{catalog[eid]["quote"]}"')
            source_list.append(dict(number=n, source_id=sid, title=s["title"], by=s.get("by"), year=s.get("year"),
                                    url=s.get("url"), type_vi=s.get("type_vi"), country=s.get("country"),
                                    evidence=[dict(id=e, evidence_id=catalog[e]["evidence_id"], start=catalog[e]["start"],
                                                   end=catalog[e]["end"]) for e in eids]))
    return dict(text="\n".join(lines) + "\n", sources=source_list, notes=notes, review_status=cfg["review_status"])


def render_fixed(cfg, body, *, disclaimer=True, dev=True):
    lines = [cfg["dev_banner"]] if dev else []
    lines.append(body)
    if disclaimer:
        lines.append(cfg["disclaimer_no_content"]["text"])
    return dict(text="\n".join(lines) + "\n", sources=[], notes=[], review_status=cfg["review_status"])
