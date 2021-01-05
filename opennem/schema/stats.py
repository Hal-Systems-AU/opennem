"""
Schemas for stats
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel
from pydantic.class_validators import validator
from xlrd.xldate import xldate_as_datetime

from opennem.core.normalizers import clean_float


class StatsSet(BaseModel):
    name: str
    source_url: str
    fetched_date: datetime


class AUCpiData(BaseModel):
    quarter_date: datetime
    cpi_value: float

    @validator("quarter_date", pre=True)
    def parse_quarter_date(cls, value) -> datetime:
        v = xldate_as_datetime(value, 0)

        if not v or not isinstance(v, datetime):
            raise ValueError("Invalid CPI quarter")

        return v

    @validator("cpi_value", pre=True)
    def parse_cpi_value(cls, value: Any) -> float:
        v = clean_float(value)

        if not v:
            raise ValueError("No CPI Value")

        return v
