import os
import requests
import time
import json
import re
import logging
import tempfile
from datetime import datetime
from typing import Optional, List
from ddgs import DDGS
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from urllib.parse import urljoin, urlparse
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(), override=True)

# Configuration: Words to always exclude
EXCLUDE_WORDS_RAW = os.getenv("EXCLUDE_WORDS", "inc,ltd,corp,plc,the,and,nv,sa,ag")
exclude_words = [w.strip().lower() for w in EXCLUDE_WORDS_RAW.split(",") if w.strip()]

# Configuration: Words to exclude conditionally
CONDITIONAL_EXCLUDE_WORDS_RAW = os.getenv("CONDITIONAL_EXCLUDE_WORDS", "limited,company,corporation,group,holdings,public,global,general,international,incorporated")
conditional_exclude_words = [w.strip().lower() for w in CONDITIONAL_EXCLUDE_WORDS_RAW.split(",") if w.strip()]

# Configuration: Search overrides for companieslogo.com
SEARCH_OVERRIDES_RAW = os.getenv("COMPANIESLOGO_SEARCH_OVERRIDES", "{}")
if SEARCH_OVERRIDES_RAW.strip().startswith("'") or SEARCH_OVERRIDES_RAW.strip().startswith('"'):
    SEARCH_OVERRIDES_RAW = SEARCH_OVERRIDES_RAW.strip()[1:-1]
try:
    search_overrides = json.loads(SEARCH_OVERRIDES_RAW)
except:
    search_overrides = {}

def get_local_logger(folder_path: str):
    """Creates a logger that writes to a file in the company folder."""
    os.makedirs(folder_path, exist_ok=True)
    log_file = os.path.join(folder_path, "logo_workflow.log")
    
    logger = logging.getLogger(folder_path)
    logger.setLevel(logging.INFO)
    
    # Avoid duplicate handlers if logger is reused
    if not logger.handlers:
        fh = logging.FileHandler(log_file, encoding='utf-8')
        fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(fh)
        logger.propagate = False
    
    return logger

def get_filtered_parts(name: str) -> List[str]:
    """Applies two-tier filtering: always exclude EXCLUDE_WORDS, 
    conditionally exclude CONDITIONAL_EXCLUDE_WORDS if 2+ other words remain."""
    # 1. Basic cleanup: remove parentheticals
    name = re.sub(r'\(.*?\)', '', name).strip()
    
    # 2. Normalize acronyms: "N.V." -> "NV", "A.G." -> "AG", "U.S.A." -> "USA"
    # This preserves them as single tokens and prevents them from being split into individual letters
    name = re.sub(r'\b(?:[a-zA-Z]\.)+[a-zA-Z]?\b', lambda m: m.group(0).replace('.', ''), name)

    # 3. Punctuation cleanup: replace dots, commas, and ampersands with spaces
    name = name.replace(',', ' ').replace('.', ' ').replace('&', ' ').strip()
    parts = [p.lower() for p in name.split() if p]
    
    # 4. Always exclude
    parts = [p for p in parts if p not in exclude_words]
    
    # 5. Conditionally exclude
    others = [p for p in parts if p not in conditional_exclude_words]
    if len(others) >= 2:
        return others
    
    return parts

def get_clean_name(name: str) -> str:
    """Returns a cleaned name string using the two-tier logic."""
    return " ".join(get_filtered_parts(name))

def get_search_name(name: str) -> str:
    """Returns a search name based on the two-tier cleaning logic."""
    parts = get_filtered_parts(name)
    if not parts:
        return name
        
    # If 3+ words remain, and it's a long name, the first two might be good
    if len(parts) >= 2:
        return f"{parts[0]} {parts[1]}"
        
    return parts[0]

def get_core_parts(name: str) -> List[str]:
    """Extracts significant name parts for matching."""
    clean = get_clean_name(name)
    primary_parts = clean.lower().split()
    
    # Define local noise words to skip
    noise_words = {"the", "and", "a", "an"}
    
    core_parts = []
    for i, part in enumerate(primary_parts):
        # Split each part by non-alphanumeric characters (e.g., "AMD.com" -> ["amd", "com"])
        sub_parts = [s for s in re.split(r'[^a-z0-9]', part) if s]
        if not sub_parts:
            continue
        
        # If no punctuation and only one sub-part, keep it (e.g., "ABC")
        if len(sub_parts) == 1 and part.isalnum():
            sub = sub_parts[0]
            # Skip noise words like "the" at the beginning
            if i == 0 and sub in noise_words and len(primary_parts) > 1:
                continue
            
            if len(sub) > 1:
                core_parts.append(sub)
            elif i == 0:
                # Keep single letter if it's the very first part (e.g., "X Corp")
                core_parts.append(sub)
            continue

        # Otherwise, the part has non-alphanumeric OR multiple sub-parts (e.g., "N.V.", "AMD.com")
        # Apply the strict filtering for 1-3 letter noise like "com", "inc", "nv", "s"
        for j, sub in enumerate(sub_parts):
            # Keep if it's the very first sub-part of the first primary part (e.g., "AMD")
            if i == 0 and j == 0:
                # Skip noise words like "the" at the beginning
                if sub in noise_words and (len(primary_parts) > 1 or len(sub_parts) > 1):
                    continue
                core_parts.append(sub)
            # Otherwise, only keep if it's > 3 letters
            elif len(sub) > 3:
                core_parts.append(sub)
    
    if not core_parts:
        # Fallback to simple split if logic above yields nothing
        parts = re.split(r'[^a-z0-9]', name.lower())
        return [p for p in parts if p]
        
    return core_parts

def update_company_profile(folder_path: str, logo_filename: str, logger: logging.Logger, logo_color: Optional[str] = None):
    profile_path = os.path.join(folder_path, "Profile.json")
    if os.path.exists(profile_path):
        temp_path = None
        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                profile = json.load(f)
            
            profile["logo_local"] = logo_filename
            if logo_color:
                profile["logo_color"] = logo_color
            
            # Create a temporary file in the same directory to ensure it's on the same partition
            # This allows for an atomic os.replace operation
            dirname = os.path.dirname(profile_path)
            fd, temp_path = tempfile.mkstemp(dir=dirname, suffix=".tmp", text=True)
            
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(profile, f, indent=2)
            
            # Atomic rename (replaces existing file if it exists)
            os.replace(temp_path, profile_path)
            
        except Exception as e:
            logger.error(f"Error updating Profile.json: {e}")
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass

def download_image(url: str, folder_path: str, logger: logging.Logger, filename_prefix: str = "logo") -> Optional[str]:
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '').lower()
            if not content_type.startswith('image/'):
                logger.warning(f"Discarded {url}: Content-type is {content_type}, not an image.")
                return None
            
            ext = ""
            if "svg" in content_type or url.lower().endswith(".svg"): ext = ".svg"
            elif "png" in content_type or url.lower().endswith(".png"): ext = ".png"
            elif "jpg" in content_type or "jpeg" in content_type or url.lower().endswith((".jpg", ".jpeg")): ext = ".jpg"
            elif "webp" in content_type or url.lower().endswith(".webp"): ext = ".webp"
            else: ext = ".png"
            
            filename = f"{filename_prefix}{ext}"
            path = os.path.join(folder_path, filename)
            with open(path, "wb") as f:
                f.write(response.content)
            return filename
        else:
            logger.warning(f"Download failed for {url}: Status {response.status_code}")
    except Exception as e:
        logger.error(f"Error downloading {url}: {e}")
        print(f"      [Error] Downloading {url}: {e}")
    return None

def search_companieslogo_com(name: str, ticker: str, folder_path: str, website: Optional[str] = None) -> str:
    """Mechanism 1: Search companieslogo.com for the logo. Best for public companies.
    
    Args:
        name: Full company name.
        ticker: Stock ticker.
        folder_path: Path to save the logo.
        website: Optional official website for better verification.
    """
    logger = get_local_logger(folder_path)
    
    # Apply search override if available (TICKER.EXCHANGE)
    ticker_exchange = os.path.basename(folder_path)
    search_name = search_overrides.get(ticker_exchange)
    if search_name:
        print(f"    [Mechanism 1] Using search override for {ticker_exchange}: {search_name}")
        logger.info(f"Using search override for {ticker_exchange}: {search_name}")
    else:
        search_name = get_search_name(name)
    
    print(f"    [Mechanism 1] Searching companieslogo.com for {search_name} ({ticker})...")
    logger.info(f"Starting Mechanism 1: companieslogo.com for {name} ({ticker})")
    
    domain = ""
    if website:
        # Simple domain extraction
        clean_ws = website.lower().replace("https://", "").replace("http://", "").replace("www.", "")
        domain = clean_ws.split('/')[0]
    
    core_parts = get_core_parts(name)
    headers = {'User-Agent': 'Mozilla/5.0'}

    try:
        with DDGS() as ddgs:
            queries = [
                f"site:companieslogo.com {search_name} {ticker} logo",
                f"site:companieslogo.com {ticker} logo"
            ]
            
            for query in queries:
                print(f"    [Mechanism 1] Searching companieslogo.com for {query}...")
                results = list(ddgs.text(query, max_results=10))
                
                for res in results:
                    href = res.get('href', '').lower()
                    title = res.get('title', '').lower()
                
                    if "companieslogo.com" in href and "/logo/" in href:
                        match_count = sum(1 for part in core_parts if part in title or part in href)
                        
                        # Strong signal: ticker match
                        ticker_lower = ticker.lower()
                        ticker_match = (re.search(rf'\b{re.escape(ticker_lower)}\b', title) or 
                                        f"({ticker_lower})" in title or
                                        f"/{ticker_lower}/" in href)
                        
                        # Strong signal: domain match
                        domain_match = domain and (domain in href or domain in title)
                        
                        # Also match if title starts with our search name and contains 'logo'
                        name_match = title.startswith(search_name.lower()) and "logo" in title

                        logger.info(f"Checking page: {href} Title: {title} TickerMatch: {ticker_match} DomainMatch: {domain_match} NameMatch: {name_match} CorePartsMatched: {match_count}/{len(core_parts)}")
                        
                        is_match = False
                        if ticker_match or domain_match or name_match:
                            is_match = True
                        elif len(core_parts) >= 2:
                            if match_count >= 2: is_match = True
                        elif len(core_parts) == 1 and match_count >= 1:
                            is_match = True

                        if is_match:
                            logger.info(f"Found matching page: {href}")
                            response = requests.get(href, headers=headers, timeout=15)
                            if response.status_code == 200:
                                soup = BeautifulSoup(response.text, 'html.parser')
                                img = soup.find('img', src=re.compile(r'img/orig')) or soup.find('img', src=re.compile(r'logos/'))
                                if img:
                                    img_url = img['src']
                                    if img_url.startswith('/'): img_url = "https://www.companieslogo.com" + img_url
                                    filename = download_image(img_url, folder_path, logger)
                                    if filename:
                                        # Check if the title or img_url suggests a white logo
                                        color = "white" if "white" in title or "white" in img_url.lower() else None
                                        logger.info(f"SUCCESS: {name} logo downloaded as {filename} from {img_url}")
                                        update_company_profile(folder_path, filename, logger, logo_color=color)
                                        return f"SUCCESS: Downloaded {filename}"
            
        logger.info(f"FAILED Mechanism 1 for {name}")
        return "FAILED: Not found on companieslogo.com"
    except Exception as e:
        logger.error(f"Error in Mechanism 1: {e}")
        return f"ERROR: {e}"

def verify_and_download_from_website(website: str, name: str, folder_path: str) -> str:
    """Mechanism 2: Verify logo on company website and download if found."""
    logger = get_local_logger(folder_path)
    if not website:
        return "FAILED: No website provided"
    
    print(f"    [Mechanism 2] Searching website {website} for logo...")
    logger.info(f"Starting Mechanism 2: Official Website for {name} ({website})")
    
    if not website.startswith("http"): website = "https://" + website
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        try:
            response = requests.get(website, headers=headers, timeout=15, allow_redirects=True)
        except requests.exceptions.RequestException as e:
            logger.warning(f"Connection error for {website}: {e}")
            return f"FAILED: Connection error"

        if response.status_code != 200:
            logger.warning(f"Website {website} returned status {response.status_code}")
            return f"FAILED: Status {response.status_code}"
            
        soup = BeautifulSoup(response.text, 'html.parser')
        potential_logos = []

        # 1. Icons and Meta (Highest Priority)
        icons = soup.find_all('link', rel=re.compile(r'icon|apple-touch-icon', re.I))
        for icon in icons:
            if icon.get('href'):
                href = icon['href']
                score = 10
                rel = icon.get('rel') or []
                if isinstance(rel, str): rel = [rel]
                if any('apple-touch-icon' in r.lower() for r in rel): score += 30
                if 'logo' in href.lower(): score += 20
                potential_logos.append((score, urljoin(website, href), "Link Icon"))

        og_image = soup.find('meta', property='og:image') or soup.find('meta', attrs={"name": "og:image"})
        if og_image and og_image.get('content'):
            potential_logos.append((45, urljoin(website, og_image['content']), "OG Image Meta"))

        # 2. Body Images
        core_parts = get_core_parts(name)
        header = soup.find('header')
        header_imgs = header.find_all('img', src=True) if header else []
        all_imgs = soup.find_all('img', src=True)
        
        for idx, img in enumerate(all_imgs):
            src = img['src'].lower()
            alt = (img.get('alt') or '').lower()
            src_clean = src.replace('-', ' ').replace('_', ' ')
            
            score = 0
            # Name match scoring
            match_count = sum(1 for part in core_parts if part in src_clean or part in alt)
            if match_count > 0:
                score += (match_count * 15)
                if match_count == len(core_parts): score += 20
            
            if 'logo' in src: score += 25
            if 'logo' in alt: score += 15
            
            # Position/Context scoring
            if img in header_imgs: score += 30
            parent_id_class = (str(img.parent.get('id', '')) + str(img.parent.get('class', ''))).lower()
            if 'logo' in parent_id_class: score += 25
            
            # Format scoring
            if '.svg' in src: score += 20
            elif '.png' in src: score += 10
            
            # Penalize deep/plugin paths
            if 'plugins/' in src or 'themes/' in src: score -= 10
            
            # Penalize white-colored logos (less severe now)
            is_white = 'white' in src or 'white' in alt
            if is_white: score -= 15
            
            # Distance from top penalty (minor)
            score -= (idx // 5)
            
            if score > 20:
                potential_logos.append((score, urljoin(website, img['src']), f"Img Tag (Score {score})", "white" if is_white else None))

        if potential_logos:
            potential_logos.sort(key=lambda x: x[0], reverse=True)
            logger.info(f"Found {len(potential_logos)} candidates. Top: {potential_logos[0][1]} Score: {potential_logos[0][0]}")
            
            for score, img_url, source_type, color in potential_logos:
                if any(x in img_url.lower() for x in ['pixel', 'tracking', 'ads', 'google-analytics', 'facebook.com']): continue
                
                filename = download_image(img_url, folder_path, logger)
                if filename:
                    logger.info(f"SUCCESS: Logo {filename} downloaded from {img_url} via {source_type}")
                    update_company_profile(folder_path, filename, logger, logo_color=color)
                    return f"SUCCESS: Downloaded {filename}"

        return "FAILED: No suitable logo found on website"
    except Exception as e:
        logger.error(f"Error in Mechanism 2: {e}")
        return f"ERROR: {e}"


def broader_internet_search(name: str, website: str, folder_path: str) -> str:
    """Mechanism 3: Broader internet search."""
    logger = get_local_logger(folder_path)
    search_name = get_search_name(name)
    ticker = ""
    ticker_match = re.search(r'[\\/]([^\\/]+)\.[^\\/]+$', folder_path)
    if ticker_match: ticker = ticker_match.group(1)

    logger.info(f"Starting Mechanism 3: Broader Internet Search for {name}")
    
    try:
        with DDGS() as ddgs:
            queries = [
                f'"{search_name}" official logo transparent png -white',
                f'"{search_name}" {ticker} logo icon -white',
                f'"{search_name}" corporate branding logo'
            ]
            
            for query in queries:
                print(f"    [Mechanism 3] Broader search for {query.replace('\"', '')}...")
                logger.info(f"Querying Images: {query}")
                results = list(ddgs.images(query, max_results=15))
                for res in results:
                    img_url = res['image'].lower()
                    title = res.get('title', '').lower()
                        
                    core_parts = get_core_parts(name)
                    match_count = sum(1 for part in core_parts if part in title or part in img_url)
                    
                    priority_domains = ['wikipedia', 'wikimedia', 'brandsoftheworld', 'seeklogo', 'logo.wine', 'linkedin.com/company', 'licdn.com']
                    
                    is_match = False
                    if len(core_parts) >= 2:
                        if match_count >= 2: is_match = True
                        elif match_count == 1 and any(x in img_url for x in priority_domains): is_match = True
                    elif len(core_parts) == 1 and match_count >= 1:
                        is_match = True
                        
                    if is_match:
                        filename = download_image(res['image'], folder_path, logger)
                        if filename:
                            update_company_profile(folder_path, filename, logger)
                            return f"SUCCESS: Downloaded {filename}"
            
        return "FAILED: No results"
    except Exception as e:
        logger.error(f"Error in Mechanism 3: {e}")
        return f"ERROR: {e}"

def generate_logo_ai(description: str, folder_path: str) -> str:
    """Mechanism 4: Generate a logo using AI."""
    logger = get_local_logger(folder_path)
    print(f"    [Mechanism 4] Generating logo using AI...")
    logger.info(f"Starting Mechanism 4: AI Generation for description: {description}")
    try:
        api_key = os.getenv("GOOGLE_API_KEY")
        client = genai.Client(api_key=api_key)
        prompt = f"A professional, modern corporate logo. Minimalist design, clean lines. Description: {description}."
        
        response = client.models.generate_images(
            model='imagen-4.0-generate-001',
            prompt=prompt,
            config=types.GenerateImagesConfig(number_of_images=1, output_mime_type='image/png')
        )
        if response.generated_images:
            filename = "logo.png"
            path = os.path.join(folder_path, filename)
            response.generated_images[0].image.save(path)
            update_company_profile(folder_path, filename, logger)
            return f"SUCCESS: Generated {filename}"
        
        return "FAILED: AI generation error"
    except Exception as e:
        logger.error(f"Error in Mechanism 4: {e}")
        return f"ERROR: {e}"
