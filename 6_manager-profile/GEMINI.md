# Manager Profile Workflow Imperative

This workflow builds and enriches detailed profiles for company officers and directors. It uses a cost-optimized hybrid approach: deterministic local data processing for base profiles, Python-driven web search for candidates, and single-turn agentic validation for high precision.

## Data Source
- `OfficersAndDirectors.json` in the parent directory (aggregated list of individuals).
- `Management.json` in `Companies/{ticker}.{exchange}` folders in the parent directory.
- `Profile.json` in `Companies/{ticker}.{exchange}` folders (for investment theses).

## Main Steps/Mechanisms

### 1. Phase 1: Base Profile Population (Deterministic)
- **Script**: `populate_base_profiles.py`
- **Action**: Iterates through `OfficersAndDirectors.json`.
- **Logic**:
    - Skips generation if `Profile.json` already exists for the manager.
    - Extracts biographical data and committee memberships from local `Management.json` files.
    - Aggregates tenure dates and `investment_theses`.
    - Sets initial `enrichment_status` to `"pending"`.

### 2. Phase 2: Multi-Agent LinkedIn & Image Enrichment (V2)
- **Script**: `main.py` (via `agent_pipeline.py`)
- **Execution**: 
    - Supports targeted enrichment via `--manager "Name"` flag.
    - Prioritizes verifying existing `socials` URLs before attempting new searches.
- **Architecture**: **Orchestrated Multi-Agent Pipeline** using Gemini 2.0/2.5 Flash.
- **Data Integration**: Automatically retrieves `name_clean` and `website` from `Companies/{ticker}.{exchange}/Profile.json` for enhanced search precision.
- **Agents**:
    - **Supervisor Agent**: Orchestrates the workflow and manages state/fallbacks.
        - **Sequential Validation**: Attempts to download images in priority order: Profile (Agent 3) -> Search (Agent 4a) -> IR Site (Agent 4b) -> Broad (Agent 4c).
    - **LinkedIn Search Agent**: Finds candidate profiles based on name, clean company names, and roles.
    - **LinkedIn Verifier Agent**: Uses **Google Search Grounding** to visit profiles and verify matches.
        - **Capture**: Captures `person_name` and `company_name` exactly as they appear on LinkedIn, prioritizing the target company.
        - **Image Priority**: Extracts `media.licdn.com/dms/image/v2/` URLs into `picture_url_li_profile`.
    - **Image Search Agent (4a)**: Performs broad searches (e.g., "Name Company") to identify LinkedIn profile pictures from search results, storing them in `picture_url_li_search`.
    - **Image Fallback Agents (4b, 4c)**: Targeted searches on IR websites and broad professional domains if LinkedIn sources fail validation or download.

### 3. Phase 3: Profile Picture Download (Post-processing)
- **Script**: `download_profile_pictures.py`
- **Action**: Processes profiles where `enrichment_status` is `"success"` but `picture_local` is missing.
- **Logic**:
    - **Download**: Prioritizes downloading the `potential_picture_url` captured in Phase 2a.
    - **Scraping**: Attempts a direct LinkedIn scrape if no potential URL exists or if direct download fails.
    - **Validation**: Automatically detects and rejects SVG placeholders (masked as JPGs), treating them as missing files.
    - **Management**: Updates `picture_local`, `has_picture`, and `picture_download_count`.

## Scripts
- `populate_base_profiles.py`: Phase 1 - Deterministic profile creation.
- `main.py`: Phase 2 - High-precision LinkedIn validation.
- `retry_notfound.py`: Phase 2 - Retry enrichment for profiles marked `"not_found"`.
- `enrich_profile_with_google_search.py`: Phase 2a - Grounded capture of `shrink_200_200` headshots.
- `download_profile_pictures.py`: Phase 3 - Final image download and file management.

## Configuration (.env)
- `GOOGLE_API_KEY`: Required for Gemini and Google Search.
- `GEMINI_MODEL`: Model used for validation (default: `gemini-2.5-flash`).
- `CONCURRENCY_LIMIT`: Number of concurrent enrichment tasks (default: `5`).
- `MAX_CONSECUTIVE_ERRORS`: Error threshold before stopping (default: `3`).
- `PROFILES_TO_ENRICH`: 
    - `> 0`: Enrich this number of profiles in the current run.
    - `0`: Attempt to enrich all remaining pending profiles.
