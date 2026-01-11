# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Python utility that displays markdown content on a Samsung Frame TV in Art Mode. Reads a markdown file, renders it to a styled 1920×1080 image using Playwright, and uploads via WebSocket to the TV.

## Commands

```bash
# Setup
uv sync
uv run playwright install chromium

# Run
export FRAME_TV_IP=192.168.1.x
export FRAME_CONTENT_FILE=/path/to/content.md
uv run frame-update
```

## Architecture

Single-module design in `src/frame_automation/main.py`:

1. **`get_config()`** - Validates `FRAME_TV_IP` and `FRAME_CONTENT_FILE` environment variables
2. **`render_to_image(content_path, output_path)`** - Converts markdown to HTML, renders to PNG via Playwright headless Chromium
3. **`upload_to_tv(tv_ip, image_path)`** - Uploads image via samsungtvws WebSocket API
4. **`set_active_art(tv_ip, content_id)`** - Sets uploaded image as active artwork
5. **`main()`** - Orchestrates workflow, handles cleanup

## Dependencies

- **markdown** - Markdown to HTML conversion
- **Playwright** - Headless browser for HTML→PNG rendering
- **samsungtvws** - Samsung TV WebSocket API client for Art Mode

## Notes

- Python 3.13+ required
- Uses uv for package management (not pip/poetry)
- Tested on Samsung Frame TV 2022 QE32LS03TC
