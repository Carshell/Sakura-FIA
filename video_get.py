import cv2

# Цифра 0 - це зазвичай вбудована вебкамера ноутбука.
# Цифра 1 (або 2) - це ваш підключений EWRF OTG приймач.
cap = cv2.VideoCapture(1)

# Якщо камера не відкрилася, пробуємо інший індекс
if not cap.isOpened():
    print("Не вдалося знайти OTG приймач. Пробую індекс 0...")
    cap = cv2.VideoCapture(0)

while True:
    # Читаємо кадр з відеопередавача
    ret, frame = cap.read()
    
    if not ret:
        print("Помилка отримання кадру")
        break

    # Показуємо кадр у вікні
    cv2.imshow('FPV Drone Camera', frame)

    # Натисніть 'q' на клавіатурі для виходу
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()