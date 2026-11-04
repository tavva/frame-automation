# frame-automation

Display markdown content on a Samsung Frame TV in Art Mode. Note that I've only tested this on an old Frame, I believe this won't work with newer models.

Reads a markdown file, or builds a board from the Focus list of [Flow](https://github.com/tavva/flow) (an Obsidian GTD plugin), renders it to a styled 1920×1080 image (I have a 32" Frame), and uploads it via [samsungtvws](https://github.com/xchwarze/samsung-tv-ws-api).

<p align="center">
  <img src="docs/assets/demo-screenshot.jpg" alt="Rendered output" width="600">
</p>

<p align="center">
  <img src="docs/assets/demo-frame.jpg" alt="On the Frame TV" width="600">
</p>

## Requirements

- Samsung Frame TV (not all versions will work, tested on 2022 QE32LS03TC)
- Python 3.13+

## Setup

```bash
git clone git@github.com:tavva/frame-automation.git
cd frame-automation
uv sync --extra render
uv run playwright install chromium
```

The `render` extra pulls in markdown, Playwright and PyYAML. Without it only
`frame-image` and the power control commands work; `uv sync` on its own is
enough for those.

## Usage

```bash
export FRAME_TV_IP=192.168.1.x
export FRAME_CONTENT_FILE=/path/to/content.md
export FRAME_THEME=clean  # optional, see below

uv run frame-update
```

To keep watching the configured file, run:

```bash
uv run frame-watch
```

`frame-watch` checks the content once per second and publishes it after
changes have stopped for 10 seconds. It records the last successful content digest in
`~/.frame-automation/last_content_sha256`, avoids duplicate uploads after a
restart, and retries failed updates after five minutes. A run of failures
is logged in full once, then only when the error changes, and once more when
an update gets through.

This repository includes
`launchd/net.ben-phillips.frame-goals-watch.plist`, a per-user macOS
LaunchAgent that runs `frame-watch` through `direnv exec`, so it takes its
settings from the repository's `.envrc` (which loads `.env` first). The
`.envrc` decides what it shows: `FRAME_CONTENT_FILE` for a markdown file such
as `/Users/ben/Documents/Main/Display goals.md`, or the focus variables below.

### Building the board from Flow's Focus list

Instead of a markdown file, the board can be built from Flow's focus file:

```bash
export FRAME_TV_IP=192.168.1.x
export FRAME_FOCUS_FILE=/path/to/vault/flow-focus-data/focus.md
export FRAME_VAULT_ROOT=/path/to/vault
export FRAME_BOARD_TITLE=Goals             # optional, the default
export FRAME_BOARD_MESSAGE="No new things!" # optional, shown in bold under the date

uv run frame-update   # or frame-watch
```

Set `FRAME_FOCUS_FILE` or `FRAME_CONTENT_FILE`, not both. frame-automation only
reads Flow's files; it never writes to them.

To switch the LaunchAgent from `Display goals.md` to the Focus board, replace
the `FRAME_CONTENT_FILE` line in `.envrc` with:

```bash
export FRAME_FOCUS_FILE="${FRAME_FOCUS_FILE:-$HOME/Documents/Main/flow-focus-data/focus.md}"
export FRAME_VAULT_ROOT="${FRAME_VAULT_ROOT:-$HOME/Documents/Main}"
export FRAME_BOARD_MESSAGE="${FRAME_BOARD_MESSAGE:-No new things!}"
```

Make sure `.env` doesn't set `FRAME_CONTENT_FILE` either, or `frame-watch`
exits with "not both". Then run `direnv allow` in the repository and restart
the agent:

```bash
launchctl kickstart -k gui/$(id -u)/net.ben-phillips.frame-goals-watch
```

To go back, restore the `FRAME_CONTENT_FILE` line and remove the three focus
lines.

The board shows today's date and the unfinished Focus items, pinned ones
first, grouped under a `###` heading each:

- items from other plugins under their source label (e.g. `Acme`)
- general next actions under `Misc`
- project actions under their top-level project, found by following each
  project's `parent-project` link up to a project with no parent. The heading
  is that project's file name, as Flow shows it.

Items completed today follow under a `#### Done today` heading. Source links
(`([[…|source]])`), `#tags`, embeds (`![[…]]`) and wikilinks are stripped from
item text, so the board shows plain wording; markdown links and emphasis are
kept. Items with no text left are left off.

Links resolve as Obsidian resolves them: by vault-relative path, then by
unique file name, ignoring case and skipping dot-folders such as `.obsidian`
and `.trash`.

`frame-watch` rebuilds the board every second, so it updates after a Focus
change, after a project moves under a different parent, and at midnight when
the date changes. A focus file line that can't be shown (bad JSON, or missing
the fields the board needs) is skipped with a warning on stderr. A file that
is briefly empty or half-written while syncing doesn't reach the TV, because
changes only publish once they've held for 10 seconds.

### Sending an existing image

```bash
export FRAME_TV_IP=192.168.1.x

uv run frame-image /path/to/image.png
```

Uploads a PNG as-is, skipping the markdown render, so it needs no `render`
extra. The image should be 1920x1080. It replaces the previously uploaded
image just as `frame-update` does.

### Power control

```bash
export FRAME_TV_IP=192.168.1.x
export FRAME_TV_MAC=aa:bb:cc:dd:ee:ff  # optional, enables Wake-on-LAN

uv run frame-art  # switch to art mode, waking the TV first if MAC is set
uv run frame-off  # turn the TV off
```

## Themes

Themes live in the `themes/` directory. A theme is either:

- A single CSS file: `themes/clean.css`
- A folder with assets: `themes/paper/theme.css` + `themes/paper/background.jpg`

Built-in themes:

- **clean** - sage background, oversized type, numbered items (the default)
- **dark** - dark background, light text
- **paper** - paper texture with shadow border
- **paper-bleed** - paper texture, full screen (no border)
- **split** - content left, photo right, with shadow border
- **split-bleed** - content left, photo right, full screen

The split themes display a photo on the right side. Place your photo at `themes/split/user-provided/photo.jpg`.

The **clean** theme numbers each `###` heading `01`, `02`, ... and lays its
list items out as sub-items. Put the date in an `h2` to have it sit at the top
right, opposite the title:

```markdown
# Goals
## August 31 2026

### First goal
- A sub-goal
```

A single `# Goals - August 31 2026` also works; the whole line then runs along
the left of the rule.

An `h4` starts a smaller, unnumbered section; the list straight after it is
struck through. The Flow board uses it for `#### Done today`; the next `###` keeps
its number.

Goals shrink to fit the frame as you add more of them, down to a quarter of
their designed size. The header and the rules stay put.

To create a custom theme, add a CSS file or folder to `themes/`. The CSS has full control over styling. Use `url(filename.jpg)` for assets relative to the theme folder.

## Content

The content file is standard markdown:

```markdown
# This Week

- First item
- Second item
- Third item
```

## License

MIT
