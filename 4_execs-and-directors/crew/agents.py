import os
from crewai import Agent, LLM
from tools.crew_tools import ddgs_search, web_fetch, edgar_filings_list, sedar_filings_list
from dotenv import load_dotenv, find_dotenv

# Prioritize local .env, then fallback to parent directory .env
load_dotenv(find_dotenv(), override=True)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

def get_llm():
    model_name = os.getenv("GEMINI_MODEL_ENRICHMENT", os.getenv("GEMINI_MODEL", "gemini-1.5-flash"))
    return LLM(
        model=f"gemini/{model_name}",
        api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0.1
    )

class CompanyAgents:
    def research_manager(self):
        return Agent(
            role="Research Manager",
            goal="Coordinate the extraction of management data for companies. Ensure all required C-suite and Board data is collected and formatted correctly.",
            backstory="You are an expert financial analyst supervisor. You know when to delegate tasks to specialists and you ensure the final output is high quality and accurate.",
            llm=get_llm(),
            verbose=True,
            allow_delegation=True
        )

    def edgar_specialist(self):
        return Agent(
            role="EDGAR Filing Specialist",
            goal="Extract C-suite and Board members from US SEC filings (10-K, DEF 14A) using EDGAR tools.",
            backstory="You are an expert at navigating the SEC EDGAR system. You know exactly how to find CIKs, identify the latest proxy statements, and extract personnel data from Item 10 or the 'Directors and Executive Officers' section.",
            llm=get_llm(),
            tools=[edgar_filings_list, ddgs_search, web_fetch],
            verbose=True,
            allow_delegation=False
        )

    def sedar_specialist(self):
        return Agent(
            role="SEDAR+ Filing Specialist",
            goal="Extract C-suite and Board members from Canadian filings using SEDAR and web search tools.",
            backstory="You are an expert in the Canadian financial regulatory environment. You know how to find Management Information Circulars and Annual Information Forms on SEDAR+ and corporate Investor Relations websites.",
            llm=get_llm(),
            tools=[sedar_filings_list, ddgs_search, web_fetch],
            verbose=True,
            allow_delegation=False
        )

    def listed_security_specialist(self):
        return Agent(
            role="International Listed Security Specialist",
            goal="Extract C-suite and Board members for international companies from official regulatory filings, annual reports, and corporate governance documents.",
            backstory="You are an expert in global financial markets and regulatory environments. You are skilled at finding and parsing annual reports (e.g., Form 20-F, annual reports in various jurisdictions) and management personnel disclosures from corporate websites and international regulatory bodies.",
            llm=get_llm(),
            tools=[ddgs_search, web_fetch],
            verbose=True,
            allow_delegation=False
        )

class ManagerAgents:
    def supervisor_agent(self):
        return Agent(
            role="Enrichment Supervisor",
            goal="Oversee the enrichment of manager profiles. Coordinate discovery and validation of additional company affiliations.",
            backstory="You are a meticulous supervisor specializing in corporate intelligence. You ensure that all found affiliations are thoroughly researched and validated before being added to a profile.",
            llm=get_llm(),
            verbose=True,
            allow_delegation=True,
            max_iter=10
        )

    def ir_research_agent(self):
        return Agent(
            role="IR Research Specialist",
            goal="Find all publicly traded company affiliations for a specific individual where they held a senior role or were a director. Include current and past roles with dates.",
            backstory="You are an expert in investor relations and corporate disclosures. You perform targeted, high-quality searches (max 5 searches) in regulatory databases, proxy statements, and corporate websites to find an individual's professional history. You avoid repetitive searching.",
            llm=get_llm(),
            tools=[ddgs_search, web_fetch, edgar_filings_list, sedar_filings_list],
            verbose=True,
            allow_delegation=False,
            max_iter=10
        )

    def validation_agent(self):
        return Agent(
            role="Affiliation Validator",
            goal="Validate discovered company affiliations to ensure they are accurate and the individual is indeed the correct person. Verify names, tickers, exchanges, and websites.",
            backstory="You are a detail-oriented auditor. You cross-reference multiple sources to confirm that a reported company affiliation is valid and corresponds to the specific individual being researched.",
            llm=get_llm(),
            tools=[ddgs_search, web_fetch],
            verbose=True,
            allow_delegation=False,
            max_iter=10
        )
