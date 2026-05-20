from crewai import Agent, LLM, Task, Crew, Process
import os
from dotenv import load_dotenv, find_dotenv
from tools import ddgs_search, web_fetch
from schema import CompanyProfile, CompanyProfileEnrichment

# Prioritize local .env, then fallback to parent directory .env
load_dotenv(find_dotenv(), override=True)
load_dotenv(os.path.join("..", ".env"))

def get_llm(is_enrichment=False):
    model_env_var = "GEMINI_MODEL_ENRICHMENT" if is_enrichment else "GEMINI_MODEL"
    model_name = os.getenv(model_env_var)
    if not model_name:
        # Fallback to GEMINI_MODEL if ENRICHMENT model isn't set, but warn
        fallback = os.getenv("GEMINI_MODEL")
        if fallback:
            print(f"Warning: {model_env_var} not set. Falling back to GEMINI_MODEL ({fallback}).")
            model_name = fallback
        else:
            raise ValueError("GEMINI_MODEL must be set in the .env file.")
            
    return LLM(
        model=f"gemini/{model_name}",
        api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0.1
    )

class ProfilingPipeline:
    def profile_researcher(self, llm):
        return Agent(
            role="Company Profile Researcher",
            goal="Identify the official website, country of domicile, a concise description, and the official logo URL of a company.",
            backstory="You are a skilled financial investigator. You excel at finding precise details about companies.",
            llm=llm,
            tools=[ddgs_search, web_fetch],
            verbose=True,
            allow_delegation=False,
            max_iter=10
        )

    def mining_specialist(self, llm):
        return Agent(
            role="Mining Industry Specialist",
            goal="Identify the primary metals and minerals (up to 3) produced by a mining company.",
            backstory="You are an expert in the mining and materials sector. You know where to find data on a company's mineral production and resources.",
            llm=llm,
            tools=[ddgs_search, web_fetch],
            verbose=True,
            allow_delegation=False,
            max_iter=10
        )

    def research_task(self, researcher, mining_spec, name, ticker, exchange, website=None, is_enrichment=False):
        description = (
            f"Find detailed profile information for {name} ({ticker}:{exchange}).\n"
            f"1. Find a one-paragraph description (approx 50-100 words).\n"
            f"2. Identify the country of domicile.\n"
            f"3. Find the URL of the official company logo (logo_url).\n"
        )
        
        if not is_enrichment:
            description += f"4. If it's a mining company, ensure the mining specialist identifies up to 3 key metals/minerals.\n"
            description += f"5. Find the official website.\n"
            description += (
                "6. Provide the final output strictly following the CompanyProfile schema.\n"
                "IMPORTANT: Do NOT attempt to populate 'investment_theses'. Leave it as an empty list."
            )
            schema = CompanyProfile
        else:
            description += f"4. Use the known website to aid your research: {website}\n"
            description += "5. Provide the final output strictly following the CompanyProfileEnrichment schema.\n"
            schema = CompanyProfileEnrichment
            
        return Task(
            description=description,
            expected_output=f"A complete company profile as per the {schema.__name__} schema.",
            agent=researcher,
            output_pydantic=schema
        )

    async def run(self, company_ref, is_enrichment=False):
        llm = get_llm(is_enrichment)
        researcher = self.profile_researcher(llm)
        
        agents = [researcher]
        mining_spec = None
        
        if not is_enrichment:
            mining_spec = self.mining_specialist(llm)
            agents.append(mining_spec)
            
        task = self.research_task(
            researcher, 
            mining_spec, 
            company_ref['name'], 
            company_ref['ticker'], 
            company_ref['exchange'], 
            website=company_ref.get('website'),
            is_enrichment=is_enrichment
        )
        
        crew = Crew(
            agents=agents,
            tasks=[task],
            process=Process.sequential,
            verbose=True
        )
        
        result = await crew.kickoff_async()
        
        pydantic_res = result.pydantic if result.pydantic else result.raw
        return pydantic_res, result.raw
