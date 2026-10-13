"""Answer planner questions and rebuild the mapping with the answers applied.

    python answer.py --job outputs/<job> --list              # show open questions
    python answer.py --job outputs/<job> Q1=per_unit Q3=none  # record answers + re-run map_rules.py

Answers are kept in answers.json and carried into schedule revisions (revise.py), so a planner is
never asked the same question twice.
"""
import argparse, datetime as dt, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_json, save_json


def rebuild(job):
    r = subprocess.run([sys.executable, os.path.join(job, "map_rules.py")], capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip())
    if r.returncode:
        print(r.stderr); sys.exit(r.returncode)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("pairs", nargs="*", help="QID=option")
    a = ap.parse_args()
    qs = {q["id"]: q for q in load_json(os.path.join(a.job, "questions.json"), [])}
    if a.list or not a.pairs:
        for q in qs.values():
            state = f"answered: {q['choice']}" if q["answered"] else f"default: {q['default']}"
            print(f"{q['id']} [{state}] {q['question']}")
            for k, v in q["options"].items():
                print(f"    {k}: {v}")
        return
    ans = load_json(os.path.join(a.job, "answers.json"), {}) or {}
    for p in a.pairs:
        qid, _, choice = p.partition("=")
        if qid not in qs:
            sys.exit(f"unknown question {qid}")
        if choice not in qs[qid]["options"]:
            sys.exit(f"{qid}: '{choice}' is not one of {list(qs[qid]['options'])}")
        ans[qid] = {"choice": choice, "question": qs[qid]["question"], "answered_at": dt.datetime.now().isoformat(timespec="minutes")}
        print(f"{qid} = {choice}")
    save_json(os.path.join(a.job, "answers.json"), ans)
    rebuild(a.job)


if __name__ == "__main__":
    main()
