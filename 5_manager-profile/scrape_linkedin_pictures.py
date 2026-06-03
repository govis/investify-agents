import os
import json
import time
import requests
import urllib.parse
import base64
import argparse
import random
import tools
from cloakbrowser import launch
from dotenv import load_dotenv, find_dotenv

load_dotenv(os.path.join("..", ".env"))
load_dotenv(find_dotenv(), override=True)

# Configuration
PROFILES_TO_PROCESS = int(os.getenv("PROFILES_TO_ENRICH", "0"))

def process_profile(page, profile_path, scrape_method="simple", linkedin_user="anonymous"):
    pages_visited = 0
    try:
        with open(profile_path, 'r', encoding='utf-8') as f:
            profile = json.load(f)
            
        full_name = profile['name']
        socials = profile.get('socials', [])
        
        # Collect all LinkedIn URLs
        linkedin_urls = []
        for s in socials:
            if 'linkedin.com' in s.get('url', '').lower():
                linkedin_urls.append(s['url'])
        
        if not linkedin_urls:
            return 0

        blacklist = tools.get_blacklist()
        
        for linkedin_url in linkedin_urls:
            if linkedin_url.lower().rstrip('/') in blacklist:
                continue

            matching_social = next((s for s in profile.get('socials', []) if s.get('url') == linkedin_url), None)
            
            print(f"  -> Navigating to {linkedin_url}...")
            
            # Unified scraping and downloading
            filename = tools.get_linkedin_profile_picture(page, profile_path, linkedin_url, matching_social)
            pages_visited += 1
            
            if filename:
                profile['picture_local'] = filename
                # Reset download count
                profile['picture_download_count'] = 0
                if matching_social:
                    matching_social['picture_download_count'] = 0
                
                print(f"  -> Successfully updated picture metadata from {linkedin_url}.")
                break
        
        with open(profile_path, 'w', encoding='utf-8') as f:
            json.dump(profile, f, indent=2)
            
    except Exception as e:
        print(f"  -> Error reading/processing profile {profile_path}: {e}")
    
    return pages_visited

def main():
    parser = argparse.ArgumentParser(description="Phase 3a: LinkedIn profile picture scraper.")
    parser.add_argument("--retry_failed", type=str, default="no", choices=["yes", "no"], help="Retry profiles with picture_download_count > 0 and not_found status")
    parser.add_argument("--scrape_method", type=str, default="simple", choices=["simple", "cloak_browser"], help="Scrape method (simple uses current, cloak_browser uses Cloak browser)")
    parser.add_argument("--linkedin_user", type=str, default="anonymous", help="LinkedIn user for login (cloak_browser only)")
    parser.add_argument("--profile_visibility", type=str, default="public", choices=["public", "private", "all"], help="Filter by profile visibility")
    parser.add_argument("--delay_min", type=int, default=5, help="Min delay between profiles in seconds (human mimicry)")
    parser.add_argument("--delay_max", type=int, default=15, help="Max delay between profiles in seconds (human mimicry)")
    parser.add_argument("--max_pages_per_hour", type=int, default=30, help="Max pages per hour (human mimicry)")
    args = parser.parse_args()

    if args.linkedin_user != "anonymous" and args.scrape_method != "cloak_browser":
        print("Warning: --linkedin_user is only supported when --scrape_method is cloak_browser. Proceeding as anonymous.")
        args.linkedin_user = "anonymous"

    managers_dir = os.path.join("..", "Managers")
    to_process = []

    print(f"Phase 3a: Scanning for profiles needing LinkedIn scraping (retry_failed={args.retry_failed}, visibility={args.profile_visibility})...")
    for root, dirs, files in os.walk(managers_dir):
        if "Profile.json" in files:
            path = os.path.join(root, "Profile.json")
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                picture_local = data.get("picture_local")
                status = data.get("enrichment_socials")
                socials = data.get("socials", [])
                
                # Check if file actually exists if picture_local is set
                file_exists = False
                if picture_local:
                    file_exists = os.path.exists(os.path.join(root, picture_local))

                if status == "success":
                    li_socials = [s for s in socials if 'linkedin.com' in s['url'].lower()]
                    if not li_socials: continue
                    
                    if not picture_local or not file_exists:
                        # Visibility check
                        is_private = any(s.get('profile_status') == 'private' for s in li_socials)
                        is_not_found = all(s.get('profile_status') == 'not_found' for s in li_socials)
                        
                        visibility_match = False
                        if args.profile_visibility == "all":
                            visibility_match = True
                        elif args.profile_visibility == "public":
                            visibility_match = not is_private
                        elif args.profile_visibility == "private":
                            visibility_match = is_private
                        
                        if visibility_match:
                            download_count = data.get("picture_download_count", 0)
                            if args.retry_failed == "yes":
                                is_eligible = True
                            else:
                                is_eligible = (download_count <= 0 and not is_not_found)
                            
                            if is_eligible:
                                to_process.append(path)
            except Exception:
                continue

    if not to_process:
        print("No profiles found needing LinkedIn scraping.")
        return

    profiles_to_process = PROFILES_TO_PROCESS
    if profiles_to_process > 0:
        to_process = to_process[:profiles_to_process]
    
    print(f"Phase 3a: Processing {len(to_process)} profiles.")
    
    print(f"Launching Browser (method={args.scrape_method})...")
    if args.scrape_method == "cloak_browser" and args.linkedin_user != "anonymous":
        browser = launch(user=args.linkedin_user)
    else:
        browser = launch()
        
    page = browser.new_page()
    
    pages_visited_this_hour = 0
    hour_start_time = time.time()
    
    for i, path in enumerate(to_process):
        # Human mimicry
        if args.linkedin_user != "anonymous":
            if pages_visited_this_hour >= args.max_pages_per_hour:
                elapsed = time.time() - hour_start_time
                if elapsed < 3600:
                    wait_time = 3600 - elapsed
                    print(f"Hourly limit reached ({args.max_pages_per_hour}). Waiting {wait_time/60:.1f} minutes...")
                    time.sleep(wait_time)
                pages_visited_this_hour = 0
                hour_start_time = time.time()
            
            if i > 0:
                delay = random.uniform(args.delay_min, args.delay_max)
                print(f"Human mimicry: Waiting {delay:.1f}s...")
                time.sleep(delay)

        print(f"[{i+1}/{len(to_process)}] Processing {os.path.basename(os.path.dirname(path))}...")
        visited = process_profile(page, path, args.scrape_method, args.linkedin_user)
        pages_visited_this_hour += visited
        
    print("Phase 3a: Finished processing all profiles.")
    browser.close()

if __name__ == '__main__':
    main()
