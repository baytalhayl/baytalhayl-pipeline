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
from datetime import date, datetime
import io
import base64
import time

# ── Config ────────────────────────────────────────────────────────────────────
INSTAGRAM_USER_ID  = os.environ["INSTAGRAM_USER_ID"]
INSTAGRAM_TOKEN    = os.environ["INSTAGRAM_ACCESS_TOKEN"]
GITHUB_TOKEN       = os.environ["GITHUB_TOKEN"]
GITHUB_REPO        = os.environ["GITHUB_REPO"]
GRAPH_API_VERSION  = "v25.0"

QUEUE_FILE    = "queue.json"
TEMPLATE_FILE = "template.png"

SIZE  = 1080
WHITE = (1, 1, 1)
IVORY = (0.961, 0.925, 0.843)
GREEN = (0.176, 0.416, 0.176)

# ── Helpers ───────────────────────────────────────────────────────────────────
def set_color(ctx, c, a=1.0):
    ctx.set_source_rgba(c[0], c[1], c[2], a)

def get_line_count(ctx, text, font_desc, width):
    layout = PangoCairo.create_layout(ctx)
    layout.set_text(text, -1)
    layout.set_font_description(Pango.FontDescription(font_desc))
    layout.set_width(width * Pango.SCALE)
    return layout.get_line_count()

def get_text_height(ctx, text, font_desc, width):
    layout = PangoCairo.create_layout(ctx)
    layout.set_text(text, -1)
    layout.set_font_description(Pango.FontDescription(font_desc))
    layout.set_width(width * Pango.SCALE)
    _, lh = layout.get_pixel_size()
    return lh

def draw_hemistich(ctx, text, font_desc, y, x_start, width, row_height):
    layout = PangoCairo.create_layout(ctx)
    layout.set_text(text, -1)
    layout.set_font_description(Pango.FontDescription(font_desc))
    layout.set_alignment(Pango.Alignment.CENTER)
    layout.set_width(width * Pango.SCALE)
    _, lh = layout.get_pixel_size()
    set_color(ctx, WHITE)
    ctx.move_to(x_start, y + (row_height - lh) // 2)
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

# ── Step 2: Pick random poem from dataset ─────────────────────────────────────
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

        max_lines = min(6, len(verses))
        if max_lines % 2 != 0:
            max_lines -= 1
        n = 4 if max_lines < 6 else random.choice([4, 6])
        start = random.randint(0, len(verses) - n)
        if start % 2 != 0:
            start = max(0, start - 1)
        lines = verses[start:start + n]

        return {"id": poem_id, "poet": poet, "lines": lines}

    raise RuntimeError("No valid poems found in dataset.")

# ── Step 3: Generate image ────────────────────────────────────────────────────
def generate_image(lines, poet):
    output_file = f"output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

    template = Image.open(TEMPLATE_FILE).convert("RGBA")
    buf = io.BytesIO()
    template.save(buf, format="PNG")
    buf.seek(0)
    bg = cairo.ImageSurface.create_from_png(buf)

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, SIZE, SIZE)
    ctx = cairo.Context(surface)
    ctx.set_source_surface(bg, 0, 0)
    ctx.paint()

    couplets = [(lines[i], lines[i+1]) for i in range(0, len(lines)-1, 2)]
    n_couplets = len(couplets)

    MARGIN = 80
    half_w = (SIZE - 2 * MARGIN) // 2
    mid_x  = SIZE // 2

    # Auto-fit font size so no hemistich wraps
    font_size = 44
    while font_size >= 24:
        font_desc = f"Scheherazade {font_size}"
        if all(get_line_count(ctx, h, font_desc, half_w) == 1 for pair in couplets for h in pair):
            break
        font_size -= 2

    font_desc = f"Scheherazade {font_size}"
    GAP = 32
    row_height = max(get_text_height(ctx, h, font_desc, half_w) for pair in couplets for h in pair)

    content_top    = 148
    content_bottom = SIZE - 148
    content_height = content_bottom - content_top
    total_h        = n_couplets * (row_height + GAP) - GAP
    start_y        = content_top + (content_height - total_h) // 2

    for i, (right_h, left_h) in enumerate(couplets):
        y = start_y + i * (row_height + GAP)
        draw_hemistich(ctx, left_h, font_desc, y, MARGIN, half_w, row_height)
        draw_hemistich(ctx, right_h, font_desc, y, mid_x, half_w, row_height)

    # Symmetrical divider
    div_y = start_y + n_couplets * (row_height + GAP) + 10
    LINE_START = 200
    LINE_END   = 390
    set_color(ctx, WHITE, 0.6)
    ctx.set_line_width(1)
    ctx.move_to(LINE_START, div_y); ctx.line_to(LINE_END, div_y); ctx.stroke()
    ctx.move_to(SIZE - LINE_END, div_y); ctx.line_to(SIZE - LINE_START, div_y); ctx.stroke()
    set_color(ctx, GREEN, 0.8)
    ctx.move_to(LINE_START, div_y - 3); ctx.line_to(LINE_END, div_y - 3); ctx.stroke()
    ctx.move_to(SIZE - LINE_END, div_y - 3); ctx.line_to(SIZE - LINE_START, div_y - 3); ctx.stroke()

    # Poet name
    layout = PangoCairo.create_layout(ctx)
    layout.set_text(f"— {poet}", -1)
    layout.set_font_description(Pango.FontDescription("Scheherazade 36"))
    layout.set_alignment(Pango.Alignment.CENTER)
    layout.set_width(SIZE * Pango.SCALE)
    _, lh = layout.get_pixel_size()
    set_color(ctx, IVORY)
    ctx.move_to(0, div_y + 40 - lh // 2)
    PangoCairo.show_layout(ctx, layout)

    surface.write_to_png(output_file)
    print(f"Image generated: {output_file}")
    return output_file

# ── Step 4: Upload image to GitHub ────────────────────────────────────────────
def upload_to_github(output_file):
    with open(output_file, "rb") as f:
        content = base64.b64encode(f.read()).decode()

    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{output_file}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}

    r = requests.get(api_url, headers=headers)
    sha = r.json().get("sha") if r.status_code == 200 else None

    payload = {"message": f"post: {date.today()}", "content": content}
    if sha:
        payload["sha"] = sha

    r = requests.put(api_url, headers=headers, json=payload)
    r.raise_for_status()

    raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{output_file}"
    print(f"Uploaded to GitHub: {raw_url}")
    return raw_url

# ── Step 5: Post to Instagram ─────────────────────────────────────────────────
def post_to_instagram(image_url, caption):
    base = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{INSTAGRAM_USER_ID}"

    r = requests.post(f"{base}/media", data={
        "image_url": image_url,
        "caption":   caption,
        "access_token": INSTAGRAM_TOKEN,
    })
    print(f"Instagram response: {r.status_code} {r.text}")
    r.raise_for_status()
    container_id = r.json()["id"]

    # Poll until container is ready
    for attempt in range(10):
        time.sleep(10)
        status_r = requests.get(
            f"https://graph.facebook.com/{GRAPH_API_VERSION}/{container_id}",
            params={"fields": "status_code", "access_token": INSTAGRAM_TOKEN}
        )
        status = status_r.json().get("status_code", "")
        print(f"Container status: {status}")
        if status == "FINISHED":
            break
        elif status == "ERROR":
            raise RuntimeError("Instagram container processing failed.")
    else:
        raise RuntimeError("Container never became ready after 100 seconds.")

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

    for _ in range(20):
        poem = fetch_poem()
        if not already_posted(queue, poem["id"]):
            break
    else:
        raise RuntimeError("Could not find an unposted poem after 20 attempts.")

    print(f"Poem fetched: {poem['poet']} — {poem['lines'][0][:30]}...")

    output_file = generate_image(poem["lines"], poem["poet"])
    image_url   = upload_to_github(output_file)
    time.sleep(30)

    caption = "\n".join(poem["lines"]) + f"\n\n— {poem['poet']}"

    queue.append({"id": poem["id"], "poet": poem["poet"], "posted_at": str(date.today())})
    save_queue(queue)
    commit_queue(queue)

    post_to_instagram(image_url, caption)

    print("Done!")

if __name__ == "__main__":
    main()
