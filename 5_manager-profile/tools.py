import os
import json
import re
from typing import List, Dict, Any, Optional
from ddgs import DDGS

def sanitize_folder_name(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()

def get_person_details_from_company(full_name: str, ticker: str, exchange: str):
    """
    Finds a person in a specific company's Management.json and returns their details.
    """
    companies_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Companies"))
    management_path = os.path.join(companies_dir, f"{ticker}.{exchange}", "Management.json")
    
    if not os.path.exists(management_path):
        return None
        
    try:
        with open(management_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        all_people = data.get("executives", []) + data.get("board_of_directors", [])
        for person in all_people:
            if person.get("name") == full_name:
                return person
    except Exception:
        pass
    return None

def populate_base_profile(person_summary: Dict[str, Any], managers_dir: str):
    """
    Deterministically populates the base Profile.json using local data.
    Skips if the file already exists.
    """
    full_name = person_summary["name"]
    first_name = person_summary["first_name"]
    last_name = person_summary["last_name"]
    
    folder_name = sanitize_folder_name(f"{first_name} {last_name}".strip()) or sanitize_folder_name(full_name)
    manager_path = os.path.join(managers_dir, folder_name)
    os.makedirs(manager_path, exist_ok=True)
    
    profile_path = os.path.join(manager_path, "Profile.json")
    
    if os.path.exists(profile_path):
        return profile_path
    
    # Initialize profile
    profile = {
        "name": full_name,
        "first_name": first_name,
        "last_name": last_name,
        "age": None,
        "age_year": None,
        "background": None,
        "picture_url": None,
        "commpanies": [],
        "investment_theses": person_summary.get("investment_theses", []),
        "socials": [],
        "committees": set(),
        "enrichment_status": "pending"
    }
    
    # Populate company specific details and biographical info
    for comp_brief in person_summary.get("commpanies", []):
        ticker = comp_brief["ticker"]
        exchange = comp_brief["exchange"]
        
        details = get_person_details_from_company(full_name, ticker, exchange)
        
        company_entry = {
            "name": comp_brief["name"],
            "ticker": ticker,
            "exchange": exchange,
            "title_or_role": comp_brief["role"],
            "start_date": None,
            "end_date": None
        }
        
        if details:
            if profile["age"] is None: profile["age"] = details.get("age")
            if profile["age_year"] is None: profile["age_year"] = details.get("age_year")
            if profile["background"] is None: profile["background"] = details.get("background")
            
            for comm in details.get("committees", []):
                profile["committees"].add(comm)
            
            tenure = details.get("tenure_dates", [])
            for t in tenure:
                if t.get("end_date") is None:
                    company_entry["start_date"] = t.get("start_date")
                    company_entry["end_date"] = t.get("end_date")
                    break
        
        profile["commpanies"].append(company_entry)
        
    profile["committees"] = sorted(list(profile["committees"]))
    
    with open(profile_path, 'w', encoding='utf-8') as f:
        json.dump(profile, f, indent=2)
        
    return profile_path

def search_social_media(person_name: str, affiliations: List[str]) -> List[Dict[str, str]]:
    """
    Searches for social media profiles (LinkedIn, X/Twitter, etc.) for a person.
    Provide affiliation names (company names) for better accuracy.
    """
    socials = []
    affiliation_str = " ".join(affiliations[:2])
    queries = [
        f'"{person_name}" {affiliation_str} LinkedIn',
        f'"{person_name}" LinkedIn',
        f'"{person_name}" {affiliation_str} Twitter X',
    ]
    
    try:
        with DDGS() as ddgs:
            for query in queries:
                results = list(ddgs.text(query, max_results=5))
                for res in results:
                    href = res.get('href', '').lower()
                    if 'linkedin.com/in/' in href:
                        socials.append({"name": "LinkedIn", "url": res['href']})
                    elif 'twitter.com/' in href or 'x.com/' in href:
                        if not any(x in href for x in ['/status/', '/search', '/i/']):
                            socials.append({"name": "X (Twitter)", "url": res['href']})
                
                # Deduplicate
                unique_socials = []
                seen_urls = set()
                for s in socials:
                    if s['url'] not in seen_urls:
                        unique_socials.append(s)
                        seen_urls.add(s['url'])
                socials = unique_socials
                if len(socials) >= 2: break
                
    except Exception:
        pass
        
    return socials

def search_profile_picture(person_name: str, affiliations: List[str]) -> Optional[str]:
    """
    Searches for a professional profile picture URL for a person.
    Provide affiliation names (company names) for better accuracy.
    """
    affiliation_str = " ".join(affiliations[:2])
    query = f'"{person_name}" {affiliation_str} professional headshot profile picture'
    try:
        with DDGS() as ddgs:
            results = list(ddgs.images(query, max_results=5))
            for res in results:
                img_url = res.get('image')
                if img_url and any(domain in img_url for domain in ['linkedin', 'licdn', 'bloomberg', 'reuters', 'wsj', 'forbes']):
                    return img_url
            if results:
                return results[0].get('image')
    except Exception:
        pass
    return None

def save_enrichment(profile_path: str, socials: List[Dict[str, str]], picture_url: Optional[str]) -> str:
    """
    Updates the Profile.json with socials and picture URL.
    """
    try:
        if not os.path.exists(profile_path):
            return "ERROR: Profile.json not found."
            
        with open(profile_path, 'r', encoding='utf-8') as f:
            profile = json.load(f)
            
        profile["socials"] = socials
        profile["picture_url"] = picture_url
        profile["enrichment_status"] = "success"
        
        with open(profile_path, 'w', encoding='utf-8') as f:
            json.dump(profile, f, indent=2)
            
        return f"SUCCESS: Enriched profile at {profile_path}"
    except Exception as e:
        return f"ERROR: Failed to save enrichment: {e}"
