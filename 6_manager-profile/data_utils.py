import os
import json
from typing import List, Dict, Any, Optional

def get_company_details(ticker: str, exchange: str) -> Dict[str, Any]:
    """
    Retrieves name_clean and website for a company from its Profile.json.
    """
    companies_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Companies"))
    profile_path = os.path.join(companies_dir, f"{ticker}.{exchange}", "Profile.json")
    
    if not os.path.exists(profile_path):
        return {"name_clean": None, "website": None}
        
    try:
        with open(profile_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return {
                "name_clean": data.get("name_clean"),
                "website": data.get("website")
            }
    except Exception:
        return {"name_clean": None, "website": None}

def get_manager_data(profile_path: str) -> Dict[str, Any]:
    """
    Reads the manager's Profile.json and enriches it with company details.
    """
    with open(profile_path, 'r', encoding='utf-8') as f:
        profile = json.load(f)
    
    enriched_companies = []
    for comp in profile.get("companies", []):
        details = get_company_details(comp["ticker"], comp["exchange"])
        comp["name_clean"] = details["name_clean"]
        comp["website"] = details["website"]
        enriched_companies.append(comp)
    
    profile["companies"] = enriched_companies
    return profile
