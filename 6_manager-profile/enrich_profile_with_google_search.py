import os
import json
import asyncio
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from google import genai
from google.genai import types
from dotenv import load_dotenv, find_dotenv

load_dotenv(os.path.join("..", ".env"))
load_dotenv(find_dotenv(), override=True)

# Configuration
CONCURRENCY_LIMIT = 1 # Strictly limited for Google Search grounding to avoid 429s
# Use specialized grounding model if specified
GEMINI_MODEL = os.getenv("GEMINI_MODEL_SEARCH_GROUNDING") or os.getenv("GEMINI_MODEL")
if not GEMINI_MODEL:
    raise ValueError("Neither GEMINI_MODEL_SEARCH_GROUNDING nor GEMINI_MODEL is set in .env")
PROFILES_TO_ENRICH = int(os.getenv("PROFILES_TO_ENRICH", "0"))

class SocialProfile(BaseModel):
    name: str
    url: str
    potential_picture_url: Optional[str] = None

class ValidationResult(BaseModel):
    validated_profiles: List[SocialProfile]

class GoogleSearchEnrichmentPipeline:
    def __init__(self, model_name: str = GEMINI_MODEL):
        self.model_name = model_name
        # Use specialized API key for grounding if specified
        api_key = os.getenv("GOOGLE_API_KEY_SEARCH_GROUNDING", os.getenv("GOOGLE_API_KEY"))
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is not set")
        
        self.client = genai.Client(api_key=api_key)
        
        self.system_instruction = (
            "You are a Digital Profile Investigator. Your task is to validate the LinkedIn profile that matches a specific company manager and extract their profile picture.\n"
            "PROTOCOL:\n"
            "1. You are provided with a manager's name, their affiliated companies, and roles, and their LinkedIn URL.\n"
            "2. Use your search tool to visit the provided LinkedIn profile and confirm it belongs to the manager (based on company/role data).\n"
            "3. Validation Criteria:\n"
            "   - The profile content explicitly confirms the person works (or worked) at the target companies or in the listed roles.\n"
            "   - OR the person's name is extremely unique AND the industry/context matches perfectly.\n"
            "4. Image Capture: If the profile is a correct match:\n"
            "   - Search for image URLs in the page source (e.g. within 'src' or 'srcset' attributes) that follow this pattern:\n"
            "     - Start with: https://media.licdn.com/dms/image/v2/\n"
            "     - Contain: 'profile-displayphoto-shrink_'\n"
            "   - Capture the 200x200 resolution version (containing 'shrink_200_200') as the highest priority.\n"
            "   - If 'shrink_200_200' is not available, capture the next available resolution (100_100, 400_400, 800_800).\n"            
            "   - Capture  the COMPLETE, UNTRUNCATED URL, do not omit any parameters (e.g., ?e=, &v=, &t=). as 'potential_picture_url'.\n"
            "5. Selection:\n"
            "   - Only select the profile if it explicitly mentions at least one of the provided company affiliations or relevant roles.\n"
            "6. Return a JSON list of validated profiles. If no high-confidence match exists, return an empty list.\n\n"
            "CRITICAL: Precision is more important than recall. Discard any profile that is likely a different person with the same name."
        )

    async def run(self, profile_path: str):
        try:
            # Add a small delay to avoid hitting RPM burst limits
            await asyncio.sleep(5)
            
            with open(profile_path, 'r', encoding='utf-8') as f:
                profile = json.load(f)
            
            full_name = profile['name']
            affiliations = [c['name'] for c in profile.get('companies', [])]
            roles = [c['title_or_role'] for c in profile.get('companies', [])]
            linkedin_url = next((s['url'] for s in profile.get('socials', []) if 'linkedin.com' in s['url'].lower()), None)
            
            if not linkedin_url:
                print(f"Phase 2a: Skipping {full_name} (No LinkedIn URL found).")
                return
            
            print(f"Phase 2a: Investigating LinkedIn for {full_name} via Google Search Grounding...")
            
            prompt = (
                f"Manager: {full_name}\n"
                f"Companies: {', '.join(affiliations)}\n"
                f"Roles: {', '.join(roles)}\n"
                f"LinkedIn URL: {linkedin_url}\n\n"
                "Task: Verify this LinkedIn profile matches the manager. If it matches, extract the 'shrink_200_200' profile display photo URL "
                "(look for media.licdn.com/dms/image/v2/ containing 'profile-displayphoto-shrink_200_200')."
            )

            # Define the search tool
            google_search_tool = types.Tool(
                google_search=types.GoogleSearch()
            )

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    tools=[google_search_tool],
                    response_mime_type="application/json",
                    response_schema=ValidationResult
                )
            )
            
            validation_data = response.parsed
            print(f"Phase 2a: Agent returned {len(validation_data.validated_profiles)} validated profiles.")
            if validation_data.validated_profiles:
                vp = validation_data.validated_profiles[0]
                print(f"Phase 2a: Validated Profile: {vp.name} - {vp.url}")
                # Update the profile with the new potential_picture_url
                new_pic = vp.potential_picture_url
                if new_pic:
                    print(f"Phase 2a: Captured photo for {full_name}: {new_pic[:60]}...")
                    # Update specific LinkedIn entry in socials
                    for s in profile['socials']:
                        if s['url'] == linkedin_url:
                            s['potential_picture_url'] = new_pic
                    
                    with open(profile_path, 'w', encoding='utf-8') as f:
                        json.dump(profile, f, indent=2)
                else:
                    print(f"Phase 2a: Profile validated for {full_name}, but no photo found.")
            else:
                print(f"Phase 2a: Could not validate or find photo for {full_name}.")

        except Exception as e:
            print(f"Phase 2a Error for {profile_path}: {e}")

async def worker(queue, pipeline):
    while not queue.empty():
        path = await queue.get()
        await pipeline.run(path)
        queue.task_done()

import argparse

async def main():
    parser = argparse.ArgumentParser(description="Enrich manager profiles with LinkedIn display photos using Google Search grounding.")
    parser.add_argument("--manager", type=str, help="Specific manager name to process (e.g. 'Aaron Jagdfeld')")
    args = parser.parse_args()

    managers_dir = os.path.join("..", "Managers")
    to_enrich = []
    
    if args.manager:
        print(f"Targeted search for manager: {args.manager}")
        # Search for specific manager folder
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
            print(f"Manager '{args.manager}' not found.")
            return
    else:
        print("Scanning for profiles with LinkedIn to enrich via Google Search...")
        for root, dirs, files in os.walk(managers_dir):
            if "Profile.json" in files:
                path = os.path.join(root, "Profile.json")
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # Targets: Has success status (socials found) but no potential_picture_url captured yet
                    has_linkedin = any('linkedin.com' in s['url'].lower() for s in data.get('socials', []))
                    has_potential = any(s.get('potential_picture_url') for s in data.get('socials', []))
                    
                    if data.get("enrichment_status") == "success" and has_linkedin and not has_potential:
                        to_enrich.append(path)
                except Exception:
                    continue

    if not to_enrich:
        print("No eligible profiles found.")
        return

    # Skip batching if a specific manager was requested
    if not args.manager and PROFILES_TO_ENRICH > 0:
        to_enrich = to_enrich[:PROFILES_TO_ENRICH]
        print(f"Phase 2a: Enriching next {len(to_enrich)} profiles.")
    else:
        print(f"Phase 2a: Processing {len(to_enrich)} profiles.")

    queue = asyncio.Queue()
    for path in to_enrich:
        queue.put_nowait(path)

    pipeline = GoogleSearchEnrichmentPipeline()
    workers = [asyncio.create_task(worker(queue, pipeline)) for _ in range(CONCURRENCY_LIMIT)]
    await asyncio.gather(*workers)
    print("Phase 2a finished.")

if __name__ == "__main__":
    asyncio.run(main())
