import json
import asyncio
import os
from pipeline import ManagerEnrichmentPipeline
from tools import populate_base_profile
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(), override=True)

# Configuration
CONCURRENCY_LIMIT = int(os.getenv("CONCURRENCY_LIMIT", "1"))
MAX_CONSECUTIVE_ERRORS = int(os.getenv("MAX_CONSECUTIVE_ERRORS", "3"))
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")

# Global state
consecutive_errors = 0
error_lock = asyncio.Lock()
stop_event = asyncio.Event()

async def worker(queue, pipeline):
    global consecutive_errors
    while not queue.empty() and not stop_event.is_set():
        profile_path = await queue.get()
        
        print(f"Main: [START] Enrichment for {os.path.basename(os.path.dirname(profile_path))}")
        try:
            result = await pipeline.run(profile_path)
            if result.get("success"):
                print(f"Main: [DONE] Enrichment for {os.path.basename(os.path.dirname(profile_path))}")
                async with error_lock:
                    consecutive_errors = 0
            else:
                raise Exception(result.get("message", "Unknown error"))
                
        except Exception as e:
            async with error_lock:
                consecutive_errors += 1
                current_errs = consecutive_errors
            print(f"Main: [ERROR] Enrichment for {profile_path}: {e}")
            if current_errs >= MAX_CONSECUTIVE_ERRORS:
                print("Main: [FATAL] Max consecutive errors reached. Signaling stop.")
                stop_event.set()
        
        queue.task_done()

async def main():
    print(f"Workflow 5: Manager Profiles starting with CONCURRENCY_LIMIT={CONCURRENCY_LIMIT}...")
    
    officers_path = os.path.join("..", "OfficersAndDirectors.json")
    managers_dir = os.path.join("..", "Managers")
    
    if not os.path.exists(officers_path):
        print(f"Error: {officers_path} not found.")
        return

    os.makedirs(managers_dir, exist_ok=True)

    try:
        with open(officers_path, "r", encoding="utf-8") as f:
            all_officers = json.load(f)
    except Exception as e:
        print(f"Error reading OfficersAndDirectors.json: {e}")
        return

    # Phase 1: Populate all base profiles
    print(f"Main: Populating base profiles for {len(all_officers)} individuals...")
    profile_paths = []
    for person in all_officers:
        path = populate_base_profile(person, managers_dir)
        profile_paths.append(path)
    
    # Phase 2: Enrich profiles using Agent
    to_enrich = []
    for path in profile_paths:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get("enrichment_status") != "success":
                    to_enrich.append(path)
        except Exception:
            continue

    if not to_enrich:
        print("Main: No profiles to enrich.")
        return

    # Use PROFILES_TO_ENRICH parameter
    profiles_to_enrich = int(os.getenv("PROFILES_TO_ENRICH", "0"))
    if profiles_to_enrich > 0:
        to_enrich = to_enrich[:profiles_to_enrich]
        print(f"Main: Enriching next {profiles_to_enrich} profiles.")
    else:
        print(f"Main: Enriching all {len(to_enrich)} remaining profiles.")

    queue = asyncio.Queue()
    for path in to_enrich:
        queue.put_nowait(path)

    pipeline = ManagerEnrichmentPipeline(model_name=GEMINI_MODEL)
    
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
