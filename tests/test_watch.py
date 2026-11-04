# ABOUTME: Tests for watching content and publishing it after changes settle.
# ABOUTME: Covers debounce, retry, saved digests and focus-mode rebuilds.

import hashlib

import pytest


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def test_initial_content_is_published_after_ten_quiet_seconds(tmp_path):
    from frame_automation import main as main_module

    content_file = tmp_path / "goals.md"
    content_file.write_text("# Goals\n")
    state_file = tmp_path / "last_content_sha256"
    clock = FakeClock()
    published = []

    watcher = main_module.ContentWatcher(
        content_file.read_text,
        published.append,
        state_file=state_file,
        clock=clock,
        debounce_seconds=10,
        retry_seconds=300,
    )

    watcher.poll()
    clock.advance(9)
    watcher.poll()
    assert published == []

    clock.advance(1)
    watcher.poll()

    assert published == ["# Goals\n"]
    assert state_file.read_text() == hashlib.sha256(b"# Goals\n").hexdigest()


def test_failed_publish_is_retried_after_five_minutes(tmp_path):
    from frame_automation import main as main_module

    content_file = tmp_path / "goals.md"
    content_file.write_text("# Goals\n")
    state_file = tmp_path / "last_content_sha256"
    clock = FakeClock()
    attempts = []

    def publish(content):
        attempts.append(clock())
        if len(attempts) == 1:
            raise ConnectionError("TV unavailable")

    watcher = main_module.ContentWatcher(
        content_file.read_text,
        publish,
        state_file=state_file,
        clock=clock,
        debounce_seconds=10,
        retry_seconds=300,
    )

    watcher.poll()
    clock.advance(10)
    watcher.poll()
    assert attempts == [10]
    assert not state_file.exists()

    clock.advance(299)
    watcher.poll()
    assert attempts == [10]

    clock.advance(1)
    watcher.poll()
    assert attempts == [10, 310]
    assert state_file.exists()


def test_watch_content_polls_once_per_second(tmp_path):
    from frame_automation import main as main_module

    content_file = tmp_path / "goals.md"
    content_file.write_text("# Goals\n")
    sleeps = []

    class StopWatching(Exception):
        pass

    def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise StopWatching

    with pytest.raises(StopWatching):
        main_module.watch_content(
            content_file.read_text,
            lambda content: None,
            state_file=tmp_path / "state",
            sleep=sleep,
        )

    assert sleeps == [1, 1]


def test_new_changes_reset_the_quiet_period(tmp_path):
    from frame_automation import main as main_module

    content_file = tmp_path / "goals.md"
    content_file.write_text("first")
    clock = FakeClock()
    published = []
    watcher = main_module.ContentWatcher(
        content_file.read_text,
        published.append,
        state_file=tmp_path / "state",
        clock=clock,
        debounce_seconds=10,
    )

    watcher.poll()
    clock.advance(6)
    content_file.write_text("second")
    watcher.poll()
    clock.advance(9)
    watcher.poll()
    assert published == []

    clock.advance(1)
    watcher.poll()
    assert published == ["second"]


def test_persisted_digest_prevents_duplicate_publish_after_restart(tmp_path):
    from frame_automation import main as main_module

    content_file = tmp_path / "goals.md"
    content_file.write_text("unchanged")
    state_file = tmp_path / "state"
    state_file.write_text(hashlib.sha256(b"unchanged").hexdigest())
    clock = FakeClock()
    published = []
    watcher = main_module.ContentWatcher(
        content_file.read_text,
        published.append,
        state_file=state_file,
        clock=clock,
    )

    watcher.poll()
    clock.advance(60)
    watcher.poll()

    assert published == []


def test_missing_file_is_ignored_until_it_reappears(tmp_path):
    from frame_automation import main as main_module

    content_file = tmp_path / "goals.md"
    clock = FakeClock()
    published = []
    watcher = main_module.ContentWatcher(
        content_file.read_text,
        published.append,
        state_file=tmp_path / "state",
        clock=clock,
        debounce_seconds=10,
    )

    watcher.poll()
    clock.advance(30)
    content_file.write_text("back")
    watcher.poll()
    clock.advance(10)
    watcher.poll()

    assert published == ["back"]


def test_file_vanishing_during_an_atomic_save_is_ignored(tmp_path):
    from frame_automation import main as main_module

    def read_vanishing_file():
        raise FileNotFoundError

    watcher = main_module.ContentWatcher(
        read_vanishing_file,
        lambda content: None,
        state_file=tmp_path / "state",
    )

    watcher.poll()


def test_main_watch_publishes_what_the_watcher_read(tmp_path, monkeypatch):
    from frame_automation import main as main_module

    content_file = tmp_path / "goals.md"
    content_file.write_text("# Goals\n")
    state_file = tmp_path / "last_content_sha256"
    calls = []

    monkeypatch.setenv("FRAME_TV_IP", "192.168.1.100")
    monkeypatch.setenv("FRAME_CONTENT_FILE", str(content_file))
    monkeypatch.delenv("FRAME_FOCUS_FILE", raising=False)
    monkeypatch.setattr(main_module, "get_watch_state_file_path", lambda: state_file)
    monkeypatch.setattr(
        main_module,
        "update_content",
        lambda tv_ip, markdown_text, theme: calls.append((tv_ip, markdown_text, theme)),
    )

    def watch_once(read_content, publish, *, state_file):
        calls.append(("watch", state_file))
        publish(read_content())

    monkeypatch.setattr(main_module, "watch_content", watch_once)

    main_module.main_watch()

    assert calls == [
        ("watch", state_file),
        ("192.168.1.100", "# Goals\n", "clean"),
    ]


def test_markdown_mode_digest_matches_the_file_bytes(tmp_path, monkeypatch):
    """Digests saved before focus mode existed must still match."""
    from frame_automation import main as main_module

    content_file = tmp_path / "goals.md"
    content_file.write_bytes(b"# Goals\r\n- caf\xc3\xa9\r\n")
    state_file = tmp_path / "state"
    state_file.write_text(hashlib.sha256(content_file.read_bytes()).hexdigest())
    monkeypatch.setenv("FRAME_TV_IP", "192.168.1.100")
    monkeypatch.setenv("FRAME_CONTENT_FILE", str(content_file))
    monkeypatch.delenv("FRAME_FOCUS_FILE", raising=False)
    clock = FakeClock()
    published = []

    watcher = main_module.ContentWatcher(
        main_module.get_config().read_content,
        published.append,
        state_file=state_file,
        clock=clock,
    )
    watcher.poll()
    clock.advance(60)
    watcher.poll()

    assert published == []


class TestFocusModeWatcher:
    """A focus-mode watcher rebuilds the board every poll from the focus file and date."""

    @pytest.fixture
    def vault(self, tmp_path):
        import shutil
        from pathlib import Path

        vault = tmp_path / "vault"
        shutil.copytree(Path(__file__).parent / "fixtures" / "vault", vault)
        return vault

    def _watcher(self, vault, today, published, clock):
        from frame_automation import main as main_module
        from frame_automation.focus_board import FocusBoard

        self.warnings = []
        return main_module.ContentWatcher(
            FocusBoard(
                vault / "flow-focus-data" / "focus.md",
                vault,
                "Goals",
                None,
                today=lambda: today[0],
                warn=self.warnings.append,
            ).build,
            published.append,
            state_file=vault.parent / "state",
            clock=clock,
            debounce_seconds=10,
        )

    def test_publishes_after_a_focus_file_edit(self, vault):
        from datetime import date

        clock = FakeClock()
        published = []
        watcher = self._watcher(vault, [date(2026, 11, 4)], published, clock)

        watcher.poll()
        clock.advance(10)
        watcher.poll()
        assert len(published) == 1

        focus_file = vault / "flow-focus-data" / "focus.md"
        focus_file.write_text(
            focus_file.read_text()
            + '{"file":"Next actions.md","lineNumber":7,"lineContent":"- [ ] Water the plants",'
            '"text":"Water the plants","sphere":"personal","isGeneral":true,"addedAt":1793520000007}\n'
        )
        watcher.poll()
        clock.advance(10)
        watcher.poll()

        assert len(published) == 2
        assert "- Water the plants\n" in published[1]
        assert "- Water the plants\n" not in published[0]

    def test_publishes_when_the_date_changes(self, vault):
        from datetime import date

        clock = FakeClock()
        published = []
        today = [date(2026, 11, 4)]
        watcher = self._watcher(vault, today, published, clock)

        watcher.poll()
        clock.advance(10)
        watcher.poll()
        clock.advance(3600)
        watcher.poll()
        assert len(published) == 1

        today[0] = date(2026, 11, 5)
        watcher.poll()
        clock.advance(10)
        watcher.poll()

        assert len(published) == 2
        assert "## November 5 2026\n" in published[1]

    def test_a_briefly_empty_or_truncated_file_never_reaches_the_tv(self, vault):
        """A sync that empties or truncates focus.md for less than the debounce is ignored."""
        from datetime import date

        clock = FakeClock()
        published = []
        watcher = self._watcher(vault, [date(2026, 11, 4)], published, clock)
        focus_file = vault / "flow-focus-data" / "focus.md"
        full = focus_file.read_text()

        watcher.poll()
        clock.advance(10)
        watcher.poll()
        assert len(published) == 1

        focus_file.write_text("")
        watcher.poll()
        clock.advance(4)
        focus_file.write_text(full[:200])
        watcher.poll()
        clock.advance(4)
        focus_file.write_text(full)
        watcher.poll()
        clock.advance(60)
        watcher.poll()

        assert len(published) == 1
        assert any(w.endswith("line 1: not valid JSON") for w in self.warnings)
