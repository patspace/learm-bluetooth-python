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
}

status = {"running": False, "connected": False, "error": ""}
stop_flag = threading.Event()

# Spin-and-clap keyframes (waist, shoulder, elbow, wrist pitch, wrist roll, gripper)
SC_CONDENSED = [(6, 1500), (5, 700),  (4, 2300), (3, 2000), (2, 1500), (1, 1500)]
SC_RAISED    = [(6, 1500), (5, 2200), (4, 1200), (3, 1000), (2, 1500), (1, 1500)]
SC_OPEN      = [(1, 2500)]
SC_CLOSED    = [(1, 1500)]


# ── BLE helpers ──────────────────────────────────────────────────────────────

def make_move(positions, duration_ms):
    count = len(positions)
    p = [count, duration_ms & 0xFF, (duration_ms >> 8) & 0xFF]
    for sid, pos in positions:
        pos = max(500, min(2500, int(pos)))
        p += [sid, pos & 0xFF, (pos >> 8) & 0xFF]
    return bytes([0x55, 0x55, len(p) + 2, 0x03] + p)


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
        await send(SC_CONDENSED, 1500, 1.8)
        if stop_flag.is_set(): break
        await send(SC_RAISED, 2000, 2.3)
        if stop_flag.is_set(): break
        # open-close 2x
        for _ in range(2):
            await send(SC_OPEN,  350, 0.45)
            if stop_flag.is_set(): break
            await send(SC_CLOSED, 350, 0.45)
            if stop_flag.is_set(): break
        await send(SC_CONDENSED, 2000, 2.3)


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
            home = SC_CONDENSED if mode == "spin_clap" else list(zip(params["joints"], params["centers"]))

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
