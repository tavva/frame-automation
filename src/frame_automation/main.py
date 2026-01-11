#!/usr/bin/env python3
# ABOUTME: Renders markdown content to an image and uploads to Samsung Frame TV.
# ABOUTME: Configured via FRAME_TV_IP, FRAME_CONTENT_FILE, and FRAME_THEME environment variables.

import base64
import mimetypes
import os
import re
import sys
import tempfile
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright
from samsungtvws import SamsungTVWS

IMAGE_WIDTH = 1920
IMAGE_HEIGHT = 1080
STATE_DIR = Path.home() / ".frame-automation"
STATE_FILE = "last_content_id"


def get_state_file_path() -> Path:
    """Return path to the state file storing the last uploaded content ID."""
    return STATE_DIR / STATE_FILE


def read_last_content_id() -> str | None:
    """Read the last uploaded content ID from state file, or None if not found."""
    state_file = get_state_file_path()
    if not state_file.exists():
        return None
    return state_file.read_text().strip()


def write_last_content_id(content_id: str) -> None:
    """Write the content ID to state file for future cleanup."""
    state_file = get_state_file_path()
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(content_id)


def get_repo_root() -> Path:
    """Get the repository root path."""
    return Path(__file__).parent.parent.parent


def get_theme_dirs() -> list[Path]:
    """Get theme directories in priority order (user-themes first)."""
    root = get_repo_root()
    return [root / "user-themes", root / "themes"]


def get_available_themes() -> list[str]:
    """List available theme names from all theme directories."""
    themes = set()
    for themes_dir in get_theme_dirs():
        if not themes_dir.exists():
            continue
        for item in themes_dir.iterdir():
            if item.is_file() and item.suffix == ".css":
                themes.add(item.stem)
            elif item.is_dir() and (item / "theme.css").exists():
                themes.add(item.name)
    return sorted(themes)


def get_config() -> tuple[str, Path, str]:
    """Read configuration from environment variables."""
    tv_ip = os.environ.get("FRAME_TV_IP")
    content_file = os.environ.get("FRAME_CONTENT_FILE")
    theme = os.environ.get("FRAME_THEME", "default")

    if not tv_ip:
        sys.exit("Error: FRAME_TV_IP environment variable not set")
    if not content_file:
        sys.exit("Error: FRAME_CONTENT_FILE environment variable not set")

    available = get_available_themes()
    if theme not in available:
        sys.exit(f"Error: Unknown theme '{theme}'. Available: {', '.join(available)}")

    content_path = Path(content_file)
    if not content_path.exists():
        sys.exit(f"Error: Content file not found: {content_path}")

    return tv_ip, content_path, theme


def find_theme_path(theme_name: str) -> tuple[Path, Path]:
    """Find theme CSS path and base directory, checking user-themes first."""
    for themes_dir in get_theme_dirs():
        if not themes_dir.exists():
            continue
        # Check for folder theme first, then single file
        theme_folder = themes_dir / theme_name
        if theme_folder.is_dir() and (theme_folder / "theme.css").exists():
            return theme_folder / "theme.css", theme_folder
        css_file = themes_dir / f"{theme_name}.css"
        if css_file.exists():
            return css_file, themes_dir
    raise FileNotFoundError(f"Theme not found: {theme_name}")


def load_theme_css(theme_name: str) -> str:
    """Load and process theme CSS, embedding local images as base64 data URIs."""
    css_path, base_dir = find_theme_path(theme_name)
    css = css_path.read_text()

    # Replace relative url() references with base64 data URIs for local images
    def resolve_url(match: re.Match) -> str:
        url = match.group(1)
        # Skip absolute URLs, data URIs, and external URLs
        if url.startswith(("http://", "https://", "data:", "file://", "/")):
            return match.group(0)
        # Resolve relative path and embed as base64
        abs_path = (base_dir / url).resolve()
        if abs_path.exists():
            mime_type, _ = mimetypes.guess_type(str(abs_path))
            if mime_type and mime_type.startswith("image/"):
                image_data = abs_path.read_bytes()
                b64 = base64.b64encode(image_data).decode("utf-8")
                return f"url(data:{mime_type};base64,{b64})"
        return match.group(0)

    css = re.sub(r"url\(['\"]?([^)'\"\s]+)['\"]?\)", resolve_url, css)

    return css


def render_to_image(content_path: Path, output_path: Path, theme: str) -> None:
    """Render markdown content to image file."""
    markdown_text = content_path.read_text()
    content_html = markdown.markdown(markdown_text)
    theme_css = load_theme_css(theme)

    html = f"""<!DOCTYPE html>
<html>
<head>
    <style>
        {theme_css}
    </style>
</head>
<body>
    <div class="container">
        {content_html}
    </div>
</body>
</html>"""

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": IMAGE_WIDTH, "height": IMAGE_HEIGHT})
        page.set_content(html)
        page.screenshot(path=str(output_path), type="png")
        browser.close()


def upload_to_tv(tv_ip: str, image_path: Path) -> str:
    """Upload image to TV and return content_id."""
    tv = SamsungTVWS(tv_ip)
    art = tv.art()

    with open(image_path, "rb") as f:
        image_data = f.read()

    content_id = art.upload(image_data, file_type="PNG", matte="none")
    return content_id


def set_active_art(tv_ip: str, content_id: str) -> None:
    """Set the uploaded image as the active artwork."""
    tv = SamsungTVWS(tv_ip)
    art = tv.art()
    art.select_image(content_id)


def delete_previous_art(tv_ip: str) -> None:
    """Delete the previously uploaded image from the TV if one exists."""
    previous_id = read_last_content_id()
    if not previous_id:
        return

    tv = SamsungTVWS(tv_ip)
    art = tv.art()
    try:
        art.delete(previous_id)
        print(f"  Deleted previous image: {previous_id}")
    except Exception as e:
        # Image may have been manually deleted - not an error
        print(f"  Could not delete previous image {previous_id}: {e}")


def main():
    tv_ip, content_file, theme = get_config()

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        image_path = Path(f.name)

    print(f"Rendering image (theme: {theme})...")
    render_to_image(content_file, image_path, theme)
    print(f"  Saved to {image_path}")

    print("Cleaning up previous image...")
    delete_previous_art(tv_ip)

    print(f"Uploading to TV ({tv_ip})...")
    content_id = upload_to_tv(tv_ip, image_path)
    print(f"  Content ID: {content_id}")

    print("Setting as active artwork...")
    set_active_art(tv_ip, content_id)

    write_last_content_id(content_id)
    print("Done!")

    # Clean up temp file
    image_path.unlink()


if __name__ == "__main__":
    main()
