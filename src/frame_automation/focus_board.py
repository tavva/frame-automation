# ABOUTME: Builds the TV board markdown from Flow's focus file (JSONL, one item per line).
# ABOUTME: Groups unfinished items by source or top-level project, with subgroups, and lists today's completions.

import json
import math
import re
import sys
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

GENERAL_GROUP = "Misc"
DONE_HEADING = "Done today"

SOURCE_LINK = re.compile(r"\s*\(\[\[[^\]]*\|source\]\]\)")
EMBED = re.compile(r"!\[\[[^\]]*\]\]")
# A tag and the space before it; Obsidian tags are letters, digits, _, - and /
TAG = re.compile(r"\s*(?<!\S)#([\w/-]+)")
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
    if completed_at is not None:
        if isinstance(completed_at, bool) or not isinstance(completed_at, (int, float)):
            return "completedAt is not a number"
        if not math.isfinite(completed_at):
            return "completedAt is not a finite number"
        try:
            datetime.fromtimestamp(completed_at / 1000)
        except (OverflowError, OSError, ValueError):
            return "completedAt is out of range"
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
    text = EMBED.sub("", text)
    # Obsidian doesn't treat an all-digit word like #42 as a tag
    text = TAG.sub(
        lambda match: match.group(0) if match.group(1).isdigit() else "", text
    )
    text = WIKILINK.sub(
        lambda match: match.group(2) or link_name(match.group(1)), text
    )
    return " ".join(text.split())


def link_name(target: str) -> str:
    """The name a link to `target` shows: its file name without `.md`."""
    name = Path(target.strip()).name
    return name[:-3] if name.lower().endswith(".md") else name


class Vault:
    """Resolves files and wikilinks in an Obsidian vault the way Obsidian does in practice.

    Links match case-insensitively, by vault-relative path and then by unique
    file name. Dot-folders such as `.obsidian` and `.trash` are not searched.
    The file index is kept between builds and rescanned at most once per build,
    when a lookup misses or finds a file that has gone.
    """

    def __init__(self, root: Path):
        self.root = root
        self.scans = 0
        self._files_by_path = {}
        self._files_by_name = {}
        self._may_rescan = True

    def allow_rescan(self) -> None:
        """Let the next missed lookup rescan the vault; called once per build."""
        self._may_rescan = True

    def resolve_link(self, target: str) -> Path | None:
        """Resolve a link target to a file, or None if it is missing or ambiguous."""
        target = target.strip()
        if not target.lower().endswith(".md"):
            target += ".md"
        found = self._lookup(target)
        if (found is None or not found.is_file()) and self._may_rescan:
            self._scan()
            found = self._lookup(target)
        return found

    def _lookup(self, target: str) -> Path | None:
        exact = self._files_by_path.get(target.lower())
        if exact is not None:
            return exact
        matches = self._files_by_name.get(Path(target).name.lower(), [])
        return matches[0] if len(matches) == 1 else None

    def _scan(self) -> None:
        self.scans += 1
        self._may_rescan = False
        self._files_by_path = {}
        self._files_by_name = {}
        for path in self.root.rglob("*.md"):
            relative = path.relative_to(self.root)
            if any(part.startswith(".") for part in relative.parts):
                continue
            self._files_by_path[relative.as_posix().lower()] = path
            self._files_by_name.setdefault(path.name.lower(), []).append(path)

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
        """Follow `parent-project` links until a project has no parent or a link fails.

        Projects whose links form a loop all share one top: the loop's project
        whose vault-relative path sorts first, wherever the walk joined it.
        """
        chain = [project.resolve()]
        while (parent := self.parent_project(project)) is not None:
            if parent.resolve() in chain:
                loop = chain[chain.index(parent.resolve()):]
                return min(loop, key=self._sort_key)
            chain.append(parent.resolve())
            project = parent
        return project

    def _sort_key(self, path: Path) -> str:
        try:
            return path.relative_to(self.root.resolve()).as_posix().lower()
        except ValueError:
            return path.as_posix().lower()


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


def board_place(item: dict, vault: Vault) -> tuple[str, str | None]:
    """Name the group and subgroup an unfinished item goes under.

    External items group by source and subgroup by their project, when they
    have one. Vault items group by top-level project and subgroup by their own
    project when it isn't the top-level one. General items have no subgroup.
    The subgroup is None for items that sit directly under the group,
    including those whose subgroup would repeat the group's name.
    """
    group, subgroup = name_board_place(item, vault)
    if subgroup is not None and subgroup.casefold() == group.casefold():
        return group, None
    return group, subgroup


def name_board_place(item: dict, vault: Vault) -> tuple[str, str | None]:
    if "external" in item:
        project_name = item["external"].get("projectName")
        if isinstance(project_name, str) and project_name.strip():
            return item["external"]["sourceLabel"], project_name.strip()
        return item["external"]["sourceLabel"], None
    if item.get("isGeneral"):
        return GENERAL_GROUP, None
    project = vault.root / item["file"]
    if not project.is_file():
        return GENERAL_GROUP, None
    top_level = vault.top_level_project(project)
    if top_level.resolve() == project.resolve():
        return top_level.stem, None
    return top_level.stem, project.stem


def completed_on(item: dict, day: date) -> bool:
    completed_at = item.get("completedAt")
    return (
        completed_at is not None
        and datetime.fromtimestamp(completed_at / 1000).date() == day
    )


def build_board_markdown(
    items: list[dict], vault: Vault, today: date, title: str, message: str | None
) -> str:
    """Build the board: grouped unfinished items, then today's completions.

    Groups are `###` headings and subgroups `####`; within a group, items with
    no subgroup come first. Items whose text is empty once vault markup is
    stripped are left off.
    """
    vault.allow_rescan()

    unfinished = [item for item in items if item.get("completedAt") is None]
    ordered = [item for item in unfinished if item.get("isPinned")] + [
        item for item in unfinished if not item.get("isPinned")
    ]
    # Each group starts with its None subgroup, for items directly under it
    groups: dict[str, dict[str | None, list[str]]] = {}
    for item in ordered:
        text = clean_item_text(item["text"])
        if text:
            group, subgroup = board_place(item, vault)
            subgroups = groups.setdefault(group, {None: []})
            subgroups.setdefault(subgroup, []).append(text)
    done = [
        text
        for item in items
        if completed_on(item, today) and (text := clean_item_text(item["text"]))
    ]

    sections = [f"# {title}\n## {today:%B} {today.day} {today.year}\n"]
    if message:
        sections.append(f"**{message}**\n")
    for heading, subgroups in groups.items():
        sections.append(f"### {heading}\n" + bullet_list(subgroups.pop(None)))
        for subheading, texts in subgroups.items():
            sections.append(f"#### {subheading}\n" + bullet_list(texts))
    if done:
        sections.append(f"##### {DONE_HEADING}\n" + bullet_list(done))
    return "\n".join(sections)


def bullet_list(texts: list[str]) -> str:
    return "".join(f"- {text}\n" for text in texts)


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
        vault: Vault,
        title: str,
        message: str | None,
        *,
        today: Callable[[], date] = date.today,
        warn: Callable[[str], None] = print_warning,
    ):
        self.focus_path = focus_path
        self.vault = vault
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
            items, self.vault, self.today(), self.title, self.message
        )
