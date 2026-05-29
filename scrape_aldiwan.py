import requests
from bs4 import BeautifulSoup
import json
import random
import time
import base64
import os

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_REPO  = os.environ["GITHUB_REPO"]
OUTPUT_FILE  = "aldiwan_poems.json"
TARGET       = 500  # number of poems to collect
HEADERS      = {"User-Agent": "Mozilla/5.0 (compatible; bot)"}

def scrape_poem(poem_id):
    url = f"https://www.aldiwan.net/poem{poem_id}.html"
    try:
        r = requests.get(url, timeout=10, headers=HEADERS)
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, "html.parser")

        # Poet name
        poet_tag = (
            soup.find("div", class_="poet-name") or
            soup.find("a", class_="poet") or
            soup.find("span", class_="poet") or
            soup.find("div", class_="ShaarName")
        )
        poet = poet_tag.get_text(strip=True) if poet_tag else None
        if not poet:
            return None

        # Verses
        verse_tags = (
            soup.find_all("div", class_="b") or
            soup.find_all("td", class_="b") or
            soup.find_all("div", class_="bayt")
        )
        verses = [v.get_text(strip=True) for v in verse_tags]
        verses = [v for v in verses if v and len(v) > 5]

        if len(verses) < 4:
            return None

        return {"poet": poet, "verses": verses}

    except Exception as e:
        print(f"  Error scraping poem {poem_id}: {e}")
        return None

def commit_to_github(poems):
    content  = base64.b64encode(json.dumps(poems, ensure_ascii=False, indent=2).encode()).decode()
    api_url  = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{OUTPUT_FILE}"
    headers  = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}

    r   = requests.get(api_url, headers=headers)
    sha = r.json().get("sha") if r.status_code == 200 else None

    payload = {"message": f"scrape: {len(poems)} poems from aldiwan", "content": content}
    if sha:
        payload["sha"] = sha

    r = requests.put(api_url, headers=headers, json=payload)
    r.raise_for_status()
    print(f"Committed {len(poems)} poems to {OUTPUT_FILE}")

def main():
    poems   = []
    ids     = random.sample(range(1, 10000), min(TARGET * 3, 9000))
    checked = 0

    for poem_id in ids:
        if len(poems) >= TARGET:
            break

        checked += 1
        print(f"Checking poem {poem_id} ({len(poems)}/{TARGET} collected)...")
        poem = scrape_poem(poem_id)

        if poem:
            poems.append(poem)
            print(f"  ✓ {poem['poet']} — {len(poem['verses'])} verses")

        # Be polite — don't hammer the server
        time.sleep(0.5)

        # Save progress every 50 poems
        if len(poems) % 50 == 0 and len(poems) > 0:
            print(f"Progress save: {len(poems)} poems collected")
            commit_to_github(poems)

    commit_to_github(poems)
    print(f"Done! Scraped {len(poems)} poems from {checked} attempts.")

if __name__ == "__main__":
    main()
