import json
import asyncio
import os
import re
import time
from collections import deque
from pipeline import DirectPipeline
from dotenv import load_dotenv, find_dotenv

# Load local workflow settings
load_dotenv(find_dotenv(), override=True)
# Load shared project settings from parent directory
load_dotenv(os.path.join("..", ".env"), override=False)

class AsyncRateLimiter:
    """A sliding window rate limiter to ensure LLM_RPM is never exceeded."""
    def __init__(self, rpm: int):
        self.rpm = rpm
        self.requests = deque()
        self.lock = asyncio.Lock()

    async def acquire(self):
        """Acquires permission to make a request, sleeping if necessary."""
        if self.rpm <= 0: return # No limit
        
        async with self.lock:
            while True:
                now = time.time()
                # Remove timestamps older than 60 seconds
                while self.requests and self.requests[0] < now - 60:
                    self.requests.popleft()

                if len(self.requests) < self.rpm:
                    # We are within the limit
                    self.requests.append(now)
                    return
                else:
                    # Limit reached, sleep until the oldest request is out of the 60s window
                    sleep_time = 60 - (now - self.requests[0])
                    if sleep_time > 0:
                        print(f"    Rate Limit (RPM) reached. Throttling for {sleep_time:.2f}s...")
                        await asyncio.sleep(sleep_time)

def apply_hyperlinks(content, companies, exchange_filter):
    """
    Apply hyperlinks to the content based on identified company mentions.
    Uses a robust single-pass regex to avoid nested links and double-linking.
    """
    if not companies:
        return content

    link_map = {} # (pattern_type, text) -> link_info
    patterns = []
    
    patterns.append(r'\[.*?\]\(.*?\)')
    
    for company in companies:
        name = company['name']
        ticker = company['ticker']
        exchange = company['exchange']
        
        if exchange_filter and exchange not in exchange_filter:
            continue
            
        link_target = f"/company/{ticker}.{exchange}"
        
        patterns.append(rf'\b({re.escape(name)})\b\s*\(\s*({re.escape(ticker)})\s*\)')
        link_map[('both', name, ticker)] = f"[{name}]({link_target}) ({ticker})"
        
        patterns.append(rf'\b({re.escape(name)})\b')
        link_map[('name', name)] = f"[{name}]({link_target})"
        
        patterns.append(rf'\b({re.escape(ticker)})\b')
        link_map[('ticker', ticker)] = f"[{ticker}]({link_target})"

    patterns.sort(key=len, reverse=True)
    combined_regex = re.compile('|'.join(patterns))
    
    def callback(match):
        full_match = match.group(0)
        if full_match.startswith('[') and '](' in full_match:
            return full_match
            
        for key, replacement in link_map.items():
            if len(key) == 3: # (ptype, n, t)
                ptype, n, t = key
                if n in full_match and t in full_match and '(' in full_match:
                    if re.fullmatch(rf'{re.escape(n)}\s*\(\s*{re.escape(t)}\s*\)', full_match):
                        return replacement
        
        for key, replacement in link_map.items():
            if len(key) == 2: # (ptype, text)
                ptype, text = key
                if full_match == text:
                    return replacement
                
        return full_match

    return combined_regex.sub(callback, content)

def chunk_content(content, max_chars):
    """Split content into chunks based on calculated max_chars."""
    if len(content) <= max_chars:
        return [content]
    
    # Split by headers
    parts = re.split(r'(\n#{1,3} .*)', content)
    chunks = []
    current_chunk = ""
    for part in parts:
        if len(current_chunk) + len(part) > max_chars:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = part
        else:
            current_chunk += part
    if current_chunk:
        chunks.append(current_chunk)
    return chunks

async def process_file(pipeline, thesis_name, file_path, consolidated, base_theses_path, output_theses_path, exchange_filter, semaphore, limiter, max_chars):
    print(f"\n--- Processing: {file_path} ({thesis_name}) ---")
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            full_content = f.read()
    except Exception as e:
        print(f"    Read Error: {e}")
        return

    chunks = chunk_content(full_content, max_chars)
    print(f"    Chunks: {len(chunks)} (Max Chars: {max_chars})")
    
    recent_context = list(consolidated.values())[-10:]
    context_str = ", ".join([f"{c['name']} ({c['ticker']}.{c['exchange']})" for c in recent_context])

    final_updated_content = ""
    
    for i, chunk in enumerate(chunks):
        # Apply RPM Rate Limiting
        await limiter.acquire()
            
        async with semaphore:
            success = False
            retries = 3
            result_data = {"companies": []}
            
            while not success and retries > 0:
                try:
                    result_data = await pipeline.process_chunk(thesis_name, chunk, context_str)
                    success = True
                except Exception as e:
                    if "429" in str(e) or "rate_limit" in str(e).lower():
                        print(f"    API Rate limit error. Backing off 60s... ({retries} left)")
                        await asyncio.sleep(60)
                        retries -= 1
                    else:
                        print(f"    Chunk Error: {e}")
                        success = True # Skip on hard errors

            # Update consolidated list
            found_companies = result_data.get("companies", [])
            for c in found_companies:
                key = f"{c['ticker']}.{c['exchange']}".upper()
                thesis_ref = {"thesis_name": thesis_name, "company_type": c['company_type']}
                
                if key not in consolidated:
                    consolidated[key] = {
                        "name": c['name'],
                        "ticker": c['ticker'],
                        "exchange": c['exchange'],
                        "theses": [thesis_ref]
                    }
                else:
                    existing = consolidated[key]
                    if not any(t['thesis_name'] == thesis_name for t in existing['theses']):
                        existing['theses'].append(thesis_ref)
                    else:
                        for t in existing['theses']:
                            if t['thesis_name'] == thesis_name:
                                t['company_type'] = c['company_type']

            # Apply hyperlinks to this chunk
            updated_chunk = apply_hyperlinks(chunk, found_companies, exchange_filter)
            final_updated_content += updated_chunk

    # Save file
    rel_path = os.path.relpath(file_path, base_theses_path)
    out_path = os.path.join(output_theses_path, rel_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(final_updated_content)
    print(f"    Saved: {out_path}")

async def main():
    print("Workflow 1: Dynamic Throttling Extraction Starting...")
    pipeline = DirectPipeline()
    
    theses = ["AI", "Defense", "Electrification", "Gold", "Nuclear", "Reshoring"]
    consolidated = {} # Global list
    
    base_path = "../Theses"
    out_path = "../ThesesWithLinks"
    
    # Read Rate Limits
    rpm = int(os.getenv("LLM_RPM", "15")) # Default to 15 if missing
    tpm = int(os.getenv("LLM_TPM", "1000000")) # Default to 1M if missing
    concurrency_limit = int(os.getenv("CONCURRENCY_LIMIT", "1"))
    
    # Dynamic Chunk Size Calculation (TPM based)
    # TPR (Tokens Per Request) = TPM / RPM
    # Buffer ~700 tokens for prompt/context/output
    tpr = tpm / max(rpm, 1)
    max_chars = int(max(500, min(8000, (tpr - 700) * 4)))
    
    limiter = AsyncRateLimiter(rpm)
    semaphore = asyncio.Semaphore(concurrency_limit)
    
    filter_str = os.getenv("EXCHANGE_FILTER", "")
    exchange_filter = [e.strip() for e in filter_str.split(",")] if filter_str else []
    
    print(f"Config: Provider={pipeline.provider.upper()}, RPM={rpm}, TPM={tpm}, ChunkSize={max_chars}, Concurrency={concurrency_limit}")

    for thesis in theses:
        thesis_dir = os.path.join(base_path, thesis)
        if not os.path.exists(thesis_dir): continue
        
        for root, _, files in os.walk(thesis_dir):
            for file in files:
                if file.endswith(".md"):
                    await process_file(pipeline, thesis, os.path.join(root, file), consolidated, base_path, out_path, exchange_filter, semaphore, limiter, max_chars)

    # Final save of consolidated list
    final_list = list(consolidated.values())
    with open("../CompanyList.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, indent=2)
    
    print(f"\nWorkflow 1 Complete: {len(final_list)} companies identified.")

if __name__ == "__main__":
    asyncio.run(main())
