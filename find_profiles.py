import os
import json

managers_dir = 'Managers'
matches = []

def is_empty(val):
    return val is None or val == "" or val == 0

for root, dirs, files in os.walk(managers_dir):
    if 'Profile.json' in files:
        file_path = os.path.join(root, 'Profile.json')
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                enrichment_socials = data.get('enrichment_socials')
                if enrichment_socials != "success":
                    continue
                
                picture_local = data.get('picture_local')
                root_download_count = data.get('picture_download_count')
                socials = data.get('socials', [])
                
                has_download_count = not is_empty(root_download_count)
                for social in socials:
                    if not is_empty(social.get('picture_download_count')):
                        has_download_count = True
                        break
                
                root_status = data.get('profile_status')
                is_private = root_status == "private"
                is_not_found = root_status == "not_found"
                
                for social in socials:
                    status = social.get('profile_status')
                    if status == "private":
                        is_private = True
                    if status == "not_found":
                        is_not_found = True
                
                if not is_empty(picture_local):
                    continue
                
                if has_download_count:
                    continue
                    
                if is_private:
                    continue
                
                if is_not_found:
                    continue
                
                matches.append(file_path)
                
        except Exception as e:
            print(f"Error reading {file_path}: {e}")

print(f"Found {len(matches)} matches:")
for match in matches:
    print(match)
