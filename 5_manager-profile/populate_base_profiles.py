import json
import os
import argparse
from tools import populate_base_profile
from dotenv import load_dotenv, find_dotenv

def main():
    load_dotenv(os.path.join("..", ".env"))
    load_dotenv(find_dotenv(), override=True)
    
    officers_path = os.path.join("..", "OfficersAndDirectors.json")
    managers_dir = os.path.join("..", "Managers")
    
    if not os.path.exists(officers_path):
        print(f"Error: {officers_path} not found.")
        return

    os.makedirs(managers_dir, exist_ok=True)

    try:
        with open(officers_path, "r", encoding="utf-8") as f:
            all_officers = json.load(f)
    except Exception as e:
        print(f"Error reading OfficersAndDirectors.json: {e}")
        return

    print(f"Phase 1: Populating base profiles for {len(all_officers)} individuals...")
    count = 0
    for person in all_officers:
        populate_base_profile(person, managers_dir)
        count += 1
        if count % 100 == 0:
            print(f"Processed {count}/{len(all_officers)} individuals...")
            
    print(f"Phase 1 complete. Processed {count} individuals.")

if __name__ == "__main__":
    main()
