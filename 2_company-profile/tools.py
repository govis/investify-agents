import time
from crewai.tools import tool
from ddgs import DDGS
import httpx
from bs4 import BeautifulSoup

@tool("ddgs_search")
def ddgs_search(query: str) -> str:
    """Useful to search the web for information. Provide a single search query string in a JSON dictionary."""
    print(f"    [Tool:Search] Query: {query}")
    try:
        time.sleep(1)
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
    """Useful to fetch the content of a specific URL. Provide a single URL string in a JSON dictionary."""
    print(f"    [Tool:Fetch] URL: {url}")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        with httpx.Client(timeout=30.0, headers=headers, follow_redirects=True) as client:
            response = client.get(url)
            if response.status_code != 200:
                return f"Failed to fetch. Status: {response.status_code}"
            
            soup = BeautifulSoup(response.text, 'html.parser')
            for script in soup(["script", "style"]):
                script.decompose()
            text = soup.get_text()
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            content = '\n'.join(chunk for chunk in chunks if chunk)
            return content[:10000]
    except Exception as e:
        return f"Error fetching URL: {e}"
