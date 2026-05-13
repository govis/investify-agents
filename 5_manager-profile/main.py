import json
import asyncio
import os
import argparse
from pipeline import ManagerEnrichmentPipeline
from dotenv import load_dotenv, find_dotenv

load_dotenv(os.path.join("..", ".env")) # Load global keys from parent
load_dotenv(find_dotenv(), override=True) # Load/Override with local settings

# Configuration
CONCURRENCY_LIMIT = int(os.getenv("CONCURRENCY_LIMIT", "1"))
MAX_CONSECUTIVE_ERRORS = int(os.getenv("MAX_CONSECUTIVE_ERRORS", "3"))
GEMINI_MODEL = os.getenv("GEMINI_MODEL")
if not GEMINI_MODEL:
    raise ValueError("GEMINI_MODEL environment variable is not set in .env")

# Global state
consecutive_errors = 0
error_lock = asyncio.Lock()
stop_event = asyncio.Event()

async def worker(queue, pipeline, get_picture, search_picture_li):
    global consecutive_errors
    while not queue.empty() and not stop_event.is_set():
        profile_path = await queue.get()
        
        print(f"Main: [START] Enrichment for {os.path.basename(os.path.dirname(profile_path))}")
        try:
            result = await pipeline.run(profile_path, get_picture=get_picture, search_picture_li=search_picture_li)
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
    parser = argparse.ArgumentParser(description="Enrich manager profiles using multi-agent pipeline.")
    parser.add_argument("--manager", type=str, help="Specific manager name to process (e.g. 'Aaron Jagdfeld')")
    parser.add_argument("--get_picture", type=str, default="no", choices=["yes", "no"], help="Whether to attempt picture downloads in subsequent steps (default: no)")
    parser.add_argument("--search_picture_li", type=str, default="no", choices=["yes", "no"], help="Whether to perform specialized LinkedIn Image Search (2a) (default: no)")
    args = parser.parse_args()

    print(f"Workflow 5: Manager Profiles starting with CONCURRENCY_LIMIT={CONCURRENCY_LIMIT}, get_picture={args.get_picture}, search_picture_li={args.search_picture_li}...")
    
    managers_dir = os.path.join("..", "Managers")
    os.makedirs(managers_dir, exist_ok=True)

    # Phase 2: Enrich profiles using Agent
    to_enrich = []
    
    if args.manager:
        print(f"Main: Targeted search for manager: {args.manager}")
        for root, dirs, files in os.walk(managers_dir):
            if "Profile.json" in files:
                path = os.path.join(root, "Profile.json")
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if data.get('name') == args.manager:
                        to_enrich.append(path)
                        break
                except Exception:
                    continue
        if not to_enrich:
            print(f"Main: Manager '{args.manager}' not found.")
            return
    else:
        print("Scanning for profiles to enrich...")
        for root, dirs, files in os.walk(managers_dir):
            if "Profile.json" in files:
                path = os.path.join(root, "Profile.json")
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if "enrichment_socials" not in data or data.get("enrichment_socials") == "pending":
                            to_enrich.append(path)
                except Exception:
                    continue

    if not to_enrich:
        print("Main: No profiles to enrich.")
        return

    # Use PROFILES_TO_ENRICH parameter (only if not targeting specific manager)
    if not args.manager:
        profiles_to_enrich = int(os.getenv("PROFILES_TO_ENRICH", "0"))
        if profiles_to_enrich > 0:
            to_enrich = to_enrich[:profiles_to_enrich]
            print(f"Main: Enriching next {len(to_enrich)} profiles.")
        else:
            print(f"Main: Enriching all {len(to_enrich)} remaining profiles.")
    else:
        print(f"Main: Processing {len(to_enrich)} targeted profile.")

    queue = asyncio.Queue()
    for path in to_enrich:
        queue.put_nowait(path)

    pipeline = ManagerEnrichmentPipeline(model_name=GEMINI_MODEL)
    
    # Start workers
    num_workers = min(CONCURRENCY_LIMIT, len(to_enrich))
    workers = [asyncio.create_task(worker(queue, pipeline, args.get_picture, args.search_picture_li)) for _ in range(num_workers)]
    
    # Wait for completion or fatal error
    if workers:
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
