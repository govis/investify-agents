import json
import asyncio
import os
from dotenv import load_dotenv, find_dotenv
from crew.crew import CompanyCrew

load_dotenv(find_dotenv(), override=True)

# Configuration
CONCURRENCY_LIMIT = int(os.getenv("CONCURRENCY_LIMIT", "1"))
MAX_CONSECUTIVE_ERRORS = int(os.getenv("MAX_CONSECUTIVE_ERRORS", "3"))

# Global state
consecutive_errors = 0
error_lock = asyncio.Lock()
stop_event = asyncio.Event()

async def worker(queue, crew_orchestrator):
    global consecutive_errors
    while not queue.empty() and not stop_event.is_set():
        company_item = await queue.get()
        folder_name = company_item['folder_name']
        
        print(f"Main: [START] Management for {folder_name}")
        try:
            await crew_orchestrator.run(company_item, folder_name)
            
            async with error_lock:
                consecutive_errors = 0
                
            print(f"Main: [DONE] Management for {folder_name}")
            
        except Exception as e:
            async with error_lock:
                consecutive_errors += 1
                current_errs = consecutive_errors
            print(f"Main: [ERROR] Management for {folder_name}: {e}")
            if current_errs >= MAX_CONSECUTIVE_ERRORS:
                print("Main: [FATAL] Max consecutive errors reached. Signaling stop.")
                stop_event.set()
        
        queue.task_done()

async def main():
    print(f"Workflow 4: Management starting with CONCURRENCY_LIMIT={CONCURRENCY_LIMIT}...")
    
    companies_dir = os.path.join("..", "Companies")
    if not os.path.exists(companies_dir):
        print(f"Error: {companies_dir} not found.")
        return

    # Filter: must have folder and Profile.json, but no Management.json
    companies_to_process = []
    
    for folder_name in os.listdir(companies_dir):
        folder_path = os.path.join(companies_dir, folder_name)
        if not os.path.isdir(folder_path):
            continue
            
        profile_path = os.path.join(folder_path, "Profile.json")
        management_path = os.path.join(folder_path, "Management.json")
        
        if os.path.exists(profile_path) and not os.path.exists(management_path):
            try:
                with open(profile_path, "r", encoding="utf-8") as pf:
                    profile_data = json.load(pf)
                    
                    # Construct company item from Profile.json
                    company_item = {
                        "name": profile_data.get("name"),
                        "ticker": profile_data.get("ticker"),
                        "exchange": profile_data.get("exchange"),
                        "profile": profile_data,
                        "folder_name": folder_name
                    }
                    
                    if company_item["ticker"] and company_item["exchange"]:
                        companies_to_process.append(company_item)
                    else:
                        print(f"Main: [SKIP] Missing ticker/exchange in Profile.json for {folder_name}")
                        
            except Exception as e:
                print(f"Main: [SKIP] Could not read Profile.json for {folder_name}: {e}")

    if not companies_to_process:
        print("Main: No new companies to process.")
        return

    print(f"Main: Found {len(companies_to_process)} companies to process.")

    queue = asyncio.Queue()
    for company in companies_to_process:
        queue.put_nowait(company)

    crew_orchestrator = CompanyCrew()
    
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
