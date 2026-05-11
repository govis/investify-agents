import os
import asyncio
import json
from crewai import Crew, Process
from crew.agents import CompanyAgents, ManagerAgents
from crew.tasks import CompanyTasks, ManagerTasks
from tools.crew_tools import set_current_folder
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(), override=True)

class CompanyCrew:
    def __init__(self):
        self.agents = CompanyAgents()
        self.tasks = CompanyTasks()
        
        # Load exchange to country mapping from environment
        self.exchange_country_map = {}
        ec_str = os.getenv("EXCHANGE_COUNTRY")
        if ec_str:
            try:
                # Clean potential quotes if the env loader didn't handle them
                cleaned_str = ec_str.strip("'").strip('"')
                self.exchange_country_map = json.loads(cleaned_str)
            except Exception as e:
                print(f"    [Warning] CompanyCrew: Failed to parse EXCHANGE_COUNTRY JSON: {e}")

    async def run(self, company: dict, folder: str):
        # folder is ticker.exchange relative to ../Companies
        abs_folder = os.path.join("..", "Companies", folder)
        set_current_folder(abs_folder)
        
        name = company.get('name', 'Unknown')
        ticker = company.get('ticker', 'Unknown')
        exchange = company.get('exchange', 'Unknown')
        
        profile = company.get('profile', {})
        # Prioritize Profile.json, then fallback to EXCHANGE_COUNTRY map, then 'US'
        country = profile.get('country_of_domicile')
        if not country:
            country = self.exchange_country_map.get(exchange.upper(), 'US')
            
        website = profile.get('website', '')
        
        try:
            research_manager = self.agents.research_manager()
            
            # Determine which specialist to use based on country and exchange
            country_upper = country.upper()
            exchange_upper = exchange.upper()
            
            if country_upper in ["US", "USA", "UNITED STATES"] or exchange_upper in ["NYSE", "NASDAQ"]:
                specialist = self.agents.edgar_specialist()
            elif country_upper in ["CANADA"] or exchange_upper in ["TSX", "TSXV", "CSE"]:
                specialist = self.agents.sedar_specialist()
            else:
                specialist = self.agents.listed_security_specialist()
            
            task = self.tasks.extraction_task(
                agent=specialist,
                company_name=name,
                ticker=ticker,
                exchange=exchange,
                country=country,
                website=website
            )
            
            crew = Crew(
                agents=[research_manager, specialist],
                tasks=[task],
                process=Process.sequential,
                verbose=True
            )
            
            result = await crew.kickoff_async()
            
            management_data = None
            if hasattr(result, 'pydantic') and result.pydantic:
                management_data = result.pydantic
            else:
                try:
                    import re
                    from schema import Management
                    raw = result.raw
                    if "```json" in raw:
                        match = re.search(r'```json\s*(.*?)\s*```', raw, re.DOTALL)
                        if match: raw = match.group(1)
                    management_data = Management.model_validate_json(raw)
                except Exception as e:
                    print(f"    [Error] Failed to parse crew result: {e}")
                    raise e

            os.makedirs(abs_folder, exist_ok=True)
            with open(os.path.join(abs_folder, "Management.json"), "w", encoding="utf-8") as f:
                f.write(management_data.model_dump_json(indent=2))
            
            # Generate Management.log
            log_content = f"Management Extraction Log for {name} ({ticker})\n"
            log_content += "="*50 + "\n"
            log_content += f"Status: Success\n"
            log_content += f"Agent Result Summary:\n{result.raw[:2000]}...\n"
            
            with open(os.path.join(abs_folder, "Management.log"), "w", encoding="utf-8") as f:
                f.write(log_content)

            with open(os.path.join(abs_folder, "Step_Crew_Raw_Response.txt"), "w", encoding="utf-8") as f:
                f.write(result.raw)

            return management_data.model_dump()
        
        except Exception as e:
            # Log the error
            log_content = f"Management Extraction Log for {name} ({ticker})\n"
            log_content += "="*50 + "\n"
            log_content += f"Status: Error\n"
            log_content += f"Error Message: {str(e)}\n"
            
            os.makedirs(abs_folder, exist_ok=True)
            with open(os.path.join(abs_folder, "Management.log"), "w", encoding="utf-8") as f:
                f.write(log_content)
            raise e

class ManagerCrew:
    def __init__(self):
        self.agents = ManagerAgents()
        self.tasks = ManagerTasks()
        self.exchange_filter = os.getenv("EXCHANGE_FILTER", "NYSE, NASDAQ, TSX, TSXV, CSE")

    async def run(self, manager_profile: dict, folder_path: str):
        # folder_path is the directory where Profile.json is located (e.g. ../Managers/Aaron Jagdfeld)
        set_current_folder(folder_path)
        
        manager_name = manager_profile.get('name', 'Unknown')
        current_affiliations = [c.get('name') for c in manager_profile.get('company_affiliations', [])]
        
        try:
            supervisor = self.agents.supervisor_agent()
            researcher = self.agents.ir_research_agent()
            validator = self.agents.validation_agent()
            
            discovery_task = self.tasks.discovery_task(
                agent=researcher,
                manager_name=manager_name,
                current_affiliations=current_affiliations,
                exchange_filter=self.exchange_filter
            )
            
            validation_task = self.tasks.validation_task(
                agent=validator,
                manager_name=manager_name
            )
            
            crew = Crew(
                agents=[supervisor, researcher, validator],
                tasks=[discovery_task, validation_task],
                process=Process.sequential,
                verbose=True
            )
            
            result = await crew.kickoff_async()
            
            enrichment_data = None
            if hasattr(result, 'pydantic') and result.pydantic:
                enrichment_data = result.pydantic
            else:
                try:
                    import re
                    from schema import ManagerProfileEnrichment
                    raw = result.raw
                    if "```json" in raw:
                        match = re.search(r'```json\s*(.*?)\s*```', raw, re.DOTALL)
                        if match: raw = match.group(1)
                    enrichment_data = ManagerProfileEnrichment.model_validate_json(raw)
                except Exception as e:
                    print(f"    [Error] Failed to parse manager enrichment result: {e}")
                    raise e

            # Update the manager profile with new affiliations
            # We merge and deduplicate based on company name/ticker
            new_affiliations = enrichment_data.company_affiliations
            existing_affiliations = manager_profile.get('company_affiliations', [])
            
            for new_aff in new_affiliations:
                # Convert Pydantic model to dict
                new_aff_dict = new_aff.model_dump()
                
                # Check if already exists
                exists = False
                for existing in existing_affiliations:
                    if existing['name'].lower() == new_aff_dict['name'].lower():
                        exists = True
                        # Update existing with new data if validated
                        if new_aff_dict['validated']:
                            existing.update(new_aff_dict)
                        break
                
                if not exists:
                    existing_affiliations.append(new_aff_dict)
            
            manager_profile['company_affiliations'] = existing_affiliations
            manager_profile['enrichment_company_affiliations'] = 'success'
            
            # Remove legacy fields if they exist
            manager_profile.pop('enrichment_status', None)
            manager_profile.pop('enrichment_step', None)
            
            # Save updated profile
            with open(os.path.join(folder_path, "Profile.json"), "w", encoding="utf-8") as f:
                json.dump(manager_profile, f, indent=2)
            
            # Generate Enrichment.log
            log_content = f"Manager Enrichment Log for {manager_name}\n"
            log_content += "="*50 + "\n"
            log_content += f"Status: Success\n"
            log_content += f"Agent Result Summary:\n{result.raw[:2000]}...\n"
            
            with open(os.path.join(folder_path, "Enrichment.log"), "w", encoding="utf-8") as f:
                f.write(log_content)

            return manager_profile
        
        except Exception as e:
            # Log the error
            log_content = f"Manager Enrichment Log for {manager_name}\n"
            log_content += "="*50 + "\n"
            log_content += f"Status: Error\n"
            log_content += f"Error Message: {str(e)}\n"
            
            with open(os.path.join(folder_path, "Enrichment.log"), "w", encoding="utf-8") as f:
                f.write(log_content)
            raise e
