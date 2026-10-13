"""Shared helpers: read a P6 XER, read/write the job folder's CSV files."""
import csv, datetime as dt, json, os


def read_text(path):
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            with open(path, encoding=enc) as fh:
                return fh.read()
        except UnicodeDecodeError:
            continue
    raise ValueError(f"cannot decode {path}")


def xer_tables(path):
    """Return {table: [row dict]} from an XER file."""
    tables, cur, fields = {}, None, None
    for line in read_text(path).splitlines():
        parts = line.rstrip("\r").split("\t")
        tag = parts[0]
        if tag == "%T":
            cur = parts[1]; tables[cur] = []
        elif tag == "%F":
            fields = parts[1:]
        elif tag == "%R" and cur:
            tables[cur].append(dict(zip(fields, parts[1:])))
    return tables


def _date(row, *keys):
    for k in keys:
        v = (row.get(k) or "").strip()
        if v:
            return v[:10]
    return ""


def read_schedule(xer_path):
    """Activities with WBS path, type, planned/actual dates. One row per activity."""
    t = xer_tables(xer_path)
    wbs = {w["wbs_id"]: w for w in t.get("PROJWBS", [])}

    def path(wid):
        out, seen = [], set()
        while wid in wbs and wid not in seen:
            seen.add(wid)
            w = wbs[wid]
            if w.get("proj_node_flag") == "Y":
                break
            out.append(w.get("wbs_name", "").strip())
            wid = w.get("parent_wbs_id")
        return " > ".join(reversed(out))

    # activity codes (if any): {task_id: "Type: Value; ..."}
    ctype = {c["actv_code_type_id"]: c.get("actv_code_type", "") for c in t.get("ACTVTYPE", [])}
    cval = {c["actv_code_id"]: (ctype.get(c.get("actv_code_type_id"), ""), c.get("short_name") or c.get("actv_code_name", ""))
            for c in t.get("ACTVCODE", [])}
    codes = {}
    for a in t.get("TASKACTV", []):
        k = cval.get(a.get("actv_code_id"))
        if k:
            codes.setdefault(a["task_id"], []).append(f"{k[0]}: {k[1]}")

    rows = []
    for x in t.get("TASK", []):
        start = _date(x, "act_start_date", "restart_date", "early_start_date", "target_start_date")
        finish = _date(x, "act_end_date", "reend_date", "early_end_date", "target_end_date")
        rows.append({
            "activity_id": x.get("task_code", "").strip(),
            "name": x.get("task_name", "").strip(),
            "wbs": path(x.get("wbs_id")),
            "type": x.get("task_type", ""),
            "status": x.get("status_code", ""),
            "start": start, "finish": finish,
            "dur_days": round(float(x.get("target_drtn_hr_cnt") or 0) / 8, 1),
            "codes": "; ".join(codes.get(x.get("task_id"), [])),
        })
    rows.sort(key=lambda r: (r["wbs"], r["start"], r["activity_id"]))
    proj = (t.get("PROJECT") or [{}])[0]
    meta = {"project": proj.get("proj_short_name", ""), "data_date": _date(proj, "last_recalc_date", "next_data_date"),
            "activities": len(rows), "source": os.path.abspath(xer_path)}
    return rows, meta


def read_msp_xml(xml_path):
    """MS Project XML (File > Save As > XML) -> same rows as read_schedule. activity_id = the task's ID.
    WBS path = names of the parent summary tasks (OutlineLevel). Rows keep the file's order."""
    import re, xml.etree.ElementTree as ET
    root = ET.parse(xml_path).getroot()
    ns = {"p": root.tag[1:].split("}")[0]} if root.tag.startswith("{") else {"p": ""}
    q = (lambda k: "p:" + k) if ns["p"] else (lambda k: k)
    rows, parents = [], {}
    for t in root.findall(q("Tasks") + "/" + q("Task"), ns):
        g = lambda k: (t.findtext(q(k), default="", namespaces=ns) or "").strip()
        name = g("Name")
        if not name or g("UID") == "0":
            continue
        lvl = int(g("OutlineLevel") or 1)
        parents = {k: v for k, v in parents.items() if k < lvl}
        m = re.match(r"PT(\d+)H(\d+)M", g("Duration"))
        hours = int(m.group(1)) + int(m.group(2)) / 60 if m else 0
        pct = float(g("PercentComplete") or 0)
        typ = "TT_WBS" if g("Summary") == "1" else "TT_Mile" if g("Milestone") == "1" else "TT_Task"
        rows.append({
            "activity_id": g("ID"), "name": name, "wbs": " > ".join(parents[k] for k in sorted(parents)),
            "type": typ, "status": "TK_Complete" if pct >= 100 else "TK_Active" if pct > 0 else "TK_NotStart",
            "start": (g("ActualStart") or g("Start"))[:10], "finish": (g("ActualFinish") or g("Finish"))[:10],
            "dur_days": round(hours / 8, 1), "codes": "",
        })
        if g("Summary") == "1":
            parents[lvl] = name
    meta = {"project": root.findtext(q("Name"), default="", namespaces=ns) or os.path.basename(xml_path),
            "data_date": (root.findtext(q("StatusDate"), default="", namespaces=ns) or "")[:10],
            "activities": len(rows), "source": os.path.abspath(xml_path)}
    return rows, meta


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path, rows, fields):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)


def read_mapping(path):
    """mapping.csv -> {activity_id: set(guid)}"""
    m = {}
    for r in read_csv(path):
        if r.get("activity_id") and r.get("guid"):
            m.setdefault(r["activity_id"].strip(), set()).add(r["guid"].strip())
    return m


def write_mapping(path, m):
    rows = [{"activity_id": a, "guid": g} for a in sorted(m) for g in sorted(m[a])]
    write_csv(path, rows, ["activity_id", "guid"])


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1)


def iso(d):
    return dt.date.fromisoformat(d) if d else None
