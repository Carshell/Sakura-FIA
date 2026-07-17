import os
import time
import sqlite3
from datetime import datetime
from threading import Lock

import cv2
import numpy as np
from flask import Flask, Response, jsonify, request, render_template_string

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR")

if DATA_DIR:
    STATIC_IMAGES_DIR = os.path.join(DATA_DIR, "static", "images")
    DB_PATH = os.path.join(DATA_DIR, "drone_data.db")
    STATIC_ROOT = os.path.join(DATA_DIR, "static")
else:
    PROJECT_ROOT = os.path.dirname(BASE_DIR)
    STATIC_IMAGES_DIR = os.path.join(PROJECT_ROOT, "static", "images")
    DB_PATH = os.path.join(BASE_DIR, "drone_data.db")
    STATIC_ROOT = os.path.join(PROJECT_ROOT, "static")

os.makedirs(STATIC_IMAGES_DIR, exist_ok=True)

app = Flask(
    __name__,
    static_folder=STATIC_ROOT,
    static_url_path="/static",
)

frame_lock = Lock()
latest_frame = None
frames_received = 0

cmd_lock = Lock()
pending_drone_cmd = None

drone_status_lock = Lock()
drone_status = {
    "esp_online": False,
    "is_armed": False,
    "mission": "",
    "mission_phase": "",
    "last_cmd": "",
    "error": "Підключіться до Wi-Fi Drone_Companion_AP",
}


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS targets
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT,
                  lat TEXT,
                  lon TEXT,
                  brigade TEXT,
                  image_path TEXT,
                  object_type TEXT,
                  confidence TEXT)"""
    )
    c.execute("PRAGMA table_info(targets)")
    columns = {row[1] for row in c.fetchall()}
    if "object_type" not in columns:
        c.execute("ALTER TABLE targets ADD COLUMN object_type TEXT DEFAULT 'Невідомо'")
    if "confidence" not in columns:
        c.execute("ALTER TABLE targets ADD COLUMN confidence TEXT DEFAULT ''")
    conn.commit()
    conn.close()


def get_targets():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM targets ORDER BY id DESC")
    data = c.fetchall()
    conn.close()
    return data


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="uk">
<head>
    <meta charset="UTF-8">
    <title>Центр Керування Дроном</title>
    <style>
        * { box-sizing: border-box; }
        body {
            background-color: #121212;
            color: #ffffff;
            font-family: 'Segoe UI', sans-serif;
            margin: 0;
            padding: 20px;
        }
        h1 {
            text-align: center;
            color: #4CAF50;
            margin-bottom: 24px;
        }
        .layout {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            align-items: start;
        }
        @media (max-width: 1100px) {
            .layout { grid-template-columns: 1fr; }
        }
        .panel {
            background-color: #1e1e1e;
            border: 1px solid #333;
            border-radius: 8px;
            padding: 16px;
        }
        .panel h2 {
            margin: 0 0 12px 0;
            font-size: 1.1rem;
            color: #81c784;
        }
        .video-wrap {
            background: #000;
            border-radius: 6px;
            overflow: hidden;
            min-height: 360px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .video-wrap img {
            width: 100%;
            display: block;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            background-color: #1e1e1e;
        }
        th, td {
            border: 1px solid #333;
            padding: 10px;
            text-align: center;
            font-size: 0.9rem;
        }
        th { background-color: #333; }
        .target-img {
            max-width: 140px;
            border-radius: 5px;
            border: 1px solid #555;
        }
        .badge {
            background: #d32f2f;
            padding: 4px 10px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 0.85rem;
        }
        .status {
            text-align: center;
            color: #aaa;
            font-size: 0.85rem;
            margin-top: 8px;
        }
        .empty-row td {
            color: #888;
            padding: 24px;
        }
        .drone-controls {
            display: flex;
            gap: 12px;
            justify-content: center;
            margin: 16px 0 8px;
        }
        .btn-arm {
            background: #d32f2f;
            color: white;
            border: none;
            border-radius: 6px;
            padding: 10px 28px;
            font-weight: bold;
            cursor: pointer;
        }
        .btn-disarm {
            background: #555;
            color: white;
            border: none;
            border-radius: 6px;
            padding: 10px 28px;
            font-weight: bold;
            cursor: pointer;
        }
        .btn-mission {
            background: #1565c0;
            color: white;
            border: none;
            border-radius: 6px;
            padding: 10px 28px;
            font-weight: bold;
            cursor: pointer;
        }
        .btn-mission:disabled,
        .btn-arm:disabled,
        .btn-disarm:disabled {
            opacity: 0.4;
            cursor: not-allowed;
        }
        .mission-controls { margin-top: 4px; }
        .esp-online { color: #4caf50; }
        .esp-offline { color: #f44336; }
    </style>
</head>
<body>
    <h1>Центр Керування Дроном</h1>

    <div class="layout">
        <div class="panel">
            <h2>Live-відео з дрона</h2>
            <div class="video-wrap">
                <img id="live-video" src="/video_feed" alt="FPV Drone Camera">
            </div>
            <p class="status">Потік оновлюється автоматично</p>

            <h2 style="margin-top: 20px;">Керування дроном</h2>
            <p id="esp-status" class="status esp-offline">
                ESP offline — підключіть ноут до Wi-Fi Drone_Companion_AP
            </p>
            <div class="drone-controls">
                <button id="btn-arm" class="btn-arm" onclick="sendDroneCmd('arm')">ARM</button>
                <button id="btn-disarm" class="btn-disarm" onclick="sendDroneCmd('disarm')" disabled>DISARM</button>
            </div>
            <div class="drone-controls mission-controls">
                <button id="btn-line" class="btn-mission" onclick="sendDroneCmd('line')" disabled>Лінія</button>
                <button id="btn-square" class="btn-mission" onclick="sendDroneCmd('square')" disabled>Квадрат</button>
            </div>
            <p id="cmd-status" class="status"></p>
        </div>

        <div class="panel">
            <h2>Виявлені цілі</h2>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Час</th>
                        <th>Координати</th>
                        <th>Тип об'єкта</th>
                        <th>Впевненість</th>
                        <th>Фото</th>
                    </tr>
                </thead>
                <tbody id="targets-body">
                    {% for target in targets %}
                    <tr>
                        <td>{{ target[0] }}</td>
                        <td>{{ target[1] }}</td>
                        <td>Ш: {{ target[2] }}<br>Д: {{ target[3] }}</td>
                        <td><span class="badge">{{ target[6] if target|length > 6 else 'Невідомо' }}</span></td>
                        <td>{{ target[7] if target|length > 7 else '-' }}</td>
                        <td><img class="target-img" src="/{{ target[5] }}" alt="Target"></td>
                    </tr>
                    {% else %}
                    <tr class="empty-row">
                        <td colspan="6">Цілей ще не виявлено</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            <p class="status">Таблиця оновлюється кожні 3 секунди</p>
        </div>
    </div>

    <script>
        function refreshTargets() {
            fetch('/api/targets')
                .then(r => r.json())
                .then(targets => {
                    const tbody = document.getElementById('targets-body');
                    if (!targets.length) {
                        tbody.innerHTML = '<tr class="empty-row"><td colspan="6">Цілей ще не виявлено</td></tr>';
                        return;
                    }
                    tbody.innerHTML = targets.map(t => `
                        <tr>
                            <td>${t.id}</td>
                            <td>${t.timestamp}</td>
                            <td>Ш: ${t.lat}<br>Д: ${t.lon}</td>
                            <td><span class="badge">${t.object_type || 'Невідомо'}</span></td>
                            <td>${t.confidence || '-'}</td>
                            <td><img class="target-img" src="/${t.image_path}" alt="Target"></td>
                        </tr>
                    `).join('');
                })
                .catch(() => {});
        }
        setInterval(refreshTargets, 3000);

        function sendDroneCmd(cmd) {
            fetch('/api/drone/cmd', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({cmd: cmd})
            })
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    document.getElementById('cmd-status').textContent = data.error;
                } else {
                    document.getElementById('cmd-status').textContent = data.message || 'OK';
                }
            })
            .catch(() => {
                document.getElementById('cmd-status').textContent = 'Помилка відправки команди';
            });
        }

        function refreshDroneStatus() {
            fetch('/api/drone/status')
                .then(r => r.json())
                .then(s => {
                    const statusEl = document.getElementById('esp-status');
                    if (s.esp_online) {
                        const armedTxt = s.is_armed ? ' | ARMED' : ' | DISARMED';
                        statusEl.textContent = 'ESP online' + armedTxt;
                        statusEl.className = 'status esp-online';
                    } else {
                        statusEl.textContent = s.error || 'ESP offline — Wi-Fi Drone_Companion_AP';
                        statusEl.className = 'status esp-offline';
                    }

                    const armed = !!s.is_armed;
                    const missionActive = !!s.mission;
                    document.getElementById('btn-arm').disabled = armed || missionActive;
                    document.getElementById('btn-disarm').disabled = !armed;
                    document.getElementById('btn-line').disabled = !armed || missionActive;
                    document.getElementById('btn-square').disabled = !armed || missionActive;

                    let statusText = s.last_cmd || '';
                    if (s.mission) {
                        const phase = s.mission_phase ? ` (${s.mission_phase})` : '';
                        statusText = `Місія ${s.mission.toUpperCase()}${phase}`;
                    } else if (s.error && !s.esp_online) {
                        statusText = s.error;
                    }
                    if (statusText) {
                        document.getElementById('cmd-status').textContent = statusText;
                    }
                })
                .catch(() => {});
        }
        refreshDroneStatus();
        setInterval(refreshDroneStatus, 1000);
    </script>
</body>
</html>
"""


def generate_frames():
    placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(
        placeholder,
        "Waiting for antenna...",
        (60, 240),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (120, 120, 120),
        2,
    )

    while True:
        with frame_lock:
            frame = latest_frame.copy() if latest_frame is not None else placeholder

        _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
        )
        time.sleep(0.033)


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE, targets=get_targets())


@app.route("/video_feed")
def video_feed():
    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/api/frame", methods=["POST"])
def upload_frame():
    global latest_frame, frames_received

    if "image" not in request.files:
        return "No image provided", 400

    file_bytes = request.files["image"].read()
    nparr = np.frombuffer(file_bytes, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if frame is not None:
        with frame_lock:
            latest_frame = frame
            frames_received += 1
            if frames_received == 1:
                print("Отримано перший кадр відео з дрона")

    return "", 204


@app.route("/api/drone/cmd", methods=["POST"])
def drone_cmd():
    global pending_drone_cmd

    data = request.get_json(silent=True) or {}
    cmd = data.get("cmd", "")
    valid_cmds = ("arm", "disarm", "line", "square")
    if cmd not in valid_cmds:
        return jsonify({"error": "invalid cmd"}), 400

    with drone_status_lock:
        is_armed = drone_status.get("is_armed", False)
        mission = drone_status.get("mission", "")

    if cmd in ("line", "square") and not is_armed:
        return jsonify({"error": "Спочатку натисніть ARM"}), 400
    if cmd in ("line", "square") and mission:
        return jsonify({"error": "Місія вже виконується"}), 400

    with cmd_lock:
        pending_drone_cmd = cmd

    labels = {
        "arm": "ARM",
        "disarm": "DISARM",
        "line": "LINE (5 м вперед)",
        "square": "SQUARE (2x2 м)",
    }
    return jsonify({"status": "ok", "message": f"Команду {labels[cmd]} надіслано"})


@app.route("/api/drone/pending")
def drone_pending():
    global pending_drone_cmd

    with cmd_lock:
        cmd = pending_drone_cmd
        pending_drone_cmd = None

    return jsonify({"cmd": cmd})


@app.route("/api/drone/status", methods=["GET", "POST"])
def drone_status_api():
    global drone_status

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        with drone_status_lock:
            drone_status.update({
                "esp_online": bool(data.get("esp_online", drone_status.get("esp_online", False))),
                "is_armed": bool(data.get("is_armed", drone_status.get("is_armed", False))),
                "mission": data.get("mission", drone_status.get("mission", "")),
                "mission_phase": data.get("mission_phase", drone_status.get("mission_phase", "")),
                "last_cmd": data.get("last_cmd", drone_status.get("last_cmd", "")),
                "error": data.get("error", drone_status.get("error", "")),
            })
        return jsonify({"status": "ok"})

    with drone_status_lock:
        return jsonify(drone_status)


@app.route("/api/targets")
def api_targets():
    rows = get_targets()
    return jsonify(
        [
            {
                "id": r[0],
                "timestamp": r[1],
                "lat": r[2],
                "lon": r[3],
                "brigade": r[4],
                "image_path": r[5],
                "object_type": r[6] if len(r) > 6 else "Невідомо",
                "confidence": r[7] if len(r) > 7 else "",
            }
            for r in rows
        ]
    )


@app.route("/api/upload", methods=["POST"])
def upload():
    if "image" not in request.files:
        return "No image provided", 400

    image = request.files["image"]
    lat = request.form.get("lat", "Невідомо")
    lon = request.form.get("lon", "Невідомо")
    brigade = request.form.get("brigade", "Авто-розподіл")
    object_type = request.form.get("object_type", "Невідомо")
    confidence = request.form.get("confidence", "")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filename = f"target_{datetime.now().strftime('%H%M%S')}.jpg"
    filepath = os.path.join("static", "images", filename)
    full_path = os.path.join(STATIC_IMAGES_DIR, filename)

    image.save(full_path)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """INSERT INTO targets
           (timestamp, lat, lon, brigade, image_path, object_type, confidence)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (timestamp, lat, lon, brigade, filepath, object_type, confidence),
    )
    conn.commit()
    conn.close()

    print(f"Нова ціль у базі: {object_type} ({confidence})")
    return "OK", 200


if __name__ == "__main__":
    init_db()
    print("Дашборд: http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, threaded=True)
