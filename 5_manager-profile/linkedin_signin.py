import argparse
from cloakbrowser import launch

def main():
    parser = argparse.ArgumentParser(description="Sign in to LinkedIn to establish a Cloak Browser session.")
    parser.add_argument("--user", type=str, required=True, help="User profile name for the session.")
    args = parser.parse_args()

    print(f"Launching Cloak Browser for user '{args.user}'...")
    print("ACTION REQUIRED:")
    print("1. Log in to LinkedIn manually in the browser window.")
    print("2. Complete any CAPTCHAs or 2FA verification.")
    print("3. Once logged in, you can close the browser window or press Enter here.")
    
    # Launch in headful mode for manual interaction
    browser = launch(user=args.user, headful=True)
    page = browser.new_page()
    page.goto("https://www.linkedin.com/login")
    
    input("\nPress Enter here once you have finished logging in and closed the browser window...")
    try:
        browser.close()
    except Exception:
        pass
    print(f"Session for '{args.user}' initialized.")

if __name__ == "__main__":
    main()
