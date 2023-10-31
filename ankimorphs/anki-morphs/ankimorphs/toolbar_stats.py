from .ankimorphs_db import AnkiMorphsDB


class MorphToolbarStats:
    # TODO: adjustable learning interval value?
    def __init__(self) -> None:
        self.unique_morphs = "U: ?"
        self.all_morphs = "A: ?"
        self.update_stats()

    def update_stats(self) -> None:
        try:
            am_db = AnkiMorphsDB()
        except TypeError:
            # The toolbar initiates before the profile
            # when this happens the path to the db can't
            # be found, and we get a type error
            return

        am_db.create_morph_table()

        all_unique_morphs = am_db.con.execute(
            """
            SELECT COUNT(*)
            FROM Morphs
            WHERE highest_learning_interval > 1 AND is_base
            """
        ).fetchone()[0]

        all_morphs = am_db.con.execute(
            """
            SELECT COUNT(*)
            FROM Morphs
            WHERE highest_learning_interval > 1
            """
        ).fetchone()[0]
        am_db.con.close()

        self.unique_morphs = f"U: {all_unique_morphs}"
        self.all_morphs = f"A: {all_morphs}"
