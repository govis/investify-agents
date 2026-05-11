from crewai import Task
from schema import Management, ManagerProfileEnrichment

class CompanyTasks:
    def extraction_task(self, agent, company_name, ticker, exchange, country, website):
        return Task(
            description=(
                f"Identify and extract the current C-suite executives and Board of Directors for {company_name} ({ticker}) on {exchange}.\n"
                f"Country of domicile is: {country}.\n"
                f"Company website is: {website}.\n\n"
                f"Instructions:\n"
                f"1. Search official sources first (EDGAR for US, SEDAR for Canada).\n"
                f"2. Locate the most recent Management Proxy, Circular, or 10-K/AIF filing.\n"
                f"3. Search semi-official sources like news releases for recent management changes (joining or departing).\n"
                f"4. CROSS-REFERENCE the official company website ({website}) to verify if the person is currently with the company or board.\n"
                f"5. If verified as currently affiliated via the website or latest filing, set `verified_current` to true.\n"
                f"6. Identify and record `end_date` if they are no longer with the company/board.\n"
                f"7. Extract names, roles, ages, and backgrounds.\n"
                f"8. Track all source URLs used in the `sources` list.\n"
                f"9. Final output must follow the Management schema strictly."
            ),
            expected_output="A structured JSON object containing executives and board of directors as per the Management schema.",
            agent=agent,
            output_pydantic=Management
        )

class ManagerTasks:
    def discovery_task(self, agent, manager_name, current_affiliations, exchange_filter):
        return Task(
            description=(
                f"Research all publicly traded company affiliations for {manager_name}.\n"
                f"Known current affiliations: {current_affiliations}.\n\n"
                f"Instructions:\n"
                f"1. Perform a few (max 5) targeted searches to find other public companies where {manager_name} holds or held a senior role (Officer/Executive) or a Board of Directors position.\n"
                f"2. Focus on high-authority sources: SEC filings (EDGAR), SEDAR, company 'Management' or 'Leadership' pages, and LinkedIn profiles.\n"
                f"3. For each found company, identify the 'name', 'ticker', 'exchange', and 'website'.\n"
                f"4. Capture the 'title_or_role', 'start_date', and 'end_date' (use null for current roles).\n"
                f"5. ONLY include companies trading on the following exchanges: {exchange_filter}.\n"
                f"6. Do NOT perform exhaustive searches for every possible mention; find the primary professional affiliations."
            ),
            expected_output="A list of newly discovered company affiliations with their details.",
            agent=agent
        )

    def validation_task(self, agent, manager_name):
        return Task(
            description=(
                f"Validate all discovered company affiliations for {manager_name}.\n"
                f"Ensure each affiliation is for the CORRECT individual and that the company details (name, ticker, exchange, website) are accurate.\n"
                f"Set 'validated': true for each affiliation that passes your verification.\n\n"
                f"Final output must strictly follow the ManagerProfileEnrichment schema."
            ),
            expected_output="A validated list of company affiliations as per the ManagerProfileEnrichment schema.",
            agent=agent,
            output_pydantic=ManagerProfileEnrichment
        )
