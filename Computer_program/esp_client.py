import os
import threading
import time

import requests

ESP_HOST = os.environ.get("ESP_HOST", "http://192.168.4.1")
DASHBOARD_HOST = os.environ.get("DASHBOARD_HOST", "http://127.0.0.1:5000")

# калібровка під конкретний дрон (підбирали експериментально)
HOVER_THROTTLE = int(os.environ.get("HOVER_THROTTLE", "1220"))
PITCH_FORWARD = 1580
PITCH_NEUTRAL = 1500
YAW_TURN = 1600
YAW_NEUTRAL = 1500

LINE_DURATION_S = float(os.environ.get("LINE_DURATION_S", "3"))
SQUARE_EDGE_DURATION_S = float(os.environ.get("SQUARE_EDGE_DURATION_S", "3"))
SQUARE_TURN_DURATION_S = float(os.environ.get("SQUARE_TURN_DURATION_S", "1.5"))
SQUARE_EDGES = 4

# AUX1=ARM, AUX2=ANGLE — тримає прошивка ESP
_session = requests.Session()
_lock = threading.Lock()

_state = {
    "is_armed": False,
    "esp_online": False,
    "mission": None,
    "mission_phase": "",
    "phase_start": 0.0,
    "square_edge": 0,
    "channels": {"r": 1500, "p": 1500, "t": 1000, "y": 1500},
    "last_cmd": "",
    "error": "",
}


def _hover():
    return {"r": 1500, "p": PITCH_NEUTRAL, "t": HOVER_THROTTLE, "y": YAW_NEUTRAL}


def _idle():
    return {"r": 1500, "p": PITCH_NEUTRAL, "t": 1000, "y": YAW_NEUTRAL}


def _send_update(ch):
    try:
        _session.get(f"{ESP_HOST}/update", params=ch, timeout=0.5)
        return True
    except requests.RequestException:
        return False


def _send_arm(armed):
    try:
        _session.get(
            f"{ESP_HOST}/cmd",
            params={"arm": "1" if armed else "0"},
            timeout=0.5,
        )
        return True
    except requests.RequestException:
        return False


def _post_status():
    with _lock:
        payload = {
            "esp_online": _state["esp_online"],
            "is_armed": _state["is_armed"],
            "mission": _state["mission"] or "",
            "mission_phase": _state["mission_phase"],
            "last_cmd": _state["last_cmd"],
            "error": _state["error"],
        }
    try:
        _session.post(f"{DASHBOARD_HOST}/api/drone/status", json=payload, timeout=0.5)
    except requests.RequestException:
        pass


def _end_mission(msg):
    with _lock:
        _state["mission"] = None
        _state["mission_phase"] = ""
        _state["square_edge"] = 0
        _state["phase_start"] = 0.0
        _state["channels"] = _hover() if _state["is_armed"] else _idle()
        _state["last_cmd"] = msg
    print(msg)
    _post_status()


def _start_mission(name):
    with _lock:
        if not _state["is_armed"]:
            _state["error"] = "Спочатку ARM"
            return False
        if _state["mission"]:
            _state["error"] = "Місія вже виконується"
            return False

        _state["mission"] = name
        _state["square_edge"] = 0
        _state["phase_start"] = time.monotonic()
        _state["error"] = ""
        _state["channels"]["t"] = HOVER_THROTTLE

        if name == "line":
            _state["mission_phase"] = "політ вперед"
            _state["channels"]["p"] = PITCH_FORWARD
        else:
            _state["mission_phase"] = "грань 1/4"
            _state["channels"]["p"] = PITCH_FORWARD
            _state["channels"]["y"] = YAW_NEUTRAL

    print(f"Місія {name.upper()} запущена")
    _post_status()
    return True


def _tick_mission(now):
    done = None

    with _lock:
        mission = _state["mission"]
        if not mission:
            return

        elapsed = now - _state["phase_start"]
        ch = _state["channels"]

        if mission == "line":
            ch["p"] = PITCH_FORWARD
            ch["t"] = HOVER_THROTTLE
            if elapsed >= LINE_DURATION_S:
                ch["p"] = PITCH_NEUTRAL
                done = "line"

        elif mission == "square":
            phase = _state["mission_phase"]
            n = _state["square_edge"] + 1

            if phase.startswith("грань"):
                ch["p"] = PITCH_FORWARD
                ch["y"] = YAW_NEUTRAL
                ch["t"] = HOVER_THROTTLE
                if elapsed >= SQUARE_EDGE_DURATION_S:
                    _state["mission_phase"] = f"поворот {n}/4"
                    _state["phase_start"] = now
                    ch["p"] = PITCH_NEUTRAL

            elif phase.startswith("поворот"):
                ch["p"] = PITCH_NEUTRAL
                ch["y"] = YAW_TURN
                ch["t"] = HOVER_THROTTLE
                if elapsed >= SQUARE_TURN_DURATION_S:
                    _state["square_edge"] += 1
                    ch["y"] = YAW_NEUTRAL
                    if _state["square_edge"] >= SQUARE_EDGES:
                        done = "square"
                    else:
                        nxt = _state["square_edge"] + 1
                        _state["mission_phase"] = f"грань {nxt}/4"
                        _state["phase_start"] = now

    if done == "line":
        _end_mission("LINE завершено")
    elif done == "square":
        _end_mission("SQUARE завершено")


def _handle_cmd(cmd, online):
    if cmd == "arm":
        ok = _send_arm(True)
        if ok:
            with _lock:
                _state["is_armed"] = True
                _state["channels"] = _hover()
                _state["last_cmd"] = "ARM"
                _state["error"] = ""
            print("ARM відправлено на ESP")
        else:
            with _lock:
                _state["error"] = "ESP недоступний"
        _post_status()
        return

    if cmd == "disarm":
        ok = _send_arm(False)
        with _lock:
            _state["is_armed"] = False
            _state["mission"] = None
            _state["mission_phase"] = ""
            _state["square_edge"] = 0
            _state["channels"] = _idle()
            _state["last_cmd"] = "DISARM"
            _state["error"] = "" if ok and online else "ESP недоступний"
        if ok:
            print("DISARM відправлено на ESP")
        _post_status()
        return

    if cmd in ("line", "square"):
        if not online:
            with _lock:
                _state["error"] = "ESP недоступний"
            _post_status()
            return
        if _start_mission(cmd):
            with _lock:
                _state["last_cmd"] = f"Місія {cmd.upper()}"
        _post_status()


def _loop():
    last_online = None

    while True:
        now = time.monotonic()

        with _lock:
            mission = _state["mission"]
            armed = _state["is_armed"]

        if mission:
            _tick_mission(now)
        elif armed:
            with _lock:
                _state["channels"] = _hover()

        with _lock:
            channels = dict(_state["channels"])

        online = _send_update(channels)
        with _lock:
            _state["esp_online"] = online

        if online != last_online:
            if online:
                print(f"ESP онлайн: {ESP_HOST}")
                with _lock:
                    _state["error"] = ""
            else:
                print("ESP офлайн — підключіться до Drone_Companion_AP")
                with _lock:
                    _state["error"] = "Підключіться до Wi-Fi Drone_Companion_AP"
            last_online = online
            _post_status()

        try:
            resp = _session.get(f"{DASHBOARD_HOST}/api/drone/pending", timeout=0.5)
            cmd = resp.json().get("cmd")
            if cmd in ("arm", "disarm", "line", "square"):
                _handle_cmd(cmd, online)
        except requests.RequestException:
            pass

        time.sleep(0.05)


def start_esp_client():
    threading.Thread(target=_loop, daemon=True, name="esp-client").start()
    print(f"ESP клієнт: {ESP_HOST}, hover={HOVER_THROTTLE}")
