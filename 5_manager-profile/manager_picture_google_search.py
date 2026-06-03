import os
import json
import argparse
import urllib.parse
import time
import tools
from playwright.sync_api import sync_playwright

def search_and_download(full_name: str, manager_dir: str):
    print(f"Searching Google Images for {full_name}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # Use existing tools.get_google_image logic
        img_src = tools.get_google_image(page, f"{full_name} linkedin")
        
        if img_src:
            print(f"  -> Found image: {img_src[:80]}...")
            filename = tools.download_image(img_src, manager_dir)
            if filename:
                print(f"  -> Saved to {filename}")
        else:
            print("  -> No image found.")
            
        browser.close()

def main():
    parser = argparse.ArgumentParser(description="Google Image Search for manager profile pictures.")
    parser.add_argument("--name", required=True, help="Full name of manager")
    parser.add_argument("--dir", required=True, help="Directory to save the image")
    args = parser.parse_args()
    
    search_and_download(args.name, args.dir)

if __name__ == '__main__':
    main()
