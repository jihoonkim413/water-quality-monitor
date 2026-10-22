"""Generate hardware/water_carrier/water_carrier.kicad_pcb from design.py.

Run with KiCad's Python:
    "%LOCALAPPDATA%/Programs/KiCad/10.0/bin/python.exe" hardware/tools/gen_pcb.py

Layout (mm, origin top-left, y down):
  - DevKit sockets J1/J2 in the middle-right, antenna end up, USB toward the bottom edge.
  - Sensor socket J3 on the left edge, pin 1 at the top.
  - Flow parts (R5, R1, R2, C1) in the strip between J3 and J1.
  - TDS (R4, R6) and temperature (R3, C2) parts under the DevKit.
  - GND fill on both layers; no copper under the ESP32 antenna.
"""

import os
from pathlib import Path

import pcbnew
from pcbnew import FromMM, VECTOR2I

import design as D
from gen_schematic import uid

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "water_carrier" / "water_carrier.kicad_pcb"
FPDIR = Path(os.environ["LOCALAPPDATA"]) / "Programs/KiCad/10.0/share/kicad/footprints"

SIG_W = 0.3   # signal track width
PWR_W = 0.5   # +5V / +3V3 track width

# --------------------------------------------------------------- geometry --
J1X, J1Y = 22.0, 14.0                 # J1 pin 1
J2X = J1X + D.DEVKIT_ROW_SPACING      # J2 pin 1 is level with J1 pin 1
J3X, J3Y = 5.0, J1Y + 4 * 2.54        # J3 pin 1, level with J1 pin 5 (TDS sense)
BOARD_W = round(J2X + 7.6, 1)
BOARD_H = 60.0

# DevKit V1 body, approx. 28.5 x 51.5 mm; pin 1 is ~7 mm from the antenna end.
KIT_L, KIT_R = J1X - 1.55, J2X + 1.55
KIT_T, KIT_B = J1Y - 7.0, J1Y - 7.0 + 51.5


def j1(n):
    return J1X, J1Y + (n - 1) * 2.54


def j2(n):
    return J2X, J2Y_ + (n - 1) * 2.54


J2Y_ = J1Y


def j3(n):
    return J3X, J3Y + (n - 1) * 2.0


# ------------------------------------------------------------------ board --
board = pcbnew.BOARD()
nets = {}


def P(x, y):
    return VECTOR2I(FromMM(x), FromMM(y))


def net(name):
    # Schematic labels are sheet-local ("/FLOW"); power nets are global ("GND");
    # unused pins get KiCad's "unconnected-(...)" names.
    full = name if name in D.POWER_NETS or name.startswith("unconnected-") else "/" + name
    if full not in nets:
        n = pcbnew.NETINFO_ITEM(board, full)
        board.Add(n)
        nets[full] = n
    return nets[full]


fps = {}


def add_fp(ref, fpid, xy, rot, pad_nets, value, board_only=False, fields=None):
    lib, name = fpid.split(":")
    fp = pcbnew.FootprintLoad(str(FPDIR / f"{lib}.pretty"), name)
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    fp.SetReference(ref)
    fp.SetValue(value)
    for k, v in (fields or {}).items():
        fp.SetField(k, v)
        f = fp.GetField(k)
        f.SetLayer(pcbnew.F_Fab)
        f.SetVisible(False)
    board.Add(fp)
    fp.SetPosition(P(*xy))
    fp.SetOrientationDegrees(rot)
    for pad in fp.Pads():
        n = pad_nets.get(pad.GetNumber())
        if n:
            pad.SetNet(net(n))
    if board_only:
        fp.SetAttributes(fp.GetAttributes() | pcbnew.FP_BOARD_ONLY
                         | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
    else:
        fp.SetPath(pcbnew.KIID_PATH("/" + uid("sym", ref)[1]))
    fps[ref] = fp
    return fp


def pad_xy(ref, num):
    p = next(p for p in fps[ref].Pads() if p.GetNumber() == str(num)).GetPosition()
    return round(pcbnew.ToMM(p.x), 3), round(pcbnew.ToMM(p.y), 3)


def track(pts, name, width=SIG_W, layer=pcbnew.F_Cu):
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(P(x1, y1))
        t.SetEnd(P(x2, y2))
        t.SetWidth(FromMM(width))
        t.SetLayer(layer)
        t.SetNet(net(name))
        board.Add(t)


def via(xy, name):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(P(*xy))
    v.SetDrill(FromMM(0.3))
    v.SetWidth(FromMM(0.6))
    v.SetNet(net(name))
    board.Add(v)


def line(layer, pts, width=0.15):
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(P(x1, y1))
        s.SetEnd(P(x2, y2))
        s.SetLayer(layer)
        s.SetWidth(FromMM(width))
        board.Add(s)


def text(s, xy, size=1.0, rot=0, layer=pcbnew.F_SilkS):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetPosition(P(*xy))
    t.SetLayer(layer)
    t.SetTextSize(VECTOR2I(FromMM(size), FromMM(size)))
    t.SetTextThickness(FromMM(size * 0.15))
    t.SetTextAngleDegrees(rot)
    board.Add(t)


def zone(layers, corners, name=None, keepout=False):
    z = pcbnew.ZONE(board)
    ls = pcbnew.LSET()
    for l in layers:
        ls.AddLayer(l)
    z.SetLayerSet(ls)
    if name:
        z.SetNet(net(name))
    ol = z.Outline()
    ol.NewOutline()
    for x, y in corners:
        ol.Append(FromMM(x), FromMM(y))
    if keepout:
        z.SetIsRuleArea(True)
        z.SetDoNotAllowTracks(True)
        z.SetDoNotAllowVias(True)
        z.SetDoNotAllowZoneFills(True)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
        z.SetZoneName("No copper under ESP32 antenna")
    else:
        z.SetLocalClearance(FromMM(0.3))
        z.SetMinThickness(FromMM(0.25))
        z.SetThermalReliefGap(FromMM(0.4))
        z.SetThermalReliefSpokeWidth(FromMM(0.4))
    board.Add(z)
    return z


# ------------------------------------------------------------- placement --
def build():
    # DevKit sockets
    for ref, names, x in (("J1", D.DEVKIT_LEFT, J1X), ("J2", D.DEVKIT_RIGHT, J2X)):
        add_fp(ref, D.HEADER_FOOTPRINT, (x, J1Y), 0,
               {str(i): n or f"unconnected-({ref}-Pin_{i}-Pad{i})"
                for i, n in D.devkit_pin_nets(names).items()},
               f"DevKit {'left' if ref == 'J1' else 'right'} (1x15)")

    # Sensor socket: rotated so pins run downward from pin 1
    add_fp("J3", D.SENSOR_FOOTPRINT, j3(1), -90,
           {str(i): n for i, n in enumerate(D.SENSOR_PINS, 1)},
           f"Sensor (JST {D.SENSOR_JST}, 6-pin)")

    # Passives: (anchor pad, where that pad goes, rotation). The anchor is the
    # pad that sits on a straight track, so it's placed exactly.
    spots = {
        "R5": (2, (9.0, j3(4)[1]), 90),       # pad 2 (pulse) top, pad 1 (+5V) below
        "R1": (1, (11.088, j3(4)[1]), 0),     # pad 1 (pulse) left, pad 2 (flow) right
        "R2": (1, (16.0, j1(10)[1]), -90),    # pad 1 (flow) top, pad 2 (GND) below
        "C1": (1, (18.5, j1(10)[1]), -90),    # pad 1 (flow) top, pad 2 (GND) below
        "R6": (1, (25.088, j1(7)[1]), 0),     # pad 1 (HI) left, pad 2 (sense) right
        "R4": (1, (25.088, j1(8)[1]), 0),     # pad 1 (LO) left, pad 2 (sense) right
        "C2": (1, (30.0, j1(4)[1]), -90),     # pad 1 (temp) top, pad 2 (GND) below
        "R3": (2, (34.088, j1(4)[1]), 180),   # pad 2 (temp) left, pad 1 (+3V3) right
    }
    for ref, value, fpid, lcsc, n1, n2, purpose in D.PASSIVES:
        anchor, (ax, ay), rot = spots[ref]
        fp = add_fp(ref, fpid, (ax, ay), rot, {"1": n1, "2": n2}, value,
                    fields={"LCSC": lcsc, "Purpose": purpose})
        px, py = pad_xy(ref, anchor)
        fp.Move(P(ax - px, ay - py))

    # Mounting holes
    for k, xy in enumerate([(3.5, 3.5), (BOARD_W - 3.5, 3.5),
                            (3.5, BOARD_H - 3.5), (BOARD_W - 3.5, BOARD_H - 3.5)], 1):
        add_fp(f"H{k}", "MountingHole:MountingHole_3.2mm_M3", xy, 0, {}, "M3", board_only=True)

    # Sanity: footprints landed where the routing below assumes
    assert pad_xy("J3", 6) == (J3X, round(J3Y + 10, 3)), pad_xy("J3", 6)
    assert pad_xy("R2", 1) == (16.0, round(j1(10)[1], 3)), pad_xy("R2", 1)
    assert pad_xy("R3", 2)[0] < pad_xy("R3", 1)[0]

    route()
    outline_and_fills()
    silkscreen()


# ---------------------------------------------------------------- routing --
def route():
    x_sense = 28.5  # vertical TDS sense bus under the DevKit
    x_flow = 14.5   # vertical flow run in the left strip
    x_tdsb = 19.0   # vertical TDS_B run, just left of J1
    x_5v = 9.0      # vertical +5V run in the left strip
    x_3v3 = J2X - 7.4

    # TDS sense: J3.1 straight across to J1.5 (D35), then the bus to R6/R4
    track([j3(1), j1(5), (x_sense, j1(5)[1]), (x_sense, j1(8)[1])], "TDS_SENSE")
    track([pad_xy("R6", 2), (x_sense, j1(7)[1])], "TDS_SENSE")
    track([pad_xy("R4", 2), (x_sense, j1(8)[1])], "TDS_SENSE")
    track([j1(7), pad_xy("R6", 1)], "TDS_HI")  # D33 -> 47k
    track([j1(8), pad_xy("R4", 1)], "TDS_LO")  # D25 -> 4.7k

    # TDS 2: J3.2 -> D26
    track([j3(2), (x_tdsb, j3(2)[1]), (x_tdsb, j1(9)[1]), j1(9)], "TDS_B")

    # Temperature: J3.3 -> via -> bottom layer up and over to J1.4 (D34),
    # then top layer under the DevKit to C2 and R3
    tv = (8.0, j3(3)[1])
    track([j3(3), tv], "TEMP")
    via(tv, "TEMP")
    track([tv, (tv[0], j1(4)[1]), j1(4)], "TEMP", layer=pcbnew.B_Cu)
    track([j1(4), pad_xy("R3", 2)], "TEMP")  # passes through C2 pad 1

    # +3V3: R3 -> J2.15 under the DevKit
    track([pad_xy("R3", 1), (x_3v3, j1(4)[1]), (x_3v3, j2(15)[1]), j2(15)], "+3V3", PWR_W)

    # Pulse: J3.4 -> R5 (pull-up) -> R1
    track([j3(4), pad_xy("R1", 1)], "PULSE_RAW")  # passes through R5 pad 2

    # Flow: R1 -> R2/C1 -> J1.10 (D27)
    track([pad_xy("R1", 2), (x_flow, j3(4)[1]), (x_flow, j1(10)[1]), j1(10)], "FLOW")

    # +5V: J3.6 and R5 -> J1.15 (VIN)
    track([j3(6), (x_5v, j3(6)[1])], "+5V", PWR_W)
    track([pad_xy("R5", 1), (x_5v, j3(6)[1]), (x_5v, j1(15)[1]), j1(15)], "+5V", PWR_W)

    # GND: the sensor's ground pin sits in a pocket boxed in by the pulse and
    # +5V tracks; a via ties that pocket to the bottom ground fill.
    gv = (7.0, j3(5)[1])
    track([j3(5), gv], "GND")
    via(gv, "GND")
    # SMD ground pads drop to the bottom fill through vias
    for ref in ("R2", "C1"):
        x, y = pad_xy(ref, 2)
        track([(x, y), (x, y + 1.5)], "GND")
        via((x, y + 1.5), "GND")
    x, y = pad_xy("C2", 2)
    track([(x, y), (x, y + 1.8)], "GND")
    via((x, y + 1.8), "GND")
    # Stitching between the two ground fills
    for xy in [(12, 45), (12, 16), (33, 45), (J2X - 3, 30), (BOARD_W - 2.5, 30),
               (33, 55), (16, 55), (3, 45), (3, 18)]:
        via(xy, "GND")


# ------------------------------------------------------- outline and fills --
def outline_and_fills():
    W, H = BOARD_W, BOARD_H
    line(pcbnew.Edge_Cuts, [(0, 0), (W, 0), (W, H), (0, H), (0, 0)], 0.1)
    full = [(0, 0), (W, 0), (W, H), (0, H)]
    zone([pcbnew.F_Cu], full, "GND")
    zone([pcbnew.B_Cu], full, "GND")
    # ESP32 antenna sits above the DevKit's top ~8 mm: keep that area copper-free
    zone([pcbnew.F_Cu, pcbnew.B_Cu],
         [(KIT_L - 1, 0), (KIT_R + 1, 0), (KIT_R + 1, J1Y - 2.2), (KIT_L - 1, J1Y - 2.2)],
         keepout=True)


# ------------------------------------------------------------- silkscreen --
def silkscreen():
    S = pcbnew.F_SilkS
    # DevKit outline so it's obvious which way it plugs in
    line(S, [(KIT_L, KIT_T), (KIT_R, KIT_T), (KIT_R, KIT_B), (KIT_L, KIT_B), (KIT_L, KIT_T)])
    cx = (KIT_L + KIT_R) / 2
    text("ESP32 DevKit V1", (cx, KIT_T + 2.5), 1.2)
    text("antenna this end", (cx, KIT_T + 4.3), 0.9)
    text("USB this end", (cx, KIT_B - 2.0), 0.9)
    # Sensor socket labels
    text("SENSOR", (J3X, J3Y - 3.6), 1.0)
    text("Water carrier rev A", (11.0, 52.0), 0.9)


def place_refs():
    """Move or hide reference labels so they don't collide."""
    def ref(r, xy=None, size=0.8, hide=False):
        t = fps[r].Reference()
        if hide:
            t.SetVisible(False)
            return
        t.SetPosition(P(*xy))
        t.SetTextAngleDegrees(0)
        t.SetTextSize(VECTOR2I(FromMM(size), FromMM(size)))
        t.SetTextThickness(FromMM(size * 0.15))

    for r in ("J3", "H1", "H2", "H3", "H4"):
        ref(r, hide=True)  # J3 is labelled SENSOR; holes need no label
    ref("R5", (11.0, j3(5)[1] + 0.5))
    ref("R1", (12.0, j3(4)[1] - 1.6))
    ref("R2", (16.0, j1(10)[1] + 4.9))
    ref("C1", (18.5, j1(10)[1] + 4.9))
    ref("R6", (26.0, j1(7)[1] - 1.6))
    ref("R4", (26.0, j1(8)[1] + 1.6))
    ref("C2", (31.9, j1(4)[1] + 0.9))
    ref("R3", (35.0, j1(4)[1] - 1.6))


def main():
    build()
    place_refs()
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pcbnew.SaveBoard(str(OUT), board)
    print(f"wrote {OUT}  ({BOARD_W} x {BOARD_H} mm)")


if __name__ == "__main__":
    main()
