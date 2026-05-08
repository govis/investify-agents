import os
import json
import asyncio
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
        affiliations = [c['name'] for c in profile.get('companies', [])]
        socials = profile.get('socials', [])
        
        # 1. Determine primary LinkedIn URL
        linkedin_url = next((s['url'] for s in socials if 'linkedin.com' in s['url'].lower()), None)
        
        # 2. Increment download attempt count
        profile['picture_download_count'] = profile.get('picture_download_count', 0) + 1
        
        # 3. Try to get picture URL
        picture_url = None
        
        # Try scraping LinkedIn first
        if linkedin_url:
            print(f"Phase 3: Scraping LinkedIn for {full_name}...")
            picture_url = tools.scrape_linkedin_picture(linkedin_url)
            
            # POC: Direct Download of Captured URL if scrape failed/blocked
            potential_url = next((s.get('potential_picture_url') for s in socials if s['url'] == linkedin_url), None)
            
            # If Phase 3 scrape failed/blocked but Phase 2a capture existed
            is_placeholder = picture_url and any(p in picture_url.lower() for p in ['ghost_person', 'default_profile', '1c5u578iilxfi4m4dvc4q810q'])
            
            if (not picture_url or picture_url == "BLOCKED" or is_placeholder) and potential_url:
                print(f"Phase 3: Direct LinkedIn scrape failed for {full_name}. Attempting direct download of captured URL...")
                
                # Try downloading the captured potential_url directly
                manager_dir = os.path.dirname(profile_path)
                local_filename = tools.download_image(potential_url, manager_dir)
                
                if local_filename:
                    picture_url = potential_url
                    print(f"Phase 3: Successfully downloaded captured URL for {full_name}")
                else:
                    print(f"Phase 3: Direct download failed for captured URL.")
            
        if picture_url and picture_url != "BLOCKED":
            print(f"Phase 3: Found valid picture URL for {full_name}: {picture_url[:60]}...")
            profile['picture_url'] = picture_url
            
            # 4. Download image (if not already downloaded above)
            manager_dir = os.path.dirname(profile_path)
            local_filename = tools.download_image(picture_url, manager_dir)
            
            if local_filename:
                profile['picture_local'] = local_filename
                profile['has_picture'] = "true"
                print(f"Phase 3: Successfully downloaded picture for {full_name}")
            else:
                profile['has_picture'] = "false"
        else:
            profile['has_picture'] = "false"
            print(f"Phase 3: No picture found for {full_name}")
            
        # Save updated profile
        with open(profile_path, 'w', encoding='utf-8') as f:
            json.dump(profile, f, indent=2)
            
    except Exception as e:
        print(f"Phase 3: Error processing {profile_path}: {e}")

async def worker(queue):
    while not queue.empty():
        profile_path = await queue.get()
        print(f"Phase 3: [START] {os.path.basename(os.path.dirname(profile_path))}")
        await download_picture_for_profile(profile_path)
        print(f"Phase 3: [DONE] {os.path.basename(os.path.dirname(profile_path))}")
        queue.task_done()

async def main():
    managers_dir = os.path.join("..", "Managers")
    to_process = []

    print("Scanning for profiles that need pictures...")
    for root, dirs, files in os.walk(managers_dir):
        if "Profile.json" in files:
            path = os.path.join(root, "Profile.json")
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                picture_local = data.get("picture_local")
                status = data.get("enrichment_status")
                is_placeholder = False
                
                # Check if local picture is a known placeholder
                if picture_local:
                    local_path = os.path.join(root, picture_local)
                    if os.path.exists(local_path):
                        # Check first few bytes for SVG header
                        with open(local_path, 'r', encoding='utf-8', errors='ignore') as img_f:
                            head = img_f.read(100)
                            if '<svg' in head.lower():
                                is_placeholder = True

                # Eligibility: Has success status, but no local picture or it's a placeholder
                if status == "success" and (not picture_local or is_placeholder):
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
        print(f"Phase 3: Processing next {len(to_process)} profiles.")
    else:
        print(f"Phase 3: Processing all {len(to_process)} profiles.")
    
    queue = asyncio.Queue()
    for path in to_process:
        queue.put_nowait(path)

    workers = [asyncio.create_task(worker(queue)) for _ in range(CONCURRENCY_LIMIT)]
    await asyncio.gather(*workers)
    print("Phase 3 processing finished.")

if __name__ == "__main__":
    asyncio.run(main())
