FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    wget \
    && rm -rf /var/lib/apt/lists/*

# CPU-only PyTorch (без CUDA, ~200 МБ замість ~2 ГБ)
RUN pip install --no-cache-dir \
    torch torchvision \
    --index-url https://download.pytorch.org/whl/cpu

COPY requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt \
    && pip install --no-cache-dir ultralytics --no-deps \
    && pip install --no-cache-dir \
        matplotlib pillow pyyaml psutil polars scipy ultralytics-thop

COPY video_get.py move_ball_hight_int.py dashboard_client.py esp_client.py detector.py camera_utils.py docker-entrypoint.sh yolov8n.pt best.pt ./
RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod +x docker-entrypoint.sh

ENV DASHBOARD_HOST=http://dashboard:5000
ENV HEADLESS=1
ENV CAMERA_INDEX=0
ENV VIDEO_SCRIPT=video_get.py

ENTRYPOINT ["./docker-entrypoint.sh"]
