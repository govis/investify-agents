import json
import asyncio
import os
from dotenv import load_dotenv, find_dotenv
from crew.crew import ManagerCrew

# Prioritize local .env, then fallback to parent directory .env
load_dotenv(find_dotenv(), override=True)
load_dotenv(os.path.join("..", ".env"))

# Configuration
CONCURRENCY_LIMIT = int(os.getenv("CONCURRENCY_LIMIT", "1"))
MAX_CONSECUTIVE_ERRORS = int(os.getenv("MAX_CONSECUTIVE_ERRORS", "3"))
MANAGERS_TO_ENRICH = int(os.getenv("MANAGERS_TO_ENRICH", "1"))

# Global state
consecutive_errors = 0
error_lock = asyncio.Lock()
stop_event = asyncio.Event()

async def worker(queue, crew_orchestrator):
    global consecutive_errors
    while not queue.empty() and not stop_event.is_set():
        manager_item = await queue.get()
        folder_path = manager_item['folder_path']
        manager_name = manager_item['name']
        
        print(f"Main: [START] Enrichment for {manager_name}")
        try:
            await crew_orchestrator.run(manager_item['profile'], folder_path)
            
            async with error_lock:
                consecutive_errors = 0
                
            print(f"Main: [DONE] Enrichment for {manager_name}")
            
        except Exception as e:
            async with error_lock:
                consecutive_errors += 1
                current_errs = consecutive_errors
            print(f"Main: [ERROR] Enrichment for {manager_name}: {e}")
            if current_errs >= MAX_CONSECUTIVE_ERRORS:
                print("Main: [FATAL] Max consecutive errors reached. Signaling stop.")
                stop_event.set()
        
        queue.task_done()

async def main():
    print(f"Workflow 4: Manager Enrichment starting with CONCURRENCY_LIMIT={CONCURRENCY_LIMIT}...")
    
    managers_dir = os.path.join("..", "Managers")
    if not os.path.exists(managers_dir):
        print(f"Error: {managers_dir} not found.")
        return

    # Find Profile.json files that need enrichment
    # For Phase 3, we might want to process all or use a flag. 
    # Let's check for those that don't have Enrichment.log yet
    managers_to_process = []
    
    for folder_name in os.listdir(managers_dir):
        folder_path = os.path.join(managers_dir, folder_name)
        if not os.path.isdir(folder_path):
            continue
            
        profile_path = os.path.join(folder_path, "Profile.json")
        
        if os.path.exists(profile_path):
            try:
                with open(profile_path, "r", encoding="utf-8") as pf:
                    profile_data = json.load(pf)
                    
                    # Incremental run: only process if company_affiliations step is not yet successful
                    if profile_data.get("enrichment_company_affiliations") != "success":
                        managers_to_process.append({
                            "name": profile_data.get("name"),
                            "profile": profile_data,
                            "folder_path": folder_path
                        })
                        
            except Exception as e:
                print(f"Main: [SKIP] Could not read Profile.json for {folder_name}: {e}")

    if not managers_to_process:
        print("Main: No new manager profiles to enrich.")
        return

    # Apply limit
    if MANAGERS_TO_ENRICH > 0:
        managers_to_process = managers_to_process[:MANAGERS_TO_ENRICH]
        print(f"Main: Limiting to next {MANAGERS_TO_ENRICH} managers for processing.")

    print(f"Main: Found {len(managers_to_process)} managers to process.")

    queue = asyncio.Queue()
    for manager in managers_to_process:
        queue.put_nowait(manager)

    crew_orchestrator = ManagerCrew()
    
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
