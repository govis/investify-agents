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
            
            # Increment attempt count
            profile['picture_download_count'] = profile.get('picture_download_count', 0) + 1
            if matching_social:
                matching_social['picture_download_count'] = matching_social.get('picture_download_count', 0) + 1
                # Save immediately to ensure tracking persists
                with open(profile_path, 'w', encoding='utf-8') as f:
                    json.dump(profile, f, indent=2)

            print(f"  -> Navigating to {linkedin_url}...")
            
            # Unified scraping and downloading
            filename = tools.get_linkedin_profile_picture(page, profile_path, linkedin_url, matching_social)
            pages_visited += 1
            
            # Save status and count after visit attempt
            with open(profile_path, 'w', encoding='utf-8') as f:
                json.dump(profile, f, indent=2)
            
            if filename:
                profile['picture_local'] = filename
                # Reset download count on success
                profile['picture_download_count'] = 0
                if matching_social:
                    matching_social['picture_download_count'] = 0
                
                print(f"  -> Successfully updated picture metadata from {linkedin_url}.")
                # Save final success state
                with open(profile_path, 'w', encoding='utf-8') as f:
                    json.dump(profile, f, indent=2)
                break
            
    except Exception as e:
        print(f"  -> Error reading/processing profile {profile_path}: {e}")
    
    return pages_visited

def main():
    parser = argparse.ArgumentParser(description="Phase 3a: LinkedIn profile picture scraper.")
    parser.add_argument("--retry_failed", type=str, default="no", choices=["yes", "no"], help="Retry profiles with picture_download_count > 0 and not_found status")
    parser.add_argument("--scrape_method", type=str, default="simple", choices=["simple", "cloak_browser"], help="Scrape method (simple uses current, cloak_browser uses Cloak browser)")
    parser.add_argument("--linkedin_user", type=str, default="anonymous", help="LinkedIn user for login (cloak_browser only)")
    parser.add_argument("--profile_visibility", type=str, default="public", choices=["public", "private", "all"], help="Filter by profile visibility")
    parser.add_argument("--manager", type=str, help="Specific manager name to process")
    args = parser.parse_args()

    # Load human mimicry parameters from environment
    delay_min = int(os.getenv("DELAY_MIN", 5))
    delay_max = int(os.getenv("DELAY_MAX", 15))
    max_pages_per_hour = int(os.getenv("MAX_PAGES_PER_HOUR", 30))

    if args.linkedin_user != "anonymous" and args.scrape_method != "cloak_browser":
        print("Warning: --linkedin_user is only supported when --scrape_method is cloak_browser. Proceeding as anonymous.")
        args.linkedin_user = "anonymous"

    managers_dir = os.path.join("..", "Managers")
    to_process = []

    print(f"Phase 3a: Scanning for profiles needing LinkedIn scraping (retry_failed={args.retry_failed}, visibility={args.profile_visibility})...")
    for root, dirs, files in os.walk(managers_dir):
        if "Profile.json" in files:
            # If a manager is specified, skip unrelated folders
            if args.manager and args.manager not in root:
                continue

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
    
    # Initialize context variable properly
    context = None
    if args.scrape_method == "cloak_browser":
        session_dir = os.path.join(os.path.dirname(__file__), "sessions", args.linkedin_user)
        os.makedirs(session_dir, exist_ok=True)
        from cloakbrowser import launch_persistent_context
        context = launch_persistent_context(user_data_dir=session_dir, headless=True)
        page = context.new_page()
    else:
        from cloakbrowser import launch
        browser = launch()
        page = browser.new_page()
    
    pages_visited_this_hour = 0
    hour_start_time = time.time()
    
    for i, path in enumerate(to_process):
        # Human mimicry
        if args.linkedin_user != "anonymous":
            hour_start_time = tools.apply_human_mimicry(i, pages_visited_this_hour, hour_start_time, 
                                                        delay_min=delay_min, 
                                                        delay_max=delay_max, 
                                                        max_pages_per_hour=max_pages_per_hour)

        print(f"[{i+1}/{len(to_process)}] Processing {os.path.basename(os.path.dirname(path))}...")
        visited = process_profile(page, path, args.scrape_method, args.linkedin_user)
        pages_visited_this_hour += visited
        
    print("Phase 3a: Finished processing all profiles.")
    if context:
        context.close()
    else:
        browser.close()

if __name__ == '__main__':
    main()
