# Company Profiling Workflow

This agentic workflow is designed to retrieve and organize information for publicly traded companies in a two-phase process.

## Workflow Overview

### Phase 1: Initial Discovery (`main.py`)
- **Input Source:** Reads from `CompanyList.json` located in the parent directory (`../CompanyList.json`).
- **Selection Criteria:** 
    - Processes companies that do **not** have a corresponding `TICKER.EXCHANGE` subfolder in the `../Companies/` directory.
    - **Ticker Validation:** Skips companies with non-alphanumeric characters in the `ticker` field (e.g., `.`, `-`, spaces).
    - **Exchange Filtering:** Checks the **original** exchange name against `EXCHANGE_FILTER`.
- **Exchange Substitution:** Applies `EXCHANGE_NAME_SUBSTITUTE` mapping to the exchange name before folder creation.
- **Data Population:**
    - Uses the `ProfilingPipeline` to find the website, country of domicile, description, and logo URL.
    - **Token Optimization:** Manually populates `investment_theses` from `CompanyList.json`.
- **Output:** Creates a `Profile.json` file in `../Companies/TICKER.EXCHANGE/`.
    - `origin`: Set to `"investment_theses"` if the source record has a `theses` field.
    - `exchange`: Matches the (substituted) exchange name in the folder path.

### Phase 2: Enrichment (`main2.py`)
- **Target Source:** Scans existing `Profile.json` files in the `../Companies/` directory.
- **Selection Criteria:** 
    - Targets profiles where `"origin": "manager_affiliation"` and `"enrichment": "pending"`.
    - **Ticker Validation:** Skips companies with non-alphanumeric characters in the `ticker` field.
    - **Exchange Substitution:** Applies `EXCHANGE_NAME_SUBSTITUTE` to ensure the `exchange` field in `Profile.json` matches the folder name conventions.
    - **Exchange Filtering:** Filters by the (possibly substituted) exchange name against `EXCHANGE_FILTER`.
- **Enrichment Logic:**
    - Uses the `ProfilingPipeline` in enrichment mode (skips website discovery as it is already known).
    - Populates country of domicile, description, and logo URL using a specialized `CompanyProfileEnrichment` schema to minimize token usage.
    - **Cost Management:**
        - Bypasses the `Mining Industry Specialist` entirely to save tokens.
        - Applies `max_iter=10` to agents to prevent runaway search loops.
        - Prioritizes `GEMINI_MODEL_ENRICHMENT` (e.g., a lighter, cheaper model) over `GEMINI_MODEL`.
    - **Status Update**: Updates `enrichment` from `"pending"` to `"success"`.
    - **Origin Preservation**: Keeps the original `"manager_affiliation"` origin.
    - **Logging**: Saves the full agent output to `Profile_Enrichment.log` in the company folder.

## Information Retrieval

The agents find the following details:
- **Company Name:** Full legal name.
- **Ticker & Exchange:** Validated against the input source.
- **Website:** Official company website (Phase 1 only).
- **Logo:** URL to the official company logo (`logo_url`).
- **Country of Domicile:** Headquarters location.
- **Description:** A brief, one-paragraph description.
- **Metals/Minerals:** Identified by the specialist for mining companies (Phase 1 only).

*Note: `name_clean` and `logo_local` are currently handled by a separate pipeline and are not populated by this workflow.*

## Specialized Agents

- **Company Profile Researcher:** Responsible for general company information and logo discovery.
- **Mining Industry Specialist:** Identifies up to 3 key metals or minerals for companies in the mining sector (Active in Phase 1 only).

## Technical Implementation

- **Main Entry Point (Phase 1):** `main.py`
- **Enrichment Entry Point (Phase 2):** `main2.py`
- **Pipeline:** `pipeline.py` (Shared logic with mode-specific task descriptions).
- **Schema:** `schema.py` defines the `CompanyProfile` Pydantic model.
- **Tools:** `tools.py` provides `ddgs_search` and `web_fetch`.

## Environment Requirements

- **Python Version:** Requires Python 3.13 (Compatibility requirement for CrewAI and Pydantic).
- **Configuration (.env):** 
    - **Loading Priority:** The workflow first looks for a `.env` in the current directory, then falls back to the parent directory (`../.env`) for any missing values. Local settings always take precedence.
    - `GEMINI_MODEL`: **Required.** The specific Gemini model to use (e.g., `gemini-1.5-pro`). No default is provided.
    - `GEMINI_MODEL_ENRICHMENT`: **Optional.** A cheaper/faster model to use specifically for Phase 2 enrichment (e.g., `gemini-3.1-flash-lite-preview`). If not set, falls back to `GEMINI_MODEL`.
    - `PROFILES_TO_PROCESS`: **Optional.** Limits the number of companies processed in a single run (default: 10000).
    - `EXCHANGE_FILTER`: **Optional.** Comma-separated list of exchanges to process.
    - `EXCHANGE_NAME_SUBSTITUTE`: **Optional.** A JSON string mapping (e.g., `{"TSX": "TSX.CA"}`) to rename exchanges.
    - `CONCURRENCY_LIMIT`: Controls parallel worker execution.
    - `MAX_CONSECUTIVE_ERRORS`: Number of errors allowed before the script terminates (default: 3).
