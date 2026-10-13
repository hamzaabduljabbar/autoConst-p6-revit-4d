# IronPython (runs inside Revit via AutoConst MCP execute_revit_code). Generated: __JOB__, __MODE__, __DATES__
# Builds 3D views from the P6_ parameters already on the elements:
#   "AutoConst 4D - by month"   every mapped element coloured by the month it starts
#   "AutoConst 4D - as of <d>"  one view per date: only what has started by that date, coloured by month
#   weekly mode: "AutoConst 4D - week NN" for every week (frames for a build-up video)
import System
from System.Collections.Generic import List
MODE = "__MODE__"           # "snapshots" or "weekly"
DATES = __DATES__           # list of ISO dates for snapshots
PREFIX = "AutoConst 4D - "

solid = [fp for fp in DB.FilteredElementCollector(doc).OfClass(DB.FillPatternElement) if fp.GetFillPattern().IsSolidFill][0]
vft = [x for x in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType) if x.ViewFamily == DB.ViewFamily.ThreeDimensional][0]

data = []   # (element, month, start, week)
hide_always = []
for e in DB.FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements():
    if e.Category is None or e.Category.CategoryType != DB.CategoryType.Model: continue
    pa = e.LookupParameter("P6_Task_ID")
    if pa is None: continue
    if pa.AsString():
        data.append((e, e.LookupParameter("P6_Month").AsString(), e.LookupParameter("P6_Start").AsString(),
                     e.LookupParameter("P6_Week").AsInteger()))
    else:
        hide_always.append(e)
for e in DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_StairsRailingBaluster).WhereElementIsNotElementType():
    hide_always.append(e)

def hsv(h, s, v):
    i = int(h * 6) % 6; f = h * 6 - int(h * 6)
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    return [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)][i]

# colour per month counted from week 1 (week_zero, fixed by the first approved version), so a month keeps
# its colour across schedule revisions: P6_Start - (P6_Week - 1) weeks = week 1
import datetime
months = sorted(set(m for _, m, _, _ in data if m))
z = min(datetime.date(*map(int, s.split("-"))) - datetime.timedelta(days=7 * (w - 1)) for _, _, s, w in data)
COL = {}
for m in months:
    i = (int(m[:4]) - z.year) * 12 + int(m[5:7]) - z.month
    r, g, b = hsv((0.05 + 0.065 * i) % 1.0, 0.75, 0.9)
    COL[m] = DB.Color(int(r * 255), int(g * 255), int(b * 255))

import time
stamp = time.strftime("%H%M%S")
for v in list(DB.FilteredElementCollector(doc).OfClass(DB.View3D)):
    if v.Name.startswith(PREFIX) and not v.IsTemplate:
        if v.Id == doc.ActiveView.Id:      # Revit can't delete the open view: park it under another name
            v.Name = "old " + stamp + " " + v.Name
        else:
            doc.Delete(v.Id)

# show only the building: hide model categories with nothing mapped (topography, site, planting...) and
# crop to the mapped elements with a section box (1 m margin)
mapped_cats = set(e.Category.Id.ToString() for e, _, _, _ in data)
other_cats = [c for c in doc.Settings.Categories if c.CategoryType == DB.CategoryType.Model and c.Id.ToString() not in mapped_cats]
bb = None
for e, _, _, _ in data:
    b = e.get_BoundingBox(None)
    if b is None: continue
    if bb is None: bb = [b.Min, b.Max]; continue
    bb = [DB.XYZ(min(bb[0].X, b.Min.X), min(bb[0].Y, b.Min.Y), min(bb[0].Z, b.Min.Z)),
          DB.XYZ(max(bb[1].X, b.Max.X), max(bb[1].Y, b.Max.Y), max(bb[1].Z, b.Max.Z))]
pad = 1000 / 304.8

def make(name, keep):
    v = DB.View3D.CreateIsometric(doc, vft.Id); v.Name = name
    v.DisplayStyle = DB.DisplayStyle.ShadingWithEdges
    for c in other_cats:
        try:
            if v.CanCategoryBeHidden(c.Id): v.SetCategoryHidden(c.Id, True)
        except Exception: pass
    sb = doc.Settings.Categories.get_Item(DB.BuiltInCategory.OST_SectionBox)
    if sb is not None and v.CanCategoryBeHidden(sb.Id): v.SetCategoryHidden(sb.Id, True)
    if bb:
        box = DB.BoundingBoxXYZ(); box.Min = bb[0] - DB.XYZ(pad, pad, pad); box.Max = bb[1] + DB.XYZ(pad, pad, pad)
        v.SetSectionBox(box)
    hide = List[DB.ElementId]([e.Id for e in hide_always if e.CanBeHidden(v)])
    shown = 0
    for e, m, s, w in data:
        if not keep(s, w):
            if e.CanBeHidden(v): hide.Add(e.Id)
            continue
        o = DB.OverrideGraphicSettings()
        o.SetSurfaceForegroundPatternId(solid.Id); o.SetSurfaceForegroundPatternColor(COL[m])
        o.SetCutForegroundPatternId(solid.Id); o.SetCutForegroundPatternColor(COL[m])
        v.SetElementOverrides(e.Id, o); shown += 1
    if hide.Count: v.HideElements(hide)
    return shown

res = [("by month", make(PREFIX + "by month", lambda s, w: True))]
if MODE == "weekly":
    for wk in range(1, max(w for _, _, _, w in data) + 1):
        res.append(("week {:02d}".format(wk), make(PREFIX + "week {:02d}".format(wk), lambda s, w, wk=wk: w <= wk)))
else:
    for d in DATES:
        res.append(("as of " + d, make(PREFIX + "as of " + d, lambda s, w, d=d: s <= d)))
print("views:", ", ".join("{} ({})".format(n, c) for n, c in res))
print("legend:", ", ".join("{}=rgb({},{},{})".format(m, COL[m].Red, COL[m].Green, COL[m].Blue) for m in months))

# two schedules: one row per activity, and every element grouped under its activity
def field(sd, name):
    for sf in sd.GetSchedulableFields():
        if sf.GetName(doc) == name: return sf
def schedule(name, itemize):
    for v in list(DB.FilteredElementCollector(doc).OfClass(DB.ViewSchedule)):
        if v.Name == name:
            if v.Id == doc.ActiveView.Id: v.Name = "old " + stamp + " " + name
            else: doc.Delete(v.Id)
    vs = DB.ViewSchedule.CreateSchedule(doc, DB.ElementId.InvalidElementId); vs.Name = name
    sd = vs.Definition; ids = {}
    names = ["P6_Start","P6_Finish","P6_Task_ID","P6_Activity"] + (["Category","Family and Type","Level","P6_All_Activities"] if itemize else ["Count"])
    for n in names:
        sf = field(sd, n)
        if sf: ids[n] = sd.AddField(sf).FieldId
    sd.AddFilter(DB.ScheduleFilter(ids["P6_Task_ID"], DB.ScheduleFilterType.HasValue))
    sd.AddSortGroupField(DB.ScheduleSortGroupField(ids["P6_Start"]))
    g = DB.ScheduleSortGroupField(ids["P6_Task_ID"])
    if itemize: g.ShowHeader = True; g.ShowFooter = True; g.ShowFooterCount = True
    sd.AddSortGroupField(g); sd.IsItemized = itemize
    if itemize: sd.ShowGrandTotal = True; sd.ShowGrandTotalCount = True
schedule(PREFIX + "activity summary", False)
schedule(PREFIX + "every element", True)
print("schedules: activity summary, every element")
