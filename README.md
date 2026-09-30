# 🛡️ FinGuard AI

### AI-система анализа финансовых рисков для банков

**FinGuard AI** — интеллектуальная система для автоматизированного анализа финансовой отчётности компаний.

Система принимает **Excel и PDF-файлы**, обрабатывает финансовые показатели, выявляет аномалии, оценивает финансовое состояние компании, прогнозирует риск и рассчитывает рекомендуемый кредитный лимит.

---

## ✨ Возможности

| Модуль                        | Описание                                      |
| ----------------------------- | --------------------------------------------- |
| 📊 **Financial Health Score** | Оценка финансового состояния компании         |
| 🔍 **Anomaly Detection**      | Поиск аномальных финансовых операций          |
| 📈 **Risk Forecast**          | Прогноз изменения риска на 3 / 6 / 12 месяцев |
| 🤖 **Probability of Default** | Расчёт вероятности дефолта                    |
| 💳 **Credit Limit**           | Расчёт рекомендуемого кредитного лимита       |
| 📄 **PDF Parser**             | Извлечение финансовых данных из PDF           |
| 📑 **Excel Parser**           | Обработка финансовой отчётности из Excel      |
| 🌐 **Web Interface**          | Веб-интерфейс для загрузки документов         |

---

# 🏗️ Архитектура

Проект состоит из двух основных FastAPI-сервисов:

```text
                    ┌──────────────────────┐
                    │      Браузер         │
                    │   Web Interface      │
                    └──────────┬───────────┘
                               │
                               │ HTTP :8000
                               ▼
                    ┌──────────────────────┐
                    │    Controller API    │
                    │      FastAPI         │
                    │                      │
                    │ PDF / Excel upload   │
                    └──────────┬───────────┘
                               │
                               │ HTTP :8001
                               ▼
                    ┌──────────────────────┐
                    │      ML Server       │
                    │      FastAPI         │
                    │                      │
                    │ Financial Health     │
                    │ Anomaly Detection    │
                    │ Risk Forecast        │
                    │ PD Model             │
                    │ Risk Engine          │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │      ML Models       │
                    │      *.joblib        │
                    └──────────────────────┘
```

### Порты

| Сервис        |   Порт | Назначение                      |
| ------------- | -----: | ------------------------------- |
| 🌐 Controller | `8000` | Web-интерфейс и загрузка файлов |
| 🤖 ML Server  | `8001` | Анализ финансовых данных        |

---

# 📁 Структура проекта

```text
AIFinance/
│
├── controller/
│   ├── static/
│   │   └── index.html
│   │
│   ├── uploads/
│   ├── results/
│   │
│   └── MainController.py
│
├── service/
│   ├── PdfService.py
│   ├── ExcelService.py
│   └── financial_parser.py
│
├── ml/
│   ├── 1_generate_data.py
│   ├── 2_financial_health.py
│   ├── 3_anomaly_detection.py
│   ├── 4_forecast.py
│   ├── 5_pd_model.py
│   ├── 6_risk_engine.py
│   ├── 7_dashboard.py
│   ├── 8_train_and_save_models.py
│   └── 9_app.py
│
├── data/
│   └── *.csv
│
├── models/
│   ├── anomaly_model.joblib
│   └── pd_model.joblib
│
├── .venv/
├── requirements.txt
└── README.md
```

---

# 💻 Требования

Для запуска проекта на **Windows 11** необходимо:

* Windows 11
* Python **3.10–3.12**
* Git
* pip
* Internet connection для установки Python-пакетов

Рекомендуемая версия:

```text
Python 3.12
```

Проверить Python:

```powershell
python --version
```

Проверить Git:

```powershell
git --version
```

---

# 🚀 Установка

## 1. Клонирование проекта

Откройте **PowerShell** или **Command Prompt**:

```powershell
git clone <URL_REPOSITORY>
cd AIFinance
```

---

## 2. Создание виртуального окружения

```powershell
python -m venv .venv
```

После выполнения в проекте появится:

```text
.venv/
```

---

## 3. Активация виртуального окружения

### PowerShell

```powershell
.venv\Scripts\Activate.ps1
```

### CMD

```cmd
.venv\Scripts\activate
```

После активации терминал должен выглядеть примерно так:

```text
(.venv) C:\Users\User\AIFinance>
```

Если появляется `(.venv)`, окружение успешно активировано.

---

## ⚠️ Если PowerShell запрещает запуск скриптов

Если появляется ошибка:

```text
running scripts is disabled on this system
```

выполните:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

После этого снова:

```powershell
.venv\Scripts\Activate.ps1
```

---

# 📦 Установка зависимостей

Если в проекте уже есть `requirements.txt`:

```powershell
pip install -r requirements.txt
```

Или установите зависимости вручную:

```powershell
pip install pandas numpy scikit-learn python-dateutil joblib fastapi uvicorn python-multipart openpyxl requests httpx beautifulsoup4 lxml pillow pyyaml
```

### Основные библиотеки

| Библиотека         | Назначение                   |
| ------------------ | ---------------------------- |
| `pandas`           | Работа с финансовыми данными |
| `numpy`            | Математические операции      |
| `scikit-learn`     | Machine Learning             |
| `joblib`           | Сохранение ML-моделей        |
| `fastapi`          | REST API                     |
| `uvicorn`          | Запуск FastAPI               |
| `python-multipart` | Загрузка файлов              |
| `openpyxl`         | Работа с Excel               |
| `requests`         | HTTP-запросы                 |
| `httpx`            | HTTP/async запросы           |
| `beautifulsoup4`   | Парсинг HTML                 |
| `lxml`             | XML/HTML parsing             |
| `pillow`           | Работа с изображениями       |
| `pyyaml`           | Работа с YAML                |

---

# 🧠 Подготовка ML-моделей

Перед первым запуском необходимо подготовить данные и обучить модели.

Перейдите в папку `ml`:

```powershell
cd ml
```

Запустите pipeline:

```powershell
python 1_generate_data.py
python 2_financial_health.py
python 3_anomaly_detection.py
python 4_forecast.py
python 8_train_and_save_models.py
```

После выполнения должны появиться данные:

```text
data/
├── financial_data.csv
├── financial_health_scores.csv
├── anomalies.csv
└── forecasts.csv
```

и обученные модели:

```text
models/
├── anomaly_model.joblib
└── pd_model.joblib
```

### Что делает pipeline?

```text
1_generate_data.py
        ↓
Генерация финансовых данных
        ↓
2_financial_health.py
        ↓
Financial Health Score
        ↓
3_anomaly_detection.py
        ↓
Поиск аномалий
        ↓
4_forecast.py
        ↓
Прогноз риска
        ↓
8_train_and_save_models.py
        ↓
Обучение и сохранение ML-моделей
```

> 💡 Pipeline нужно выполнять заново только тогда, когда необходимо пересоздать данные или переобучить модели.

После завершения вернитесь в корневую директорию:

```powershell
cd ..
```

---

# 🤖 Запуск ML Server

ML-сервер отвечает непосредственно за AI-анализ.

Откройте **первый терминал**.

Перейдите в проект:

```powershell
cd AIFinance
```

Активируйте окружение:

```powershell
.venv\Scripts\Activate.ps1
```

Запустите сервер:

```powershell
cd ml
uvicorn 9_app:app --host 127.0.0.1 --port 8001 --reload
```

При успешном запуске появится:

```text
Uvicorn running on http://127.0.0.1:8001
```

ML API:

```text
http://127.0.0.1:8001
```

Swagger документация:

```text
http://127.0.0.1:8001/docs
```

---

# 🌐 Запуск Controller

Controller отвечает за:

* веб-интерфейс;
* загрузку Excel;
* загрузку PDF;
* взаимодействие с ML-сервером.

Откройте **второй терминал**.

Перейдите в проект:

```powershell
cd AIFinance
```

Активируйте окружение:

```powershell
.venv\Scripts\Activate.ps1
```

Запустите Controller:

```powershell
cd controller
uvicorn MainController:app --host 127.0.0.1 --port 8000 --reload
```

После запуска:

```text
Uvicorn running on http://127.0.0.1:8000
```

---

# 🖥️ Запуск приложения

После запуска обоих серверов:

### Web Interface

**http://127.0.0.1:8000**

### Controller API

**http://127.0.0.1:8000/docs**

### ML API

**http://127.0.0.1:8001/docs**

---

# 🔌 API

## Controller API

### `GET /`

Открывает веб-интерфейс.

---

### `POST /upload/excel`

Загрузка Excel-файла с финансовой отчётностью.

```text
POST http://127.0.0.1:8000/upload/excel
```

Controller получает Excel и передаёт финансовые данные ML-сервису.

---

### `POST /upload`

Загрузка PDF-файла.

```text
POST http://127.0.0.1:8000/upload
```

PDF обрабатывается через `PdfService`.

---

# 🤖 ML API

### `POST /analyze`

Основной endpoint AI-анализа.

```text
POST http://127.0.0.1:8001/analyze
```

Endpoint принимает финансовый файл и необходимые параметры анализа.

Проверить структуру запроса можно через:

```text
http://127.0.0.1:8001/docs
```

---

# 📊 Финансовый анализ

После загрузки финансовых данных система выполняет несколько этапов.

### 1️⃣ Financial Health

Рассчитываются финансовые показатели компании:

* прибыльность;
* долговая нагрузка;
* ликвидность;
* финансовая устойчивость;
* другие финансовые коэффициенты.

Результатом является:

```text
Financial Health Score
```

---

### 2️⃣ Anomaly Detection

Для поиска необычных транзакций используется:

```text
Isolation Forest
```

Модель помогает обнаруживать операции, которые отличаются от нормального поведения.

---

### 3️⃣ Risk Forecast

Система строит прогноз изменения финансового риска:

```text
3 месяца
6 месяцев
12 месяцев
```

---

### 4️⃣ Probability of Default

ML-модель рассчитывает:

```text
Probability of Default (PD)
```

то есть вероятность дефолта компании.

Используемая модель:

```text
Logistic Regression
```

---

### 5️⃣ Credit Limit

На основе полученных финансовых показателей и уровня риска рассчитывается рекомендуемый кредитный лимит.

---

# 📑 Формат Excel

Excel-файл должен содержать финансовые показатели компании.

Основные поля:

| Поле                  | Описание                    |
| --------------------- | --------------------------- |
| `year`                | Отчётный год                |
| `revenue`             | Выручка                     |
| `ebitda`              | EBITDA                      |
| `net_profit`          | Чистая прибыль              |
| `debt`                | Общий долг                  |
| `cash`                | Денежные средства           |
| `current_assets`      | Оборотные активы            |
| `current_liabilities` | Краткосрочные обязательства |
| `receivables`         | Дебиторская задолженность   |
| `payables`            | Кредиторская задолженность  |
| `equity`              | Собственный капитал         |
| `assets`              | Общие активы                |

Пример:

```text
year | revenue | ebitda | net_profit | debt | cash | equity | assets
2024 | 460000  | 55000  | 20000      | 250000 | 15000 | 100000 | 400000
```

---

# 🧪 Тестирование

## Проверка ML-сервера

После запуска ML Server откройте:

```text
http://127.0.0.1:8001/docs
```

Найдите:

```text
POST /analyze
```

и нажмите:

```text
Try it out
```

Swagger позволит выполнить тестовый запрос непосредственно из браузера.

---

# 🔎 Проверка Controller

После запуска Controller откройте:

```text
http://127.0.0.1:8000/docs
```

Должны быть доступны:

```text
GET  /
POST /upload
POST /upload/excel
```

---

# 🛠️ Troubleshooting

## ❌ `uvicorn is not recognized`

Убедитесь, что виртуальное окружение активировано:

```powershell
.venv\Scripts\Activate.ps1
```

Затем:

```powershell
pip install uvicorn
```

---

## ❌ `ModuleNotFoundError`

Проверьте окружение:

```powershell
where python
```

Оно должно указывать примерно на:

```text
AIFinance\.venv\Scripts\python.exe
```

Также можно установить зависимости:

```powershell
pip install -r requirements.txt
```

---

## ❌ `Port 8000 is already in use`

Проверьте процесс:

```powershell
netstat -ano | findstr :8000
```

Завершите процесс:

```powershell
taskkill /PID <PID> /F
```

Для ML:

```powershell
netstat -ano | findstr :8001
```

---

## ❌ `Port 8001 is already in use`

Можно использовать другой порт:

```powershell
uvicorn 9_app:app --host 127.0.0.1 --port 8002 --reload
```

Но тогда Controller должен обращаться к новому адресу:

```text
http://127.0.0.1:8002
```

---

## ❌ Модели не найдены

Повторно запустите:

```powershell
cd ml

python 1_generate_data.py
python 2_financial_health.py
python 3_anomaly_detection.py
python 4_forecast.py
python 8_train_and_save_models.py
```

Проверьте:

```text
models/
├── anomaly_model.joblib
└── pd_model.joblib
```

---

## ❌ ML возвращает `422 Unprocessable Entity`

Ошибка `422` обычно означает, что запрос не соответствует формату, который ожидает FastAPI.

Проверьте:

```text
http://127.0.0.1:8001/docs
```

Особенно внимательно проверьте:

* название поля `file`;
* тип `UploadFile`;
* `company_name`;
* `transactions_file`;
* `requested_limit`.

Для файлов необходимо использовать:

```text
multipart/form-data
```

а не обычный JSON.

---

# 📋 Requirements

Рекомендуется хранить зависимости проекта в:

```text
requirements.txt
```

Пример:

```text
pandas>=2.0.0
numpy>=1.24.0
scikit-learn>=1.3.0
joblib>=1.3.0
fastapi>=0.100.0
uvicorn>=0.23.0
python-multipart>=0.0.6
openpyxl>=3.1.0
requests>=2.31.0
httpx>=0.24.0
beautifulsoup4>=4.12.0
lxml>=4.9.0
pillow>=10.0.0
pyyaml>=6.0
python-dateutil>=2.8.0
```

Установка:

```powershell
pip install -r requirements.txt
```

---

# 🔄 Полный порядок запуска

Если нужно запустить проект с нуля:

### Terminal 1 — подготовка

```powershell
cd AIFinance

python -m venv .venv

.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### Terminal 1 — ML pipeline

```powershell
cd ml

python 1_generate_data.py
python 2_financial_health.py
python 3_anomaly_detection.py
python 4_forecast.py
python 8_train_and_save_models.py
```

### Terminal 1 — ML Server

```powershell
uvicorn 9_app:app --host 127.0.0.1 --port 8001 --reload
```

---

### Terminal 2 — Controller

Откройте новый PowerShell:

```powershell
cd AIFinance

.venv\Scripts\Activate.ps1

cd controller

uvicorn MainController:app --host 127.0.0.1 --port 8000 --reload
```

---

### 🌐 Открыть приложение

Перейдите в браузере:

```text
http://127.0.0.1:8000
```

---

# 🧭 Быстрый запуск

Если всё уже установлено и модели обучены:

### Terminal 1

```powershell
cd AIFinance
.venv\Scripts\Activate.ps1
cd ml
uvicorn 9_app:app --host 127.0.0.1 --port 8001 --reload
```

### Terminal 2

```powershell
cd AIFinance
.venv\Scripts\Activate.ps1
cd controller
uvicorn MainController:app --host 127.0.0.1 --port 8000 --reload
```

После этого:

**🌐 http://127.0.0.1:8000**

---

# 📌 Полезные адреса

| Адрес                        | Назначение            |
| ---------------------------- | --------------------- |
| `http://127.0.0.1:8000`      | 🌐 Web Interface      |
| `http://127.0.0.1:8000/docs` | 📚 Controller Swagger |
| `http://127.0.0.1:8001`      | 🤖 ML Server          |
| `http://127.0.0.1:8001/docs` | 📚 ML Swagger         |

---

# 🔐 Production

Текущая конфигурация предназначена прежде всего для локальной разработки.

Перед production-развёртыванием рекомендуется:

* отключить `--reload`;
* ограничить CORS;
* добавить authentication;
* добавить logging;
* настроить переменные окружения;
* не хранить секреты в исходном коде;
* настроить HTTPS;
* добавить валидацию загружаемых файлов;
* ограничить размер файлов;
* настроить production web server.

---

# 📜 License

MIT License

---

# 👥 Authors

**AIFinance Team**

---

<div align="center">

### 🛡️ FinGuard AI

**AI-powered financial risk analysis**

`FastAPI` · `Python` · `Pandas` · `Scikit-learn` · `Machine Learning`

</div>
