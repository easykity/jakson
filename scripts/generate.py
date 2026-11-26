import os
import glob
import shutil
import subprocess
import requests
from urllib.parse import quote
from io import BytesIO
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont, ImageOps

try:
    from curl_cffi import requests as cf_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

# ---------------- Configuration ----------------
JSON_URL = (os.environ.get("KSA_SERVER1") or "").strip()
ASSET_DIR = "ASSET"
POSTERS_DIR = "posters"
PLAYLIST_FILE = "LiveEVENT.m3u"
TEMPLATE_VERSION = "v7"

# Poster dimensions (16:9)
POSTER_WIDTH = 800
POSTER_HEIGHT = 450

# GitHub repository and branch
GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "easykity/jakson")
GITHUB_BRANCH = os.environ.get("GITHUB_REF_NAME", "main")
RAW_BASE_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{POSTERS_DIR}"

GOOGLE_FONT_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/Poppins-Bold.ttf"
LOCAL_FONT_CACHE = "/tmp/Poppins-Bold.ttf"

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
}


def get_background_path():
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.PNG", "*.JPG", "*.JPEG"):
        files = glob.glob(os.path.join(ASSET_DIR, ext))
        if files:
            return files[0]
    raise FileNotFoundError(f"No background image found in '{ASSET_DIR}' folder!")


def ensure_google_font():
    custom_fonts = glob.glob(os.path.join(ASSET_DIR, "*.ttf")) + glob.glob(os.path.join(ASSET_DIR, "*.otf"))
    if custom_fonts:
        return custom_fonts[0]

    if not os.path.exists(LOCAL_FONT_CACHE):
        try:
            print("Downloading Google Bold font (Poppins-Bold)...")
            r = requests.get(GOOGLE_FONT_URL, timeout=20)
            r.raise_for_status()
            with open(LOCAL_FONT_CACHE, "wb") as f:
                f.write(r.content)
        except Exception as e:
            print(f"Google font download failed: {e}")

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


def fit_font_to_width(draw, text, font_path, start_size, max_width, stroke_width=2):
    min_size = max(12, round(20 * (POSTER_HEIGHT / 720)))
    size = start_size
    while size > min_size:
        font = load_font(font_path, size)
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
        text_w = bbox[2] - bbox[0]
        if text_w <= max_width:
            return font
        size -= 1
    return load_font(font_path, min_size)


def download_image(url):
    if not url:
        return None

    if HAS_CURL_CFFI:
        try:
            resp = cf_requests.get(
                url,
                impersonate="chrome",
                headers={"Referer": "https://www.sofascore.com/"},
                timeout=15,
            )
            if resp.status_code == 200 and resp.content:
                return Image.open(BytesIO(resp.content)).convert("RGBA")
        except Exception as e:
            print(f"curl_cffi failed ({url}): {e}")

    try:
        resp = requests.get(
            url,
            headers={**BROWSER_HEADERS, "Referer": "https://www.sofascore.com/"},
            timeout=15,
        )
        if resp.status_code == 200 and resp.content:
            return Image.open(BytesIO(resp.content)).convert("RGBA")
    except Exception as e:
        print(f"requests failed ({url}): {e}")

    try:
        proxy_url = f"https://wsrv.nl/?url={quote(url, safe='')}&output=png"
        resp = requests.get(proxy_url, headers=BROWSER_HEADERS, timeout=20)
        if resp.status_code == 200 and resp.content:
            return Image.open(BytesIO(resp.content)).convert("RGBA")
    except Exception as e:
        print(f"proxy failed ({url}): {e}")

    return None


def crop_transparent(img):
    if img is None:
        return None
    bbox = img.getbbox()
    if bbox:
        return img.crop(bbox)
    return img


def scale_to_fit(img, target_w, target_h):
    if img is None:
        return None
    img = crop_transparent(img)
    w, h = img.size
    if w == 0 or h == 0:
        return None
    ratio = min(target_w / w, target_h / h)
    new_w = max(1, int(w * ratio))
    new_h = max(1, int(h * ratio))
    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)


def draw_text_centered_at(draw, text, center_x, y, font, fill="white", stroke_fill="black", stroke_width=2):
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    text_w = bbox[2] - bbox[0]
    x = center_x - (text_w // 2) - bbox[0]
    draw.text((x, y), text, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill)


def draw_text_centered_xy(draw, text, center_x, center_y, font, fill="white", stroke_fill="black", stroke_width=2):
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = center_x - (text_w // 2) - bbox[0]
    y = center_y - (text_h // 2) - bbox[1]
    draw.text((x, y), text, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill)


def is_match_active(match):
    event = match.get("event") or {}
    end_utc_str = event.get("endTimeUTC")
    if not end_utc_str:
        return True
    try:
        end_dt = datetime.strptime(end_utc_str, "%Y/%m/%d %H:%M:%S %z")
        now_utc = datetime.now(timezone.utc)
        return now_utc <= end_dt
    except Exception:
        return True


def get_match_category(match):
    event = match.get("event") or {}
    cat = event.get("category") or match.get("category") or match.get("cat") or "Sports"
    return str(cat).strip()


def run_pngquant(input_path, output_path, quality_range):
    if os.path.exists(output_path):
        os.remove(output_path)
    subprocess.run(
        [
            "pngquant",
            "--force",
            "--output", output_path,
            f"--quality={quality_range}",
            "--speed=1",
            "--",
            input_path,
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return os.path.exists(output_path)


def save_compressed_png(img, output_path, max_kb=250):
    rgb = img.convert("RGB")
    max_bytes = max_kb * 1024
    rgb.save(output_path, format="PNG", optimize=True)

    if os.path.getsize(output_path) <= max_bytes:
        print(f"Poster created: {output_path} ({os.path.getsize(output_path) // 1024} KB)")
        return

    pngquant_bin = shutil.which("pngquant")
    if pngquant_bin:
        tmp_out = output_path + ".tmp.png"
        for q_range in ("80-95", "65-85", "50-75"):
            if run_pngquant(output_path, tmp_out, q_range):
                if os.path.getsize(tmp_out) <= max_bytes or q_range == "50-75":
                    shutil.move(tmp_out, output_path)
                    if os.path.getsize(output_path) <= max_bytes:
                        print(f"Poster created: {output_path} ({os.path.getsize(output_path) // 1024} KB)")
                        return
                    break

        if os.path.getsize(output_path) > max_bytes:
            smaller = rgb.resize((640, 360), Image.Resampling.LANCZOS)
            smaller.save(output_path, format="PNG", optimize=True)
            if run_pngquant(output_path, tmp_out, "75-92"):
                shutil.move(tmp_out, output_path)

        if os.path.exists(tmp_out):
            os.remove(tmp_out)

        print(f"Poster created: {output_path} ({os.path.getsize(output_path) // 1024} KB)")
        return

    # Pillow fallback with smooth Floyd-Steinberg dithering if pngquant is unavailable
    for candidate in (rgb, rgb.resize((640, 360), Image.Resampling.LANCZOS)):
        q = candidate.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG)
        buf = BytesIO()
        q.save(buf, format="PNG", optimize=True)
        data = buf.getvalue()
        with open(output_path, "wb") as f:
            f.write(data)
        if len(data) <= max_bytes:
            break

    print(f"Poster created: {output_path} ({os.path.getsize(output_path) // 1024} KB)")


def create_poster(match, bg_path, font_path, output_path):
    bg = Image.open(bg_path).convert("RGBA")
    bg = ImageOps.fit(bg, (POSTER_WIDTH, POSTER_HEIGHT), Image.Resampling.LANCZOS)

    event = match.get("event") or {}
    tourney_name = (event.get("name") or "").replace("\n", " ").strip().upper()
    team_a_name = (event.get("teamA") or "").replace("\n", " ").strip().upper()
    team_b_name = (event.get("teamB") or "").replace("\n", " ").strip().upper()

    stroke_w = max(2, round(3 * (POSTER_HEIGHT / 720)))
    box_radius = max(6, round(14 * (POSTER_HEIGHT / 720)))
    box_pad = max(16, round(40 * (POSTER_WIDTH / 1280)))

    tourney_logo = scale_to_fit(
        download_image(event.get("logo")),
        int(POSTER_WIDTH * 0.21),
        int(POSTER_HEIGHT * 0.24),
    )

    team_a_flag = scale_to_fit(
        download_image(event.get("teamAFlag")),
        int(POSTER_WIDTH * 0.34),
        int(POSTER_HEIGHT * 0.42),
    )
    team_b_flag = scale_to_fit(
        download_image(event.get("teamBFlag")),
        int(POSTER_WIDTH * 0.34),
        int(POSTER_HEIGHT * 0.42),
    )

    draw = ImageDraw.Draw(bg)

    if tourney_name:
        font_tourney = fit_font_to_width(
            draw, tourney_name, font_path,
            int(POSTER_HEIGHT * 0.095), int(POSTER_WIDTH * 0.94), stroke_width=stroke_w
        )
        draw_text_centered_at(draw, tourney_name, POSTER_WIDTH // 2, int(POSTER_HEIGHT * 0.025), font_tourney, stroke_width=stroke_w)

    if tourney_logo:
        lx = (POSTER_WIDTH - tourney_logo.width) // 2
        ly = int(POSTER_HEIGHT * 0.175)
        bg.paste(tourney_logo, (lx, ly), tourney_logo)

    left_center_x = int(POSTER_WIDTH * 0.24)
    right_center_x = int(POSTER_WIDTH * 0.76)
    logo_center_y = int(POSTER_HEIGHT * 0.52)

    if team_a_flag:
        ax = left_center_x - (team_a_flag.width // 2)
        ay = logo_center_y - (team_a_flag.height // 2)
        bg.paste(team_a_flag, (ax, ay), team_a_flag)

    if team_b_flag:
        bx = right_center_x - (team_b_flag.width // 2)
        by = logo_center_y - (team_b_flag.height // 2)
        bg.paste(team_b_flag, (bx, by), team_b_flag)

    font_vs = load_font(font_path, int(POSTER_HEIGHT * 0.125))
    draw_text_centered_xy(draw, "VS", POSTER_WIDTH // 2, int(POSTER_HEIGHT * 0.545), font_vs, fill="#FFD700", stroke_width=stroke_w)

    box_w = int(POSTER_WIDTH * 0.43)
    box_h = int(POSTER_HEIGHT * 0.13)
    box_center_y = int(POSTER_HEIGHT * 0.84)
    box_top = box_center_y - (box_h // 2)
    box_bottom = box_center_y + (box_h // 2)

    overlay = Image.new("RGBA", bg.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    grey_bg = (25, 25, 25, 190)

    if team_a_name:
        box_a = [left_center_x - (box_w // 2), box_top, left_center_x + (box_w // 2), box_bottom]
        overlay_draw.rounded_rectangle(box_a, radius=box_radius, fill=grey_bg)

    if team_b_name:
        box_b = [right_center_x - (box_w // 2), box_top, right_center_x + (box_w // 2), box_bottom]
        overlay_draw.rounded_rectangle(box_b, radius=box_radius, fill=grey_bg)

    bg = Image.alpha_composite(bg, overlay)
    draw = ImageDraw.Draw(bg)

    team_max_w = box_w - box_pad
    team_start_size = int(POSTER_HEIGHT * 0.105)

    if team_a_name:
        font_a = fit_font_to_width(draw, team_a_name, font_path, team_start_size, team_max_w, stroke_width=stroke_w)
        draw_text_centered_xy(draw, team_a_name, left_center_x, box_center_y, font_a, stroke_width=stroke_w)

    if team_b_name:
        font_b = fit_font_to_width(draw, team_b_name, font_path, team_start_size, team_max_w, stroke_width=stroke_w)
        draw_text_centered_xy(draw, team_b_name, right_center_x, box_center_y, font_b, stroke_width=stroke_w)

    save_compressed_png(bg, output_path, max_kb=250)


def category_priority(cat_name):
    c = (cat_name or "Other").strip().lower()
    if c == "football":
        return (0, c)
    elif c == "cricket":
        return (1, c)
    return (2, c)


def main():
    if not JSON_URL:
        raise ValueError("KSA_SERVER1 secret not found! Please check GitHub Secrets.")

    os.makedirs(POSTERS_DIR, exist_ok=True)
    bg_path = get_background_path()
    font_path = ensure_google_font()

    version_file = os.path.join(POSTERS_DIR, ".poster_version")
    current_version = ""
    if os.path.exists(version_file):
        with open(version_file, "r", encoding="utf-8") as f:
            current_version = f.read().strip()

    if current_version != TEMPLATE_VERSION:
        print("New template version detected. Rebuilding all posters...")
        for f_name in os.listdir(POSTERS_DIR):
            f_path = os.path.join(POSTERS_DIR, f_name)
            if os.path.isfile(f_path):
                os.remove(f_path)
        with open(version_file, "w", encoding="utf-8") as f:
            f.write(TEMPLATE_VERSION)

    print("Fetching JSON data...")
    resp = requests.get(JSON_URL, headers={"User-Agent": BROWSER_HEADERS["User-Agent"]}, timeout=20)
    resp.raise_for_status()
    matches = resp.json()

    active_matches = [m for m in matches if is_match_active(m)]
    active_filenames = {".poster_version"}

    for m in active_matches:
        match_id = m.get("id")
        filename = f"{match_id}.png"
        active_filenames.add(filename)
        poster_path = os.path.join(POSTERS_DIR, filename)

        if not os.path.exists(poster_path):
            create_poster(m, bg_path, font_path, poster_path)

    for existing_file in os.listdir(POSTERS_DIR):
        if existing_file not in active_filenames:
            old_path = os.path.join(POSTERS_DIR, existing_file)
            if os.path.isfile(old_path):
                os.remove(old_path)
                print(f"Old poster deleted: {old_path}")

    sorted_matches = sorted(
        active_matches,
        key=lambda m: category_priority(get_match_category(m))
    )

    m3u_lines = ["#EXTM3U"]
    for m in sorted_matches:
        streams = m.get("dashStreams") or []
        if not streams:
            continue

        match_id = m.get("id")
        match_title = (m.get("title") or "").strip()
        category = get_match_category(m)
        poster_url = f"{RAW_BASE_URL}/{match_id}.png"

        for s in streams:
            if not isinstance(s, dict):
                continue
            stream_title = (s.get("title") or "").strip()
            stream_type = (s.get("type") or "").strip().lower()
            stream_url = (s.get("url") or "").strip()
            stream_key = (s.get("key") or "").strip()

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

    print(f"Playlist updated: {PLAYLIST_FILE}")


if __name__ == "__main__":
    main()
