"""Operation-scoped failure feedback without a transient loading element.

Ordinary phases and successful completion render no UI. Existing callers retain
an operation scope so source acquisition, snapshots and exception handling keep
working. Failed/unavailable results still use their translated messages.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

import streamlit as st

from .i18n import normalize_language, translate

_ACTIVE: ContextVar[LoadingFeedback | None] = ContextVar("speedlocal_loading_feedback", default=None)


class LoadingFeedback:
    """Keep failure handling in its reserved slot; normal work adds no element."""

    def __init__(self, slot: Any, language: str) -> None:
        self._slot = slot
        self._language = normalize_language(language)
        self._state = "running"
        self._last_failure: tuple[str, str] | None = None
        self._map_expected = False

    @property
    def map_expected(self) -> bool:
        return self._map_expected

    def _failure(self, message_id: str) -> None:
        identity = (self._state, message_id)
        if identity == self._last_failure:
            return
        self._last_failure = identity
        with self._slot.container():
            render = st.error if self._state == "error" else st.warning
            render(translate(message_id, self._language))

    def phase(self, message_id: str, *, detail: str = "", completed: int | None = None, total: int | None = None) -> None:
        if self._state != "running":
            raise RuntimeError("Loading phases cannot change after the operation has finished")
        if completed is not None or total is not None:
            if type(completed) is not int or type(total) is not int or total <= 0 or not 0 <= completed <= total:
                raise ValueError("Completed and total must be paired valid integer step counts")

    def map_html(self, html: str) -> str:
        """Leave the complete map document and its payload unchanged."""
        if self._state != "running":
            raise RuntimeError("Map HTML must be registered before finishing the operation")
        if not isinstance(html, str):
            raise TypeError("Map HTML must be a string")
        self._map_expected = True
        return html

    def finish(self) -> None:
        if self._state != "running":
            return
        if not self._map_expected:
            self.unavailable()
            return
        self._state = "complete"

    def unavailable(self) -> None:
        self._state = "unavailable"
        self._failure("loading.unavailable")

    def error(self) -> None:
        self._state = "error"
        self._failure("loading.failed")


@contextmanager
def active_loading(feedback: LoadingFeedback) -> Iterator[LoadingFeedback]:
    """Expose the operation to UI helpers, restoring the prior scope on exit."""
    token = _ACTIVE.set(feedback)
    try:
        yield feedback
    finally:
        _ACTIVE.reset(token)


def current_loading() -> LoadingFeedback | None:
    return _ACTIVE.get()
