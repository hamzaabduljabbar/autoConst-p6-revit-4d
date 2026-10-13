"""Step 1: create a job folder from a P6 XER (or an MS Project XML).

    python start.py --xer schedule.xer --job outputs/<job>
    python start.py --msp schedule.xml --job outputs/<job>

Writes schedule.csv + schedule_meta.json. elements.csv comes from Revit (revit_code.py --step dump).
"""
import argparse, os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import read_schedule, read_msp_xml, write_csv, save_json

FIELDS = ["activity_id", "name", "wbs", "type", "status", "start", "finish", "dur_days", "codes"]


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--xer"); src.add_argument("--msp", help="MS Project XML")
    ap.add_argument("--job", required=True)
    a = ap.parse_args()
    os.makedirs(a.job, exist_ok=True)
    rows, meta = read_schedule(a.xer) if a.xer else read_msp_xml(a.msp)
    dup = {r["activity_id"] for r in rows if sum(1 for x in rows if x["activity_id"] == r["activity_id"]) > 1}
    if dup:
        print(f"WARNING: duplicate activity IDs (links use IDs): {sorted(dup)[:10]}")
    write_csv(os.path.join(a.job, "schedule.csv"), rows, FIELDS)
    shutil.copy(a.xer or a.msp, os.path.join(a.job, "schedule.xer" if a.xer else "schedule.xml"))
    save_json(os.path.join(a.job, "schedule_meta.json"), meta)
    print(f"{meta['activities']} activities, project '{meta['project']}', data date {meta['data_date'] or '?'} -> {a.job}")


if __name__ == "__main__":
    main()
