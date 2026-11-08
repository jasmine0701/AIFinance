import os
import sys
import shutil
import pymupdf as fitz
import pandas as pd
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import List

sys.path.append(str(BASE_DIR))

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from service.PdfService import PdfService
from service.ExcelService import ExcelService
from service.pdf_parser.financial_parser import IntelligentFinancialParser

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Financial Reports Uploader")


@app.post("/upload/pdf")
async def upload_multiple_pdfs(
    files: List[UploadFile] = File(...),
    requested_limit: float = Form(60_000_000)
):
    uploads_dir = "uploads"
    os.makedirs(uploads_dir, exist_ok=True)

    if not files:
        return {"error": "Файлы не выбраны"}

    merged_pdf = fitz.Document()
    for file in files:
        if not file.filename.lower().endswith('.pdf'):
            return {"error": f"Файл {file.filename} не является PDF."}
        file_bytes = await file.read()
        temp_doc = fitz.Document(stream=file_bytes, filetype="pdf")
        merged_pdf.insert_pdf(temp_doc)
        temp_doc.close()

    merged_path = os.path.join(uploads_dir, "merged_financial_report.pdf")
    merged_pdf.save(merged_path)
    merged_pdf.close()

    parser = IntelligentFinancialParser(filepath=merged_path)
    result = parser.parse()

    if not result.periods:
        if os.path.exists(merged_path):
            os.remove(merged_path)
        return {"error": "Парсер не смог найти финансовые показатели в этих файлах."}

    records = []
    for p in result.periods:
        records.append({
            "Год": p.year,
            "Выручка": p.revenue or 0,
            "EBITDA / операционная прибыль": p.ebitda or 0,
            "Чистая прибыль": p.net_profit or 0,
            "Долг": p.debt or 0,
            "Деньги": p.cash or 0,
            "Краткосрочные активы": p.current_assets or 0,
            "Краткосрочные обязательства": p.current_liabilities or 0,
            "Дебиторская задолженность": p.receivables or 0,
            "Кредиторская задолженность": p.payables or 0,
            "Капитал": p.equity or 0,
            "Активы всего": p.assets or 0
        })
    df = pd.DataFrame(records)

    # Создаем временный Excel файл с правильным заголовком размерности
    with NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        with pd.ExcelWriter(tmp.name, engine='openpyxl') as writer:
            # Вставляем заголовок в первую ячейку, чтобы ExcelService понял, что это миллионы
            title_df = pd.DataFrame([["Финансовый отчет (тыс. тенге)"]])
            title_df.to_excel(writer, index=False, header=False, startrow=0)
            # Основные данные записываем со второй строки
            df.to_excel(writer, index=False, startrow=1)
        tmp_path = tmp.name

    with open(tmp_path, "rb") as f:
        mock_upload = UploadFile(filename="parsed_pdf.xlsx", file=f)
        ml_result = await ExcelService.process_upload(mock_upload, requested_limit)

    if os.path.exists(tmp_path):
        os.remove(tmp_path)
    if os.path.exists(merged_path):
        os.remove(merged_path)

    return ml_result


@app.post("/upload/excel")
async def upload_financial_excel(
    file: UploadFile = File(...),
    requested_limit: float = Form(60_000_000)
):
    result = await ExcelService.process_upload(file, requested_limit)
    return JSONResponse(content=result)


@app.post("/upload")
async def upload_report(file: UploadFile = File(...)):
    result = PdfService.process_upload(file)
    return JSONResponse(content=result)


@app.get("/")
async def root():
    return FileResponse(BASE_DIR / "static" / "index.html")

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")