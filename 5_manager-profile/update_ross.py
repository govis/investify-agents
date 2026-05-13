import json
import os

profile_path = os.path.join("..", "Managers", "Ross McElroy", "Profile.json")
with open(profile_path, "r", encoding="utf-8") as f:
    data = json.load(f)

# Update to the URL provided by the user
data["socials"] = [{
    "name": "LinkedIn",
    "url": "https://www.linkedin.com/in/ross-mcelroy-5a550835/",
    "person_name": "Ross McElroy",
    "company_name": "Fission Uranium Corp.",
    "potential_picture_url": None
}]
data["enrichment_status"] = "pending" # Reset to pending so the grounded search can run on THIS specific URL

with open(profile_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)

print("Updated Ross McElroy Profile.json with user-provided URL.")
