import os
import re
import math
import pdfplumber
import pandas as pd
import pytesseract
from pdf2image import convert_from_path
from typing import List, Dict

from img2table.document import PDF
from img2table.ocr import TesseractOCR

from .models import ParserResult, ParserMetadata, FinancialPeriod
from .metric_dictionary import FINANCIAL_METRICS
from .text_normalizer import normalize_number
from .context_analyzer import ContextAnalyzer
from .financial_validator import FinancialValidator


class IntelligentFinancialParser:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.metadata = ParserMetadata(
            filename=os.path.basename(filepath),
            pages_processed=0,
            extraction_method="CV + OCR + TextFallback",
            warnings=[]
        )
        self.extracted_data: Dict[int, FinancialPeriod] = {}
        self.company_name = "Unknown Company"

    def parse(self) -> ParserResult:
        print(f"\n{'=' * 15} СТАРТ ПАРСИНГА PDF (ГИБРИД) {'=' * 15}")

        # 1. Быстрый поиск имени компании
        self._detect_company_name_fast()

        # Узнаем количество страниц, чтобы ограничить сканирование первыми 15 страницами
        with pdfplumber.open(self.filepath) as pdf:
            total_pages = len(pdf.pages)
            pages_to_scan = min(15, total_pages)
            self.metadata.pages_processed = total_pages

        # 2. Инициализация img2table (Включаем 4 потока CPU для скорости)
        ocr = TesseractOCR(n_threads=4, lang="rus+eng")

        # Ограничиваем CV только первыми страницами (индексы от 0 до pages_to_scan-1)
        pdf_doc = PDF(src=self.filepath, pages=list(range(pages_to_scan)))

        print(f"Сканирование структуры таблиц (Computer Vision) — только первые {pages_to_scan} стр...")
        extracted_tables = pdf_doc.extract_tables(
            ocr=ocr,
            implicit_rows=True,
            borderless_tables=True,
            min_confidence=40
        )

        # 3. Постраничная гибридная обработка
        with pdfplumber.open(self.filepath) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                page_num = page_idx + 1

                # --- Шаг А: Обработка таблиц (только если они были найдены на первых страницах) ---
                if extracted_tables and page_idx in extracted_tables:
                    for table in extracted_tables[page_idx]:
                        self._process_dataframe(table.df, page_num)

                # --- Шаг Б: Быстрый текстовый парсинг для остальных страниц ---
                text = page.extract_text()

                # Если текста нет (чистый скан) - пропускаем страницу через OCR
                if not text or len(text) < 50:
                    try:
                        images = convert_from_path(self.filepath, first_page=page_num, last_page=page_num, dpi=150)
                        if images:
                            text = pytesseract.image_to_string(images[0], lang="rus+eng", config="--psm 6")
                    except Exception:
                        text = ""

                # Если текст найден - прогоняем через построчный поиск
                if text:
                    self._parse_text_lines(text)

        # 4. Вывод итогов и валидация
        print("\n--- ИТОГИ СБОРА ДАННЫХ ИЗ PDF ---")
        for year, period in self.extracted_data.items():
            print(
                f"Год {year}: Выручка={period.revenue}, Долг={period.debt}, Активы={period.assets}, Прибыль={period.net_profit}")
        print("=" * 48 + "\n")

        for year, period in self.extracted_data.items():
            warnings = FinancialValidator.validate_period(period)
            self.metadata.warnings.extend(warnings)

        periods_list = list(self.extracted_data.values())
        periods_list.sort(key=lambda x: x.year, reverse=True)

        return ParserResult(
            company=self.company_name,
            periods=periods_list,
            metadata=self.metadata
        )

    def _detect_company_name_fast(self):
        try:
            with pdfplumber.open(self.filepath) as pdf:
                if len(pdf.pages) > 0:
                    text = pdf.pages[0].extract_text()
                    if text:
                        for pattern in [r"(АО\s+[«\"].+?[»\"])", r"(ТОО\s+[«\"].+?[»\"])", r"(АО\s+[А-ЯA-ZЁ].{1,50})"]:
                            match = re.search(pattern, text[:2000], flags=re.IGNORECASE)
                            if match:
                                self.company_name = match.group(1).strip().replace('\n', ' ')
                                print(f"[ДЕТЕКТОР] Найдено название: {self.company_name}")
                                return
        except Exception:
            pass
        self.company_name = os.path.splitext(self.metadata.filename)[0]

    def _process_dataframe(self, df: pd.DataFrame, page_num: int):
        if df.empty or len(df.columns) < 2:
            return

        years_map = {}
        for row_idx in range(min(6, len(df))):
            for col_idx in range(len(df.columns)):
                cell_val = str(df.iloc[row_idx, col_idx]).strip()
                years = re.findall(r'\b(202[0-5])\b', cell_val)
                if years:
                    years_map[col_idx] = int(years[0])

        if not years_map:
            return

        for row_idx in range(len(df)):
            row_title = str(df.iloc[row_idx, 0]).replace('\n', ' ')

            for metric_key in FINANCIAL_METRICS.keys():
                if ContextAnalyzer.calculate_confidence(row_title.lower(), metric_key) > 0.75:
                    for col_idx, year in years_map.items():
                        if col_idx < len(df.columns):
                            cell_val = str(df.iloc[row_idx, col_idx]).lower()

                            # ЗАЩИТА ОТ ОШИБКИ 422 (NaN)
                            if 'nan' in cell_val:
                                continue

                            val = normalize_number(cell_val)

                            # Пропускаем нули, NaN и номера годов (случайно попавшие в значения)
                            if val != 0 and not math.isnan(val) and not (2000 <= val <= 2100):
                                self._update_period(year, metric_key, val)

    def _parse_text_lines(self, text: str):
        lines = text.split('\n')
        years = []
        for line in lines[:40]:
            found = re.findall(r'\b(202[0-5])\b', line)
            if found:
                seen = set()
                years = [int(y) for y in found if not (y in seen or seen.add(y))]
                break

        if not years:
            years = [2025, 2024, 2023]

        for line in lines:
            line_lower = line.lower()
            for metric_key in FINANCIAL_METRICS.keys():
                if ContextAnalyzer.calculate_confidence(line_lower, metric_key) > 0.75:

                    # 1. Сначала удаляем само название метрики из строки, чтобы оно не мешало
                    # Используем просто замену текста до первой цифры
                    match_text = re.search(r'\d', line)
                    if match_text:
                        clean_line = line[match_text.start():]
                    else:
                        continue

                    # 2. Ищем отдельные финансовые числа. Строго разделяем их.
                    # Регулярка теперь ищет: (опционально скобка) + цифры + (опционально точка/запятая) + (опционально скобка)
                    # Она больше не склеивает цифры через пробел!
                    raw_nums = re.findall(r'\(?\b\d+[\.,]?\d*\b\)?', clean_line)

                    nums = []
                    for n in raw_nums:
                        val = normalize_number(n)
                        # Защита: пропускаем нули, NaN, года (2000-2100)
                        # и номера примечаний (маленькие числа от 1 до 50, если они идут без дробей)
                        if val != 0 and not math.isnan(val) and not (2000 <= val <= 2100):
                            if 1 <= val <= 50 and float(val).is_integer() and len(nums) == 0:
                                continue  # Пропускаем номер примечания, если он стоит первым
                            nums.append(val)

                    for i, val in enumerate(nums):
                        if i < len(years):
                            self._update_period(years[i], metric_key, val)

    def _update_period(self, year: int, metric_key: str, value: float):
        if year not in self.extracted_data:
            self.extracted_data[year] = FinancialPeriod(year=year)

        period = self.extracted_data[year]
        if getattr(period, metric_key) is None:
            setattr(period, metric_key, value)