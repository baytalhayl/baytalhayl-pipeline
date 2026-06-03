"""
Downloads the Ashaar dataset from Hugging Face and saves a curated
JSON file of poems with 4+ verses to the repo.
"""
import json
import base64
import os
import requests
import random

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_REPO  = os.environ["GITHUB_REPO"]
OUTPUT_FILE  = "aldiwan_poems.json"
TARGET       = 5000

def commit_to_github(poems):
    content  = base64.b64encode(json.dumps(poems, ensure_ascii=False, indent=2).encode()).decode()
    api_url  = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{OUTPUT_FILE}"
    headers  = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}

    r   = requests.get(api_url, headers=headers)
    sha = r.json().get("sha") if r.status_code == 200 else None

    payload = {"message": f"scrape: {len(poems)} poems from Ashaar dataset", "content": content}
    if sha:
        payload["sha"] = sha

    r = requests.put(api_url, headers=headers, json=payload)
    r.raise_for_status()
    print(f"Committed {len(poems)} poems to {OUTPUT_FILE}")

def main():
    from datasets import load_dataset
    print("Downloading Ashaar dataset...")
    ds = load_dataset("arbml/ashaar", split="train", trust_remote_code=True)
    print(f"Dataset loaded: {len(ds)} poems")
    print(f"Columns: {ds.column_names}")

    poems = []
    indices = list(range(len(ds)))
    random.shuffle(indices)

    for i in indices:
        if len(poems) >= TARGET:
            break
        item   = ds[i]
        verses = item.get("poem verses", [])
        poet   = item.get("poet name", "مجهول")

        if not isinstance(verses, list) or len(verses) < 4:
            continue
        if not poet or not isinstance(poet, str):
            continue

        poems.append({
            "poet":   poet.strip(),
            "verses": [v.strip() for v in verses if v and v.strip()]
        })

    print(f"Collected {len(poems)} valid poems.")
    commit_to_github(poems)
    print("Done!")

if __name__ == "__main__":
    main()
