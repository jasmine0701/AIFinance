FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-rus \
    tesseract-ocr-eng \
    poppler-utils \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем файл зависимостей
COPY controller/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь репозиторий (controller, service и т.д.)
COPY controller .

# Переходим в папку controller для запуска
WORKDIR /app/controller

CMD ["sh", "-c", "uvicorn MainController:app --host 0.0.0.0 --port ${PORT:-8000}"]