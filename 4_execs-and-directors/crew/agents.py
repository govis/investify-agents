import os
from crewai import Agent, LLM
from tools.crew_tools import ddgs_search, web_fetch, edgar_filings_list, sedar_filings_list
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(), override=True)

def get_llm():
    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
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
