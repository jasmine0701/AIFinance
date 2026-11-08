from __future__ import annotations

import os
import math
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List
import httpx

import pandas as pd
from fastapi import UploadFile, HTTPException

# ИЗМЕНЕНИЕ ДЛЯ RENDER: Динамическое получение URL ML-сервера
ML_SERVER_URL = os.getenv("ML_SERVER_URL", "http://127.0.0.1:8001") + "/analyze"

BASE_DIR = Path(__file__).resolve().parent.parent

UPLOAD_DIR = BASE_DIR / "controller" / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True, parents=True)

MAX_FILE_SIZE_MB = 20

COLUMN_MAPPING = {
    "Год": "year",
    "Выручка": "revenue",
    "EBITDA / операционная прибыль": "ebitda",
    "Чистая прибыль": "net_profit",
    "Долг": "debt",
    "Деньги": "cash",
    "Краткосрочные активы": "current_assets",
    "Краткосрочные обязательства": "current_liabilities",
    "Дебиторская задолженность": "receivables",
    "Кредиторская задолженность": "payables",
    "Капитал": "equity",
    "Активы всего": "assets",
}

REQUIRED_COLUMNS = list(COLUMN_MAPPING.keys())


def sanitize_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        if value.is_integer():
            return int(value)
    return value


def detect_unit(title: str) -> str | None:
    if not title:
        return None
    match = re.search(r"\((тыс\.\s*тенге|млн\s*тенге)\)", title, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def detect_company_name(sheet_name: str, title: str) -> str:
    match = re.match(r"(.+?)\s+20\d{2}-20\d{2}", sheet_name.strip())
    if match:
        return match.group(1).strip()
    if title:
        if "—" in title:
            return title.split("—")[0].strip()
        return title.strip()
    return sheet_name


def find_header_row(raw_df: pd.DataFrame) -> int:
    for index in range(min(10, len(raw_df))):
        values = [str(value).strip() for value in raw_df.iloc[index].tolist() if not pd.isna(value)]
        if "Год" in values:
            return index
    raise HTTPException(status_code=400, detail="Не удалось найти строку заголовков. Ожидается колонка 'Год'.")


def validate_columns(columns: List[str], sheet_name: str) -> None:
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in columns]
    if missing_columns:
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"Некорректная структура листа '{sheet_name}'",
                "missing_columns": missing_columns,
                "required_columns": REQUIRED_COLUMNS,
            },
        )


class ExcelService:
    @staticmethod
    def save_upload(file: UploadFile) -> Path:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Файл не имеет имени")
        extension = Path(file.filename).suffix.lower()
        if extension not in [".xlsx", ".xls"]: # Поддержка .xls
            raise HTTPException(status_code=400, detail="Ожидается Excel-файл формата .xlsx или .xls")
        unique_name = f"{uuid.uuid4().hex}_{Path(file.filename).name}"
        saved_path = UPLOAD_DIR / unique_name
        try:
            with saved_path.open("wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        finally:
            file.file.close()
        size_mb = saved_path.stat().st_size / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB:
            saved_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=f"Файл слишком большой ({size_mb:.1f} MB). Максимум {MAX_FILE_SIZE_MB} MB")
        return saved_path

    @staticmethod
    def process_sheet(excel_path: Path, sheet_name: str) -> Dict[str, Any]:
        engine = "openpyxl" if excel_path.suffix.lower() == ".xlsx" else "xlrd"
        raw_df = pd.read_excel(excel_path, sheet_name=sheet_name, header=None, engine=engine)
        if raw_df.empty:
            raise HTTPException(status_code=400, detail=f"Лист '{sheet_name}' пустой")

        title = ""
        first_value = raw_df.iloc[0, 0]
        if not pd.isna(first_value):
            title = str(first_value).strip()

        company = detect_company_name(sheet_name, title)
        unit = detect_unit(title)

        header_row = find_header_row(raw_df)
        df = pd.read_excel(excel_path, sheet_name=sheet_name, header=header_row, engine=engine)
        df = df.dropna(how="all")
        df.columns = [str(column).strip() for column in df.columns]

        validate_columns(list(df.columns), sheet_name)

        df = df[REQUIRED_COLUMNS].copy()

        for column in REQUIRED_COLUMNS:
            if column == "Год":
                continue
            df[column] = pd.to_numeric(df[column], errors="coerce")

        df["Год"] = pd.to_numeric(df["Год"], errors="coerce")
        df = df.dropna(subset=["Год"])

        records = []
        for _, row in df.iterrows():
            record = {
                "company": company,
                "year": sanitize_value(row["Год"]),
                "unit": unit,
            }
            for excel_column, ml_column in COLUMN_MAPPING.items():
                if excel_column == "Год":
                    continue
                record[ml_column] = sanitize_value(row[excel_column])
            records.append(record)

        return {
            "sheet": sheet_name,
            "company": company,
            "unit": unit,
            "records": records,
        }

    @classmethod
    async def process_upload(
            cls,
            file: UploadFile,
            requested_limit: float = 60_000_000,
    ) -> Dict[str, Any]:
        saved_path = cls.save_upload(file)
        try:
            engine = "openpyxl" if saved_path.suffix.lower() == ".xlsx" else "xlrd"
            excel_file = pd.ExcelFile(saved_path, engine=engine)
            sheet_names = excel_file.sheet_names

            if not sheet_names:
                raise HTTPException(status_code=400, detail="Excel-файл не содержит листов")

            all_records = []
            for sheet_name in sheet_names:
                result = cls.process_sheet(saved_path, sheet_name)
                all_records.extend(result["records"])

            if not all_records:
                raise HTTPException(status_code=400, detail="В файле не найдено ни одной строки с данными")

            by_company: Dict[str, list] = {}
            for record in all_records:
                by_company.setdefault(record["company"], []).append(record)

            results = []
            async with httpx.AsyncClient(timeout=120.0) as client:
                for company, records in by_company.items():
                    records.sort(key=lambda r: r["year"])
                    response = await client.post(
                        ML_SERVER_URL,
                        json={
                            "filename": file.filename,
                            "records_count": len(records),
                            "data": records,
                            "requested_limit": requested_limit,
                        },
                    )
                    if response.status_code != 200:
                        raise HTTPException(
                            status_code=502,
                            detail={
                                "message": f"Ошибка ML-сервера для '{company}'",
                                "status_code": response.status_code,
                                "response": response.text,
                            },
                        )
                    ml_result = response.json()
                    if "error" in ml_result:
                        raise HTTPException(status_code=422, detail=ml_result["error"])
                    results.append(ml_result)

            return {
                "filename": file.filename,
                "records_count": len(all_records),
                "results": results,
                "ml_result": results[0],
            }

        except HTTPException:
            raise
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"ML server недоступен ({ML_SERVER_URL}): {e}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Ошибка при обработке Excel: {e}")
        finally:
            saved_path.unlink(missing_ok=True)