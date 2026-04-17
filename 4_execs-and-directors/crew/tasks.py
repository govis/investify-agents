from crewai import Task
from schema import Management

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
