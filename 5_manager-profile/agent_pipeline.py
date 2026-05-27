import os
import json
import asyncio
import time
from collections import deque
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from groq import Groq
from dotenv import load_dotenv, find_dotenv
import tools
from data_utils import get_manager_data

load_dotenv(find_dotenv(), override=True)

# Configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()
GEMINI_MODEL = os.getenv("GEMINI_MODEL")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
SEARCH_GROUNDING_MODEL = os.getenv("GEMINI_MODEL_SEARCH_GROUNDING") or GEMINI_MODEL
VALIDATE_PROFILE_USING = os.getenv("VALIDATE_PROFILE_USING", "SEARCH_GROUNDING").upper()
MAX_AGENT_CALLS_PER_MANAGER = int(os.getenv("MAX_AGENT_CALLS_PER_MANAGER", "10"))

# Dynamic Throttling Settings
LLM_RPM = int(os.getenv("LLM_RPM", "15"))
LLM_TPM = int(os.getenv("LLM_TPM", "1000000"))

# Dynamic Chunking/Truncation Calculation (TPM based)
tpr = LLM_TPM / max(LLM_RPM, 1)
MAX_CHARS = int(max(500, min(8000, (tpr - 700) * 4)))

if LLM_PROVIDER == "gemini" and not GEMINI_MODEL:
    raise ValueError("GEMINI_MODEL environment variable is not set in .env")

class AsyncRateLimiter:
    """A sliding window rate limiter to ensure LLM_RPM is never exceeded."""
    def __init__(self, rpm: int):
        self.rpm = rpm
        self.requests = deque()
        self.lock = asyncio.Lock()

    async def acquire(self):
        """Acquires permission to make a request, sleeping if necessary."""
        if self.rpm <= 0: return # No limit
        
        async with self.lock:
            while True:
                now = time.time()
                while self.requests and self.requests[0] < now - 60:
                    self.requests.popleft()

                if len(self.requests) < self.rpm:
                    self.requests.append(now)
                    return
                else:
                    sleep_time = 60 - (now - self.requests[0])
                    if sleep_time > 0:
                        print(f"    Rate Limit (RPM) reached. Throttling for {sleep_time:.2f}s...")
                        await asyncio.sleep(sleep_time)

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
    def __init__(self, client: Any, model: str, system_instruction: str, limiter: AsyncRateLimiter, provider: str = "gemini", max_iter: int = 10):
        self.client = client
        self.model = model
        self.system_instruction = system_instruction
        self.max_output_tokens = 2048
        self.timeout = 90
        self.max_iter = max_iter
        self.limiter = limiter
        self.provider = provider

    async def call(self, prompt: str, schema: Any, use_search: bool = False):
        await self.limiter.acquire()
        
        if self.provider == "gemini":
            return await self._call_gemini(prompt, schema, use_search)
        elif self.provider == "groq":
            return await self._call_groq(prompt, schema, use_search)

    async def _call_gemini(self, prompt: str, schema: Any, use_search: bool):
        config = types.GenerateContentConfig(
            system_instruction=self.system_instruction,
            response_mime_type="application/json",
            response_schema=schema,
            max_output_tokens=self.max_output_tokens,
            temperature=0.0,
        )
        if use_search:
            config.tools = [types.Tool(google_search=types.GoogleSearch())]
        
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self.client.models.generate_content,
                    model=self.model,
                    contents=prompt,
                    config=config
                ),
                timeout=self.timeout
            )
            return response.parsed
        except Exception as e:
            print(f"Agent (Gemini): Error: {e}")
            return None

    async def _call_groq(self, prompt: str, schema: Any, use_search: bool):
        messages = [
            {"role": "system", "content": self.system_instruction},
            {"role": "user", "content": prompt}
        ]
        
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self.client.chat.completions.create,
                    model=self.model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.0,
                    max_tokens=self.max_output_tokens
                ),
                timeout=self.timeout
            )
            content = response.choices[0].message.content
            data = json.loads(content)
            
            # Robust extraction for Groq's tendency to wrap results
            try:
                return schema.model_validate(data)
            except Exception:
                # Try to find a list or object that matches the schema inside common hallucinated keys
                for key in ['candidates', 'search_results', 'verification_result', 'result', 'data']:
                    if key in data:
                        try:
                            if isinstance(data[key], list) and 'candidates' in schema.model_fields:
                                return schema.model_validate({'candidates': data[key]})
                            return schema.model_validate(data[key])
                        except Exception:
                            continue
                raise
        except Exception as e:
            print(f"Agent (Groq): Error: {e}")
            return None

def get_slim_manager_context(manager: Dict[str, Any]) -> Dict[str, Any]:
    """
    Creates a minimal context for the LLM to reduce token usage and cost.
    """
    return {
        "name": manager.get("name"),
        "age": manager.get("age"),
        "affiliations": [
            {
                "company": c["name"],
                "role": c["title_or_role"]
            } for c in manager.get("company_affiliations", [])
        ],
        "background": manager.get("background_truncated")
    }

class Supervisor:
    def __init__(self, pipeline: 'ManagerEnrichmentPipelineV2'):
        self.pipeline = pipeline
        self.max_verifications = 3
        self.call_count = 0

    def _check_budget(self):
        if self.call_count >= MAX_AGENT_CALLS_PER_MANAGER:
            print(f"Supervisor: [BUDGET EXCEEDED] Reached {MAX_AGENT_CALLS_PER_MANAGER} agent calls.")
            return False
        self.call_count += 1
        return True

    async def orchestrate(self, profile_path: str, get_picture: str = "no", search_picture_li: str = "no"):
        print(f"Supervisor: Starting enrichment for {os.path.basename(profile_path)} using {LLM_PROVIDER.upper()} and {VALIDATE_PROFILE_USING}")
        self.call_count = 0
        manager_full = get_manager_data(profile_path)
        manager_dir = os.path.dirname(profile_path)
        blacklist = tools.get_blacklist()
        known_urls = tools.get_known_urls()
        
        # TPM-aware truncation
        background = manager_full.get('background', '')
        if background and len(background) > MAX_CHARS:
            background = background[:MAX_CHARS] + "..."
        manager_full['background_truncated'] = background
        
        # Create SLIM context to save tokens
        manager = get_slim_manager_context(manager_full)

        best_candidate_url = known_urls.get(manager['name'])
        best_verification = None
        
        if best_candidate_url:
            print(f"Supervisor: Found known LinkedIn URL for {manager['name']}: {best_candidate_url}")
            if self._check_budget():
                v_res = await self._verify_wrapper(manager, best_candidate_url)
                if v_res is None:
                    await self.finalize(profile_path, "error")
                    return
                if v_res.is_verified:
                    best_verification = v_res
                else:
                    best_candidate_url = None

        if not best_verification:
            existing_linkedin = next((s['url'] for s in manager_full.get('socials', []) if 'linkedin.com' in s['url'].lower()), None)
            if existing_linkedin:
                if existing_linkedin.lower().rstrip('/') in blacklist:
                    print(f"Supervisor: Existing URL {existing_linkedin} is in blacklist.")
                else:
                    print(f"Supervisor: Attempting verification for existing URL {existing_linkedin}...")
                    if self._check_budget():
                        v_res = await self._verify_wrapper(manager, existing_linkedin)
                        if v_res is None:
                            await self.finalize(profile_path, "error")
                            return
                        if v_res.is_verified:
                            best_verification = v_res
                            best_candidate_url = existing_linkedin
            
            if not best_verification:
                print(f"Supervisor: Searching for LinkedIn Profile...")
                if self._check_budget():
                    if LLM_PROVIDER == "groq" or VALIDATE_PROFILE_USING == "CLOCK_BROWSER":
                        search_results = await asyncio.to_thread(tools.search_social_media, manager['name'], [c['company'] for c in manager['affiliations']])
                        prompt = (
                            f"MANAGER IDENTITY:\n{json.dumps(manager, indent=2)}\n\n"
                            f"SEARCH RESULTS TO EVALUATE:\n{json.dumps(search_results, indent=2)}\n\n"
                            "TASK: Identify the best LinkedIn profile match from the search results.\n"
                            "Return a JSON object with a 'candidates' key containing a list of objects with 'name', 'url', 'match_confidence', and 'reasoning'."
                        )
                        search_res = await self.pipeline.agents['search'].call(prompt, SearchAgentResult)
                    else:
                        search_res = await self.pipeline.agents['search'].search(manager)
                    
                    if search_res is None:
                        await self.finalize(profile_path, "error")
                        return

                    candidates = search_res.candidates
                    candidates = [c for c in candidates if c.url.lower().rstrip('/') not in blacklist]
                    candidates = sorted(candidates, key=lambda x: x.match_confidence, reverse=True)[:5]

                    if not candidates:
                        await self.finalize(profile_path, "not_found")
                        return

                    verification_count = 0
                    for candidate in candidates:
                        if candidate.match_confidence < 0.3: continue
                        if verification_count >= self.max_verifications: break
                        if existing_linkedin and candidate.url.rstrip('/') == existing_linkedin.rstrip('/'): continue

                        print(f"Supervisor: Verifying candidate {candidate.url} (Attempt {verification_count + 1})...")
                        if self._check_budget():
                            v_res = await self._verify_wrapper(manager, candidate.url)
                            verification_count += 1
                            if v_res is None:
                                await self.finalize(profile_path, "error")
                                return
                            if v_res.is_verified:
                                best_verification = v_res
                                best_candidate_url = candidate.url
                                break
        
        if not best_verification:
            await self.finalize(profile_path, "not_found")
            return

        print(f"Supervisor: Checking URL status for {best_candidate_url}...")
        url_status = await asyncio.to_thread(tools.check_url_status, best_candidate_url)
        
        existing_social = next((s for s in manager_full.get('socials', []) if 'linkedin.com' in s['url'].lower()), {})
        picture_url_li_profile = best_verification.potential_picture_url or existing_social.get('picture_url_li_profile')
        picture_url_li_search = existing_social.get('picture_url_li_search')
        final_pic_url = None
        
        if url_status == 'success' and picture_url_li_profile and get_picture == "yes":
            if tools.download_image(picture_url_li_profile, manager_dir):
                final_pic_url = picture_url_li_profile
        
        if search_picture_li == "yes" and not final_pic_url and best_verification.person_name:
            if self._check_budget():
                if LLM_PROVIDER == "groq":
                    picture_url_li_search = await asyncio.to_thread(tools.search_profile_picture, best_verification.person_name, [best_verification.company_name], best_candidate_url)
                else:
                    res = await self.pipeline.agents['img_li'].search(best_verification.person_name, best_verification.company_name)
                    picture_url_li_search = res.image_url if res else None
                
                if picture_url_li_search and get_picture == "yes":
                    if tools.download_image(picture_url_li_search, manager_dir):
                        final_pic_url = picture_url_li_search

        social_entry = {
            "name": "LinkedIn", "url": best_candidate_url,
            "person_name": best_verification.person_name, "company_name": best_verification.company_name,
            "profile_status": url_status, "potential_picture_url": final_pic_url,
            "picture_url_li_profile": picture_url_li_profile, "picture_url_li_search": picture_url_li_search
        }
        await self.finalize(profile_path, "success", [social_entry])

    async def _verify_wrapper(self, manager, url):
        """Helper to switch between Search Grounding and Clock Browser validation."""
        if VALIDATE_PROFILE_USING == "CLOCK_BROWSER":
            print(f"Supervisor: Validating {url} using CLOCK_BROWSER (Scraper)...")
            img_url = await asyncio.to_thread(tools.scrape_linkedin_picture, url)
            prompt = (
                f"MANAGER IDENTITY:\n{json.dumps(manager, indent=2)}\n\n"
                f"LINKEDIN URL TO VERIFY: {url}\n"
                f"IMAGE FOUND ON PAGE: {img_url}\n\n"
                "TASK: Verify if this URL belongs to the manager described. "
                "Return a JSON object with: 'is_verified' (bool), 'person_name', 'company_name', and 'verification_reasoning'."
            )
            v_res = await self.pipeline.agents['verifier'].call(prompt, VerificationResult)
            if v_res:
                if v_res.is_verified and img_url and img_url != "BLOCKED" and not v_res.potential_picture_url:
                    v_res.potential_picture_url = img_url
                return v_res
        else:
            return await self.pipeline.agents['verifier'].verify(manager, url)
        return None


    async def finalize(self, profile_path: str, status: str, new_socials: List[Dict] = None):
        with open(profile_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        data["enrichment_socials"] = status
        blacklist = tools.get_blacklist()
        existing_socials = data.get("socials", [])
        if new_socials:
            for ns in new_socials:
                found = False
                for i, es in enumerate(existing_socials):
                    if es.get('name') == ns.get('name'):
                        existing_socials[i] = ns
                        found = True
                        break
                if not found: existing_socials.append(ns)
        data["socials"] = [s for s in existing_socials if s.get('url', '').lower().rstrip('/') not in blacklist]
        with open(profile_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

class LinkedInSearchAgent(Agent):
    async def search(self, manager: Dict[str, Any]) -> SearchAgentResult:
        prompt = (f"MANAGER IDENTITY:\n{json.dumps(manager, indent=2)}\n\n"
                  f"TASK: Find the official personal LinkedIn profile for this individual.\n"
                  f"Return a JSON object with a 'candidates' key containing a list of candidates.")
        return await self.call(prompt, SearchAgentResult, use_search=True)

class LinkedInVerifierAgent(Agent):
    async def verify(self, manager: Dict[str, Any], url: str) -> VerificationResult:
        prompt = (f"MANAGER IDENTITY:\n{json.dumps(manager, indent=2)}\n\n"
                  f"LINKEDIN URL TO VERIFY: {url}\n\n"
                  f"TASK: Verify if this URL belongs to the manager described.\n"
                  f"Return a JSON object with: 'is_verified' (bool), 'person_name', 'company_name', and 'verification_reasoning'.")
        return await self.call(prompt, VerificationResult, use_search=True)

class ImageSearchAgent2a(Agent):
    async def search(self, name: str, company: str) -> ImageSearchResult:
        prompt = f"Perform an image search for: '{name} {company}' LinkedIn profile picture."
        return await self.call(prompt, ImageSearchResult, use_search=True)

class ManagerEnrichmentPipelineV2:
    def __init__(self):
        self.limiter = AsyncRateLimiter(LLM_RPM)
        if LLM_PROVIDER == "gemini":
            self.client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        else:
            self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
            
        self.agents = {
            'search': LinkedInSearchAgent(self.client, GEMINI_MODEL if LLM_PROVIDER == "gemini" else GROQ_MODEL, "LinkedIn Search Agent. Return a JSON object.", self.limiter, provider=LLM_PROVIDER),
            'verifier': LinkedInVerifierAgent(self.client, SEARCH_GROUNDING_MODEL if LLM_PROVIDER == "gemini" else GROQ_MODEL, "LinkedIn Verifier Agent. Return a JSON object.", self.limiter, provider=LLM_PROVIDER),
            'img_li': ImageSearchAgent2a(self.client, GEMINI_MODEL if LLM_PROVIDER == "gemini" else GROQ_MODEL, "LinkedIn Image Agent. Return a JSON object.", self.limiter, provider=LLM_PROVIDER)
        }
        self.supervisor = Supervisor(self)

    async def run(self, profile_path: str, get_picture: str = "no", search_picture_li: str = "no"):
        try:
            await self.supervisor.orchestrate(profile_path, get_picture=get_picture, search_picture_li=search_picture_li)
            return {"success": True}
        except Exception as e:
            print(f"Pipeline Error: {e}")
            return {"success": False, "message": str(e)}
