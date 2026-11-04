# Focus Board Design

## Overview

Build the TV board straight from Flow's Focus list, so the hand-kept
`Display goals.md` note can be retired. A new focus mode reads Flow's focus
file, turns it into board markdown, and renders it the same way as today. The
existing mode, which renders a markdown file as written, stays as it is.

Flow writes nothing for the TV. frame-automation only reads Flow's files,
relying on the focus file format documented in Flow's README (see Flow's
`docs/plans/2026-11-04-focus-api-design.md`).

## Configuration

| Variable              | Meaning                                                              |
| --------------------- | -------------------------------------------------------------------- |
| `FRAME_FOCUS_FILE`    | Path to Flow's focus file, e.g. `<vault>/flow-focus-data/focus.md`   |
| `FRAME_VAULT_ROOT`    | Vault root, for resolving item files and `parent-project` links      |
| `FRAME_BOARD_TITLE`   | Board `h1`, default `Goals`                                          |
| `FRAME_BOARD_MESSAGE` | Optional line under the date, shown in bold (e.g. `No new things!`) |

`get_config()` picks the mode: `FRAME_FOCUS_FILE` set means focus mode, which
needs `FRAME_VAULT_ROOT`. Setting both `FRAME_FOCUS_FILE` and
`FRAME_CONTENT_FILE` is an error. The launchd agent's `.envrc` switches to the
focus variables; the plist doesn't change.

## Building the board

A new module, `src/frame_automation/focus_board.py`, holds a pure function:

```python
def build_board_markdown(
    items: list[dict], vault_root: Path, today: date, title: str, message: str | None
) -> str
```

and `read_focus_items(path)`, which parses JSONL and skips lines that fail to
parse, as Flow does.

Output, matching what the clean theme already expects:

```markdown
# Goals
## November 4 2026

**No new things!**

### Acme
- Write up and share onboarding guide
### Misc
- Buy bubble bath

#### Done today
- Draft section 2 of the onboarding guide
```

### Groups

- An item with `external` goes under `external.sourceLabel`.
- An item with `isGeneral: true` goes under `Misc`.
- Any other item goes under its top-level project. Start from the item's
  `file`, read its frontmatter, and follow `parent-project: "[[X]]"` until a
  project has no parent. The heading is that project's file name without
  `.md`.
- Wikilinks resolve the way Obsidian's do in practice: an exact
  vault-relative path first, then a unique file name match anywhere in the
  vault (ignoring `.obsidian/`). `[[X|alias]]` and `[[X#heading]]` use `X`.
- A missing file, an unresolved link or a loop (a project seen twice) stops
  the walk at the last project found. If the item's own file is missing, the
  item goes under `Misc`. The board still renders, and nothing is raised.

Frontmatter is parsed with PyYAML, which becomes a dependency of the `render`
extra.

### Order

Unfinished items only. Pinned items come first, then the rest, each in file
order (Flow's Focus order). Groups appear in the order of their first item, so
a group holding a pinned item comes first. `Misc` sorts the same way as any
other group.

### Done today

Items whose `completedAt` falls on today's local date are listed under
`#### Done today`, in file order, with no grouping. Older completed items are
left off. The heading is omitted when nothing was done today.

### Item text

Flow's `text` can carry vault markup that means nothing on the TV, and the
board strips it:

- a trailing source link like ` ([[2026-10-26T11-01-47|source]])`
- `#tags`, e.g. `#sphere/work` or `#context/calls`
- other wikilinks become their alias or target name

Markdown links and emphasis are kept.

## Watching

`ContentWatcher` now hashes the file's bytes. It changes to hash content
returned by a `read_content()` callable:

- markdown mode: the file's bytes, as now
- focus mode: the board markdown built from the focus file and today's date

Building the board every second covers every reason the board can change: a
Focus edit, a project being moved under a different parent, and the date
changing at midnight. The midnight rollover needs no timer, because the date
is part of the built markdown. The watcher keeps its current debounce (10s),
its retry (5 minutes) and its saved digest. Publishing renders the markdown it
just built, so what reaches the TV is exactly what was hashed.

`render_to_image` takes markdown text instead of a path, so both modes share
it. `frame-update` in focus mode builds and publishes once.

## Clean theme

```css
h4 {
    margin-top: 72px;
    padding-left: 118px;
    font-family: 'Space Mono', monospace;
    font-size: 26px;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: #7d8c7e;
}

h4 ~ ul li {
    font-size: 30px;
    color: #5f6e61;
    text-decoration: line-through;
}
```

`h4` joins the `zoom: var(--fit-scale)` rule alongside `h3, ul, ol, p`, so the
fit-to-frame scaling counts it and shrinks it with everything else. `h4` uses
no `counter-increment`, so the `###` numbering is unaffected. The lists after
it keep the em-dash bullets. Whether the line-through reads well on the TV is
a judgement to make on the first real render.

The other themes don't style `h4` specially; they show it as their default
heading.

## Errors

- A missing focus file at startup exits with an error, as a missing content
  file does now. A file that disappears while watching is skipped, as now.
- An unreadable vault project file falls back as described under Groups.
- An empty Focus list renders a board with only the header and message.

## Testing

Tests use fixture vaults under `tests/fixtures/` (real focus files and
project notes copied from the shapes Flow writes), not mocks:

- grouping: external by `sourceLabel`, general under `Misc`, project items
  under their top-level project through a two-level `parent-project` chain,
  aliased and heading links, a path link, an unresolved link, a loop
- order: pinned first, groups by first item, file order within groups
- done today: today's completions listed, yesterday's left off, heading
  omitted when empty, local-time midnight boundary
- rollover: the same items built for two dates give different markdown and
  different digests
- text cleanup: source links, tags and wikilinks stripped
- watcher: a focus-mode watcher publishes after a focus file edit and after
  the date changes, using an injected clock and date
- config: focus mode chosen, missing vault root, both modes set
- render: a page with a `####` section renders, the `h4` doesn't take a goal
  number (the next `###` keeps its count), and fit-to-frame still shrinks an
  overflowing board

## Docs

README and CLAUDE.md gain the focus mode, its variables, and the `h4`
section in the clean theme.
