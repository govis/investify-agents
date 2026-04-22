import os
import json
import asyncio
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types
from groq import Groq
from dotenv import load_dotenv, find_dotenv

# Load settings
load_dotenv(find_dotenv(), override=True)
load_dotenv(os.path.join("..", ".env"), override=False)

class DirectPipeline:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "gemini").lower()
        
        # Gemini setup
        self.gemini_client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        
        # Groq setup
        self.groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    def _get_system_instruction(self, thesis_name: str) -> str:
        return (
            f"You are a Meticulous Financial Data Analyst specializing in the '{thesis_name}' investment thesis. "
            "Your task is to identify EVERY publicly traded company mentioned in the text.\n\n"
            "CRITICAL RULES:\n"
            "1. EXTRACT: Name, Ticker, and Exchange (infer exchange if missing: TSX for Canada, ASX for Australia, NYSE/NASDAQ for USA).\n"
            "2. TYPE: Define 'company_type' specifically as it relates to the thesis.\n"
            "3. MENTIONS: Provide a list of EXACT text strings (mentions) found in the provided text that refer to this company. "
            "Include both the full name and the ticker if they appear. Be case-sensitive and precise.\n"
            "4. SCOPE: ONLY include companies mentioned in the provided text chunk. DO NOT include companies from your general knowledge or previous chunks.\n"
            "5. OUTPUT: You MUST return a valid JSON object following the required schema."
        )

    async def process_chunk(self, thesis_name: str, content: str, existing_companies: str, exchange_filter: List[str] = None) -> Dict[str, Any]:
        """Process a text chunk and return a list of identified companies with their mentions."""
        system_instr = self._get_system_instruction(thesis_name)
        
        prompt = (
            f"TEXT CONTENT TO PROCESS:\n{content}\n\n"
        )
        if existing_companies:
            prompt += f"CONTEXT (Already identified companies in this thesis): {existing_companies}\n\n"
            
        prompt += (
            "Return a JSON object with a 'companies' key containing a list of objects. Each object must have: "
            "'name', 'ticker', 'exchange', 'company_type', and 'mentions' (list of exact strings from text)."
        )

        if self.provider == "gemini":
            return await self._call_gemini(system_instr, prompt)
        else:
            return await self._call_groq(system_instr, prompt)

    async def _call_gemini(self, system_instr: str, prompt: str) -> Dict[str, Any]:
        # JSON Schema for Gemini
        response_schema = {
            "type": "OBJECT",
            "properties": {
                "companies": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "name": {"type": "STRING"},
                            "ticker": {"type": "STRING"},
                            "exchange": {"type": "STRING"},
                            "company_type": {"type": "STRING"},
                            "mentions": {"type": "ARRAY", "items": {"type": "STRING"}}
                        },
                        "required": ["name", "ticker", "exchange", "company_type", "mentions"]
                    }
                }
            },
            "required": ["companies"]
        }

        try:
            config = types.GenerateContentConfig(
                system_instruction=system_instr,
                response_mime_type="application/json",
                response_schema=response_schema,
                temperature=0.1
            )
            
            # Use to_thread for the synchronous SDK call
            response = await asyncio.to_thread(
                self.gemini_client.models.generate_content,
                model=self.gemini_model,
                contents=prompt,
                config=config
            )
            
            if response.text:
                return json.loads(response.text)
            return {"companies": []}
            
        except Exception as e:
            print(f"    Gemini API Error: {e}")
            raise e

    async def _call_groq(self, system_instr: str, prompt: str) -> Dict[str, Any]:
        try:
            # Groq uses standard OpenAI-style completions
            response = await asyncio.to_thread(
                self.groq_client.chat.completions.create,
                model=self.groq_model,
                messages=[
                    {"role": "system", "content": system_instr},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            
            content = response.choices[0].message.content
            if content:
                return json.loads(content)
            return {"companies": []}
            
        except Exception as e:
            print(f"    Groq API Error: {e}")
            raise e
