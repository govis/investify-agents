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
    - Supports `--search_picture_li` runtime flag (default: `"no"`).
- **Architecture**: **Orchestrated Multi-Agent Pipeline** using Gemini Flash models.
- **Model Config**: Requires `GEMINI_MODEL` to be set in `.env` (no default).
- **Logic Modification**: Respects `--get_picture` and `--search_picture_li` command-line arguments.
    - If `--get_picture no`: Captures image URLs (if found) but skips download validation and skips alternative search steps (2b/2c).
    - If `--get_picture yes`: Attempts sequential download and validation of all found images.
    - If `--search_picture_li no`: Skips specialized LinkedIn Image Search (2a).
    - If `--search_picture_li yes`: Performs specialized LinkedIn Image Search (2a) to find profile pictures.
- **Verification & Status Enrichment**: 
    - **Known URL Priority**: Checks `known_linkedin_urls.json` for manually verified profiles before searching.
    - **LinkedIn URL Status Check**: Performs a real-time HTTP check after verification to detect `404` (sets `profile_status: "not_found"`) or LinkedIn login walls (sets `profile_status: "private"`).
- **Refinement**: Agents strictly reject company or school pages; prioritize affiliations mentioned in the background bio.
- **Status**: Sets `enrichment_socials` to `"success"` (if verified) or `"not_found"` (if no match found).

### 3. Phase 3a: LinkedIn Profile Picture Scraper (Stealth)
- **Script**: `scrape_linkedin_pictures.py`
- **Action**: Processes profiles where `enrichment_socials` is `"success"` but the profile picture is missing.
- **Parameters**: 
    - `--retry_failed [yes|no]`: Default `"no"`. If `"no"`, only processes profiles with `picture_download_count <= 0`. If `"yes"`, ignores the attempt count.
- **Logic**:
    - **Eligibility**: Targets profiles where `picture_local` is missing **OR** the actual image file is missing.
    - **Attempt Filter**: By default, only processes if `picture_download_count` in the profile is 0 or missing (skips profiles that failed in previous runs).
    - **Status Filtering**: Automatically skips profiles where `profile_status` is `"not_found"` or `"private"` (detected in Phase 2).
    - **Multi-URL Fallback**: Iterates through ALL LinkedIn URLs in a manager's `socials` list until a valid image is found. Note that for managers with multiple profiles (e.g., Luca Maestri), the primary profile is typically marked with `"name": "LinkedIn"`.
    - **Transient Tracking**: Increments `picture_download_count` in the profile and the specific social record on every attempt; this field is **set to 0** for the profile and the matching social record once a picture is successfully saved.
    - **Validation**: Automatically detects and rejects SVG placeholders (masked as JPGs).
    - Updates `picture_local` and `picture_url`.

## Configuration & Tools

### Blacklist & Known URLs
- **Files**: 
    - `blacklist_linkedin_urls.json`: Maps `{ "LinkedIn URL": "Manager Name" }` to explicitly ignore false positives.
    - `known_linkedin_urls.json`: Maps `{ "Manager Name": "LinkedIn URL" }` for manual overrides and high-precision matches.
- **Integration**: Checked by Phase 2 (Supervisor) and Phase 3a (Stealth Scraper).

### Tools Utility
- **File**: `tools.py`
- **Functions**:
    - `get_blacklist()`: Loads and normalizes the LinkedIn URL blacklist.
    - `get_known_urls()`: Loads manually verified LinkedIn URLs for specific managers.
    - `check_url_status()`: Performs HTTP checks for 404s and Auth-Walls.
    - `download_image()`: Shared logic for image retrieval with SVG detection.
    - `populate_base_profile()`: Phase 1 deterministic logic.

## Configuration (.env)
- `GOOGLE_API_KEY`: Required for Gemini and Google Search.
- `GEMINI_MODEL`: **Mandatory**. Cost-effective model for enrichment (e.g., `gemini-flash-latest`).
- `GEMINI_MODEL_SEARCH_GROUNDING`: Optional. Specialized model for search grounding (defaults to `GEMINI_MODEL`).
- `CONCURRENCY_LIMIT`: Number of concurrent enrichment tasks (default: `5`).
- `MAX_CONSECUTIVE_ERRORS`: Error threshold before stopping (default: `3`).
- `PROFILES_TO_ENRICH`: 
    - `> 0`: Limit processing to this number of profiles.
    - `0`: Attempt to process all eligible profiles.

