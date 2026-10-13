"""Revision mode: a new XER (monthly update) against an approved job.

    python revise.py --old outputs/<job> --xer new.xer --job outputs/<job>-rev1 [--elements new_elements.csv]

Matches activities by Activity ID (P6 keeps IDs across updates):
  unchanged  same ID, same name + WBS        -> links carried (dates may have moved)
  renamed    same ID, name or WBS changed    -> links carried, flagged REVIEW (scope may have changed)
  deleted    ID no longer in the schedule    -> links dropped; elements left with no activity are listed
  added      new ID                          -> must be mapped (only these go back to Claude)
Model changes (if --elements is a fresh dump): links to deleted elements are dropped; new elements listed.
Answers to planner questions and no-element decisions are carried over.

Writes in the new job: schedule.csv, elements.csv, carried.csv, decisions_carried.json, answers.json,
changes.md, changes.json. Then: write map_rules.py that calls job.carry() and maps only what changed.
"""
import argparse, collections, datetime as dt, os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import read_schedule, read_csv, write_csv, read_mapping, write_mapping, load_json, save_json
from start import FIELDS


def days(a, b):
    try: return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days
    except ValueError: return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True); ap.add_argument("--xer", required=True); ap.add_argument("--job", required=True)
    ap.add_argument("--elements", default="")
    a = ap.parse_args()
    os.makedirs(a.job, exist_ok=True)
    new, meta = read_schedule(a.xer)
    write_csv(os.path.join(a.job, "schedule.csv"), new, FIELDS)
    shutil.copy(a.xer, os.path.join(a.job, "schedule.xer"))
    meta["revision_of"] = os.path.abspath(a.old)
    old_meta = load_json(os.path.join(a.old, "schedule_meta.json"), {}) or {}
    if old_meta.get("week_zero"):
        meta["week_zero"] = old_meta["week_zero"]
    save_json(os.path.join(a.job, "schedule_meta.json"), meta)

    old = {r["activity_id"]: r for r in read_csv(os.path.join(a.old, "schedule.csv"))}
    newd = {r["activity_id"]: r for r in new}
    oldM = read_mapping(os.path.join(a.old, "mapping.csv"))
    oldD = load_json(os.path.join(a.old, "decisions.json"), {}) or {}

    # model
    old_els = read_csv(os.path.join(a.old, "elements.csv"))
    els_src = a.elements or os.path.join(a.old, "elements.csv")
    new_els = read_csv(els_src)
    shutil.copy(els_src, os.path.join(a.job, "elements.csv"))
    og, ng = {e["guid"] for e in old_els}, {e["guid"] for e in new_els}
    gone_els, new_el_ids = og - ng, ng - og

    unchanged, renamed, moved = [], [], []
    for x in newd:
        if x in old:
            if old[x]["name"] != newd[x]["name"] or old[x]["wbs"] != newd[x]["wbs"]:
                renamed.append(x)
            else:
                unchanged.append(x)
            ds, df = days(old[x]["start"], newd[x]["start"]), days(old[x]["finish"], newd[x]["finish"])
            if ds or df:
                moved.append((x, ds, df))
    added = [x for x in newd if x not in old]
    deleted = [x for x in old if x not in newd]

    carried = {x: {g for g in oldM[x] if g in ng} for x in oldM if x in newd}
    carried = {x: gs for x, gs in carried.items() if gs}
    write_mapping(os.path.join(a.job, "carried.csv"), carried)
    empty = {x: r for x, r in (oldD.get("no_elements") or {}).items() if x in newd}
    save_json(os.path.join(a.job, "decisions_carried.json"),
              {"no_elements": empty, "reasons": {x: r for x, r in (oldD.get("reasons") or {}).items() if x in carried}})
    if os.path.exists(os.path.join(a.old, "questions.json")):
        shutil.copy(os.path.join(a.old, "questions.json"), os.path.join(a.job, "questions_carried.json"))
    if os.path.exists(os.path.join(a.old, "answers.json")):
        shutil.copy(os.path.join(a.old, "answers.json"), os.path.join(a.job, "answers.json"))

    still = {g for gs in carried.values() for g in gs}
    orphans = {g for x in deleted for g in oldM.get(x, set()) if g in ng and g not in still}
    el = {e["guid"]: e for e in new_els}
    grp = lambda gs: ", ".join(f"{k} x{v}" for k, v in collections.Counter(
        f"{el[g]['level'] or '-'} / {el[g]['category']}" for g in gs if g in el).most_common(5))
    affected = sum(len(carried.get(x, ())) for x, _, _ in moved)

    old_name, new_name = os.path.basename(os.path.normpath(a.old)), os.path.basename(os.path.normpath(a.job))
    L = [f"# Schedule revision: {old_name} -> {new_name}", "",
         f"Activities: {len(old)} -> {len(newd)} | unchanged {len(unchanged)} | renamed {len(renamed)} | "
         f"added {len(added)} | deleted {len(deleted)} | dates moved {len(moved)} (affecting {affected} linked elements)",
         f"Model: {len(og)} -> {len(ng)} elements | removed {len(gone_els)} | new {len(new_el_ids)}",
         f"Links carried: {sum(len(v) for v in carried.values())} on {len(carried)} activities", "",
         "## Added activities (map these)", ""]
    L += [f"- {x} | {newd[x]['name']} | {newd[x]['wbs']} | {newd[x]['start']} > {newd[x]['finish']}" for x in added] or ["- none"]
    L += ["", "## Renamed / moved in WBS (links carried, REVIEW scope)", ""]
    L += [f"- {x} | '{old[x]['name']}' -> '{newd[x]['name']}'" + (f" | WBS '{old[x]['wbs']}' -> '{newd[x]['wbs']}'" if old[x]['wbs'] != newd[x]['wbs'] else "")
          + f" | {len(carried.get(x, ()))} elements" for x in renamed] or ["- none"]
    L += ["", "## Deleted activities", ""]
    L += [f"- {x} | {old[x]['name']} | had {len(oldM.get(x, ()))} elements" for x in deleted] or ["- none"]
    L += ["", f"## Elements left with no activity after deletions ({len(orphans)}) - re-map or confirm", "", f"- {grp(orphans)}" if orphans else "- none"]
    L += ["", f"## New model elements ({len(new_el_ids)}) - map", "", f"- {grp(new_el_ids)}" if new_el_ids else "- none"]
    L += ["", "## Dates moved", "", "| activity | name | start shift (d) | finish shift (d) | elements |", "|---|---|---|---|---|"]
    L += [f"| {x} | {newd[x]['name']} | {ds:+d} | {df:+d} | {len(carried.get(x, ()))} |" for x, ds, df in sorted(moved, key=lambda t: -abs(t[1]))]
    open(os.path.join(a.job, "changes.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    save_json(os.path.join(a.job, "changes.json"), {"added": added, "renamed": renamed, "deleted": deleted,
              "moved": moved, "orphans": sorted(orphans), "new_elements": sorted(new_el_ids), "removed_elements": sorted(gone_els)})
    print("\n".join(L[2:5]))
    print(f"to map: {len(added)} added activities, {len(renamed)} renamed to review, {len(orphans)} orphaned + {len(new_el_ids)} new elements")


if __name__ == "__main__":
    main()
