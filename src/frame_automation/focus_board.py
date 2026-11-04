# ABOUTME: Builds the TV board markdown from Flow's focus file (JSONL, one item per line).
# ABOUTME: Groups unfinished items by source or top-level project and lists today's completions.

import json
import re
from datetime import date, datetime
from pathlib import Path

GENERAL_GROUP = "Misc"
DONE_HEADING = "Done today"

SOURCE_LINK = re.compile(r"\s*\(\[\[[^\]]*\|source\]\]\)")
TAG = re.compile(r"(?<!\S)#(?!\d+(?!\S))[^\s#]+")
WIKILINK = re.compile(r"\[\[([^\]|#]*)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]")


def read_focus_items(path: Path) -> list[dict]:
    """Read Flow's focus file, skipping lines that fail to parse as Flow does."""
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            items.append(item)
    return items


def clean_item_text(text: str) -> str:
    """Strip vault markup that means nothing on the TV, keeping markdown."""
    text = SOURCE_LINK.sub("", text)
    text = TAG.sub("", text)
    text = WIKILINK.sub(
        lambda match: match.group(2) or Path(match.group(1)).name, text
    )
    return " ".join(text.split())


class Vault:
    """Resolves files and wikilinks in an Obsidian vault the way Obsidian does in practice."""

    def __init__(self, root: Path):
        self.root = root
        self._files_by_name = None

    def resolve_link(self, target: str) -> Path | None:
        """Resolve a link target by vault-relative path, then by unique file name."""
        if not target.endswith(".md"):
            target += ".md"
        exact = self.root / target
        if exact.is_file():
            return exact
        matches = self._files_named(Path(target).name)
        return matches[0] if len(matches) == 1 else None

    def _files_named(self, name: str) -> list[Path]:
        if self._files_by_name is None:
            self._files_by_name = {}
            for path in self.root.rglob("*.md"):
                if ".obsidian" in path.relative_to(self.root).parts:
                    continue
                self._files_by_name.setdefault(path.name, []).append(path)
        return self._files_by_name.get(name, [])

    def parent_project(self, project: Path) -> Path | None:
        """Return the file a project's `parent-project` link points to, if it resolves."""
        link = read_frontmatter(project).get("parent-project")
        if not isinstance(link, str):
            return None
        match = WIKILINK.fullmatch(link.strip())
        if not match or not match.group(1).strip():
            return None
        return self.resolve_link(match.group(1).strip())

    def top_level_project(self, project: Path) -> Path:
        """Follow `parent-project` links until a project has no parent or a link fails."""
        seen = {project.resolve()}
        while (parent := self.parent_project(project)) is not None:
            if parent.resolve() in seen:
                break
            seen.add(parent.resolve())
            project = parent
        return project


def read_frontmatter(path: Path) -> dict:
    """Parse a note's YAML frontmatter, returning {} when it is missing or invalid."""
    import yaml

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    match = re.match(r"---\n(.*?)\n---(?:\n|$)", text, re.DOTALL)
    if not match:
        return {}
    try:
        frontmatter = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return {}
    return frontmatter if isinstance(frontmatter, dict) else {}


def group_name(item: dict, vault: Vault) -> str:
    """Name the board group an unfinished item belongs to."""
    if "external" in item:
        return item["external"]["sourceLabel"]
    if item.get("isGeneral"):
        return GENERAL_GROUP
    project = vault.root / item["file"]
    if not project.is_file():
        return GENERAL_GROUP
    return vault.top_level_project(project).stem


def completed_on(item: dict, day: date) -> bool:
    completed_at = item.get("completedAt")
    return (
        completed_at is not None
        and datetime.fromtimestamp(completed_at / 1000).date() == day
    )


def build_board_markdown(
    items: list[dict], vault_root: Path, today: date, title: str, message: str | None
) -> str:
    """Build the board: grouped unfinished items, then today's completions."""
    vault = Vault(vault_root)

    unfinished = [item for item in items if item.get("completedAt") is None]
    ordered = [item for item in unfinished if item.get("isPinned")] + [
        item for item in unfinished if not item.get("isPinned")
    ]
    groups: dict[str, list[str]] = {}
    for item in ordered:
        groups.setdefault(group_name(item, vault), []).append(
            clean_item_text(item["text"])
        )
    done = [clean_item_text(item["text"]) for item in items if completed_on(item, today)]

    sections = [f"# {title}\n## {today:%B} {today.day} {today.year}\n"]
    if message:
        sections.append(f"**{message}**\n")
    for heading, texts in groups.items():
        sections.append(f"### {heading}\n" + "".join(f"- {text}\n" for text in texts))
    if done:
        sections.append(f"#### {DONE_HEADING}\n" + "".join(f"- {text}\n" for text in done))
    return "\n".join(sections)
