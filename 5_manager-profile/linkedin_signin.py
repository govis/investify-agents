import argparse
import os
from cloakbrowser import launch_persistent_context

def main():
    parser = argparse.ArgumentParser(description="Sign in to LinkedIn to establish a Cloak Browser session.")
    parser.add_argument("--user", type=str, required=True, help="User profile name for the session.")
    args = parser.parse_args()

    session_dir = os.path.join(os.path.dirname(__file__), "sessions", args.user)
    os.makedirs(session_dir, exist_ok=True)

    print(f"Launching Cloak Browser for user '{args.user}'...")
    print("ACTION REQUIRED:")
    print("1. Log in to LinkedIn manually in the browser window.")
    print("2. Complete any CAPTCHAs or 2FA verification.")
    print("3. Once logged in, close the browser.")
    
    context = launch_persistent_context(user_data_dir=session_dir, headless=False)
    page = context.new_page()
    page.goto("https://www.linkedin.com/login")
    
    input("\nPress Enter here once you have finished logging in and closed the browser window...")
    try:
        context.close()
    except Exception:
        pass
    print(f"Session for '{args.user}' initialized.")

if __name__ == "__main__":
    main()
