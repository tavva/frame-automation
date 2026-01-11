# ABOUTME: Tests for frame-automation state file operations.
# ABOUTME: Covers reading/writing the last uploaded content ID.

import tempfile
from pathlib import Path

import pytest


def test_get_state_file_path_uses_home_directory():
    """State file should be stored in ~/.frame-automation/."""
    from frame_automation.main import get_state_file_path

    path = get_state_file_path()
    assert path.parent.name == ".frame-automation"
    assert path.parent.parent == Path.home()
    assert path.name == "last_content_id"


def test_read_last_content_id_returns_none_when_file_missing(tmp_path, monkeypatch):
    """Should return None if no state file exists."""
    from frame_automation.main import get_state_file_path, read_last_content_id

    monkeypatch.setattr(
        "frame_automation.main.get_state_file_path", lambda: tmp_path / "missing"
    )
    assert read_last_content_id() is None


def test_read_last_content_id_returns_stored_value(tmp_path, monkeypatch):
    """Should return the content ID stored in the state file."""
    from frame_automation.main import read_last_content_id

    state_file = tmp_path / "last_content_id"
    state_file.write_text("MY_F0001_abc123")
    monkeypatch.setattr(
        "frame_automation.main.get_state_file_path", lambda: state_file
    )
    assert read_last_content_id() == "MY_F0001_abc123"


def test_read_last_content_id_strips_whitespace(tmp_path, monkeypatch):
    """Should strip whitespace from stored content ID."""
    from frame_automation.main import read_last_content_id

    state_file = tmp_path / "last_content_id"
    state_file.write_text("  MY_F0001_abc123\n  ")
    monkeypatch.setattr(
        "frame_automation.main.get_state_file_path", lambda: state_file
    )
    assert read_last_content_id() == "MY_F0001_abc123"


def test_write_last_content_id_creates_directory_and_file(tmp_path, monkeypatch):
    """Should create parent directory if missing and write content ID."""
    from frame_automation.main import write_last_content_id

    state_file = tmp_path / ".frame-automation" / "last_content_id"
    monkeypatch.setattr(
        "frame_automation.main.get_state_file_path", lambda: state_file
    )

    write_last_content_id("MY_F0002_xyz789")

    assert state_file.exists()
    assert state_file.read_text() == "MY_F0002_xyz789"


def test_write_last_content_id_overwrites_existing(tmp_path, monkeypatch):
    """Should overwrite existing content ID."""
    from frame_automation.main import write_last_content_id

    state_file = tmp_path / "last_content_id"
    state_file.write_text("old_id")
    monkeypatch.setattr(
        "frame_automation.main.get_state_file_path", lambda: state_file
    )

    write_last_content_id("new_id")

    assert state_file.read_text() == "new_id"
