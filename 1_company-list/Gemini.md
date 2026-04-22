# Agentic Workflow Imperative: Company List Identification & Hyperlinking

## Objective
Identify and create a comprehensive list of publicly traded companies mentioned across a set of investment theses, and update the source markdown files with standardized hyperlinks for each company mention.

## Source Information
- **Location:** `../Theses/` and its subfolders.
- **Format:** Markdown files.
- **Thematic Scope:** AI, Defense, Electrification, Gold, Nuclear, Reshoring.

## Output Requirements
1.  **Consolidated Data:** `../CompanyList.json`.
2.  **Hyperlinked Markdown:** `../ThesesWithLinks/` containing updated markdown files with company mentions formatted as `[Company Name](/company/TICKER.EXCHANGE)`.

## Processing Logic (Dynamic SDK Pipeline)
The pipeline is optimized for maximum reliability and throughput by communicating directly with LLM providers using dynamic throttling:

1.  **Dynamic Rate Limiting (RPM):** Uses an asynchronous sliding window rate limiter based on the `LLM_RPM` parameter in `.env`. The script dynamically pauses only when the request limit within a rolling 60-second window is reached.
2.  **Dynamic Chunking (TPM):** Automatically calculates the ideal markdown chunk size based on `LLM_TPM` and `LLM_RPM`.
    *   **Formula:** `max_chars = (TPM / RPM - 700_tokens_buffer) * 4_chars_per_token`.
    *   Capped between 500 and 8,000 characters to ensure stability.
3.  **Company Extraction & Mention Mapping:** The LLM identifies company details and specific text strings (`mentions`) where they appear.
4.  **Robust Python-Side Hyperlinking:**
    *   **Double-Link Prevention:** Uses a single-pass regex to ensure that in patterns like `Name (Ticker)`, only the name is hyperlinked.
    *   **Nested Link Prevention:** Prevents hyperlinking text that is already part of a markdown link.
    *   **Exchange Filter:** Respects the `EXCHANGE_FILTER` setting.

## Environment Requirements
- **Python Version:** Python 3.13+ (Fully compatible with Python 3.14).
- **Dependencies:** `google-genai`, `groq`, `python-dotenv`, `beautifulsoup4`.
- **Configuration (.env):**
    *   `LLM_PROVIDER`: `gemini` or `groq`.
    *   `LLM_RPM`: Requests per minute limit.
    *   `LLM_TPM`: Tokens per minute limit.
    *   `CONCURRENCY_LIMIT`: Max simultaneous requests.
