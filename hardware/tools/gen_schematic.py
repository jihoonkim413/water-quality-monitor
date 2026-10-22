"""Generate hardware/water_carrier/water_carrier.kicad_sch from design.py.

Run with KiCad's Python (any Python 3 works; no KiCad modules needed):
    python hardware/tools/gen_schematic.py
"""

import math
import os
import uuid
from datetime import date
from pathlib import Path

import design as D
from sexpr import Sym, dump, find, find_all, parse

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "water_carrier" / "water_carrier.kicad_sch"
PROJECT = "water_carrier"
SYMDIR = Path(os.environ.get(
    "KICAD_SYMBOL_DIR",
    Path(os.environ["LOCALAPPDATA"]) / "Programs/KiCad/10.0/share/kicad/symbols"))

NS = uuid.UUID("6f1c2a7e-1d3b-4c6a-9e51-7a0b9c2d4e10")
ROOT_UUID = str(uuid.uuid5(NS, "root"))


def uid(*parts):
    return [Sym("uuid"), str(uuid.uuid5(NS, "/".join(map(str, parts))))]


def font(size=1.27, justify=None, hide=False):
    eff = [Sym("effects"), [Sym("font"), [Sym("size"), size, size]]]
    if justify:
        eff.append([Sym("justify")] + [Sym(j) for j in justify])
    if hide:
        eff.append([Sym("hide"), Sym("yes")])
    return eff


# ------------------------------------------------------------ library symbols --

_lib_cache = {}


def lib_symbol(lib_id):
    """Return (definition for lib_symbols, {pin number: (x, y, angle)})."""
    if lib_id in _lib_cache:
        return _lib_cache[lib_id]
    lib, name = lib_id.split(":")
    tree = parse((SYMDIR / f"{lib}.kicad_sym").read_text(encoding="utf-8"))
    sym = next(s for s in find_all(tree, "symbol") if s[1] == name)
    if find(sym, "extends"):
        raise SystemExit(f"{lib_id} uses 'extends'; flattening not implemented")
    sym = [sym[0], lib_id] + sym[2:]
    pins = {}
    for sub in find_all(sym, "symbol"):
        for p in find_all(sub, "pin"):
            at = find(p, "at")
            num = find(p, "number")[1]
            pins[num] = (float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0)
    _lib_cache[lib_id] = (sym, pins)
    return sym, pins


def pin_xy(lib_id, at, pin):
    """Schematic coordinates of a pin's connection point (symbol unrotated)."""
    _, pins = lib_symbol(lib_id)
    px, py, ang = pins[str(pin)]
    return at[0] + px, at[1] - py, ang


def outward(angle):
    """Unit vector (schematic coords) pointing away from the symbol body."""
    a = math.radians(angle)
    return -round(math.cos(a)), round(math.sin(a))


# ------------------------------------------------------------------ builders --

items = []
used_libs = set()
pwr_count = [0]


def rotation_for(natural, out):
    """Symbol rotation (degrees, CCW) that turns `natural` into `out` (screen coords)."""
    for a in (0, 90, 180, 270):
        r = math.radians(a)
        vx = round(natural[0] * math.cos(r) + natural[1] * math.sin(r))
        vy = round(-natural[0] * math.sin(r) + natural[1] * math.cos(r))
        if (vx, vy) == tuple(out):
            return a
    raise ValueError(out)


def place(lib_id, ref, value, at, footprint="", fields=None, pins=(), in_bom=True, rot=0,
          ref_pos=None, val_pos=None, justify=("left",), hide_ref=False):
    used_libs.add(lib_id)
    # Field angles are relative to the symbol; this keeps text horizontal.
    fa = 90 if rot in (90, 270) else 0
    rp = ref_pos or (at[0] + 2.54, at[1] - 1.27)
    vp = val_pos or (at[0] + 2.54, at[1] + 1.27)
    just = list(justify) if justify else None
    props = [
        [Sym("property"), "Reference", ref, [Sym("at"), rp[0], rp[1], fa],
         font(justify=just, hide=hide_ref)],
        [Sym("property"), "Value", value, [Sym("at"), vp[0], vp[1], fa], font(justify=just)],
        [Sym("property"), "Footprint", footprint, [Sym("at"), at[0], at[1], 0], font(hide=True)],
        [Sym("property"), "Datasheet", "", [Sym("at"), at[0], at[1], 0], font(hide=True)],
    ]
    for k, v in (fields or {}).items():
        props.append([Sym("property"), k, v, [Sym("at"), at[0], at[1], 0], font(hide=True)])
    node = [Sym("symbol"), [Sym("lib_id"), lib_id], [Sym("at"), at[0], at[1], rot],
            [Sym("unit"), 1], [Sym("exclude_from_sim"), Sym("no")],
            [Sym("in_bom"), Sym("yes" if in_bom else "no")], [Sym("on_board"), Sym("yes")],
            [Sym("dnp"), Sym("no")], uid("sym", ref)] + props
    for p in pins:
        node.append([Sym("pin"), str(p), uid("pin", ref, p)])
    node.append([Sym("instances"), [Sym("project"), PROJECT,
                 [Sym("path"), "/" + ROOT_UUID, [Sym("reference"), ref], [Sym("unit"), 1]]]])
    items.append(node)


def wire(x1, y1, x2, y2):
    items.append([Sym("wire"), [Sym("pts"), [Sym("xy"), x1, y1], [Sym("xy"), x2, y2]],
                  [Sym("stroke"), [Sym("width"), 0], [Sym("type"), Sym("default")]],
                  uid("wire", x1, y1, x2, y2)])


def label(net, x, y, direction):
    """Local label at (x, y); direction is the (dx, dy) the stub runs."""
    dx, dy = direction
    angle = {(1, 0): 0, (0, -1): 90, (-1, 0): 180, (0, 1): 270}[(dx, dy)]
    just = ["left", "bottom"] if angle in (0, 90) else ["right", "bottom"]
    items.append([Sym("label"), net, [Sym("at"), x, y, angle], font(justify=just),
                  uid("label", net, x, y)])


def power(net, x, y, out):
    """Power symbol at (x, y), its graphic pointing in direction `out`."""
    pwr_count[0] += 1
    ref = f"#PWR{pwr_count[0]:02d}"
    lib_id = {"GND": "power:GND", "+5V": "power:+5V", "+3V3": "power:+3V3"}[net]
    natural = (0, 1) if net == "GND" else (0, -1)  # GND hangs down, supplies point up
    rot = rotation_for(natural, out)
    if out[0]:  # horizontal: net name just beyond the symbol, centred
        vp, just = (x + out[0] * 8.89, y), None
    else:       # vertical: net name beside the symbol
        vp, just = (x + 1.27, y + out[1] * 3.81), ("left",)
    place(lib_id, ref, net, (x, y), pins=[1], in_bom=False, rot=rot,
          val_pos=vp, justify=just, hide_ref=True)


def no_connect(x, y):
    items.append([Sym("no_connect"), [Sym("at"), x, y], uid("nc", x, y)])


def text(s, x, y, size=1.8):
    """Text block whose top-left corner is at (x, y)."""
    items.append([Sym("text"), s, [Sym("exclude_from_sim"), Sym("no")],
                  [Sym("at"), x, y, 0], font(size, justify=["left", "top"]), uid("text", s)])


def attach(lib_id, at, pin, net, stub=2.54):
    """Connect a pin to a net with a short wire stub and a label/power symbol."""
    x, y, ang = pin_xy(lib_id, at, pin)
    if net is None:
        no_connect(x, y)
        return
    dx, dy = outward(ang)
    ex, ey = x + dx * stub, y + dy * stub
    wire(x, y, ex, ey)
    if net in D.POWER_NETS:
        power(net, ex, ey, (dx, dy))  # symbol points straight out from the pin
    else:
        label(net, ex, ey, (dx, dy))


# ------------------------------------------------------------------- layout --

def build():
    conn6, conn15 = "Connector_Generic:Conn_01x06", "Connector_Generic:Conn_01x15"

    # Sensor connector
    j3 = (45.72, 83.82)
    top = j3[1] - 6.35
    place(conn6, "J3", f"Sensor (JST {D.SENSOR_JST}, 6-pin)", j3, D.SENSOR_FOOTPRINT,
          pins=range(1, 7), ref_pos=(j3[0], top - 5.08), val_pos=(j3[0], top - 2.54), justify=None)
    for i, net in enumerate(D.SENSOR_PINS, 1):
        attach(conn6, j3, i, net)
    text("DWS-MH-02 sensor plug\n" + "\n".join(f"{i}: {n}" for i, n in enumerate(D.SENSOR_PIN_NAMES, 1)),
         22.86, 99.06, 1.5)

    # DevKit headers
    for ref, names, at, title in (("J1", D.DEVKIT_LEFT, (208.28, 83.82), "DevKit left"),
                                  ("J2", D.DEVKIT_RIGHT, (261.62, 83.82), "DevKit right")):
        top = at[1] - 17.78
        place(conn15, ref, f"{title} (1x15)", at, D.HEADER_FOOTPRINT, pins=range(1, 16),
              ref_pos=(at[0], top - 5.08), val_pos=(at[0], top - 2.54), justify=None)
        for i, net in D.devkit_pin_nets(names).items():
            attach(conn15, at, i, net)
        # Pin names to the right of the connector body
        for i, n in enumerate(names, 1):
            _, py, _ = pin_xy(conn15, at, i)
            items.append([Sym("text"), n, [Sym("exclude_from_sim"), Sym("no")],
                          [Sym("at"), at[0] + 3.81, py, 0], font(1.27, justify=["left"]),
                          uid("pinname", ref, i)])
    text("ESP32 DevKit V1 sockets (pin 1 = antenna end)", 195.58, 49.53)

    # Passives: one column per part, grouped by function
    groups = [
        ("Flow input: 5 V pulse -> 3.3 V", 81.28, 45.72, ["R5", "R1", "R2", "C1"]),
        ("Temperature (NTC divider)", 81.28, 93.98, ["R3", "C2"]),
        ("TDS auto-range references", 81.28, 142.24, ["R4", "R6"]),
    ]
    by_ref = {p[0]: p for p in D.PASSIVES}
    for title, x0, y0, refs in groups:
        text(title, x0 - 2.54, y0 - 26.67)
        for k, ref in enumerate(refs):
            _, value, fp, lcsc, n1, n2, purpose = by_ref[ref]
            lib_id = "Device:R" if ref.startswith("R") else "Device:C"
            at = (x0 + k * 22.86, y0)
            place(lib_id, ref, value, at, fp, {"LCSC": lcsc, "Purpose": purpose}, pins=[1, 2])
            attach(lib_id, at, 1, n1)
            attach(lib_id, at, 2, n2)

    # Power flags so ERC knows the supplies are driven by the DevKit
    text("Supplies come from the DevKit", 195.58, 132.08, 1.5)
    for k, net in enumerate(["+5V", "+3V3", "GND"]):
        x, y = 200.66 + k * 20.32, 142.24
        used_libs.add("power:PWR_FLAG")
        ref = f"#FLG{k + 1:02d}"
        place("power:PWR_FLAG", ref, "PWR_FLAG", (x, y), pins=[1], in_bom=False,
              val_pos=(x + 1.27, y - 3.81), hide_ref=True)
        wire(x, y, x, y + 2.54)
        power(net, x, y + 2.54, (0, 1))


def main():
    build()
    lib_syms = [lib_symbol(l)[0] for l in sorted(used_libs)]
    doc = [Sym("kicad_sch"), [Sym("version"), 20231120], [Sym("generator"), "water_quality_gen"],
           [Sym("generator_version"), "1.0"], [Sym("uuid"), ROOT_UUID], [Sym("paper"), "A4"],
           [Sym("title_block"), [Sym("title"), "Water sensor carrier for ESP32 DevKit V1"],
            [Sym("date"), date.today().isoformat()], [Sym("rev"), "A"],
            [Sym("comment"), 1, "Generated by hardware/tools/gen_schematic.py - edit design.py, not this file"]],
           [Sym("lib_symbols")] + lib_syms] + items + [
           [Sym("sheet_instances"), [Sym("path"), "/", [Sym("page"), "1"]]]]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(dump(doc) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
