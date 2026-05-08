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
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
SEARCH_GROUNDING_MODEL = os.getenv("GEMINI_MODEL_SEARCH_GROUNDING", "gemini-2.0-flash")

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

    async def orchestrate(self, profile_path: str):
        print(f"Supervisor: Starting enrichment for {os.path.basename(profile_path)}")
        manager = get_manager_data(profile_path)
        
        # 1. Search for LinkedIn Profile
        print(f"Supervisor: Delegating to LinkedIn Search Agent...")
        candidates = await self.pipeline.agents['search'].search(manager)
        print(f"Supervisor: Found {len(candidates)} candidates: {[c.url for c in candidates]}")
        
        if not candidates:
            print("Supervisor: No candidates found.")
            await self.finalize(profile_path, "not_found")
            return

        # 2. Verify Candidates
        best_verification = None
        best_candidate_url = None
        for candidate in sorted(candidates, key=lambda x: x.match_confidence, reverse=True):
            if candidate.match_confidence < 0.3: continue
            print(f"Supervisor: Verifying candidate {candidate.url}...")
            v_res = await self.pipeline.agents['verifier'].verify(manager, candidate.url)
            if v_res.is_verified:
                best_verification = v_res
                best_candidate_url = candidate.url
                print(f"Supervisor: Verified {candidate.url}")
                break
            else:
                print(f"Supervisor: Candidate {candidate.url} not verified. Reasoning: {v_res.verification_reasoning}")
        
        if not best_verification:
            print("Supervisor: No candidate verified.")
            await self.finalize(profile_path, "not_found")
            return

        # 3. Handle Images
        current_pic = best_verification.potential_picture_url
        if not current_pic:
            print("Supervisor: No picture found on LinkedIn profile. Trying alternative agents...")
            # 4a. LinkedIn Image Search
            if best_verification.person_name and best_verification.company_name:
                print("Supervisor: Trying LinkedIn Image Search (4a)...")
                res = await self.pipeline.agents['img_li'].search(best_verification.person_name, best_verification.company_name)
                current_pic = res.image_url
            
            # 4b. IR Website Search
            if not current_pic:
                print("Supervisor: Trying IR Website Search (4b)...")
                res = await self.pipeline.agents['img_ir'].search(manager)
                current_pic = res.image_url
                
            # 4c. Broad IR Search
            if not current_pic:
                print("Supervisor: Trying Broad IR Search (4c)...")
                res = await self.pipeline.agents['img_broad'].search(manager)
                current_pic = res.image_url

        # Finalize
        social_entry = {
            "name": "LinkedIn",
            "url": best_candidate_url,
            "person_name": best_verification.person_name,
            "company_name": best_verification.company_name,
            "potential_picture_url": current_pic
        }
        await self.finalize(profile_path, "success", [social_entry])

    async def finalize(self, profile_path: str, status: str, socials: List[Dict] = None):
        with open(profile_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        data["enrichment_status"] = status
        if socials:
            data["socials"] = socials
        with open(profile_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        print(f"Supervisor: Finished with status {status}")

class LinkedInSearchAgent(Agent):
    async def search(self, manager: Dict[str, Any]) -> List[SocialProfileCandidate]:
        affiliations_str = ', '.join([f"{c['name']} ({c['name_clean']})" for c in manager['companies']])
        roles_str = ', '.join([c['title_or_role'] for c in manager['companies']])
        prompt = (
            f"Manager: {manager['name']}\n"
            f"Affiliations: {affiliations_str}\n"
            f"Roles: {roles_str}\n\n"
            "Task: Find the official LinkedIn profile for this individual.\n"
            "Search for their name along with their current company and role.\n"
            "Be aware that some roles might be recent (2023-2024). Look for news or press releases if the LinkedIn profile doesn't immediately show the role in the snippet."
        )
        res = await self.call(prompt, SearchAgentResult, use_search=True)
        return res.candidates

class LinkedInVerifierAgent(Agent):
    async def verify(self, manager: Dict[str, Any], url: str) -> VerificationResult:
        prompt = (
            f"Verify if this LinkedIn profile: {url}\n"
            f"Matches Manager: {manager['name']}\n"
            f"Affiliations: {', '.join([f'{c['name']} / {c['name_clean']}' for c in manager['companies']])}\n"
            f"Roles: {', '.join([c['title_or_role'] for c in manager['companies']])}\n"
            "If verified, capture exact name, company, and picture URL (shrink_200_200 priority)."
        )
        return await self.call(prompt, VerificationResult, use_search=True)

class ImageSearchAgent4a(Agent):
    async def search(self, name: str, company: str) -> ImageSearchResult:
        prompt = f"Search site:licdn.com for professional profile picture of {name} at {company}"
        return await self.call(prompt, ImageSearchResult, use_search=True)

class ImageSearchAgent4b(Agent):
    async def search(self, manager: Dict[str, Any]) -> ImageSearchResult:
        sites = [c['website'] for c in manager['companies'] if c.get('website')]
        prompt = f"Find manager {manager['name']} picture on Investor Relations pages of: {', '.join(sites)}"
        return await self.call(prompt, ImageSearchResult, use_search=True)

class ImageSearchAgent4c(Agent):
    async def search(self, manager: Dict[str, Any]) -> ImageSearchResult:
        affiliations = [c['name'] for c in manager['companies']]
        prompt = f"Broad search for professional picture of {manager['name']} at {', '.join(affiliations)} on IR websites."
        return await self.call(prompt, ImageSearchResult, use_search=True)

class ManagerEnrichmentPipelineV2:
    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        self.client = genai.Client(api_key=api_key)
        self.agents = {
            'search': LinkedInSearchAgent(self.client, GEMINI_MODEL, "You are a LinkedIn Profile Search Agent. Find the best match profile."),
            'verifier': LinkedInVerifierAgent(self.client, SEARCH_GROUNDING_MODEL, "You are a LinkedIn Verifier Agent. Use search to visit the profile and verify it. Capture name, company and photo URL (v2 media.licdn.com pattern, prioritize shrink_200_200, then 100_100, 400_400, 800_800)."),
            'img_li': ImageSearchAgent4a(self.client, GEMINI_MODEL, "You are a LinkedIn Image Search Agent."),
            'img_ir': ImageSearchAgent4b(self.client, GEMINI_MODEL, "You are an IR Website Image Search Agent."),
            'img_broad': ImageSearchAgent4c(self.client, GEMINI_MODEL, "You are a Broad IR Search Agent.")
        }
        self.supervisor = Supervisor(self)

    async def run(self, profile_path: str):
        try:
            await self.supervisor.orchestrate(profile_path)
            return {"success": True}
        except Exception as e:
            print(f"Pipeline Error: {e}")
            return {"success": False, "message": str(e)}
