# P6 → Revit 4D (Claude Code skill)

Link a construction schedule to a building model and write it into Revit as 4D. Claude decides which model
elements each activity builds and writes down why. It asks the planner whenever the data can't decide, checks
the build order, and writes to Revit only after approval. When next month's schedule arrives, it keeps every
link that is still valid, re-maps only what changed, and shows in colour what moved.

![Revision changes view](docs/revision1-changes.png)

## Why

4D tools (Navisworks TimeLiner, Synchro, Dynamo scripts) only link automatically when the schedule and the
model share the same code. On real projects they don't, so someone links activities to elements by hand
and redoes it on every revision.

In 34 real building XERs (126,838 activities):
- only 31% of activity names say where the work is;
- the same name repeats ("Pour" ×6), with the location shown only by the date order;
- formwork, rebar and pour all build the same slab.

That decision is the part this skill does.

## What it does

| Step | What happens |
|---|---|
| 1. Start | Reads a P6 XER (`--xer`) or an MS Project XML (`--msp`) |
| 2. Read the model | Live from Revit through MCP (`execute_revit_code`), or from an IFC file (`ifc_read.py`) |
| 3. Understand | Writes `brief.md`: where location lives in the schedule, the build sequence, and how the model is organised |
| 4. Map | Claude writes `map_rules.py`. Every activity is either linked with a reason or marked "no elements" with a reason. Repeated rounds are settled with evidence or asked |
| 5. Check | Unknown or undecided items, milestones with elements, build order, and repeated rounds left unresolved |
| 6. Planner gate | Questions with options and defaults. `answer.py` applies the answers and re-runs the rules. `approval.json` is required |
| 7. Write | Writes `P6_Task_ID`, `P6_Activity`, `P6_Start`, `P6_Finish`, `P6_All_Activities`, `P6_Week` and `P6_Month` on every element, and reports new / changed / moved / cleared |
| 8. Views | "by month", "as of <date>" or weekly 3D views, plus an activity-summary schedule and an every-element schedule |
| Revision | `revise.py` keeps unchanged links and maps only what changed. The changes view shows delayed (red), earlier (green), new (blue) and unchanged (see-through grey) |

The full workflow for Claude is in [SKILL.md](SKILL.md).

## Results (details in [docs/RESULTS.md](docs/RESULTS.md))

**A real project (IFC + MS Project), blind against the real project team's own 4D links.**
The project is Schependomlaan, an apartment building in NL (public dataset, CC BY 4.0) with 121 activities and
3,505 elements.

- 3,504 of 3,505 elements placed, with 16 planner questions.
- **Structure: 80%** the same building activity as the team.
- **82%** of elements appear within 2 weeks of the team's date.
- 12 links fail the build-order check, against 64 in the team's own links.
- Façade, roof and finishes: about 40–50% the same. A planner still reviews these. Part of the gap is the team's own links being inconsistent.

**A real P6 schedule with a sample Revit model, live in Revit.**
- Two independent mappings agreed on 98.7% of elements.
- 649 elements written with 0 failures.
- On a month-2 revision, Revit's write report matched the prediction exactly: 10 new, 37 changed activity, 154 dates moved and 458 unchanged.

## Install

1. Copy this folder to `~/.claude/skills/p6-revit-4d` (or your project's `.claude/skills/`).
2. Python 3.10+. `pip install ifcopenshell` is needed only to read IFC models.
3. For Revit: a Revit MCP server that exposes `execute_revit_code` (IronPython through pyRevit), `set_active_view`
   and `get_revit_view`. Built and tested with the AutoConst Revit MCP, a fork of the open-source
   revit-mcp-server. With an IFC model, steps 1–6 work without Revit.

Then ask Claude: *"link this P6 schedule to the open Revit model"* (attach the .xer), or *"here's next
month's XER, update the 4D"*.

## Limits

- No public project publishes its P6 file together with its Revit model. Testing covered a real project as IFC + MS Project, and a real P6 schedule against a sample Revit model.
- Largest model tested: 3,505 elements.
- Links use Activity IDs, so renumbered activities show up as deleted and added.
- Revit doesn't allow parameters on stair balusters. They follow their railing and are hidden in 4D views.
- The skill links elements and writes dates. It doesn't create or change schedule logic.

## License

AutoConst Source Available License: free to use, including commercially within your own organisation. You may
not resell or rebrand it. See [LICENSE](LICENSE).

Built by Hamza Jabbar, [hamzajabbar.online](https://hamzajabbar.online)
