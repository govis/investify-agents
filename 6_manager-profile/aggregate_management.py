import os
import json

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
                        "companies": [],
                        "investment_theses": set() # Use a set for unique theses
                    }
                
                # Add company investment theses to the person
                company_theses = profile.get("investment_theses", [])
                for thesis in company_theses:
                    thesis_name = thesis.get("thesis_name")
                    if thesis_name:
                        officers_registry[full_name]["investment_theses"].add(thesis_name)
                
                # Check if this company entry already exists for this person (e.g. if in both lists)
                existing_company = next((c for c in officers_registry[full_name]["companies"] 
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
                    officers_registry[full_name]["companies"].append({
                        "name": company_name,
                        "ticker": ticker,
                        "exchange": exchange,
                        "role": role
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
    except OSError as e:
        print(f"Error writing output file: {e}")

if __name__ == "__main__":
    aggregate_management()
