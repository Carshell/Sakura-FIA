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
# ⚙️ НАЛАШТУВАННЯ БЕЗПЕКИ ТА ПОЛЬОТУ
# ==========================================
HOVER_THROTTLE = 1350  # Базовий газ для утримання висоти (ПІДБЕРІТЬ ВАШЕ ЗНАЧЕННЯ!)
TARGET_AREA = 12000    # Ідеальний розмір м'яча (дистанція до нього)
MAX_PITCH = 100        # Максимальний нахил вперед/назад (до 1500 ± 100)
MAX_YAW = 150          # Максимальна швидкість повороту (до 1500 ± 150)
SMOOTHING = 0.15       # Коефіцієнт плавності рухів (0.01 - дуже повільно, 1.0 - миттєво)
MAX_LOST_FRAMES = 15   # Скільки кадрів пам'ятати м'яч, якщо він зник (15 кадрів ≈ 0.5 сек)
# ==========================================

# Поточні згладжені значення, які реально летять на дрон
ch_current = {'r': 1500, 'p': 1500, 't': 1000, 'y': 1500}
# Цільові значення, куди ШІ хоче направити дрон
ch_target = {'r': 1500, 'p': 1500, 't': 1000, 'y': 1500}

lost_frames_count = 0
last_send_time = 0

print("Готово! Натисніть 'A' для Арму, 'D' для Дізарму, 'Q' для виходу.")

while True:
    ret, frame = cap.read()
    if not ret: break

    height, width, _ = frame.shape
    center_x = width // 2
    center_y = height // 2

    # Шукаємо м'яч
    results = model.predict(frame, classes=[32], verbose=False)
    
    ball_found = False

    for result in results:
        if len(result.boxes) > 0:
            box = result.boxes[0] # Беремо найперший знайдений м'яч
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            
            obj_x = (x1 + x2) // 2
            obj_y = (y1 + y2) // 2
            obj_area = (x2 - x1) * (y2 - y1)

            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.circle(frame, (obj_x, obj_y), 5, (0, 0, 255), -1)
            
            ball_found = True
            lost_frames_count = 0 # Скидаємо лічильник втрати

            # ---- ОБЧИСЛЕННЯ ЦІЛЬОВИХ КОМАНД ----
            if is_armed:
                # 1. Поворот (Yaw) - цілимось по центру X
                error_x = obj_x - center_x
                if abs(error_x) > 30:
                    ch_target['y'] = 1500 + int(error_x * 0.4)
                else:
                    ch_target['y'] = 1500
                    
                # 2. Дистанція (Pitch) - підлітаємо або відлітаємо
                # Якщо об'єкт менший за TARGET_AREA - він далеко, летимо вперед
                area_error = TARGET_AREA - obj_area
                if abs(area_error) > 2000:
                    ch_target['p'] = 1500 + int((area_error / TARGET_AREA) * 150)
                else:
                    ch_target['p'] = 1500

                # 3. Висота (Throttle) - тримаємось на рівні м'яча по Y
                error_y = center_y - obj_y # Інвертуємо, бо Y росте вниз
                if abs(error_y) > 30:
                    ch_target['t'] = HOVER_THROTTLE + int(error_y * 0.5)
                else:
                    ch_target['t'] = HOVER_THROTTLE
            break

    # Якщо м'яч втрачено
    if not ball_found:
        lost_frames_count += 1
        cv2.putText(frame, "TARGET LOST!", (center_x - 70, center_y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        
        # Якщо немає занадто довго - переходимо в режим стабілізації (Hover)
        if lost_frames_count > MAX_LOST_FRAMES:
            ch_target['r'] = 1500
            ch_target['p'] = 1500
            ch_target['y'] = 1500
            ch_target['t'] = HOVER_THROTTLE if is_armed else 1000

    # ---- МАТЕМАТИКА ПЛАВНОСТІ (Exponential Moving Average) ----
    # Обрізаємо цільові значення лімітами безпеки
    ch_target['p'] = max(1500 - MAX_PITCH, min(1500 + MAX_PITCH, ch_target['p']))
    ch_target['y'] = max(1500 - MAX_YAW, min(1500 + MAX_YAW, ch_target['y']))
    
    # Плавне наближення поточних значень до цільових
    for key in ['r', 'p', 't', 'y']:
        ch_current[key] = int(ch_current[key] + SMOOTHING * (ch_target[key] - ch_current[key]))

    # Примусово глушимо мотор, якщо не заармлено
    if not is_armed:
        ch_current['t'] = 1000

    # ---- ВІДПРАВКА ДАНИХ (Не частіше 20 разів на секунду) ----
    if time.time() - last_send_time > 0.05:
        try:
            req = f"{ESP_UPD_URL}?r={ch_current['r']}&p={ch_current['p']}&t={ch_current['t']}&y={ch_current['y']}"
            requests.get(req, timeout=0.05)
            last_send_time = time.time()
        except:
            pass

    # ---- ІНТЕРФЕЙС ТА КНОПКИ ----
    status_txt = "ARMED" if is_armed else "DISARMED"
    color = (0, 0, 255) if is_armed else (0, 255, 0)
    cv2.putText(frame, f"STATUS: {status_txt} | THR: {ch_current['t']} P: {ch_current['p']} Y: {ch_current['y']}", 
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    cv2.imshow("Drone Auto-Flight", frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('a') and not is_armed:
        try:
            requests.get(f"{ESP_CMD_URL}?arm=1", timeout=0.2)
            is_armed = True
            ch_current['t'] = HOVER_THROTTLE # Одразу ставимо базовий газ
        except: print("Помилка ESP")
    elif key == ord('d') and is_armed:
        try:
            requests.get(f"{ESP_CMD_URL}?arm=0", timeout=0.2)
            is_armed = False
        except: print("Помилка ESP")
    elif key == ord('q'):
        if is_armed: requests.get(f"{ESP_CMD_URL}?arm=0", timeout=0.2)
        break

cap.release()
cv2.destroyAllWindows()