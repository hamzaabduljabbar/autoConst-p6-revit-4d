"""Library used by a job's map_rules.py (written by Claude for each project).

map_rules.py describes the mapping as rules, not as a hand-typed list, so it can be re-run:
when the planner answers a question, when the schedule is revised, when the model changes.

    import sys; sys.path.insert(0, r"<skill>/scripts")
    from maplib import Job
    job = Job(__file__)                      # loads schedule.csv, elements.csv, answers.json
    walls = job.sel(category="Walls", level="02_First Floor")
    roof = job.ask("Q1", "Is the timber roof built in 'Roof slab' or separately?",
                   options={"roof_slab": "with Roof slab (V-1-120)", "none": "not in this schedule"},
                   default="roof_slab", why="schedule assumes a concrete roof; model has a pitched timber roof",
                   candidates=job.sel(category="Roofs"))
    if roof == "roof_slab":
        job.link("V-1-120", job.sel(category="Roofs"), "timber roof stands in for the roof slab")
    job.no_elements("A1200", "mobilisation, not modelled")
    job.save()                                # writes mapping.csv, rationale.md, questions.json/.md

Every activity must end up either linked or declared no_elements (job.save reports the rest).
"""
import collections, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import read_csv, write_csv, load_json, save_json  # noqa: E402


class Job:
    def __init__(self, rules_file):
        self.dir = os.path.dirname(os.path.abspath(rules_file))
        self.sched = read_csv(os.path.join(self.dir, "schedule.csv"))
        self.acts = {r["activity_id"]: r for r in self.sched}
        self.els = read_csv(os.path.join(self.dir, "elements.csv"))
        self.by_guid = {e["guid"]: e for e in self.els}
        self.answers = load_json(os.path.join(self.dir, "answers.json"), {}) or {}
        self.links = collections.defaultdict(set)      # activity -> guids
        self.reasons = collections.defaultdict(list)   # activity -> [(n, reason)]
        self.empty = {}                                 # activity -> reason
        self.questions = []
        self.settled = []                               # repeated rounds decided by the data, with evidence

    # ---- selecting elements --------------------------------------------------------------
    def sel(self, category=None, level=None, type=None, family=None, name_re=None, where=None,
            zmin=None, zmax=None, exclude=None):
        """Select element guids. category/level/type/family: exact string or list; type/family also
        accept a regex via name_re (matched against 'family : type'). where: f(element)->bool."""
        def ok(v, want):
            if want is None: return True
            return v in (want if isinstance(want, (list, tuple, set)) else [want])
        out = []
        rx = re.compile(name_re, re.I) if name_re else None
        excl = set(exclude or [])
        for e in self.els:
            if not ok(e["category"], category) or not ok(e["level"], level): continue
            if not ok(e["type"], type) or not ok(e["family"], family): continue
            if rx and not rx.search(f"{e['family']} : {e['type']}"): continue
            z = int(e["zmin"]) if e.get("zmin") not in (None, "") else None
            if zmin is not None and (z is None or z < zmin): continue
            if zmax is not None and (z is None or z > zmax): continue
            if where and not where(e): continue
            if e["guid"] in excl: continue
            out.append(e["guid"])
        return out

    def acts_like(self, name_re=None, wbs_re=None):
        """Activity ids whose name / wbs match regexes (case-insensitive)."""
        n = re.compile(name_re, re.I) if name_re else None
        w = re.compile(wbs_re, re.I) if wbs_re else None
        return [a for a, r in self.acts.items()
                if (not n or n.search(r["name"])) and (not w or w.search(r["wbs"]))]

    # ---- repeated rounds ---------------------------------------------------------------------
    def rounds(self, name_re):
        """Activities whose name matches, in date order: the 'rounds' of repeated work (Masonry x3 ...)."""
        n = re.compile(name_re, re.I)
        return sorted((a for a, r in self.acts.items() if n.search(r["name"])),
                      key=lambda a: (self.acts[a]["start"], a))

    def repeated(self):
        """{name: [activity ids in date order]} for every name used more than once with the SAME WBS and codes,
        i.e. rounds whose location is not written anywhere (only the date order tells them apart)."""
        c = collections.defaultdict(list)
        for a, r in self.acts.items():
            c[(re.sub(r"\s+", " ", r["name"].strip().lower()), r["wbs"], r.get("codes", ""))].append(a)
        return {k[0]: sorted(v, key=lambda a: (self.acts[a]["start"], a)) for k, v in c.items() if len(v) > 1}

    def settle(self, ids, how, evidence):
        """Record that the data itself decides how repeated rounds split (no planner question needed).
        how: e.g. "one floor per round, bottom-up". evidence: what proves it (round count = floors with that
        work, dates follow the pours, predecessor chain ...). Use ask(..., about=ids) instead when not decisive."""
        for a in ids:
            if a not in self.acts: raise KeyError(f"unknown activity {a}")
        self.settled.append({"about": list(ids), "how": how, "evidence": evidence})

    def split(self, guids, by="level", n=None):
        """Split elements into ordered groups, to try the possible meanings of repeated rounds:
        by="level": one group per level, bottom-up (by median zmin) -> [(level, [guids]), ...]
        by="side":  facade side by position against the plan extent of `guids` -> {"N"|"E"|"S"|"W": [guids]}
        by="x"/"y": n equal bands along that axis, low to high -> [[guids], ...]"""
        E = [self.by_guid[g] for g in guids if g in self.by_guid]
        num = lambda v: float(v) if v not in (None, "") else None
        if by == "level":
            grp = collections.defaultdict(list)
            for e in E: grp[e["level"]].append(e)
            def mz(es):
                z = sorted(num(e["zmin"]) for e in es if num(e["zmin"]) is not None)
                return z[len(z) // 2] if z else 0
            return [(lv, [e["guid"] for e in es]) for lv, es in sorted(grp.items(), key=lambda kv: mz(kv[1]))]
        P = [(e, num(e["cx"]), num(e["cy"])) for e in E if num(e["cx"]) is not None and num(e["cy"]) is not None]
        if not P: return {} if by == "side" else []
        x0, x1 = min(p[1] for p in P), max(p[1] for p in P)
        y0, y1 = min(p[2] for p in P), max(p[2] for p in P)
        if by == "side":
            out = collections.defaultdict(list)
            for e, x, y in P:
                d = {"W": x - x0, "E": x1 - x, "S": y - y0, "N": y1 - y}
                out[min(d, key=d.get)].append(e["guid"])
            return dict(out)
        lo, hi, k = (x0, x1, 1) if by == "x" else (y0, y1, 2)
        n = n or 2
        bands = [[] for _ in range(n)]
        for p in P:
            i = min(n - 1, int((p[k] - lo) / ((hi - lo) or 1) * n))
            bands[i].append(p[0]["guid"])
        return bands

    # ---- recording decisions -------------------------------------------------------------
    def link(self, activity_id, guids, reason):
        if activity_id not in self.acts:
            raise KeyError(f"unknown activity {activity_id}")
        guids = [g for g in guids if g in self.by_guid]
        self.empty.pop(activity_id, None)          # a link overrides an earlier/carried "no elements"
        self.links[activity_id].update(guids)
        self.reasons[activity_id].append((len(guids), reason))

    def carry(self):
        """Revision mode: start from the previous approved mapping (carried.csv from revise.py)."""
        from common import read_mapping
        m = read_mapping(os.path.join(self.dir, "carried.csv"))
        d = load_json(os.path.join(self.dir, "decisions_carried.json"), {}) or {}
        for x, gs in m.items():
            self.links[x].update(g for g in gs if g in self.by_guid)
            for r in (d.get("reasons") or {}).get(x, ["carried from previous mapping"]):
                self.reasons[x].append((len(self.links[x]), f"[carried] {r}"))
        for x, r in (d.get("no_elements") or {}).items():
            if x in self.acts and x not in self.links:
                self.empty[x] = f"[carried] {r}"
        # earlier questions stay on record with their answers (re-asking with ask() replaces them)
        for q in load_json(os.path.join(self.dir, "questions_carried.json"), []) or []:
            a = self.answers.get(q["id"]); a = a.get("choice") if isinstance(a, dict) else a
            q = dict(q, answered=a in q["options"], choice=a if a in q["options"] else q["default"], carried=True)
            self.questions.append(q)
        return self

    def unlink(self, activity_id, guids=None, reason=""):
        """Remove links (all of an activity's links if guids is None), e.g. when a revision re-scopes it."""
        gone = set(self.links.get(activity_id, set())) if guids is None else set(guids)
        self.links[activity_id] -= gone
        if not self.links[activity_id]:
            del self.links[activity_id]
        self.reasons[activity_id].append((-len(gone), f"removed: {reason}"))

    def no_elements(self, activity_id, reason):
        if activity_id not in self.acts:
            raise KeyError(f"unknown activity {activity_id}")
        if self.links.get(activity_id):
            raise ValueError(f"{activity_id} already has {len(self.links[activity_id])} links; unlink() first")
        self.empty[activity_id] = reason

    def ask(self, qid, question, options, default, why="", candidates=None, about=None):
        """Declare a question the data can't settle. Returns the planner's answer if given in
        answers.json, otherwise the default. options: {key: description}.
        about: the activity ids the question decides (required for repeated rounds, see save())."""
        self.questions = [q for q in self.questions if q["id"] != qid]
        if default not in options:
            raise ValueError(f"{qid}: default '{default}' not in options")
        ans = self.answers.get(qid, {}).get("choice") if isinstance(self.answers.get(qid), dict) else self.answers.get(qid)
        chosen = ans if ans in options else default
        cand = ""
        if candidates:
            c = collections.Counter(f"{self.by_guid[g]['level'] or '-'} / {self.by_guid[g]['category']}" for g in candidates if g in self.by_guid)
            cand = f"{len(candidates)} elements: " + ", ".join(f"{k} x{v}" for k, v in c.most_common(6))
        self.questions.append({"id": qid, "question": question, "why": why, "options": options,
                               "default": default, "answered": ans in options, "choice": chosen,
                               "candidates": cand, "about": list(about or [])})
        return chosen

    # ---- output --------------------------------------------------------------------------
    def save(self):
        both = set(self.links) & set(self.empty)
        if both:
            raise ValueError(f"activities both linked and no_elements: {sorted(both)}")
        rows = [{"activity_id": a, "guid": g} for a in sorted(self.links) for g in sorted(self.links[a])]
        write_csv(os.path.join(self.dir, "mapping.csv"), rows, ["activity_id", "guid"])
        save_json(os.path.join(self.dir, "questions.json"), self.questions)
        save_json(os.path.join(self.dir, "decisions.json"),
                  {"no_elements": self.empty, "rounds_settled": self.settled,
                   "reasons": {a: [r for _, r in v] for a, v in self.reasons.items()}})

        undecided = [a for a in self.acts if a not in self.links and a not in self.empty]
        linked_els = {g for gs in self.links.values() for g in gs}
        L = ["# Mapping rationale", "",
             f"Activities: {len(self.acts)} | linked: {len(self.links)} | no elements: {len(self.empty)} | "
             f"UNDECIDED: {len(undecided)}",
             f"Links: {len(rows)} | elements linked: {len(linked_els)} of {len(self.els)}", "",
             "## Linked activities", ""]
        for r in self.sched:
            a = r["activity_id"]
            if a in self.links:
                L.append(f"**{a} {r['name']}** ({r['start']} - {r['finish']}), {len(self.links[a])} elements")
                L += [f"- {n}: {why}" for n, why in self.reasons[a]]
                L.append("")
        L += ["## No elements", ""] + [f"- {a} {self.acts[a]['name']}: {why}" for a, why in self.empty.items()]
        if undecided:
            L += ["", "## UNDECIDED (fix before approval)", ""] + [f"- {a} {self.acts[a]['name']}" for a in undecided]
        # repeated rounds: show how each linked round was split, and flag any that no question covers
        asked = {a for q in self.questions + self.settled for a in q.get("about", [])}
        how = {a: f"settled: {d['how']} ({d['evidence']})" for d in self.settled for a in d["about"]}
        how.update({a: f"planner question {q['id']}: {q['options'][q['choice']]}" for q in self.questions for a in q.get("about", [])})
        unasked = []
        L += ["## Repeated rounds (same name, no location)", ""]
        for name, ids in self.repeated().items():
            linked = [a for a in ids if self.links.get(a)]
            if len(linked) < 2: continue
            flag = "" if set(linked) <= asked else "  **NOT ASKED**"
            if flag: unasked.append(f"{self.acts[ids[0]]['name']} x{len(ids)}")
            L.append(f"**{self.acts[ids[0]]['name']}** x{len(ids)}{flag}" + (f" - {how[linked[0]]}" if linked[0] in how else ""))
            for a in ids:
                c = collections.Counter(self.by_guid[g]["level"] or "-" for g in self.links.get(a, ()))
                L.append(f"- {a} ({self.acts[a]['start']}): {len(self.links.get(a, ()))} el. " + ", ".join(f"{k} x{v}" for k, v in c.most_common(4)))
            L.append("")
        self.unasked_rounds = unasked
        left = collections.Counter(f"{e['level'] or '-'} / {e['category']} / {e['type'][:40]}" for e in self.els if e["guid"] not in linked_els)
        L += ["", "## Elements in no activity", ""] + [f"- {k}: {v}" for k, v in left.most_common()]
        with open(os.path.join(self.dir, "rationale.md"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(L) + "\n")

        Q = ["# Questions for the planner", "",
             "Each question changes the mapping. Answer in chat, or set the choice in answers.json and re-run map_rules.py.", ""]
        for q in self.questions:
            Q.append(f"**{q['id']}. {q['question']}**" + ("  _(answered)_" if q["answered"] else "  _(using default)_"))
            if q["why"]: Q.append(f"- Why: {q['why']}")
            if q["candidates"]: Q.append(f"- Affects: {q['candidates']}")
            for k, v in q["options"].items():
                mark = "**[x]**" if k == q["choice"] else "[ ]"
                Q.append(f"- {mark} `{k}`: {v}" + ("  (default)" if k == q["default"] else ""))
            Q.append("")
        with open(os.path.join(self.dir, "questions.md"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(Q) + "\n")
        print(f"mapping: {len(self.links)} activities linked, {len(self.empty)} no-elements, "
              f"{len(undecided)} undecided, {len(rows)} links, {len(linked_els)}/{len(self.els)} elements; "
              f"questions: {len(self.questions)} ({sum(q['answered'] for q in self.questions)} answered)")
        if unasked:
            print(f"REPEATED ROUNDS NOT ASKED ({len(unasked)}): " + "; ".join(unasked) +
                  " - ask the planner how the rounds split (job.ask(..., about=[ids]))")
        return undecided
