# Agentic Workflow: C-Suite and Board of Directors Extraction

## Goal
Retrieve and verify information about C-suite executives and board of directors members for publicly traded companies.

## Tech Stack
- **Framework:** CrewAI
- **Schema/Validation:** Pydantic (v2+)
- **Python Version:** 3.13 (Required for CrewAI/Pydantic compatibility)

## Phases

### Phase 1: C-Suite and Board Extraction (Agentic)
- **Script**: `main.py`
- **Action**: Retrieves and verifies information about C-suite executives and board members for publicly traded companies.
- **Logic**:
  - Uses CrewAI with specialized agents to extract data from official (EDGAR, SEDAR) and semi-official sources.
  - Cross-references company websites to confirm current affiliation.
  - Outputs results to `Management.json` within the company's directory in `../Companies/`.

### Phase 2: Management Aggregation & Profile Creation (Deterministic)
- **Script**: `aggregate_management.py`
- **Action**: Aggregates all extracted individuals into a unified registry (`OfficersAndDirectors.json`) and creates individual manager profiles.
- **Logic**:
  - Iterates through the `../Companies/` directory.
  - Extracts executives and directors from `Management.json` and `investment_theses` from `Profile.json`.
  - Captures the company `website` for each affiliation.
  - Aggregates tenure dates, roles, and company affiliations for each unique individual.
  - Saves the final list to `../OfficersAndDirectors.json`.
  - Creates/updates individual `Profile.json` files for each manager in `../Managers/<Manager_Name>/`, populating biographical data, committees, and company affiliations (including websites).

### Phase 3: Manager Profile Enrichment (Agentic)
- **Script**: `main_enrich.py`
- **Action**: Enriches individual manager profiles with additional company affiliations found across public markets.
- **Logic**:
  - Iterates through the `../Managers/` directory.
  - Skips profiles where `enrichment_company_affiliations == "success"`.
  - Uses a cost-efficient CrewAI pipeline (prioritizing `gemini-3.1-flash-lite-preview` via `GEMINI_MODEL_ENRICHMENT`):
    - **Enrichment Supervisor**: Oversees task coordination.
    - **IR Research Specialist**: Performs targeted, high-authority searches (max 5) for senior/director roles.
    - **Affiliation Validator**: Verifies the found affiliations and company details.
  - Implements **max_iter=10** on agents to prevent runaway search loops and excessive API costs.
  - Filters results by `EXCHANGE_FILTER` specified in the parent directory's `.env`.
  - Captures and validates "name", "ticker", "exchange", and "website" for new affiliations.
  - Updates the `company_affiliations` list in each manager's `Profile.json` and sets `"enrichment_company_affiliations": "success"` for completed profiles.
  - Automatically cleans up legacy status fields (`enrichment_status`, `enrichment_step`) during processing.
  - Supports `MANAGERS_TO_ENRICH` environment variable for controlled batch processing.
  - Generates an `Enrichment.log` for each manager processed.

## Data Flow
- **Inputs:** `Profile.json` files located in `../Companies/<Company_Name>/` directory (parent directory of the project).
- **Outputs:**
  - `Management.json`: Structured data following `schema.py`.
  - `Management.log`: Detailed log of search, extraction, and errors.

## Data Retrieval Strategy
1. **Official Sources (Primary):**
   - **EDGAR:** For US-domiciled companies or companies listed on **NYSE/NASDAQ** (10-K, DEF 14A, etc.).
   - **SEDAR:** For Canada-domiciled companies or companies listed on **TSX/TSXV/CSE**.
   - **International Filings:** For other global companies, utilizing annual reports and regulatory disclosures from local jurisdictions.
2. **Semi-Official Sources (Secondary):**
   - News releases (announcements of appointments or departures).
   - Management proxy documents.
3. **Verification (Critical):**
   - Cross-reference company official websites to confirm current affiliation.
   - If not current, identify the `end_date`.

## Agent Specialization & Routing
- **EDGAR Filing Specialist:** Used if Country = "UNITED STATES" or Exchange ∈ {"NYSE", "NASDAQ"}.
- **SEDAR+ Filing Specialist:** Used if Country = "CANADA" or Exchange ∈ {"TSX", "TSXV", "CSE"}.
- **International Listed Security Specialist:** Used for all other international companies.
- **Research Manager:** Coordinates extraction and ensures schema adherence.

## Logic & Rules
- **verified_current Flag:** Set to `true` ONLY if the person is verified as currently affiliated via the company website or the latest official filing.
- **End Date:** Must be identified and recorded if the person is no longer with the company/board.
- **Sources Tracking:** All sources that provided data points must be added to the `sources` list in `Management.json`.
- **Comprehensive Logging:** `Management.log` must capture the full extraction process, including successful hits and any errors encountered during the search.
- **Name Cleaning Utility (`clean_names.py`):**
  - An on-demand script used to normalize executive and director names.
  - Normalizes names with initials or nicknames (e.g., "John S. (John) Doe" -> "John Doe").
  - Preserves the original extracted name in the `name_original` field.
  - Usage: `python clean_names.py [Company_Folder]` (Optional: provide a specific company folder name like `AAPL.NASDAQ` to process only that company).
