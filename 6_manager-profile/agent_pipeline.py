import os
import json
import asyncio
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from dotenv import load_dotenv, find_dotenv
import tools
from data_utils import get_manager_data

load_dotenv(find_dotenv(), override=True)

# Configuration
GEMINI_MODEL = os.getenv("GEMINI_MODEL")
SEARCH_GROUNDING_MODEL = os.getenv("GEMINI_MODEL_SEARCH_GROUNDING") or GEMINI_MODEL

if not GEMINI_MODEL:
    raise ValueError("GEMINI_MODEL environment variable is not set in .env")

class SocialProfileCandidate(BaseModel):
    name: str = Field(description="The name of the social platform, e.g., LinkedIn")
    url: str = Field(description="The URL of the profile")
    match_confidence: float = Field(description="Confidence score from 0 to 1")
    reasoning: str = Field(description="Brief explanation of why this is a match")

class SearchAgentResult(BaseModel):
    candidates: List[SocialProfileCandidate]

class VerificationResult(BaseModel):
    is_verified: bool
    person_name: Optional[str] = None
    company_name: Optional[str] = None
    potential_picture_url: Optional[str] = None
    verification_reasoning: str

class ImageSearchResult(BaseModel):
    image_url: Optional[str] = None
    source_url: Optional[str] = None
    reasoning: str

class Agent:
    def __init__(self, client: genai.Client, model: str, system_instruction: str):
        self.client = client
        self.model = model
        self.system_instruction = system_instruction

    async def call(self, prompt: str, schema: Any, use_search: bool = False):
        config = types.GenerateContentConfig(
            system_instruction=self.system_instruction,
            response_mime_type="application/json",
            response_schema=schema,
        )
        if use_search:
            config.tools = [types.Tool(google_search=types.GoogleSearch())]
        
        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model=self.model,
            contents=prompt,
            config=config
        )
        return response.parsed

class Supervisor:
    def __init__(self, pipeline: 'ManagerEnrichmentPipelineV2'):
        self.pipeline = pipeline

    async def orchestrate(self, profile_path: str, get_picture: str = "no", search_picture_li: str = "no"):
        print(f"Supervisor: Starting enrichment for {os.path.basename(profile_path)}")
        manager = get_manager_data(profile_path)
        manager_dir = os.path.dirname(profile_path)
        blocklist = tools.get_blocklist()
        
        # Check if we already have a LinkedIn URL to verify
        existing_linkedin = next((s['url'] for s in manager.get('socials', []) if 'linkedin.com' in s['url'].lower()), None)
        
        best_verification = None
        best_candidate_url = None

        if existing_linkedin:
            if existing_linkedin.lower().rstrip('/') in blocklist:
                print(f"Supervisor: Existing URL {existing_linkedin} is in blocklist. Skipping.")
            else:
                print(f"Supervisor: Found existing LinkedIn URL {existing_linkedin}. Attempting verification...")
                v_res = await self.pipeline.agents['verifier'].verify(manager, existing_linkedin)
                if v_res and v_res.is_verified:
                    best_verification = v_res
                    best_candidate_url = existing_linkedin
                    print(f"Supervisor: Verified existing URL {existing_linkedin}")
                else:
                    reason = v_res.verification_reasoning if v_res else "No response"
                    print(f"Supervisor: Existing URL {existing_linkedin} not verified. Reasoning: {reason}")
        
        if not best_verification:
            # 1. Search for LinkedIn Profile
            print(f"Supervisor: Delegating to LinkedIn Search Agent...")
            search_res = await self.pipeline.agents['search'].search(manager)
            candidates = search_res.candidates if search_res else []
            
            # Filter candidates using blocklist
            original_count = len(candidates)
            candidates = [c for c in candidates if c.url.lower().rstrip('/') not in blocklist]
            if len(candidates) < original_count:
                print(f"Supervisor: Filtered out {original_count - len(candidates)} blocklisted candidates.")

            print(f"Supervisor: Found {len(candidates)} candidates: {[c.url for c in candidates]}")
            
            if not candidates:
                print("Supervisor: No candidates found.")
                await self.finalize(profile_path, "not_found")
                return

            # 2. Verify Candidates
            for candidate in sorted(candidates, key=lambda x: x.match_confidence, reverse=True):
                if candidate.match_confidence < 0.3: continue
                # Skip if it's the one we just failed to verify
                if existing_linkedin and candidate.url.rstrip('/') == existing_linkedin.rstrip('/'):
                    continue

                print(f"Supervisor: Verifying candidate {candidate.url}...")
                v_res = await self.pipeline.agents['verifier'].verify(manager, candidate.url)
                if v_res and v_res.is_verified:
                    best_verification = v_res
                    best_candidate_url = candidate.url
                    print(f"Supervisor: Verified {candidate.url}")
                    break
                else:
                    reason = v_res.verification_reasoning if v_res else "No response"
                    print(f"Supervisor: Candidate {candidate.url} not verified. Reasoning: {reason}")
        
        if not best_verification:
            print("Supervisor: No candidate verified.")
            await self.finalize(profile_path, "not_found")
            return

        # 3. Handle Images - Sequential Download Validation
        # Preserve existing values from the file if we don't find new ones
        existing_social = next((s for s in manager.get('socials', []) if 'linkedin.com' in s['url'].lower()), {})
        picture_url_li_profile = best_verification.potential_picture_url or existing_social.get('picture_url_li_profile')
        picture_url_li_search = existing_social.get('picture_url_li_search')
        final_pic_url = None
        
        # Try Profile Image first (Agent 3 results)
        if picture_url_li_profile and get_picture == "yes":
            print(f"Supervisor: Attempting to download profile image: {picture_url_li_profile[:60]}...")
            if tools.download_image(picture_url_li_profile, manager_dir):
                print("Supervisor: Successfully downloaded profile image.")
                final_pic_url = picture_url_li_profile
        
        # Execute LinkedIn Image Search (2a) ONLY if search_picture_li is "yes"
        if search_picture_li == "yes" and best_verification and best_verification.person_name and best_verification.company_name:
            print(f"Supervisor: Executing LinkedIn Image Search (2a) for {best_verification.person_name} {best_verification.company_name}...")
            res = await self.pipeline.agents['img_li'].search(best_verification.person_name, best_verification.company_name)
            if res and res.image_url:
                picture_url_li_search = res.image_url # Capture new search URL
                
                # Only try to download if we haven't succeeded with profile image yet and get_picture is yes
                if not final_pic_url and get_picture == "yes":
                    print(f"Supervisor: Attempting to download search image: {picture_url_li_search[:60]}...")
                    if tools.download_image(picture_url_li_search, manager_dir):
                        print("Supervisor: Successfully downloaded search image.")
                        final_pic_url = picture_url_li_search
        elif search_picture_li != "yes":
            print(f"Supervisor: Skipping LinkedIn Image Search (2a) (search_picture_li={search_picture_li})")

        # If still no image, proceed to alternative agents (2b, 2c) ONLY if get_picture is yes
        if not final_pic_url and get_picture == "yes":
            print("Supervisor: No LinkedIn pictures validated. Trying IR agents...")
            # 2b. IR Website Search
            print("Supervisor: Trying IR Website Search (2b)...")
            res = await self.pipeline.agents['img_ir'].search(manager)
            if res and res.image_url:
                print(f"Supervisor: Attempting to download IR website image: {res.image_url[:60]}...")
                if tools.download_image(res.image_url, manager_dir):
                    final_pic_url = res.image_url
            
            # 2c. Broad IR Search
            if not final_pic_url:
                print("Supervisor: Trying Broad IR Search (2c)...")
                res = await self.pipeline.agents['img_broad'].search(manager)
                if res and res.image_url:
                    print(f"Supervisor: Attempting to download broad search image: {res.image_url[:60]}...")
                    if tools.download_image(res.image_url, manager_dir):
                        final_pic_url = res.image_url
        elif not final_pic_url and get_picture != "yes":
            print(f"Supervisor: Skipping subsequent image download/search steps (get_picture={get_picture})")

        # Finalize
        social_entry = {
            "name": "LinkedIn",
            "url": best_candidate_url,
            "person_name": best_verification.person_name,
            "company_name": best_verification.company_name,
            "potential_picture_url": final_pic_url,
            "picture_url_li_profile": picture_url_li_profile,
            "picture_url_li_search": picture_url_li_search
        }
        await self.finalize(profile_path, "success", [social_entry])

    async def finalize(self, profile_path: str, status: str, new_socials: List[Dict] = None):
        with open(profile_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        data["enrichment_socials"] = status
        blocklist = tools.get_blocklist()
        
        existing_socials = data.get("socials", [])
        if new_socials:
            # Update or Add
            for ns in new_socials:
                found = False
                for i, es in enumerate(existing_socials):
                    if es.get('name') == ns.get('name'):
                        existing_socials[i] = ns
                        found = True
                        break
                if not found:
                    existing_socials.append(ns)
        
        # Filter all socials against blocklist
        data["socials"] = [s for s in existing_socials if s.get('url', '').lower().rstrip('/') not in blocklist]
            
        with open(profile_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        print(f"Supervisor: Finished with status {status}")

class LinkedInSearchAgent(Agent):
    async def search(self, manager: Dict[str, Any]) -> SearchAgentResult:
        affiliations = manager.get('company_affiliations', [])
        affiliations_str = ', '.join([f"{c['name']} ({c['name_clean']})" for c in affiliations])
        roles_str = ', '.join([c['title_or_role'] for c in affiliations])
        
        # Include background summary for better context (e.g. CEO of Calico)
        background = manager.get('background', '')
        
        prompt = (
            f"Manager: {manager['name']}\n"
            f"Background: {background}\n"
            f"Affiliations: {affiliations_str}\n"
            f"Roles: {roles_str}\n\n"
            "Task: Find the official personal LinkedIn profile for this individual.\n"
            "Search for their name along with their current company and role.\n"
            "Be aware that some roles might be recent or from their background (e.g. Calico CEO).\n"
            "Return only candidates that look like personal profiles (/in/ or /pub/)."
        )
        return await self.call(prompt, SearchAgentResult, use_search=True)

class LinkedInVerifierAgent(Agent):
    async def verify(self, manager: Dict[str, Any], url: str) -> VerificationResult:
        affiliations = [f"{c['name']} / {c['name_clean']}" for c in manager.get('company_affiliations', [])]
        background = manager.get('background', '')
        
        prompt = (
            f"Verify if this LinkedIn profile: {url}\n"
            f"Matches Manager: {manager['name']}\n"
            f"Background Bio: {background}\n"
            f"Target Affiliations: {', '.join(affiliations)}\n"
            f"Target Roles: {', '.join([c['title_or_role'] for c in manager.get('company_affiliations', [])])}\n\n"
            "CRITICAL RULES:\n"
            "1. REJECT if the URL is for a company (e.g., linkedin.com/company/...) or a school (e.g., linkedin.com/school/...). We only want PERSONAL profiles.\n"
            "2. PRIORITIZE affiliations mentioned in the Background Bio (e.g., CEO of Calico).\n"
            "3. If verified, capture:\n"
            "   - 'person_name': Name on the profile.\n"
            "   - 'company_name': The EXACT string used for the matching company on the profile.\n"
            "   - 'potential_picture_url': Profile picture URL (media.licdn.com pattern)."
        )
        return await self.call(prompt, VerificationResult, use_search=True)

class ImageSearchAgent2a(Agent):
    async def search(self, name: str, company: str) -> ImageSearchResult:
        prompt = (
            f"Perform an image search for: '{name} {company}'.\n"
            "Your goal is to find the professional LinkedIn profile picture for this person.\n"
            "1. Identify the top image search results.\n"
            "2. Look for the result that is explicitly from 'LinkedIn' or has a source URL from 'linkedin.com'.\n"
            "3. Capture the direct image URL (prefer media.licdn.com pattern).\n"
            "4. If you find a base64 encoded image (data:image/...) in the top LinkedIn results, you may return it if no direct URL is available.\n\n"
            "CRITICAL: Prioritize the image that matches the visual representation of a LinkedIn profile picture as seen in search results."
        )
        return await self.call(prompt, ImageSearchResult, use_search=True)

class ImageSearchAgent2b(Agent):
    async def search(self, manager: Dict[str, Any]) -> ImageSearchResult:
        affiliations = manager.get('company_affiliations', [])
        sites = [c['website'] for c in affiliations if c.get('website')]
        prompt = f"Find manager {manager['name']} picture on Investor Relations pages of: {', '.join(sites)}"
        return await self.call(prompt, ImageSearchResult, use_search=True)

class ImageSearchAgent2c(Agent):
    async def search(self, manager: Dict[str, Any]) -> ImageSearchResult:
        affiliations = [c['name'] for c in manager.get('company_affiliations', [])]
        prompt = f"Broad search for professional picture of {manager['name']} at {', '.join(affiliations)} on IR websites."
        return await self.call(prompt, ImageSearchResult, use_search=True)

class ManagerEnrichmentPipelineV2:
    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        self.client = genai.Client(api_key=api_key)
        self.agents = {
            'search': LinkedInSearchAgent(self.client, GEMINI_MODEL, "You are a LinkedIn Profile Search Agent. Find the best match profile."),
            'verifier': LinkedInVerifierAgent(self.client, SEARCH_GROUNDING_MODEL, "You are a LinkedIn Verifier Agent. Use search to visit the profile and verify it. Capture name, company and photo URL (v2 media.licdn.com pattern, prioritize shrink_200_200, then 100_100, 400_400, 800_800)."),
            'img_li': ImageSearchAgent2a(self.client, GEMINI_MODEL, "You are a LinkedIn Image Search Agent."),
            'img_ir': ImageSearchAgent2b(self.client, GEMINI_MODEL, "You are an IR Website Image Search Agent."),
            'img_broad': ImageSearchAgent2c(self.client, GEMINI_MODEL, "You are a Broad IR Search Agent.")
        }
        self.supervisor = Supervisor(self)

    async def run(self, profile_path: str, get_picture: str = "no", search_picture_li: str = "no"):
        try:
            await self.supervisor.orchestrate(profile_path, get_picture=get_picture, search_picture_li=search_picture_li)
            return {"success": True}
        except Exception as e:
            print(f"Pipeline Error: {e}")
            return {"success": False, "message": str(e)}
