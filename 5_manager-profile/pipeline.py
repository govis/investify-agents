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
            "1. Use search_social_media to find LinkedIn and X (Twitter) profiles. Be accurate, cross-reference with the provided company affiliations and roles.\n"
            "2. Use search_profile_picture to find a professional headshot URL.\n"
            "3. Use save_enrichment to commit these two pieces of information to the Profile.json.\n\n"
            "CRITICAL: Be extremely precise. Ensure the profiles match the specific person based on their company and title."
        )

    async def run(self, profile_path: str):
        try:
            with open(profile_path, 'r', encoding='utf-8') as f:
                profile = json.load(f)
        except Exception as e:
            return {"success": False, "message": f"Could not read profile: {e}"}

        full_name = profile['name']
        affiliations = [c['name'] for c in profile.get('commpanies', [])]
        roles = [c['title_or_role'] for c in profile.get('commpanies', [])]
        
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
