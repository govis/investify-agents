# Logo Workflow Imperative

This workflow is designed to download logo images for publicly traded companies.

## Data Source
- `Profile.json` in `Companies/{ticker}.{exchange}` folder in parent directory.
- Fields: `name`, `ticker`, `website`.

## Main Steps/Mechanisms
1. **Searching `companieslogo.com`**: Primary source for official logos. Uses multiple query variations and robust verification.
2. **Website Verification/Download**: Checking the official website for logos. Handles lazy-loading, data URIs (Base64), and uses a sophisticated scoring system.
3. **Broader Internet Search**: Using search engines to find official logos, transparent PNGs, or SVGs.
4. **AI Generation (Imagen)**: Generating a placeholder logo based on visual details gathered from the web search.

## Search Logic
- **Searchable Term Generation (Three-Tier Filtering)**:
  - **Tier 1: Always Exclude from End (`EXCLUDE_END_WORDS`)**:
    - Checks for exact string matches at the end of the name (e.g., `["Inc", "Ltd.", "Corp", "N.V.", "Aktiengesellschaft"]`).
    - Matching is case-insensitive.
    - **Flexibility**: If a word in the list (e.g., "Inc") does not end in a dot, it will also match a name ending in that word with a dot (e.g., "Inc.").
    - If a match is found, the suffix is removed, followed by stripping trailing spaces, commas, and dots.
    - This process runs **twice** to handle nested suffixes (e.g., "Amazon.com, Inc." -> "Amazon.com" -> "Amazon").
  - **Tier 2: Noise Words Removal (`NOISE_WORDS`)**:
    - Parses a comma-separated list (e.g., "the,and").
    - Removes these words from anywhere in the name, but **only if** at least 2 other significant words remain after removal.
  - **Tier 3: Conditional End Exclusion (`CONDITIONAL_EXCLUDE_WORDS`)**:
    - Parses a comma-separated list (e.g., "limited,company,corporation").
    - Removes these words strictly from the end of the remaining name, one by one.
    - A word is removed **only if** at least 2 other "truly significant" words (not noise, not conditional) remain in the final term.
- **Normalization for Matching**:
  - The generated searchable term and all search result text (URLs/Titles) are normalized before matching.
  - **Accent Removal**: Diacritics are decomposed and stripped (e.g., "Réalis" -> "realis", "Química" -> "quimica").
  - **ASCII Conversion**: Text is converted to lowercase ASCII for robust matching across different character sets.
- **Search Term Generation**:
  - For Mechanism 1, multiple variations are tried: `{name} {ticker} logo`, `{ticker} logo`, `{name} logo`, and `{first_word} {ticker} logo`.
  - For general matching, if 2 or more words remain, the search is performed using the **first two words**. If only one word remains, that word is used.
- **Verification & Matching (Mechanism 1)**:
    - **Ticker Matching**: Uses regex with word boundaries to find tickers in titles/URLs (prevents false positives like `AA` matching `AAL`).
    - **Domain Matching**: High-confidence match if the company's website domain part (e.g., `siemens` from `siemens.com`) appears in the target URL.
    - **Short Name Protection**: For very short names (<= 3 chars, e.g., "LG"), additional evidence (domain or multiple part matches) is required to avoid matching massive unrelated brands.
- **Structural Scoring & Extraction (Mechanism 2)**:
  - **Visual Prominence**: Images in the `<header>`, `<nav>`, or wrapped in a link to the homepage (very strong signal) receive significant score bonuses (+40 to +50).
  - **Contextual Matching**: Incorporates the website's domain part into the name-matching logic for image paths and alt text.
  - **Lazy Loading & Data URIs**: Specifically extracts from `data-src`, `data-lazy-src`, `srcset`, etc., and supports decoding Base64 data URIs.
  - **Ad-Filter Safe**: Uses word boundaries for ad-filtering (e.g., `\bads\b`) to avoid blocking legitimate WordPress `uploads` directories.
  - **Social Media Penalties**: Heavy penalties (-150) are applied to images containing social media keywords (twitter, facebook, linkedin, etc.) in their path, alt text, or parent link.
- **Configuration Validation**:
  - Critical parameters (`EXCLUDE_END_WORDS`, `NOISE_WORDS`, `CONDITIONAL_EXCLUDE_WORDS`) are strictly validated. Missing or malformed configuration will raise a `ValueError`.
- **Search Overrides**:
  - Specific search terms for `companieslogo.com` can be overridden via `COMPANIESLOGO_SEARCH_OVERRIDES` in `.env`.
  - Format: `{"TICKER.EXCHANGE": "Exact Search Term"}`.

## Logging & Output
- **Console Window**: Concise, showing the current company (using `TICKER.EXCHANGE` format), mechanism, and its specific query/website.
- **Log File**: A detailed `logo_workflow.log` file is written to each company folder.
- **Image Filename**: All logos must be saved as `logo` (+ appropriate extension) in the company folder.
- **Profile Update**: 
  - `name_clean`: Updated in `Profile.json` with the filtered searchable term (core parts) before search commences.
  - `logo_local`: Upon successful download/generation, updated with the filename (e.g., `"logo_local": "logo.png"`).
  - `logo_color`: Updated if a "white" logo variation is detected during search or download.
