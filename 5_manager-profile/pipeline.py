import os
import json
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from google import genai
from google.genai import types
from dotenv import load_dotenv, find_dotenv
import tools

load_dotenv(find_dotenv(), override=True)

# Configuration
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

class SocialProfile(BaseModel):
    name: str
    url: str
    potential_picture_url: Optional[str] = None

class ValidationResult(BaseModel):
    validated_profiles: List[SocialProfile]

class ManagerEnrichmentPipeline:
    def __init__(self, model_name: str = GEMINI_MODEL):
        self.model_name = model_name
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is not set")
        
        self.client = genai.Client(api_key=api_key)
        
        self.system_instruction = (
            "You are a Data Validation Specialist. Your task is to identify LinkedIn profile(s) that match a specific company manager.\n"
            "PROTOCOL:\n"
            "1. Review the manager's name, affiliated companies, and roles.\n"
            "2. Examine the provided search results. Discard any result that refers to a DIFFERENT person with the same name.\n"
            "3. Validation Criteria:\n"
            "   - The search result snippet or profile/URL explicitly confirms the person works (or worked) at the target companies or in the listed roles.\n"
            "   - OR the person's name is extremely unique AND the industry/context matches perfectly.\n"
            "4. Selection:\n"
            "   - Only select profiles where the snippet or profile/URL explicitly mentions at least one of the provided company affiliations or relevant roles.\n"
            "   - If you find multiple potential profiles for the same person, prioritize the one that matches their CURRENT role and company most closely.\n"
            "5. Return a JSON list of validated profiles. If no high-confidence matches exist, return an empty list.\n\n"
            "CRITICAL: Precision is more important than recall. Discard any profile that is likely a different person with the same name."
        )

    async def run(self, profile_path: str):
        try:
            with open(profile_path, 'r', encoding='utf-8') as f:
                profile = json.load(f)
        except Exception as e:
            return {"success": False, "message": f"Could not read profile: {e}"}

        full_name = profile['name']
        affiliations = [c['name'] for c in profile.get('companies', [])]
        roles = [c['title_or_role'] for c in profile.get('companies', [])]
        
        # Step 1: Search Social Media via Python
        search_results = tools.search_social_media(full_name, affiliations)
        
        # Step 2: Validate Results via Gemini (Single Turn)
        search_results_json = json.dumps(search_results, indent=2)
        prompt = (
            f"Verify these LinkedIn search results for {full_name}.\n"
            f"Affiliated Companies: {', '.join(affiliations)}\n"
            f"Roles: {', '.join(roles)}\n\n"
            f"SEARCH RESULTS:\n{search_results_json}\n\n"
            "Identify which of these LinkedIn profiles are correct. Respond with only the validated profiles in the required JSON format."
        )
        
        config = types.GenerateContentConfig(
            system_instruction=self.system_instruction,
            response_mime_type="application/json",
            response_schema=ValidationResult
        )

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config
            )
            
            validation_data = response.parsed
            raw_validated = [p.model_dump() for p in validation_data.validated_profiles]
            
            # Step 3: Handle Multiple Profiles & Select Primary
            normalized_validated = []
            seen_urls = set()
            for p in raw_validated:
                url = p['url'].lower()
                if 'linkedin.com' in url and url not in seen_urls:
                    p['url'] = url
                    normalized_validated.append(p)
                    seen_urls.add(url)

            final_socials = []
            if normalized_validated:
                # Store original search order (index) to use as a tie-breaker
                for i, lp in enumerate(normalized_validated):
                    lp['_search_index'] = i
                
                # Standardize primary LinkedIn
                normalized_validated.sort(key=lambda x: (x['_search_index'], 0 if 'www.linkedin.com' in x['url'].lower() else 1))
                primary_linkedin_url = normalized_validated[0]['url']

                # Standardize names for LinkedIn profiles
                for lp in normalized_validated:
                    if '_search_index' in lp: del lp['_search_index']
                    lp['name'] = "LinkedIn" if lp['url'] == primary_linkedin_url else full_name
                    final_socials.append(lp)

            # Step 4: Save Results via Python
            save_result = tools.save_enrichment(profile_path, final_socials)
            
            if "ERROR" in save_result:
                raise Exception(save_result)
            
            # Final Status Check
            final_status = "success" if final_socials else "not_found"
            
            with open(profile_path, 'r', encoding='utf-8') as f:
                p_data = json.load(f)
            p_data["enrichment_status"] = final_status
            with open(profile_path, 'w', encoding='utf-8') as f:
                json.dump(p_data, f, indent=2)

            return {
                "success": True,
                "message": f"Enrichment completed with status: {final_status}",
                "profile_path": profile_path
            }
            
        except Exception as e:
            print(f"Pipeline Error for {full_name}: {e}")
            return {
                "success": False,
                "message": str(e),
                "profile_path": profile_path
            }
