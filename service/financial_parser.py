#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FINANCIAL REPORT PARSER
-----------------------
Парсит годовые финансовые отчеты компаний в PDF и извлекает:

1. Выручка
2. EBITDA / операционная прибыль
3. Чистая прибыль
4. Долг
5. Деньги
6. Краткосрочные активы
7. Краткосрочные обязательства
8. Дебиторская задолженность
9. Кредиторская задолженность
10. Капитал
11. Активы всего

Поддерживает:
- обычные PDF с текстовым слоем;
- сканированные PDF через OCR;
- несколько PDF в одной папке;
- русские и английские названия показателей;
- экспорт результата в Excel.

ВАЖНО:
Для OCR необходимо установить Tesseract OCR отдельно:
https://github.com/tesseract-ocr/tesseract

Python-библиотеки:
    pip install pdfplumber pytesseract pdf2image pandas openpyxl pillow

Для Windows также нужен Poppler:
https://github.com/oschwartz10612/poppler-windows/releases
"""

from __future__ import annotations

import re
import sys
import logging
from pathlib import Path
from typing import Optional, Dict, List, Tuple

import pandas as pd

# PDF text extraction
try:
    import pdfplumber
except ImportError:
    print("Установите pdfplumber: pip install pdfplumber")
    sys.exit(1)

# OCR
try:
    import pytesseract
    from pdf2image import convert_from_path
except ImportError:
    print(
        "Для OCR установите: pip install pytesseract pdf2image pillow"
    )
    sys.exit(1)


# ============================================================
# НАСТРОЙКИ
# ============================================================

INPUT_DIR = Path("pdf_reports")
OUTPUT_FILE = Path("financial_data.xlsx")

# Если Tesseract не находится автоматически, укажите путь.
# Например:
# TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSERACT_CMD = None

# Если Poppler не добавлен в PATH, укажите путь к папке bin.
# Например:
# POPPLER_PATH = r"C:\poppler\Library\bin"
POPPLER_PATH = None

# OCR запускается только если в PDF практически нет текста.
OCR_DPI = 250

# Чтобы не OCR-ить абсолютно все страницы большого отчета,
# сначала пытаемся найти страницы по ключевым словам.
OCR_ALL_PAGES_IF_NOT_FOUND = True

# Минимальное количество символов текста, чтобы считать,
# что PDF имеет нормальный текстовый слой.
MIN_TEXT_CHARS = 100

# Язык OCR.
# Важно: rus+eng требует установки русской модели Tesseract.
OCR_LANG = "rus+eng"

# Логи
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("financial_parser")


# ============================================================
# НАЗВАНИЯ ПОКАЗАТЕЛЕЙ
# ============================================================

METRIC_PATTERNS = {

    "Выручка": [
        r"выручк",
        r"доход[а-яё\s]*от\s+реализац",
        r"доход[а-яё\s]*по\s+договорам\s+с\s+клиент",
        r"revenue",
        r"sales",
        r"turnover",
        r"revenue\s+from\s+contracts\s+with\s+customers",
    ],

    "EBITDA / операционная прибыль": [
        r"ebitda",
        r"операционн[а-яё\s]*прибыл",
        r"operating\s+profit",
        r"profit\s+from\s+operations",
        r"operating\s+income",
    ],

    "Чистая прибыль": [
        r"чист[а-яё\s]*прибыл",
        r"прибыл[а-яё\s]+за\s+год",
        r"прибыл[а-яё\s]+за\s+период",
        r"net\s+profit",
        r"profit\s+for\s+the\s+year",
        r"profit\s+for\s+the\s+period",
        r"net\s+income",
    ],

    "Долг": [
        r"долг",
        r"займ",
        r"заем",
        r"заём",
        r"borrowings",
        r"loans\s+and\s+borrowings",
        r"interest[-\s]?bearing\s+debt",
        r"debt",
    ],

    "Деньги": [
        r"денежн[а-яё\s]+средств[а-яё\s]+и\s+их\s+эквивалент",
        r"денежн[а-яё\s]+средств",
        r"cash\s+and\s+cash\s+equivalents",
        r"cash\s+equivalents",
        r"cash",
    ],

    "Краткосрочные активы": [
        r"итого\s+оборотн[а-яё\s]+актив",
        r"всего\s+оборотн[а-яё\s]+актив",
        r"оборотн[а-яё\s]+актив",
        r"total\s+current\s+assets",
        r"current\s+assets",
    ],

    "Краткосрочные обязательства": [
        r"итого\s+краткосрочн[а-яё\s]+обязательств",
        r"всего\s+краткосрочн[а-яё\s]+обязательств",
        r"краткосрочн[а-яё\s]+обязательств",
        r"total\s+current\s+liabilities",
        r"current\s+liabilities",
    ],

    "Дебиторская задолженность": [
        r"торгов[а-яё\s]+дебиторск[а-яё\s]+задолж",
        r"дебиторск[а-яё\s]+задолж",
        r"дебиторск[а-яё\s]+долг",
        r"trade\s+receivables",
        r"accounts\s+receivable",
        r"receivables",
    ],

    "Кредиторская задолженность": [
        r"торгов[а-яё\s]+кредиторск[а-яё\s]+задолж",
        r"кредиторск[а-яё\s]+задолж",
        r"кредиторск[а-яё\s]+долг",
        r"trade\s+payables",
        r"accounts\s+payable",
        r"payables",
    ],

    "Капитал": [
        r"итого\s+капитал",
        r"всего\s+капитал",
        r"капитал\s+акционер",
        r"total\s+equity",
        r"equity",
    ],

    "Активы всего": [
        r"итого\s+актив",
        r"всего\s+актив",
        r"total\s+assets",
        r"assets\s+total",
    ],
}


# ============================================================
# НОРМАЛИЗАЦИЯ ТЕКСТА
# ============================================================

def normalize_text(text: str) -> str:
    """Приводит OCR/text к более удобному виду."""
    if not text:
        return ""

    text = text.replace("\u00a0", " ")
    text = text.replace("–", "-")
    text = text.replace("—", "-")
    text = text.replace("−", "-")

    # Частые OCR-ошибки
    replacements = {
        "Итого активы": "Итого активов",
        "Итого актив": "Итого активов",
        "Итого капитала": "Итого капитал",
        "Денежные средства и их эквиваленты": "Денежные средства и их эквиваленты",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    # Убираем слишком много пробелов
    text = re.sub(r"[ \t]+", " ", text)

    return text


# ============================================================
# ПОЛУЧЕНИЕ ТЕКСТА ИЗ PDF
# ============================================================

def extract_text_from_pdf(pdf_path: Path) -> Tuple[str, List[str]]:
    """
    Сначала пытается получить текст обычным способом.
    Возвращает:
        full_text
        page_texts
    """

    page_texts = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                try:
                    txt = page.extract_text() or ""
                except Exception:
                    txt = ""

                page_texts.append(txt)

    except Exception as e:
        logger.error(f"Ошибка чтения PDF {pdf_path.name}: {e}")
        return "", []

    full_text = "\n".join(page_texts)

    return full_text, page_texts


# ============================================================
# OCR
# ============================================================

def setup_tesseract():
    if TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


def ocr_page_image(image) -> str:
    """OCR одной страницы."""
    try:
        text = pytesseract.image_to_string(
            image,
            lang=OCR_LANG,
            config="--psm 6"
        )
        return text or ""
    except Exception as e:
        logger.warning(f"OCR error: {e}")
        return ""


def ocr_pdf(pdf_path: Path) -> List[str]:
    """OCR всего PDF."""
    logger.info(f"OCR: {pdf_path.name}")

    kwargs = {
        "dpi": OCR_DPI,
        "fmt": "jpeg",
    }

    if POPPLER_PATH:
        kwargs["poppler_path"] = POPPLER_PATH

    try:
        images = convert_from_path(str(pdf_path), **kwargs)
    except Exception as e:
        logger.error(
            f"Не удалось конвертировать PDF в изображения: {e}"
        )
        return []

    page_texts = []

    for i, image in enumerate(images, start=1):
        logger.info(
            f"OCR страница {i}/{len(images)}: {pdf_path.name}"
        )
        page_texts.append(ocr_page_image(image))

    return page_texts


# ============================================================
# ПОИСК ФИНАНСОВЫХ СТРАНИЦ
# ============================================================

FINANCIAL_KEYWORDS = [
    "выруч",
    "прибыл",
    "актив",
    "обязательств",
    "капитал",
    "revenue",
    "profit",
    "assets",
    "liabilities",
    "equity",
    "cash",
    "borrowings",
]


def find_relevant_pages(page_texts: List[str]) -> List[int]:
    """
    Возвращает номера страниц, на которых вероятнее всего
    находятся финансовые таблицы.
    """

    relevant = []

    for idx, text in enumerate(page_texts):
        low = text.lower()

        hits = sum(
            1 for keyword in FINANCIAL_KEYWORDS
            if keyword in low
        )

        if hits >= 2:
            relevant.append(idx)

    return relevant


# ============================================================
# ПОИСК ГОДА
# ============================================================

def detect_report_year(text: str, pdf_path: Path) -> Optional[int]:
    """
    Пытается определить год отчета.
    """

    patterns = [
        r"за\s+год[,\s]+закончивш[а-яё]+\s+\d{1,2}\s+\w+\s+(20\d{2})",
        r"год[,\s]+закончивш[а-яё]+\s+\d{1,2}\s+\w+\s+(20\d{2})",
        r"year\s+ended\s+\w+\s+\d{1,2}[,\s]+(20\d{2})",
        r"31\s+декабр[яь]\s+(20\d{2})",
        r"31\s+december\s+(20\d{2})",
        r"\b(20\d{2})\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                pass

    # Последняя попытка — имя файла
    match = re.search(r"(20\d{2})", pdf_path.name)
    if match:
        return int(match.group(1))

    return None


# ============================================================
# ОЧИСТКА ЧИСЕЛ
# ============================================================

def normalize_number_string(value: str) -> str:
    """
    Чистит строку с числом:
    254 749
    254,749
    254.749
    (14 106)
    -14 106
    """

    value = value.strip()

    # OCR иногда распознаёт похожие символы
    replacements = {
        "O": "0",
        "О": "0",
        "o": "0",
        "I": "1",
        "l": "1",
        "|": "1",
        "S": "5",
        "B": "8",
    }

    for old, new in replacements.items():
        value = value.replace(old, new)

    value = value.replace("\u00a0", " ")

    # Скобки в финансовой отчетности = отрицательное число
    negative = (
        value.startswith("(")
        and value.endswith(")")
    )

    value = value.replace("(", "")
    value = value.replace(")", "")

    # Убираем валютные обозначения и текст
    value = re.sub(
        r"[^0-9,\.\-\s]",
        "",
        value
    )

    value = value.strip()

    if not value:
        return ""

    # 254 749 -> 254749
    value = re.sub(r"\s+", "", value)

    if negative and not value.startswith("-"):
        value = "-" + value

    return value


def parse_number(value: str) -> Optional[float]:
    """
    Преобразует строку в число.
    """

    value = normalize_number_string(value)

    if not value:
        return None

    # Если есть и точка, и запятая:
    # считаем последний разделитель десятичным.
    if "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "")
            value = value.replace(",", ".")
        else:
            value = value.replace(",", "")

    elif "," in value:
        parts = value.split(",")

        # 254,749 обычно означает разделитель тысяч
        if len(parts[-1]) == 3:
            value = "".join(parts)
        else:
            value = value.replace(",", ".")

    elif "." in value:
        parts = value.split(".")

        if len(parts[-1]) == 3:
            value = "".join(parts)

    try:
        return float(value)
    except ValueError:
        return None


# ============================================================
# ПОИСК ЧИСЕЛ В СТРОКЕ
# ============================================================

NUMBER_PATTERN = re.compile(
    r"""
    (?<![\w])
    \(?\s*
    -?
    (?:\d[\d\s.,]*\d|\d)
    \s*\)?
    (?![\w])
    """,
    re.VERBOSE
)


def extract_numbers_from_line(line: str) -> List[float]:
    numbers = []

    for match in NUMBER_PATTERN.finditer(line):
        raw = match.group(0)

        # Не считать год отдельным финансовым значением
        cleaned = normalize_number_string(raw)

        if re.fullmatch(r"-?20\d{2}", cleaned):
            continue

        value = parse_number(raw)

        if value is not None:
            numbers.append(value)

    return numbers


# ============================================================
# ПОИСК СТРОКИ ПОКАЗАТЕЛЯ
# ============================================================

def metric_matches(line: str, metric: str) -> bool:
    low = line.lower()

    for pattern in METRIC_PATTERNS[metric]:
        try:
            if re.search(pattern, low, flags=re.IGNORECASE):
                return True
        except re.error:
            continue

    return False


def metric_priority(line: str, metric: str) -> int:
    """
    Чем выше score, тем более вероятно,
    что строка содержит нужный показатель.

    Это важно, например, для:
    - "Итого активы"
    - "Дебиторская задолженность"
    - "Кредиторская задолженность"
    """

    low = line.lower()
    score = 0

    if metric_matches(line, metric):
        score += 10

    if "итого" in low or "total" in low:
        score += 5

    # Предпочитаем строки с числами
    nums = extract_numbers_from_line(line)
    if nums:
        score += 10

    # Не брать строки с "за период", если ищем balance sheet,
    # кроме тех случаев, где это именно прибыль.
    if metric in {
        "Краткосрочные активы",
        "Краткосрочные обязательства",
        "Капитал",
        "Активы всего",
        "Деньги",
        "Дебиторская задолженность",
        "Кредиторская задолженность",
        "Долг",
    }:
        if "за год" in low or "за период" in low:
            score -= 3

    return score


# ============================================================
# ОПРЕДЕЛЕНИЕ КОЛОНКИ ГОДА
# ============================================================

def find_years_in_text(text: str) -> List[int]:
    years = []

    for match in re.findall(r"\b20\d{2}\b", text):
        year = int(match)

        if 2000 <= year <= 2100 and year not in years:
            years.append(year)

    return years


def select_value_for_year(
    line: str,
    report_year: Optional[int],
    all_years: List[int]
) -> Optional[float]:
    """
    В простых таблицах значения обычно идут:
        2025    2024
        254749  245000

    Если строка содержит два числа, выбираем первое для
    отчетного года.

    Это эвристика. Для сложных таблиц лучше использовать
    отдельный table parser.
    """

    numbers = extract_numbers_from_line(line)

    if not numbers:
        return None

    # Если есть только одно число — оно почти наверняка значение.
    if len(numbers) == 1:
        return numbers[0]

    # Убираем значения, которые выглядят как годы.
    filtered = [
        n for n in numbers
        if not (2000 <= n <= 2100)
    ]

    if filtered:
        numbers = filtered

    if not numbers:
        return None

    # Обычно первое число — текущий отчетный год.
    return numbers[0]


# ============================================================
# ИЗВЛЕЧЕНИЕ ПОКАЗАТЕЛЕЙ
# ============================================================

def extract_metric_from_pages(
    page_texts: List[str],
    metric: str,
    report_year: Optional[int]
) -> Tuple[Optional[float], Optional[str], Optional[int]]:

    candidates = []

    for page_idx, page_text in enumerate(page_texts):
        lines = page_text.splitlines()

        for line_idx, line in enumerate(lines):

            if not metric_matches(line, metric):
                continue

            nums = extract_numbers_from_line(line)

            # Если число находится на следующей строке,
            # OCR мог разделить название и значение.
            combined_line = line

            if not nums and line_idx + 1 < len(lines):
                combined_line += " " + lines[line_idx + 1]
                nums = extract_numbers_from_line(
                    lines[line_idx + 1]
                )

            if not nums:
                # Иногда значение находится через 2 строки
                if line_idx + 2 < len(lines):
                    combined_line += (
                        " " + lines[line_idx + 1]
                        + " " + lines[line_idx + 2]
                    )
                    nums = extract_numbers_from_line(
                        combined_line
                    )

            if not nums:
                continue

            score = metric_priority(line, metric)

            # Бонус, если есть "итого"
            low = line.lower()

            if metric in {
                "Активы всего",
                "Капитал",
                "Краткосрочные активы",
                "Краткосрочные обязательства",
            }:
                if "итого" in low or "total" in low:
                    score += 10

            candidates.append(
                (
                    score,
                    page_idx,
                    line,
                    nums
                )
            )

    if not candidates:
        return None, None, None

    # Лучший кандидат
    candidates.sort(
        key=lambda x: x[0],
        reverse=True
    )

    best_score, page_idx, line, nums = candidates[0]

    value = select_value_for_year(
        line,
        report_year,
        find_years_in_text(page_texts[page_idx])
    )

    return value, line.strip(), page_idx + 1


# ============================================================
# СПЕЦИАЛЬНАЯ ЛОГИКА ДЛЯ ДОЛГА
# ============================================================

def extract_debt(
    page_texts: List[str],
    report_year: Optional[int]
) -> Tuple[Optional[float], Optional[str], Optional[int]]:

    # Сначала пытаемся найти строку "итого займы",
    # "total borrowings" и аналогичные.
    patterns = [
        r"итого.*займ",
        r"всего.*займ",
        r"total.*borrowings",
        r"total.*loans",
        r"займ.*итого",
        r"borrowings.*total",
    ]

    candidates = []

    for page_idx, page_text in enumerate(page_texts):
        for line in page_text.splitlines():

            low = line.lower()

            if any(
                re.search(p, low)
                for p in patterns
            ):
                nums = extract_numbers_from_line(line)

                if nums:
                    candidates.append(
                        (
                            30,
                            page_idx,
                            line,
                            nums
                        )
                    )

    if candidates:
        candidates.sort(
            key=lambda x: x[0],
            reverse=True
        )

        _, page_idx, line, nums = candidates[0]

        return (
            select_value_for_year(line, report_year, []),
            line.strip(),
            page_idx + 1
        )

    # Иначе ищем borrowings / loans
    return extract_metric_from_pages(
        page_texts,
        "Долг",
        report_year
    )


# ============================================================
# СПЕЦИАЛЬНАЯ ЛОГИКА ДЛЯ EBITDA
# ============================================================

def extract_ebitda_or_operating_profit(
    page_texts: List[str],
    report_year: Optional[int]
) -> Tuple[Optional[float], Optional[str], Optional[int], str]:

    # Сначала EBITDA
    result = extract_metric_from_pages(
        page_texts,
        "EBITDA / операционная прибыль",
        report_year
    )

    value, source_line, page = result

    if value is not None and source_line:
        if "ebitda" in source_line.lower():
            return value, source_line, page, "reported EBITDA"

    # Если EBITDA не найдена — операционная прибыль
    for page_idx, page_text in enumerate(page_texts):
        for line in page_text.splitlines():

            low = line.lower()

            if (
                "операцион" in low
                and "прибыл" in low
            ) or (
                "operating profit" in low
            ) or (
                "operating income" in low
            ):
                nums = extract_numbers_from_line(line)

                if nums:
                    return (
                        select_value_for_year(
                            line,
                            report_year,
                            []
                        ),
                        line.strip(),
                        page_idx + 1,
                        "operating profit"
                    )

    return None, None, None, "not found"


# ============================================================
# НАЗВАНИЕ КОМПАНИИ
# ============================================================

def detect_company_name(
    text: str,
    pdf_path: Path
) -> str:

    # Частые варианты:
    # АО «Кселл»
    # АО "Kcell"
    # JSC Kcell

    patterns = [
        r"(АО\s+[«\"].+?[»\"])",
        r"(АО\s+[А-ЯA-ZЁ].{1,100})",
        r"(JSC\s+[A-Za-z].{1,100})",
        r"(LLP\s+[A-Za-zА-Яа-яЁё].{1,100})",
    ]

    first_part = text[:5000]

    for pattern in patterns:
        match = re.search(
            pattern,
            first_part,
            flags=re.IGNORECASE
        )

        if match:
            company = match.group(1).strip()

            # Убираем мусор после переноса
            company = company.split("\n")[0]

            return company[:150]

    # Если не нашли — имя файла
    return pdf_path.stem


# ============================================================
# ОБРАБОТКА ОДНОГО PDF
# ============================================================

def process_pdf(pdf_path: Path) -> Dict:

    logger.info("=" * 70)
    logger.info(f"Обработка: {pdf_path.name}")

    # 1. Обычный текст
    full_text, page_texts = extract_text_from_pdf(
        pdf_path
    )

    text_length = len(full_text.strip())

    logger.info(
        f"Текстовый слой: {text_length} символов"
    )

    # 2. Если текста практически нет — OCR
    if text_length < MIN_TEXT_CHARS:

        logger.info(
            "Текстовый слой отсутствует/недостаточен. "
            "Запускаем OCR."
        )

        page_texts = ocr_pdf(pdf_path)
        full_text = "\n".join(page_texts)

    else:
        # Даже если текст есть, можно оставить его.
        pass

    full_text = normalize_text(full_text)

    # 3. Компания и год
    company = detect_company_name(
        full_text,
        pdf_path
    )

    report_year = detect_report_year(
        full_text,
        pdf_path
    )

    logger.info(f"Компания: {company}")
    logger.info(f"Год: {report_year}")

    # 4. Результат
    result = {
        "Компания": company,
        "Год": report_year,
        "Файл": pdf_path.name,
    }

    # 5. EBITDA / Operating Profit
    (
        value,
        source_line,
        page,
        source_type
    ) = extract_ebitda_or_operating_profit(
        page_texts,
        report_year
    )

    result["EBITDA / операционная прибыль"] = value
    result["EBITDA source"] = source_type
    result["EBITDA source text"] = source_line
    result["EBITDA page"] = page

    # 6. Остальные показатели
    metrics = [
        "Выручка",
        "Чистая прибыль",
        "Деньги",
        "Краткосрочные активы",
        "Краткосрочные обязательства",
        "Дебиторская задолженность",
        "Кредиторская задолженность",
        "Капитал",
        "Активы всего",
    ]

    for metric in metrics:

        value, source_line, page = (
            extract_metric_from_pages(
                page_texts,
                metric,
                report_year
            )
        )

        result[metric] = value
        result[f"{metric} source"] = source_line
        result[f"{metric} page"] = page

    # 7. Долг отдельно
    value, source_line, page = extract_debt(
        page_texts,
        report_year
    )

    result["Долг"] = value
    result["Долг source"] = source_line
    result["Долг page"] = page

    return result


# ============================================================
# ПРОВЕРКА РЕЗУЛЬТАТА
# ============================================================

MAIN_COLUMNS = [
    "Компания",
    "Год",
    "Файл",
    "Выручка",
    "EBITDA / операционная прибыль",
    "Чистая прибыль",
    "Долг",
    "Деньги",
    "Краткосрочные активы",
    "Краткосрочные обязательства",
    "Дебиторская задолженность",
    "Кредиторская задолженность",
    "Капитал",
    "Активы всего",
]


def calculate_quality_score(row: pd.Series) -> int:

    score = 0

    for column in MAIN_COLUMNS[3:]:
        value = row.get(column)

        if pd.notna(value):
            score += 1

    return score


# ============================================================
# СОХРАНЕНИЕ В EXCEL
# ============================================================

def save_to_excel(results: List[Dict], output_file: Path = OUTPUT_FILE):

    df = pd.DataFrame(results)

    if df.empty:
        logger.warning("Нет данных для сохранения.")
        return

    # Сначала основные столбцы
    existing_main = [
        col for col in MAIN_COLUMNS
        if col in df.columns
    ]

    other_columns = [
        col for col in df.columns
        if col not in existing_main
    ]

    df = df[
        existing_main + other_columns
    ]

    # Качество парсинга
    df["Заполнено показателей"] = (
        df.apply(
            calculate_quality_score,
            axis=1
        )
    )

    # Сохраняем
    with pd.ExcelWriter(
        output_file,
        engine="openpyxl"
    ) as writer:

        df.to_excel(
            writer,
            sheet_name="Financial Data",
            index=False
        )

        # Отдельный лист с проблемами
        problems = []

        for _, row in df.iterrows():

            missing = []

            for metric in MAIN_COLUMNS[3:]:
                if pd.isna(row.get(metric)):
                    missing.append(metric)

            if missing:
                problems.append({
                    "Компания": row.get("Компания"),
                    "Год": row.get("Год"),
                    "Файл": row.get("Файл"),
                    "Не найдено": ", ".join(missing),
                })

        if problems:
            pd.DataFrame(problems).to_excel(
                writer,
                sheet_name="Needs Review",
                index=False
            )

    logger.info(
        f"Excel сохранен: {output_file.resolve()}"
    )


# ============================================================
# MAIN (запуск скрипта напрямую, батч-обработка папки)
# ============================================================

def main():

    setup_tesseract()

    if not INPUT_DIR.exists():
        INPUT_DIR.mkdir(
            parents=True,
            exist_ok=True
        )

        print(
            f"\nСоздана папка: {INPUT_DIR.resolve()}"
        )
        print(
            "Положите туда PDF-файлы и запустите скрипт снова."
        )
        return

    pdf_files = sorted(
        INPUT_DIR.glob("*.pdf")
    )

    if not pdf_files:
        print(
            f"\nВ папке {INPUT_DIR.resolve()} нет PDF."
        )
        return

    logger.info(
        f"Найдено PDF: {len(pdf_files)}"
    )

    results = []

    for pdf_path in pdf_files:

        try:
            result = process_pdf(pdf_path)
            results.append(result)

        except Exception as e:
            logger.exception(
                f"Ошибка при обработке {pdf_path.name}: {e}"
            )

            # Даже при ошибке создаём запись
            results.append({
                "Компания": pdf_path.stem,
                "Год": None,
                "Файл": pdf_path.name,
            })

    save_to_excel(results)

    print("\n" + "=" * 70)
    print("ГОТОВО")
    print("=" * 70)
    print(f"Обработано PDF: {len(pdf_files)}")
    print(f"Excel: {OUTPUT_FILE.resolve()}")
    print("=" * 70)


if __name__ == "__main__":
    main()