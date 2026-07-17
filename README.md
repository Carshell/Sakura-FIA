# FPV Drone — пошук ям

Дрон з FPV-камерою, комп'ютерним зором і керуванням через ESP32.

## Що вміє

- live-відео з відеоприймача на дашборд
- детекція ям (YOLOv8, модель `best.pt`)
- ARM / DISARM і місії Лінія / Квадрат через ESP
- захист HC-SR04: близька перешкода → DISARM

## Структура

```
Computer_program/   # відео, YOLO, клієнт ESP
Dashbord_program/   # Flask-дашборд
ESP_program/        # прошивка ESP32
docker-compose.yml
start.ps1
```

## Запуск (Windows)

1. Підключити USB-відеоприймач
2. Закрити програму «Камера» Windows
3. Підняти середовище і залежності:

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r Computer_program\requirements.txt
pip install -r Dashbord_program\requirements.txt
```

4. Запустити:

```powershell
.\start.ps1
```

Дашборд: http://127.0.0.1:5000

Для ARM підключіть ноут до Wi-Fi `Drone_Companion_AP` (пароль `123456789_FPV`).

## Калібровка польоту

У `Computer_program/esp_client.py`:

- `HOVER_THROTTLE` — газ для зависання
- `LINE_DURATION_S` / `SQUARE_*` — таймінги місій
- `PITCH_FORWARD`, `YAW_TURN` — нахил і поворот

## ESP32

Прошивка: `ESP_program/working_esp.ino`  
MSP на політний контролер (Betaflight), ANGLE на AUX2, ARM на AUX1.  
HC-SR04: TRIG=4, ECHO=5.
