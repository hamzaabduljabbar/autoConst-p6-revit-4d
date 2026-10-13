# P6 → Revit 4D skill: brief (13 Oct 2026)

## What we built
A Claude Code skill, `p6-revit-4d`, that links a construction schedule to a building model and writes the result into Revit as 4D.

- **Inputs:** a schedule (Primavera P6 XER or MS Project XML) and a model (live Revit through the AutoConst Revit MCP, or an IFC file).
- **Outputs:**
  - every element carries P6_Task_ID, activity, start, finish, all activities, week and month;
  - coloured 3D views: "by month", "as of <date>", and weekly views for video;
  - two Revit schedules;
  - for a schedule update, a "changes" view: red = delayed, green = earlier, blue = newly scheduled, grey = unchanged.

## Why it matters
- **4D tools only link automatically when the schedule and the model share the same code.** Navisworks TimeLiner, Synchro and Dynamo all work that way. In real projects they don't share codes: the schedule is organised by work and location, and the model by element and level.
- **So the real work is a person deciding which elements each activity builds,** activity by activity, then redoing it every time the schedule changes.
- **Real schedules make that hard.** In 34 real building XERs (126,838 activities):
  - only 31% of activity names say where the work is; the rest leave it to the WBS or codes;
  - at least 14% of activities aren't physical (approvals, procurement, milestones);
  - the same name repeats ("Pour" ×6), and the location shows only in the date order;
  - formwork, rebar and pour all build the same slab.

## What it does, step by step
1. **Reads both sides:** the schedule, and the model straight from Revit or an IFC file (no slow export).
2. **Understands the structure:** where the location lives in the schedule, the build sequence, which activities are physical, and how the model is organised.
3. **Maps every activity, as re-runnable rules:**
   - each activity is linked to elements with a written reason, or marked "no elements" with a reason;
   - repeated rounds (the same name with no location) are either settled with evidence, such as round count = floor count plus predecessor chains, or asked.
4. **Asks the planner** about anything the data can't decide. Each question has options and a default. Answers are applied straight away, saved, and never asked again.
5. **Checks the result:**
   - no unknown or undecided items;
   - no milestones with elements;
   - build order: nothing scheduled before the floor it stands on;
   - every set of repeated rounds was either settled or asked.
6. **Approval gate:** nothing is written to Revit until the planner approves.
7. **Writes to Revit and builds the views and schedules.** Revit reports the counts of new, changed and moved elements.
8. **Revision mode** for the next month's schedule:
   - finds added, renamed, deleted and moved activities;
   - keeps every unchanged link;
   - maps only what changed;
   - checks Revit's write counts against the prediction;
   - builds the changes view.

## Real results

### Test A: a real project (IFC model + MS Project schedule), blind
- **Data:** Schependomlaan, an apartment building in Nijmegen, NL, built in 2015 and public under CC BY 4.0. It comes with the real schedule (121 activities), the real model (3,505 elements) and **the real project team's own 4D links**, which served as the answer key.
- **Blind setup:** a fresh agent got only the skill, the schedule and the element list. It never saw the team's links.
- **What it produced:**
  - 82 activities linked, 39 marked "no elements" with reasons;
  - 3,504 of 3,505 elements placed (the one left out is the survey origin marker);
  - 16 planner questions;
  - 0 errors.

| Compared with the real team's links | Result |
|---|---|
| Structure (foundations, concrete, steel, floors): same building activity | **80%** |
| Every element: same building activity | 54% |
| Element appears within 1 week / 2 weeks / 4 weeks of the team's date | 61% / **82%** / 89% |
| Activities with exactly the team's elements | 27 (the best of all runs) |
| Façade / roof / interior and finishes: same activity | 46% / 37% / 68% |
| Links that fail the build-order check | **12** (the team's own: 64) |

- **The planner questions:** answering them in each alternative way only lowered the match. The skill's defaults were already the best fit.
- **Why the façade scores low:** the team's own façade links are inconsistent. Round 2 holds two floors, round 3 is empty, and one floor's brick is linked to two rounds.
- **Run-to-run variation:** about 5 points between blind runs.

### Test B: a real P6 schedule + a sample Revit model, live in Revit
- **Data:** a real villa P6 schedule (96 activities) and the 3H house sample model in Revit (702 elements).
- **Consistency:** two independent blind mappings chose the same activity for 98.7% of elements.
- **Planner questions:** 6 asked and answered in chat. The answers were applied straight away; one of them ("one house per villa group") rebuilt the whole mapping.
- **Written to Revit:** 649 elements, 0 failures, plus the views and schedules.
- **Revision test** (next month's XER: a 14-day delay, a split activity, a deleted activity, a new one):
  - **Revit's own write report matched the prediction exactly:** 10 new, 37 changed activity, 154 dates moved, 458 unchanged.
  - Rolling back worked too: the 10 elements were cleared.
  - The changes view showed 190 delayed, 10 newly scheduled and 1 re-assigned element.

### Bugs found and fixed by testing
- Week numbers shifted after a revision, so they're now anchored to the first approved version.
- Month colours shifted between versions, so they're now fixed per month.
- The terrain swamped the 3D views, so the views now crop to the building.
- Windows line endings broke the script loader.
- The build-order check never ran on IFC models.
- Synchro's IFC export puts every element on one dummy floor, so the reader now takes the real floor from the authoring tool's data.
- A hint specific to one test project had slipped into the skill's instructions; it's been removed.

## Verdict
**Ready as "AI does the first pass with reasons and questions, the planner approves."**

- **Structure** is reliable.
- **Façade, roof and finishes** come out as a draft, and the skill shows the planner exactly what to check.

**Limits:**
- No public project publishes its P6 file together with its Revit model, so it was tested on:
  - a real project as IFC + MS Project;
  - a real P6 schedule against a sample Revit model.
- The largest model tested has 3,500 elements.
- Links use Activity IDs, so if the planner renumbers activities, they show up as deleted and added.
