import os
import json
import asyncio
import tools
import re
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(), override=True)

def is_bad_logo(svg_path):
    if not os.path.exists(svg_path):
        return False
    try:
        with open(svg_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read(1000)
            # The generic companieslogo.com logo has this specific title
            if "Screenshot 2022-03-12 at 02-svg" in content:
                return True
    except:
        pass
    return False

async def sync_svgs():
    companies_dir = "../Companies"
    if not os.path.exists(companies_dir):
        print(f"Error: {companies_dir} not found.")
        return

    folders = [f for f in os.listdir(companies_dir) if os.path.isdir(os.path.join(companies_dir, f))]
    print(f"Checking {len(folders)} companies for missing or incorrect SVG logos...\n")
    
    to_process = []
    for folder_name in folders:
        folder_path = os.path.join(companies_dir, folder_name)
        svg_path = os.path.join(folder_path, "logo.svg")
        
        if not os.path.exists(svg_path) or is_bad_logo(svg_path):
            to_process.append(folder_name)
            
    print(f"Found {len(to_process)} companies to process. Starting sync...\n")
    
    batch_size = 5 # Reduced batch size for better logging and less search pressure
    total = len(to_process)
    
    for i in range(0, total, batch_size):
        batch = to_process[i:i+batch_size]
        tasks = [process_svg_sync(f, companies_dir) for f in batch]
        results = await asyncio.gather(*tasks)
        
        for res in results:
            if res:
                print(res)
        
        print(f"Progress: {min(i + batch_size, total)}/{total}...")

async def process_svg_sync(folder_name, companies_dir):
    folder_path = os.path.join(companies_dir, folder_name)
    profile_path = os.path.join(folder_path, "Profile.json")
    
    if not os.path.exists(profile_path):
        return None

    try:
        with open(profile_path, 'r', encoding='utf-8') as f:
            profile = json.load(f)
        
        name = profile.get("name", "")
        ticker = profile.get("ticker", "")
        website = profile.get("website", "")
        
        # If there's a bad logo, delete it first to ensure we try to get a new one
        svg_path = os.path.join(folder_path, "logo.svg")
        if is_bad_logo(svg_path):
            os.remove(svg_path)

        # Use Mechanism 1 (prioritized for SVG in tools.py)
        res = tools.search_companieslogo_com(name, ticker, folder_path, website)
        
        if "SUCCESS" in res:
            # Check if it actually downloaded an SVG
            if os.path.exists(os.path.join(folder_path, "logo.svg")):
                return f"  [NEW SVG] {folder_name}"
            else:
                return f"  [PNG ONLY] {folder_name}"
        else:
            return f"  [FAILED] {folder_name}: {res}"
    except Exception as e:
        return f"  [ERROR] {folder_name}: {e}"
    
    return None

if __name__ == "__main__":
    asyncio.run(sync_svgs())
