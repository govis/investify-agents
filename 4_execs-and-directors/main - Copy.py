import json
import asyncio
import os
from dotenv import load_dotenv, find_dotenv
from crew.crew import CompanyCrew

load_dotenv(find_dotenv(), override=True)

# Configuration
CONCURRENCY_LIMIT = int(os.getenv("CONCURRENCY_LIMIT", "1"))
MAX_CONSECUTIVE_ERRORS = int(os.getenv("MAX_CONSECUTIVE_ERRORS", "3"))
EXCHANGE_MAPPING_STR = os.getenv("EXCHANGE_MAPPING", '{"TSX": "Canada", "TSXV": "Canada", "CSE": "Canada", "NYSE": "US", "NASDAQ": "US"}')

try:
    EXCHANGE_MAPPING = json.loads(EXCHANGE_MAPPING_STR)
except:
    EXCHANGE_MAPPING = {"TSX": "Canada", "TSXV": "Canada", "CSE": "Canada", "NYSE": "US", "NASDAQ": "US"}

# Global state
consecutive_errors = 0
error_lock = asyncio.Lock()
stop_event = asyncio.Event()

async def worker(queue, crew_orchestrator):
    global consecutive_errors
    while not queue.empty() and not stop_event.is_set():
        company = await queue.get()
        ticker = company['ticker']
        exchange = company['exchange']
        folder = os.path.join("Companies", f"{ticker}.{exchange}")
        
        print(f"Main: [START] Management for {ticker}.{exchange}")
        try:
            await crew_orchestrator.run(company, folder)
            
            async with error_lock:
                consecutive_errors = 0
                
            print(f"Main: [DONE] Management for {ticker}.{exchange}")
            
        except Exception as e:
            async with error_lock:
                consecutive_errors += 1
                current_errs = consecutive_errors
            print(f"Main: [ERROR] Management for {ticker}.{exchange}: {e}")
            if current_errs >= MAX_CONSECUTIVE_ERRORS:
                print("Main: [FATAL] Max consecutive errors reached. Signaling stop.")
                stop_event.set()
        
        queue.task_done()

async def main():
    print(f"Workflow 4: Management starting with CONCURRENCY_LIMIT={CONCURRENCY_LIMIT}...")
    list_path = "../CompanyList.json"
    if not os.path.exists(list_path):
        print(f"{list_path} not found. Run Workflow 1 first.")
        return

    with open(list_path, "r") as f:
        all_companies = json.load(f)

    # Filter out companies that already have management data
    companies_to_process = []
    for company in all_companies:
        path = os.path.join("..", "Companies", f"{company['ticker']}.{company['exchange']}", "Management.json")
        if not os.path.exists(path):
            companies_to_process.append(company)

    if not companies_to_process:
        print("Main: No new companies to process.")
        return

    queue = asyncio.Queue()
    for company in companies_to_process:
        queue.put_nowait(company)

    crew_orchestrator = CompanyCrew(EXCHANGE_MAPPING)
    
    # Start workers
    workers = [asyncio.create_task(worker(queue, crew_orchestrator)) for _ in range(CONCURRENCY_LIMIT)]
    
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
