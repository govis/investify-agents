from typing import List, Optional
from pydantic import BaseModel, Field

class ThesisReference(BaseModel):
    thesis_name: str = Field(description="Thesis name")
    company_type: str = Field(description="Type as it relates to the investment thesis")


class CompanyReference(BaseModel):
    name: str = Field(description="Company name")
    ticker: str = Field(description="Stock ticker symbol")
    exchange: str = Field(description="Stock exchange")
    theses: List[ThesisReference] = Field(description="Investment theses it relates to")


class CompanyList(BaseModel):
    companies: List[CompanyReference] = Field(description="List of companies identified in the theses")
