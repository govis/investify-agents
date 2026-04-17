# Company Profiling Workflow

This agentic workflow is designed to retrieve and organize information for publicly traded companies.

## Workflow Overview

1.  **Input Source:** The workflow reads from `CompanyList.json` located in the parent directory (`../CompanyList.json`).
2.  **Output Structure:** For each company, a directory is created at `../Companies/TICKER.EXCHANGE/`.
3.  **Data File:** Inside each company folder, a `Profile.json` file is generated following the schema defined in `schema.py`.

## Information Retrieval

The agents are tasked with finding the following details for each company:
- **Company Name:** Full legal name.
- **Ticker & Exchange:** The stock symbol and the exchange it trades on.
- **Website:** The official company website.
- **Logo:** The URL to the official company logo.
- **Country of Domicile:** The country where the company is headquartered or legally registered.
- **Description:** A brief, one-paragraph description of the company's business activities.

## Specialized Agents

- **Company Profile Researcher:** Responsible for general company information, website, domicile, and logo.
- **Mining Industry Specialist:** If a company is identified as a mining company, this specialist agent finds up to 3 key metals or minerals that are central to the company's business.

## Environment Requirements

- **Python Version:** This workflow requires Python 3.13. Higher versions (like Python 3.14+) currently encounter compatibility issues with CrewAI and Pydantic dependencies.

## Technical Implementation

- **Main Entry Point:** `main.py` handles the queue of companies and coordinates the workers.
- **Pipeline:** `pipeline.py` defines the CrewAI agents and tasks.
- **Schema:** `schema.py` defines the `CompanyProfile` Pydantic model.
- **Tools:** `tools.py` provides web search (`ddgs_search`) and web fetching (`web_fetch`) capabilities.
