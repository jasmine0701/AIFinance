from .metric_dictionary import FINANCIAL_METRICS, ANTI_DICTIONARY
import re


class ContextAnalyzer:
    @staticmethod
    def calculate_confidence(row_text: str, metric_key: str) -> float:
        row_text_lower = row_text.lower().strip()
        confidence = 0.0

        # Проверка на Anti-Dictionary (False Positives)
        if metric_key in ANTI_DICTIONARY:
            for anti_word in ANTI_DICTIONARY[metric_key]:
                if anti_word in row_text_lower:
                    return 0.1  # Очень низкий шанс

        # Точное совпадение с алиасами
        aliases = FINANCIAL_METRICS.get(metric_key, [])
        for alias in aliases:
            if alias == row_text_lower:
                return 0.98  # Идеальное совпадение
            if alias in row_text_lower:
                confidence = max(confidence, 0.85)

        # Если есть слово "Итого" или "Total" - это повышает уверенность для итоговых показателей
        if "total" in row_text_lower or "итого" in row_text_lower:
            if metric_key in ["assets", "equity", "current_assets", "current_liabilities"]:
                confidence = min(confidence + 0.1, 0.95)

        return confidence