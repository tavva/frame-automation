# ABOUTME: Builds the TV board markdown from Flow's focus file (JSONL, one item per line).
# ABOUTME: Groups unfinished items by source or top-level project and lists today's completions.

import json
import re
import sys
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

GENERAL_GROUP = "Misc"
DONE_HEADING = "Done today"

SOURCE_LINK = re.compile(r"\s*\(\[\[[^\]]*\|source\]\]\)")
TAG = re.compile(r"(?<!\S)#(?!\d+(?!\S))[^\s#]+")
WIKILINK = re.compile(r"\[\[([^\]|#]*)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]")


def read_focus_items(path: Path) -> tuple[list[dict], list[str]]:
    """Read Flow's focus file, returning its items and a note on each line skipped.

    Lines that fail to parse or lack the fields the board needs are skipped, as
    Flow skips lines it can't parse. Blank lines are skipped without a note.
    """
    items = []
    problems = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            problems.append(f"line {number}: not valid JSON")
            continue
        problem = find_item_problem(item)
        if problem:
            problems.append(f"line {number}: {problem}")
            continue
        items.append(item)
    return items, problems


def find_item_problem(item) -> str | None:
    """Say what stops a parsed line from being shown, or None if it can be."""
    if not isinstance(item, dict):
        return "not a JSON object"
    if not isinstance(item.get("text"), str):
        return "no text"
    completed_at = item.get("completedAt")
    if completed_at is not None and (
        isinstance(completed_at, bool) or not isinstance(completed_at, (int, float))
    ):
        return "completedAt is not a number"
    if "external" in item:
        external = item["external"]
        if not isinstance(external, dict):
            return "external is not an object"
        if not isinstance(external.get("sourceLabel"), str) or not external["sourceLabel"].strip():
            return "external item has no sourceLabel"
    elif not isinstance(item.get("file"), str):
        return "vault item has no file"
    return None


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


def print_warning(message: str) -> None:
    print(f"Warning: {message}", file=sys.stderr, flush=True)


class FocusBoard:
    """Builds the board from Flow's focus file, warning once about each skipped line.

    The watcher rebuilds the board every second, so a skipped line is reported
    when it first appears rather than on every build.
    """

    def __init__(
        self,
        focus_path: Path,
        vault_root: Path,
        title: str,
        message: str | None,
        *,
        today: Callable[[], date] = date.today,
        warn: Callable[[str], None] = print_warning,
    ):
        self.focus_path = focus_path
        self.vault_root = vault_root
        self.title = title
        self.message = message
        self.today = today
        self.warn = warn
        self.reported_problems = set()

    def build(self) -> str:
        items, problems = read_focus_items(self.focus_path)
        for problem in problems:
            if problem not in self.reported_problems:
                self.warn(f"Skipped {self.focus_path} {problem}")
        self.reported_problems = set(problems)
        return build_board_markdown(
            items, self.vault_root, self.today(), self.title, self.message
        )
