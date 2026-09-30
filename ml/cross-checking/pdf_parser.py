"""
FinGuard AI — простой встроенный парсер PDF-отчётности.

ЧЕСТНОЕ ОГРАНИЧЕНИЕ: это НЕ полноценный ИИ-парсер, а поиск по ключевым словам
(эвристика по регулярным выражениям). Он находит строку, где встречается
нужное ключевое слово (например "Выручка"), и вытаскивает из неё первое число.
Работает надёжно для отчётов, где показатель назван словами похожими на
KEYWORDS ниже (стандартная терминология МСФО-отчётности РК). Если в чьём-то
отчёте формулировки сильно другие — конкретное поле может не найтись,
тогда API вернёт понятную ошибку с указанием, каких полей не хватает.

Если позже в команде появится "настоящий" парсер (более умный, от партнёра
по команде) — этот файл просто не используется, его заменяет тот процесс.
"""

import re
import pdfplumber

# ключевые слова -> в каком порядке искать (первое найденное совпадение побеждает)
KEYWORDS = {
    "revenue": ["выручка", "доход от реализации", "доход от основной деятельности"],
    "ebitda": ["операционная прибыль", "прибыль от операционной деятельности", "ebitda"],
    "net_profit": ["чистая прибыль", "чистый доход за период", "итоговая прибыль"],
    "debt": ["займы", "кредиты банков", "заемные средства", "долгосрочные и краткосрочные займы"],
    "cash": ["денежные средства", "денежные средства и их эквиваленты"],
    "current_assets": ["краткосрочные активы", "оборотные активы", "текущие активы"],
    "current_liabilities": ["краткосрочные обязательства", "текущие обязательства"],
    "receivables": ["дебиторская задолженность"],
    "payables": ["кредиторская задолженность"],
    "equity": ["итого капитал", "собственный капитал", "капитал"],
    "assets": ["итого активы", "всего активы", "баланс"],
}

NUMBER_RE = re.compile(r"[-]?\d[\d\s]*[.,]?\d*")


def extract_number(line: str):
    """Достаёт первое число из строки, убирая пробелы-разделители тысяч."""
    match = NUMBER_RE.search(line)
    if not match:
        return None
    raw = match.group().replace(" ", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def parse_pdf_report(file_obj) -> dict:
    """Возвращает словарь {revenue: ..., ebitda: ..., ...}. Ненайденные поля = None."""
    with pdfplumber.open(file_obj) as pdf:
        full_text = "\n".join((page.extract_text() or "") for page in pdf.pages)

    lines = full_text.split("\n")
    result = {field: None for field in KEYWORDS}

    for field, keywords in KEYWORDS.items():
        for line in lines:
            line_lower = line.lower()
            if any(kw in line_lower for kw in keywords):
                num = extract_number(line)
                if num is not None:
                    result[field] = num
                    break  # нашли — переходим к следующему полю

    # EBITDA fallback: если не нашли явную EBITDA, а операционная прибыль
    # уже попала в тот же список ключевых слов — result["ebitda"] уже
    # содержит операционную прибыль благодаря списку KEYWORDS["ebitda"] выше.
    # Отдельно ничего делать не нужно — это уже встроено в порядок поиска.

    return result


if __name__ == "__main__":
    with open("test_report.pdf", "rb") as f:
        parsed = parse_pdf_report(f)
    for k, v in parsed.items():
        print(f"{k:22s} = {v}")
