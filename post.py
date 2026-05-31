import os
import json
import random
import requests
import cairo
import gi
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Pango, PangoCairo
from PIL import Image
from datetime import date
import io
import base64

# ── Config ────────────────────────────────────────────────────────────────────
INSTAGRAM_USER_ID  = os.environ["INSTAGRAM_USER_ID"]
INSTAGRAM_TOKEN    = os.environ["INSTAGRAM_ACCESS_TOKEN"]
GITHUB_TOKEN       = os.environ["GITHUB_TOKEN"]
GITHUB_REPO        = os.environ["GITHUB_REPO"]          # e.g. "baytalhayl/baytalhayl-pipeline"
GRAPH_API_VERSION  = "v25.0"

QUEUE_FILE    = "queue.json"
TEMPLATE_FILE = "template.png"
OUTPUT_FILE   = "output.png"

SIZE  = 1080
WHITE = (1, 1, 1)
IVORY = (0.961, 0.925, 0.843)
GREEN = (0.176, 0.416, 0.176)

# ── Helpers ───────────────────────────────────────────────────────────────────
def set_color(ctx, c, a=1.0):
    ctx.set_source_rgba(c[0], c[1], c[2], a)

def draw_centered_text(ctx, text, font_desc, y, color=WHITE):
    layout = PangoCairo.create_layout(ctx)
    layout.set_text(text, -1)
    layout.set_font_description(Pango.FontDescription(font_desc))
    layout.set_alignment(Pango.Alignment.CENTER)
    layout.set_width((SIZE - 160) * Pango.SCALE)
    _, lh = layout.get_pixel_size()
    set_color(ctx, color)
    ctx.move_to(80, y - lh // 2)
    PangoCairo.show_layout(ctx, layout)

# ── Step 1: Load queue ────────────────────────────────────────────────────────
def load_queue():
    if not os.path.exists(QUEUE_FILE):
        return []
    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_queue(queue):
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)

def already_posted(queue, poem_id):
    return any(p["id"] == poem_id for p in queue)

# ── Step 2: Pick random poem from local dataset ───────────────────────────────
def fetch_poem():
    with open("aldiwan_poems.json", "r", encoding="utf-8") as f:
        poems = json.load(f)

    random.shuffle(poems)

    for poem in poems:
        poem_id = f"{poem['poet']}_{poem['verses'][0][:10]}"
        verses  = poem["verses"]
        poet    = poem["poet"]

        if len(verses) < 4:
            continue

        n     = random.randint(4, min(6, len(verses)))
        start = random.randint(0, len(verses) - n)
        lines = verses[start:start + n]

        return {
            "id":    poem_id,
            "poet":  poet,
            "lines": lines,
        }

    raise RuntimeError("No valid poems found in dataset.")

# ── Step 3: Generate image ────────────────────────────────────────────────────
def generate_image(lines, poet):
    template = Image.open(TEMPLATE_FILE).convert("RGBA")
    buf = io.BytesIO()
    template.save(buf, format="PNG")
    buf.seek(0)
    bg = cairo.ImageSurface.create_from_png(buf)

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, SIZE, SIZE)
    ctx = cairo.Context(surface)
    ctx.set_source_surface(bg, 0, 0)
    ctx.paint()

    n = len(lines)
    if n <= 4:
        font_size = 74
    elif n == 5:
        font_size = 66
    else:
        font_size = 58

    line_spacing   = font_size + 28
    content_top    = 148
    content_bottom = SIZE - 148
    content_height = content_bottom - content_top
    total_h        = n * line_spacing + 70 + 55
    start_y        = content_top + (content_height - total_h) // 2 + font_size // 2

    for i, line in enumerate(lines):
        draw_centered_text(ctx, line, f"Scheherazade {font_size}", start_y + i * line_spacing)

    div_y = start_y + n * line_spacing + 18
    set_color(ctx, WHITE, 0.6)
    ctx.set_line_width(1)
    ctx.move_to(280, div_y); ctx.line_to(490, div_y); ctx.stroke()
    set_color(ctx, GREEN, 0.8)
    ctx.move_to(280, div_y - 3); ctx.line_to(490, div_y - 3); ctx.stroke()
    set_color(ctx, WHITE)
    ctx.move_to(SIZE//2, div_y - 10)
    ctx.line_to(SIZE//2 + 10, div_y)
    ctx.line_to(SIZE//2, div_y + 10)
    ctx.line_to(SIZE//2 - 10, div_y)
    ctx.close_path(); ctx.fill()

    draw_centered_text(ctx, f"— {poet}", "Scheherazade 36", div_y + 46, color=IVORY)

    surface.write_to_png(OUTPUT_FILE)
    print(f"Image generated: {OUTPUT_FILE}")

# ── Step 4: Upload image to GitHub ────────────────────────────────────────────
def upload_to_github():
    with open(OUTPUT_FILE, "rb") as f:
        content = base64.b64encode(f.read()).decode()

    path    = OUTPUT_FILE
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}

    # Check if file already exists (need SHA to update)
    r = requests.get(api_url, headers=headers)
    sha = r.json().get("sha") if r.status_code == 200 else None

    payload = {
        "message": f"post: {date.today()}",
        "content": content,
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(api_url, headers=headers, json=payload)
    r.raise_for_status()

    raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{path}"
    print(f"Uploaded to GitHub: {raw_url}")
    return raw_url

# ── Step 5: Post to Instagram ─────────────────────────────────────────────────
def post_to_instagram(image_url, caption):
    base = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{INSTAGRAM_USER_ID}"

    # Create container
    r = requests.post(f"{base}/media", data={
        "image_url": image_url,
        "caption":   caption,
        "access_token": INSTAGRAM_TOKEN,
    })
    print(f"Instagram response: {r.status_code} {r.text}")
    r.raise_for_status()
    container_id = r.json()["id"]

    # Publish
    r = requests.post(f"{base}/media_publish", data={
        "creation_id":  container_id,
        "access_token": INSTAGRAM_TOKEN,
    })
    print(f"Publish response: {r.status_code} {r.text}")
    r.raise_for_status()
    post_id = r.json()["id"]
    print(f"Posted to Instagram: {post_id}")
    return post_id

# ── Step 6: Update queue and commit ──────────────────────────────────────────
def commit_queue(queue):
    content  = base64.b64encode(json.dumps(queue, ensure_ascii=False, indent=2).encode()).decode()
    api_url  = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{QUEUE_FILE}"
    headers  = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}

    r   = requests.get(api_url, headers=headers)
    sha = r.json().get("sha") if r.status_code == 200 else None

    payload = {"message": f"queue: {date.today()}", "content": content}
    if sha:
        payload["sha"] = sha

    r = requests.put(api_url, headers=headers, json=payload)
    r.raise_for_status()
    print("Queue committed to GitHub.")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    queue = load_queue()
    print(f"Queue has {len(queue)} entries.")

    # Fetch a poem not already posted
    for _ in range(20):
        poem = fetch_poem()
        if not already_posted(queue, poem["id"]):
            break
    else:
        raise RuntimeError("Could not find an unposted poem after 20 attempts.")

    print(f"Poem fetched: {poem['poet']} — {poem['lines'][0][:30]}...")

    # Generate image
    generate_image(poem["lines"], poem["poet"])

    # Upload to GitHub
    image_url = upload_to_github()
    import time
    time.sleep(10)
    # Build caption — poem lines + poet name
    caption = "\n".join(poem["lines"]) + f"\n\n— {poem['poet']}"

    # Post to Instagram
    post_to_instagram(image_url, caption)

    # Update queue
    queue.append({"id": poem["id"], "poet": poem["poet"], "posted_at": str(date.today())})
    save_queue(queue)
    commit_queue(queue)

    print("Done!")

if __name__ == "__main__":
    main()
