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
print(f"DEBUG: PROFILES_TO_PROCESS is {PROFILES_TO_PROCESS}")
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
        company_data = await queue.get()
        ticker = company_data['ticker']
        exchange = company_data['exchange']
        profile_path = company_data['profile_path']
        
        print(f"Main2: [START] {ticker}.{exchange} (Enrichment)")
        try:
            # Run the pipeline in enrichment mode
            result, raw_result = await pipeline.run(company_data, is_enrichment=True)
            
            # Log the agent output (always do this if we got a response)
            log_path = os.path.join(os.path.dirname(profile_path), "Profile_Enrichment.log")
            if raw_result:
                with open(log_path, "w", encoding="utf-8") as log_file:
                    log_file.write(raw_result)

            if result:
                # Map specialized enrichment results to existing profile data
                with open(profile_path, "r", encoding="utf-8") as f:
                    final_profile = json.load(f)

                # Extract fields from result (could be pydantic model, dict, or string)
                if hasattr(result, 'model_dump'):
                    res_dict = result.model_dump()
                elif isinstance(result, dict):
                    res_dict = result
                else:
                    print(f"Main2: [ERROR] {ticker}.{exchange}: Result is not a dictionary or model. Check Profile_Enrichment.log.")
                    async with error_lock:
                        consecutive_errors += 1
                    continue

                # Update only the enriched fields
                final_profile['country_of_domicile'] = res_dict.get('country_of_domicile')
                final_profile['description'] = res_dict.get('description')
                final_profile['logo_url'] = res_dict.get('logo_url')
                final_profile['enrichment'] = "success"

                with open(profile_path, "w", encoding="utf-8") as f:
                    json.dump(final_profile, f, indent=2)
                print(f"Main2: [DONE] {ticker}.{exchange}")
                
            async with error_lock:
                consecutive_errors = 0
                
        except Exception as e:
            async with error_lock:
                consecutive_errors += 1
                current_errs = consecutive_errors
            print(f"Main2: [ERROR] {ticker}.{exchange}: {e}")
            if current_errs >= MAX_CONSECUTIVE_ERRORS:
                print("Main2: [FATAL] Max consecutive errors reached. Signaling stop.")
                stop_event.set()
        
        queue.task_done()

async def main():
    print(f"Workflow 2: Enrichment (Phase 2) starting with CONCURRENCY_LIMIT={CONCURRENCY_LIMIT}...")
    companies_dir = "../Companies"
    if not os.path.exists(companies_dir):
        print(f"Error: {companies_dir} not found.")
        return

    companies_to_process = []
    
    # Scan for Profile.json files that need enrichment
    for root, dirs, files in os.walk(companies_dir):
        if len(companies_to_process) >= PROFILES_TO_PROCESS:
            break
            
        if "Profile.json" in files:
            path = os.path.join(root, "Profile.json")
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                if data.get("origin") == "manager_affiliation" and data.get("enrichment") == "pending":
                    ticker = data.get("ticker", "")
                    orig_exchange = data.get("exchange", "")

                    # Skip if ticker has non-alphanumeric characters
                    if not ticker.isalnum():
                        continue

                    # Apply substitution to the exchange
                    new_exchange = exchange_subs.get(orig_exchange, orig_exchange)
                    data['exchange'] = new_exchange

                    # Filter by (possibly substituted) exchange if provided
                    if included_exchanges and new_exchange not in included_exchanges:
                        continue
                        
                    # Add path to data so worker knows where to save
                    data['profile_path'] = path
                    companies_to_process.append(data)
            except Exception as e:
                print(f"Main2: Error reading {path}: {e}")

    if not companies_to_process:
        print("Main2: No companies found for enrichment.")
        return

    print(f"Main2: Found {len(companies_to_process)} companies to enrich.")

    queue = asyncio.Queue()
    for company in companies_to_process:
        queue.put_nowait(company)

    pipeline = ProfilingPipeline()
    
    # Start workers
    workers = [asyncio.create_task(worker(queue, pipeline)) for _ in range(CONCURRENCY_LIMIT)]
    
    # Wait for completion or fatal error
    done, pending = await asyncio.wait(workers, return_when=asyncio.FIRST_COMPLETED)
    
    if stop_event.is_set():
        print("\nMain2: FATAL ERROR detected. Cancelling remaining workers.")
        for w in workers:
            if not w.done():
                w.cancel()
    
    await asyncio.gather(*workers, return_exceptions=True)
    print("Main2: Enrichment finished.")

if __name__ == "__main__":
    asyncio.run(main())
