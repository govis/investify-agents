import os
import json
import asyncio
from typing import Dict, Any
from google import genai
from google.genai import types
from dotenv import load_dotenv, find_dotenv
import tools

load_dotenv(find_dotenv(), override=True)

class LogoPipeline:
    def __init__(self, model_name: str = "gemini-flash-latest"):
        self.model_name = model_name
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is not set")
        
        self.client = genai.Client(api_key=api_key)
        
        # System instructions to enforce the protocol
        self.system_instruction = (
            "You are a Visual Identity Specialist responsible for securing official company logos. "
            "You follow a strict protocol to ensure authenticity and quality:\n"
            "1. Start with search_companieslogo_com (most reliable for public companies).\n"
            "2. If that fails, use verify_and_download_from_website to check the official site.\n"
            "3. If still nothing, use broader_internet_search to find the best available asset.\n"
            "4. As a last resort, if no logo exists, use broader_internet_search to gather visual details "
            "and then call generate_logo_ai to create a placeholder.\n\n"
            "CRITICAL: STOP IMMEDIATELY once any tool returns a 'SUCCESS' message. "
            "Do not proceed to further steps if a logo has been secured. "
            "Always prioritize SVGs and high-resolution PNGs."
        )

    async def run(self, company_ref: Dict[str, Any], website: str, folder_path: str):
        name = company_ref['name']
        ticker = company_ref['ticker']
        
        prompt = (
            f"Find or generate the logo for {name} ({ticker}).\n"
            f"Official website: {website}\n"
            f"Target folder: {folder_path}\n"
            "Proceed step-by-step through your protocol."
        )
        
        # Mapping functions for tool calling
        config = types.GenerateContentConfig(
            system_instruction=self.system_instruction,
            tools=[
                tools.search_companieslogo_com,
                tools.verify_and_download_from_website,
                tools.broader_internet_search,
                tools.generate_logo_ai
            ],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=False)
        )

        try:
            # We use a synchronous call within the async run for simplicity with the SDK
            # The SDK handles the iterative function calling internally
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config
            )
            
            # Simple success/fail result
            return {
                "success": True,
                "message": response.text if response.text else "Logo processing completed.",
                "folder_path": folder_path
            }
            
        except Exception as e:
            print(f"Pipeline Error for {ticker}: {e}")
            return {
                "success": False,
                "message": str(e),
                "folder_path": folder_path
            }
