#!/usr/bin/env python3
# ABOUTME: Renders weekly goals to an image and uploads to Samsung Frame TV.
# ABOUTME: Configured via FRAME_TV_IP and FRAME_GOALS_FILE environment variables.

import os
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright
from samsungtvws import SamsungTVWS

IMAGE_WIDTH = 1920
IMAGE_HEIGHT = 1080


def get_config() -> tuple[str, Path]:
    """Read configuration from environment variables."""
    tv_ip = os.environ.get("FRAME_TV_IP")
    goals_file = os.environ.get("FRAME_GOALS_FILE")

    if not tv_ip:
        sys.exit("Error: FRAME_TV_IP environment variable not set")
    if not goals_file:
        sys.exit("Error: FRAME_GOALS_FILE environment variable not set")

    goals_path = Path(goals_file)
    if not goals_path.exists():
        sys.exit(f"Error: Goals file not found: {goals_path}")

    return tv_ip, goals_path


def read_goals(path: Path) -> list[str]:
    """Read goals from markdown file, returning list of goal strings."""
    text = path.read_text()
    goals = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if line.startswith("- "):
            goals.append(line[2:])
        elif line.startswith("* "):
            goals.append(line[2:])
        elif line:
            goals.append(line)
    return goals


def render_goals_to_image(goals: list[str], output_path: Path) -> None:
    """Render goals as HTML and screenshot to image file."""
    goals_html = "\n".join(f"<li>{goal}</li>" for goal in goals)

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
            margin-bottom: 48px;
            color: #e0e0e0;
            letter-spacing: -0.5px;
        }}
        ul {{
            list-style: none;
        }}
        li {{
            font-size: 32px;
            font-weight: 400;
            line-height: 1.6;
            margin-bottom: 24px;
            padding-left: 40px;
            position: relative;
        }}
        li::before {{
            content: "→";
            position: absolute;
            left: 0;
            color: #888;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>This Week</h1>
        <ul>
            {goals_html}
        </ul>
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
    tv_ip, goals_file = get_config()

    print("Reading goals...")
    goals = read_goals(goals_file)
    print(f"  Found {len(goals)} goals")

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        image_path = Path(f.name)

    print("Rendering image...")
    render_goals_to_image(goals, image_path)
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
