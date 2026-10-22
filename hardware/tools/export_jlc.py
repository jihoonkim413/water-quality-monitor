"""Build the JLCPCB order package for the carrier board.

    python hardware/tools/export_jlc.py

Writes hardware/water_carrier/jlcpcb/:
    water_carrier_gerbers.zip   upload on the PCB order page
    bom.csv                     upload at the "PCB Assembly" step
    cpl.csv                     upload at the "PCB Assembly" step

Only the SMD parts are in the BOM/CPL. The sockets (J1-J3) are through-hole
and soldered by hand, so the factory doesn't place them.
"""

import csv
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import design as D

ROOT = Path(__file__).resolve().parents[1] / "water_carrier"
PCB = ROOT / "water_carrier.kicad_pcb"
OUT = ROOT / "jlcpcb"
CLI = Path(os.environ["LOCALAPPDATA"]) / "Programs/KiCad/10.0/bin/kicad-cli.exe"
LAYERS = "F.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts"


def run(*args):
    subprocess.run([str(CLI), *map(str, args)], check=True, capture_output=True, text=True)


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    gerb = OUT / "gerbers"
    gerb.mkdir(parents=True)

    # Gerbers + drill files (JLCPCB's recommended KiCad settings)
    run("pcb", "export", "gerbers", "--layers", LAYERS, "--subtract-soldermask",
        "--check-zones", "-o", gerb, PCB)
    run("pcb", "export", "drill", "--format", "excellon", "--excellon-units", "mm",
        "--excellon-zeros-format", "decimal", "--excellon-oval-format", "alternate",
        "-o", gerb, PCB)
    zpath = OUT / "water_carrier_gerbers.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(gerb.iterdir()):
            z.write(f, f.name)
    files = sorted(f.name for f in gerb.iterdir())
    shutil.rmtree(gerb)

    # BOM: one row per value/footprint, grouped
    groups = {}
    for ref, value, fp, lcsc, *_ in D.PASSIVES:
        key = (value, fp.split(":")[1], lcsc)
        groups.setdefault(key, []).append(ref)
    with open(OUT / "bom.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (value, fp, lcsc), refs in sorted(groups.items(), key=lambda g: g[1][0]):
            w.writerow([value, ",".join(sorted(refs)), fp, lcsc])

    # CPL: KiCad placement file -> JLCPCB column names
    raw = OUT / "pos_raw.csv"
    run("pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "front",
        "--smd-only", "-o", raw, PCB)
    with open(raw, newline="") as f:
        rows = list(csv.DictReader(f))
    raw.unlink()
    with open(OUT / "cpl.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for r in sorted(rows, key=lambda r: r["Ref"]):
            rot = float(r["Rot"]) % 360
            w.writerow([r["Ref"], f'{float(r["PosX"]):.3f}mm', f'{float(r["PosY"]):.3f}mm',
                        "Top" if r["Side"].lower() == "top" else "Bottom", f"{rot:g}"])

    placed = {r["Ref"] for r in rows}
    expected = {p[0] for p in D.PASSIVES}
    assert placed == expected, f"CPL {sorted(placed)} != BOM {sorted(expected)}"
    print(f"gerber zip: {zpath.name} ({len(files)} files: {', '.join(files)})")
    print(f"bom.csv: {len(groups)} lines, cpl.csv: {len(rows)} parts")


if __name__ == "__main__":
    main()
