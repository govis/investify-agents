# Logo Workflow Imperative

This workflow is designed to download logo images for publicly traded companies.

## Data Source
- `Profile.json` in `Companies/{ticker}.{exchange}` folder in parent directory.
- Fields: `name`, `ticker`, `website`.

## Main Steps/Mechanisms
1. **Searching `companieslogo.com`**: Primary source for official logos.
2. **Website Verification/Download**: Checking the official website for logos (icons, OG images, or relevant `<img>` tags).
3. **Broader Internet Search**: Using search engines to find official logos, transparent PNGs, or SVGs.
4. **AI Generation (Imagen)**: Generating a placeholder logo based on visual details gathered from the web search.

## Search Logic
- **Searchable Term Generation (Three-Tier Filtering)**:
  - **Tier 1: Always Exclude from End (`EXCLUDE_END_WORDS`)**:
    - Checks for exact string matches at the end of the name (e.g., `["Inc", "Ltd.", "Corp", "N.V."]`).
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
  - After filtering, if 2 or more words remain, the search is performed using the **first two words**. If only one word remains, that word is used.
- **Structural Scoring (Mechanism 2)**:
  - **Visual Prominence**: Images in the `<header>` or wrapped in a link to the homepage (very strong signal) receive significant score bonuses.
  - **Social Media Penalties**: Heavy penalties are applied to images containing social media keywords (twitter, facebook, linkedin, etc.) in their path or alt text to prevent incorrect icon retrieval.
- **Configuration Validation**:
  - Critical parameters (`EXCLUDE_END_WORDS`, `NOISE_WORDS`, `CONDITIONAL_EXCLUDE_WORDS`) are strictly validated. Missing or malformed configuration will raise a `ValueError`.
- **Search Overrides**:
  - Specific search terms for `companieslogo.com` can be overridden via `COMPANIESLOGO_SEARCH_OVERRIDES` in `.env`.
  - Format: `{"TICKER.EXCHANGE": "Exact Search Term"}`.

## Logging & Output
- **Console Window**: Should be concise, showing the current company, mechanism, and its specific query/website.
- **Log File**: A detailed `logo_workflow.log` file is written to each company folder.
- **Image Filename**: All logos must be saved as `logo` (+ appropriate extension) in the company folder.
- **Profile Update**: Upon successful download/generation, attribute `logo_local` in `Profile.json` is updated with the filename (e.g., `"logo_local": "logo.png"`).
