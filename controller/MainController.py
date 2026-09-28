import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from service.PdfService import PdfService
from service.ExcelService import ExcelService

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Financial Reports Uploader")


@app.post("/upload/excel")
async def upload_financial_excel(file: UploadFile = File(...)):
    result = await ExcelService.process_upload(file)
    return JSONResponse(content=result)


@app.post("/upload")
async def upload_report(file: UploadFile = File(...)):
    result = PdfService.process_upload(file)
    return JSONResponse(content=result)


@app.get("/")
async def root():
    return FileResponse(BASE_DIR / "static" / "index.html")


# если появятся отдельные css/js/картинки
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")