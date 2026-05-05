import os
import json
import re
from typing import List, Dict, Any, Optional
from ddgs import DDGS
import requests
import html

def sanitize_folder_name(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()

def download_image(url: str, manager_dir: str) -> Optional[str]:
    """
    Downloads an image from a URL and saves it as "Picture.ext" in the manager's directory.
    Returns the filename if successful, None otherwise.
    """
    try:
        # Unescape HTML entities (e.g. &amp;)
        url = html.unescape(url)
        
        # Use a common User-Agent to avoid being blocked
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, timeout=15, stream=True, headers=headers)
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '').lower()
            
            # Determine extension
            ext = 'jpg'
            if 'png' in content_type: ext = 'png'
            elif 'webp' in content_type: ext = 'webp'
            elif 'jpeg' in content_type or 'jpg' in content_type: ext = 'jpg'
            else:
                # Try to extract from URL if content-type is generic
                url_path = url.split('?')[0]
                if url_path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    ext = url_path.split('.')[-1].lower()
                    if ext == 'jpeg': ext = 'jpg'

            filename = f"Picture.{ext}"
            full_save_path = os.path.join(manager_dir, filename)
            
            with open(full_save_path, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            return filename
    except Exception as e:
        print(f"Failed to download image from {url}: {e}")
    return None

def scrape_linkedin_picture(url: str) -> Optional[str]:
    """
    Attempts to scrape the profile picture URL from a public LinkedIn profile using Open Graph metadata.
    """
    try:
        # High quality User-Agent to mimic a browser
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }
        # Use a longer timeout for LinkedIn
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            # Search for og:image meta tag
            match = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', response.text)
            if not match:
                # Fallback to name-based search if og:image is missing (e.g. name attribute instead of property)
                match = re.search(r'<meta[^>]+name="twitter:image"[^>]+content="([^"]+)"', response.text)
            
            if match:
                img_url = match.group(1)
                # Ignore default/placeholder images
                if any(p in img_url.lower() for p in ['ghost_person', 'default_profile', 'placeholder']):
                    return None
                return img_url
    except Exception as e:
        print(f"DEBUG: LinkedIn scrape failed for {url}: {e}")
    return None

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
        "picture_local": None,
        "companies": [],
        "investment_theses": person_summary.get("investment_theses", []),
        "socials": [],
        "committees": set(),
        "enrichment_status": "pending"
    }
    
    # Populate company specific details and biographical info
    for comp_brief in person_summary.get("companies", []):
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
        
        profile["companies"].append(company_entry)
        
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
                    snippet = res.get('body', '')
                    if 'linkedin.com/in/' in href:
                        socials.append({
                            "name": "LinkedIn", 
                            "url": res['href'],
                            "snippet": snippet
                        })
                    elif 'twitter.com/' in href or 'x.com/' in href:
                        if not any(x in href for x in ['/status/', '/search', '/i/']):
                            socials.append({
                                "name": "X (Twitter)", 
                                "url": res['href'],
                                "snippet": snippet
                            })
                
                # Deduplicate by URL
                unique_socials = []
                seen_urls = set()
                for s in socials:
                    if s['url'] not in seen_urls:
                        unique_socials.append(s)
                        seen_urls.add(s['url'])
                socials = unique_socials
                if len(socials) >= 4: break # Get a decent list for agent to pick from
                
    except Exception:
        pass
        
    return socials

def search_profile_picture(person_name: str, affiliations: List[str], linkedin_url: Optional[str] = None) -> Optional[str]:
    """
    Searches for a professional profile picture URL for a person.
    Prioritizes:
    1. Direct scraping of the provided LinkedIn URL.
    2. LinkedIn/Licdn images from search results (favoring JPEG over WebP).
    3. Other high-authority professional domains.
    """
    # 1. Try scraping the LinkedIn URL directly if provided
    if linkedin_url:
        scraped_url = scrape_linkedin_picture(linkedin_url)
        if scraped_url:
            return scraped_url

    affiliation_str = " ".join(affiliations[:2])
    queries = [
        f'site:licdn.com "{person_name}" {affiliation_str}',
        f'site:linkedin.com "{person_name}" {affiliation_str} profile picture',
        f'"{person_name}" {affiliation_str} professional headshot profile picture'
    ]

    try:
        with DDGS() as ddgs:
            found_licdn_urls = []
            all_other_urls = []

            for query in queries:
                results = list(ddgs.images(query, max_results=15))
                for res in results:
                    img_url = res.get('image', '')
                    if not img_url: continue
                    
                    # Ignore known placeholders
                    if any(p in img_url.lower() for p in ['ghost_person', 'default_profile', 'placeholder']):
                        continue

                    if any(domain in img_url for domain in ['licdn.com', 'linkedin.com']):
                        found_licdn_urls.append(img_url)
                    else:
                        all_other_urls.append(img_url)

            # 2. Prioritize LinkedIn/Licdn images, favoring non-webp (JPEG/PNG)
            if found_licdn_urls:
                jpegs = [u for u in found_licdn_urls if '.webp' not in u.lower()]
                return jpegs[0] if jpegs else found_licdn_urls[0]

            # 3. Fallback to other professional domains
            professional_domains = ['bloomberg.com', 'reuters.com', 'wsj.com', 'forbes.com', 'businessweek.com', 'fortune.com', 'adobe.com', 'apple.com']
            for img_url in all_other_urls:
                if any(domain in img_url for domain in professional_domains):
                    return img_url
                    
            if all_other_urls:
                return all_other_urls[0]
                
    except Exception:
        pass
    return None

def save_enrichment(profile_path: str, socials: List[Dict[str, str]], picture_url: Optional[str]) -> str:
    """
    Updates the Profile.json with socials and picture URL.
    Downloads a local copy of the picture if a LinkedIn profile is found.
    """
    try:
        if not os.path.exists(profile_path):
            return "ERROR: Profile.json not found."
            
        with open(profile_path, 'r', encoding='utf-8') as f:
            profile = json.load(f)
            
        profile["socials"] = socials
        profile["picture_url"] = picture_url
        profile["picture_local"] = None
        
        # Requirement: download picture if LinkedIn page is present
        has_linkedin = any(s.get("name") == "LinkedIn" for s in socials)
        if has_linkedin and picture_url:
            manager_dir = os.path.dirname(profile_path)
            local_filename = download_image(picture_url, manager_dir)
            if local_filename:
                profile["picture_local"] = local_filename
        
        profile["enrichment_status"] = "success"
        
        with open(profile_path, 'w', encoding='utf-8') as f:
            json.dump(profile, f, indent=2)
            
        return f"SUCCESS: Enriched profile at {profile_path}"
    except Exception as e:
        return f"ERROR: Failed to save enrichment: {e}"
