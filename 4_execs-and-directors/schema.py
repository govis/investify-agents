from typing import List, Optional
from pydantic import BaseModel, Field

class PersonInfo(BaseModel):
    name: str = Field(description="Full name of the person")
    age: Optional[int] = Field(None, description="Approximate age of the person")
    age_year: Optional[int] = Field(None, description="Year the age was estimated")
    background: Optional[str] = Field(None, description="Brief professional background")

class ExecutiveTenureRecord(BaseModel):
    title: str = Field(description="Title or role of the executive (e.g., CEO, CFO)")
    start_date: Optional[str] = Field(None, description="The date the executive started in this role")
    end_date: Optional[str] = Field(None, description="The date the executive ended this role (null if current)")

class DirectorTenureRecord(BaseModel):
    role:  Optional[str] = Field(description="Role on the board (e.g., Chairman, Independent Director)")
    start_date: Optional[str] = Field(None, description="The date the member joined the board")
    end_date: Optional[str] = Field(None, description="The date the member left the board (null if current)")

class CompanyExecutive(PersonInfo):
    verified_current: Optional[bool] = Field(None, description="Whether executive is currently with the company")    
    tenure_dates: List[ExecutiveTenureRecord] = Field(None, description="Date(s)s and roles(s) of the employment with the company")    

class BoardMember(PersonInfo):
    verified_current: Optional[bool] = Field(None, description="Whether director is currently a member of the board")    
    tenure_dates: List[DirectorTenureRecord] = Field(None, description="Date(s)s and roles(s) of the director board membership")    
    committees: List[str] = Field(default_factory=list, description="Committees the director belongs to")

class SourceInformation(BaseModel):
    source_url: Optional[str] = Field(None, description="URL of the source document")
    source_description: Optional[str] = Field(None, description="Brief description of the source or document (e.g., 10-K, Management Proxy)")
    as_of_date: Optional[str] = Field(None, description="The date information was updated or reported")

class Management(BaseModel):
    executives: List[CompanyExecutive] = Field(description="List of C-suite and other key executives")
    board_of_directors: List[BoardMember] = Field(description="List of board of directors members")
    sources: List[SourceInformation] = Field(description="List of source document(s)")
