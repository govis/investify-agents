import argparse
import time
from cloakbrowser import launch

def main():
    parser = argparse.ArgumentParser(description="Sign out of LinkedIn to clear a Cloak Browser session.")
    parser.add_argument("--user", type=str, required=True, help="User profile name for the session.")
    args = parser.parse_args()

    print(f"Launching Cloak Browser for user '{args.user}' to sign out...")
    
    # Headless is sufficient for signout
    browser = launch(user=args.user, headful=False)
    page = browser.new_page()
    try:
        page.goto("https://www.linkedin.com/logout", timeout=30000)
        time.sleep(5) # Wait for logout to process
        print(f"Successfully signed out for user '{args.user}'.")
    except Exception as e:
        print(f"Error during signout: {e}")
    finally:
        browser.close()

if __name__ == "__main__":
    main()
