#  ball

import cv2
import requests
from ultralytics import YOLO

# 1. Ініціалізація нейромережі (YOLOv8 Nano)
model = YOLO('yolov8n.pt')

# 2. Підключення до камери дрона через EWRF OTG
cap = cv2.VideoCapture(1)

if not cap.isOpened():
    print("Не вдалося знайти OTG приймач. Пробую індекс 0...")
    cap = cv2.VideoCapture(0)

# IP адреса вашої ESP32
ESP_URL = "http://192.168.4.1/update"

# Базові значення стіків
channels = {'r': 1500, 'p': 1500, 't': 1000, 'y': 1500}

while True:
    ret, frame = cap.read()
    if not ret:
        print("Помилка отримання кадру")
        break

    height, width, _ = frame.shape
    center_x = width // 2  # Ідеальний центр кадру по X

    # 3. Розпізнавання об'єктів (шукаємо тільки клас 32 - sports ball)
    results = model.predict(frame, classes=[32], verbose=False)
    
    # Скидаємо Yaw в центр перед новою перевіркою
    channels['y'] = 1500

    for result in results:
        boxes = result.boxes
        for box in boxes:
            # Отримуємо координати рамки
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            
            # Знаходимо центр м'яча
            obj_x = (x1 + x2) // 2
            
            # Малюємо жовту рамку та червону точку в центрі
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
            cv2.circle(frame, (obj_x, (y1 + y2) // 2), 5, (0, 0, 255), -1)

            # 4. Логіка центрування (Пропорційний регулятор)
            error_x = obj_x - center_x
            
            # Мертва зона (щоб дрон не смикався)
            if abs(error_x) > 40: 
                # Якщо м'яч правіше, крутимо дрон вправо
                yaw_val = 1500 + int(error_x * 0.5)
                
                # Обмежуємо максимальну швидкість повороту
                channels['y'] = max(1300, min(1700, yaw_val))
            
            break # Беремо тільки перший знайдений м'яч

    # 5. Відправка команд на ESP32
    try:
        req = f"{ESP_URL}?r={channels['r']}&p={channels['p']}&t={channels['t']}&y={channels['y']}"
        requests.get(req, timeout=0.05)
    except requests.exceptions.RequestException:
        pass # Ігноруємо помилки мережі

    # Показуємо відео на екрані ноутбука
    cv2.imshow("Drone Ball Tracking", frame)

    # Вихід по кнопці 'q'
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()