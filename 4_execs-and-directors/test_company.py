import json
import asyncio
import os
import sys
from dotenv import load_dotenv, find_dotenv
from crew.crew import CompanyCrew

# Load environment variables from .env in parent directory
load_dotenv(find_dotenv(), override=True)

async def test_company(ticker, exchange, name):
    print(f"Test: [START] Management for {ticker}.{exchange} ({name})")
    
    # Path to Profile.json
    folder_name = f"{ticker}.{exchange}"
    abs_folder = os.path.join("..", "Companies", folder_name)
    profile_path = os.path.join(abs_folder, "Profile.json")
    
    profile_data = {}
    if os.path.exists(profile_path):
        with open(profile_path, "r", encoding="utf-8") as pf:
            profile_data = json.load(pf)
    else:
        print(f"Test: [WARNING] Profile.json not found at {profile_path}. Using defaults.")
    
    company_item = {
        "ticker": ticker,
        "exchange": exchange,
        "name": name,
        "profile": profile_data
    }
    
    crew_orchestrator = CompanyCrew()
    
    try:
        await crew_orchestrator.run(company_item, folder_name)
        print(f"Test: [DONE] Management for {ticker}.{exchange}")
    except Exception as e:
        print(f"Test: [ERROR] Management for {ticker}.{exchange}: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        # Default test cases
        asyncio.run(test_company("NVDA", "NASDAQ", "NVIDIA Corporation"))
    else:
        ticker = sys.argv[1]
        exchange = sys.argv[2]
        name = sys.argv[3]
        asyncio.run(test_company(ticker, exchange, name))
