# Themes Design

## Overview

Add a theming system to customise the visual appearance of rendered content.

## Theme Structure

Themes live in `themes/` at the repo root. A theme can be either:

- A single CSS file: `themes/default.css`
- A folder with assets: `themes/paper/theme.css` + `themes/paper/background.jpg`

When loading theme `foo`, check for `themes/foo/theme.css` first, then fall back to `themes/foo.css`.

Each theme is self-contained - complete CSS styling, no inheritance or merging.

## Asset Resolution

Relative `url()` references in CSS are converted to absolute `file://` paths at render time.

Example: `url(background.jpg)` in `themes/paper/theme.css` becomes `url(file:///path/to/repo/themes/paper/background.jpg)`.

## Theme Selection

Via `FRAME_THEME` environment variable. Defaults to `default`.

```bash
FRAME_THEME=paper uv run frame-update
```

Exit with error listing available themes if theme not found.

## Code Changes

1. `get_config()` returns theme name as third value
2. `render_to_image()` takes theme parameter
3. New function to load and process theme CSS (resolve relative URLs)
4. HTML template reduced to structure only - styling comes from theme

## Built-in Themes

1. `themes/default.css` - current dark theme extracted as-is
2. `themes/paper/theme.css` + `themes/paper/background.jpg` - light text on paper texture (image resized to 1920×1080)
