#!/usr/bin/env python3
# ABOUTME: Renders markdown content to an image and uploads to Samsung Frame TV.
# ABOUTME: Configured via FRAME_TV_IP and FRAME_CONTENT_FILE environment variables.

import os
import sys
import tempfile
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright
from samsungtvws import SamsungTVWS

IMAGE_WIDTH = 1920
IMAGE_HEIGHT = 1080


def get_config() -> tuple[str, Path]:
    """Read configuration from environment variables."""
    tv_ip = os.environ.get("FRAME_TV_IP")
    content_file = os.environ.get("FRAME_CONTENT_FILE")

    if not tv_ip:
        sys.exit("Error: FRAME_TV_IP environment variable not set")
    if not content_file:
        sys.exit("Error: FRAME_CONTENT_FILE environment variable not set")

    content_path = Path(content_file)
    if not content_path.exists():
        sys.exit(f"Error: Content file not found: {content_path}")

    return tv_ip, content_path


def render_to_image(content_path: Path, output_path: Path) -> None:
    """Render markdown content to image file."""
    markdown_text = content_path.read_text()
    content_html = markdown.markdown(markdown_text)

    html = f"""<!DOCTYPE html>
<html>
<head>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            width: {IMAGE_WIDTH}px;
            height: {IMAGE_HEIGHT}px;
            background: #1a1a1a;
            color: #f5f5f5;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 80px;
        }}
        .container {{
            max-width: 1400px;
        }}
        h1 {{
            font-size: 48px;
            font-weight: 300;
            margin-bottom: 32px;
            color: #e0e0e0;
            letter-spacing: -0.5px;
        }}
        h2 {{
            font-size: 36px;
            font-weight: 300;
            margin-bottom: 24px;
            color: #e0e0e0;
        }}
        h3 {{
            font-size: 28px;
            font-weight: 400;
            margin-bottom: 20px;
            color: #e0e0e0;
        }}
        p {{
            font-size: 32px;
            font-weight: 400;
            line-height: 1.6;
            margin-bottom: 24px;
        }}
        ul, ol {{
            margin-bottom: 24px;
            padding-left: 40px;
        }}
        li {{
            font-size: 32px;
            font-weight: 400;
            line-height: 1.6;
            margin-bottom: 16px;
        }}
        ul {{
            list-style: none;
        }}
        ul li {{
            position: relative;
            padding-left: 40px;
        }}
        ul li::before {{
            content: "→";
            position: absolute;
            left: 0;
            color: #888;
        }}
        ol {{
            list-style-position: inside;
            padding-left: 0;
        }}
        ol li {{
            padding-left: 8px;
        }}
        strong {{
            font-weight: 600;
        }}
        em {{
            font-style: italic;
        }}
        code {{
            font-family: "SF Mono", Monaco, "Courier New", monospace;
            background: #2a2a2a;
            padding: 2px 6px;
            border-radius: 4px;
        }}
        pre {{
            background: #2a2a2a;
            padding: 16px;
            border-radius: 8px;
            margin-bottom: 24px;
            overflow-x: auto;
        }}
        pre code {{
            background: none;
            padding: 0;
        }}
        blockquote {{
            border-left: 4px solid #888;
            padding-left: 20px;
            margin-bottom: 24px;
            color: #ccc;
        }}
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
    tv_ip, content_file = get_config()

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        image_path = Path(f.name)

    print("Rendering image...")
    render_to_image(content_file, image_path)
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
