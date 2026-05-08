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

### 2. Phase 2: High-Precision LinkedIn Enrichment
- **Script**: `main.py` (standard) or `retry_notfound.py` (retries)
- **Tool**: Gemini 2.5 Flash with **Pydantic Structured Output**.
- **Action**: Processes profiles where `enrichment_status` is `"pending"`.
- **Logic**:
    - **Validation**: Broad search using snippets to find and verify the correct LinkedIn profile.
    - **Schema**: Uses Pydantic to enforce consistent JSON responses.
    - **Status Updates**: Sets `"success"` if a verified LinkedIn profile is found; otherwise `"not_found"`.
    - **Sequential Dependency**: This phase is typically run **first** to establish the verified identity (LinkedIn URL) before visual enrichment.

### 3. Phase 2a: Grounded Image Capture
- **Script**: `enrich_profile_with_google_search.py`
- **Tool**: Gemini 2.0 Flash with **Google Search Grounding** and Pydantic.
- **Action**: Processes profiles with `"success"` status that have a LinkedIn URL but no `potential_picture_url`.
- **Logic**:
    - **Grounded Verification**: Uses Gemini's search tool to "visit" the verified LinkedIn profile page.
    - **Image Grabbing**: Specifically extracts the `shrink_200_200` version of the profile display photo from the `media.licdn.com/dms/image/v2/` path.
    - **Quota Management**: Since grounding has lower rate limits, this script only targets already-validated identities from Phase 2.

### 4. Phase 3: Profile Picture Download (Post-processing)
- **Script**: `download_profile_pictures.py`
- **Action**: Processes profiles where `enrichment_status` is `"success"` but `picture_local` is missing or is an invalid placeholder.
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
