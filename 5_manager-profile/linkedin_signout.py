import argparse
import time
import os
import shutil
from cloakbrowser import launch_persistent_context

def main():
    parser = argparse.ArgumentParser(description="Sign out of LinkedIn and clear a Cloak Browser session.")
    parser.add_argument("--user", type=str, required=True, help="User profile name for the session.")
    args = parser.parse_args()

    session_dir = os.path.join(os.path.dirname(__file__), "sessions", args.user)
    
    if not os.path.exists(session_dir):
        print(f"No session found for user '{args.user}'.")
        return

    print(f"Signing out user '{args.user}'...")
    
    # Sign out via browser
    context = launch_persistent_context(user_data_dir=session_dir, headless=True)
    page = context.new_page()
    try:
        page.goto("https://www.linkedin.com/logout", timeout=30000)
        time.sleep(5)
        print(f"Successfully signed out for user '{args.user}'.")
    except Exception as e:
        print(f"Error during signout: {e}")
    finally:
        context.close()
    
    # Delete the session data
    shutil.rmtree(session_dir)
    print(f"Session data for '{args.user}' cleared.")

if __name__ == "__main__":
    main()
