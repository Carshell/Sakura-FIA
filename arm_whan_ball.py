import cv2
import requests
from ultralytics import YOLO

# 1. Ініціалізація нейромережі
model = YOLO('yolov8n.pt')

# 2. Підключення до OTG приймача (камери дрона)
cap = cv2.VideoCapture(1)
if not cap.isOpened():
    print("OTG приймач не знайдено, перемикання на веб-камеру...")
    cap = cv2.VideoCapture(0)

# URL твоєї ESP32 для команд Arm/Disarm
ESP_CMD_URL = "http://192.168.4.1/cmd"

# Змінна для відстеження поточного стану дрона (щоб не спамити по Wi-Fi)
is_armed = False

print("Система запущена. Очікування м'яча в кадрі...")

while True:
    ret, frame = cap.read()
    if not ret:
        print("Помилка отримання кадру")
        break

    # 3. Шукаємо м'яч (клас 32)
    results = model.predict(frame, classes=[32], verbose=False)
    
    ball_detected = False

    for result in results:
        # Якщо в кадрі є хоча б один об'єкт (м'яч)
        if len(result.boxes) > 0:
            ball_detected = True
            
            # Малюємо рамку для візуалізації
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
                cv2.putText(frame, "TARGET LOCKED", (x1, y1 - 10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            break

    # 4. Логіка відправки команд на ESP32
    if ball_detected and not is_armed:
        # М'яч з'явився -> відправляємо ARM
        try:
            requests.get(f"{ESP_CMD_URL}?arm=1", timeout=0.2)
            is_armed = True
            print("М'яч знайдено! Дрон ЗААРМЛЕНО.")
        except requests.exceptions.RequestException:
            print("Помилка зв'язку з ESP32!")
            
    elif not ball_detected and is_armed:
        # М'яч зник -> відправляємо DISARM
        try:
            requests.get(f"{ESP_CMD_URL}?arm=0", timeout=0.2)
            is_armed = False
            print("Ціль втрачено! Дрон ДИЗААРМЛЕНО.")
        except requests.exceptions.RequestException:
            print("Помилка зв'язку з ESP32!")

    # Відображення статусу на екрані
    status_text = "ARMED (MOTORS SPINNING)" if is_armed else "DISARMED (SAFE)"
    text_color = (0, 0, 255) if is_armed else (0, 255, 0)
    cv2.putText(frame, f"STATUS: {status_text}", (20, 40), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, text_color, 2)

    # 5. Вивід відео
    cv2.imshow("Auto-Arming Vision", frame)

    # Вихід по клавіші 'q'
    if cv2.waitKey(1) & 0xFF == ord('q'):
        # Гарантований DISARM при виході з програми
        if is_armed:
            try:
                requests.get(f"{ESP_CMD_URL}?arm=0", timeout=0.2)
                print("Примусовий Disarm при виході.")
            except:
                pass
        break

cap.release()
cv2.destroyAllWindows()