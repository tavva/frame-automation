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
        content_file,
        lambda: published.append(content_file.read_text()),
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

    def publish():
        attempts.append(clock())
        if len(attempts) == 1:
            raise ConnectionError("TV unavailable")

    watcher = main_module.ContentWatcher(
        content_file,
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
            content_file,
            lambda: None,
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
        content_file,
        lambda: published.append(content_file.read_text()),
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
        content_file,
        lambda: published.append(True),
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
        content_file,
        lambda: published.append(content_file.read_text()),
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

    class VanishingFile:
        def exists(self):
            return True

        def read_bytes(self):
            raise FileNotFoundError

    watcher = main_module.ContentWatcher(
        VanishingFile(),
        lambda: None,
        state_file=tmp_path / "state",
    )

    watcher.poll()


def test_main_watch_reuses_the_configured_update_path(tmp_path, monkeypatch):
    from frame_automation import main as main_module

    content_file = tmp_path / "goals.md"
    content_file.write_text("# Goals\n")
    state_file = tmp_path / "last_content_sha256"
    calls = []

    monkeypatch.setattr(
        main_module,
        "get_config",
        lambda: ("192.168.1.100", content_file, "clean"),
    )
    monkeypatch.setattr(
        main_module,
        "get_watch_state_file_path",
        lambda: state_file,
        raising=False,
    )
    monkeypatch.setattr(
        main_module,
        "update_content",
        lambda tv_ip, path, theme: calls.append((tv_ip, path, theme)),
        raising=False,
    )

    def watch_once(path, publish, *, state_file):
        calls.append(("watch", path, state_file))
        publish()

    monkeypatch.setattr(main_module, "watch_content", watch_once)

    main_module.main_watch()

    assert calls == [
        ("watch", content_file, state_file),
        ("192.168.1.100", content_file, "clean"),
    ]
