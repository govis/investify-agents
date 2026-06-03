import os
import json

managers_dir = 'Managers'
matches = [
    "Managers\\Ahmad Khan\\Profile.json",
    "Managers\\Amy Zegart\\Profile.json",
    "Managers\\Ana Cabral-Gardner\\Profile.json",
    "Managers\\Andrea Fuder\\Profile.json",
    "Managers\\Andrew Bosworth\\Profile.json",
    "Managers\\Andrew Houston\\Profile.json",
    "Managers\\Anna Ohlsson-Leijon\\Profile.json",
    "Managers\\Badar Khan\\Profile.json",
    "Managers\\Barnaby Egerton-Warburton\\Profile.json",
    "Managers\\Bernard Harris, Jr\\Profile.json",
    "Managers\\Bethany Mayer\\Profile.json",
    "Managers\\Betsy Atkins\\Profile.json",
    "Managers\\Cecilia Sandberg\\Profile.json",
    "Managers\\Christian Luiga\\Profile.json",
    "Managers\\Christina Lampe-Önnerud\\Profile.json",
    "Managers\\César Ruipérez\\Profile.json",
    "Managers\\Darren Walker\\Profile.json",
    "Managers\\George Hambro\\Profile.json",
    "Managers\\John Harris II\\Profile.json",
    "Managers\\Mark Leschly\\Profile.json"
]

for match in matches:
    with open(match, 'r', encoding='utf-8') as f:
        data = json.load(f)
        pdc = data.get('picture_download_count')
        social_pdc = [s.get('picture_download_count') for s in data.get('socials', []) if 'picture_download_count' in s]
        print(f"{match}: root pdc={pdc}, social pdc={social_pdc}")
