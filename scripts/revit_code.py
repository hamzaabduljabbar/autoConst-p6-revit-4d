"""Generate ready-to-run IronPython for the AutoConst Revit MCP (execute_revit_code).

    python revit_code.py --job outputs/<job> --step dump
    python revit_code.py --job outputs/<job> --step write
    python revit_code.py --job outputs/<job> --step views [--weekly | --dates 2013-03-31,2013-05-31]
    python revit_code.py --job outputs/<job>-rev1 --step changes --old outputs/<job>   (revision: one view of what moved)

Writes <job>/revit_<step>.py. Pass that file's full text as `code` to execute_revit_code.
Without --dates/--weekly, snapshot dates = 4 evenly spaced dates across the mapped activities.
"""
import argparse, datetime as dt, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_json

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--step", required=True, choices=["dump", "write", "views", "changes"])
    ap.add_argument("--weekly", action="store_true")
    ap.add_argument("--dates", default="")
    ap.add_argument("--old", default="", help="changes step: the previous approved job")
    a = ap.parse_args()
    job = os.path.abspath(a.job)
    src = open(os.path.join(HERE, "revit", a.step + ".py"), encoding="utf-8").read()
    src = src.replace("__JOB__", job).replace("__SKILL__", SKILL)
    if a.step == "write" and not os.path.exists(os.path.join(job, "revit_values.json")):
        sys.exit("run values.py first")
    if a.step == "views":
        dates = [d for d in a.dates.split(",") if d]
        if not dates and not a.weekly:
            v = load_json(os.path.join(job, "revit_values.json"), {}) or {}
            s = sorted({x["start"] for x in v.values()}); f = sorted({x["finish"] for x in v.values()})
            if s:
                d0, d1 = dt.date.fromisoformat(s[0]), dt.date.fromisoformat(f[-1])
                dates = [(d0 + (d1 - d0) * k / 4).isoformat() for k in (1, 2, 3, 4)]
        src = src.replace("__MODE__", "weekly" if a.weekly else "snapshots").replace("__DATES__", json.dumps(dates))
    if a.step == "changes":
        if not a.old:
            sys.exit("--old <previous job> is required for --step changes")
        old = load_json(os.path.join(a.old, "revit_values.json"), {}) or {}
        new = load_json(os.path.join(job, "revit_values.json"), {}) or {}
        cls, rows = {}, []
        for g in set(old) | set(new):
            o, n = old.get(g), new.get(g)
            if o and not n: c = "unscheduled"
            elif n and not o: c = "new"
            elif n["start"] > o["start"]: c = "later"
            elif n["start"] < o["start"]: c = "earlier"
            elif n["id"] != o["id"]: c = "activity"
            else: c = "unchanged"
            cls[g] = c
            rows.append([g, c, (o or {}).get("id", ""), (o or {}).get("start", ""), (n or {}).get("id", ""), (n or {}).get("start", "")])
        import csv
        with open(os.path.join(job, "element_changes.csv"), "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh); w.writerow(["guid", "change", "old_activity", "old_start", "new_activity", "new_start"])
            w.writerows(sorted(rows, key=lambda r: (r[1], r[4], r[0])))
        import collections
        print("element changes:", dict(collections.Counter(cls.values())))
        src = (src.replace("__CLASSES__", json.dumps(cls)).replace("__OLD__", os.path.basename(os.path.normpath(a.old)))
               .replace("__NEW__", os.path.basename(os.path.normpath(job))))
    out = os.path.join(job, f"revit_{a.step}.py")
    open(out, "w", encoding="utf-8", newline="\n").write(src)
    print(out)


if __name__ == "__main__":
    main()
