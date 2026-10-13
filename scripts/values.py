"""Step 7: turn the approved mapping into the values written on each Revit element.

    python values.py --job outputs/<job>

Writes revit_values.json {guid: {id, name, start, finish, all, week, month}}.
"id" = the element's building activity = its earliest linked activity. "all" = every linked activity.
Week 1 = the week of the earliest linked activity's start in the first approved version (kept in schedule_meta.json). Refuses to run if approval.json is missing.
"""
import argparse, datetime as dt, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import read_csv, read_mapping, load_json, save_json


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--job", required=True); a = ap.parse_args()
    if not load_json(os.path.join(a.job, "approval.json")):
        sys.exit("not approved: show the planner rationale.md / questions.md / check.md, then write approval.json")
    acts = {r["activity_id"]: r for r in read_csv(os.path.join(a.job, "schedule.csv"))}
    M = read_mapping(os.path.join(a.job, "mapping.csv"))
    per = {}
    for x, gs in M.items():
        for g in gs:
            per.setdefault(g, []).append(x)
    meta_p = os.path.join(a.job, "schedule_meta.json")
    meta = load_json(meta_p, {}) or {}
    if meta.get("week_zero"):        # fixed by the first approved version, so week numbers stay stable across revisions
        d0 = dt.date.fromisoformat(meta["week_zero"])
    else:
        starts = [acts[x]["start"] for x in M if acts.get(x, {}).get("start")]
        d0 = dt.date.fromisoformat(min(starts)); d0 -= dt.timedelta(days=d0.weekday())
        meta["week_zero"] = d0.isoformat(); save_json(meta_p, meta)
    out = {}
    for g, xs in per.items():
        xs = sorted((x for x in xs if x in acts), key=lambda x: (acts[x]["start"], x))
        if not xs:
            continue
        b = acts[xs[0]]
        out[g] = {"id": xs[0], "name": b["name"], "start": b["start"], "finish": b["finish"], "all": ";".join(xs),
                  "week": (dt.date.fromisoformat(b["start"]) - d0).days // 7 + 1, "month": b["start"][:7]}
    save_json(os.path.join(a.job, "revit_values.json"), out)
    print(f"revit_values.json: {len(out)} elements, weeks 1-{max(v['week'] for v in out.values())}, week 1 = {d0}")


if __name__ == "__main__":
    main()
