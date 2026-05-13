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
        
        # Collect all LinkedIn URLs
        linkedin_urls = []
        for s in socials:
            if 'linkedin.com' in s.get('url', '').lower():
                # Skip if status is not_found or private as per upstream check
                if s.get('profile_status') in ['not_found', 'private']:
                    print(f"  -> Skipping LinkedIn URL {s['url']} (status: {s['profile_status']})")
                    continue
                linkedin_urls.append(s['url'])
        
        if not linkedin_urls:
            print(f"  -> No eligible LinkedIn URL for {full_name}. Skipping.")
            return

        blacklist = tools.get_blacklist()
        
        found_image = False
        for linkedin_url in linkedin_urls:
            if linkedin_url.lower().rstrip('/') in blacklist:
                print(f"  -> LinkedIn URL {linkedin_url} is in blacklist. Skipping.")
                continue

            # Increment download attempt count
            profile['picture_download_count'] = profile.get('picture_download_count', 0) + 1
            for s in profile.get('socials', []):
                if s.get('url') == linkedin_url:
                    s['picture_download_count'] = s.get('picture_download_count', 0) + 1
                    break

            print(f"  -> Navigating to {linkedin_url}...")
            username = linkedin_url.rstrip('/').split('/')[-1]
            if not username:
                username = full_name.replace(" ", "_")

            try:
                page.goto(linkedin_url, wait_until='domcontentloaded', timeout=30000)
                time.sleep(5) # Wait for dynamic content
                
                # Check for Auth Wall or Login Redirect
                current_url = page.url
                is_auth_wall = any(x in current_url for x in ['linkedin.com/authwall', 'linkedin.com/login', 'checkpoint/lg/login'])
                
                # Check for login form or sign-in elements if URL check is not enough
                if not is_auth_wall:
                    is_auth_wall = page.evaluate('''() => {
                        const body = document.body.innerText.toLowerCase();
                        return body.includes('sign in to linkedin') || 
                               !!document.querySelector('form[data-adv-search-form]') ||
                               !!document.querySelector('input[name="session_key"]');
                    }''')

                if is_auth_wall:
                    print(f"  -> AUTH WALL DETECTED for {linkedin_url}. Profile is likely private or requires login.")
                    # Update profile_status in the matching social entry
                    for s in profile.get('socials', []):
                        if s.get('url') == linkedin_url:
                            s['profile_status'] = 'private'
                            break
                    # We continue to fallback, but we know why it failed.
                
                img_selector = 'img.top-card__profile-image, img[src*="profile-displayphoto"]'
                img_src = None
                try:
                    page.wait_for_selector(img_selector, timeout=10000)
                    img_src = page.evaluate(f"() => {{ const el = document.querySelector('{img_selector}'); return el ? el.src : null; }}")
                except Exception:
                    print(f"  -> Could not find image element on LinkedIn for {full_name} at {linkedin_url}.")
                
                # If img_src is found, try to download it. If it's an SVG placeholder, it will be rejected.
                local_filename = None
                if img_src:
                    print(f"  -> Found LinkedIn image URL: {img_src[:80]}...")
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
                                    print(f"  -> Rejected base64 SVG placeholder from {linkedin_url}.")
                                    os.remove(full_path)
                                    img_src = None # Trigger fallback
                        except Exception: pass
                        
                        if img_src: # If not rejected
                            local_filename = filename
                    else:
                        local_filename = tools.download_image(img_src, manager_dir)
                        if not local_filename:
                            img_src = None # Trigger fallback

                # Fallback to Google Image Search if no valid image found yet
                if not img_src:
                    img_src = get_google_image(page, username)
                    if img_src:
                        print(f"  -> Found fallback image URL: {img_src[:80]}...")
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
                            local_filename = filename
                        else:
                            local_filename = tools.download_image(img_src, manager_dir)
                    
                if local_filename:
                    profile['picture_local'] = local_filename
                    profile['picture_url'] = img_src
                    # Reset download count on success for top level and matching social
                    profile['picture_download_count'] = 0
                    for s in profile.get('socials', []):
                        if s.get('url') == linkedin_url:
                            s['picture_download_count'] = 0
                            break
                    
                    print(f"  -> Successfully updated picture metadata from {linkedin_url}.")
                    found_image = True
                    break # Success! Stop iterating URLs
                else:
                    print(f"  -> No valid image found for {full_name} at {linkedin_url} even after fallback")
                
            except Exception as e:
                print(f"  -> Error processing {linkedin_url}: {e}")
        
        # Save updated profile (with increments or success)
        with open(profile_path, 'w', encoding='utf-8') as f:
            json.dump(profile, f, indent=2)
            
    except Exception as e:
        print(f"  -> Error reading/processing profile {profile_path}: {e}")

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
