import time
import tkinter as tk

import pytest

from interactive_inflater_app.state.background_worker import run_in_background


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available for Tk root")
    r.withdraw()
    yield r
    r.destroy()


def _pump_until(root, predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        root.update()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_run_in_background_delivers_progress_and_done_on_main_thread(root):
    import threading

    main_thread = threading.get_ident()
    progress_calls = []
    done_result = {}

    def fn(progress_callback):
        progress_callback("working")
        return "finished"

    def on_progress(payload):
        progress_calls.append((payload, threading.get_ident()))

    def on_done(result):
        done_result["value"] = result
        done_result["thread"] = threading.get_ident()

    run_in_background(root, fn, on_done, on_progress=on_progress)
    assert _pump_until(root, lambda: "value" in done_result)

    assert progress_calls == [("working", main_thread)]
    assert done_result == {"value": "finished", "thread": main_thread}


def test_run_in_background_calls_on_error_with_exception_message(root):
    caught = {}

    def fn(progress_callback):
        raise ValueError("boom")

    def on_done(result):
        raise AssertionError("on_done should not be called on error")

    def on_error(message):
        caught["message"] = message

    run_in_background(root, fn, on_done, on_error=on_error)
    assert _pump_until(root, lambda: "message" in caught)
    assert caught["message"] == "boom"


def test_run_in_background_reraises_when_no_on_error_given(root):
    def fn(progress_callback):
        raise ValueError("kaboom")

    def on_done(result):
        pass

    run_in_background(root, fn, on_done)
    # No on_error handler -- the error is re-raised inside the `root.after` callback, which Tk
    # reports via `report_callback_exception` rather than propagating back through `update()`.
    seen = {}
    original = root.report_callback_exception

    def capture(exc, val, tb):
        seen["val"] = val

    root.report_callback_exception = capture
    try:
        assert _pump_until(root, lambda: "val" in seen)
    finally:
        root.report_callback_exception = original
    assert isinstance(seen["val"], RuntimeError)
    assert str(seen["val"]) == "kaboom"
