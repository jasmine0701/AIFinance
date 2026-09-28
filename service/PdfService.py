"""
Сервисный слой: сохранение PDF-файла на диск и вызов вашего парсера
(financial_parser.process_pdf) для извлечения финансовых показателей.
"""

import math
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import UploadFile, HTTPException

from service.financial_parser import process_pdf, save_to_excel

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "controller" / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True, parents=True)

RESULTS_DIR = Path(__file__).resolve().parent.parent / "controller" / "results"
RESULTS_DIR.mkdir(exist_ok=True, parents=True)

ALLOWED_CONTENT_TYPES = {"application/pdf"}
MAX_FILE_SIZE_MB = 100  # финотчёты могут быть увесистыми


def _sanitize_for_json(value: Any) -> Any:
    """
    process_pdf может вернуть float('nan') там, где показатель не найден
    (через pandas-совместимые операции). JSON не умеет сериализовать NaN,
    поэтому заменяем такие значения на None.
    """
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


class PdfService:

    @staticmethod
    def save_upload(file: UploadFile) -> Path:
        """Сохраняет загруженный файл на диск и возвращает путь к нему."""
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(status_code=400, detail="Файл должен быть в формате PDF")

        if not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Ожидается файл с расширением .pdf")

        unique_name = f"{uuid.uuid4().hex}_{file.filename}"
        saved_path = UPLOAD_DIR / unique_name

        try:
            with saved_path.open("wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        finally:
            file.file.close()

        size_mb = saved_path.stat().st_size / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB:
            saved_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=400,
                detail=f"Файл слишком большой ({size_mb:.1f} MB). Максимум {MAX_FILE_SIZE_MB} MB",
            )

        return saved_path

    @staticmethod
    def parse_financial_report(file_path: Path) -> Dict[str, Any]:
        """Вызывает ваш парсер и приводит результат к JSON-safe виду."""
        raw_result = process_pdf(file_path)
        return {key: _sanitize_for_json(val) for key, val in raw_result.items()}

    @classmethod
    def process_upload(cls, file: UploadFile) -> Dict[str, Any]:
        """Полный цикл: сохранить файл -> распарсить -> вернуть результат."""
        saved_path = cls.save_upload(file)

        try:
            result = cls.parse_financial_report(saved_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Ошибка при парсинге файла: {e}")

        size_mb = round(saved_path.stat().st_size / (1024 * 1024), 2)

        return {
            "original_filename": file.filename,
            "saved_as": saved_path.name,
            "size_mb": size_mb,
            "parsing_result": result,
        }

    @classmethod
    def process_upload_and_export_excel(cls, file: UploadFile) -> Path:
        """
        То же самое, но результат сразу сохраняется в Excel
        (использует ваш save_to_excel) и путь к файлу возвращается вызывающему.
        """
        saved_path = cls.save_upload(file)

        try:
            raw_result = process_pdf(saved_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Ошибка при парсинге файла: {e}")

        excel_path = RESULTS_DIR / f"{saved_path.stem}.xlsx"
        save_to_excel([raw_result], output_file=excel_path)

        return excel_path