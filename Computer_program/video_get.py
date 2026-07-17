import os
import threading
import time

import cv2

from camera_utils import open_camera, reopen_camera
from dashboard_client import push_frame, start_dashboard_stream, upload_target
from detector import ObjectDetector
from esp_client import start_esp_client

# якщо CAMERA_INDEX не задано — шукаємо USB Video за іменем
_raw_index = os.environ.get("CAMERA_INDEX")
CAMERA_INDEX = int(_raw_index) if _raw_index else None
HEADLESS = os.environ.get("HEADLESS", "0") == "1"

FRAME_SKIP = 2
DETECT_EVERY_N = 4
PHOTO_INTERVAL = 5.0
MAX_READ_FAILS = 30

cap, active_index = open_camera(CAMERA_INDEX)
if cap is None:
    print("Не вдалося відкрити відеоприймач (USB Video).")
    print("Закрийте програму 'Камера' Windows і спробуйте ще раз.")
    raise SystemExit(1)

latest_frame = None
frame_lock = threading.Lock()
running = True
read_fail_streak = 0

detector = ObjectDetector(conf=0.4)
frame_counter = 0
last_upload_time = {}
last_detections = []


def camera_reader():
    global cap, active_index, latest_frame, read_fail_streak, running

    while running:
        ret, frame = cap.read()

        if ret and frame is not None:
            with frame_lock:
                latest_frame = frame
            read_fail_streak = 0
        else:
            read_fail_streak += 1
            if read_fail_streak == 1:
                print("Помилка кадру, пробую відновити...")
            if read_fail_streak >= MAX_READ_FAILS:
                print("Перепідключення антени...")
                cap, active_index = reopen_camera(cap, CAMERA_INDEX)
                read_fail_streak = 0
                if cap is None:
                    print("Антену не відновлено, зупинка.")
                    running = False
                    break
            time.sleep(0.05)
            continue

        time.sleep(0.001)


reader_thread = threading.Thread(target=camera_reader, daemon=True)
reader_thread.start()

start_dashboard_stream()
start_esp_client()
print("Дашборд: http://127.0.0.1:5000")
print("Детекція: ями (best.pt)")
print("Локальне вікно: q — вихід")

while running:
    with frame_lock:
        frame = None if latest_frame is None else latest_frame.copy()

    if frame is None:
        time.sleep(0.01)
        continue

    frame_counter += 1
    display_frame = frame.copy()

    if frame_counter % DETECT_EVERY_N == 0:
        last_detections = detector.detect(frame)
        detector.draw(display_frame, last_detections)
    elif last_detections:
        detector.draw(display_frame, last_detections)

    now = time.time()
    for det in last_detections:
        obj = det["object_type"]
        if now - last_upload_time.get(obj, 0) < PHOTO_INTERVAL:
            continue
        last_upload_time[obj] = now
        upload_target(
            display_frame.copy(),
            object_type=obj,
            confidence=det["confidence"],
        )

    if frame_counter % FRAME_SKIP == 0:
        push_frame(display_frame)

    if not HEADLESS:
        cv2.imshow("FPV Drone Camera", display_frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            running = False
            break

running = False
cap.release()
if not HEADLESS:
    cv2.destroyAllWindows()
