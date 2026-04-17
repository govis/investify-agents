import os
import httpx
import io
from crewai.tools import tool
from ddgs import DDGS
from pypdf import PdfReader
from tools.edgar_tools import fetch_edgar_management_info
from tools.sedar_tools import fetch_sedar_management_info

current_folder = ""

def set_current_folder(folder: str):
    global current_folder
    current_folder = folder
    os.makedirs(folder, exist_ok=True)

@tool("ddgs_search")
def ddgs_search(query: str) -> str:
    """Perform a web search using DuckDuckGo for latest info. Returns titles, snippets and URLs from results."""
    print(f"    [Tool:Search] Query: {query}")
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
            if not results:
                return "No results found for this query."
            
            summary = "Search Results:\n"
            for r in results:
                summary += f"- Title: {r['title']}\n  Snippet: {r['body']}\n  URL: {r['href']}\n"
            return summary
    except Exception as e:
        return f"Error performing search: {e}"

@tool("web_fetch")
def web_fetch(url: str) -> str:
    """Fetch the text content of a URL (HTML or PDF)."""
    print(f"    [Tool:Fetch] URL: {url}")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        with httpx.Client(timeout=30.0, headers=headers, follow_redirects=True) as client:
            response = client.get(url)
            if response.status_code != 200:
                return f"Failed to fetch. Status: {response.status_code}"
            
            content = ""
            if url.lower().endswith('.pdf') or 'application/pdf' in response.headers.get('Content-Type', '').lower():
                try:
                    pdf_file = io.BytesIO(response.content)
                    reader = PdfReader(pdf_file)
                    for i in range(min(10, len(reader.pages))):
                        content += reader.pages[i].extract_text() + "\n"
                        if len(content) > 10000: break
                except Exception as e:
                    return f"Error parsing PDF: {e}"
            else:
                content = response.text[:10000]
            
            if current_folder:
                with open(os.path.join(current_folder, "Step_WebFetch.txt"), "a", encoding="utf-8") as f:
                    f.write(f"\n--- URL: {url} ---\n{content[:2000]}\n")
            
            return content
    except Exception as e:
        return f"Error fetching URL: {e}"

@tool("edgar_filings_list")
def edgar_filings_list(ticker: str) -> str:
    """Fetch recent SEC filings list from EDGAR for a US ticker. Returns CIK and filing metadata."""
    print(f"    [Tool:EDGAR] Fetching list for {ticker}...")
    result = fetch_edgar_management_info(ticker)
    if current_folder:
        with open(os.path.join(current_folder, "Step_EDGAR_Raw.txt"), "w", encoding="utf-8") as f:
            f.write(result)
    return result

@tool("sedar_filings_list")
def sedar_filings_list(company_name: str, ticker: str) -> str:
    """Fetch search hints for Canadian filings on SEDAR for a company."""
    print(f"    [Tool:SEDAR] Fetching hints for {company_name}...")
    result = fetch_sedar_management_info(company_name, ticker)
    if current_folder:
        with open(os.path.join(current_folder, "Step_SEDAR_Raw.txt"), "w", encoding="utf-8") as f:
            f.write(result)
    return result
