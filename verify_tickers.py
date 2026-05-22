import os
import json
import yfinance as yf
import sys
import time

EXCHANGE_MAP = {
    "NASDAQ": [""],
    "NYSE": [""],
    "HKEX": [".HK"],
    "HKSE": [".HK"],
    "TSE": [".T"],
    "TYO": [".T"],
    "TWSE": [".TW", ".TWO"],
    "TPEX": [".TWO"],
    "ASX": [".AX"],
    "LSE": [".L"],
    "TSX": [".TO"],
    "TSXV": [".V"],
    "OTC": [".PK", ".OB", ""],
    "AEX": [".AS"],
    "XETRA": [".DE"],
    "Xetra": [".DE"],
    "BMV": [".MX"],
    "SZSE": [".SZ"],
    "SSE": [".SS"],
    "AMEX": [""],
    "OTCMKTS": [".PK", ".OB"],
    "B3": [".SA"],
    "BVMF": [".SA"],
    "SWX": [".SW"],
    "SIX": [".SW"],
    "MIL": [".MI"],
    "PAR": [".PA"],
    "FRA": [".F"],
    "STO": [".ST"],
    "OSL": [".OL"],
    "HEL": [".HE"],
    "CPH": [".CO"],
    "ICE": [".IC"],
    "MAD": [".MC"],
    "LIS": [".LS"],
    "VIE": [".VI"],
    "ATH": [".AT"],
    "IST": [".IS"],
    "JSE": [".JO"],
    "NSE": [".NS"],
    "BSE": [".BO"],
    "KRX": [".KS", ".KQ"],
    "SGX": [".SI"],
    "KLSE": [".KL"],
    "SET": [".BK"],
    "IDX": [".JK"],
    "PSE": [".PS"],
    "HOSE": [".VN"],
    "HNX": [".VN"]
}

def log(message):
    print(message)
    try:
        with open("verification_log.txt", "a", encoding="utf-8") as f:
            f.write(message + "\n")
    except:
        pass

def verify_company(profile_path):
    try:
        with open(profile_path, 'r', encoding='utf-8') as f:
            profile = json.load(f)
    except Exception as e:
        log(f"Error reading {profile_path}: {e}")
        return

    # Skip if already verified (yes or no)
    if profile.get("ticker_verified") in ["yes", "no"]:
        return

    ticker = profile.get("ticker")
    exchange = profile.get("exchange")
    current_name = profile.get("name")

    if not ticker or not exchange:
        return

    suffixes = EXCHANGE_MAP.get(exchange, [""])
    
    verified = False
    for suffix in suffixes:
        yahoo_ticker = f"{ticker}{suffix}"
        try:
            stock = yf.Ticker(yahoo_ticker)
            info = stock.info
            
            if not info or 'symbol' not in info:
                continue

            # Check if active
            if not info.get('marketCap') and not info.get('regularMarketPrice'):
                 fast = stock.fast_info
                 if not fast.get('last_price') or fast.get('last_price') == 0:
                     continue

            profile["ticker_verified"] = "yes"
            
            yahoo_name = info.get("longName") or info.get("shortName")
            if yahoo_name and yahoo_name.lower() != current_name.lower():
                profile["name_verified"] = yahoo_name
                log(f"Verified {yahoo_ticker}: Name mismatch. Local: {current_name}, Yahoo: {yahoo_name}")
            else:
                # log(f"Verified {yahoo_ticker}: Match")
                pass

            with open(profile_path, 'w', encoding='utf-8') as f:
                json.dump(profile, f, indent=2)
            
            verified = True
            break # Found a match

        except Exception as e:
            continue
            
    if not verified:
        log(f"Ticker {ticker} not found/active on {exchange} (tried {suffixes}) for {profile_path} [Local Name: {current_name}]")
        profile["ticker_verified"] = "no"
        try:
            with open(profile_path, 'w', encoding='utf-8') as f:
                json.dump(profile, f, indent=2)
        except:
            pass

def main():
    RESUME_FROM = 2260 # Skip the first N folders

    companies_dir = "Companies"
    folders = os.listdir(companies_dir)
    total = len(folders)
    
    # Optional: ensure deterministic order
    folders.sort()

    log(f"Resuming verification from index {RESUME_FROM}/{total}...")
    
    for i, folder in enumerate(folders):
        if i < RESUME_FROM:
            continue
            
        if i % 10 == 0:
            log(f"Processing {i}/{total}...")
        
        folder_path = os.path.join(companies_dir, folder)
        if os.path.isdir(folder_path):
            profile_path = os.path.join(folder_path, "Profile.json")
            if os.path.exists(profile_path):
                verify_company(profile_path)
        
        time.sleep(0.1)

if __name__ == "__main__":
    main()
