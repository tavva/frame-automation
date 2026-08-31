# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Python utility that displays markdown content on a Samsung Frame TV in Art Mode. Reads a markdown file, renders it to a styled 1920×1080 image using Playwright, and uploads via WebSocket to the TV.

## Commands

```bash
# Setup
uv sync --extra render  # omit the extra for power control commands only
uv run playwright install chromium

# Run
export FRAME_TV_IP=192.168.1.x
export FRAME_CONTENT_FILE=/path/to/content.md
export FRAME_THEME=default  # optional: default, paper, paper-bleed, split, split-bleed
uv run frame-update

# Send an existing PNG (no render extra needed)
uv run frame-image /path/to/image.png

# Power control (needs FRAME_TV_IP, optionally FRAME_TV_MAC for Wake-on-LAN)
uv run frame-art
uv run frame-off

# Test
uv run pytest
```

## Architecture

Single-module design in `src/frame_automation/main.py`:

1. **`get_config()`** - Validates environment variables, returns TV IP, content path, theme
2. **`load_theme_css(theme_name)`** - Loads theme CSS, embedding relative `url()` images as base64 data URIs
3. **`render_to_image(content_path, output_path, theme)`** - Converts markdown to HTML, applies theme CSS, renders to PNG
4. **`upload_to_tv(tv_ip, image_path)`** - Uploads image via samsungtvws WebSocket API
5. **`set_active_art(tv_ip, content_id)`** - Sets uploaded image as active artwork
6. **`delete_previous_art(tv_ip)`** - Removes the image uploaded by the previous run, tracked in `~/.frame-automation/last_content_id`
7. **`ensure_art_mode(tv_ip, mac)`** - Switches to art mode, sending Wake-on-LAN packets and retrying when a MAC is given
8. **`turn_off(tv_ip)`** - Powers the TV off by holding `KEY_POWER`
9. **`publish_image(tv_ip, image_path)`** - Uploads an image, activates it and deletes the previous one; shared by `frame-update` and `frame-image`

`publish_image()` uploads and activates the new image before deleting the
previous one, so a failure part way through never leaves the TV without
artwork.

## Themes

Themes live in `themes/` directory:

- Single CSS file: `themes/default.css`
- Folder with assets: `themes/paper/theme.css` + `themes/paper/background.jpg`

Each theme is self-contained CSS with full styling control. Relative `url()` references are resolved to the theme's directory.

## Dependencies

- **markdown** - Markdown to HTML conversion
- **Playwright** - Headless browser for HTML→PNG rendering
- **samsungtvws** - Samsung TV WebSocket API client for Art Mode

## Notes

- Python 3.13+ required
- Uses uv for package management (not pip/poetry)
- Tested on Samsung Frame TV 2022 QE32LS03TC
