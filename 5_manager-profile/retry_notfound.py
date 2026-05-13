import os
import json
import asyncio
from pipeline import ManagerEnrichmentPipeline
from dotenv import load_dotenv, find_dotenv

load_dotenv(os.path.join("..", ".env"))
load_dotenv(find_dotenv(), override=True)

# Configuration
CONCURRENCY_LIMIT = int(os.getenv("CONCURRENCY_LIMIT", "5"))
GEMINI_MODEL = os.getenv("GEMINI_MODEL")
if not GEMINI_MODEL:
    raise ValueError("GEMINI_MODEL environment variable is not set in .env")

async def worker(queue, pipeline):
    while not queue.empty():
        profile_path = await queue.get()
        print(f"Retry: [START] {os.path.basename(os.path.dirname(profile_path))}")
        try:
            await pipeline.run(profile_path)
            print(f"Retry: [DONE] {os.path.basename(os.path.dirname(profile_path))}")
        except Exception as e:
            print(f"Retry: [ERROR] {profile_path}: {e}")
        queue.task_done()

async def main():
    managers_dir = os.path.join("..", "Managers")
    to_retry = []

    print("Scanning for profiles with 'not_found' status to retry...")
    for root, dirs, files in os.walk(managers_dir):
        if "Profile.json" in files:
            path = os.path.join(root, "Profile.json")
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                status = data.get("enrichment_status")
                if status == "not_found":
                    to_retry.append(path)
            except Exception:
                continue

    if not to_retry:
        print("No profiles found with 'not_found' status.")
        return

    # Use PROFILES_TO_ENRICH parameter
    profiles_to_enrich = int(os.getenv("PROFILES_TO_ENRICH", "0"))
    if profiles_to_enrich > 0:
        to_retry = to_retry[:profiles_to_enrich]
        print(f"Retry: Retrying next {len(to_retry)} profiles.")
    else:
        print(f"Retry: Retrying all {len(to_retry)} profiles.")
    
    queue = asyncio.Queue()
    for path in to_retry:
        queue.put_nowait(path)

    pipeline = ManagerEnrichmentPipeline(model_name=GEMINI_MODEL)
    workers = [asyncio.create_task(worker(queue, pipeline)) for _ in range(CONCURRENCY_LIMIT)]
    await asyncio.gather(*workers)
    print("Retry processing finished.")

if __name__ == "__main__":
    asyncio.run(main())
