# IronPython (runs inside Revit via AutoConst MCP execute_revit_code). Generated paths: __JOB__
# Reads every buildable model element into __JOB__\elements.csv
import System
JOB = r"__JOB__"
CATS = ["OST_Walls","OST_Floors","OST_Roofs","OST_StructuralFraming","OST_StructuralColumns","OST_Columns",
        "OST_StructuralFoundation","OST_Doors","OST_Windows","OST_Stairs","OST_StairsRailing","OST_RailingHandRail",
        "OST_RailingTopRail","OST_Ceilings","OST_PlumbingFixtures","OST_GenericModel","OST_Fascia","OST_Gutter",
        "OST_RoofSoffit","OST_EdgeSlab","OST_StairsRuns","OST_StairsLandings","OST_SpecialityEquipment",
        "OST_MechanicalEquipment","OST_ElectricalEquipment","OST_ElectricalFixtures","OST_LightingFixtures",
        "OST_DuctCurves","OST_PipeCurves","OST_CableTray","OST_Conduit","OST_DuctFitting","OST_PipeFitting",
        "OST_DuctTerminal","OST_Sprinklers","OST_CurtainWallPanels","OST_CurtainWallMullions","OST_Casework",
        "OST_Furniture","OST_Topography","OST_Planting","OST_Site","OST_Parking","OST_Ramps"]
# not exported: balusters (Revit allows no parameters on them; they follow their railing)

def p(el, bip):
    try:
        x = el.get_Parameter(getattr(DB.BuiltInParameter, bip))
        if x is None: return ""
        if x.StorageType == DB.StorageType.String: s = x.AsString()
        elif x.StorageType == DB.StorageType.ElementId:
            e2 = doc.GetElement(x.AsElementId()); s = e2.Name if e2 else ""
        else: s = x.AsValueString()
        return s or ""
    except: return ""

def lvl(el):
    for b in ["FAMILY_LEVEL_PARAM","WALL_BASE_CONSTRAINT","LEVEL_PARAM","INSTANCE_REFERENCE_LEVEL_PARAM",
              "STAIRS_BASE_LEVEL_PARAM","ROOF_BASE_LEVEL_PARAM","SCHEDULE_LEVEL_PARAM","FAMILY_BASE_LEVEL_PARAM",
              "RBS_START_LEVEL_PARAM"]:
        v = p(el, b)
        if v: return v
    try:
        if el.LevelId and el.LevelId.IntegerValue > 0: return doc.GetElement(el.LevelId).Name
    except: pass
    return ""

def top(el):
    for b in ["WALL_HEIGHT_TYPE","FAMILY_TOP_LEVEL_PARAM","STAIRS_TOP_LEVEL_PARAM"]:
        v = p(el, b)
        if v: return v
    return ""

rows = []; seen = set()
for c in CATS:
    try: bic = getattr(DB.BuiltInCategory, c)
    except: continue
    for el in DB.FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType().ToElements():
        if el.Id.IntegerValue in seen or el.Category is None: continue
        seen.add(el.Id.IntegerValue)
        t = doc.GetElement(el.GetTypeId())
        fam = ""; tname = ""
        try: fam = t.FamilyName
        except: pass
        try: tname = t.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM).AsString() or ""
        except: pass
        bb = el.get_BoundingBox(None)
        zmin = zmax = cx = cy = ""
        if bb:
            zmin = int(round(bb.Min.Z*304.8)); zmax = int(round(bb.Max.Z*304.8))
            cx = int(round((bb.Min.X+bb.Max.X)/2*304.8)); cy = int(round((bb.Min.Y+bb.Max.Y)/2*304.8))
        rows.append([el.UniqueId, str(el.Id.IntegerValue), el.Category.Name, fam, tname, lvl(el), top(el),
                     p(t,"FUNCTION_PARAM") if t else "",
                     p(el,"INSTANCE_STRUCT_USAGE_PARAM") or p(el,"WALL_STRUCTURAL_USAGE_PARAM") or p(el,"FLOOR_PARAM_IS_STRUCTURAL"),
                     p(el,"STRUCTURAL_MATERIAL_PARAM") or (p(t,"STRUCTURAL_MATERIAL_PARAM") if t else ""),
                     p(t,"UNIFORMAT_CODE") if t else "", p(el,"ALL_MODEL_INSTANCE_COMMENTS"), p(el,"ALL_MODEL_MARK"),
                     p(el,"PHASE_CREATED"), p(el,"ELEM_PARTITION_PARAM"), str(zmin), str(zmax), str(cx), str(cy)])
hdr = ["guid","element_id","category","family","type","level","top_level","function","structural","material",
       "assembly_code","comments","mark","phase","workset","zmin","zmax","cx","cy"]
def q(s):
    return '"' + (s or "").replace('"','""').replace("\n"," ").replace("\r"," ") + '"'
System.IO.File.WriteAllText(JOB + r"\elements.csv", "\n".join([",".join(hdr)] + [",".join(q(v) for v in r) for r in rows]),
                            System.Text.Encoding.UTF8)
from collections import Counter
print("elements.csv: {} elements from '{}'".format(len(rows), doc.Title))
print(sorted(Counter(r[2] for r in rows).items(), key=lambda x: -x[1])[:15])
