import os
import json
import asyncio
import argparse
import tools
from dotenv import load_dotenv, find_dotenv

load_dotenv(os.path.join("..", ".env"))
load_dotenv(find_dotenv(), override=True)

# Configuration
CONCURRENCY_LIMIT = int(os.getenv("CONCURRENCY_LIMIT", "5"))
PROFILES_TO_ENRICH = int(os.getenv("PROFILES_TO_ENRICH", "0"))

async def download_picture_for_profile(profile_path: str):
    try:
        with open(profile_path, 'r', encoding='utf-8') as f:
            profile = json.load(f)
            
        full_name = profile['name']
        socials = profile.get('socials', [])
        
        # 1. Determine primary LinkedIn URL
        linkedin_url = next((s['url'] for s in socials if 'linkedin.com' in s['url'].lower()), None)
        
        # 2. Increment download attempt count
        profile['picture_download_count'] = profile.get('picture_download_count', 0) + 1
        
        # 3. Try to get picture URL
        picture_url = None
        
        # Try scraping LinkedIn first
        if linkedin_url:
            print(f"Phase 3b: Scraping LinkedIn for {full_name}...")
            picture_url = tools.scrape_linkedin_picture(linkedin_url)
            
            # POC: Direct Download of Captured URL if scrape failed/blocked
            potential_url = next((s.get('potential_picture_url') for s in socials if s['url'] == linkedin_url), None)
            
            # If Phase 3 scrape failed/blocked but Phase 2a capture existed
            is_placeholder = picture_url and any(p in picture_url.lower() for p in ['ghost_person', 'default_profile', '1c5u578iilxfi4m4dvc4q810q'])
            
            if (not picture_url or picture_url == "BLOCKED" or is_placeholder) and potential_url:
                print(f"Phase 3b: Direct LinkedIn scrape failed for {full_name}. Attempting direct download of captured URL...")
                
                # Try downloading the captured potential_url directly
                manager_dir = os.path.dirname(profile_path)
                local_filename = tools.download_image(potential_url, manager_dir)
                
                if local_filename:
                    picture_url = potential_url
                    print(f"Phase 3b: Successfully downloaded captured URL for {full_name}")
                else:
                    print(f"Phase 3b: Direct download failed for captured URL.")
            
        if picture_url and picture_url != "BLOCKED":
            print(f"Phase 3b: Found valid picture URL for {full_name}: {picture_url[:60]}...")
            profile['picture_url'] = picture_url
            
            # 4. Download image (if not already downloaded above)
            manager_dir = os.path.dirname(profile_path)
            local_filename = tools.download_image(picture_url, manager_dir)
            
            if local_filename:
                profile['picture_local'] = local_filename
                # Remove download count on success from top level and nested socials
                profile.pop('picture_download_count', None)
                for s in profile.get('socials', []):
                    s.pop('picture_download_count', None)
                print(f"Phase 3b: Successfully downloaded picture for {full_name}")
            else:
                pass
        else:
            print(f"Phase 3b: No picture found for {full_name}")
            
        # Save updated profile
        with open(profile_path, 'w', encoding='utf-8') as f:
            json.dump(profile, f, indent=2)
            
    except Exception as e:
        print(f"Phase 3b: Error processing {profile_path}: {e}")

async def worker(queue):
    while not queue.empty():
        profile_path = await queue.get()
        print(f"Phase 3b: [START] {os.path.basename(os.path.dirname(profile_path))}")
        await download_picture_for_profile(profile_path)
        print(f"Phase 3b: [DONE] {os.path.basename(os.path.dirname(profile_path))}")
        queue.task_done()

async def main():
    print("\n" + "!"*60)
    print("!!! PHASE 3B NEEDS MORE WORK - DO NOT RUN !!!")
    print("!"*60 + "\n")
    
    # Still update logic as requested, even though we shouldn't run it
    parser = argparse.ArgumentParser(description="Phase 3b: Profile picture download (experimental).")
    parser.add_argument("--retry_failed", type=str, default="no", choices=["yes", "no"], help="Retry profiles with picture_download_count > 0")
    args = parser.parse_args()

    managers_dir = os.path.join("..", "Managers")
    to_process = []

    print(f"Phase 3b: Scanning for profiles needing picture downloads (retry_failed={args.retry_failed})...")
    for root, dirs, files in os.walk(managers_dir):
        if "Profile.json" in files:
            path = os.path.join(root, "Profile.json")
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                picture_local = data.get("picture_local")
                status = data.get("enrichment_socials")
                socials = data.get("socials", [])
                has_linkedin = any('linkedin.com' in s['url'].lower() for s in socials)
                download_count = data.get("picture_download_count", 0)
                
                # Check if file actually exists if picture_local is set
                file_exists = False
                if picture_local:
                    file_exists = os.path.exists(os.path.join(root, picture_local))

                is_eligible = False
                if status == "success" and has_linkedin:
                    if not picture_local or not file_exists:
                        if args.retry_failed == "yes" or download_count <= 0:
                            is_eligible = True

                if is_eligible:
                    to_process.append(path)
            except Exception:
                continue

    if not to_process:
        print("No profiles found needing picture downloads.")
        return

    # Use PROFILES_TO_ENRICH parameter from environment, defaulting to 0
    profiles_to_enrich = int(os.environ.get("PROFILES_TO_ENRICH", "0"))
    
    if profiles_to_enrich > 0:
        to_process = to_process[:profiles_to_enrich]
        print(f"Phase 3b: Processing next {len(to_enrich)} profiles.")
    else:
        print(f"Phase 3b: Processing all {len(to_process)} profiles.")
    
    queue = asyncio.Queue()
    for path in to_process:
        queue.put_nowait(path)

    workers = [asyncio.create_task(worker(queue)) for _ in range(CONCURRENCY_LIMIT)]
    await asyncio.gather(*workers)
    print("Phase 3b processing finished.")

if __name__ == "__main__":
    asyncio.run(main())
