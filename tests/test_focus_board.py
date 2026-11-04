# ABOUTME: Tests for building the TV board markdown from Flow's focus file.
# ABOUTME: Uses fixture vaults with real focus lines and project notes, not mocks.

import time
from datetime import date, datetime
from pathlib import Path

import pytest

from frame_automation.focus_board import (
    FocusBoard,
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


def external_item(label, text, **fields):
    return {
        "id": f"id-{text}",
        "text": text,
        "sphere": "work",
        "addedAt": 1793520000000,
        "external": {
            "sourceName": "linear",
            "sourceLabel": label,
            "url": "https://linear.app/acme/issue/ABC-1/x",
            "externalId": "ABC-1",
        },
        **fields,
    }


def board(items, today=date(2026, 11, 4), title="Goals", message=None):
    return build_board_markdown(items, VAULT, today, title, message)


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

        assert len(items) == 9
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
            focus_file, VAULT, "Goals", None,
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

        board_text = FocusBoard(focus_file, VAULT, "Goals", None).build()

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
            "### Misc\n"
            "- Book the [MOT](https://example.com/mot) for the *car*\n"
            "- Call the plumber\n"
            "\n"
            "### Flow\n"
            "- Pick default shortcuts for the common commands\n"
            "- Write a cheatsheet for shortcut keys\n"
            "\n"
            "### Orphan\n"
            "- Find this a home\n"
            "\n"
            "#### Done today\n"
            "- Draft section 2 of the onboarding guide\n"
            "- Ship the syncing beta\n"
        )

    def test_real_focus_file_on_its_completion_day_lists_everything_as_done(self):
        markdown = board(
            read_focus_items(FIXTURES / "real-focus.md")[0], today=date(2026, 10, 30)
        )

        assert headings(markdown) == []
        assert markdown.endswith(
            "#### Done today\n"
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

    def test_obsidian_folder_is_not_searched(self):
        # .obsidian/Flow.md would make [[Flow]] ambiguous if it were searched
        item = vault_item("Projects/Keyboard shortcuts for Flow.md", "Tools")

        assert group_of(item) == "Flow"

    def test_loop_stops_at_the_last_project_before_repeating(self):
        assert group_of(vault_item("Projects/Loop A.md", "Untangle")) == "Loop B"

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
        assert markdown.endswith("#### Done today\n- Onboarding\n- Bath\n")

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

        assert markdown.endswith("#### Done today\n- Early\n")

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
        ],
    )
    def test_strips_vault_markup_and_keeps_markdown(self, text, cleaned):
        assert clean_item_text(text) == cleaned

    def test_external_item_text_is_cleaned_too(self):
        item = external_item("Acme", "Review [[Onboarding guide|the plan]] #context/work")

        assert "### Acme\n- Review the plan\n" in board([item])
