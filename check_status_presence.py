import os
import json

managers_dir = 'Managers'
count_no_status = 0
count_success = 0

for root, dirs, files in os.walk(managers_dir):
    if 'Profile.json' in files:
        file_path = os.path.join(root, 'Profile.json')
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get('enrichment_socials') == "success":
                    count_success += 1
                    socials = data.get('socials', [])
                    has_status = 'profile_status' in data
                    for social in socials:
                        if 'profile_status' in social:
                            has_status = True
                            break
                    if not has_status:
                        count_no_status += 1
        except:
            pass

print(f"Success enrichment: {count_success}")
print(f"Success enrichment with NO status: {count_no_status}")
