#!/usr/bin/env python3
# ABOUTME: Renders weekly goals to an image and uploads to Samsung Frame TV.
# ABOUTME: Run with: uv run python update_frame.py

import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright
from samsungtvws import SamsungTVWS

TV_IP = "TV_IP_HERE"
GOALS_FILE = Path.home() / "path/to/goals.md"
IMAGE_WIDTH = 1920
IMAGE_HEIGHT = 1080


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


def upload_to_tv(image_path: Path) -> str:
    """Upload image to TV and return content_id."""
    tv = SamsungTVWS(TV_IP)
    art = tv.art()

    with open(image_path, "rb") as f:
        image_data = f.read()

    content_id = art.upload(image_data, file_type="PNG", matte="none")
    return content_id


def set_active_art(content_id: str) -> None:
    """Set the uploaded image as the active artwork."""
    tv = SamsungTVWS(TV_IP)
    art = tv.art()
    art.select_image(content_id)


def main():
    print("Reading goals...")
    goals = read_goals(GOALS_FILE)
    print(f"  Found {len(goals)} goals")

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        image_path = Path(f.name)

    print("Rendering image...")
    render_goals_to_image(goals, image_path)
    print(f"  Saved to {image_path}")

    print("Uploading to TV...")
    content_id = upload_to_tv(image_path)
    print(f"  Content ID: {content_id}")

    print("Setting as active artwork...")
    set_active_art(content_id)

    print("Done!")

    # Clean up temp file
    image_path.unlink()


if __name__ == "__main__":
    main()
