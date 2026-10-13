"""Step 2 without Revit: read the model from an IFC file into elements.csv (same columns as the Revit dump).

    python ifc_read.py --ifc model.ifc --job outputs/<job>       (needs: pip install ifcopenshell)

Use when there is no Revit model (an IFC from ArchiCAD/Tekla/Synchro...) or Revit is not available.
The mapping, questions, check and report steps work the same; writing parameters and views needs Revit.
Columns: the Revit dump's, plus name, layer, zone, part_of (aggregate parent). Lengths in mm.
Level = the authoring tool's home story when the file has one (exports from Synchro etc. often put everything on
one dummy storey), else the IfcBuildingStorey.
Schedule data inside the IFC (IfcTask) is deliberately NOT read: the mapping is made from the schedule file.
"""
import argparse, csv, os, re, sys
import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element as ue

COLS = ["guid", "element_id", "category", "family", "type", "level", "top_level", "function", "structural",
        "material", "assembly_code", "comments", "mark", "phase", "workset", "zmin", "zmax", "cx", "cy",
        "name", "layer", "zone", "part_of"]
SKIP = ("IfcSpatialStructureElement", "IfcOpeningElement", "IfcVirtualElement", "IfcAnnotation", "IfcGrid",
        "IfcSpace", "IfcPort", "IfcSpatialZone")


def pick(props, *ends):
    """First property value whose name ends with one of `ends` (ArchiCAD/Revit/Tekla put them under different psets)."""
    for end in ends:
        for k, v in props.items():
            if k.lower().endswith(end.lower()) and v not in (None, ""):
                return str(v)
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ifc", required=True); ap.add_argument("--job", required=True)
    ap.add_argument("--no-geometry", action="store_true", help="skip bounding boxes (fast, but no z/cx/cy)")
    a = ap.parse_args()
    os.makedirs(a.job, exist_ok=True)
    f = ifcopenshell.open(a.ifc)
    els = [e for e in f.by_type("IfcProduct") if not any(e.is_a(s) for s in SKIP)]
    rows = {}
    for e in els:
        flat = {}
        for ps, vals in ue.get_psets(e).items():
            for k, v in vals.items():
                if k != "id": flat[f"{ps}.{k}"] = v
        cont = ue.get_container(e)
        agg = ue.get_aggregate(e)
        if cont is None and agg is not None:
            cont = ue.get_container(agg)
        t = ue.get_type(e)
        mats = []
        try:
            m = ue.get_material(e, should_skip_usage=True)
            if m is not None:
                for layer in getattr(m, "MaterialLayers", None) or getattr(m, "Materials", None) or [m]:
                    mm = getattr(layer, "Material", layer)
                    if getattr(mm, "Name", None): mats.append(mm.Name)
        except Exception:
            pass
        name = re.sub(r"_\(#?\d+\)$", "", (e.Name or "").strip())
        lb = pick(flat, ".LoadBearing")
        rows[e.id()] = {
            "guid": e.GlobalId, "element_id": e.id(), "category": e.is_a()[3:],
            "family": (t.Name if t is not None and t.Name else (e.ObjectType or "")) or "",
            "type": name, "level": pick(flat, "Home Story") or ((cont.Name or "") if cont is not None and cont.is_a("IfcBuildingStorey") else ""),
            "top_level": pick(flat, "Top Link Story"), "function": pick(flat, "Structural Function"),
            "structural": "1" if lb.lower() in ("true", "1") or "load-bearing" in pick(flat, "Structural Function").lower() else "",
            "material": ";".join(dict.fromkeys(mats)), "assembly_code": pick(flat, "Element Classification", ".Reference"),
            "comments": "", "mark": e.Tag or "", "phase": pick(flat, "Renovation Status", ".Phase Created"),
            "workset": "", "zmin": "", "zmax": "", "cx": "", "cy": "",
            "name": name, "layer": pick(flat, "Layer"), "zone": pick(flat, "Zone Name"),
            "part_of": agg.GlobalId if agg is not None and not agg.is_a("IfcSpatialStructureElement") else "",
        }
    # parts (IfcBuildingElementPart etc.) often carry no properties: inherit level/layer/zone from their parent
    by_guid = {r["guid"]: r for r in rows.values()}
    for r in rows.values():
        par = by_guid.get(r["part_of"])
        if par is not None:
            for k in ("level", "top_level", "layer", "zone", "function", "phase", "assembly_code"):
                if not r[k] or (k == "level" and not r["layer"]):
                    r[k] = par[k] or r[k]
    if not a.no_geometry:
        s = ifcopenshell.geom.settings(); s.set("use-world-coords", True)
        it = ifcopenshell.geom.iterator(s, f, max(1, (os.cpu_count() or 2) - 1), include=els)
        n = 0
        if it.initialize():
            while True:
                sh = it.get()
                r = rows.get(sh.id)
                v = sh.geometry.verts
                if r is not None and v:
                    xs, ys, zs = v[0::3], v[1::3], v[2::3]
                    k = 1000.0          # the geometry kernel returns metres whatever the file unit
                    r["zmin"], r["zmax"] = round(min(zs) * k), round(max(zs) * k)
                    r["cx"], r["cy"] = round((min(xs) + max(xs)) / 2 * k), round((min(ys) + max(ys)) / 2 * k)
                    n += 1
                if not it.next(): break
        print(f"geometry: {n} of {len(rows)} elements")
    out = os.path.join(a.job, "elements.csv")
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, COLS); w.writeheader(); w.writerows(rows.values())
    import collections
    print(f"elements.csv: {len(rows)} elements from '{os.path.basename(a.ifc)}'")
    print(collections.Counter(r["category"] for r in rows.values()).most_common())


if __name__ == "__main__":
    main()
