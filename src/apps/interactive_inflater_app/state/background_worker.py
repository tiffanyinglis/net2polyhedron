"""Generic Tkinter-safe background-worker helper, pulled out of InflaterPane._run_background
(2026-09-30 modularization) -- this one was already almost fully generic (its only InflaterPane-
specific bit was a hardcoded revert-on-error call), so making the error path an injected
callback turns it into a standalone utility with zero dependency on InflaterPane's own state.
"""
import queue
import threading


def run_in_background(root, fn, on_done, on_progress=None, on_error=None):
    """Runs `fn(progress_callback)` on a background daemon thread, polling its result back onto
    the main thread via `root.after` -- Tkinter itself is not thread-safe, so every one of
    `on_done`/`on_progress`/`on_error` below is always called from the MAIN thread, never the
    worker.

    `fn` is called with one argument, a `progress_callback(payload)` it may call as often as it
    likes from the WORKER thread -- each call is queued and later delivered to `on_progress` (if
    given), in order, via the same polling loop that delivers the final result. `on_done(result)`
    is called once `fn` returns normally. `on_error(message)` is called if `fn` raises --
    surfaces a crash instead of silently hanging forever or leaving an exception stuck on a
    thread nobody's watching; if not given, the exception is re-raised inside the `root.after`
    callback instead (surfacing through Tkinter's own default callback-exception reporting)."""
    q = queue.Queue()

    def queue_progress(payload):
        q.put(("progress", payload))

    def worker():
        try:
            q.put(("done", fn(queue_progress)))
        except Exception as e:  # surface a crash instead of hanging forever
            q.put(("error", str(e)))

    threading.Thread(target=worker, daemon=True).start()

    def poll():
        try:
            while True:
                kind, payload = q.get_nowait()
                if kind == "progress":
                    if on_progress is not None:
                        on_progress(payload)
                    continue
                if kind == "error":
                    if on_error is not None:
                        on_error(payload)
                    else:
                        raise RuntimeError(payload)
                    return
                on_done(payload)
                return
        except queue.Empty:
            pass
        root.after(100, poll)

    root.after(100, poll)
