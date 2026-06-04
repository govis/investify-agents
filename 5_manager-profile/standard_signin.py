import argparse
import os
from playwright.sync_api import sync_playwright

def main():
    parser = argparse.ArgumentParser(description="Standard browser sign-in to establish persistent session.")
    parser.add_argument("--user", type=str, required=True, help="User profile name.")
    args = parser.parse_args()

    session_dir = os.path.join(os.path.dirname(__file__), "sessions", args.user)
    os.makedirs(session_dir, exist_ok=True)

    print(f"Launching standard browser for user '{args.user}'...")
    print("ACTION: Log in to LinkedIn, complete the challenge, then close the browser.")
    
    with sync_playwright() as p:
        # Use standard Chromium launch
        browser = p.chromium.launch_persistent_context(
            user_data_dir=session_dir,
            headless=False,
            channel="chrome" # Use system Chrome if available, or just 'chromium'
        )
        page = browser.pages[0]
        page.goto("https://www.linkedin.com/login")
        
        input("\nPress Enter here after you have successfully logged in and closed the browser...")
        browser.close()

if __name__ == "__main__":
    main()
