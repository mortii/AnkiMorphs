# -*- coding: utf-8 -*-
import codecs
import datetime
from os import path
from typing import Any, Dict, List, Optional

from aqt import mw
from aqt.qt import *
from aqt.utils import showCritical, showInfo

from anki.notes import Note

from .preferences import get_preference
from .morphemes import MorphDb

T = TypeVar("T")

###############################################################################
# Global data
###############################################################################
_allDb = None


def get_all_db() -> MorphDb:
    global _allDb

    # Force reload if all.db got deleted
    all_db_path = get_preference("path_all")
    reload = not path.isfile(all_db_path)

    if reload or (_allDb is None):
        from .morphemes import MorphDb

        _allDb = MorphDb(all_db_path, ignoreErrors=True)
    return _allDb


###############################################################################
# Preferences
###############################################################################


# Filters are the 'note filter' option in morphman gui preferences on which note types they want morphman to handle
# If a note is matched multiple times only the first filter in the list will be used
def get_filter(note: Note) -> Optional[dict]:
    note_type = note.note_type()["name"]
    return get_filter_by_type_and_tags(note_type, note.tags)


def getFilterByMidAndTags(mid, tags):
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


def getReadEnabledModels():
    included_types = set()
    include_all = False
    for f in get_preference("Filter"):
        if f.get("Read", True):
            if f["Type"] is not None:
                included_types.add(f["Type"])
            else:
                include_all = True
                break
    return included_types, include_all


def getModifyEnabledModels():
    included_types = set()
    include_all = False
    for f in get_preference("Filter"):
        if f.get("Modify", True):
            if f["Type"] is not None:
                included_types.add(f["Type"])
            else:
                include_all = True
                break
    return included_types, include_all


###############################################################################
# Logging and MsgBoxes
###############################################################################
def errorMsg(msg):
    showCritical(msg)
    printf(msg)


def infoMsg(msg):
    showInfo(msg)
    printf(msg)


def printf(msg):
    txt = "%s: %s" % (datetime.datetime.now(), msg)
    f = codecs.open(get_preference("path_log"), "a", "utf-8")
    f.write(txt + "\r\n")
    f.close()
    print(txt.encode("utf-8"))


def clearLog():
    f = codecs.open(get_preference("path_log"), "w", "utf-8")
    f.close()


###############################################################################
# Qt helper functions
###############################################################################
def mkBtn(txt, f, parent):
    b = QPushButton(txt)
    b.clicked.connect(f)
    parent.addWidget(b)
    return b
