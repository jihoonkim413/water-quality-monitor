"""Home server: stores water sensor readings and serves them to the phone app.

Run:  python server/app.py        (or: uvicorn app:app --host 0.0.0.0 --port 8000)
Dashboard: http://<server>:8000/
API docs:  http://<server>:8000/docs

Reading data is open to anyone on your network; sending data needs the API key.
"""

import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
DB_PATH = os.environ.get("WATER_DB", str(HERE / "water.db"))
DASHBOARD = HERE / "static" / "index.html"


def _api_key():
    """WATER_API_KEY if set; otherwise, on the dev PC, the key the ESP32 was
    built with (firmware/include/secrets.h), so both always match."""
    if os.environ.get("WATER_API_KEY"):
        return os.environ["WATER_API_KEY"]
    secrets = HERE.parent / "firmware" / "include" / "secrets.h"
    if secrets.exists():
        m = re.search(r'#define\s+API_KEY\s+"([^"]*)"', secrets.read_text())
        if m:
            return m.group(1)
    return "change-me"


API_KEY = _api_key()

app = FastAPI(title="Water Quality")


class Reading(BaseModel):
    device_id: str
    ts: datetime
    flow_lpm: float
    liters: float
    total_liters: float | None = None
    temp_c: float | None = None
    tds_ppm: float | None = None


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


with db() as c:
    c.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY,
            device_id TEXT NOT NULL,
            ts TEXT NOT NULL,
            flow_lpm REAL, liters REAL, total_liters REAL,
            temp_c REAL, tds_ppm REAL
        )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_dev_ts ON readings(device_id, ts)")


def check_key(x_api_key: str | None = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(401, "bad API key")


def utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def where(since: str, device_id: str | None):
    sql, args = " WHERE ts >= ?", [since]
    if device_id:
        sql += " AND device_id = ?"
        args.append(device_id)
    return sql, args


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(DASHBOARD)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/readings", dependencies=[Depends(check_key)])
def add_readings(readings: list[Reading]):
    with db() as c:
        c.executemany(
            "INSERT INTO readings (device_id, ts, flow_lpm, liters, total_liters, temp_c, tds_ppm)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(r.device_id, utc_iso(r.ts), r.flow_lpm, r.liters, r.total_liters, r.temp_c, r.tds_ppm)
             for r in readings],
        )
    return {"stored": len(readings)}


@app.get("/api/readings/latest")
def latest(device_id: str | None = None):
    sql = "SELECT * FROM readings"
    args = []
    if device_id:
        sql += " WHERE device_id = ?"
        args.append(device_id)
    with db() as c:
        row = c.execute(sql + " ORDER BY ts DESC LIMIT 1", args).fetchone()
    if row is None:
        raise HTTPException(404, "no readings yet")
    return dict(row)


@app.get("/api/readings")
def history(device_id: str | None = None,
            hours: float = Query(24, gt=0, le=24 * 365),
            limit: int = Query(5000, gt=0, le=100000)):
    """Raw readings, newest `limit` within the window, oldest first."""
    since = utc_iso(datetime.now(timezone.utc) - timedelta(hours=hours))
    sql, args = where(since, device_id)
    with db() as c:
        rows = c.execute("SELECT * FROM readings" + sql + " ORDER BY ts DESC LIMIT ?",
                         args + [limit]).fetchall()
    return [dict(r) for r in reversed(rows)]


@app.get("/api/series")
def series(device_id: str | None = None,
           hours: float = Query(24, gt=0, le=24 * 365),
           points: int = Query(240, ge=10, le=2000)):
    """Readings averaged into about `points` time buckets, for charts.
    `liters` is the water used within each bucket."""
    bucket = max(10, int(hours * 3600 / points))
    since = utc_iso(datetime.now(timezone.utc) - timedelta(hours=hours))
    sql, args = where(since, device_id)
    with db() as c:
        rows = c.execute(
            "SELECT CAST(strftime('%s', ts) AS INTEGER) / ? AS b, MAX(ts) AS ts,"
            " AVG(tds_ppm) AS tds_ppm, AVG(temp_c) AS temp_c, AVG(flow_lpm) AS flow_lpm,"
            " SUM(liters) AS liters FROM readings" + sql + " GROUP BY b ORDER BY b",
            [bucket] + args,
        ).fetchall()
    return [{k: r[k] for k in ("ts", "tds_ppm", "temp_c", "flow_lpm", "liters")} for r in rows]


@app.get("/api/usage")
def usage(device_id: str | None = None, days: int = Query(7, gt=0, le=365)):
    """Liters used per day (UTC) for the last N days."""
    since = utc_iso(datetime.now(timezone.utc) - timedelta(days=days))
    sql, args = where(since, device_id)
    with db() as c:
        rows = c.execute("SELECT substr(ts, 1, 10) AS day, SUM(liters) AS liters FROM readings"
                         + sql + " GROUP BY day ORDER BY day", args).fetchall()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("WATER_PORT", "8000"))
    key_note = "from WATER_API_KEY" if os.environ.get("WATER_API_KEY") else (
        "from firmware/include/secrets.h" if API_KEY != "change-me" else "DEFAULT 'change-me'")
    print(f"Water server on http://0.0.0.0:{port}  (API key {key_note}, database {DB_PATH})", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=port)
