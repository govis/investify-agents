from crewai import Agent, LLM, Task, Crew, Process
import os
from dotenv import load_dotenv, find_dotenv
from tools import ddgs_search, web_fetch
from schema import CompanyProfile

load_dotenv(find_dotenv(), override=True)

def get_llm():
    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    return LLM(
        model=f"gemini/{model_name}",
        api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0.1
    )

class ProfilingPipeline:
    def __init__(self):
        self.llm = get_llm()

    def profile_researcher(self):
        return Agent(
            role="Company Profile Researcher",
            goal="Identify the official website, country of domicile, a concise description, and the official logo URL of a company.",
            backstory="You are a skilled financial investigator. You excel at finding precise details about companies.",
            llm=self.llm,
            tools=[ddgs_search, web_fetch],
            verbose=True,
            allow_delegation=False
        )

    def mining_specialist(self):
        return Agent(
            role="Mining Industry Specialist",
            goal="Identify the primary metals and minerals (up to 3) produced by a mining company.",
            backstory="You are an expert in the mining and materials sector. You know where to find data on a company's mineral production and resources.",
            llm=self.llm,
            tools=[ddgs_search, web_fetch],
            verbose=True,
            allow_delegation=False
        )

    def research_task(self, researcher, mining_spec, name, ticker, exchange, theses):
        return Task(
            description=(
                f"Find detailed profile information for {name} ({ticker}:{exchange}).\n"
                f"1. Find the official website and a one-paragraph description (approx 50-100 words).\n"
                f"2. Identify the country of domicile.\n"
                f"3. If it's a mining company, ensure the mining specialist identifies up to 3 key metals/minerals.\n"
                f"4. Find the URL of the official company logo (logo_url).\n"
                f"5. Provide the final output strictly following the CompanyProfile schema.\n"
                f"Use the following list for the 'investment_theses' field exactly as provided: {theses}"
            ),
            expected_output="A complete company profile as per the CompanyProfile schema.",
            agent=researcher,
            output_pydantic=CompanyProfile
        )

    async def run(self, company_ref):
        researcher = self.profile_researcher()
        mining_spec = self.mining_specialist()
        task = self.research_task(
            researcher, 
            mining_spec, 
            company_ref['name'], 
            company_ref['ticker'], 
            company_ref['exchange'], 
            company_ref['theses']
        )
        
        crew = Crew(
            agents=[researcher, mining_spec],
            tasks=[task],
            process=Process.sequential,
            verbose=True
        )
        
        result = await crew.kickoff_async()
        
        # Ensure the investment_theses are copied exactly as provided
        res_data = result.pydantic if result.pydantic else result.raw
        if res_data:
            if hasattr(res_data, 'investment_theses'):
                res_data.investment_theses = company_ref['theses']
            elif isinstance(res_data, dict):
                res_data['investment_theses'] = company_ref['theses']
                
        return res_data
