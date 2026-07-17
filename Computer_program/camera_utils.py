import os
import sys
import time

import cv2

# на Windows індекси камер плавають, тому шукаємо по імені
CAMERA_NAME = os.environ.get("CAMERA_NAME", "USB Video")
REJECT_NAMES = ["integrated camera", "ir camera"]
ALLOW_WEBCAM_FALLBACK = os.environ.get("ALLOW_WEBCAM_FALLBACK", "0") == "1"
MAX_CAMERA_INDEX = int(os.environ.get("MAX_CAMERA_INDEX", "5"))


def _backends():
    if sys.platform == "win32":
        return [("DSHOW", cv2.CAP_DSHOW), ("MSMF", cv2.CAP_MSMF)]
    return [("default", cv2.CAP_ANY)]


def _try_open(index, backend):
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        cap.release()
        return None, None

    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    ret, frame = cap.read()
    if ret and frame is not None:
        return cap, frame

    cap.release()
    return None, None


def list_dshow_device_names():
    if sys.platform != "win32":
        return []
    try:
        from pygrabber.dshow_graph import FilterGraph

        return list(FilterGraph().get_input_devices())
    except Exception as e:
        print(f"Не вдалося прочитати список камер: {e}")
        return []


def resolve_camera_index(preferred_index=None):
    names = list_dshow_device_names()
    if not names:
        return preferred_index

    print("Камери:")
    for i, name in enumerate(names):
        print(f"  [{i}] {name}")

    wanted = CAMERA_NAME.lower()
    for i, name in enumerate(names):
        if wanted in name.lower():
            print(f"Вибрано: [{i}] {name}")
            return i

    for i, name in enumerate(names):
        if any(r in name.lower() for r in REJECT_NAMES):
            continue
        print(f"Вибрано: [{i}] {name}")
        return i

    if ALLOW_WEBCAM_FALLBACK:
        print("Увага: беру вебкамеру (ALLOW_WEBCAM_FALLBACK=1)")
        return 0

    print(f"Відеоприймач '{CAMERA_NAME}' не знайдено")
    return None


def list_cameras(max_index=None):
    max_index = MAX_CAMERA_INDEX if max_index is None else max_index
    names = list_dshow_device_names()
    found = []

    for index in range(max_index + 1):
        for backend_name, backend in _backends():
            cap, frame = _try_open(index, backend)
            if cap is None:
                continue
            h, w = frame.shape[:2]
            found.append(
                {
                    "index": index,
                    "name": names[index] if index < len(names) else "?",
                    "backend": backend_name,
                    "width": w,
                    "height": h,
                }
            )
            cap.release()
            break

    return found


def open_camera(preferred_index=None):
    env_index = os.environ.get("CAMERA_INDEX")
    fallback = preferred_index
    if fallback is None and env_index:
        fallback = int(env_index)

    index = resolve_camera_index(fallback)
    if index is None:
        return None, None

    names = list_dshow_device_names()
    chosen = names[index] if index < len(names) else f"index {index}"

    if not ALLOW_WEBCAM_FALLBACK and any(r in chosen.lower() for r in REJECT_NAMES):
        print(f"Це вебкамера ноута ({chosen}), пропускаю")
        return None, None

    for backend_name, backend in _backends():
        cap, _ = _try_open(index, backend)
        if cap is None:
            continue
        print(f"Камера відкрита: [{index}] {chosen} ({backend_name})")
        return cap, index

    print(f"Не вдалося відкрити [{index}] {chosen}. Можливо зайнята іншою програмою.")
    return None, None


def reopen_camera(cap, preferred_index=None):
    if cap is not None:
        cap.release()
    time.sleep(0.5)
    return open_camera(preferred_index)
