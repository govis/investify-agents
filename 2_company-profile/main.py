import json
import asyncio
import os
from pipeline import ProfilingPipeline
from schema import CompanyProfile
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(), override=True)

# Configuration
CONCURRENCY_LIMIT = int(os.getenv("CONCURRENCY_LIMIT", "1"))
MAX_CONSECUTIVE_ERRORS = int(os.getenv("MAX_CONSECUTIVE_ERRORS", "3"))
EXCHANGE_FILTER = os.getenv("EXCHANGE_FILTER", "")

# Parse exchange filter into a list
included_exchanges = [e.strip() for e in EXCHANGE_FILTER.split(",") if e.strip()]

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
            result = await pipeline.run(company)
            if result:
                # Ensure ticker and exchange match CompanyList.json
                if hasattr(result, 'ticker'):
                    result.ticker = ticker
                elif isinstance(result, dict):
                    result['ticker'] = ticker
                    
                if hasattr(result, 'exchange'):
                    result.exchange = exchange
                elif isinstance(result, dict):
                    result['exchange'] = exchange

                os.makedirs(folder, exist_ok=True)
                with open(profile_path, "w", encoding="utf-8") as f:
                    if hasattr(result, 'model_dump_json'):
                        f.write(result.model_dump_json(indent=2))
                    else:
                        json.dump(result, f, indent=2)
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

    # Filter out companies that already have profiles or don't match exchange filter
    companies_to_process = []
    for company in companies:
        if included_exchanges and company['exchange'] not in included_exchanges:
            continue

        path = os.path.join("..", "Companies", f"{company['ticker']}.{company['exchange']}", "Profile.json")
        if not os.path.exists(path):
            companies_to_process.append(company)

    if not companies_to_process:
        print("Main: No new companies to process.")
        return

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
