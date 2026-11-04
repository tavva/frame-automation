# ABOUTME: Tests for building the TV board markdown from Flow's focus file.
# ABOUTME: Uses fixture vaults with real focus lines and project notes, not mocks.

import time
from datetime import date, datetime
from pathlib import Path

import pytest

from frame_automation.focus_board import (
    FocusBoard,
    Vault,
    build_board_markdown,
    clean_item_text,
    read_focus_items,
)

FIXTURES = Path(__file__).parent / "fixtures"
VAULT = FIXTURES / "vault"
FOCUS_FILE = VAULT / "flow-focus-data" / "focus.md"


@pytest.fixture(autouse=True)
def london_time(monkeypatch):
    """Fixture timestamps are written for Ben's local time."""
    monkeypatch.setenv("TZ", "Europe/London")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def millis(text: str) -> int:
    return int(datetime.fromisoformat(text).timestamp() * 1000)


def vault_item(file, text, **fields):
    return {
        "file": file,
        "lineNumber": 9,
        "lineContent": f"- [ ] {text}",
        "text": text,
        "sphere": "personal",
        "isGeneral": False,
        "addedAt": 1793520000000,
        **fields,
    }


def general_item(text, **fields):
    return vault_item("Next actions.md", text, isGeneral=True, **fields)


def external_item(label, text, project=None, **fields):
    external = {
        "sourceName": "linear",
        "sourceLabel": label,
        "url": "https://linear.app/acme/issue/ABC-1/x",
        "externalId": "ABC-1",
    }
    if project is not None:
        external["projectName"] = project
    return {
        "id": f"id-{text}",
        "text": text,
        "sphere": "work",
        "addedAt": 1793520000000,
        "external": external,
        **fields,
    }


def board(items, today=date(2026, 11, 4), title="Goals", message=None):
    return build_board_markdown(items, Vault(VAULT), today, title, message)


def headings(markdown):
    return [line[4:] for line in markdown.splitlines() if line.startswith("### ")]


def group_of(item):
    return headings(board([item]))[0]


class TestReadFocusItems:
    def test_reads_every_line_of_the_real_focus_file(self):
        items, problems = read_focus_items(FIXTURES / "real-focus.md")

        assert problems == []
        assert [item["text"] for item in items][:2] == [
            "Buy bubble bath",
            "Look at kerning on the website relaunch logo",
        ]
        assert len(items) == 5

    def test_skips_lines_that_fail_to_parse_and_blank_lines(self):
        items, problems = read_focus_items(FOCUS_FILE)

        assert len(items) == 11
        assert problems == ["line 5: not valid JSON"]

    @pytest.mark.parametrize(
        ("line", "problem"),
        [
            ('{"text": "Truncated mid-sy', "not valid JSON"),
            ('["not", "an", "object"]', "not a JSON object"),
            ('{"text": "Onboarding", "external": null}', "external is not an object"),
            ('{"text": "Onboarding", "external": {"sourceName": "linear"}}',
             "external item has no sourceLabel"),
            ('{"text": "Plumber", "isGeneral": true}', "vault item has no file"),
            ('{"file": "Next actions.md", "isGeneral": true}', "no text"),
            ('{"file": "Next actions.md", "text": "Bath", "completedAt": "today"}',
             "completedAt is not a number"),
            ('{"file": "Next actions.md", "text": "Bath", "completedAt": NaN}',
             "completedAt is not a finite number"),
            ('{"file": "Next actions.md", "text": "Bath", "completedAt": Infinity}',
             "completedAt is not a finite number"),
            ('{"file": "Next actions.md", "text": "Bath", "completedAt": 1e300}',
             "completedAt is out of range"),
        ],
    )
    def test_skips_lines_the_board_cannot_show(self, tmp_path, line, problem):
        focus_file = tmp_path / "focus.md"
        good = '{"file": "Next actions.md", "text": "Bath", "isGeneral": true}'
        focus_file.write_text(f"{good}\n{line}\n")

        items, problems = read_focus_items(focus_file)

        assert [item["text"] for item in items] == ["Bath"]
        assert problems == [f"line 2: {problem}"]

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            read_focus_items(tmp_path / "focus.md")


class TestFocusBoard:
    def test_warns_once_about_each_skipped_line(self, tmp_path):
        focus_file = tmp_path / "focus.md"
        focus_file.write_text('{"text": "Onboarding", "external": null}\n')
        warnings = []
        focus_board = FocusBoard(
            focus_file, Vault(VAULT), "Goals", None,
            today=lambda: date(2026, 11, 4), warn=warnings.append,
        )

        focus_board.build()
        focus_board.build()
        assert warnings == [f"Skipped {focus_file} line 1: external is not an object"]

        focus_file.write_text('{"text": "Onboarding", "external": null}\n{oops\n')
        focus_board.build()

        assert warnings[1:] == [f"Skipped {focus_file} line 2: not valid JSON"]

    def test_warning_goes_to_stderr_by_default(self, tmp_path, capsys):
        focus_file = tmp_path / "focus.md"
        focus_file.write_text("{oops\n")

        board_text = FocusBoard(focus_file, Vault(VAULT), "Goals", None).build()

        assert board_text.startswith("# Goals\n")
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == f"Warning: Skipped {focus_file} line 1: not valid JSON\n"


class TestWholeBoard:
    def test_builds_the_board_from_the_fixture_focus_file(self):
        markdown = board(read_focus_items(FOCUS_FILE)[0], message="No new things!")

        assert markdown == (
            "# Goals\n"
            "## November 4 2026\n"
            "\n"
            "**No new things!**\n"
            "\n"
            "### Acme\n"
            "- Write up and share onboarding guide\n"
            "\n"
            "#### Data platform\n"
            "- Label the first 50 traces\n"
            "\n"
            "### Misc\n"
            "- Book the [MOT](https://example.com/mot) for the *car*\n"
            "- Call the plumber\n"
            "\n"
            "### Flow\n"
            "- Release Flow 2.0\n"
            "\n"
            "#### Keyboard shortcuts for Flow\n"
            "- Pick default shortcuts for the common commands\n"
            "\n"
            "#### Shortcut cheatsheet\n"
            "- Write a cheatsheet for shortcut keys\n"
            "\n"
            "### Orphan\n"
            "- Find this a home\n"
            "\n"
            "##### Done today\n"
            "- Draft section 2 of the onboarding guide\n"
            "- Ship the syncing beta\n"
        )

    def test_real_focus_file_on_its_completion_day_lists_everything_as_done(self):
        markdown = board(
            read_focus_items(FIXTURES / "real-focus.md")[0], today=date(2026, 10, 30)
        )

        assert headings(markdown) == []
        assert markdown.endswith(
            "##### Done today\n"
            "- Buy bubble bath\n"
            "- Look at kerning on the website relaunch logo\n"
            "- Add Chris to the shared drive\n"
            "- Drop the feature chat feature from the demo app\n"
            "- Send overview of consultancy thing to Joe Bloggs\n"
        )

    def test_empty_focus_list_renders_only_the_header_and_message(self):
        assert board([], title="Focus", message="Rest") == (
            "# Focus\n## November 4 2026\n\n**Rest**\n"
        )

    def test_message_is_optional(self):
        assert board([]) == "# Goals\n## November 4 2026\n"


class TestGroups:
    def test_external_items_group_by_source_label(self):
        assert group_of(external_item("Acme", "Onboarding")) == "Acme"

    def test_general_items_go_under_misc(self):
        assert group_of(general_item("Buy bubble bath")) == "Misc"

    def test_project_without_a_parent_is_its_own_group(self):
        assert group_of(vault_item("Projects/Flow.md", "Release")) == "Flow"

    def test_project_item_goes_under_its_parent_by_file_name(self):
        item = vault_item("Projects/Keyboard shortcuts for Flow.md", "Tools")

        assert group_of(item) == "Flow"

    def test_two_level_chain_through_an_aliased_link(self):
        assert group_of(vault_item("Projects/Shortcut cheatsheet.md", "Cheatsheet")) == "Flow"

    def test_path_link_with_a_heading(self):
        assert group_of(vault_item("Projects/Flow sync.md", "Ship")) == "Flow"

    def test_unresolved_link_stops_at_the_last_project_found(self):
        assert group_of(vault_item("Projects/Orphan.md", "Home")) == "Orphan"

    def test_ambiguous_file_name_is_treated_as_unresolved(self):
        assert group_of(vault_item("Projects/Dup child.md", "Pick")) == "Dup child"

    def test_dot_folders_are_not_searched(self):
        # .obsidian/Flow.md and .trash/Flow.md would make [[Flow]] ambiguous
        item = vault_item("Projects/Keyboard shortcuts for Flow.md", "Tools")

        assert group_of(item) == "Flow"

    def test_links_match_case_insensitively_and_use_the_real_file_name(self):
        # Lower link.md links to [[flow]]; the heading is the file's own name
        assert group_of(vault_item("Projects/Lower link.md", "Lower")) == "Flow"

    def test_path_link_with_the_md_extension(self):
        item = vault_item("Projects/Extension link.md", "Extension")

        assert group_of(item) == "Flow"

    def test_projects_in_a_loop_share_one_group(self):
        # Loop A and Loop B are each other's parent; the first path sorts top
        markdown = board(
            [
                vault_item("Projects/Loop B.md", "Untangle B"),
                vault_item("Projects/Loop A.md", "Untangle A"),
            ]
        )

        assert markdown.endswith(
            "### Loop A\n- Untangle A\n\n#### Loop B\n- Untangle B\n"
        )

    def test_a_chain_into_a_loop_joins_the_loop_group(self, tmp_path):
        projects = tmp_path / "Projects"
        projects.mkdir()
        (projects / "Into loop.md").write_text('---\nparent-project: "[[Loop B]]"\n---\n')
        (projects / "Loop A.md").write_text('---\nparent-project: "[[Loop B]]"\n---\n')
        (projects / "Loop B.md").write_text('---\nparent-project: "[[Loop A]]"\n---\n')
        markdown = build_board_markdown(
            [vault_item("Projects/Into loop.md", "Join")],
            Vault(tmp_path), date(2026, 11, 4), "Goals", None,
        )

        assert markdown.endswith("### Loop A\n\n#### Into loop\n- Join\n")

    def test_unparseable_frontmatter_stops_the_walk(self):
        item = vault_item("Projects/Broken frontmatter.md", "Fix")

        assert group_of(item) == "Broken frontmatter"

    def test_missing_item_file_goes_under_misc(self):
        assert group_of(vault_item("Projects/Deleted.md", "Gone")) == "Misc"

    def test_items_with_the_same_heading_share_a_group(self):
        markdown = board(
            [
                vault_item("Projects/Flow.md", "Release"),
                vault_item("Projects/Keyboard shortcuts for Flow.md", "Tools"),
            ]
        )

        assert headings(markdown) == ["Flow"]


def subheadings(markdown):
    return [line[5:] for line in markdown.splitlines() if line.startswith("#### ")]


class TestSubgroups:
    def test_linear_items_subgroup_by_project_with_unassigned_items_first(self):
        markdown = board(
            [
                external_item("Acme", "Label traces", project="Data platform"),
                external_item("Acme", "Reply to Sam"),
                external_item("Acme", "Fix login", project="Web app"),
                external_item("Acme", "Score traces", project="Data platform"),
            ]
        )

        assert markdown.endswith(
            "### Acme\n"
            "- Reply to Sam\n"
            "\n"
            "#### Data platform\n"
            "- Label traces\n"
            "- Score traces\n"
            "\n"
            "#### Web app\n"
            "- Fix login\n"
        )

    @pytest.mark.parametrize("project", ["", "   ", 7, ["Onboarding"]])
    def test_blank_or_odd_project_names_sit_directly_under_the_group(self, project):
        markdown = board([external_item("Acme", "Reply", project=project)])

        assert markdown.endswith("### Acme\n- Reply\n")

    def test_project_name_is_trimmed(self):
        markdown = board(
            [
                external_item("Acme", "One", project="Onboarding "),
                external_item("Acme", "Two", project="Onboarding"),
            ]
        )

        assert subheadings(markdown) == ["Onboarding"]

    def test_each_workspace_keeps_its_own_projects(self):
        markdown = board(
            [
                external_item("Acme", "Plan", project="Roadmap"),
                external_item("Globex", "Invoice", project="Roadmap"),
            ]
        )

        assert markdown.endswith(
            "### Acme\n\n#### Roadmap\n- Plan\n\n"
            "### Globex\n\n#### Roadmap\n- Invoice\n"
        )

    def test_sub_project_is_a_subgroup_and_top_level_actions_come_first(self):
        markdown = board(
            [
                vault_item("Projects/Keyboard shortcuts for Flow.md", "Tools"),
                vault_item("Projects/Flow.md", "Release"),
            ]
        )

        assert markdown.endswith(
            "### Flow\n- Release\n\n#### Keyboard shortcuts for Flow\n- Tools\n"
        )

    def test_deeper_chain_collapses_to_top_level_and_own_project(self):
        # Shortcut cheatsheet -> Keyboard shortcuts for Flow -> Flow
        markdown = board([vault_item("Projects/Shortcut cheatsheet.md", "Cheatsheet")])

        assert markdown.endswith("### Flow\n\n#### Shortcut cheatsheet\n- Cheatsheet\n")

    def test_project_whose_parent_does_not_resolve_has_no_subgroup(self):
        markdown = board([vault_item("Projects/Orphan.md", "Home")])

        assert markdown.endswith("### Orphan\n- Home\n")

    @pytest.mark.parametrize("project", ["Acme", "acme"])
    def test_project_named_like_its_workspace_sits_directly_under_it(self, project):
        markdown = board(
            [
                external_item("Acme", "Reply to Sam"),
                external_item("Acme", "Plan", project=project),
            ]
        )

        assert markdown.endswith("### Acme\n- Reply to Sam\n- Plan\n")

    def test_sub_project_named_like_its_top_level_project_sits_directly_under_it(
        self, tmp_path
    ):
        (tmp_path / "Projects").mkdir()
        (tmp_path / "Areas").mkdir()
        (tmp_path / "Projects" / "Garden.md").write_text("---\nstatus: live\n---\n")
        (tmp_path / "Areas" / "Garden.md").write_text(
            '---\nparent-project: "[[Projects/Garden]]"\n---\n'
        )
        markdown = build_board_markdown(
            [vault_item("Areas/Garden.md", "Weed"), vault_item("Projects/Garden.md", "Mow")],
            Vault(tmp_path), date(2026, 11, 4), "Goals", None,
        )

        assert markdown.endswith("### Garden\n- Weed\n- Mow\n")

    def test_general_items_have_no_subgroups(self):
        markdown = board([general_item("Plumber"), general_item("MOT")])

        assert markdown.endswith("### Misc\n- Plumber\n- MOT\n")

    def test_subgroups_follow_their_first_item_after_pinned_items(self):
        markdown = board(
            [
                external_item("Acme", "Label traces", project="Data platform"),
                external_item("Acme", "Fix login", project="Web app", isPinned=True),
            ]
        )

        assert subheadings(markdown) == ["Web app", "Data platform"]


class TestVaultIndex:
    """The vault's file index is reused between builds and rescanned on a miss."""

    @pytest.fixture
    def vault_copy(self, tmp_path):
        import shutil

        shutil.copytree(VAULT, tmp_path / "vault")
        return tmp_path / "vault"

    def build(self, vault, items):
        return build_board_markdown(items, vault, date(2026, 11, 4), "Goals", None)

    def test_hits_reuse_the_index_between_builds(self, vault_copy):
        vault = Vault(vault_copy)
        items = [vault_item("Projects/Keyboard shortcuts for Flow.md", "Tools")]

        self.build(vault, items)
        self.build(vault, items)
        self.build(vault, items)

        assert vault.scans == 1

    def test_a_miss_rescans_and_finds_a_new_file(self, vault_copy):
        vault = Vault(vault_copy)
        child = vault_copy / "Projects" / "New child.md"
        child.write_text('---\nparent-project: "[[New parent]]"\n---\n')
        items = [vault_item("Projects/New child.md", "Child")]

        assert headings(self.build(vault, items)) == ["New child"]

        (vault_copy / "Areas").mkdir()
        (vault_copy / "Areas" / "New parent.md").write_text("---\nstatus: live\n---\n")

        assert headings(self.build(vault, items)) == ["New parent"]

    def test_a_moved_file_is_found_at_its_new_place(self, vault_copy):
        vault = Vault(vault_copy)
        items = [vault_item("Projects/Keyboard shortcuts for Flow.md", "Tools")]
        assert headings(self.build(vault, items)) == ["Flow"]

        (vault_copy / "Archive" / "Flow.md").write_bytes(
            (vault_copy / "Projects" / "Flow.md").read_bytes()
        )
        (vault_copy / "Projects" / "Flow.md").unlink()

        assert headings(self.build(vault, items)) == ["Flow"]
        assert vault.scans == 2

    def test_a_miss_rescans_at_most_once_per_build(self, vault_copy):
        vault = Vault(vault_copy)
        items = [
            vault_item("Projects/Orphan.md", "One"),
            vault_item("Projects/Orphan.md", "Two"),
        ]

        self.build(vault, items)

        assert vault.scans == 1


class TestOrder:
    def test_pinned_items_come_first_and_lead_their_groups(self):
        markdown = board(
            [
                vault_item("Projects/Flow.md", "Release"),
                general_item("Plumber"),
                external_item("Acme", "Onboarding", isPinned=True),
                general_item("MOT", isPinned=True),
            ]
        )

        assert headings(markdown) == ["Acme", "Misc", "Flow"]
        assert "### Misc\n- MOT\n- Plumber\n" in markdown

    def test_groups_follow_the_order_of_their_first_item(self):
        markdown = board(
            [
                general_item("One"),
                vault_item("Projects/Flow.md", "Two"),
                general_item("Three"),
            ]
        )

        assert headings(markdown) == ["Misc", "Flow"]
        assert "### Misc\n- One\n- Three\n" in markdown


class TestDoneToday:
    def test_lists_todays_completions_in_file_order_without_grouping(self):
        markdown = board(
            [
                external_item("Acme", "Onboarding", completedAt=millis("2026-11-04 09:30")),
                general_item("Bath", completedAt=millis("2026-11-04 08:15")),
            ]
        )

        assert headings(markdown) == []
        assert markdown.endswith("##### Done today\n- Onboarding\n- Bath\n")

    def test_older_completions_are_left_off(self):
        markdown = board([general_item("Bath", completedAt=millis("2026-11-03 12:00"))])

        assert "Bath" not in markdown

    def test_heading_is_omitted_when_nothing_was_done_today(self):
        assert "Done today" not in board([general_item("Bath")])

    def test_local_midnight_is_the_boundary(self):
        markdown = board(
            [
                general_item("Late", completedAt=millis("2026-11-03 23:59:59.999")),
                general_item("Early", completedAt=millis("2026-11-04 00:00:00")),
            ]
        )

        assert markdown.endswith("##### Done today\n- Early\n")

    def test_same_items_on_two_dates_build_different_boards(self):
        items, _ = read_focus_items(FOCUS_FILE)

        assert board(items, today=date(2026, 11, 4)) != board(
            items, today=date(2026, 11, 5)
        )


class TestCleanItemText:
    @pytest.mark.parametrize(
        ("text", "cleaned"),
        [
            (
                "Send overview of consultancy thing to Joe Bloggs "
                "([[2026-10-26T11-01-47|source]])",
                "Send overview of consultancy thing to Joe Bloggs",
            ),
            ("Call the plumber #context/calls #sphere/personal", "Call the plumber"),
            ("Ask [[Steve Smith|Steve]] about it", "Ask Steve about it"),
            ("Read [[Projects/Flow#Next actions]] notes", "Read Flow notes"),
            ("Read [[Flow sync]]", "Read Flow sync"),
            (
                "Book the [MOT](https://example.com/mot#top) for the *car*",
                "Book the [MOT](https://example.com/mot#top) for the *car*",
            ),
            ("Fix issue #42 today", "Fix issue #42 today"),
            ("Call Bob #urgent.", "Call Bob."),
            ("Look at ![[diagram.png]] again", "Look at again"),
            ("Read [[Projects/Flow sync.md]]", "Read Flow sync"),
        ],
    )
    def test_strips_vault_markup_and_keeps_markdown(self, text, cleaned):
        assert clean_item_text(text) == cleaned

    def test_items_that_clean_to_nothing_are_left_off(self):
        markdown = board(
            [
                general_item("#someday"),
                general_item("Bath"),
                general_item("![[photo.jpg]]", completedAt=millis("2026-11-04 08:00")),
            ]
        )

        assert markdown == "# Goals\n## November 4 2026\n\n### Misc\n- Bath\n"

    def test_external_item_text_is_cleaned_too(self):
        item = external_item("Acme", "Review [[Onboarding guide|the plan]] #context/work")

        assert "### Acme\n- Review the plan\n" in board([item])
