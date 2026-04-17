import httpx
from typing import Dict, Any, Optional

class EdgarClient:
    BASE_URL = "https://data.sec.gov/submissions"
    
    def __init__(self, user_agent: str = "CompanyFeedAgent/1.0 (contact@example.com)"):
        self.headers = {"User-Agent": user_agent}

    def get_cik(self, ticker: str) -> Optional[str]:
        with httpx.Client(headers=self.headers) as client:
            response = client.get("https://www.sec.gov/files/company_tickers.json")
            if response.status_code == 200:
                data = response.json()
                for key, val in data.items():
                    if val['ticker'] == ticker.upper():
                        return str(val['cik_str']).zfill(10)
        return None

    def get_company_submissions(self, cik: str) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/CIK{cik}.json"
        with httpx.Client(headers=self.headers) as client:
            response = client.get(url)
            if response.status_code == 200:
                return response.json()
        return {}

def fetch_edgar_management_info(ticker: str) -> str:
    """Fetch recent filings list from EDGAR for US tickers."""
    client = EdgarClient()
    cik = client.get_cik(ticker)
    if not cik:
        return f"Could not find CIK for ticker {ticker}"
    
    submissions = client.get_company_submissions(cik)
    recent = submissions.get('recent', {})
    
    filings = []
    forms = recent.get('form', [])
    accession_numbers = recent.get('accessionNumber', [])
    filing_dates = recent.get('filingDate', [])
    primary_documents = recent.get('primaryDocument', [])
    
    for i in range(min(15, len(forms))):
        filings.append({
            "form": forms[i],
            "date": filing_dates[i],
            "accession": accession_numbers[i],
            "document": primary_documents[i]
        })
    
    summary = f"Company CIK: {cik}\nRecent Filings:\n"
    for f in filings:
        summary += f"- {f['form']} filed on {f['date']} (Accession: {f['accession']})\n"
    
    summary += "\nInstruction: Identify the latest 10-K or DEF 14A (Proxy Statement). "
    summary += f"Use google_search to find the 'Item 10' or 'Directors and Executive Officers' section for CIK {cik} in these specific filings."
    
    return summary
