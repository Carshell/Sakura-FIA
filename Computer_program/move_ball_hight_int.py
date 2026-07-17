import os
import cv2
import requests
import time
import threading
from ultralytics import YOLO

from dashboard_client import push_frame, start_dashboard_stream

DASHBOARD_HOST = os.environ.get("DASHBOARD_HOST", "http://127.0.0.1:5000")
CAMERA_INDEX = int(os.environ.get("CAMERA_INDEX", "1"))
HEADLESS = os.environ.get("HEADLESS", "0") == "1"

model = YOLO('yolov8n.pt')

cap = cv2.VideoCapture(CAMERA_INDEX)
if not cap.isOpened():
    cap = cv2.VideoCapture(0)

session = requests.Session()
ESP_CMD_URL = "http://192.168.4.1/cmd"
ESP_UPD_URL = "http://192.168.4.1/update"


#  НАЛАШТУВАННЯ ДЛЯ ДАШБОРДА (FLASK)
DASHBOARD_URL = f"{DASHBOARD_HOST}/api/upload"
last_photo_time = 0
PHOTO_INTERVAL = 5.0 # Скільки секунд чекати між відправкою нових фото однієї цілі
frame_counter = 0
FRAME_SKIP = 2  # Відправляти кожен N-й кадр (щоб не перевантажувати мережу)


is_armed = False


#  НАЛАШТУВАННЯ "ТУРЕЛІ" + ВИСОТИ
HOVER_THROTTLE = 1200       # Базовий газ для зависання
MAX_YAW = 150               # Наскільки сильно можна крутитися по осі Z (до 1500 ± 150)
MAX_THROTTLE_ADJUST = 100   # Максимальне відхилення газу від HOVER_THROTTLE для набору/зниження висоти
SMOOTHING = 0.15            # Плавність поворотів та зміни газу
MAX_LOST_FRAMES = 15        # Затримка перед зупинкою обертання та поверненням до базового газу
# ==========================================

ch_current = {'r': 1500, 'p': 1500, 't': 1000, 'y': 1500}
ch_target = {'r': 1500, 'p': 1500, 't': 1000, 'y': 1500}

lost_frames_count = 0

# Координати кнопок на екрані
BTN_ARM = (10, 50, 130, 90)
BTN_DISARM = (140, 50, 280, 90)


# НЕЗАЛЕЖНИЙ МЕРЕЖЕВИЙ ПОТІК

def wifi_transmitter():
    while True:
        try:
            req = f"{ESP_UPD_URL}?r={ch_current['r']}&p={ch_current['p']}&t={ch_current['t']}&y={ch_current['y']}"
            session.get(req, timeout=0.2)
        except:
            pass
        time.sleep(0.05) # Жорстко чекаємо 50 мс (20 Гц)

tx_thread = threading.Thread(target=wifi_transmitter, daemon=True)
tx_thread.start()

start_dashboard_stream()


# --- ОБРОБНИК КЛІКІВ МИШКИ ---
def mouse_click(event, x, y, flags, param):
    global is_armed
    
    if event == cv2.EVENT_LBUTTONDOWN:
        if BTN_ARM[0] <= x <= BTN_ARM[2] and BTN_ARM[1] <= y <= BTN_ARM[3]:
            if not is_armed:
                try:
                    session.get(f"{ESP_CMD_URL}?arm=1", timeout=0.2)
                    is_armed = True
                    ch_current['t'] = HOVER_THROTTLE
                    ch_target['t'] = HOVER_THROTTLE
                    print("Клік: Дрон ЗААРМЛЕНО")
                except: pass
                    
        elif BTN_DISARM[0] <= x <= BTN_DISARM[2] and BTN_DISARM[1] <= y <= BTN_DISARM[3]:
            if is_armed:
                try:
                    session.get(f"{ESP_CMD_URL}?arm=0", timeout=0.2)
                    is_armed = False
                    print("Клік: Дрон ДИЗАРМЛЕНО")
                except: pass

if not HEADLESS:
    cv2.namedWindow("Drone Vision Tracker")
    cv2.setMouseCallback("Drone Vision Tracker", mouse_click)

print(f"Program started (headless={HEADLESS}), dashboard={DASHBOARD_HOST}")

while True:
    ret, frame = cap.read()
    if not ret: break

    frame_counter += 1
    if frame_counter % FRAME_SKIP == 0:
        push_frame(frame)

    height, width, _ = frame.shape
    center_x = width // 2
    center_y = height // 2 # Визначаємо центр екрана по вертикалі

    results = model.predict(frame, classes=[32], verbose=False)
    
    ball_found = False

    for result in results:
        if len(result.boxes) > 0:
            box = result.boxes[0]
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            
            obj_x = (x1 + x2) // 2
            obj_y = (y1 + y2) // 2 # Координата м'яча по висоті
            
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.circle(frame, (obj_x, obj_y), 5, (0, 0, 255), -1)
            
            ball_found = True
            lost_frames_count = 0

            if is_armed:

                # Save data to dashbord

                current_time = time.time()
                if current_time - last_photo_time > PHOTO_INTERVAL:
                    last_photo_time = current_time
                    
                    # Копіюємо кадр, щоб малювання поверх нього не заважало наступним ітераціям
                    frame_to_send = frame.copy()
                    
                    # В реальному проекті тут беруться дані з MAVLink або GPS модуля дрона.
                    # Поки що ставимо статичні координати для демонстрації роботи дашборда.
                    lat_demo = '50.4501' 
                    lon_demo = '30.5234'
                    
                    # Запускаємо відправку у фоновому потоці, щоб не гальмувати відео і YOLO
                    def send_to_dashboard(img_frame, lat, lon):
                        try:
                            _, img_encoded = cv2.imencode('.jpg', img_frame)
                            files = {'image': ('target.jpg', img_encoded.tobytes(), 'image/jpeg')}
                            data = {
                                'lat': lat,
                                'lon': lon,
                                'brigade': 'Авто-розподіл'
                            }
                            requests.post(DASHBOARD_URL, files=files, data=data, timeout=1.0)
                            print("📸 Ціль виявлено! Фото відправлено на дашборд.")
                        except Exception as e:
                            print(f"⚠️ Не вдалося відправити на дашборд (перевірте чи запущений Flask): {e}")
                    
                    threading.Thread(target=send_to_dashboard, args=(frame_to_send, lat_demo, lon_demo), daemon=True).start()


                # ЛОГІКА КЕРУВАННЯ (YAW ТА THROTTLE)
                # 1. ЛОГІКА ПОВОРОТУ (YAW - Вліво/Вправо)
                error_x = obj_x - center_x
                if abs(error_x) > 30: 
                    ch_target['y'] = 1500 + int(error_x * 0.4)
                else:
                    ch_target['y'] = 1500
                
                # 2. ЛОГІКА ВИСОТИ (THROTTLE - Вгору/Вниз)
                # Інвертуємо логіку, бо Y=0 це верх екрана. Якщо error_y > 0, м'яч вище центру.
                error_y = center_y - obj_y 
                if abs(error_y) > 30: 
                    # Чим вище м'яч, тим більше газу додаємо. 0.4 - це коефіцієнт чутливості (PID)
                    throttle_calc = HOVER_THROTTLE + int(error_y * 0.4) 
                else:
                    throttle_calc = HOVER_THROTTLE
                
                # Обмежуємо газ, щоб не було різких стрибків
                ch_target['t'] = max(HOVER_THROTTLE - MAX_THROTTLE_ADJUST, 
                                     min(HOVER_THROTTLE + MAX_THROTTLE_ADJUST, throttle_calc))
                
                ch_target['p'] = 1500 # Тангаж (вперед/назад) поки що зафіксований
                ch_target['r'] = 1500
            break

    if not ball_found:
        lost_frames_count += 1
        cv2.putText(frame, "TARGET LOST!", (center_x - 70, center_y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        
        if lost_frames_count > MAX_LOST_FRAMES:
            ch_target['y'] = 1500
            ch_target['t'] = HOVER_THROTTLE if is_armed else 1000 # Повертаємось до стабільного зависання

    # Застосовуємо ліміти до Yaw
    ch_target['y'] = max(1500 - MAX_YAW, min(1500 + MAX_YAW, ch_target['y']))
    
    # Плавне згладжування для всіх каналів (EMA фільтр)
    for key in ['r', 'p', 't', 'y']:
        ch_current[key] = int(ch_current[key] + SMOOTHING * (ch_target[key] - ch_current[key]))

    if not is_armed:
        ch_current['t'] = 1000


    #  МАЛЮВАННЯ ІНТЕРФЕЙСУ (КНОПКИ ТА ТЕКСТ)

    
    status_txt = "ARMED" if is_armed else "DISARMED"
    color_status = (0, 0, 255) if is_armed else (0, 255, 0)
    # Додали вивід поточного газу (THR) на екран для відлагодження
    cv2.putText(frame, f"STATUS: {status_txt} | YAW: {ch_current['y']} | THR: {ch_current['t']}", 
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color_status, 2)

    arm_bg_color = (0, 100, 0) if is_armed else (0, 200, 0)
    cv2.rectangle(frame, (BTN_ARM[0], BTN_ARM[1]), (BTN_ARM[2], BTN_ARM[3]), arm_bg_color, -1)
    cv2.putText(frame, "ARM", (BTN_ARM[0] + 30, BTN_ARM[1] + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    disarm_bg_color = (0, 0, 200) if is_armed else (0, 0, 100)
    cv2.rectangle(frame, (BTN_DISARM[0], BTN_DISARM[1]), (BTN_DISARM[2], BTN_DISARM[3]), disarm_bg_color, -1)
    cv2.putText(frame, "DISARM", (BTN_DISARM[0] + 25, BTN_DISARM[1] + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    # Малюємо приціл (перехрестя) по центру екрана
    cv2.line(frame, (center_x - 20, center_y), (center_x + 20, center_y), (255, 255, 255), 1)
    cv2.line(frame, (center_x, center_y - 20), (center_x, center_y + 20), (255, 255, 255), 1)

    if not HEADLESS:
        cv2.imshow("Drone Vision Tracker", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            if is_armed: 
                try: session.get(f"{ESP_CMD_URL}?arm=0", timeout=0.2)
                except: pass
            break
    else:
        time.sleep(0.001)

cap.release()
if not HEADLESS:
    cv2.destroyAllWindows()