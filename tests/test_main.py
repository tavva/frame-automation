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


class TestTurnOff:
    """Tests for the turn_off function."""

    def test_turn_off_holds_power_key(self, monkeypatch, tmp_path):
        """Should hold KEY_POWER for 3 seconds via remote API on port 8002."""
        from frame_automation.main import turn_off

        held_keys = []
        init_args = []

        class MockTV:
            def __init__(self, host, port=8001, token_file=None):
                init_args.append({"host": host, "port": port})

            def hold_key(self, key, seconds):
                held_keys.append((key, seconds))

        monkeypatch.setattr("frame_automation.main.SamsungTVWS", MockTV)
        monkeypatch.setattr("frame_automation.main.STATE_DIR", tmp_path)

        turn_off("192.168.1.100")

        assert init_args == [{"host": "192.168.1.100", "port": 8002}]
        assert held_keys == [("KEY_POWER", 3)]


class TestEnsureArtMode:
    """Tests for the ensure_art_mode function."""

    def test_ensure_art_mode_sets_art_mode_on(self, monkeypatch):
        """Should call set_artmode(True) via the art API."""
        from frame_automation.main import ensure_art_mode

        art_mode_calls = []

        class MockArt:
            def get_artmode(self):
                return "on"

            def set_artmode(self, mode):
                art_mode_calls.append(mode)

        class MockTV:
            def __init__(self, host, port=8001, timeout=None, token_file=None):
                pass

            def art(self):
                return MockArt()

        monkeypatch.setattr("frame_automation.main.SamsungTVWS", MockTV)

        ensure_art_mode("192.168.1.100")

        assert art_mode_calls == [True]

    def test_ensure_art_mode_sends_wol_when_mac_provided(self, monkeypatch):
        """Should send WoL packets with broadcast address when MAC is provided."""
        from frame_automation.main import ensure_art_mode

        wol_calls = []
        art_mode_calls = []

        def mock_send_magic_packet(mac, ip_address=None):
            wol_calls.append({"mac": mac, "ip_address": ip_address})

        class MockArt:
            def get_artmode(self):
                return "on"

            def set_artmode(self, mode):
                art_mode_calls.append(mode)

        class MockTV:
            def __init__(self, host, port=8001, timeout=None, token_file=None):
                pass

            def art(self):
                return MockArt()

        monkeypatch.setattr(
            "frame_automation.main.send_magic_packet", mock_send_magic_packet
        )
        monkeypatch.setattr("frame_automation.main.SamsungTVWS", MockTV)

        ensure_art_mode("192.168.1.100", mac="AA:BB:CC:DD:EE:FF")

        # Should send 3 WoL packets with broadcast address
        assert len(wol_calls) == 3
        assert all(c["mac"] == "AA:BB:CC:DD:EE:FF" for c in wol_calls)
        assert all(c["ip_address"] == "192.168.1.255" for c in wol_calls)
        assert art_mode_calls == [True]

    def test_ensure_art_mode_retries_on_connection_failure(self, monkeypatch):
        """Should retry after WoL if initial connection fails."""
        from frame_automation.main import ensure_art_mode

        wol_calls = []
        connection_attempts = []

        def mock_send_magic_packet(mac, ip_address=None):
            wol_calls.append(mac)

        class MockArt:
            def get_artmode(self):
                return "on"

            def set_artmode(self, mode):
                connection_attempts.append("art_mode")

        class MockTV:
            def __init__(self, host, port=8001, timeout=None, token_file=None):
                connection_attempts.append("connect")
                # Fail on first attempt, succeed on second
                if len(connection_attempts) == 1:
                    raise ConnectionRefusedError("TV is off")

            def art(self):
                return MockArt()

        monkeypatch.setattr(
            "frame_automation.main.send_magic_packet", mock_send_magic_packet
        )
        monkeypatch.setattr("frame_automation.main.SamsungTVWS", MockTV)
        monkeypatch.setattr("frame_automation.main.WAKE_RETRY_DELAY", 0)

        ensure_art_mode("192.168.1.100", mac="AA:BB:CC:DD:EE:FF")

        # Should have sent WoL packets (3 per attempt, 2 attempts)
        assert len(wol_calls) == 6
        assert "art_mode" in connection_attempts
