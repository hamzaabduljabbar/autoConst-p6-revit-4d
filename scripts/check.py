"""Step 5: validate the mapping before anything is written to Revit.

    python check.py --job outputs/<job>

ERRORS (block writing): unknown activity ids or element guids, milestones with elements,
activities neither linked nor declared no-elements.
WARNINGS (show the planner): build-order violations, unlinked elements, linked LOE/WBS-summary rows.
Build order: an element is "built" at the start of its earliest activity. Non-structural elements on a
level must not be built before that level's structure (columns/framing/foundations/structural floors) starts.
Writes check.md. Exit code 1 if there are errors.
"""
import argparse, collections, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import read_csv, read_mapping, load_json

STRUCTURE = {"Structural Columns", "Structural Framing", "Structural Foundations", "Columns"}
STANDS_ON = {"Walls", "Doors", "Windows", "Stairs", "Railings", "Plumbing Fixtures", "Ceilings",
             "Generic Models", "Furniture", "Casework", "Mechanical Equipment", "Specialty Equipment",
             "Electrical Fixtures", "Lighting Fixtures", "Curtain Panels", "Curtain Wall Mullions"}
# the same for models read from IFC (ifc_read.py: category = IFC class without "Ifc")
STRUCTURE |= {"Column", "Footing", "Pile"}
STANDS_ON |= {"Wall", "WallStandardCase", "Door", "Window", "Stair", "StairFlight", "Railing", "CurtainWall",
              "Covering", "FurnishingElement", "FlowTerminal", "BuildingElementProxy"}
FLOORS = {"Floors", "Slab"}


def primary(mapping, acts):
    first = {}
    for a, gs in mapping.items():
        for g in gs:
            if g not in first or (acts[a]["start"], a) < (acts[first[g]]["start"], first[g]):
                first[g] = a
    return first


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--job", required=True); ap.add_argument("--mapping", default="mapping.csv")
    a = ap.parse_args()
    S = read_csv(os.path.join(a.job, "schedule.csv")); acts = {r["activity_id"]: r for r in S}
    E = read_csv(os.path.join(a.job, "elements.csv")); els = {e["guid"]: e for e in E}
    M = read_mapping(os.path.join(a.job, a.mapping))
    dec = load_json(os.path.join(a.job, "decisions.json"), {}) or {}
    empty = dec.get("no_elements", {})
    errors, warns = [], []

    bad_a = [x for x in M if x not in acts]
    bad_g = {g for gs in M.values() for g in gs if g not in els}
    if bad_a: errors.append(f"{len(bad_a)} activity ids not in the schedule: {bad_a[:10]}")
    if bad_g: errors.append(f"{len(bad_g)} element guids not in the model (deleted/changed?): {sorted(bad_g)[:5]}")
    M = {x: {g for g in gs if g in els} for x, gs in M.items() if x in acts}
    miles = [x for x in M if acts[x]["type"] in ("TT_Mile", "TT_FinMile") and M[x]]
    if miles: errors.append(f"milestones with elements: {miles}")
    undecided = [x for x in acts if x not in M and x not in empty]
    if undecided: errors.append(f"{len(undecided)} activities neither linked nor declared no-elements: {undecided[:15]}")
    soft = [x for x in M if acts[x]["type"] in ("TT_LOE", "TT_WBS")]
    if soft: warns.append(f"level-of-effort / WBS-summary activities with elements (check intent): {soft}")

    # build order
    first = primary(M, acts)
    struct_start = {}
    for g, x in first.items():
        e = els[g]
        if e["category"] in STRUCTURE or (e["category"] in FLOORS and e["structural"] in ("Yes", "1", "True")):
            s = acts[x]["start"]
            if e["level"] and (e["level"] not in struct_start or s < struct_start[e["level"]][0]):
                struct_start[e["level"]] = (s, x)
    viol = collections.Counter()
    for g, x in first.items():
        e = els[g]
        if e["category"] in STANDS_ON and e["level"] in struct_start and acts[x]["start"] < struct_start[e["level"]][0]:
            s, sx = struct_start[e["level"]]
            viol[(x, acts[x]["name"], acts[x]["start"], e["level"], e["category"], s, sx)] += 1
    for (x, n, st, lvl, cat, s, sx), c in viol.most_common():
        warns.append(f"build order: {x} {n} ({st}) builds {c} {cat} on {lvl}, but that level's structure starts {s} ({sx})")

    # repeated rounds linked without a planner question that covers them
    qs = load_json(os.path.join(a.job, "questions.json"), []) or []
    dec = load_json(os.path.join(a.job, "decisions.json"), {}) or {}
    asked = {x for q in qs + (dec.get("rounds_settled") or []) for x in q.get("about", [])}
    names = collections.defaultdict(list)      # same name AND same WBS/codes = location only in the date order
    for x, r in acts.items():
        names[(" ".join(r["name"].lower().split()), r["wbs"], r.get("codes", ""))].append(x)
    for nm, ids in names.items():
        linked = [x for x in ids if M.get(x)]
        if len(linked) >= 2 and not set(linked) <= asked:
            warns.append(f"repeated rounds not asked: '{acts[ids[0]]['name']}' x{len(ids)} ({', '.join(sorted(linked))}) - "
                         "settle with evidence (job.settle) or ask the planner (job.ask(..., about=[...]))")

    unl = collections.Counter(f"{e['level'] or '-'} / {e['category']}" for e in E if e["guid"] not in first)
    n_links = sum(len(v) for v in M.values())
    L = ["# Mapping check", "",
         f"Activities {len(acts)}: linked {len(M)}, no-elements {len(empty)}, undecided {len(undecided)}",
         f"Links {n_links}; elements linked {len(first)} of {len(E)}", "",
         f"## Errors ({len(errors)})", ""] + [f"- {x}" for x in errors] + ["", f"## Warnings ({len(warns)})", ""] + \
        [f"- {x}" for x in warns] + ["", "## Elements in no activity", ""] + [f"- {k}: {v}" for k, v in unl.most_common()] + \
        ["", "## Structure start per level", ""] + [f"- {k}: {v[0]} ({v[1]})" for k, v in sorted(struct_start.items(), key=lambda kv: kv[1])]
    open(os.path.join(a.job, "check.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"check: {len(errors)} errors, {len(warns)} warnings, {len(first)}/{len(E)} elements linked, "
          f"{len(undecided)} undecided -> check.md")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
