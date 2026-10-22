"""Snap-fit case for the water sensor carrier board + ESP32 DevKit V1.

Run inside FreeCAD (Python console or macro):
    exec(open(r"C:/repos/water_quality/hardware/case/make_case.py").read())

Creates document "WaterCase" with Base, Lid and see-through reference parts,
then exports base.stl and lid.stl next to this file.

Coordinates: X/Y match the KiCad board (origin at the board's top-left corner,
Y flipped so it points up), Z up from the outside of the case floor.
Front (Y = 0 side) is the USB end; back is the antenna end.
"""

import os

import FreeCAD as App
import Part
from FreeCAD import Vector as V

HERE = r"C:/repos/water_quality/hardware/case"
FONT = r"C:/Windows/Fonts/arialbd.ttf"

# ------------------------------------------------- board (from gen_pcb.py) --
BW, BH, BT = 55.0, 60.0, 1.6                 # carrier board size, thickness
HOLES_K = [(3.5, 3.5), (51.5, 3.5), (3.5, 56.5), (51.5, 56.5)]
J1X, J2X = 22.0, 47.4                        # DevKit socket rows (KiCad x)
KIT_W, KIT_LEN = 28.5, 51.5                  # DevKit V1 board
KIT_CX = (J1X + J2X) / 2
KIT_TOP_K = 7.0                              # antenna edge (KiCad y)
KIT_BOT_K = KIT_TOP_K + KIT_LEN              # USB edge (KiCad y)
SENSOR_K = (5.0, 29.16)                      # middle of the JST socket


def fy(y_kicad):
    """KiCad y (down) -> case Y (up)."""
    return BH - y_kicad


# ------------------------------------- stack heights (measure to confirm) --
FLOOR = 2.0        # case floor
STANDOFF = 5.0     # room for through-hole pins under the board
HEADER_H = 8.5     # female socket height on the carrier
KIT_SPACER = 2.5   # plastic spacer on the DevKit's own pins
KIT_PCB = 1.6
MODULE_H = 3.2     # ESP32 module shield above the DevKit board
USB_H = 3.0        # micro-USB socket height above the DevKit board
TOP_CLEAR = 2.0    # air gap under the lid

# ------------------------------------------------------------ case shape --
WALL = 2.0
GAP = 0.6          # board edge to inner wall
R_OUT = 3.0        # outer corner radius
LID_T = 2.0
LIP_H = 4.0        # lid lip that drops inside the walls
LIP_T = 1.4
FIT = 0.2          # lip-to-wall clearance per side
SNAP_R = 0.5       # snap bump radius on the lip
GROOVE_R = 0.65    # matching groove in the walls

# Derived heights
Z_BOARD_BOT = FLOOR + STANDOFF
Z_BOARD_TOP = Z_BOARD_BOT + BT
Z_KIT_BOT = Z_BOARD_TOP + HEADER_H + KIT_SPACER
Z_KIT_TOP = Z_KIT_BOT + KIT_PCB
Z_USB = Z_KIT_TOP + USB_H / 2
H_BASE = Z_KIT_TOP + MODULE_H + TOP_CLEAR    # top of the base walls
Z_SNAP = H_BASE - LIP_H / 2

# Inner / outer outlines
IX0, IY0, IX1, IY1 = -GAP, -GAP, BW + GAP, BH + GAP
OX0, OY0, OX1, OY1 = IX0 - WALL, IY0 - WALL, IX1 + WALL, IY1 + WALL

# Openings (case coordinates)
USB_W, USB_HGT = 12.0, 9.0                   # fits a micro-USB plug's overmold
SENSOR_Y = fy(SENSOR_K[1])
SENSOR_W, SENSOR_DEPTH = 7.0, 9.0            # cable notch in the left wall
BTN_Y = fy(KIT_BOT_K - 4.5)                  # EN/BOOT, ~4.5 mm from USB edge
BTN_DX = 9.0                                 # buttons either side of USB
LED_Y = fy(KIT_BOT_K - 9.0)                  # LEDs just behind the buttons
SNAP_Y = [IY0 + 12, IY1 - 12]                # snap positions on left/right


# --------------------------------------------------------------- helpers --
def rbox(x0, y0, x1, y1, z0, h, r):
    """Box with vertical edges rounded to radius r."""
    b = Part.makeBox(x1 - x0, y1 - y0, h, V(x0, y0, z0))
    if r > 0.01:
        vert = [e for e in b.Edges
                if abs(e.Vertexes[0].Point.x - e.Vertexes[1].Point.x) < 1e-6
                and abs(e.Vertexes[0].Point.y - e.Vertexes[1].Point.y) < 1e-6]
        b = b.makeFillet(r, vert)
    return b


def cyl_z(x, y, z0, h, r):
    return Part.makeCylinder(r, h, V(x, y, z0))


def cyl_y(x, y0, z, length, r):
    return Part.makeCylinder(r, length, V(x, y0, z), V(0, 1, 0))


def slot_y(x, y, z0, h, width, length):
    """Rounded slot running along Y."""
    r = width / 2
    s = Part.makeBox(width, length - width, h, V(x - r, y - length / 2 + r, z0))
    s = s.fuse(cyl_z(x, y - length / 2 + r, z0, h, r))
    s = s.fuse(cyl_z(x, y + length / 2 - r, z0, h, r))
    return s.removeSplitter()


def text_solid(s, size, cx, cy, z_top, depth):
    """Engraving tool: text centred on (cx, cy), cutting down from z_top."""
    try:
        chars = Part.makeWireString(s, FONT, size)
        faces = []
        for wires in chars:
            if wires:
                faces.append(Part.makeFace(wires, "Part::FaceMakerBullseye"))
        shape = Part.makeCompound(faces)
        bb = shape.BoundBox
        shape.translate(V(cx - bb.Center.x, cy - bb.Center.y, z_top - depth))
        return shape.extrude(V(0, 0, depth + 0.5))
    except Exception as e:
        print("text skipped:", s, e)
        return None


# ------------------------------------------------------------------ base --
def make_base():
    base = rbox(OX0, OY0, OX1, OY1, 0, H_BASE, R_OUT)
    base = base.cut(rbox(IX0, IY0, IX1, IY1, FLOOR, H_BASE, R_OUT - WALL))

    # Standoffs for the carrier board (M3 self-tapping, 2.6 mm pilot)
    for x, yk in HOLES_K:
        y = fy(yk)
        base = base.fuse(cyl_z(x, y, FLOOR - 0.01, STANDOFF + 0.01, 3.0))
        base = base.cut(cyl_z(x, y, FLOOR + 0.6, STANDOFF, 1.3))

    # USB notch in the front wall, open at the top
    base = base.cut(Part.makeBox(USB_W, WALL + 2, H_BASE,
                                 V(KIT_CX - USB_W / 2, OY0 - 1, Z_USB - USB_HGT / 2)))
    # Sensor cable notch in the left wall, open at the top
    base = base.cut(Part.makeBox(WALL + 2, SENSOR_W, SENSOR_DEPTH + 1,
                                 V(OX0 - 1, SENSOR_Y - SENSOR_W / 2, H_BASE - SENSOR_DEPTH)))

    # Vent slots: right wall and back wall, below the snap zone
    vz0, vh = Z_BOARD_TOP + 2, 9.0
    for y in [12, 20, 28, 36, 44]:
        base = base.cut(Part.makeBox(WALL + 2, 1.6, vh, V(IX1 - 1, y, vz0)))
    for x in [12, 20, 28, 36, 44]:
        base = base.cut(Part.makeBox(1.6, WALL + 2, vh, V(x, IY1 - 1, vz0)))

    # Snap grooves on the inside of the left and right walls
    for y in SNAP_Y:
        for x in (IX0, IX1):
            base = base.cut(cyl_y(x, y - 5.5, Z_SNAP, 11.0, GROOVE_R))
    return base.removeSplitter()


# ------------------------------------------------------------------- lid --
def make_lid():
    lid = rbox(OX0, OY0, OX1, OY1, H_BASE, LID_T, R_OUT)

    # Lip that drops inside the walls
    lx0, ly0, lx1, ly1 = IX0 + FIT, IY0 + FIT, IX1 - FIT, IY1 - FIT
    lip = rbox(lx0, ly0, lx1, ly1, H_BASE - LIP_H, LIP_H + 0.01, R_OUT - WALL)
    lip = lip.cut(rbox(lx0 + LIP_T, ly0 + LIP_T, lx1 - LIP_T, ly1 - LIP_T,
                       H_BASE - LIP_H - 1, LIP_H + 2, 0))
    # Gaps in the lip at the USB and sensor notches
    lip = lip.cut(Part.makeBox(USB_W + 1, LIP_T + 2, LIP_H + 1,
                               V(KIT_CX - (USB_W + 1) / 2, ly0 - 1, H_BASE - LIP_H - 0.5)))
    lip = lip.cut(Part.makeBox(LIP_T + 2, SENSOR_W + 1, LIP_H + 1,
                               V(lx0 - 1, SENSOR_Y - (SENSOR_W + 1) / 2, H_BASE - LIP_H - 0.5)))
    # Snap bumps on the outside of the lip
    for y in SNAP_Y:
        lip = lip.fuse(cyl_y(lx0, y - 4.5, Z_SNAP, 9.0, SNAP_R))
        lip = lip.fuse(cyl_y(lx1, y - 4.5, Z_SNAP, 9.0, SNAP_R))
    lid = lid.fuse(lip)

    top = H_BASE + LID_T
    # Button access slots (press with a paperclip)
    for dx in (-BTN_DX, BTN_DX):
        lid = lid.cut(slot_y(KIT_CX + dx, BTN_Y, H_BASE - 1, LID_T + 2, 3.0, 6.0))
    # LED window: lid thinned to 0.6 mm (light shows through light filament)
    lid = lid.cut(Part.makeBox(16.0, 5.0, LID_T, V(KIT_CX - 8.0, LED_Y - 2.5, H_BASE + 0.6)))

    # Lid vents over the board area
    for x in [6, 10, 14]:
        lid = lid.cut(slot_y(x, fy(45), H_BASE - 1, LID_T + 2, 1.6, 14.0))

    # Engraved labels
    for s, size, cx, cy in [("WATER", 6.0, KIT_CX, fy(25)),
                            ("EN", 2.5, KIT_CX - BTN_DX - 4.5, BTN_Y),
                            ("BOOT", 2.5, KIT_CX + BTN_DX + 7.0, BTN_Y),
                            ("USB", 2.5, KIT_CX, fy(KIT_BOT_K) + 2.0)]:
        t = text_solid(s, size, cx, cy, top, 0.6)
        if t is not None:
            lid = lid.cut(t)
    return lid.removeSplitter()


# ------------------------------------------------------- reference parts --
def make_reference():
    board = Part.makeBox(BW, BH, BT, V(0, 0, Z_BOARD_BOT))
    for x, yk in HOLES_K:
        board = board.cut(cyl_z(x, fy(yk), Z_BOARD_BOT - 1, BT + 2, 1.6))
    kit = Part.makeBox(KIT_W, KIT_LEN, KIT_PCB,
                       V(KIT_CX - KIT_W / 2, fy(KIT_BOT_K), Z_KIT_BOT))
    module = Part.makeBox(18.0, 25.5, MODULE_H,
                          V(KIT_CX - 9.0, fy(KIT_TOP_K) - 25.5, Z_KIT_TOP))
    usb = Part.makeBox(8.0, 5.5, USB_H, V(KIT_CX - 4.0, fy(KIT_BOT_K) - 0.8, Z_KIT_TOP))
    sockets = [Part.makeBox(2.5, 38.1, HEADER_H, V(x - 1.25, fy(14.0) - 36.83, Z_BOARD_TOP))
               for x in (J1X, J2X)]
    jst = Part.makeBox(4.5, 14.0, 6.0, V(SENSOR_K[0] - 2.2, SENSOR_Y - 7.0, Z_BOARD_TOP))
    return {"RefBoard": (board, (0.1, 0.45, 0.2)),
            "RefDevKit": (kit.fuse([module, usb]), (0.15, 0.15, 0.2)),
            "RefSockets": (sockets[0].fuse(sockets[1]), (0.1, 0.1, 0.1)),
            "RefJST": (jst, (0.95, 0.95, 0.95))}


# ---------------------------------------------------------- print files --
def print_oriented(base, lid):
    """Both parts sitting on the bed (z = 0): base upright, lid upside down,
    side by side with a 10 mm gap."""
    b = base.copy()
    b.translate(V(-b.BoundBox.XMin, -b.BoundBox.YMin, -b.BoundBox.ZMin))
    l = lid.copy()
    l.rotate(V(0, 0, 0), V(1, 0, 0), 180)   # flat top face down on the bed
    l.translate(V(-l.BoundBox.XMin + b.BoundBox.XMax + 10,
                  -l.BoundBox.YMin, -l.BoundBox.ZMin))
    return b, l


def export_print_files(doc, base, lid):
    import Mesh
    import MeshPart

    def mesh(shape):
        return Mesh.Mesh(MeshPart.meshFromShape(Shape=shape, LinearDeflection=0.05,
                                                AngularDeflection=0.2, Relative=False))

    b, l = print_oriented(base, lid)
    for label, shape in (("base", b), ("lid", l)):
        m = mesh(shape)
        bb = m.BoundBox
        m.translate(-bb.XMin, -bb.YMin, 0)    # each STL on its own at the origin
        m.write(os.path.join(HERE, f"{label}.stl"))

    # One 3MF with both parts as separate objects, ready for Bambu Studio
    objs = []
    for label, shape in (("case_base", b), ("case_lid", l)):
        o = doc.addObject("Mesh::Feature", label)
        o.Mesh = mesh(shape)
        if App.GuiUp:
            o.ViewObject.Visibility = False
        objs.append(o)
    Mesh.export(objs, os.path.join(HERE, "water_case.3mf"))
    for o in objs:
        doc.removeObject(o.Name)


# ------------------------------------------------------------------- main --
def build():
    name = "WaterCase"
    if name in App.listDocuments():
        App.closeDocument(name)
    doc = App.newDocument(name)

    base, lid = make_base(), make_lid()
    for label, shape, color in (("Base", base, (0.85, 0.87, 0.9)),
                                ("Lid", lid, (0.55, 0.75, 0.95))):
        obj = doc.addObject("Part::Feature", label)
        obj.Shape = shape
        if App.GuiUp:
            obj.ViewObject.ShapeColor = color
    for label, (shape, color) in make_reference().items():
        obj = doc.addObject("Part::Feature", label)
        obj.Shape = shape
        if App.GuiUp:
            obj.ViewObject.ShapeColor = color
            obj.ViewObject.Transparency = 40
    doc.recompute()

    export_print_files(doc, base, lid)
    doc.saveAs(os.path.join(HERE, "water_case.FCStd"))

    print(f"outer {OX1 - OX0:.1f} x {OY1 - OY0:.1f} x {H_BASE + LID_T:.1f} mm "
          f"(base wall height {H_BASE:.1f})")
    print(f"base valid={base.isValid()} solids={len(base.Solids)}; "
          f"lid valid={lid.isValid()} solids={len(lid.Solids)}")
    return doc


build()
