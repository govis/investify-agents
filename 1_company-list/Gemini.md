yes# Agentic Workflow Imperative: Company List Identification

## Objective
Identify and create a comprehensive list of publicly traded companies mentioned across a set of investment theses.

## Source Information
- **Location:** `../Theses/` and its subfolders.
- **Format:** Markdown files.
- **Thematic Scope:** 6 Investment Theses:
  1. AI
  2. Defense
  3. Electrification
  4. Gold
  5. Nuclear
  6. Reshoring

## Output Requirements
- **File:** `../CompanyList.json`
- **Schema:** Defined in `schema.py` (utilizing `CompanyList`, `CompanyReference`, and `ThesisReference`).
- **Data Points per Company:**
  - Company Name
  - Ticker
  - Exchange
  - Associated Theses (List)
  - Company Type (Specific to each associated thesis)

## Consolidation & Refinement Logic
- **New Company:** Add to the list with all extracted information.
- **Existing Company, New Thesis:** Append the new thesis and the company's specific type for that thesis to the existing company record.
- **Existing Company, Existing Thesis:** Re-evaluate and double-check the company type to ensure it is refined and accurate based on the new context.

## Environment Requirements

- **Python Version:** This workflow requires Python 3.13. Higher versions (like Python 3.14+) currently encounter compatibility issues with CrewAI and Pydantic dependencies.
