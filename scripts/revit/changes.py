# IronPython (runs inside Revit via AutoConst MCP execute_revit_code). Generated: __JOB__
# One 3D view showing what a schedule revision changed, element by element:
#   red = starts later   green = starts earlier   blue = newly scheduled   orange = other activity, same date
#   magenta = no longer scheduled   see-through grey = unchanged
import System
from System.Collections.Generic import List
NAME = "AutoConst 4D - changes __OLD__ to __NEW__"
CLS = __CLASSES__           # {guid: class}
COL = {"later": (220, 40, 40), "earlier": (40, 170, 70), "new": (40, 110, 230), "activity": (240, 150, 30),
       "unscheduled": (210, 40, 200)}

solid = [fp for fp in DB.FilteredElementCollector(doc).OfClass(DB.FillPatternElement) if fp.GetFillPattern().IsSolidFill][0]
vft = [x for x in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType) if x.ViewFamily == DB.ViewFamily.ThreeDimensional][0]

for v in list(DB.FilteredElementCollector(doc).OfClass(DB.View3D)):
    if v.Name == NAME and not v.IsTemplate:
        if v.Id == doc.ActiveView.Id:
            import time; v.Name = "old " + time.strftime("%H%M%S") + " " + NAME
        else:
            doc.Delete(v.Id)

els = []
for g, c in CLS.items():
    e = doc.GetElement(g)
    if e is not None and e.Category is not None: els.append((e, c))

v = DB.View3D.CreateIsometric(doc, vft.Id); v.Name = NAME
v.DisplayStyle = DB.DisplayStyle.ShadingWithEdges
cats = set(e.Category.Id.ToString() for e, _ in els)
for c in doc.Settings.Categories:
    if c.CategoryType == DB.CategoryType.Model and c.Id.ToString() not in cats:
        try:
            if v.CanCategoryBeHidden(c.Id): v.SetCategoryHidden(c.Id, True)
        except Exception: pass
sb = doc.Settings.Categories.get_Item(DB.BuiltInCategory.OST_SectionBox)
if sb is not None and v.CanCategoryBeHidden(sb.Id): v.SetCategoryHidden(sb.Id, True)
bb = None
for e, _ in els:
    b = e.get_BoundingBox(None)
    if b is None: continue
    if bb is None: bb = [b.Min, b.Max]; continue
    bb = [DB.XYZ(min(bb[0].X, b.Min.X), min(bb[0].Y, b.Min.Y), min(bb[0].Z, b.Min.Z)),
          DB.XYZ(max(bb[1].X, b.Max.X), max(bb[1].Y, b.Max.Y), max(bb[1].Z, b.Max.Z))]
if bb:
    pad = 1000 / 304.8; box = DB.BoundingBoxXYZ()
    box.Min = bb[0] - DB.XYZ(pad, pad, pad); box.Max = bb[1] + DB.XYZ(pad, pad, pad); v.SetSectionBox(box)

# hide whatever is in a mapped category but in neither version (and balusters)
keep = set(e.Id.ToString() for e, _ in els)
hide = List[DB.ElementId]()
for e in DB.FilteredElementCollector(doc, v.Id).WhereElementIsNotElementType().ToElements():
    if e.Category is not None and e.Category.CategoryType == DB.CategoryType.Model and e.Id.ToString() not in keep and e.CanBeHidden(v):
        hide.Add(e.Id)
if hide.Count: v.HideElements(hide)

grey = DB.Color(190, 190, 190)
n = {}
for e, c in els:
    o = DB.OverrideGraphicSettings()
    if c == "unchanged":
        o.SetSurfaceForegroundPatternId(solid.Id); o.SetSurfaceForegroundPatternColor(grey)
        o.SetSurfaceTransparency(85)
        o.SetProjectionLineColor(DB.Color(150, 150, 150))
    else:
        col = DB.Color(*COL[c])
        o.SetSurfaceForegroundPatternId(solid.Id); o.SetSurfaceForegroundPatternColor(col)
        o.SetCutForegroundPatternId(solid.Id); o.SetCutForegroundPatternColor(col)
    v.SetElementOverrides(e.Id, o)
    n[c] = n.get(c, 0) + 1
print("view: " + NAME)
print("elements: " + ", ".join("{} {}".format(k, n.get(k, 0)) for k in ["later", "earlier", "new", "activity", "unscheduled", "unchanged"]))
