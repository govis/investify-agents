import os
import json

managers_dir = 'Managers'
count = 0

for root, dirs, files in os.walk(managers_dir):
    if 'Profile.json' in files:
        file_path = os.path.join(root, 'Profile.json')
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get('enrichment_socials') == "success":
                    if not data.get('picture_local'):
                        count += 1
        except:
            pass

print(f"Success enrichment, no local picture: {count}")
