import os
import glob
import requests
from io import BytesIO
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont, ImageOps

# ---------------- কনফিগারেশন ----------------
JSON_URL = os.environ.get("KSA_SERVER1", "").strip()
ASSET_DIR = "ASSET"
POSTERS_DIR = "posters"
PLAYLIST_FILE = "LiveEVENT.m3u"

# পোস্টারের সাইজ
POSTER_WIDTH = 1280
POSTER_HEIGHT = 720

# আপনার GitHub রিপোজিটরি ও ব্রাঞ্চ
GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "easykity/jakson")
GITHUB_BRANCH = os.environ.get("GITHUB_REF_NAME", "main")
RAW_BASE_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{POSTERS_DIR}"

GOOGLE_FONT_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/Poppins-Bold.ttf"
LOCAL_FONT_CACHE = "/tmp/Poppins-Bold.ttf"

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


def ensure_google_font():
    # যদি ASSET ফোল্ডারে নিজের কোনো ফন্ট রাখেন, তবে সেটি আগে প্রাধান্য পাবে
    custom_fonts = glob.glob(os.path.join(ASSET_DIR, "*.ttf")) + glob.glob(os.path.join(ASSET_DIR, "*.otf"))
    if custom_fonts:
        return custom_fonts[0]

    # Google জনপ্রিয় Poppins-Bold ফন্ট ডাউনলোড করা
    if not os.path.exists(LOCAL_FONT_CACHE):
        try:
            print("Google Bold ফন্ট ডাউনলোড করা হচ্ছে (Poppins-Bold)...")
            r = requests.get(GOOGLE_FONT_URL, timeout=20)
            r.raise_for_status()
            with open(LOCAL_FONT_CACHE, "wb") as f:
                f.write(r.content)
        except Exception as e:
            print(f"Google ফন্ট ডাউনলোড ব্যর্থ, সিস্টেম Bold ফন্ট ব্যবহার করা হবে: {e}")

    if os.path.exists(LOCAL_FONT_CACHE):
        return LOCAL_FONT_CACHE

    for fallback in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ):
        if os.path.exists(fallback):
            return fallback
    return None


def load_font(font_path, size):
    if font_path:
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def fit_font_to_width(draw, text, font_path, start_size, max_width, stroke_width=4):
    size = start_size
    while size > 18:
        font = load_font(font_path, size)
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
        text_w = bbox[2] - bbox[0]
        if text_w <= max_width:
            return font
        size -= 2
    return load_font(font_path, 18)


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


def draw_centered_text(draw, text, y, font, fill="white", stroke_fill="black", stroke_width=5):
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


def create_poster(match, bg_path, font_path, output_path):
    bg = Image.open(bg_path).convert("RGBA")
    bg = ImageOps.fit(bg, (POSTER_WIDTH, POSTER_HEIGHT), Image.Resampling.LANCZOS)

    event = match.get("event", {})
    # সব লেখা বড় হাতের (UPPERCASE) করা হয়েছে
    tourney_name = event.get("name", "").strip().upper()
    match_title = match.get("title", "").strip().upper()

    tourney_logo = resize_contain(download_image(event.get("logo")), int(POSTER_WIDTH * 0.18), int(POSTER_HEIGHT * 0.17))
    team_a_flag = resize_contain(download_image(event.get("teamAFlag")), int(POSTER_WIDTH * 0.19), int(POSTER_HEIGHT * 0.26))
    team_b_flag = resize_contain(download_image(event.get("teamBFlag")), int(POSTER_WIDTH * 0.19), int(POSTER_HEIGHT * 0.26))

    draw = ImageDraw.Draw(bg)
    max_text_width = int(POSTER_WIDTH * 0.90)

    # ১. উপরে মাঝে টুর্নামেন্টের নাম (বোল্ড ও বড় হাতের)
    if tourney_name:
        font_tourney = fit_font_to_width(draw, tourney_name, font_path, int(POSTER_HEIGHT * 0.058), max_text_width)
        draw_centered_text(draw, tourney_name, int(POSTER_HEIGHT * 0.05), font_tourney)

    # ২. নামের নিচে মাঝে টুর্নামেন্টের লোগো
    if tourney_logo:
        lx = (POSTER_WIDTH - tourney_logo.width) // 2
        ly = int(POSTER_HEIGHT * 0.14)
        bg.paste(tourney_logo, (lx, ly), tourney_logo)

    # ৩. মাঝে বাম পাশে Team A, মাঝখানে VS, ডান পাশে Team B
    center_y = int(POSTER_HEIGHT * 0.53)

    if team_a_flag:
        ax = int(POSTER_WIDTH * 0.25) - (team_a_flag.width // 2)
        ay = center_y - (team_a_flag.height // 2)
        bg.paste(team_a_flag, (ax, ay), team_a_flag)

    if team_b_flag:
        bx = int(POSTER_WIDTH * 0.75) - (team_b_flag.width // 2)
        by = center_y - (team_b_flag.height // 2)
        bg.paste(team_b_flag, (bx, by), team_b_flag)

    font_vs = load_font(font_path, int(POSTER_HEIGHT * 0.08))
    vs_bbox = draw.textbbox((0, 0), "VS", font=font_vs, stroke_width=5)
    vs_h = vs_bbox[3] - vs_bbox[1]
    draw_centered_text(draw, "VS", center_y - (vs_h // 2) - 5, font_vs, fill="#FFD700")

    # ৪. দুই দলের নিচে ম্যাচের টাইটেল (বোল্ড ও বড় হাতের)
    if match_title:
        font_title = fit_font_to_width(draw, match_title, font_path, int(POSTER_HEIGHT * 0.068), max_text_width)
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
    if not JSON_URL:
        raise ValueError("KSA_SERVER1 সিক্রেট পাওয়া যায়নি! GitHub Secrets চেক করুন।")

    os.makedirs(POSTERS_DIR, exist_ok=True)
    bg_path = get_background_path()
    font_path = ensure_google_font()

    print("JSON ডাটা আনা হচ্ছে...")
    resp = requests.get(JSON_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    matches = resp.json()

    active_matches = [m for m in matches if is_match_active(m)]
    active_filenames = set()

    for m in active_matches:
        match_id = m.get("id")
        filename = f"{match_id}.png"
        active_filenames.add(filename)
        poster_path = os.path.join(POSTERS_DIR, filename)

        if not os.path.exists(poster_path):
            create_poster(m, bg_path, font_path, poster_path)

    # খেলা শেষ বা JSON-এ না থাকা পুরোনো পোস্টার ডিলিট করা
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
