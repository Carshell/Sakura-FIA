FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY dashboard.py .

ENV DATA_DIR=/app/data
RUN mkdir -p /app/data/static/images

EXPOSE 5000

HEALTHCHECK --interval=5s --timeout=3s --retries=10 \
    CMD curl -f http://localhost:5000/api/targets || exit 1

CMD ["python", "dashboard.py"]
