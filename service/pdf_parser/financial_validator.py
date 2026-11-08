from typing import List
from .models import FinancialPeriod


class FinancialValidator:
    @staticmethod
    def validate_period(period: FinancialPeriod) -> List[str]:
        warnings = []

        # 1. Assets = Liabilities + Equity
        if period.assets and period.equity:
            # Приближенная проверка (учитываем погрешности округления)
            estimated_liabilities = period.assets - period.equity
            # В идеале нужно проверять total_liabilities, если бы мы его извлекали
            if estimated_liabilities < 0:
                warnings.append(f"Год {period.year}: Капитал превышает активы, возможна ошибка извлечения.")

        # 2. Current assets <= Total assets
        if period.current_assets and period.assets:
            if period.current_assets > period.assets:
                warnings.append(f"Год {period.year}: Оборотные активы больше общих активов.")

        # 3. Cash <= Total assets
        if period.cash and period.assets:
            if period.cash > period.assets:
                warnings.append(f"Год {period.year}: Денежные средства больше общих активов.")

        # 4. Проверка EBITDA vs Operating Profit
        if period.ebitda is None and period.operating_profit is not None:
            warnings.append(f"Год {period.year}: Найдена операционная прибыль, но не найдена EBITDA.")

        return warnings