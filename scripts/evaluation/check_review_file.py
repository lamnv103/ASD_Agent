"""Blind helpers for a manual review file. Never reads the key, so arms stay hidden.

  python -B scripts/evaluation/check_review_file.py CRITERIA REVIEW          # one review: complete and valid?
  python -B scripts/evaluation/check_review_file.py CRITERIA TEAM MODEL      # two reviews: list every disagreement

Checks against the blind sheet named in CRITERIA: every review_id exactly once, no extra rows, the claim
text unchanged, concepts a list of the row's concept_choices, each field one of the registered values.
The judge (measure_repair.py --judge) still does the full check with the key; this only lets the team
find mistakes before committing and see the disagreements to adjudicate, without unblinding.
Exit 0 = valid (and, for two files, both valid), 2 = problems.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIELDS = ("concepts", "term_correct", "faithful", "contains_known_wrong_content")


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def problems(crit, sheet, review):
    values = crit["review"]["values"]
    by_id = {r["review_id"]: r for r in sheet}
    out = []
    if not isinstance(review, list):
        return ["review file must be a JSON list of rows (copy review_sheet.json and fill it in)"]
    ids = [x.get("review_id") for x in review]
    out += [f"{rid}: appears more than once" for rid in sorted({i for i in ids if ids.count(i) > 1})]
    out += [f"{rid}: not on the sheet" for rid in sorted(set(ids) - set(by_id))]
    out += [f"{rid}: missing" for rid in sorted(set(by_id) - set(ids))]
    for x in review:
        rid = x.get("review_id")
        row = by_id.get(rid)
        if row is None:
            continue
        if x.get("text") != row["text"]:
            out.append(f"{rid}: claim text differs from the sheet (do not edit text)")
        allowed = {c["id"] for c in row["concept_choices"]}
        c = x.get("concepts")
        if not (isinstance(c, list) and set(c) <= allowed and len(c) == len(set(c))):
            out.append(f"{rid}: concepts must be a list (may be empty) of {sorted(allowed)}, got {c!r}")
        for f in FIELDS[1:]:
            if x.get(f) not in values[f]:
                out.append(f"{rid}: {f} must be one of {values[f]}, got {x.get(f)!r}")
    return out


def main(argv):
    if len(argv) not in (2, 3):
        print(__doc__)
        return 2
    crit = load(argv[0])
    sheet = load(crit["review"]["sheet"])
    reviews = [load(p) for p in argv[1:]]
    bad = False
    for path, review in zip(argv[1:], reviews):
        p = problems(crit, sheet, review)
        print(f"{path}: {'OK, ' + str(len(sheet)) + ' rows valid' if not p else str(len(p)) + ' problem(s)'}")
        for line in p:
            print("  " + line)
        bad = bad or bool(p)
    if bad or len(reviews) == 1:
        return 2 if bad else 0
    a, b = ({x["review_id"]: x for x in r} for r in reviews)
    norm = lambda v: sorted(v) if isinstance(v, list) else v
    diff = [(rid, f, a[rid][f], b[rid][f]) for rid in sorted(a) for f in FIELDS if norm(a[rid][f]) != norm(b[rid][f])]
    print(f"disagreements: {len(diff)} field(s) on {len({d[0] for d in diff})} of {len(a)} rows")
    for rid, f, x, y in diff:
        print(f"  {rid} {f}: {Path(argv[1]).stem}={x!r}  {Path(argv[2]).stem}={y!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
