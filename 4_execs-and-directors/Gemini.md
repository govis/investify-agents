# Agentic Workflow: C-Suite and Board of Directors Extraction

## Goal
Retrieve and verify information about C-suite executives and board of directors members for publicly traded companies.

## Tech Stack
- **Framework:** CrewAI
- **Schema/Validation:** Pydantic (v2+)
- **Python Version:** 3.13 (Required for CrewAI/Pydantic compatibility)

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
