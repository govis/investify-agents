# From $20 to $0.27: How We Reduced AI Processing Costs by 98% Through Architectural Simplification

In the rush to build "Agentic" workflows, it is remarkably easy to fall into the trap of over-engineering. We recently took a production-grade data extraction pipeline from a **$20.00** run-cost down to just **$0.27**—a staggering 98.6% reduction—without changing our data inputs or sacrificing the quality of our outputs. 

The secret wasn't just switching to a cheaper model; it was a fundamental architectural shift that moved logic away from the LLM and back into the hands of efficient code.

## The Challenge: Extract, Consolidate, and Hyperlink
Our task was straightforward but token-intensive: 
1. Scan a large corpus of investment theses (Markdown files).
2. Identify every publicly traded company mentioned.
3. Consolidate them into a structured JSON list (Name, Ticker, Exchange, and Thesis-specific "Type").
4. Rewrite the original Markdown files, turning every company mention into a standardized hyperlink: `[Company Name](/company/TICKER.EXCHANGE)`.

## The "Before" Architecture: The Agentic Over-Engineered Trap
Our initial implementation used what many consider the modern standard for AI apps:
- **Framework:** CrewAI (Agentic Orchestration).
- **Validation:** Pydantic (Strict schema enforcement).
- **Mechanism:** We asked the LLM to process a text chunk and return a JSON object containing the data *and the fully rewritten markdown text*.

### Why this cost $20:
1. **Output Token Bloat:** LLM providers typically charge 3x to 4x more for output tokens than input tokens. By asking the LLM to "rewrite" the markdown, we were paying premium rates for it to repeat back data we already had.
2. **Context Overhead:** Agentic frameworks add "backstory," "task descriptions," and "formatting instructions" to every call. While useful for complex reasoning, this adds thousands of hidden tokens to every request.
3. **Truncation Failures:** Because the output JSON (containing the rewritten text) was so large, it frequently hit model output limits, causing the JSON to break and forcing expensive retries.

## The "After" Architecture: Direct SDK & Mention Mapping
We stripped the system down to its bare essentials. We removed CrewAI and Pydantic, replacing them with a custom Python pipeline using the direct Gemini and Groq SDKs.

### The Game-Changing Shift: Mention Mapping
Instead of asking the LLM to rewrite the text, we asked it for a **Mention Map**.
We told the LLM: *"Don't rewrite the file. Just give me a JSON list of the exact strings where you found these companies."*

**New Output Format:**
```json
{
  "companies": [
    {
      "name": "Nvidia",
      "ticker": "NVDA",
      "exchange": "NASDAQ",
      "mentions": ["Nvidia", "NVDA", "Nvidia Corp"]
    }
  ]
}
```

We then built a robust **Regex Engine in Python** to handle the hyperlinking. Python is infinitely faster and free at replacing strings. It also allowed us to implement complex logic (like "Double-Link Prevention") that is difficult for LLMs to follow consistently.

### Dynamic Throttling (RPM/TPM Optimization)
To support different API tiers, we built a sliding-window rate limiter. Instead of hardcoded delays, the script now calculates the ideal chunk size based on the model's **Tokens Per Minute (TPM)** and **Requests Per Minute (RPM)** limits. 

This ensures that we always operate at the absolute maximum throughput of the API key without ever triggering a `429 Rate Limit` error.

## The Model Factor: Gemini 3.1 Flash Lite
While architecture was the primary driver, the choice of model mattered. We ran the final optimized pipeline using **Gemini 3.1 Flash Lite**. This model is specifically optimized for high-volume, low-latency extraction tasks. Combined with our "Mention Mapping" approach, it processed the entire corpus with surgical precision for less than the cost of a cup of coffee.

## The Results
| Metric | Previous (Agentic) | Current (Direct SDK) | Improvement |
| :--- | :--- | :--- | :--- |
| **Frameworks** | CrewAI + Pydantic | Direct SDK (Python) | Lower Complexity |
| **Logic** | LLM Rewriting | Python Regex Mapping | Higher Reliability |
| **Processing** | Sequential | Concurrent (Semaphore) | Much Faster |
| **Total Cost** | **$20.00** | **$0.27** | **-98.6%** |

## Lessons for Developers
1. **Output is Gold:** Every token your LLM outputs is the most expensive part of your app. If you can do it in Python, do it in Python.
2. **Frameworks have a Tax:** Agentic frameworks are great for multi-step reasoning, but for data extraction, the "Token Tax" they impose is often not worth it.
3. **Structured Output != Rewriting:** Use LLMs for what they are good at (identifying patterns) and use code for what it is good at (formatting and string manipulation).

Architecture is the most powerful tool in your cost-optimization toolkit. Before you reach for a bigger model or a more complex framework, ask yourself: *"How much of this work could I be doing with a regex?"*
