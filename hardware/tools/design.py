"""Single source of truth for the carrier board: parts, values and connections.

The schematic and PCB generators both read this file. To change a part value,
the sensor's wire order or the connector type, edit it here and regenerate.
"""

# ------------------------------------------------------------------ choices --

# Sensor plug pitch: "PH" (2.0 mm) or "XH" (2.5 mm).  TODO: measure.
SENSOR_JST = "PH"

# Sensor plug wire order, pin 1 first.  TODO: confirm against the real plug.
# Guess from the product photo: blue, red, green, yellow, black, red.
SENSOR_PINS = ["TDS_SENSE", "TDS_B", "TEMP", "PULSE_RAW", "GND", "+5V"]
SENSOR_PIN_NAMES = ["TDS 1", "TDS 2", "Temp", "Pulse", "GND (-)", "+5V (+)"]

# Distance between the DevKit's two pin rows, centre to centre (mm).
# TODO: measure. 30-pin DevKit V1 boards are usually 25.4; some are 22.86.
DEVKIT_ROW_SPACING = 25.4

# DevKit V1 (30-pin) headers, pin 1 at the antenna end.
DEVKIT_LEFT = ["EN", "VP", "VN", "D34", "D35", "D32", "D33", "D25", "D26", "D27",
               "D14", "D12", "D13", "GND", "VIN"]
DEVKIT_RIGHT = ["D23", "D22", "TX0", "RX0", "D21", "D19", "D18", "D5", "TX2", "RX2",
                "D4", "D2", "D15", "GND", "3V3"]

# Which DevKit pin carries which net. Pins not listed are left unconnected.
DEVKIT_NETS = {
    "D34": "TEMP",
    "D35": "TDS_SENSE",
    "D33": "TDS_HI",
    "D25": "TDS_LO",
    "D26": "TDS_B",
    "D27": "FLOW",
    "GND": "GND",
    "VIN": "+5V",
    "3V3": "+3V3",
}

POWER_NETS = {"+5V", "+3V3", "GND"}

# -------------------------------------------------------------------- parts --
# pins: pin number -> net.  For R/C, pin 1 is the top end in the schematic.
# LCSC numbers are JLCPCB "basic" parts (no extra setup fee).

R0805 = "Resistor_SMD:R_0805_2012Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

PASSIVES = [
    # ref,  value,   footprint, LCSC,     pin1 net,    pin2 net,   purpose
    ("R5", "4.7k",  R0805, "C17673", "+5V",       "PULSE_RAW", "pulse pull-up"),
    ("R1", "10k",   R0805, "C17414", "PULSE_RAW", "FLOW",      "pulse divider"),
    ("R2", "20k",   R0805, "C4328",  "FLOW",      "GND",       "pulse divider"),
    ("C1", "1nF",   C0805, "C46653", "FLOW",      "GND",       "pulse filter"),
    ("R3", "10k",   R0805, "C17414", "+3V3",      "TEMP",      "thermistor pull-up"),
    ("C2", "100nF", C0805, "C49678", "TEMP",      "GND",       "temperature filter"),
    ("R4", "4.7k",  R0805, "C17673", "TDS_LO",    "TDS_SENSE", "TDS ref, tap water"),
    ("R6", "47k",   R0805, "C17713", "TDS_HI",    "TDS_SENSE", "TDS ref, filtered water"),
]

SENSOR_FOOTPRINT = {
    "PH": "Connector_JST:JST_PH_B6B-PH-K_1x06_P2.00mm_Vertical",
    "XH": "Connector_JST:JST_XH_B6B-XH-A_1x06_P2.50mm_Vertical",
}[SENSOR_JST]

HEADER_FOOTPRINT = "Connector_PinSocket_2.54mm:PinSocket_1x15_P2.54mm_Vertical"


def devkit_pin_nets(names):
    return {i + 1: DEVKIT_NETS.get(n) for i, n in enumerate(names)}
