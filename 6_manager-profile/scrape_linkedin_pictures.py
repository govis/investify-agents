import os
import json
import time
import requests
import urllib.parse
import base64
import argparse
import tools
from cloakbrowser import launch
from dotenv import load_dotenv, find_dotenv

load_dotenv(os.path.join("..", ".env"))
load_dotenv(find_dotenv(), override=True)

# Configuration
PROFILES_TO_PROCESS = int(os.getenv("PROFILES_TO_ENRICH", "0"))

def get_google_image(page, username):
    print(f"  -> Attempting fallback: Google Image Search for '{username} linkedin'")
    query = f"{username} linkedin"
    search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&udm=2"
    
    try:
        page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
        time.sleep(3) # Wait for images to load
        
        img_src = page.evaluate('''() => {
            const imgs = Array.from(document.querySelectorAll('img'));
            for (let img of imgs) {
                if (img.src && img.src.startsWith('data:image/')) {
                    const rect = img.getBoundingClientRect();
                    if (rect.width > 40 || rect.height > 40 || img.width > 40) {
                        return img.src;
                    }
                }
                if (img.src && img.src.includes('encrypted-tbn0.gstatic.com/images')) {
                    return img.src;
                }
            }
            return null;
        }''')
        return img_src
    except Exception as e:
        print(f"  -> Google Image search failed: {e}")
        return None

def process_profile(page, profile_path):
    try:
        with open(profile_path, 'r', encoding='utf-8') as f:
            profile = json.load(f)
            
        full_name = profile['name']
        socials = profile.get('socials', [])
        linkedin_url = next((s['url'] for s in socials if 'linkedin.com' in s['url'].lower()), None)
        
        if not linkedin_url:
            print(f"  -> No LinkedIn URL for {full_name}. Skipping.")
            return

        # Increment download attempt count
        profile['picture_download_count'] = profile.get('picture_download_count', 0) + 1

        print(f"  -> Navigating to {linkedin_url}...")
        username = linkedin_url.rstrip('/').split('/')[-1]
        if not username:
            username = full_name.replace(" ", "_")

        try:
            page.goto(linkedin_url, wait_until='domcontentloaded', timeout=30000)
            time.sleep(5) # Wait for dynamic content
            
            img_selector = 'img.top-card__profile-image, img[src*="profile-displayphoto"]'
            img_src = None
            try:
                page.wait_for_selector(img_selector, timeout=10000)
                img_src = page.evaluate(f"() => {{ const el = document.querySelector('{img_selector}'); return el ? el.src : null; }}")
            except Exception:
                print(f"  -> Could not find image element on LinkedIn for {full_name}.")
                
            if not img_src:
                img_src = get_google_image(page, username)
                
            if img_src:
                print(f"  -> Found image URL: {img_src[:80]}...")
                manager_dir = os.path.dirname(profile_path)
                
                if img_src.startswith('data:image'):
                    header, encoded = img_src.split(",", 1)
                    ext = "jpg"
                    if "png" in header: ext = "png"
                    elif "webp" in header: ext = "webp"
                    
                    filename = f"Picture.{ext}"
                    full_path = os.path.join(manager_dir, filename)
                    with open(full_path, 'wb') as f_img:
                        f_img.write(base64.b64decode(encoded))
                    
                    # Manual validation for base64
                    try:
                        with open(full_path, 'rb') as f_check:
                            head = f_check.read(100).lower()
                            if b'<svg' in head:
                                print(f"  -> Rejected base64 SVG placeholder.")
                                os.remove(full_path)
                                # Save count even if rejected
                                with open(profile_path, 'w', encoding='utf-8') as f:
                                    json.dump(profile, f, indent=2)
                                return
                    except Exception: pass
                    
                    profile['picture_local'] = filename
                else:
                    # Use tools.download_image for consistency and SVG detection
                    local_filename = tools.download_image(img_src, manager_dir)
                    if local_filename:
                        profile['picture_local'] = local_filename
                    else:
                        print(f"  -> Image download failed or rejected (SVG).")
                        # Save count even if failed
                        with open(profile_path, 'w', encoding='utf-8') as f:
                            json.dump(profile, f, indent=2)
                        return

                print(f"  -> Successfully updated picture metadata.")
                profile['picture_url'] = img_src
                # Remove download count on success from top level and nested socials
                profile.pop('picture_download_count', None)
                for s in profile.get('socials', []):
                    s.pop('picture_download_count', None)
            else:
                print(f"  -> No image found for {full_name} even after fallback")
            
            # Save updated profile
            with open(profile_path, 'w', encoding='utf-8') as f:
                json.dump(profile, f, indent=2)
                
        except Exception as e:
            print(f"  -> Error processing {linkedin_url}: {e}")
            # Still save the download count increment
            with open(profile_path, 'w', encoding='utf-8') as f:
                json.dump(profile, f, indent=2)
            
    except Exception as e:
        print(f"  -> Error reading profile {profile_path}: {e}")

def main():
    parser = argparse.ArgumentParser(description="Phase 3a: LinkedIn profile picture scraper.")
    parser.add_argument("--retry_failed", type=str, default="no", choices=["yes", "no"], help="Retry profiles with picture_download_count > 0")
    args = parser.parse_args()

    managers_dir = os.path.join("..", "Managers")
    to_process = []

    print(f"Phase 3a: Scanning for profiles needing LinkedIn scraping (retry_failed={args.retry_failed})...")
    for root, dirs, files in os.walk(managers_dir):
        if "Profile.json" in files:
            path = os.path.join(root, "Profile.json")
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                picture_local = data.get("picture_local")
                status = data.get("enrichment_socials")
                socials = data.get("socials", [])
                has_linkedin = any('linkedin.com' in s['url'].lower() for s in socials)
                download_count = data.get("picture_download_count", 0)
                
                # Check if file actually exists if picture_local is set
                file_exists = False
                if picture_local:
                    file_exists = os.path.exists(os.path.join(root, picture_local))

                is_eligible = False
                if status == "success" and has_linkedin:
                    if not picture_local or not file_exists:
                        if args.retry_failed == "yes" or download_count <= 0:
                            is_eligible = True
                
                if is_eligible:
                    to_process.append(path)
            except Exception:
                continue

    if not to_process:
        print("No profiles found needing LinkedIn scraping.")
        return

    profiles_to_process = PROFILES_TO_PROCESS
    if profiles_to_process > 0:
        to_process = to_process[:profiles_to_process]
    
    print(f"Phase 3a: Processing {len(to_process)} profiles.")
    
    print("Launching CloakBrowser...")
    browser = launch()
    page = browser.new_page()
    
    for i, path in enumerate(to_process):
        print(f"[{i+1}/{len(to_process)}] Processing {os.path.basename(os.path.dirname(path))}...")
        process_profile(page, path)
        
    print("Phase 3a: Finished processing all profiles.")
    browser.close()

if __name__ == '__main__':
    main()
