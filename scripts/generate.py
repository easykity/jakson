import os
import glob
import requests
from io import BytesIO
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont, ImageOps

# ---------------- কনফিগারেশন ----------------
JSON_URL = "https://allrounderlive.in/api/football.json"
ASSET_DIR = "ASSET"
POSTERS_DIR = "posters"
PLAYLIST_FILE = "playlist.m3u"

# পোস্টারের সাইজ (আপনার প্রয়োজনমতো Width ও Height পরিবর্তন করতে পারবেন)
POSTER_WIDTH = 1280
POSTER_HEIGHT = 720

# GitHub Raw URL অটোমেটিক তৈরি হবে (GitHub Actions থেকে)
GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "YOUR_USERNAME/YOUR_REPO")
GITHUB_BRANCH = os.environ.get("GITHUB_REF_NAME", "main")
RAW_BASE_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{POSTERS_DIR}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json,image/webp,image/apng,image/*,*/*;q=0.8",
    "Referer": "https://allrounderlive.in/"
}


def get_background_path():
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.PNG", "*.JPG", "*.JPEG"):
        files = glob.glob(os.path.join(ASSET_DIR, ext))
        if files:
            return files[0]
    raise FileNotFoundError(f"'{ASSET_DIR}' ফোল্ডারে কোনো ব্যাকগ্রাউন্ড ছবি পাওয়া যায়নি!")


def load_font(size):
    font_candidates = glob.glob(os.path.join(ASSET_DIR, "*.ttf")) + glob.glob(os.path.join(ASSET_DIR, "*.otf")) + [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for path in font_candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def download_image(url):
    if not url:
        return None
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return Image.open(BytesIO(resp.content)).convert("RGBA")
    except Exception as e:
        print(f"ইমেজ ডাউনলোড ব্যর্থ ({url}): {e}")
        return None


def resize_contain(img, max_w, max_h):
    if img is None:
        return None
    copy_img = img.copy()
    copy_img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    return copy_img


def draw_centered_text(draw, text, y, font, fill="white", stroke_fill="black", stroke_width=4):
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    text_w = bbox[2] - bbox[0]
    x = (POSTER_WIDTH - text_w) // 2
    draw.text((x, y), text, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill)


def is_match_active(match):
    event = match.get("event", {})
    end_utc_str = event.get("endTimeUTC")
    if not end_utc_str:
        return True
    try:
        end_dt = datetime.strptime(end_utc_str, "%Y/%m/%d %H:%M:%S %z")
        now_utc = datetime.now(timezone.utc)
        return now_utc <= end_dt
    except Exception:
        return True


def create_poster(match, bg_path, output_path):
    bg = Image.open(bg_path).convert("RGBA")
    bg = ImageOps.fit(bg, (POSTER_WIDTH, POSTER_HEIGHT), Image.Resampling.LANCZOS)

    event = match.get("event", {})
    tourney_name = event.get("name", "").strip()
    match_title = match.get("title", "").strip()

    tourney_logo = resize_contain(download_image(event.get("logo")), int(POSTER_WIDTH * 0.18), int(POSTER_HEIGHT * 0.16))
    team_a_flag = resize_contain(download_image(event.get("teamAFlag")), int(POSTER_WIDTH * 0.18), int(POSTER_HEIGHT * 0.25))
    team_b_flag = resize_contain(download_image(event.get("teamBFlag")), int(POSTER_WIDTH * 0.18), int(POSTER_HEIGHT * 0.25))

    draw = ImageDraw.Draw(bg)

    # ফন্ট সাইজ (পোস্টারের উচ্চতা অনুযায়ী আনুপাতিক)
    font_tourney = load_font(int(POSTER_HEIGHT * 0.055))
    font_vs = load_font(int(POSTER_HEIGHT * 0.075))
    font_title = load_font(int(POSTER_HEIGHT * 0.065))

    # ১. উপরে মাঝে টুর্নামেন্টের নাম (name)
    if tourney_name:
        draw_centered_text(draw, tourney_name.upper(), int(POSTER_HEIGHT * 0.05), font_tourney)

    # ২. নামের নিচে মাঝে টুর্নামেন্টের লোগো (logo)
    if tourney_logo:
        lx = (POSTER_WIDTH - tourney_logo.width) // 2
        ly = int(POSTER_HEIGHT * 0.14)
        bg.paste(tourney_logo, (lx, ly), tourney_logo)

    # ৩. মাঝে বাম পাশে Team A, মাঝখানে VS, ডান পাশে Team B
    center_y = int(POSTER_HEIGHT * 0.52)

    if team_a_flag:
        ax = int(POSTER_WIDTH * 0.25) - (team_a_flag.width // 2)
        ay = center_y - (team_a_flag.height // 2)
        bg.paste(team_a_flag, (ax, ay), team_a_flag)

    if team_b_flag:
        bx = int(POSTER_WIDTH * 0.75) - (team_b_flag.width // 2)
        by = center_y - (team_b_flag.height // 2)
        bg.paste(team_b_flag, (bx, by), team_b_flag)

    # VS টেক্সট মাঝখানে
    vs_bbox = draw.textbbox((0, 0), "VS", font=font_vs, stroke_width=4)
    vs_h = vs_bbox[3] - vs_bbox[1]
    draw_centered_text(draw, "VS", center_y - (vs_h // 2) - 5, font_vs, fill="#FFD700")

    # ৪. দুই দলের নিচে ম্যাচের টাইটেল (title)
    if match_title:
        draw_centered_text(draw, match_title, int(POSTER_HEIGHT * 0.78), font_title)

    bg.convert("RGB").save(output_path, "PNG", optimize=True)
    print(f"পোস্টার তৈরি হয়েছে: {output_path}")


def category_priority(cat_name):
    c = cat_name.strip().lower()
    if c == "football":
        return (0, c)
    elif c == "cricket":
        return (1, c)
    return (2, c)


def main():
    os.makedirs(POSTERS_DIR, exist_ok=True)
    bg_path = get_background_path()

    print("JSON ডাটা আনা হচ্ছে...")
    resp = requests.get(JSON_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    matches = resp.json()

    # যেসব ম্যাচ এখনো শেষ হয়নি ও JSON-এ আছে সেগুলো ফিল্টার করা
    active_matches = [m for m in matches if is_match_active(m)]
    active_filenames = set()

    for m in active_matches:
        match_id = m.get("id")
        filename = f"{match_id}.png"
        active_filenames.add(filename)
        poster_path = os.path.join(POSTERS_DIR, filename)

        # আগে থেকে পোস্টার না থাকলে নতুন করে বানাবে (ফলে প্রতি ৫ মিনিটে অযথা রিকোয়েস্ট হবে না)
        if not os.path.exists(poster_path):
            create_poster(m, bg_path, poster_path)

    # খেলা শেষ হওয়া বা JSON থেকে বাদ পড়া পুরোনো পোস্টার ডিলিট করা
    for existing_file in os.listdir(POSTERS_DIR):
        if existing_file not in active_filenames:
            old_path = os.path.join(POSTERS_DIR, existing_file)
            if os.path.isfile(old_path):
                os.remove(old_path)
                print(f"পুরোনো পোস্টার ডিলিট করা হয়েছে: {old_path}")

    # প্লেলিস্ট সাজানো: Football -> Cricket -> অন্যান্য
    sorted_matches = sorted(
        active_matches,
        key=lambda m: category_priority(m.get("event", {}).get("category") or m.get("cat") or "Other")
    )

    m3u_lines = ["#EXTM3U"]
    for m in sorted_matches:
        streams = m.get("dashStreams") or []
        if not streams:
            continue

        match_id = m.get("id")
        match_title = m.get("title", "").strip()
        category = (m.get("event", {}).get("category") or m.get("cat") or "Sports").strip()
        poster_url = f"{RAW_BASE_URL}/{match_id}.png"

        for s in streams:
            stream_title = s.get("title", "").strip()
            stream_type = s.get("type", "").strip().lower()
            stream_url = s.get("url", "").strip()
            stream_key = s.get("key", "").strip()

            if not stream_url:
                continue

            full_title = f"{match_title} {stream_title}".strip()
            m3u_lines.append(f'#EXTINF:-1 tvg-logo="{poster_url}" group-title="{category}", {full_title}')

            if stream_type == "dash" or ".mpd" in stream_url.lower():
                m3u_lines.append("#KODIPROP:inputstream=inputstream.adaptive")
                m3u_lines.append("#KODIPROP:inputstream.adaptive.manifest_type=mpd")
                if stream_key:
                    m3u_lines.append("#KODIPROP:inputstream.adaptive.license_type=clearkey")
                    m3u_lines.append(f"#KODIPROP:inputstream.adaptive.license_key={stream_key}")

            m3u_lines.append(stream_url)

    with open(PLAYLIST_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(m3u_lines) + "\n")

    print(f"প্লেলিস্ট আপডেট সম্পন্ন: {PLAYLIST_FILE}")


if __name__ == "__main__":
    main()
