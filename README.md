# frame-automation

Display markdown content on a Samsung Frame TV in Art Mode.

Reads a markdown file, renders it to a styled 1920×1080 image (I have a 32" Frame), and uploads it via [samsungtvws](https://github.com/xchwarze/samsung-tv-ws-api).

## Requirements

- Samsung Frame TV (not all versions will work, tested on 2022 QE32LS03TC)
- Python 3.13+

## Setup

```bash
git clone git@github.com:tavva/frame-automation.git
cd frame-automation
uv sync
uv run playwright install chromium
```

## Usage

```bash
export FRAME_TV_IP=192.168.1.x
export FRAME_CONTENT_FILE=/path/to/content.md

uv run frame-update
```

The content file is standard markdown:

```markdown
# This Week

- First item
- Second item
- Third item
```

## License

MIT
