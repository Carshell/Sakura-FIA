import os
import queue
import threading

import cv2
import requests

DASHBOARD_HOST = os.environ.get("DASHBOARD_HOST", "http://127.0.0.1:5000")
FRAME_URL = f"{DASHBOARD_HOST}/api/frame"
UPLOAD_URL = f"{DASHBOARD_HOST}/api/upload"

_frame_queue = queue.Queue(maxsize=1)
_session = requests.Session()
_upload_session = requests.Session()
_running = False
_started = False
_frames_sent = 0


def _sender_loop():
    global _frames_sent

    while _running:
        try:
            frame = _frame_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        try:
            _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            resp = _session.post(
                FRAME_URL,
                files={"image": ("frame.jpg", jpeg.tobytes(), "image/jpeg")},
                timeout=1.0,
            )
            if resp.status_code in (200, 204):
                _frames_sent += 1
                if _frames_sent == 1:
                    print(f"Відео підключено до дашборду: {DASHBOARD_HOST}")
                elif _frames_sent % 100 == 0:
                    print(f"Надіслано кадрів: {_frames_sent}")
        except Exception as e:
            if _frames_sent == 0:
                print(f"Не вдалося надіслати кадр: {e}")


def start_dashboard_stream():
    global _running, _started
    if _started:
        return
    _started = True
    _running = True
    threading.Thread(target=_sender_loop, daemon=True, name="dashboard-stream").start()
    print(f"Стрім на дашборд: {FRAME_URL}")


def push_frame(frame):
    start_dashboard_stream()
    try:
        _frame_queue.put_nowait(frame.copy())
    except queue.Full:
        try:
            _frame_queue.get_nowait()
        except queue.Empty:
            pass
        _frame_queue.put_nowait(frame.copy())


def upload_target(frame, object_type, lat="50.4501", lon="30.5234", confidence=0.0):
    try:
        _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        files = {"image": ("target.jpg", jpeg.tobytes(), "image/jpeg")}
        data = {
            "lat": lat,
            "lon": lon,
            "brigade": "Авто-розподіл",
            "object_type": object_type,
            "confidence": f"{confidence:.0%}",
        }
        resp = _upload_session.post(UPLOAD_URL, files=files, data=data, timeout=2.0)
        if resp.status_code == 200:
            print(f"Збережено в базу: {object_type} ({confidence:.0%})")
            return True
    except Exception as e:
        print(f"Не вдалося зберегти {object_type}: {e}")
    return False
