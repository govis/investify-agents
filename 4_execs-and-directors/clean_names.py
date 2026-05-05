import os
import json
import re
import sys

def clean_name_from_background(background):
    if not background:
        return None
    
    stop_words = ["is", "has", "was", "joined", "serves", "currently", "holds", "brings", "manages", "leads", "appointed"]
    honorifics = ["mr", "ms", "mrs", "dr", "prof", "sir"]
    
    bg_words = background.split()
    name_candidates = []
    
    start_idx = 0
    if bg_words and re.sub(r'[^\w\s]', '', bg_words[0].lower()) in honorifics:
        start_idx = 1
        
    for i in range(start_idx, len(bg_words)):
        word = bg_words[i]
        clean_word = re.sub(r'[^\w\s]', '', word.lower())
        if clean_word in stop_words or not clean_word:
            break
        name_candidates.append(word)
        if len(name_candidates) >= 4:
            break
            
    if len(name_candidates) >= 2:
        potential = " ".join(name_candidates)
        return re.sub(r'[,\.]$', '', potential).strip()
    return None

def clean_messy_name(messy_name, background):
    # Step 1: Extract nickname if it exists, but skip (Ret.) or (Ret)
    nickname = None
    paren_match = re.search(r'\((.*?)\)', messy_name)
    if paren_match:
        n = paren_match.group(1).strip()
        if n.lower().strip('.') != 'ret':
            nickname = n
    
    # Step 2: Clean the name by removing ALL parens and initials
    clean_name = re.sub(r'\(.*?\)', '', messy_name)
    # Remove initials: "A. " or " A." or "A.B. "
    clean_name = re.sub(r'\b[A-Z]\.\s*', '', clean_name)
    clean_name = re.sub(r'\s+[A-Z]\.\b', '', clean_name)
    
    parts = clean_name.split()
    # Skip common titles and honorifics ONLY if they are at the beginning
    titles = ["mr", "ms", "mrs", "dr", "prof", "sir", "admiral", "general", "the", "lord", "ret", "hon"]
    
    filtered_parts = [p for p in parts if len(p.strip('.')) > 1 or p.lower().strip('.') == 'st']
    
    while filtered_parts and filtered_parts[0].lower().strip('().') in titles:
        filtered_parts = filtered_parts[1:]
        
    # Step 3: If we have a nickname, try to use it + Surname
    if nickname and len(nickname) > 1:
        if filtered_parts:
            return f"{nickname} {filtered_parts[-1]}"
            
    if len(filtered_parts) >= 2:
        return " ".join(filtered_parts)
    
    # Fallback to background
    if background:
        bg_name = clean_name_from_background(background)
        if bg_name: return bg_name

    return " ".join(filtered_parts) if len(filtered_parts) >= 2 else messy_name

def get_original_name(folder_path, target_person_data):
    raw_path = os.path.join(folder_path, "Step_Crew_Raw_Response.txt")
    if not os.path.exists(raw_path):
        return None
        
    try:
        with open(raw_path, 'r', encoding='utf-8') as f:
            raw_content = f.read()
            
        json_match = re.search(r'(\{.*\})', raw_content, re.DOTALL)
        if json_match:
            raw_json = json.loads(json_match.group(1))
            for key in ['executives', 'board_of_directors']:
                if key in raw_json:
                    for person in raw_json[key]:
                        if person.get('background') == target_person_data.get('background'):
                            return person.get('name')
    except:
        pass
    return None

def process_files(specific_company=None):
    companies_dir = os.path.join("..", "Companies")
    if not os.path.exists(companies_dir):
        print(f"Error: {companies_dir} not found.")
        return

    for folder_name in os.listdir(companies_dir):
        if specific_company and folder_name.lower() != specific_company.lower():
            continue
            
        folder_path = os.path.join(companies_dir, folder_name)
        file_path = os.path.join(folder_path, "Management.json")
        
        if os.path.exists(file_path):
            changed = False
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                for key in ['executives', 'board_of_directors']:
                    if key in data:
                        for person in data[key]:
                            name = person.get('name', '')
                            raw_original = get_original_name(folder_path, person)
                            
                            # Preserve original name logic
                            # If name_original is missing OR if we found a better raw original
                            current_original = person.get('name_original')
                            if not current_original or (raw_original and raw_original != current_original and len(raw_original) > len(current_original)):
                                person['name_original'] = raw_original if raw_original else name
                                changed = True
                            
                            source_name = raw_original if raw_original else name
                            new_name = clean_messy_name(source_name, person.get('background', ''))
                            
                            if new_name and new_name != name:
                                parts = new_name.split()
                                if len(parts) >= 2:
                                    person['name'] = new_name
                                    print(f"Updated in {file_path}:")
                                    print(f"  From: {name}")
                                    print(f"  To:   {new_name} (Source: {source_name})")
                                    changed = True
                
                if changed:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2)
                        
            except Exception as e:
                print(f"Error processing {file_path}: {e}")

if __name__ == "__main__":
    company = sys.argv[1] if len(sys.argv) > 1 else None
    process_files(company)
