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

- **Phase 2: Multi-Agent LinkedIn & Image Enrichment (V2)**
- **Script**: `main.py` (via `agent_pipeline.py`)
- **Execution**: 
    - Supports targeted enrichment via `--manager "Name"` flag.
    - Supports `--get_picture` runtime flag (default: `"no"`).
    - Supports `--search_picture_li` runtime flag (default: `"no"`).
    - Supports `--reprocess_not_found` runtime flag (default: `"no"`).
- **Inputs**: 
    - Individual `Profile.json` for each manager.
    - Scans for profiles where `enrichment_socials` is missing, `"pending"`, or `"error"` (or `"not_found"` if `--reprocess_not_found` is enabled).
    - Fields used: `name`, `age`, `background`, and `company_affiliations` (names and roles).
- **Outputs**:
    - Updates `socials` list in `Profile.json` with LinkedIn data.
    - Updates `enrichment_socials` status (`success`, `not_found`, or `error`).
    - Captures `picture_url_li_profile` and `potential_picture_url`.
- **Architecture**: **Orchestrated Multi-Provider Pipeline**.
    - **LLM_PROVIDER**: Switch between `gemini` and `groq` (high-speed inference).
    - **VALIDATE_PROFILE_USING**: 
        - `CLOAK_BROWSER`: Uses a local Python scraper/stealth-fetcher to retrieve profile data before LLM analysis.
- **Search & Validation Mechanics**:
    1. **Identity Slimming**: Filters the manager's profile down to a "Slim Context" (essential fields only) to minimize token cost and stay within TPM limits.
    2. **Sliding Window Search**: 
        - Performs a manual DuckDuckGo search for LinkedIn profiles and passes snippets to the LLM.
    3. **Verification Loop**: 
        - Iterates through the top 3 candidates.
        - **Grounding**: The LLM reads the scraped content from the Cloak Browser to cross-reference the manager's background and affiliations.
        - **Precision Filtering**: Strictly rejects company/school pages; prioritizes unique name matches.
    4. **Image Retrieval**:
        - Captures the `media.licdn.com` pattern from the verified profile.
        - If missing, optionally triggers a specialized LinkedIn Image Search (Agent 2a) or IR searches (2b/2c).
- **Cost Management & Fail-Safes**:
    - **Global Budget**: Restricts total agent calls per manager to **10** (`MAX_AGENT_CALLS_PER_MANAGER`).
    - **Dynamic Rate Limiting (RPM)**: sliding window throttler based on `LLM_RPM`.
    - **Dynamic Chunking (TPM)**: Calculates safe character limits (`MAX_CHARS`) for input truncation.
    - **Image Optimization**: Skips redundant image search calls if a picture is found during verification.
    - **Deterministic Execution**: Uses `temperature: 0.0` and `max_output_tokens: 2048`.

### 3. Phase 3a: LinkedIn Profile Picture Scraper (Stealth)
- **Script**: `scrape_linkedin_pictures.py`
- **Action**: Processes profiles where `enrichment_socials` is `"success"` but the profile picture is missing. Uses shared `tools.get_linkedin_profile_picture` for scraping and downloading.
- **Parameters**: 
    - `--scrape_method [simple|cloak_browser]`: Default `"simple"`. If `"simple"`, uses the current method to open web page. If `"cloak_browser"`, uses Cloak browser.
    - `--linkedin_user [anonymous|user_name]`: Default `"anonymous"`. If `"anonymous"`, opens linkedin profiles anonymously. If `"user_name"`, signs in to linkedin with the `"user_name"`. User name is only supported with `cloak_browser` and includes human mimicry (random delays, hourly limits).
    - `--profile_visibility [public|private|all]`: Default `"public"`. Filters by the `profile_status` detected in Phase 2.
    - `--retry_failed [no|yes]`: Default `"no"`. If `"no"`, only processes profiles with `picture_download_count <= 0` and `profile_status` is NOT `"not_found"`. If `"yes"`, ignores attempt count and includes `"not_found"`.
- **Logic**:
    - **Eligibility**: Targets profiles where `picture_local` is missing **OR** the actual image file is missing.
    - **Multi-URL Fallback**: Iterates through ALL LinkedIn URLs in a manager's `socials` list until a valid image is found.
    - **Transient Tracking**: Increments `picture_download_count` on every attempt; this field (and `profile_status`) is cleared once a picture is successfully saved.
    - **Status Filtering**: Updates `profile_status` to `"private"` (if auth wall detected) or `"not_found"` (if 404). If a status changes (e.g., private to not_found), `picture_download_count` is reset to 0 to enable fresh attempts.
    - **Validation**: Automatically detects and rejects SVG placeholders (masked as JPGs).
    - Updates `picture_local` and `picture_url`.

### 4. Phase 4: Reprocess Not Found
- **Script**: `reprocess_not_found.py`
- **Action**: Searches for and validates LinkedIn profiles for managers previously marked as `"not_found"`.
- **Logic**:
    - Scans profiles based on `--has_profile` (targets `enrichment_socials` or `profile_status`).
    - Uses `tools.search_social_media` to discover new potential LinkedIn URLs.
    - Validates identity using the shared `tools.LinkedInVerifierAgent`.
    - Scrapes and downloads pictures using `tools.get_linkedin_profile_picture`.
- **Behavior**: Shares human mimicry (random delays, hourly limits) via `tools.apply_human_mimicry`.

### Utilities: manager_picture_google_search.py
- **Script**: `manager_picture_google_search.py`
- **Action**: A standalone utility to perform broad Google Image searches for a manager's picture (replaces the old fallback logic in scraping scripts).

### Scraping & Stealth Mechanisms
- **Consolidation**: Core scraping, downloading, and human mimicry logic is consolidated in `tools.py` for shared use across Phase 3a and Phase 4.
- **Cloak Browser Method**: Used for authenticated sessions to bypass anti-bot detections (fingerprinting, behavioral analysis) and access private profiles.

### Session Management
For authenticated scraping (Phase 3a/4 with `--scrape_method cloak_browser`), use:
### Session Management
This project uses the **Cloak Browser** with persistent `user_data_dir` to maintain authenticated LinkedIn sessions. All sessions are stored in the `./sessions/{linkedin_user}/` directory.

- **Initialization (Login)**: 
    Run `python linkedin_signin.py --user {username}`. Follow instructions to log in and save state.
- **Termination (Logout & Cleanup)**:
    Run `python linkedin_signout.py --user {username}`. This logs out of LinkedIn and deletes the session data folder.
- **Persistence**: Scrapers automatically load the persistent context based on the `--linkedin_user` flag provided at runtime.

## Data Persistence Standard (Mandatory)
To prevent the loss of scraping status and tracking metrics (e.g., `profile_status`, `picture_download_count`), this project enforces an **Immediate Persistence Standard**:

1.  **Atomicity**: Any modification to a manager's `Profile.json` object (such as updating a status or incrementing a counter) must be persisted to disk **immediately** following the update.
2.  **No Lazy Saving**: Do not wait until the end of a loop or script execution to save the profile. If a state change occurs, commit it to `Profile.json` before moving to the next task or exiting the function scope.
3.  **Error Recovery**: Scripts should save state before and after network-dependent actions (like scraping or validation) to ensure that partial progress (like marking a profile as 'private') is never lost due to subsequent errors or script termination.

Any future code changes or refactors **must** maintain these save points to ensure status and count persistence.

### Blacklist & Known URLs
- **Files**: 
    - `blacklist_linkedin_urls.json`: Maps `{ "LinkedIn URL": "Manager Name" }` to explicitly ignore false positives.
    - `known_linkedin_urls.json`: Maps `{ "Manager Name": "LinkedIn URL" }` for manual overrides and high-precision matches.
- **Integration**: Checked by Phase 2 (Supervisor), Phase 3a, and Phase 4.

### Tools Utility
- **File**: `tools.py`
- **Functions**:
    - `get_linkedin_profile_picture(page, profile_path, url, matching_social)`: Unified scraping, accessibility checking, and downloading.
    - `apply_human_mimicry(...)`: Shared delays/rate limiting logic.
    - `search_social_media(...)`: Discovery utility.
    - `LinkedInVerifierAgent`: Shared identity verification agent.
    - `download_image(...)`: Shared image retrieval and SVG detection.
    - `check_url_status(...)`: Performs HTTP checks for 404s and Auth-Walls.

## Configuration (.env)
- `GOOGLE_API_KEY`: Required for Gemini and Google Search.
- `GEMINI_MODEL`: **Mandatory**. Cost-effective model for enrichment (e.g., `gemini-flash-latest`).
- `CONCURRENCY_LIMIT`: Number of concurrent enrichment tasks (default: `5`).
- `MAX_CONSECUTIVE_ERRORS`: Error threshold before stopping (default: `3`).
- `PROFILES_TO_ENRICH`: 
    - `> 0`: Limit processing to this number of profiles.
    - `0`: Attempt to process all eligible profiles.

