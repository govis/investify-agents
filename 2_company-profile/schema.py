from typing import List, Optional
from pydantic import BaseModel, Field

class InvestmentThesisReference(BaseModel):
    thesis_name: str = Field(description="Thesis name")
    company_type: str = Field(description="Type as it relates to the investment thesis")


class CompanyProfileEnrichment(BaseModel):
    country_of_domicile: str = Field(description="Country of domicile")
    description: str = Field(description="One paragraph description (approx 50-100 words)")
    logo_url: Optional[str] = Field(None, description="URL to the official company logo")


class CompanyProfile(BaseModel):
    name: str = Field(description="Full legal name of the company")
    name_former: Optional[str] = Field(None, description="Former name of the company")
    name_clean: Optional[str] = Field(None, description="Text friendly name of the company")
    ticker: str = Field(description="Stock ticker symbol")
    exchange: str = Field(description="Stock exchange")
    website: Optional[str] = Field(None, description="Official company website")
    logo_url: Optional[str] = Field(None, description="URL to the company logo")
    logo_local: Optional[str] = Field(None, description="Local file name of the company logo")
    country_of_domicile: Optional[str] = Field(None, description="Country of domicile")
    description: Optional[str] = Field(None, description="One paragraph description")
    metals_and_minerals: Optional[List[str]] = Field(None, description="Up to 3 key metals/minerals for mining companies")
    investment_theses: List[InvestmentThesisReference] = Field(default_factory=list, description="Investment theses it relates to")
    origin: Optional[str] = Field(None, description="Source of the company data")
    enrichment: Optional[str] = Field(None, description="Enrichment status")

