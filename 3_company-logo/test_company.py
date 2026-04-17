import asyncio
import os
import json
import sys
from pipeline import LogoPipeline

async def test_company(ticker_exchange):
    # Expected format: TICKER.EXCHANGE (e.g., AMD.NASDAQ)
    if "." not in ticker_exchange:
        print("Error: Provide company in TICKER.EXCHANGE format (e.g., AMD.NASDAQ)")
        return

    ticker, exchange = ticker_exchange.split(".", 1)
    folder = os.path.join("..", "Companies", f"{ticker}.{exchange}")
    profile_path = os.path.join(folder, "Profile.json")

    if not os.path.exists(profile_path):
        print(f"Error: {profile_path} not found.")
        return

    with open(profile_path, "r", encoding="utf-8") as f:
        profile = json.load(f)

    company = {
        "name": profile.get("name", ""),
        "ticker": ticker,
        "exchange": exchange
    }
    website = profile.get("website", "")
    
    # Ensure directory exists (though it should if Profile.json exists)
    os.makedirs(folder, exist_ok=True)
    
    pipeline = LogoPipeline()
    print(f"Main: [START] Logo for {ticker_exchange}")
    result = await pipeline.run(company, website, folder)
    print(f"Main: [DONE] Logo for {ticker_exchange}")
    print(f"Result: {result}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_company.py TICKER.EXCHANGE")
    else:
        asyncio.run(test_company(sys.argv[1]))
