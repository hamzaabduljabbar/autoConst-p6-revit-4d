---
name: p6-revit-4d
description: Link a Primavera P6 schedule (XER) to the elements of the open Revit model and write it in as 4D - P6_Task_ID, activity, start/finish, week and month on every element, plus coloured "build by month" and "as of <date>" 3D views and two schedules. Claude reads both sides, maps every activity to elements with a reason (or declares it has none), asks the planner about anything the data can't settle and applies the answers, checks build order, and only writes to Revit after approval. Revision mode takes the next month's XER, carries all unchanged links, maps only what changed, reports which elements moved and colours them in a "changes" 3D view (red = delayed, blue = newly scheduled, grey = unchanged). Use when someone wants 4D / construction sequencing / schedule-to-model linking / timeliner-style linking in Revit, wants to colour a model by schedule, or has an updated P6 schedule to push into an already-linked model. Requires a Revit MCP with execute_revit_code (e.g. AutoConst Revit MCP) and the model open; an IFC model (and P6 XER or MS Project XML) works for mapping without Revit.
---

# P6 → Revit 4D

The hard part of 4D is not the animation, it is deciding **which model elements each activity builds**
when the schedule and the model were made by different people with different breakdowns (location in
the WBS, repeated names like "Pour" x6, formwork/rebar/pour on the same slab, activities with nothing
modelled). This skill does that decision with a reason per activity, asks the planner when the data
can't decide, and keeps it working through monthly schedule updates.

Tested on: a real apartment project (real schedule + model + the real team's links: Claude matched
the team as closely as hand-tuned rules, with far fewer build-order errors) and a real P6 villa schedule
against a Revit house (two independent runs agreed on 98.7% of elements). See `docs/RESULTS.md`.

Scripts are in `scripts/` (this skill's folder, called `<S>` below). Use any Python 3.10+ (`python`).
Job folder = `outputs/<job>` in the user's working folder.

## Steps

**1. Start** - `python <S>/scripts/start.py --xer <file.xer> --job outputs/<job>` (or `--msp <file.xml>` for an MS Project XML)
   (schedule.csv). If the user gives a CSV/Excel schedule instead, write schedule.csv with the same columns.

**2. Read the model** - `python <S>/scripts/revit_code.py --job outputs/<job> --step dump`, then run it with the
   Revit MCP `execute_revit_code`, passing this two-line loader as `code` (not the whole file):
   ```
   import System
   exec(System.IO.File.ReadAllText(r"<absolute job path>\revit_dump.py").replace("\r\n", "\n"), globals())
   ```
   Produces elements.csv. (Same loader for revit_write.py and revit_views.py.)
   Read live; do not export IFC (slow, can lock Revit). If the MCP times out, Revit has a dialog open: ask the
   user to close it.

   **No Revit / model only as IFC:** `python <S>/scripts/ifc_read.py --ifc <model.ifc> --job outputs/<job>`
   (needs `pip install ifcopenshell`) writes the same elements.csv (category = IFC class, level = authoring
   home story if present). Steps 3-6 work the same; steps 7-8 need Revit. It never reads IfcTask data.

**3. Understand both sides** - `python <S>/scripts/profile.py --job outputs/<job>`, then READ brief.md fully.
   Work out: where location lives in the schedule (WBS path, activity codes, or only date order for repeated
   names); the build sequence; which activities are physical; how the model is organised (levels, buildings
   by cx/cy, what is and is not modelled, e.g. finish floors but no structural slabs).

**4. Write the mapping as rules** - create `outputs/<job>/map_rules.py`:
   ```python
   import sys; sys.path.insert(0, r"<S>/scripts")
   from maplib import Job
   job = Job(__file__)
   job.link("A1010", job.sel(category="Structural Columns", level="01_Ground Floor"), "GF columns")
   job.no_elements("A1000", "mobilisation, not modelled")
   choice = job.ask("Q1", "question", options={"a": "...", "b": "..."}, default="a", why="...", candidates=[...])
   job.settle(job.rounds("Pour"), "one floor per round, bottom-up", "4 pours = 4 slabs; each pour follows that floor's rebar")
   job.save()
   ```
   then `python outputs/<job>/map_rules.py`. Rules (from the tests):
   - Every activity is either `link`ed or `no_elements` with a reason. `job.save()` lists UNDECIDED ones.
   - Read location from the **WBS path / codes**, never the name alone.
   - **Repeated rounds** (same name, same WBS/codes, e.g. "Masonry" x3): the location is only in the date order,
     and "round n = floor n" is an assumption, not a fact. Crews often work by facade side, wing/zone or
     scaffold lift, or make several passes over the same elements. For every such set
     (`job.repeated()`, `ids = job.rounds("Masonry")`), list the plausible splits and test them on the
     elements with `job.split(guids, by="level" | "side" | "x" | "y", n)`:
     - `job.settle(ids, how, evidence)` only when the data decides it: the number of rounds equals the number
       of locations that have that work, AND the dates follow the order the locations become available
       (each round right after that floor's pour, or a predecessor chain). Typical: concrete cycles.
     - otherwise `job.ask(qid, ..., about=ids)` with each plausible split as an option and the best fit as
       default. Typical: facade (masonry, frames, cladding), roof, finishes, railings. Rounds count ≠
       locations count is always a question.
     check.py warns about any set that is neither settled nor asked. rationale.md shows each round's split.
   - Steps of the same work (formwork, rebar, pour; 1st/2nd fix) link to the **same elements**.
   - Purpose beats home level: read type/family names (e.g. roof steel modelled on the floor below is still
     roof steel).
   - Finishing trades (plaster, paint, insulation) are extra links on elements already built; an element's
     building activity is its earliest one.
   - Non-physical rows (approvals, procurement, audits, milestones, setting out, scaffold) → `no_elements`.
   - **Never guess silently.** Anything the data can't settle (which building a schedule group is, scaffold
     lifts, whether a trade applies to drywall, model/schedule system mismatch) → `job.ask(...)` with a
     sensible default, the options, and the candidate elements. Each option must change the rules.

**5. Check** - `python <S>/scripts/check.py --job outputs/<job>`. Fix every ERROR (unknown ids, undecided
   activities, milestones with elements). Fix build-order warnings that are mapping mistakes; the ones
   caused by the schedule's own logic stay as findings for the planner.

**6. Planner review + answers (the gate)** - show the user: the summary line, the questions
   (questions.md), check warnings, and the elements in no activity. **Ask the questions with
   AskUserQuestion** (max 4 per call; options = the question's options, default first marked
   "(default)"). Apply answers with
   `python <S>/scripts/answer.py --job outputs/<job> Q1=<option> Q2=<option>` - this records answers.json
   and re-runs map_rules.py. Re-run check.py. Repeat until the user approves, then write
   `outputs/<job>/approval.json` = `{"approved_by": "<user>", "date": "<today>", "note": "..."}`.
   Questions the user leaves open keep their default and stay listed as defaults.

**7. Write to Revit** - `python <S>/scripts/values.py --job outputs/<job>`, then
   `python <S>/scripts/revit_code.py --job outputs/<job> --step write` and run `revit_write.py` via
   execute_revit_code (loader as in step 2). Creates/updates P6_Task_ID, P6_Activity, P6_Start, P6_Finish, P6_All_Activities,
   P6_Week, P6_Month (group "AutoConst 4D", instance, Data), clears them on elements no longer mapped, and
   reports new / moved / changed counts (revit_write_report.json). Balusters can't hold parameters in
   Revit; they follow their railing and are hidden in 4D views.

**8. Views** - `python <S>/scripts/revit_code.py --job outputs/<job> --step views` (4 snapshot dates
   across the job) or `--dates 2025-03-31,...` or `--weekly` (one view per week, for video frames). Run
   `revit_views.py`. Creates "AutoConst 4D - by month", "AutoConst 4D - as of <date>" / "week NN", and
   schedules "AutoConst 4D - activity summary" + "every element". Then `set_active_view` to "AutoConst
   4D - by month" and `get_revit_view` to show the user. Views hide categories with nothing mapped (topography,
   site) and crop to the building; month colours are fixed from week 1, so before/after views of two revisions
   compare directly (use the same `--dates` for both). Do not save the Revit file unless asked.

## Revision mode (next month's XER)

1. Re-read the model (step 2) into a temp file if it may have changed, then
   `python <S>/scripts/revise.py --old outputs/<job> --xer <new.xer> --job outputs/<job>-<rev> [--elements <fresh elements.csv>]`
2. Read changes.md: added / renamed (review scope) / deleted activities, orphaned and new elements,
   date moves with how many elements each affects.
3. Write `outputs/<job>-<rev>/map_rules.py` that starts with `job = Job(__file__).carry()` and only handles
   what changed (earlier questions and answers are carried: re-`ask` only if a question's options change): link added activities, `unlink`/re-link renamed ones whose scope changed, re-home
   orphaned elements or `ask`. Previous answers are carried in answers.json; reuse the same question ids
   so nobody is asked twice.
4. Steps 5-8 as normal (approval = show the user changes.md in plain words and ask). Week numbers stay
   anchored to the first approved version (week_zero in schedule_meta.json). The write report
   (revit_write_report.json) must match the expected changes: new / activity_changed / dates_moved / cleared.
5. Show what moved: `python <S>/scripts/revit_code.py --job outputs/<job>-<rev> --step changes --old outputs/<job>`
   and run `revit_changes.py`. One 3D view "AutoConst 4D - changes <old> to <new>": red = starts later,
   green = earlier, blue = newly scheduled, orange = other activity, magenta = no longer scheduled,
   see-through grey = unchanged (so interior changes show through). Also writes element_changes.csv.
   Use this to show a revision, not two "as of" views: delays often hit interior work that a snapshot hides.

## Report to the user
Activities linked / no-elements, links, elements linked of total, the questions with the answers used,
build-order findings, what is in no activity and why, and (revisions) what changed. Plain words, not file
dumps. Say what was written to Revit and that the file is not saved.

## Limits
- Links use Activity IDs: if a planner renumbers activities, revise.py sees delete + add (it says so).
- One model = one building-set mapping; multiple schedule groups for repeated buildings are a planner
  question (map all to one, or split by building with cx/cy).
- Uses each activity's current start/finish (actual if started, else early/remaining, else planned).
