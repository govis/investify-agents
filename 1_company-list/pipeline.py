from crewai import Agent, LLM, Task, Crew, Process
import os
import json
from typing import List
from dotenv import load_dotenv, find_dotenv
from tools import thesis_reader
from schema import CompanyList

load_dotenv(find_dotenv(), override=True)

def get_llm():
    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    return LLM(
        model=f"gemini/{model_name}",
        api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0.2
    )

class ExtractionPipeline:
    def __init__(self):
        self.llm = get_llm()

    def create_agent(self, thesis_name: str):
        return Agent(
            role="Financial Data Extraction Specialist",
            goal=f"Meticulously scan EVERY line and table in the Theses/{thesis_name} folder to identify ALL publicly traded companies. I expect a high volume of companies (dozens per thesis).",
            backstory="You are an expert financial analyst. You have a 'zero-miss' policy. You know that companies are often hidden in tables, bullet points, and parenthetical mentions like (Ticker: EXCHANGE). You never skip a company just because it's in a list.",
            llm=self.llm,
            tools=[thesis_reader],
            verbose=True,
            allow_delegation=False
        )

    def create_task(self, agent, thesis_name: str, existing_companies: str = ""):
        description = (
            f"URGENT: Extract ALL publicly traded companies from the '{thesis_name}' thesis. There are likely 20-40+ companies in this section alone.\n"
            f"1. Call thesis_reader(thesis_name='{thesis_name}') to get the content.\n"
            "2. SCAN ALL TABLES: Many companies are listed in tables with columns for 'Company', 'Ticker', 'Region', etc. EXTRACT EVERY SINGLE ONE.\n"
            "3. Identify name, ticker, and exchange for each. If exchange is missing, infer it (e.g., TSX for Canadian, ASX for Australian, NYSE/NASDAQ for US).\n"
            f"4. For each company, define its 'company_type' specifically as it relates to the '{thesis_name}' thesis.\n"
        )
        
        if existing_companies:
            description += (
                "\n4. CRITICAL REFINEMENT STEP:\n"
                "The following companies were already identified in other theses:\n"
                f"{existing_companies}\n"
                "If you find any of these companies in the current thesis, DOUBLE CHECK and REFINE their 'company_type' based on the new information provided in this thesis. "
                "Ensure the 'company_type' is descriptive and accurate for the current context."
            )
        
        description += "\n5. Return a CompanyList with all identified companies for THIS thesis."

        return Task(
            description=description,
            expected_output=f"A CompanyList object containing companies found in the {thesis_name} thesis.",
            agent=agent,
            output_pydantic=CompanyList
        )

    async def run_thesis(self, thesis_name: str, existing_companies_data: List[dict] = None):
        existing_str = ""
        if existing_companies_data:
            existing_str = json.dumps(existing_companies_data, indent=2)
            
        agent = self.create_agent(thesis_name)
        task = self.create_task(agent, thesis_name, existing_str)
        
        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            verbose=True
        )
        
        result = await crew.kickoff_async()
        return result.pydantic if result.pydantic else result.raw
