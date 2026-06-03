import os
import json
import argparse
import time
import tools
from cloakbrowser import launch
from dotenv import load_dotenv, find_dotenv
from groq import Groq
from google import genai

load_dotenv(os.path.join("..", ".env"))
load_dotenv(find_dotenv(), override=True)

# Helper to get LLM client and Verifier Agent
def get_verifier_agent():
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    model = os.getenv("GEMINI_MODEL") if provider == "gemini" else os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    
    if provider == "gemini":
        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    else:
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    
    return tools.LinkedInVerifierAgent(client, model, "LinkedIn Verifier Agent. Return a JSON object.", provider=provider)

def process_reprocess(page, profile_path, verifier_agent):
    print(f"  -> Reprocessing {profile_path}...")
    try:
        with open(profile_path, 'r', encoding='utf-8') as f:
            profile = json.load(f)
        
        manager_name = profile['name']
        affiliations = [c['name'] for c in profile.get('company_affiliations', [])]
        
        # 1. Search for new URL
        search_results = tools.search_social_media(manager_name, affiliations)
        li_urls = [r['url'] for r in search_results if r['type'] == 'social_profile' and 'linkedin.com' in r['url']]
        
        if not li_urls:
            print(f"  -> No new LinkedIn profiles found for {manager_name}.")
            return 0
            
        # 2. Validate with Verifier Agent then download picture
        manager_dir = os.path.dirname(profile_path)
        for url in li_urls:
            print(f"  -> Verifying identity for {url}...")
            
            # Identity Verification using shared LLM agent
            v_res = verifier_agent.verify(profile, url)
            if not v_res.is_verified:
                print(f"  -> Identity mismatch. Skipping.")
                continue

            print(f"  -> Verified. Scraping...")
            matching_social = next((s for s in profile.get('socials', []) if s.get('url') == url), None)
            filename = tools.get_linkedin_profile_picture(page, profile_path, url, matching_social)
            
            if filename:
                profile['picture_local'] = filename
                profile['enrichment_socials'] = 'success'
                if not matching_social:
                    profile['socials'].append({"name": "LinkedIn", "url": url})
                
                with open(profile_path, 'w', encoding='utf-8') as f:
                    json.dump(profile, f, indent=2)
                print(f"  -> Success: Profile updated for {manager_name}")
                return 1
        
        print(f"  -> Failed to find valid profile for {manager_name}.")
        return 1
    except Exception as e:
        print(f"  -> Error: {e}")
        return 0

def main():
    parser = argparse.ArgumentParser(description="Phase 4: Reprocess profiles marked as 'not_found'.")
    parser.add_argument("--has_profile", type=str, default="yes", choices=["yes", "no"], help="Target based on enrichment_socials (no) or profile_status (yes)")
    parser.add_argument("--linkedin_user", type=str, required=True, help="LinkedIn user for session-authenticated scraping")
    args = parser.parse_args()

    verifier_agent = get_verifier_agent()
    
    managers_dir = os.path.join("..", "Managers")
    to_process = []
    
    # Scanning logic
    for root, dirs, files in os.walk(managers_dir):
        if "Profile.json" in files:
            path = os.path.join(root, "Profile.json")
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if args.has_profile == "no":
                if data.get("enrichment_socials") == "not_found":
                    to_process.append(path)
            else:
                socials = data.get("socials", [])
                if any(s.get("profile_status") == "not_found" for s in socials):
                    to_process.append(path)
    
    print(f"Reprocessing {len(to_process)} profiles...")
    
    # Load mimicry parameters
    delay_min = int(os.getenv("DELAY_MIN", 5))
    delay_max = int(os.getenv("DELAY_MAX", 15))
    max_pages_per_hour = int(os.getenv("MAX_PAGES_PER_HOUR", 30))
    
    # Determine path for the user data directory
    session_dir = os.path.join(os.path.dirname(__file__), "sessions", args.linkedin_user)
    os.makedirs(session_dir, exist_ok=True)
    # Use launch_persistent_context for persistent sessions
    from cloakbrowser import launch_persistent_context
    context = launch_persistent_context(user_data_dir=session_dir, headless=False)
    page = context.new_page()
    
    pages_visited = 0
    hour_start_time = time.time()
    for i, path in enumerate(to_process):
        hour_start_time = tools.apply_human_mimicry(i, pages_visited, hour_start_time, 
                                                    delay_min=delay_min, 
                                                    delay_max=delay_max, 
                                                    max_pages_per_hour=max_pages_per_hour)
        pages_visited += process_reprocess(page, path, verifier_agent)
        
    context.close()

if __name__ == '__main__':
    main()
