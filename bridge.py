"""Runs on the computer the Arduino is plugged into.
    python bridge.py                 (auto-detects the port)
    python bridge.py --port COM3
Close the Arduino IDE Serial Monitor first.
"""
import argparse, os, sqlite3, time
from datetime import datetime, timezone

import requests
import serial
import serial.tools.list_ports
from dotenv import load_dotenv

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
CLOUD = bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)
DB = "sensor_data.db"


def init_db():
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,
        temperature REAL, humidity REAL, distance REAL, mq2 INTEGER, mq135 INTEGER,
        flags INTEGER, status INTEGER, relay INTEGER, warmup INTEGER)""")
    con.commit()
    return con


def find_port():
    for p in serial.tools.list_ports.comports():
        text = f"{p.description} {p.manufacturer}".lower()
        if any(k in text for k in ("arduino", "ch340", "usb serial", "usb-serial")):
            return p.device
    ports = list(serial.tools.list_ports.comports())
    return ports[0].device if ports else None


def parse(line):
    t, h, d, mq2, mq135, flags, status, relay, warm = line.split(",")
    dist = float(d)
    return {
        "temperature": float(t), "humidity": float(h),
        "distance": None if dist < 0 else dist,
        "mq2": int(mq2), "mq135": int(mq135), "flags": int(flags),
        "status": int(status), "relay": int(relay), "warmup": int(warm),
    }


def save_local(con, ts, r):
    con.execute("""INSERT INTO readings (ts,temperature,humidity,distance,mq2,mq135,flags,status,relay,warmup)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (ts, r["temperature"], r["humidity"], r["distance"], r["mq2"], r["mq135"],
                 r["flags"], r["status"], r["relay"], r["warmup"]))
    con.commit()


def save_cloud(ts, r):
    try:
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/readings",
            json={"ts": ts, **r},
            headers={"apikey": SUPABASE_SERVICE_KEY,
                     "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                     "Content-Type": "application/json", "Prefer": "return=minimal"},
            timeout=5)
        if resp.status_code >= 300:
            print("  cloud error:", resp.status_code, resp.text[:150])
    except requests.RequestException as e:
        print("  cloud unreachable (kept locally):", e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port")
    ap.add_argument("--baud", type=int, default=9600)
    args = ap.parse_args()

    con = init_db()
    print(f"cloud upload: {'ON' if CLOUD else 'OFF (local only)'} | Ctrl+C to stop")

    while True:
        try:
            port = args.port or find_port()
            if not port:
                raise serial.SerialException("no Arduino found")
            ser = serial.Serial(port, args.baud, timeout=5)
            time.sleep(2)
            print("Connected to", port)
            while True:
                line = ser.readline().decode(errors="ignore").strip()
                if not line:
                    continue
                try:
                    r = parse(line)
                except ValueError:
                    print("skipped:", line)
                    continue
                ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
                save_local(con, ts, r)
                if CLOUD:
                    save_cloud(ts, r)
                print(ts, r)
        except (serial.SerialException, OSError) as e:
            print("Connection lost, retrying in 3 s...", e)
            time.sleep(3)


if __name__ == "__main__":
    main()
