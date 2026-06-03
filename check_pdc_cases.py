import os
import json

managers_dir = 'Managers'
count_has_pdc = 0

for root, dirs, files in os.walk(managers_dir):
    if 'Profile.json' in files:
        file_path = os.path.join(root, 'Profile.json')
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get('enrichment_socials') == "success":
                    if not data.get('picture_local'):
                        pdc = data.get('picture_download_count')
                        has_pdc = pdc is not None and pdc > 0
                        if not has_pdc:
                            for social in data.get('socials', []):
                                s_pdc = social.get('picture_download_count')
                                if s_pdc is not None and s_pdc > 0:
                                    has_pdc = True
                                    break
                        if has_pdc:
                             count_has_pdc += 1
        except:
            pass

print(f"Success enrichment, no local picture, but HAS download count > 0 (including socials): {count_has_pdc}")
