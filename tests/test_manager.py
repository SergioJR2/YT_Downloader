import pytest
from PyQt6.QtCore import QObject, pyqtSignal

from models.errors import PAUSED_MSG
from models.manager import DownloadManager, TaskState


class FakeThread(QObject):
    progress = pyqtSignal(str, float, str, str)
    task_finished = pyqtSignal(str, bool, str)

    def __init__(self, task):
        super().__init__()
        self.task_id = task.id
        self.started = False
        self.pause_requested = False

    def start(self): self.started = True
    def request_pause(self): self.pause_requested = True
    def wait(self, _ms=0): return True
    def isFinished(self): return True
    def deleteLater(self): pass

    def finish(self, ok=True, msg=""):
        self.task_finished.emit(self.task_id, ok, msg)


@pytest.fixture
def env():
    threads = []

    def factory(task, _cookies):
        t = FakeThread(task)
        threads.append(t)
        return t

    mgr = DownloadManager(2, thread_factory=factory)
    events = []
    mgr.state_changed.connect(lambda i, s, m: events.append((i, s, m)))
    removed = []
    mgr.task_removed.connect(removed.append)

    def add(title="Video", url=None, fmt="mp4", quality="best", folder="/tmp/x"):
        return mgr.add_task(title, url or f"https://y/{title}", fmt, quality,
                            "best", 192, folder, 0, True)

    return mgr, threads, add, events, removed


def states(mgr):
    return [t.state for t in mgr.tasks.values()]


def test_respects_concurrency_and_starts_next(env):
    mgr, threads, add, *_ = env
    a, b, c = add("a"), add("b"), add("c")
    mgr.pump()
    assert states(mgr) == [TaskState.RUNNING, TaskState.RUNNING, TaskState.QUEUED]
    assert mgr.queued_ids() == [c.id]
    threads[0].finish()
    assert a.state is TaskState.DONE and c.state is TaskState.RUNNING
    assert len(threads) == 3


def test_pause_active_then_resume(env):
    mgr, threads, add, *_ = env
    a = add("a"); mgr.pump()
    mgr.toggle(a.id)
    assert a.state is TaskState.PAUSING and threads[0].pause_requested
    threads[0].finish(False, PAUSED_MSG)
    assert a.state is TaskState.PAUSED and not mgr.has_pending()
    mgr.toggle(a.id)
    assert a.state is TaskState.RUNNING and len(threads) == 2


def test_pause_queued_does_not_start(env):
    mgr, threads, add, *_ = env
    add("a"); add("b"); c = add("c"); mgr.pump()
    mgr.toggle(c.id)
    assert c.state is TaskState.PAUSED and mgr.queued_ids() == []
    threads[0].finish()
    assert c.state is TaskState.PAUSED and len(threads) == 2


def test_error_then_retry(env):
    mgr, threads, add, events, _ = env
    a = add("a"); mgr.pump()
    threads[0].finish(False, "boom")
    assert a.state is TaskState.ERROR and ("boom" in [m for *_, m in events])
    mgr.toggle(a.id)
    assert a.state is TaskState.RUNNING


def test_remove_queued_and_idle(env):
    mgr, threads, add, _, removed = env
    add("a"); add("b"); c = add("c"); mgr.pump()
    mgr.remove(c.id)
    assert removed == [c.id] and c.id not in mgr.tasks and mgr.queued_ids() == []
    threads[0].finish()
    mgr.remove(next(iter(mgr.tasks)))      # una terminada también se puede quitar
    assert len(removed) == 2


def test_remove_active_waits_for_thread(env):
    mgr, threads, add, events, removed = env
    a = add("a"); mgr.pump()
    mgr.remove(a.id)
    assert a.state is TaskState.REMOVING and threads[0].pause_requested
    assert removed == []
    threads[0].finish(False, PAUSED_MSG)
    assert removed == [a.id] and a.id not in mgr.tasks
    assert TaskState.PAUSED not in [s for _, s, _ in events]


def test_reserved_names_and_is_busy_ignore_done(env):
    mgr, threads, add, *_ = env
    a = add("Song (Official Video)", fmt="mp3", quality="192", folder="/tmp/x")
    mgr.pump()
    names = mgr.reserved_names("/tmp/x")
    assert ("audio", "song") in names
    assert mgr.reserved_names("/tmp/other") == set()
    assert mgr.is_busy(a.url, "mp3", "192") and not mgr.is_busy(a.url, "mp4", "best")
    threads[0].finish()
    assert mgr.reserved_names("/tmp/x") == set() and not mgr.is_busy(a.url, "mp3", "192")


def test_max_concurrent_clamps_and_pumps(env):
    mgr, threads, add, *_ = env
    for n in "abcd":
        add(n)
    mgr.pump()
    assert len(threads) == 2
    mgr.max_concurrent = 99
    assert mgr.max_concurrent == 5 and len(threads) == 4
    mgr.max_concurrent = 0
    assert mgr.max_concurrent == 1


def test_shutdown_pauses_everything_and_stops_pumping(env):
    mgr, threads, add, *_ = env
    add("a"); add("b"); c = add("c"); mgr.pump()
    mgr.shutdown()
    assert all(t.pause_requested for t in threads) and mgr.closing
    threads[0].finish(False, PAUSED_MSG)
    assert c.state is TaskState.QUEUED and len(threads) == 2


def test_factory_failure_becomes_error():
    def broken(_task, _cookies):
        raise RuntimeError("sin hilo")
    mgr = DownloadManager(2, thread_factory=broken)
    t = mgr.add_task("a", "u", "mp4", "best", "best", 192, "/tmp", 0, True)
    mgr.pump()
    assert t.state is TaskState.ERROR and not mgr.has_pending()


def test_pause_all_pauses_running_and_queued_and_starts_nothing(env):
    mgr, threads, add, *_ = env
    for name in "abcd":
        add(name)
    mgr.pump()
    mgr.pause_all()
    assert states(mgr) == [TaskState.PAUSING, TaskState.PAUSING,
                           TaskState.PAUSED, TaskState.PAUSED]
    assert all(t.pause_requested for t in threads)
    for t in list(threads):
        t.finish(False, PAUSED_MSG)
    assert states(mgr) == [TaskState.PAUSED] * 4
    assert len(threads) == 2            # al parar los activos no arrancó ninguno nuevo


def test_resume_all_requeues_in_creation_order(env):
    mgr, threads, add, *_ = env
    a, b, c = add("a"), add("b"), add("c")
    mgr.pump()
    mgr.pause_all()
    for t in list(threads):
        t.finish(False, PAUSED_MSG)
    mgr.resume_all()
    assert states(mgr) == [TaskState.RUNNING, TaskState.RUNNING, TaskState.QUEUED]
    assert mgr.queued_ids() == [c.id]


def test_resume_all_ignores_errors_and_done(env):
    mgr, threads, add, *_ = env
    a, b = add("a"), add("b")
    mgr.pump()
    threads[0].finish(True)
    threads[1].finish(False, "falló")
    mgr.resume_all()
    assert states(mgr) == [TaskState.DONE, TaskState.ERROR]


def test_cancel_all_removes_everything_unfinished(env):
    mgr, threads, add, events, removed = env
    a, b, c, d = add("a"), add("b"), add("c"), add("d")
    mgr.pump()
    threads[0].finish(True)             # a termina: c ocupa su hueco, d sigue en cola
    assert states(mgr) == [TaskState.DONE, TaskState.RUNNING,
                           TaskState.RUNNING, TaskState.QUEUED]
    mgr.cancel_all()
    assert removed == [d.id]                     # la que esperaba se quita al instante
    assert all(t.pause_requested for t in threads[1:3])
    for t in threads[1:3]:
        t.finish(False, PAUSED_MSG)              # las activas se quitan al parar
    assert list(mgr.tasks) == [a.id]             # solo queda la terminada
    assert len(threads) == 3                     # no arrancó nada nuevo
