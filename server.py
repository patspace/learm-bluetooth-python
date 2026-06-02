#!/usr/bin/env python3
"""
Web UI for real-time LeArm animation control.

    pip install flask bleak
    python server.py

Then open http://localhost:5002
"""

import asyncio
import math
import threading
import time

from bleak import BleakClient, BleakScanner
from flask import Flask, jsonify, request, render_template

app = Flask(__name__)

CHAR_HANDLE = 32

# Shared state — read/written from both Flask and the BLE thread.
# Python's GIL makes plain dict access safe for simple scalar updates.
params = {
    "joints":      [6,    5,    4,    3,    2,    1   ],
    "centers":     [1500, 1500, 1500, 1000, 1500, 1500],
    "amplitude":   120,
    "period":      5.0,
    "phase_step":  0.40,
    "update_hz":   20,
    "mode":        "wave",   # "wave" | "spin_clap"
    # Spin & clap keyframe positions (tunable from UI)
    "sc_waist_coiled":      1000,
    "sc_waist_extended":    2000,
    "sc_shoulder_coiled":   1200,
    "sc_shoulder_extended": 1900,
    "sc_elbow_coiled":      2200,
    "sc_elbow_extended":    1300,
    "sc_wrist_coiled":      1800,
    "sc_wrist_extended":    1000,
}

status = {"running": False, "connected": False, "error": ""}
stop_flag = threading.Event()

SC_INT_KEYS = (
    "sc_waist_coiled", "sc_waist_extended",
    "sc_shoulder_coiled", "sc_shoulder_extended",
    "sc_elbow_coiled", "sc_elbow_extended",
    "sc_wrist_coiled", "sc_wrist_extended",
)


# ── BLE helpers ──────────────────────────────────────────────────────────────

def make_move(positions, duration_ms):
    count = len(positions)
    p = [count, duration_ms & 0xFF, (duration_ms >> 8) & 0xFF]
    for sid, pos in positions:
        pos = max(500, min(2500, int(pos)))
        p += [sid, pos & 0xFF, (pos >> 8) & 0xFF]
    return bytes([0x55, 0x55, len(p) + 2, 0x03] + p)


def sc_keyframes():
    """Build spin-and-clap keyframes from current params."""
    coiled = [
        (6, params["sc_waist_coiled"]),
        (5, params["sc_shoulder_coiled"]),
        (4, params["sc_elbow_coiled"]),
        (3, params["sc_wrist_coiled"]),
        (2, 1500),
        (1, 1500),
    ]
    extended = [
        (6, params["sc_waist_extended"]),
        (5, params["sc_shoulder_extended"]),
        (4, params["sc_elbow_extended"]),
        (3, params["sc_wrist_extended"]),
        (2, 1500),
        (1, 1500),
    ]
    return coiled, extended


async def find_arm():
    devices = await BleakScanner.discover(timeout=5.0)
    for d in devices:
        if d.name and "hiwonder" in d.name.lower():
            return d.address
    return None


async def wave_loop(client):
    start = time.time()
    while not stop_flag.is_set():
        t     = time.time() - start
        omega = 2 * math.pi / params["period"]
        hz    = params["update_hz"]
        amp   = params["amplitude"]
        ps    = params["phase_step"]
        positions = [
            (sid, params["centers"][i] + amp * math.sin(omega * t + i * ps))
            for i, sid in enumerate(params["joints"])
        ]
        dur = int(1000 / hz * 1.4)
        await client.write_gatt_char(CHAR_HANDLE, make_move(positions, dur), response=False)
        await asyncio.sleep(1.0 / hz)


async def spin_clap_loop(client):
    async def send(pos, dur, pause):
        await client.write_gatt_char(CHAR_HANDLE, make_move(pos, dur), response=False)
        await asyncio.sleep(pause)

    while not stop_flag.is_set():
        coiled, extended = sc_keyframes()
        await send(coiled,    1500, 1.8)
        if stop_flag.is_set(): break
        await send(extended,  2000, 2.3)
        if stop_flag.is_set(): break
        for _ in range(2):
            await send([(1, 2500)], 350, 0.45)
            if stop_flag.is_set(): break
            await send([(1, 1500)], 350, 0.45)
            if stop_flag.is_set(): break
        await send(coiled, 2000, 2.3)


async def run_animation():
    address = await find_arm()
    if not address:
        status["error"] = "Arm not found — is Bluetooth on?"
        status["running"] = False
        return

    try:
        async with BleakClient(address) as client:
            status["connected"] = True
            status["error"] = ""

            mode = params["mode"]
            home = sc_keyframes()[0] if mode == "spin_clap" else list(zip(params["joints"], params["centers"]))

            await client.write_gatt_char(CHAR_HANDLE, make_move(home, 2000), response=False)
            await asyncio.sleep(2.5)

            if mode == "spin_clap":
                await spin_clap_loop(client)
            else:
                await wave_loop(client)

            await client.write_gatt_char(CHAR_HANDLE, make_move(home, 2000), response=False)
            await asyncio.sleep(2.5)

    except Exception as e:
        status["error"] = str(e)
    finally:
        status["connected"] = False
        status["running"] = False


def _ble_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_animation())
    loop.close()


# ── Flask routes ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def get_status():
    return jsonify({**status, "params": params})


@app.route("/api/params", methods=["POST"])
def set_params():
    data = request.json or {}
    for key in ("amplitude", "period", "phase_step", "update_hz"):
        if key in data:
            params[key] = float(data[key])
    if "centers" in data:
        params["centers"] = [int(x) for x in data["centers"]]
    if "mode" in data and data["mode"] in ("wave", "spin_clap"):
        params["mode"] = data["mode"]
    for key in SC_INT_KEYS:
        if key in data:
            params[key] = int(data[key])
    return jsonify({"ok": True})


@app.route("/api/start", methods=["POST"])
def start():
    if status["running"]:
        return jsonify({"ok": True})
    stop_flag.clear()
    status["running"] = True
    status["error"] = ""
    threading.Thread(target=_ble_thread, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/stop", methods=["POST"])
def stop():
    stop_flag.set()
    return jsonify({"ok": True})


if __name__ == "__main__":
    print("LeArm control UI → http://localhost:5002")
    app.run(host="0.0.0.0", port=5002, debug=False)
