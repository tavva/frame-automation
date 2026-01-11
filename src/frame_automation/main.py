#!/usr/bin/env python3
# ABOUTME: Renders markdown content to an image and uploads to Samsung Frame TV.
# ABOUTME: Configured via FRAME_TV_IP, FRAME_CONTENT_FILE, and FRAME_THEME environment variables.

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


def get_themes_dir() -> Path:
    """Get the themes directory path."""
    return Path(__file__).parent.parent.parent / "themes"


def get_available_themes() -> list[str]:
    """List available theme names."""
    themes_dir = get_themes_dir()
    if not themes_dir.exists():
        return []

    themes = []
    for item in themes_dir.iterdir():
        if item.is_file() and item.suffix == ".css":
            themes.append(item.stem)
        elif item.is_dir() and (item / "theme.css").exists():
            themes.append(item.name)
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


def load_theme_css(theme_name: str) -> str:
    """Load and process theme CSS, resolving relative URLs to file:// paths."""
    themes_dir = get_themes_dir()

    # Check for folder theme first, then single file
    theme_folder = themes_dir / theme_name
    if theme_folder.is_dir():
        css_path = theme_folder / "theme.css"
        base_dir = theme_folder
    else:
        css_path = themes_dir / f"{theme_name}.css"
        base_dir = themes_dir

    css = css_path.read_text()

    # Replace relative url() references with absolute file:// paths
    def resolve_url(match: re.Match) -> str:
        url = match.group(1)
        # Skip absolute URLs, data URIs, and external URLs
        if url.startswith(("http://", "https://", "data:", "file://", "/")):
            return match.group(0)
        # Resolve relative path
        abs_path = (base_dir / url).resolve()
        return f"url(file://{abs_path})"

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


def main():
    tv_ip, content_file, theme = get_config()

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        image_path = Path(f.name)

    print(f"Rendering image (theme: {theme})...")
    render_to_image(content_file, image_path, theme)
    print(f"  Saved to {image_path}")

    print(f"Uploading to TV ({tv_ip})...")
    content_id = upload_to_tv(tv_ip, image_path)
    print(f"  Content ID: {content_id}")

    print("Setting as active artwork...")
    set_active_art(tv_ip, content_id)

    print("Done!")

    # Clean up temp file
    image_path.unlink()


if __name__ == "__main__":
    main()
