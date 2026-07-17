import cv2
from ultralytics import YOLO

# 1. Завантажуємо твою натреновану модель
model = YOLO('C:/Users/Loq/Documents/cybercec/koz/drone/video_from_drone/Computer_program/best.pt')

# 2. Вмикаємо веб-камеру (0 або 1)
cap = cv2.VideoCapture(0)

print("Камера запущена. Покажи в об'єктив фото ями (наприклад, з екрана телефону).")
print("Для виходу натисни клавішу 'q'.")

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # 3. Відправляємо кадр у нейромережу
    results = model.predict(frame, conf=0.4) # conf=0.4 показує тільки ті об'єкти, в яких модель впевнена на 40%+

    # 4. Автоматично малюємо рамки на кадрі
    annotated_frame = results[0].plot()

    # 5. Показуємо результат на екрані
    cv2.imshow("Pothole Detection Test", annotated_frame)

    # Вихід на клавішу 'q'
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()