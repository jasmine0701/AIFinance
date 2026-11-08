from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any

class ExtractedMetric(BaseModel):
    value: float
    year: int
    confidence: float
    matched_alias: str
    source_page: int
    extraction_method: str = "table"

class FinancialPeriod(BaseModel):
    year: int
    revenue: Optional[float] = None
    ebitda: Optional[float] = None
    operating_profit: Optional[float] = None
    net_profit: Optional[float] = None
    debt: Optional[float] = None
    cash: Optional[float] = None
    current_assets: Optional[float] = None
    current_liabilities: Optional[float] = None
    receivables: Optional[float] = None
    payables: Optional[float] = None
    equity: Optional[float] = None
    assets: Optional[float] = None

class ParserMetadata(BaseModel):
    filename: str
    pages_processed: int
    extraction_method: str
    warnings: List[str] = []

class ParserResult(BaseModel):
    company: Optional[str] = "Unknown"
    currency: Optional[str] = "KZT"
    unit: Optional[str] = "thousand"
    periods: List[FinancialPeriod] = []
    metadata: ParserMetadata