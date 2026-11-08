FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-rus \
    tesseract-ocr-eng \
    poppler-utils \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем зависимости
COPY controller/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все файлы проекта в /app
COPY . .

# Запуск из /app/controller, где лежит MainController.py
WORKDIR /app/controller

CMD ["sh", "-c", "uvicorn MainController:app --host 0.0.0.0 --port ${PORT:-8000}"]