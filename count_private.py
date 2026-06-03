import os
import json

managers_dir = 'Managers'
private_count = 0
total_count = 0

for root, dirs, files in os.walk(managers_dir):
    if 'Profile.json' in files:
        file_path = os.path.join(root, 'Profile.json')
        total_count += 1
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                socials = data.get('socials', [])
                is_private = data.get('profile_status') == "private"
                if not is_private:
                    for social in socials:
                        if social.get('profile_status') == "private":
                            is_private = True
                            break
                if is_private:
                    private_count += 1
        except:
            pass

print(f"Total Profile.json: {total_count}")
print(f"Private profiles: {private_count}")
