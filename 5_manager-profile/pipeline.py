import os
import json
from typing import Dict, Any, List
from google import genai
from google.genai import types
from dotenv import load_dotenv, find_dotenv
import tools

load_dotenv(find_dotenv(), override=True)

class ManagerEnrichmentPipeline:
    def __init__(self, model_name: str = "gemini-1.5-pro"):
        self.model_name = model_name
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is not set")
        
        self.client = genai.Client(api_key=api_key)
        
        self.system_instruction = (
            "You are a Data Enrichment Specialist. Your task is to find social media profiles and professional pictures for company managers.\n"
            "Your protocol:\n"
            "1. Use search_social_media to find LinkedIn and X (Twitter) profiles. Each result contains a 'snippet'.\n"
            "2. VERIFY each profile: Only select profiles where the snippet or URL explicitly mentions at least one of the provided company affiliations or relevant roles.\n"
            "3. Use search_profile_picture to find a professional headshot URL. MANDATORY: If you found a valid LinkedIn profile in step 1, pass its URL to search_profile_picture as the 'linkedin_url' parameter to prioritize LinkedIn-sourced headshots.\n"
            "4. Use save_enrichment to commit these pieces of information to the Profile.json.\n\n"
            "CRITICAL: Be extremely precise. If no profile matches the company affiliations in the search snippets, do NOT include it in the socials list. You MUST ALWAYS call the save_enrichment tool at the end of your run, even if the socials list is empty and the picture_url is None. This is required to mark the profile as 'success' (meaning it has been investigated). False positives are worse than missing data."
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
        
        prompt = (
            f"Enrich the profile for {full_name}.\n"
            f"Affiliated Companies: {', '.join(affiliations)}\n"
            f"Roles: {', '.join(roles)}\n"
            f"Profile Path: {profile_path}\n"
            "Find the LinkedIn profile, X/Twitter profile, and a professional picture URL."
        )
        
        config = types.GenerateContentConfig(
            system_instruction=self.system_instruction,
            tools=[
                tools.search_social_media,
                tools.search_profile_picture,
                tools.save_enrichment
            ],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=False)
        )

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config
            )
            
            return {
                "success": True,
                "message": response.text if response.text else "Enrichment completed.",
                "profile_path": profile_path
            }
            
        except Exception as e:
            print(f"Pipeline Error for {full_name}: {e}")
            return {
                "success": False,
                "message": str(e),
                "profile_path": profile_path
            }
