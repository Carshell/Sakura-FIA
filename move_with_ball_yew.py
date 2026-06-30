import cv2
import requests
import time
from ultralytics import YOLO

# 1. Налаштування
model = YOLO('yolov8n.pt')

cap = cv2.VideoCapture(1)
if not cap.isOpened():
    cap = cv2.VideoCapture(0)

ESP_CMD_URL = "http://192.168.4.1/cmd"
ESP_UPD_URL = "http://192.168.4.1/update"

is_armed = False

# ==========================================
# ⚙️ НАЛАШТУВАННЯ "ТУРЕЛІ"
# ==========================================
HOVER_THROTTLE = 1000  # Газ для зависання (ПІДБЕРІТЬ ВАШЕ ЗНАЧЕННЯ)
MAX_YAW = 150          # Наскільки сильно можна крутитися (до 1500 ± 150)
SMOOTHING = 0.15       # Плавність поворотів
MAX_LOST_FRAMES = 15   # Затримка перед зупинкою обертання, якщо м'яч зник
# ==========================================

ch_current = {'r': 1500, 'p': 1500, 't': 1000, 'y': 1500}
ch_target = {'r': 1500, 'p': 1500, 't': 1000, 'y': 1500}

lost_frames_count = 0
last_send_time = 0

print("Режим Турелі готовий! Натисніть 'A' для Арму, 'D' для Дізарму, 'Q' для виходу.")

while True:
    ret, frame = cap.read()
    if not ret: break

    height, width, _ = frame.shape
    center_x = width // 2

    # Шукаємо м'яч (клас 32)
    results = model.predict(frame, classes=[32], verbose=False)
    
    ball_found = False

    for result in results:
        if len(result.boxes) > 0:
            box = result.boxes[0]
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            
            obj_x = (x1 + x2) // 2
            
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.circle(frame, (obj_x, (y1 + y2) // 2), 5, (0, 0, 255), -1)
            
            ball_found = True
            lost_frames_count = 0

            # ---- ЛОГІКА ПОВОРОТУ (ТІЛЬКИ YAW) ----
            if is_armed:
                error_x = obj_x - center_x
                if abs(error_x) > 30: # Мертва зона по центру
                    ch_target['y'] = 1500 + int(error_x * 0.4)
                else:
                    ch_target['y'] = 1500
                
                # Всі інші осі жорстко зафіксовані
                ch_target['p'] = 1500
                ch_target['r'] = 1500
                ch_target['t'] = HOVER_THROTTLE
            break

    # Якщо м'яч втрачено з кадру
    if not ball_found:
        lost_frames_count += 1
        cv2.putText(frame, "TARGET LOST!", (center_x - 70, height // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        
        # Перестаємо крутитися і просто висимо на місці
        if lost_frames_count > MAX_LOST_FRAMES:
            ch_target['y'] = 1500
            ch_target['t'] = HOVER_THROTTLE if is_armed else 1000

    # ---- МАТЕМАТИКА ПЛАВНОСТІ ----
    ch_target['y'] = max(1500 - MAX_YAW, min(1500 + MAX_YAW, ch_target['y']))
    
    for key in ['r', 'p', 't', 'y']:
        ch_current[key] = int(ch_current[key] + SMOOTHING * (ch_target[key] - ch_current[key]))

    if not is_armed:
        ch_current['t'] = 1000

    # ---- ВІДПРАВКА КОМАНД НА ESP32 ----
    if time.time() - last_send_time > 0.05:
        try:
            req = f"{ESP_UPD_URL}?r={ch_current['r']}&p={ch_current['p']}&t={ch_current['t']}&y={ch_current['y']}"
            requests.get(req, timeout=0.05)
            last_send_time = time.time()
        except:
            pass

    # ---- ІНТЕРФЕЙС ----
    status_txt = "ARMED (HOVERING)" if is_armed else "DISARMED"
    color = (0, 0, 255) if is_armed else (0, 255, 0)
    cv2.putText(frame, f"STATUS: {status_txt} | YAW: {ch_current['y']}", 
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    cv2.imshow("Drone Yaw Tracker", frame)

    # ---- КЕРУВАННЯ КЛАВІАТУРОЮ ----
    key = cv2.waitKey(1) & 0xFF
    if key == ord('a') and not is_armed:
        try:
            requests.get(f"{ESP_CMD_URL}?arm=1", timeout=0.2)
            is_armed = True
            ch_current['t'] = HOVER_THROTTLE
            ch_target['t'] = HOVER_THROTTLE
        except: print("Помилка зв'язку з ESP")
    elif key == ord('d') and is_armed:
        try:
            requests.get(f"{ESP_CMD_URL}?arm=0", timeout=0.2)
            is_armed = False
        except: print("Помилка зв'язку з ESP")
    elif key == ord('q'):
        if is_armed: requests.get(f"{ESP_CMD_URL}?arm=0", timeout=0.2)
        break

cap.release()
cv2.destroyAllWindows()