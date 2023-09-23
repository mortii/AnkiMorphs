import gzip
import pickle
from functools import partial

from aqt.utils import tooltip

from ankimorphs.exceptions import ProfileNotYetLoadedException
from ankimorphs.morph_db import MorphDb
from ankimorphs.preferences import get_preference as cfg
from ankimorphs.util import mw


def get_stat_path():
    return cfg("path_stats")


def load_stats():
    try:
        file = gzip.open(get_stat_path())
        data = pickle.load(file)
        file.close()
        return data
    except OSError:  # file DNE => create it
        return update_stats()
    except (
        ProfileNotYetLoadedException
    ):  # profile not loaded yet, can't do anything but wait
        return None


def save_stats(data):
    file = gzip.open(get_stat_path(), "wb")
    pickle.dump(data, file, -1)
    file.close()


def update_stats(known_db=None):
    mw.taskman.run_on_main(
        partial(mw.progress.start, label="Updating stats", immediate=True)
    )

    # Load known.db and get total morphemes known
    if known_db is None:
        known_db = MorphDb(cfg("path_known"), ignore_errors=True)

    data = {"totalVariations": len(known_db.db), "totalKnown": len(known_db.groups)}

    save_stats(data)
    mw.taskman.run_on_main(mw.progress.finish)
    return data


def get_unique_morph_toolbar_stats():
    data = load_stats()
    if not data:
        return "U ???", "???"

    unique_morphs = data.get("totalKnown", 0)

    name = f"U: {unique_morphs}"
    details = "U = Known Unique Morphs"
    return name, details


def get_all_morph_toolbar_stats():
    data = load_stats()
    if not data:
        return "A ????", "???"

    unique_morphs = data.get("totalKnown", 0)
    all_morphs = data.get("totalVariations", unique_morphs)

    name = f"A: {all_morphs}"
    details = "A = All Known Morphs"
    return name, details


def on_morph_stats_clicked():
    tooltip("U = Known Unique Morphs<br>A = All Known Morphs")
