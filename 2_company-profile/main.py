import json
import asyncio
import os
from pipeline import ProfilingPipeline
from schema import CompanyProfile
from dotenv import load_dotenv, find_dotenv

# Prioritize local .env, then fallback to parent directory .env
load_dotenv(find_dotenv(), override=True)
load_dotenv(os.path.join("..", ".env"))

# Configuration
CONCURRENCY_LIMIT = int(os.getenv("CONCURRENCY_LIMIT", "1"))
MAX_CONSECUTIVE_ERRORS = int(os.getenv("MAX_CONSECUTIVE_ERRORS", "3"))
PROFILES_TO_PROCESS = int(os.getenv("PROFILES_TO_PROCESS", "10000"))
EXCHANGE_FILTER = os.getenv("EXCHANGE_FILTER", "")
EXCHANGE_NAME_SUBSTITUTE = os.getenv("EXCHANGE_NAME_SUBSTITUTE", "{}")

# Parse exchange filter into a list
included_exchanges = [e.strip() for e in EXCHANGE_FILTER.split(",") if e.strip()]

# Parse exchange substitutes (expected as JSON string mapping)
try:
    exchange_subs = json.loads(EXCHANGE_NAME_SUBSTITUTE)
except json.JSONDecodeError:
    print(f"Warning: EXCHANGE_NAME_SUBSTITUTE is not valid JSON. Using empty mapping.")
    exchange_subs = {}

# Global state
consecutive_errors = 0
error_lock = asyncio.Lock()
stop_event = asyncio.Event()

async def worker(queue, pipeline):
    global consecutive_errors
    while not queue.empty() and not stop_event.is_set():
        company = await queue.get()
        ticker = company['ticker']
        exchange = company['exchange']
        folder = os.path.join("..", "Companies", f"{ticker}.{exchange}")
        profile_path = os.path.join(folder, "Profile.json")
        
        print(f"Main: [START] {ticker}.{exchange}")
        try:
            result, raw_result = await pipeline.run(company)
            if result:
                # Map results (could be pydantic model, dict, or string)
                if hasattr(result, 'model_dump'):
                    res_dict = result.model_dump()
                elif isinstance(result, dict):
                    res_dict = result
                else:
                    print(f"Main: [ERROR] {ticker}.{exchange}: Result is not a dictionary or model.")
                    async with error_lock:
                        consecutive_errors += 1
                    continue

                # Ensure ticker, exchange, and investment_theses match CompanyList.json exactly
                # We do this manually to save LLM tokens and ensure precision
                res_dict['ticker'] = ticker
                res_dict['exchange'] = exchange
                theses = company.get('theses', [])
                res_dict['investment_theses'] = theses
                if theses:
                    res_dict['origin'] = "investment_theses"

                os.makedirs(folder, exist_ok=True)
                with open(profile_path, "w", encoding="utf-8") as f:
                    json.dump(res_dict, f, indent=2)
                print(f"Main: [DONE] {ticker}.{exchange}")
                
            async with error_lock:
                consecutive_errors = 0
                
        except Exception as e:
            async with error_lock:
                consecutive_errors += 1
                current_errs = consecutive_errors
            print(f"Main: [ERROR] {ticker}.{exchange}: {e}")
            if current_errs >= MAX_CONSECUTIVE_ERRORS:
                print("Main: [FATAL] Max consecutive errors reached. Signaling stop.")
                stop_event.set()
        
        queue.task_done()

async def main():
    print(f"Workflow 2: Profiling starting with CONCURRENCY_LIMIT={CONCURRENCY_LIMIT}...")
    company_list_file = "../CompanyList.json"
    if not os.path.exists(company_list_file):
        print(f"Error: {company_list_file} not found. Run Workflow 1 first.")
        return

    with open(company_list_file, "r", encoding="utf-8") as f:
        companies = json.load(f)

    # Filter out companies that already have folders, don't match exchange filter, or have non-alphanumeric tickers
    companies_to_process = []
    for company in companies:
        ticker = company['ticker']
        orig_exchange = company['exchange']
        
        # Skip if ticker has non-alphanumeric characters ('.', '-', ' ', etc.)
        if not ticker.isalnum():
            continue

        # Check original exchange against filter
        if included_exchanges and orig_exchange not in included_exchanges:
            continue

        # Apply substitution to the company record
        new_exchange = exchange_subs.get(orig_exchange, orig_exchange)
        company['exchange'] = new_exchange

        folder = os.path.join("..", "Companies", f"{company['ticker']}.{new_exchange}")
        if not os.path.exists(folder):
            companies_to_process.append(company)

    if not companies_to_process:
        print("Main: No new companies to process.")
        return

    # Limit the number of companies to process
    companies_to_process = companies_to_process[:PROFILES_TO_PROCESS]
    print(f"Main: Processing {len(companies_to_process)} companies.")

    queue = asyncio.Queue()
    for company in companies_to_process:
        queue.put_nowait(company)

    pipeline = ProfilingPipeline()
    
    # Start workers
    workers = [asyncio.create_task(worker(queue, pipeline)) for _ in range(CONCURRENCY_LIMIT)]
    
    # Wait for completion or fatal error
    done, pending = await asyncio.wait(workers, return_when=asyncio.FIRST_COMPLETED)
    
    if stop_event.is_set():
        print("\nMain: FATAL ERROR detected. Cancelling remaining workers.")
        for w in workers:
            if not w.done():
                w.cancel()
    
    await asyncio.gather(*workers, return_exceptions=True)
    print("Main: Processing finished.")

if __name__ == "__main__":
    asyncio.run(main())
