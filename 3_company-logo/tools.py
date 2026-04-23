import os
import requests
import time
import json
import re
import logging
import tempfile
import unicodedata
import base64
from datetime import datetime
from typing import Optional, List
from ddgs import DDGS
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from urllib.parse import urljoin, urlparse
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(), override=True)

# Configuration: Words to always exclude from the end
exclude_end_words_raw = os.getenv("EXCLUDE_END_WORDS")
if not exclude_end_words_raw:
    raise ValueError("Missing EXCLUDE_END_WORDS in .env")

exclude_end_words_raw = exclude_end_words_raw.strip()
while (exclude_end_words_raw.startswith("'") and exclude_end_words_raw.endswith("'")) or \
      (exclude_end_words_raw.startswith('"') and exclude_end_words_raw.endswith('"')):
    exclude_end_words_raw = exclude_end_words_raw[1:-1].strip()

try:
    exclude_end_words = json.loads(exclude_end_words_raw)
except json.JSONDecodeError as e:
    raise ValueError(f"Failed to parse EXCLUDE_END_WORDS as JSON: {e}\nRaw value: {exclude_end_words_raw}")

# Add common German legal suffixes if not present
for g_word in ["Aktiengesellschaft", "GmbH"]:
    if g_word not in exclude_end_words:
        exclude_end_words.append(g_word)

# Configuration: Noise words
noise_words_raw = os.getenv("NOISE_WORDS")
if not noise_words_raw:
    raise ValueError("Missing NOISE_WORDS in .env")
noise_words = [w.strip().lower() for w in noise_words_raw.split(",")]

# Configuration: Words to exclude conditionally
conditional_exclude_words_raw = os.getenv("CONDITIONAL_EXCLUDE_WORDS")
if not conditional_exclude_words_raw:
    raise ValueError("Missing CONDITIONAL_EXCLUDE_WORDS in .env")
conditional_exclude_words = [w.strip().lower() for w in conditional_exclude_words_raw.split(",")]

# Configuration: Search overrides for companieslogo.com
SEARCH_OVERRIDES_RAW = os.getenv("COMPANIESLOGO_SEARCH_OVERRIDES", "{}").strip()
while (SEARCH_OVERRIDES_RAW.startswith("'") and SEARCH_OVERRIDES_RAW.endswith("'")) or \
      (SEARCH_OVERRIDES_RAW.startswith('"') and SEARCH_OVERRIDES_RAW.endswith('"')):
    SEARCH_OVERRIDES_RAW = SEARCH_OVERRIDES_RAW[1:-1].strip()
try:
    search_overrides = json.loads(SEARCH_OVERRIDES_RAW)
except json.JSONDecodeError as e:
    raise ValueError(f"Failed to parse COMPANIESLOGO_SEARCH_OVERRIDES as JSON: {e}")

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
    """Applies three-tier filtering to generate a reliable searchable term:
    1. Always exclude EXCLUDE_END_WORDS from the end (runs twice, preserves suffix punctuation).
    2. Remove NOISE_WORDS from anywhere if 2+ significant words remain.
    3. Remove CONDITIONAL_EXCLUDE_WORDS from end if 2+ truly significant words remain."""
    
    if not name:
        return []
    
    # Tier 1: Always exclude from end (twice)
    def clean_end(n: str):
        n = n.strip()
        # Clean trailing commas/dots temporarily for matching if needed, 
        # but the imperative says matching punctuation must be exact for things like N.V.
        # However, it also says "if it ends in one of the EXCLUDE_END_WORDS it gets removed. any remaining spaces or if there's "," left those are removed as well."
        
        lower_n = n.lower()
        for word in exclude_end_words:
            if not word: continue
            lower_word = word.lower()
            
            # Direct exact match at end
            if lower_n.endswith(lower_word):
                n = n[:-len(word)].rstrip(" ,.")
                return n, True
            
            # Flexible match: if word in list is "Inc" but name has "Inc.", match it
            if not lower_word.endswith(".") and lower_n.endswith(lower_word + "."):
                n = n[:-len(word)-1].rstrip(" ,.")
                return n, True
                
        return n, False

    temp_name = name
    for _ in range(2):
        temp_name, changed = clean_end(temp_name)
        if not changed:
            break
            
    # Initial split into words
    parts = temp_name.split()
    if not parts:
        return []

    # Helper to clean a word for membership checks (strip comma AND dot for noise/conditional)
    def clean_w(w): return w.lower().strip(" ,.")

    # Tier 2: Noise words
    significant_count = sum(1 for p in parts if clean_w(p) not in noise_words)
    if significant_count >= 2:
        parts = [p.rstrip(",") for p in parts if clean_w(p) not in noise_words]
    else:
        # Just strip trailing commas even if we don't remove noise words
        parts = [p.rstrip(",") for p in parts]
        
    # Tier 3: Conditional exclude words from end
    # "Truly significant" words are neither noise nor conditional
    def is_truly_significant(w):
        cw = clean_w(w)
        return cw and cw not in noise_words and cw not in conditional_exclude_words

    while len(parts) > 0:
        last_word_clean = clean_w(parts[-1])
        if last_word_clean in conditional_exclude_words:
            # Check if removal leaves at least 2 truly significant words
            remaining_ts_count = sum(1 for p in parts[:-1] if is_truly_significant(p))
            if remaining_ts_count >= 2:
                parts.pop()
            else:
                break
        else:
            break
            
    return parts

def get_search_name(name: str) -> str:
    parts = get_filtered_parts(name)
    if not parts:
        return name
        
    # If 2+ words remain, take first two
    if len(parts) >= 2:
        return f"{parts[0]} {parts[1]}"
        
    return parts[0]

def get_core_parts(name: str) -> List[str]:
    """Extracts significant name parts for matching."""
    core_parts = get_filtered_parts(name)
    
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

def update_profile_clean_name(folder_path: str, clean_name: str, logger: logging.Logger):
    """Updates Profile.json with the cleaned search name."""
    profile_path = os.path.join(folder_path, "Profile.json")
    if os.path.exists(profile_path):
        temp_path = None
        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                profile = json.load(f)
            
            if profile.get("name_clean") == clean_name:
                return

            profile["name_clean"] = clean_name
            
            dirname = os.path.dirname(profile_path)
            fd, temp_path = tempfile.mkstemp(dir=dirname, suffix=".tmp", text=True)
            
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(profile, f, indent=2)
            
            os.replace(temp_path, profile_path)
            logger.info(f"Updated Profile.json with name_clean: {clean_name}")
            
        except Exception as e:
            logger.error(f"Error updating name_clean in Profile.json: {e}")
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass

def download_image(url: str, folder_path: str, logger: logging.Logger, filename_prefix: str = "logo") -> Optional[str]:
    """Downloads an image from a URL or decodes a data URI."""
    if not url:
        return None

    # Handle Data URIs (e.g., data:image/png;base64,...)
    if url.startswith('data:'):
        try:
            header, encoded = url.split(',', 1)
            mime_type = header.split(':', 1)[1].split(';', 1)[0].lower()
            
            # Skip common dummy placeholders (e.g., 1x1 transparent GIFs/SVGs)
            if len(encoded) < 100:
                # Small data URIs are almost always placeholders or tiny icons
                logger.info(f"Skipped small data URI (placeholder?): {url[:50]}...")
                return None

            data = base64.b64decode(encoded)
            
            ext = ".png"
            if "svg" in mime_type: ext = ".svg"
            elif "png" in mime_type: ext = ".png"
            elif "jpg" in mime_type or "jpeg" in mime_type: ext = ".jpg"
            elif "webp" in mime_type: ext = ".webp"
            elif "gif" in mime_type: ext = ".gif"
            
            filename = f"{filename_prefix}{ext}"
            path = os.path.join(folder_path, filename)
            with open(path, "wb") as f:
                f.write(data)
            logger.info(f"Successfully decoded data URI to {filename}")
            return filename
        except Exception as e:
            logger.error(f"Error decoding data URI: {e}")
            return None

    # Handle standard URLs
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': urlparse(url).netloc
    }
    try:
        response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '').lower()
            
            # Some SVGs might return text/xml or image/svg+xml
            if not any(x in content_type for x in ['image/', 'text/xml', 'application/xml', 'application/octet-stream']):
                logger.warning(f"Discarded {url}: Content-type is {content_type}, likely not an image.")
                return None
            
            # Special case for application/octet-stream or xml - check extension
            if 'image/' not in content_type:
                if not any(url.lower().endswith(ext) for ext in ['.svg', '.png', '.jpg', '.jpeg', '.webp']):
                    logger.warning(f"Discarded {url}: Content-type {content_type} and no image extension.")
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

def normalize_for_match(text: str) -> str:
    """Removes accents and converts to lowercase ASCII for robust matching."""
    if not text:
        return ""
    # Normalize to NFKD to separate characters and accents, then encode to ASCII and ignore errors
    normalized = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    return normalized.lower().strip()

def search_companieslogo_com(name: str, ticker: str, folder_path: str, website: Optional[str] = None) -> str:
    """Mechanism 1: Search companieslogo.com for the logo. Best for public companies."""
    logger = get_local_logger(folder_path)
    
    # Apply search override if available (TICKER.EXCHANGE)
    ticker_exchange = os.path.basename(folder_path)
    search_name = search_overrides.get(ticker_exchange)
    if search_name:
        print(f"    [Mechanism 1] Using search override for {ticker_exchange}: {search_name}")
        logger.info(f"Using search override for {ticker_exchange}: {search_name}")
    else:
        search_name = get_search_name(name)

    core_parts = get_core_parts(name)
    # Update Profile.json with cleaned name (all significant parts)
    name_clean = " ".join(core_parts)
    update_profile_clean_name(folder_path, name_clean, logger)
    
    print(f"    [Mechanism 1] Searching companieslogo.com for {search_name} ({ticker_exchange})...")
    logger.info(f"Starting Mechanism 1: companieslogo.com for {name} ({ticker_exchange})")
    
    domain_main = ""
    if website:
        # Simple domain extraction
        clean_ws = website.lower().replace("https://", "").replace("http://", "").replace("www.", "")
        domain = clean_ws.split('/')[0]
        domain_main = domain.split('.')[0] # e.g. 'atkinsrealis' from 'atkinsrealis.com'
    
    core_parts = get_core_parts(name)
    # Normalized versions for matching
    normalized_core_parts = [normalize_for_match(p) for p in core_parts if p]
    
    headers = {'User-Agent': 'Mozilla/5.0'}

    try:
        with DDGS() as ddgs:
            # Generate multiple query variations for better coverage
            queries = [
                f"site:companieslogo.com {search_name} {ticker} logo",
                f"site:companieslogo.com {ticker} logo",
                f"site:companieslogo.com {search_name} logo"
            ]
            
            # Add a variation with just the first word if name is multi-word
            first_word = core_parts[0] if core_parts else ""
            if first_word and first_word.lower() != search_name.lower():
                queries.append(f"site:companieslogo.com {first_word} {ticker} logo")
            
            # Remove duplicates while preserving order
            seen_queries = set()
            unique_queries = []
            for q in queries:
                if q not in seen_queries:
                    unique_queries.append(q)
                    seen_queries.add(q)

            for query in unique_queries:
                print(f"    [Mechanism 1] Searching companieslogo.com for {query}...")
                results = list(ddgs.text(query, max_results=10))
                
                for res in results:
                    href = res.get('href', '').lower()
                    title = res.get('title', '').lower()
                    
                    # Normalize page info for matching
                    norm_href = normalize_for_match(href)
                    norm_title = normalize_for_match(title)
                
                    if "companieslogo.com" in href and "/logo/" in href:
                        # Match against normalized parts
                        match_count = sum(1 for part in normalized_core_parts if part in norm_title or part in norm_href)
                        
                        # Strong signal: ticker match
                        ticker_lower = ticker.lower()
                        ticker_match = (re.search(rf'\b{re.escape(ticker_lower)}\b', norm_title) or 
                                        re.search(rf'\b{re.escape(ticker_lower)}\b', norm_href) or
                                        f"({ticker_lower})" in norm_title or
                                        f"/{ticker_lower}/" in norm_href)
                        
                        # Strong signal: domain match
                        domain_match = domain_main and (domain_main in norm_href or domain_main in norm_title)
                        
                        # Also match if title contains our search name and "logo"
                        # Be careful with very short names
                        name_match = False
                        if search_name.lower() in norm_title and "logo" in norm_title:
                            # If search name is very short (e.g. "LG"), require more evidence
                            if len(search_name) <= 3:
                                if domain_match or match_count >= 2:
                                    name_match = True
                            else:
                                name_match = True
                        elif first_word and first_word.lower() in norm_title and "logo" in norm_title:
                            # Only trust first word match if it's long enough or domain also matches
                            if len(first_word) >= 4 or domain_match:
                                name_match = True

                        logger.info(f"Checking page: {href} Title: {title} TickerMatch: {ticker_match} DomainMatch: {domain_match} NameMatch: {name_match} CorePartsMatched: {match_count}/{len(core_parts)}")
                        
                        is_match = False
                        # If ticker is very short, be stricter
                        if ticker_match and len(ticker) <= 2:
                            if domain_match or match_count >= 1 or name_match:
                                is_match = True
                        elif ticker_match or domain_match or name_match:
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
                                
                                img_url = None
                                # 1. Try to find the primary SVG download link
                                # On companieslogo.com, these are usually <a> tags pointing to /img/orig/ with .svg
                                svg_link = soup.find('a', href=re.compile(r'/img/orig/.*\.svg', re.I)) or \
                                           soup.find('a', href=re.compile(r'\.svg', re.I), string=re.compile(r'SVG logo', re.I))
                                
                                if svg_link:
                                    img_url = svg_link['href']
                                else:
                                    # 2. Try to find the primary PNG download link
                                    png_link = soup.find('a', href=re.compile(r'/img/orig/.*\.png', re.I))
                                    if png_link:
                                        img_url = png_link['href']
                                    else:
                                        # 3. Fallback to img tags, but exclude generic ones and prioritize company-specific paths
                                        img = soup.find('img', src=re.compile(r'/img/orig/', re.I)) or \
                                              soup.find('img', src=re.compile(r'/logos/', re.I))
                                        
                                        if not img:
                                            # Avoid generic site SVGs
                                            all_imgs = soup.find_all('img', src=re.compile(r'\.svg', re.I))
                                            for candidate in all_imgs:
                                                src = candidate.get('src', '').lower()
                                                if all(x not in src for x in ['companies-logo.svg', 'calendar', 'warning', 'check-circle']):
                                                    img = candidate
                                                    break
                                        
                                        if img:
                                            img_url = img['src']
                                      
                                if img_url:
                                    if img_url.startswith('/'): img_url = "https://www.companieslogo.com" + img_url
                                    filename = download_image(img_url, folder_path, logger)
                                    if filename:
                                        # Check if the title or img_url suggests a white logo
                                        color = "white" if "white" in norm_title or "white" in normalize_for_match(img_url) else None
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
    
    # Extract main domain for matching
    parsed_ws = urlparse(website)
    clean_ws = parsed_ws.netloc.lower().replace("www.", "")
    domain_main = clean_ws.split('.')[0] # e.g. 'atkinsrealis' from 'atkinsrealis.com'

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9'
        }
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
                potential_logos.append((score, urljoin(website, href), "Link Icon", None))

        og_image = soup.find('meta', property='og:image') or soup.find('meta', attrs={"name": "og:image"})
        if og_image and og_image.get('content'):
            potential_logos.append((45, urljoin(website, og_image['content']), "OG Image Meta", None))

        # 2. Body Images
        core_parts = get_core_parts(name)
        # Add domain part for matching if available
        domain_parts = domain_main.split('-') if domain_main else []
        match_terms = list(set([p.lower() for p in core_parts] + domain_parts))
        
        header = soup.find('header')
        # Some sites use <div class="header"> instead of <header>
        if not header:
            header = soup.find(class_=re.compile(r'header|nav|topbar', re.I))
            
        header_imgs = header.find_all('img') if header else []
        footer = soup.find('footer') or soup.find(class_=re.compile(r'footer', re.I))
        footer_imgs = footer.find_all('img') if footer else []
        all_imgs = soup.find_all('img')
        
        for idx, img in enumerate(all_imgs):
            # Check multiple attributes for the image source (handle lazy loading)
            src_attrs = ['src', 'data-src', 'data-lazy-src', 'data-original', 'data-original-src', 'data-fallback-src']
            best_src = None
            
            # Find the best source attribute for this image
            for attr in src_attrs:
                val = img.get(attr)
                if val:
                    # Prefer standard URLs over data URIs if both exist
                    if not val.startswith('data:'):
                        best_src = val
                        break
                    elif not best_src:
                        best_src = val
            
            if not best_src:
                # Check srcset as a fallback
                srcset = img.get('srcset') or img.get('data-srcset')
                if srcset:
                    # Take the first (usually smallest or default) image from srcset
                    best_src = srcset.split(',')[0].split(' ')[0]
            
            if not best_src:
                continue

            src_lower = best_src.lower()
            alt = (img.get('alt') or '').lower()
            src_clean = src_lower.replace('-', ' ').replace('_', ' ')
            
            score = 0
            # Name/Domain match scoring
            match_count = sum(1 for part in match_terms if len(part) >= 3 and (part in src_clean or part in alt))
            if match_count > 0:
                score += (match_count * 20)
                if match_count == len(match_terms): score += 20
            
            if 'logo' in src_lower: score += 30
            if 'logo' in alt: score += 20
            
            # Position/Context scoring
            if img in header_imgs: score += 40
            if img in footer_imgs: score += 20
            
            # Check for link to homepage (very strong logo signal)
            parent_a = img.find_parent('a')
            if parent_a and parent_a.get('href'):
                href = parent_a['href'].lower()
                # matches "/", "", "https://domain.com", "https://domain.com/"
                if href in ['/', '', website.lower(), website.lower() + '/'] or \
                   href == urljoin(website, '/') or href == urljoin(website, ''):
                    score += 50
            
            parent_id_class = ""
            for p in img.parents:
                parent_id_class += str(p.get('id', '')) + " " + " ".join(p.get('class', []) if isinstance(p.get('class'), list) else [str(p.get('class', ''))])
                if p.name in ['header', 'nav']: break # Don't go too far up
                if len(parent_id_class) > 200: break
                
            parent_id_class = parent_id_class.lower()
            if 'logo' in parent_id_class: score += 25
            
            # Format scoring
            if '.svg' in src_lower: score += 25
            elif '.png' in src_lower: score += 10
            
            # Penalize social media icons (very important)
            social_keywords = ['twitter', 'facebook', 'linkedin', 'instagram', 'youtube', 'twiter', 'x.com', 'threads.net', 'vimeo.com', 'pinterest', 'tiktok']
            if any(k in src_lower or k in alt for k in social_keywords):
                score -= 150
                
            # Check if parent <a> link is social media
            if parent_a and parent_a.get('href'):
                href = parent_a['href'].lower()
                if any(k in href for k in social_keywords):
                    score -= 150
            
            # Penalize deep/plugin paths
            if 'plugins/' in src_lower or 'themes/' in src_lower: score -= 10
            
            # Penalize white-colored logos (less severe)
            is_white = 'white' in src_lower or 'white' in alt
            if is_white: score -= 10
            
            # Distance from top penalty (minor)
            score -= (idx // 3)
            
            if score > 20:
                potential_logos.append((score, urljoin(website, best_src), f"Img Tag (Score {score})", "white" if is_white else None))

        if potential_logos:
            # Filter out duplicates and keep highest score for each URL
            unique_potential = {}
            for score, url, source, color in potential_logos:
                if url not in unique_potential or score > unique_potential[url][0]:
                    unique_potential[url] = (score, source, color)
            
            sorted_logos = sorted([(s, u, src, c) for u, (s, src, c) in unique_potential.items()], key=lambda x: x[0], reverse=True)
            logger.info(f"Found {len(sorted_logos)} candidates. Top: {sorted_logos[0][1]} Score: {sorted_logos[0][0]}")
            
            for score, img_url, source_type, color in sorted_logos:
                # Blacklist tracking/junk (use word boundaries for 'ads' to avoid matching 'uploads')
                blacklist = ['pixel', 'tracking', r'\bads\b', 'google-analytics', 'facebook.com', 'quantserve', 'doubleclick']
                if any(re.search(pattern, img_url.lower()) if '\\b' in pattern else pattern in img_url.lower() for pattern in blacklist):
                    logger.info(f"Skipping blacklisted URL: {img_url}")
                    continue
                
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
    
    ticker_exchange = os.path.basename(folder_path)
    ticker = ticker_exchange.split('.')[0] if '.' in ticker_exchange else ticker_exchange

    logger.info(f"Starting Mechanism 3: Broader Internet Search for {name} ({ticker_exchange})")
    
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
