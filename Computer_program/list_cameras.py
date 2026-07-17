"""Список камер. Запуск: python list_cameras.py"""
from camera_utils import CAMERA_NAME, list_cameras, list_dshow_device_names, resolve_camera_index

if __name__ == "__main__":
    names = list_dshow_device_names()
    if names:
        print("DirectShow:")
        for i, name in enumerate(names):
            tag = ""
            if CAMERA_NAME.lower() in name.lower():
                tag = "  <- FPV"
            elif "integrated" in name.lower():
                tag = "  <- webcam"
            print(f"  [{i}] {name}{tag}")

    idx = resolve_camera_index()
    print(f"\nАвтовибір: {idx} ({CAMERA_NAME})")

    for cam in list_cameras():
        print(f"  [{cam['index']}] {cam.get('name')} {cam['backend']} {cam['width']}x{cam['height']}")
