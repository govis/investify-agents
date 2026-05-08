import os
import json
import re

def sanitize_folder_name(name):
    """
    Removes characters that are illegal in Windows file/folder names.
    """
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()

def get_person_details_from_company(full_name, ticker, exchange, base_companies_dir):
    """
    Finds a person in a specific company's Management.json and returns their details.
    """
    folder_name = f"{ticker}.{exchange}"
    management_path = os.path.join(base_companies_dir, folder_name, "Management.json")
    
    if not os.path.exists(management_path):
        return None
        
    try:
        with open(management_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        all_people = data.get("executives", []) + data.get("board_of_directors", [])
        for person in all_people:
            if person.get("name") == full_name:
                return person
    except Exception:
        pass
    return None

def create_manager_profiles():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    officers_path = os.path.join(base_dir, "..", "OfficersAndDirectors.json")
    companies_dir = os.path.join(base_dir, "..", "Companies")
    managers_dir = os.path.join(base_dir, "..", "Managers")
    
    if not os.path.exists(officers_path):
        print("Error: OfficersAndDirectors.json not found.")
        return

    with open(officers_path, 'r', encoding='utf-8') as f:
        officers_data = json.load(f)

    print(f"Processing {len(officers_data)} individuals...")

    for person_summary in officers_data:
        full_name = person_summary["name"]
        first_name = person_summary["first_name"]
        last_name = person_summary["last_name"]
        
        # Determine manager folder name
        manager_folder_name = sanitize_folder_name(f"{first_name} {last_name}".strip())
        if not manager_folder_name:
            manager_folder_name = sanitize_folder_name(full_name)
        
        manager_path = os.path.join(managers_dir, manager_folder_name)
        os.makedirs(manager_path, exist_ok=True)
        
        # Initialize profile
        profile = {
            "name": full_name,
            "first_name": first_name,
            "last_name": last_name,
            "age": None,
            "age_year": None,
            "background": None,
            "picture_url": None,
            "companies": [],
            "investment_theses": person_summary.get("investment_theses", []),
            "socials": [],
            "committees": set()
        }
        
        # Populate company specific details and biographical info
        for comp_brief in person_summary.get("companies", []):
            ticker = comp_brief["ticker"]
            exchange = comp_brief["exchange"]
            
            details = get_person_details_from_company(full_name, ticker, exchange, companies_dir)
            
            company_entry = {
                "name": comp_brief["name"],
                "ticker": ticker,
                "exchange": exchange,
                "title_or_role": comp_brief["role"],
                "start_date": None,
                "end_date": None
            }
            
            if details:
                # Basic bio (take from the first company we find it in)
                if profile["age"] is None: profile["age"] = details.get("age")
                if profile["age_year"] is None: profile["age_year"] = details.get("age_year")
                if profile["background"] is None: profile["background"] = details.get("background")
                
                # Committees
                for comm in details.get("committees", []):
                    profile["committees"].add(comm)
                
                # Tenure dates for this specific company
                tenure = details.get("tenure_dates", [])
                # If there are multiple, we look for current ones (end_date null) or just the latest
                for t in tenure:
                    # Logic to match the role if possible, or just take the current one
                    if t.get("end_date") is None:
                        company_entry["start_date"] = t.get("start_date")
                        company_entry["end_date"] = t.get("end_date")
                        break
            
            profile["companies"].append(company_entry)
            
        profile["committees"] = sorted(list(profile["committees"]))
        
        # Write the Profile.json
        with open(os.path.join(manager_path, "Profile.json"), 'w', encoding='utf-8') as f:
            json.dump(profile, f, indent=2)

    print("Profiles created successfully.")

if __name__ == "__main__":
    create_manager_profiles()
