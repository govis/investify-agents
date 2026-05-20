import json
import os
import glob
import re
from pathlib import Path
from dotenv import load_dotenv, find_dotenv

# Load environment variables
load_dotenv(find_dotenv(), override=True)
load_dotenv(os.path.join("..", ".env"), override=False)

# Constants
ALLOWED_EXCHANGES = {"NYSE", "NASDAQ", "TSX", "TSXV", "CSE", "OTC", "ASX", "LSE"}
COMPANY_LIST_PATH = Path("../CompanyList.json")
MANAGERS_DIR = Path("../Managers")
COMPANIES_DIR = Path("../Companies")
COMPANY_CANDIDATES_DIR = Path("../Company Candidates")

# Load exchange sanitization configs
UNCOMMON_CODES = os.getenv("UNCOMMON_EXCHANGE_CODES", "").split(",")
ALL_EXCHANGE_CODES = ALLOWED_EXCHANGES.union(set(c.strip() for c in UNCOMMON_CODES if c.strip()))

try:
    EXCHANGE_SUBSTITUTES = json.loads(os.getenv("EXCHANGE_NAME_SUBSTITUTE", "{}"))
except json.JSONDecodeError:
    EXCHANGE_SUBSTITUTES = {}

def load_json(path):
    if not path.exists():
        return None
    with open(path, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return None

def save_json(path, data):
    os.makedirs(path.parent, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def sanitize_exchange(exchange_str):
    if not exchange_str:
        return []
    
    # 1. Apply EXCHANGE_NAME_SUBSTITUTE
    # We sort by length descending to replace longer strings first (e.g. "NYSE American" before "NYSE")
    sorted_subs = sorted(EXCHANGE_SUBSTITUTES.items(), key=lambda x: len(x[0]), reverse=True)
    
    # Process multiple potential exchanges in the string
    # First, replace separators with commas
    exchange_str = str(exchange_str).replace('/', ',').replace(';', ',')
    parts = [p.strip() for p in exchange_str.split(',')]
    
    sanitized_parts = []
    for part in parts:
        current_part = part
        for verbose, code in sorted_subs:
            if verbose in current_part:
                current_part = current_part.replace(verbose, code)
        
        # 2. Removing repetition (e.g. "LSE (London Stock Exchange)" -> "LSE (LSE)")
        # Then clean up brackets and redundancy
        # Extract all exchange codes from the string
        found_codes = []
        for code in ALL_EXCHANGE_CODES:
            # Match code as whole word or in brackets
            pattern = r'\b' + re.escape(code) + r'\b'
            if re.search(pattern, current_part):
                found_codes.append(code)
        
        if found_codes:
            # If we found known codes, use them and ignore the rest of the text in this part
            sanitized_parts.extend(found_codes)
        else:
            # Otherwise just clean up brackets and use what's left if it's alphanumeric
            clean_part = re.sub(r'[\(\)]', '', current_part).strip()
            if clean_part:
                sanitized_parts.append(clean_part)
                
    return list(dict.fromkeys(sanitized_parts)) # Deduplicate

def sanitize_ticker_and_exchanges(raw_ticker, raw_exchanges):
    """
    Returns a list of (ticker, exchange) tuples.
    Handles "AMRQ (LSE)" and logic for splitting if ticker-exchange differs from field-exchange.
    """
    if not raw_ticker:
        return []
        
    # Remove prefixes like "TSXV: "
    ticker_base = str(raw_ticker)
    if ":" in ticker_base:
        ticker_base = ticker_base.split(":")[-1].strip()
        
    # Split multiple tickers (e.g. "GBIX / GEX")
    ticker_parts = [t.strip() for t in ticker_base.replace('/', ',').replace(';', ',').split(',')]
    
    # Sanitize the exchanges from the exchange field
    field_exchanges = sanitize_exchange(raw_exchanges)
    
    results = []
    for tp in ticker_parts:
        # Check for bracketed exchange in ticker (e.g. "BMO (TSX)")
        match = re.search(r'(.*?)\s*\((.*?)\)', tp)
        if match:
            clean_ticker = match.group(1).strip()
            bracket_exchange_str = match.group(2).strip()
            bracket_exchanges = sanitize_exchange(bracket_exchange_str)
            
            # For each bracket exchange, it's a definite pair
            for be in bracket_exchanges:
                results.append((clean_ticker, be))
            
            # Also pair the clean ticker with any field exchanges NOT already covered by brackets
            for fe in field_exchanges:
                if fe not in bracket_exchanges:
                    results.append((clean_ticker, fe))
        else:
            # No brackets, pair this ticker with all field exchanges
            for fe in field_exchanges:
                results.append((tp, fe))
                
    return list(set(results)) # Deduplicate pairs

def get_role_sections(title_or_role):
    if not title_or_role:
        return ["executives"]
    
    role_lower = title_or_role.lower()
    # Split into words to avoid sub-word matches (like 'cto' in 'director')
    import re
    words = set(re.findall(r'\w+', role_lower))
    
    # Heuristic for Board of Directors
    board_keywords = {"director", "chairman"}
    is_board = any(kw in words for kw in board_keywords)
    
    # Heuristic for Executives
    exec_keywords = {"ceo", "cfo", "cto", "coo", "president", "vp", "manager", "officer", "chief", "exec", "executive", "managing"}
    is_exec = any(kw in words for kw in exec_keywords)
    
    # Special case for "Vice President"
    if "vice" in words and "president" in words:
        is_exec = True
        
    # If it doesn't clearly match either, default to executives for safety
    if not is_board and not is_exec:
        is_exec = True
        
    sections = []
    if is_exec:
        sections.append("executives")
    if is_board:
        sections.append("board_of_directors")
    
    return sections

def process_affiliations():
    print("Loading Company List...")
    company_list = load_json(COMPANY_LIST_PATH) or []
    # Index for fast lookup: (ticker, exchange) -> index
    company_index = {(c.get('ticker'), c.get('exchange')): i for i, c in enumerate(company_list)}
    
    print("Finding manager profiles...")
    profile_paths = glob.glob(str(MANAGERS_DIR / "*" / "Profile.json"))
    print(f"Found {len(profile_paths)} profiles.")
    
    updated_companies_count = 0
    new_companies_count = 0
    
    for profile_path in profile_paths:
        manager_profile = load_json(Path(profile_path))
        if not manager_profile:
            continue
            
        manager_data = {
            "name": manager_profile.get("name"),
            "age": manager_profile.get("age"),
            "age_year": manager_profile.get("age_year"),
            "background": manager_profile.get("background")
        }
        
        affiliations = manager_profile.get("company_affiliations", [])
        for aff in affiliations:
            raw_ticker = aff.get("ticker")
            raw_exchange = aff.get("exchange")
            
            if not raw_ticker or not raw_exchange:
                continue
            
            # Use the new robust sanitization logic
            sanitized_pairs = sanitize_ticker_and_exchanges(raw_ticker, raw_exchange)
            
            for ticker, exchange in sanitized_pairs:
                if exchange not in ALLOWED_EXCHANGES:
                    continue
                
                # Check for illegal characters (anything other than Letters, Numbers, or Dots)
                is_valid = bool(re.fullmatch(r'[A-Za-z0-9.]+', ticker)) and bool(re.fullmatch(r'[A-Za-z0-9.]+', exchange))
                
                base_dir = COMPANIES_DIR if is_valid else COMPANY_CANDIDATES_DIR
                
                # 1. Update CompanyList.json (ONLY if valid)
                if is_valid:
                    key = (ticker, exchange)
                    if key not in company_index:
                        new_company = {
                            "name": aff.get("name"),
                            "ticker": ticker,
                            "exchange": exchange
                        }
                        company_list.append(new_company)
                        company_index[key] = len(company_list) - 1
                        new_companies_count += 1
                
                # 2. Company Directory & Profile.json
                company_folder_name = f"{ticker}.{exchange}"
                company_dir = base_dir / company_folder_name
                profile_json_path = company_dir / "Profile.json"
                
                if not company_dir.exists():
                    os.makedirs(company_dir, exist_ok=True)
                
                if not profile_json_path.exists():
                    profile_data = {
                        "name": aff.get("name"),
                        "ticker": ticker,
                        "exchange": exchange,
                        "website": aff.get("website"),
                        "origin": "manager_affiliation",
                        "enrichment": "pending"
                    }
                    save_json(profile_json_path, profile_data)
                
                # 3. Management.json structure
                mgmt_json_path = company_dir / "Management.json"
                mgmt_data = load_json(mgmt_json_path)
                if mgmt_data is None:
                    mgmt_data = {"executives": [], "board_of_directors": []}
                
                # Ensure sections exist if file existed but was empty or different structure
                if "executives" not in mgmt_data: mgmt_data["executives"] = []
                if "board_of_directors" not in mgmt_data: mgmt_data["board_of_directors"] = []
                
                # 4. Update Management.json
                sections = get_role_sections(aff.get("title_or_role"))
                
                for section in sections:
                    # Check if manager already in section
                    existing_manager = next((m for m in mgmt_data[section] if m.get("name") == manager_data["name"]), None)
                    
                    # Prepare tenure record
                    tenure_record = {
                        "title": aff.get("title_or_role"),
                        "start_date": aff.get("start_date"),
                        "end_date": aff.get("end_date")
                    }
                    
                    verified_current = aff.get("validated") is True and aff.get("end_date") is None
                    
                    if not existing_manager:
                        new_manager_entry = {
                            "name": manager_data["name"],
                            "age": manager_data["age"],
                            "age_year": manager_data["age_year"],
                            "background": manager_data["background"],
                            "verified_current": verified_current,
                            "tenure_dates": [tenure_record]
                        }
                        mgmt_data[section].append(new_manager_entry)
                    else:
                        # Manager exists, check if this tenure is already there
                        if not any(t.get("title") == tenure_record["title"] and t.get("start_date") == tenure_record["start_date"] for t in existing_manager.get("tenure_dates", [])):
                            if "tenure_dates" not in existing_manager:
                                existing_manager["tenure_dates"] = []
                            existing_manager["tenure_dates"].append(tenure_record)
                        
                        # Update verified_current if this record is current
                        if verified_current:
                            existing_manager["verified_current"] = True

                save_json(mgmt_json_path, mgmt_data)
                updated_companies_count += 1
                
    # Save updated CompanyList.json
    save_json(COMPANY_LIST_PATH, company_list)
    print(f"Processing complete.")
    print(f"New companies added to CompanyList.json: {new_companies_count}")
    print(f"Total company folders processed/updated: {updated_companies_count}")

if __name__ == "__main__":
    process_affiliations()
