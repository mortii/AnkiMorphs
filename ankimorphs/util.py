# -*- coding: utf-8 -*-
import codecs
import datetime
from os import path
from typing import Any, Dict, List, Optional

from anki.notes import Note
from aqt import mw
from aqt.qt import *
from aqt.utils import showCritical, showInfo

from .morphemes import MorphDb
from .preferences import get_preference

T = TypeVar("T")

###############################################################################
# Global data
###############################################################################
_all_db = None


def get_all_db() -> MorphDb:
    global _all_db

    # Force reload if all.db got deleted
    all_db_path = get_preference("path_all")
    reload = not path.isfile(all_db_path)

    if reload or (_all_db is None):
        _all_db = MorphDb(all_db_path, ignore_errors=True)
    return _all_db


###############################################################################
# Preferences
###############################################################################


# Filters are the 'note filter' option in morphman gui preferences on which note types they want morphman to handle
# If a note is matched multiple times only the first filter in the list will be used
def get_filter(note: Note) -> Optional[dict]:
    note_type = note.note_type()["name"]
    return get_filter_by_type_and_tags(note_type, note.tags)


def get_filter_by_mid_and_tags(mid, tags):
    # type: (Any, List[str]) -> Optional[Dict[...]]
    return get_filter_by_type_and_tags(mw.col.models.get(mid)["name"], tags)


def get_filter_by_type_and_tags(note_type: str, note_tags: List[str]) -> Optional[dict]:
    for note_filter in get_preference("Filter"):
        if (
            note_type == note_filter["Type"] or note_filter["Type"] is None
        ):  # None means 'All note types' is selected
            note_tags = set(note_tags)
            note_filter_tags = set(note_filter["Tags"])
            if note_filter_tags.issubset(
                note_tags
            ):  # required tags have to be subset of actual tags
                return note_filter
    return None  # card did not match (note type and tags) set in preferences GUI


def get_read_enabled_models():
    included_types = set()
    include_all = False
    for _filter in get_preference("Filter"):
        if _filter.get("Read", True):
            if _filter["Type"] is not None:
                included_types.add(_filter["Type"])
            else:
                include_all = True
                break
    return included_types, include_all


def get_modify_enabled_models():
    included_types = set()
    include_all = False
    for _filter in get_preference("Filter"):
        if _filter.get("Modify", True):
            if _filter["Type"] is not None:
                included_types.add(_filter["Type"])
            else:
                include_all = True
                break
    return included_types, include_all


def error_msg(msg):
    showCritical(msg)
    printf(msg)


def info_msg(msg):
    showInfo(msg)
    printf(msg)


def printf(msg):
    txt = f"{datetime.datetime.now()}: {msg}"
    file = codecs.open(get_preference("path_log"), "a", "utf-8")
    file.write(txt + "\r\n")
    file.close()
    print(txt.encode("utf-8"))


def clear_log():
    file = codecs.open(get_preference("path_log"), "w", "utf-8")
    file.close()


###############################################################################
# Qt helper functions
###############################################################################
def mk_btn(txt, _function, parent):
    _btn = QPushButton(txt)
    _btn.clicked.connect(_function)
    parent.addWidget(_btn)
    return _btn
