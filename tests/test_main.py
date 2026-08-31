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


class TestMainOrdering:
    """Tests for the order of operations in main."""

    def test_previous_art_is_deleted_only_after_new_image_is_active(
        self, monkeypatch, tmp_path
    ):
        """The TV must never be left without artwork if a step fails."""
        from frame_automation import main as main_module

        calls = []
        content_file = tmp_path / "content.md"
        content_file.write_text("# Hello")

        monkeypatch.setattr(
            main_module, "get_config", lambda: ("192.168.1.100", content_file, "default")
        )
        monkeypatch.setattr(
            main_module,
            "render_to_image",
            lambda content, output, theme: calls.append("render"),
        )
        monkeypatch.setattr(
            main_module,
            "delete_previous_art",
            lambda tv_ip: calls.append("delete_previous"),
        )
        monkeypatch.setattr(
            main_module,
            "upload_to_tv",
            lambda tv_ip, path: (calls.append("upload"), "MY_F0002")[1],
        )
        monkeypatch.setattr(
            main_module,
            "set_active_art",
            lambda tv_ip, content_id: calls.append("set_active"),
        )
        monkeypatch.setattr(
            main_module,
            "write_last_content_id",
            lambda content_id: calls.append("write_state"),
        )

        main_module.main()

        assert calls.index("delete_previous") > calls.index("set_active")
        assert calls.index("delete_previous") < calls.index("write_state")


class TestMainCleanup:
    """Tests for temporary file handling in main."""

    def test_rendered_image_is_removed_when_upload_fails(self, monkeypatch, tmp_path):
        """A failed run must not leave rendered images behind."""
        from frame_automation import main as main_module

        content_file = tmp_path / "content.md"
        content_file.write_text("# Hello")
        rendered = []

        monkeypatch.setattr(
            main_module, "get_config", lambda: ("192.168.1.100", content_file, "default")
        )
        monkeypatch.setattr(
            main_module,
            "render_to_image",
            lambda content, output, theme: rendered.append(output),
        )

        def fail_to_upload(tv_ip, image_path):
            raise ConnectionError("TV unreachable")

        monkeypatch.setattr(main_module, "upload_to_tv", fail_to_upload)

        with pytest.raises(ConnectionError):
            main_module.main()

        assert rendered, "render_to_image was never called"
        assert not rendered[0].exists()


class TestEnsureArtMode:
    """Tests for the ensure_art_mode function."""

    def test_ensure_art_mode_skips_set_when_already_in_art_mode(self, monkeypatch):
        """The TV sends no reply to set_artmode when it is already on, so the
        websocket read blocks until it times out. Skip the redundant call."""
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

        assert art_mode_calls == []

    def test_ensure_art_mode_sets_art_mode_on(self, monkeypatch):
        """Should call set_artmode(True) via the art API."""
        from frame_automation.main import ensure_art_mode

        art_mode_calls = []

        class MockArt:
            def get_artmode(self):
                return "off"

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
                return "off"

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
                return "off"

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


class TestSendImage:
    """Tests for sending an existing image file to the TV."""

    def _patch_upload_chain(self, monkeypatch, calls):
        from frame_automation import main as main_module

        monkeypatch.setattr(
            main_module,
            "upload_to_tv",
            lambda tv_ip, path: (calls.append(("upload", path)), "MY_F0003")[1],
        )
        monkeypatch.setattr(
            main_module,
            "set_active_art",
            lambda tv_ip, content_id: calls.append(("set_active", content_id)),
        )
        monkeypatch.setattr(
            main_module,
            "delete_previous_art",
            lambda tv_ip: calls.append(("delete_previous", None)),
        )
        monkeypatch.setattr(
            main_module,
            "write_last_content_id",
            lambda content_id: calls.append(("write_state", content_id)),
        )

    def test_uploads_the_given_image_and_makes_it_active(self, monkeypatch, tmp_path):
        """The named file should be uploaded and selected as the artwork."""
        from frame_automation import main as main_module

        image = tmp_path / "artwork.png"
        image.write_bytes(b"fake png")
        calls = []
        self._patch_upload_chain(monkeypatch, calls)
        monkeypatch.setenv("FRAME_TV_IP", "192.168.1.100")
        monkeypatch.setattr("sys.argv", ["frame-image", str(image)])

        main_module.main_image()

        assert ("upload", image) in calls
        assert ("set_active", "MY_F0003") in calls
        assert ("write_state", "MY_F0003") in calls

    def test_previous_art_is_deleted_only_after_new_image_is_active(
        self, monkeypatch, tmp_path
    ):
        """The TV must never be left without artwork if a step fails."""
        from frame_automation import main as main_module

        image = tmp_path / "artwork.png"
        image.write_bytes(b"fake png")
        calls = []
        self._patch_upload_chain(monkeypatch, calls)
        monkeypatch.setenv("FRAME_TV_IP", "192.168.1.100")
        monkeypatch.setattr("sys.argv", ["frame-image", str(image)])

        main_module.main_image()

        names = [name for name, _ in calls]
        assert names.index("delete_previous") > names.index("set_active")
        assert names.index("delete_previous") < names.index("write_state")

    def test_exits_when_no_image_path_given(self, monkeypatch):
        """Should explain usage rather than fail obscurely."""
        from frame_automation import main as main_module

        monkeypatch.setenv("FRAME_TV_IP", "192.168.1.100")
        monkeypatch.setattr("sys.argv", ["frame-image"])

        with pytest.raises(SystemExit) as excinfo:
            main_module.main_image()

        assert "Usage" in str(excinfo.value)

    def test_exits_when_image_file_missing(self, monkeypatch, tmp_path):
        """Should report a missing file before contacting the TV."""
        from frame_automation import main as main_module

        missing = tmp_path / "nothing-here.png"
        monkeypatch.setenv("FRAME_TV_IP", "192.168.1.100")
        monkeypatch.setattr("sys.argv", ["frame-image", str(missing)])

        with pytest.raises(SystemExit) as excinfo:
            main_module.main_image()

        assert "not found" in str(excinfo.value)

    def test_exits_when_image_is_not_a_png(self, monkeypatch, tmp_path):
        """Uploads are sent as PNG, so other formats must be rejected."""
        from frame_automation import main as main_module

        image = tmp_path / "artwork.jpg"
        image.write_bytes(b"fake jpeg")
        monkeypatch.setenv("FRAME_TV_IP", "192.168.1.100")
        monkeypatch.setattr("sys.argv", ["frame-image", str(image)])

        with pytest.raises(SystemExit) as excinfo:
            main_module.main_image()

        assert "PNG" in str(excinfo.value)


class TestDefaultTheme:
    """Tests for the theme used when FRAME_THEME is not set."""

    def test_get_config_defaults_to_the_clean_theme(self, monkeypatch, tmp_path):
        """An unset FRAME_THEME should render the clean design."""
        from frame_automation.main import get_config

        content_file = tmp_path / "content.md"
        content_file.write_text("# Goals")
        monkeypatch.setenv("FRAME_TV_IP", "192.168.1.100")
        monkeypatch.setenv("FRAME_CONTENT_FILE", str(content_file))
        monkeypatch.delenv("FRAME_THEME", raising=False)

        _, _, theme = get_config()

        assert theme == "clean"


class TestFitToFrame:
    """Tests for scaling content down to fit the fixed 1920x1080 frame."""

    def _scale_for(self, markdown_text):
        from playwright.sync_api import sync_playwright

        from frame_automation.main import (
            IMAGE_HEIGHT,
            IMAGE_WIDTH,
            build_page_html,
            fit_to_frame,
        )

        html = build_page_html(markdown_text, "clean")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(
                viewport={"width": IMAGE_WIDTH, "height": IMAGE_HEIGHT}
            )
            page.set_content(html)
            scale = fit_to_frame(page)
            browser.close()
        return scale

    def test_content_that_already_fits_is_left_alone(self):
        """Short content must not be scaled up or down."""
        pytest.importorskip("playwright")

        scale = self._scale_for("# Goals\n## Today\n\n### One goal\n- One item")

        assert scale == 1.0

    def test_overflowing_content_is_scaled_down(self):
        """Content taller than the frame must shrink to fit."""
        pytest.importorskip("playwright")

        goals = "\n\n".join(
            f"### Goal number {n} with a reasonably long title\n"
            "- First item\n- Second item\n- Third item"
            for n in range(1, 8)
        )

        scale = self._scale_for(f"# Goals\n## Today\n\n{goals}")

        assert 0.25 <= scale < 1.0
