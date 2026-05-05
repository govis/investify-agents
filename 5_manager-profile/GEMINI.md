# Manager Profile Workflow Imperative

This workflow is designed to build and enrich detailed profiles for company officers and directors. It uses a hybrid approach: deterministic local data processing for base profiles and agentic web search for enrichment.

## Data Source
- `OfficersAndDirectors.json` in the parent directory (aggregated list of individuals).
- `Management.json` in `Companies/{ticker}.{exchange}` folders in the parent directory.
- `Profile.json` in `Companies/{ticker}.{exchange}` folders (for investment theses).

## Main Steps/Mechanisms

### 1. Phase 1: Base Profile Population (Deterministic)
- **Tool**: `tools.populate_base_profile`
- **Action**: Iterates through `OfficersAndDirectors.json`.
- **Logic**:
    - Skips generation if `Profile.json` already exists for the manager.
    - Extracts biographical data (age, background) and committee memberships from local `Management.json` files.
    - Aggregates tenure dates (start/end) for each company affiliation.
    - Includes `investment_theses` aggregated from the company profiles.
    - Sets initial `enrichment_status` to `"pending"`.

### 2. Phase 2: Agentic Enrichment (Gemini Agent)
- **Tool**: `ManagerEnrichmentPipeline` (Gemini 1.5 Pro)
- **Action**: Identifies profiles where `enrichment_status` is not `"success"`.
- **Logic**:
    - Tasks the agent with finding accurate social media profiles (LinkedIn, X/Twitter).
    - Tasks the agent with finding a professional headshot/profile picture URL.
    - Uses specialized search tools (`search_social_media`, `search_profile_picture`) that cross-reference names with company affiliations and roles for precision.
    - Updates `Profile.json` with the found data and sets `enrichment_status` to `"success"`.

## Profile Structure
Each manager has a subfolder in `Managers/` named "First Last Name". Inside, a `Profile.json` contains:
```json
{
  "name": "Full Name",
  "first_name": "First Name",
  "last_name": "Last Name",
  "age": 60,
  "age_year": 2024,
  "background": "...",
  "picture_url": "https://...",
  "commpanies": [
    {
      "name": "Company Name",
      "ticker": "TICKER",
      "exchange": "EXCHANGE",
      "title_or_role": "Role",
      "start_date": "YYYY-MM-DD",
      "end_date": null
    }
  ],
  "investment_theses": ["Thesis Name"],
  "socials": [
    { "name": "LinkedIn", "url": "https://..." },
    { "name": "X (Twitter)", "url": "https://..." }
  ],
  "committees": ["Audit Committee"],
  "enrichment_status": "success"
}
```

## Configuration (.env)
- `GOOGLE_API_KEY`: Required for Gemini and Google Search.
- `GEMINI_MODEL`: Model used for enrichment (default: `gemini-1.5-pro`).
- `CONCURRENCY_LIMIT`: Number of concurrent enrichment tasks (default: `1`).
- `MAX_CONSECUTIVE_ERRORS`: Error threshold before stopping (default: `3`).
- `PROFILES_TO_ENRICH`: 
    - `> 0`: Enrich this number of profiles in the current run.
    - `0`: Attempt to enrich all remaining pending profiles.

## Usage
Run the workflow from the `5_manager-profile` directory:
```bash
python main.py
```
The script will first ensure all base profiles exist and then proceed to enrich the pending batch based on your `.env` configuration.
