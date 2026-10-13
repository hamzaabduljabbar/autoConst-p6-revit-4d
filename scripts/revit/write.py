# IronPython (runs inside Revit via AutoConst MCP execute_revit_code). Generated paths: __JOB__
# Writes the P6_ parameters from __JOB__\revit_values.json onto the elements (creates them if needed),
# clears them on elements that are no longer mapped, and reports what changed.
import System, json
JOB = r"__JOB__"
SKILL = r"__SKILL__"
app = doc.Application
vals = json.loads(System.IO.File.ReadAllText(JOB + r"\revit_values.json"))
spf = SKILL + r"\autoconst_4d_shared_params.txt"
if not System.IO.File.Exists(spf):
    System.IO.File.WriteAllText(spf, "")
SPECS = [("P6_Task_ID", DB.SpecTypeId.String.Text), ("P6_Activity", DB.SpecTypeId.String.Text),
         ("P6_Start", DB.SpecTypeId.String.Text), ("P6_Finish", DB.SpecTypeId.String.Text),
         ("P6_All_Activities", DB.SpecTypeId.String.Text), ("P6_Month", DB.SpecTypeId.String.Text),
         ("P6_Week", DB.SpecTypeId.Int.Integer)]
TEXT = [("P6_Task_ID","id"),("P6_Activity","name"),("P6_Start","start"),("P6_Finish","finish"),
        ("P6_All_Activities","all"),("P6_Month","month")]

els = {}
for uid in vals.keys():
    e = doc.GetElement(uid)
    if e is not None and e.Category is not None and e.Category.AllowsBoundParameters:
        els[uid] = e

# bind parameters to every category that has a mapped element (plus any already bound)
cats = DB.CategorySet()
for e in els.values(): cats.Insert(e.Category)
orig = app.SharedParametersFilename
app.SharedParametersFilename = spf
try:
    f = app.OpenSharedParameterFile()
    grp = f.Groups.get_Item("AutoConst 4D") or f.Groups.Create("AutoConst 4D")
    for name, spec in SPECS:
        d = grp.Definitions.get_Item(name) or grp.Definitions.Create(DB.ExternalDefinitionCreationOptions(name, spec))
        existing = doc.ParameterBindings.get_Item(d)
        if existing is not None:
            for c in existing.Categories: cats.Insert(c)
        b = app.Create.NewInstanceBinding(cats)
        if not doc.ParameterBindings.Insert(d, b, DB.GroupTypeId.Data):
            doc.ParameterBindings.ReInsert(d, b, DB.GroupTypeId.Data)
finally:
    app.SharedParametersFilename = orig
doc.Regenerate()

def get(e, n):
    pa = e.LookupParameter(n)
    if pa is None: return None
    return pa.AsString() if pa.StorageType == DB.StorageType.String else pa.AsInteger()

changed = {"new": 0, "dates_moved": 0, "activity_changed": 0, "unchanged": 0, "cleared": 0, "failed": 0}
moved = []
for uid, e in els.items():
    v = vals[uid]
    try:
        old_id, old_start = get(e, "P6_Task_ID"), get(e, "P6_Start")
        if not old_id: changed["new"] += 1
        elif old_id != v["id"]: changed["activity_changed"] += 1
        elif old_start != v["start"]:
            changed["dates_moved"] += 1; moved.append("{} {} {} -> {}".format(e.Id.IntegerValue, v["id"], old_start, v["start"]))
        else: changed["unchanged"] += 1
        for k, key in TEXT: e.LookupParameter(k).Set(v[key])
        e.LookupParameter("P6_Week").Set(int(v["week"]))
    except Exception as ex:
        changed["failed"] += 1

# clear elements that carry P6 values but are no longer mapped
for e in DB.FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements():
    if e.UniqueId in vals: continue
    pa = e.LookupParameter("P6_Task_ID")
    if pa is not None and pa.AsString():
        for k, _ in TEXT: e.LookupParameter(k).Set("")
        e.LookupParameter("P6_Week").Set(0)
        changed["cleared"] += 1

changed["not_writable"] = len(vals) - len(els)
System.IO.File.WriteAllText(JOB + r"\revit_write_report.json", json.dumps({"counts": changed, "dates_moved": moved[:500]}, indent=1))
print("written to '{}': {}".format(doc.Title, changed))
