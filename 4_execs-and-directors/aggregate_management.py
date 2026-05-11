import os
import json
import re

def sanitize_folder_name(name):
    """
    Removes characters that are illegal in Windows file/folder names.
    """
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()

def parse_name(full_name):
    """
    Simple name parser to split into first and last name.
    """
    parts = full_name.split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    
    # Simple heuristic: first part is first name, rest is last name
    first_name = parts[0]
    last_name = " ".join(parts[1:])
    return first_name, last_name

def get_current_role(person):
    """
    Extracts current role(s) from tenure_dates where end_date is null.
    """
    tenure = person.get("tenure_dates", [])
    roles = []
    for t in tenure:
        if t.get("end_date") is None:
            # Use 'title' (execs) or 'role' (directors)
            r = t.get("title") or t.get("role")
            if r:
                roles.append(r)
    
    # Return comma-separated roles if multiple exist (e.g., "Director, Chairman")
    return ", ".join(roles) if roles else "Unknown Role"

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

def create_manager_profiles(final_data):
    """
    Creates individual Profile.json files for each manager in the ../Managers directory.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    managers_dir = os.path.abspath(os.path.join(base_dir, "..", "Managers"))
    companies_dir = os.path.abspath(os.path.join(base_dir, "..", "Companies"))
    
    os.makedirs(managers_dir, exist_ok=True)
    
    print(f"Creating/updating profiles for {len(final_data)} individuals in {managers_dir}...")
    
    for person_summary in final_data:
        full_name = person_summary["name"]
        first_name = person_summary["first_name"]
        last_name = person_summary["last_name"]
        
        # Determine manager folder name
        manager_folder_name = sanitize_folder_name(f"{first_name} {last_name}".strip())
        if not manager_folder_name:
            manager_folder_name = sanitize_folder_name(full_name)
        
        manager_path = os.path.join(managers_dir, manager_folder_name)
        os.makedirs(manager_path, exist_ok=True)
        
        profile_path = os.path.join(manager_path, "Profile.json")
        
        # Load existing profile if it exists to preserve data
        existing_profile = {}
        if os.path.exists(profile_path):
            try:
                with open(profile_path, 'r', encoding='utf-8') as f:
                    existing_profile = json.load(f)
            except Exception:
                pass

        # Initialize/Update profile
        profile = {
            "name": full_name,
            "first_name": first_name,
            "last_name": last_name,
            "age": existing_profile.get("age"),
            "age_year": existing_profile.get("age_year"),
            "background": existing_profile.get("background"),
            "picture_url": existing_profile.get("picture_url"),
            "picture_local": existing_profile.get("picture_local"),
            "company_affiliations": [],
            "investment_theses": person_summary.get("investment_theses", []),
            "socials": existing_profile.get("socials", []),
            "committees": set(existing_profile.get("committees", []))
        }
        
        # Populate company specific details and biographical info
        for comp_brief in person_summary.get("company_affiliations", []):
            ticker = comp_brief["ticker"]
            exchange = comp_brief["exchange"]
            
            details = get_person_details_from_company(full_name, ticker, exchange, companies_dir)
            
            company_entry = {
                "name": comp_brief["name"],
                "ticker": ticker,
                "exchange": exchange,
                "title_or_role": comp_brief["role"],
                "website": comp_brief.get("website"),
                "start_date": None,
                "end_date": None
            }
            
            if details:
                # Basic bio (take if not already present)
                if profile["age"] is None: profile["age"] = details.get("age")
                if profile["age_year"] is None: profile["age_year"] = details.get("age_year")
                if profile["background"] is None: profile["background"] = details.get("background")
                
                # Committees
                for comm in details.get("committees", []):
                    profile["committees"].add(comm)
                
                # Tenure dates
                tenure = details.get("tenure_dates", [])
                for t in tenure:
                    if t.get("end_date") is None:
                        company_entry["start_date"] = t.get("start_date")
                        company_entry["end_date"] = t.get("end_date")
                        break
            
            profile["company_affiliations"].append(company_entry)
            
        profile["committees"] = sorted(list(profile["committees"]))
        
        # Write the Profile.json
        with open(profile_path, 'w', encoding='utf-8') as f:
            json.dump(profile, f, indent=2)

def aggregate_management():
    # Paths are relative to the script's expected location in the 5_manager-profile directory
    # Data is in ../Companies/
    # Output should be ../OfficersAndDirectors.json
    
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Companies"))
    output_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "OfficersAndDirectors.json"))
    
    if not os.path.exists(base_dir):
        print(f"Error: Companies directory not found at {base_dir}")
        return

    officers_registry = {}

    # Iterate through each TICKER.EXCHANGE folder
    for folder_name in os.listdir(base_dir):
        folder_path = os.path.join(base_dir, folder_name)
        
        if not os.path.isdir(folder_path):
            continue
            
        if "." not in folder_name:
            continue
            
        ticker, exchange = folder_name.split(".", 1)
        
        profile_path = os.path.join(folder_path, "Profile.json")
        management_path = os.path.join(folder_path, "Management.json")
        
        if not os.path.exists(profile_path) or not os.path.exists(management_path):
            continue
            
        try:
            with open(profile_path, 'r', encoding='utf-8') as f:
                profile = json.load(f)
                company_name = profile.get("name", "Unknown Company")
                company_website = profile.get("website")
                
            with open(management_path, 'r', encoding='utf-8') as f:
                management_data = json.load(f)
                
            # Management.json contains 'executives' and 'board_of_directors'
            executives = management_data.get("executives", [])
            directors = management_data.get("board_of_directors", [])
            
            # Combine both lists
            all_people = executives + directors
                
            for person in all_people:
                full_name = person.get("name")
                role = get_current_role(person)
                
                if not full_name:
                    continue
                    
                if full_name not in officers_registry:
                    first, last = parse_name(full_name)
                    officers_registry[full_name] = {
                        "name": full_name,
                        "first_name": first,
                        "last_name": last,
                        "company_affiliations": [],
                        "investment_theses": set() # Use a set for unique theses
                    }
                
                # Add company investment theses to the person
                company_theses = profile.get("investment_theses", [])
                for thesis in company_theses:
                    thesis_name = thesis.get("thesis_name")
                    if thesis_name:
                        officers_registry[full_name]["investment_theses"].add(thesis_name)
                
                # Check if this company entry already exists for this person (e.g. if in both lists)
                existing_company = next((c for c in officers_registry[full_name]["company_affiliations"] 
                                       if c["ticker"] == ticker and c["exchange"] == exchange), None)
                
                if existing_company:
                    # If person is in both lists, we might want to combine roles if they differ
                    if role != "Unknown Role" and role not in existing_company["role"]:
                        if existing_company["role"] == "Unknown Role":
                            existing_company["role"] = role
                        else:
                            # Combine unique roles
                            current_roles = set(existing_company["role"].split(", "))
                            new_roles = set(role.split(", "))
                            combined = ", ".join(sorted(list(current_roles.union(new_roles))))
                            existing_company["role"] = combined
                else:
                    officers_registry[full_name]["company_affiliations"].append({
                        "name": company_name,
                        "ticker": ticker,
                        "exchange": exchange,
                        "role": role,
                        "website": company_website
                    })
                
        except (json.JSONDecodeError, OSError) as e:
            print(f"Error processing {folder_name}: {e}")
            continue

    # Convert registry to a list of person objects
    final_data = []
    for person in officers_registry.values():
        person["investment_theses"] = sorted(list(person["investment_theses"]))
        final_data.append(person)
    
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, indent=2)
        print(f"Successfully aggregated {len(final_data)} officers and directors into {output_path}")
        
        # Create individual manager profiles
        create_manager_profiles(final_data)
        
    except OSError as e:
        print(f"Error writing output file: {e}")

if __name__ == "__main__":
    aggregate_management()
