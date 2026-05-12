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
    - **Note**: Performs a clean initialization; no longer sets a "pending" status.
    - **Fields**: Uses `company_affiliations` for company records.

### 2. Phase 2: Multi-Agent LinkedIn & Image Enrichment (V2)
- **Script**: `main.py` (via `agent_pipeline.py`)
- **Execution**: 
    - Supports targeted enrichment via `--manager "Name"` flag.
    - Supports `--get_picture` runtime flag (default: `"no"`).
- **Architecture**: **Orchestrated Multi-Agent Pipeline** using Gemini Flash models.
- **Model Config**: Requires `GEMINI_MODEL` to be set in `.env` (no default).
- **Logic Modification**: Respects `--get_picture` command-line argument.
    - If `--get_picture no`: Captures image URLs (`picture_url_li_profile`, `picture_url_li_search`) but skips download validation and skips alternative search steps (4b/4c).
    - If `--get_picture yes`: Attempts sequential download and validation of all found images.
- **Refinement**: Agents strictly reject company or school pages; prioritize affiliations mentioned in the background bio.
- **Status**: Sets `enrichment_socials` to `"success"` (if verified) or `"not_found"` (if no match found).

### 3. Phase 3a: LinkedIn Profile Picture Scraper (Stealth)
- **Script**: `scrape_linkedin_pictures.py`
- **Action**: Processes profiles where `enrichment_socials` is `"success"` but the profile picture is missing.
- **Parameters**: 
    - `--retry_failed [yes|no]`: Default `"no"`. If `"no"`, only processes profiles with `picture_download_count <= 0`. If `"yes"`, ignores the attempt count.
- **Logic**:
    - Targets profiles where `picture_local` is missing **OR** the actual image file is missing.
    - Uses **CloakBrowser** (Stealth Chromium) to bypass anti-bot mechanisms.
    - **Transient Tracking**: Increments `picture_download_count` on every attempt; this field is **fully purged** (top-level and nested social records) once a picture is successfully saved.
    - **Validation**: Automatically detects and rejects SVG placeholders (masked as JPGs).
    - Updates `picture_local` and `picture_url`.

### 4. Phase 3b: Profile Picture Download (EXPERIMENTAL)
- **Script**: `download_profile_pictures.py`
- **Warning**: **NEEDS MORE WORK - DO NOT RUN!**
- **Action**: Final fallback for downloading images from `potential_picture_url` or performing a basic LinkedIn scrape (non-stealth).
- **Logic**: Logic-synchronized with Phase 3a but currently deferred.

## Scripts
- `populate_base_profiles.py`: Phase 1 - Deterministic profile creation.
- `main.py`: Phase 2 - High-precision LinkedIn validation.
- `scrape_linkedin_pictures.py`: Phase 3a - Stealth LinkedIn image scraping.
- `download_profile_pictures.py`: Phase 3b - (EXPERIMENTAL) Final image download.

## Configuration (.env)
- `GOOGLE_API_KEY`: Required for Gemini and Google Search.
- `GEMINI_MODEL`: **Mandatory**. Cost-effective model for enrichment (e.g., `gemini-flash-latest`).
- `GEMINI_MODEL_SEARCH_GROUNDING`: Optional. Specialized model for search grounding (defaults to `GEMINI_MODEL`).
- `CONCURRENCY_LIMIT`: Number of concurrent enrichment tasks (default: `5`).
- `MAX_CONSECUTIVE_ERRORS`: Error threshold before stopping (default: `3`).
- `PROFILES_TO_ENRICH`: 
    - `> 0`: Limit processing to this number of profiles.
    - `0`: Attempt to process all eligible profiles.
