"""Bounded ownership of immutable inputs across existing refresh windows.

This is for the GIS/context readers, not a replacement refresh policy. All
non-window arguments remain the identity, and readers run outside the lock.
"""
from collections import OrderedDict, namedtuple
from concurrent.futures import Future
from dataclasses import dataclass, field
from functools import wraps
from inspect import signature
from threading import RLock, get_ident


_MISSING = object()
_CacheInfo = namedtuple('CacheInfo', 'hits misses maxsize currsize')
_MAXSIZE = 8


@dataclass(eq=False)
class _InputSlot:
    window: int
    value: object = _MISSING
    pending: Future = field(default_factory=Future)
    owner_thread: int = field(default_factory=get_ident)


def cache_input_windows(*, window_index: int):
    """Retain at most one completed window per existing reader identity.

    The eight-slot bound includes unfinished admissions. Replaced, evicted or
    cleared slots cannot be restored by an older in-flight completion. Active
    callers still own their results. Same-identity/window followers await one
    read outside the lock; unrelated identities and newer windows proceed.
    """
    def decorate(reader):
        parameters = signature(reader)
        entries = OrderedDict()
        lock = RLock()
        hits = misses = 0

        @wraps(reader)
        def cached(*args, **kwargs):
            nonlocal hits, misses
            if kwargs:
                bound = parameters.bind(*args, **kwargs)
                bound.apply_defaults()
                values = tuple(bound.arguments.values())
            else:
                values = args
            window = values[window_index]
            key = values[:window_index] + values[window_index + 1:]
            pending = None
            with lock:
                slot = entries.get(key)
                if slot is not None and window == slot.window:
                    entries.move_to_end(key)
                    if slot.value is not _MISSING:
                        hits += 1
                        return slot.value
                    if slot.owner_thread == get_ident():
                        # A reader callback may reenter its own cache. Preserve
                        # that independent read rather than waiting on itself.
                        slot = None
                    else:
                        pending = slot.pending
                elif slot is None or window > slot.window:
                    # Retire the previous cache-owned object immediately.
                    # An active operation can continue to own that object.
                    slot = _InputSlot(window)
                    entries[key] = slot
                    entries.move_to_end(key)
                    while len(entries) > _MAXSIZE:
                        entries.popitem(last=False)
                else:
                    # A delayed older request may finish for its caller, but
                    # cannot replace the already admitted newer window.
                    slot = None
                misses += 1
            if pending is not None:
                return pending.result()
            try:
                result = reader(*args, **kwargs)
            except BaseException as error:
                with lock:
                    if slot is not None and entries.get(key) is slot:
                        del entries[key]
                if slot is not None:
                    slot.pending.set_exception(error)
                raise
            with lock:
                if slot is not None:
                    if entries.get(key) is slot and slot.value is _MISSING:
                        slot.value = result
                        entries.move_to_end(key)
            if slot is not None:
                slot.pending.set_result(result)
            return result

        def cache_clear():
            nonlocal hits, misses
            with lock:
                entries.clear()
                hits = misses = 0

        def cache_info():
            with lock:
                return _CacheInfo(hits, misses, _MAXSIZE,
                    sum(slot.value is not _MISSING for slot in entries.values()))

        cached.cache_clear = cache_clear
        cached.cache_info = cache_info
        cached.cache_parameters = lambda: {'maxsize': _MAXSIZE, 'typed': False}
        return cached
    return decorate
