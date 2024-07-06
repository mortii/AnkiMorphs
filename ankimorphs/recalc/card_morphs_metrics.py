from ..ankimorphs_config import AnkiMorphsConfig
from ..morpheme import Morpheme


class CardMorphsMetrics:
    __slots__ = (
        "all_morphs",
        "unknown_morphs",
        "num_learning_morphs",
        "has_learning_morphs",
        "total_priority_unknown_morphs",
        "total_priority_all_morphs",
    )

    def __init__(
        self,
        am_config: AnkiMorphsConfig,
        card_id: int,
        card_morph_map_cache: dict[int, list[Morpheme]],
        morph_priorities: dict[str, int],
    ) -> None:
        self.all_morphs: list[Morpheme] = []
        self.unknown_morphs: list[Morpheme] = []
        self.num_learning_morphs: int = 0
        self.has_learning_morphs: bool = False
        self.total_priority_unknown_morphs = 0
        self.total_priority_all_morphs = 0

        try:
            card_morphs: list[Morpheme] = card_morph_map_cache[card_id]
            self.all_morphs = card_morphs
            self._process(am_config, morph_priorities, card_morphs)
        except KeyError:
            # card does not have morphs or is buggy in some way
            pass

    def _process(
        self,
        am_config: AnkiMorphsConfig,
        morph_priorities: dict[str, int],
        card_morphs: list[Morpheme],
    ) -> None:

        # setting default avoid an extra if statement
        default_morph_priority = len(morph_priorities) + 1

        if am_config.evaluate_morph_lemma:
            self._process_using_lemma(
                am_config, default_morph_priority, morph_priorities, card_morphs
            )
        else:
            self._process_using_inflection(
                am_config, default_morph_priority, morph_priorities, card_morphs
            )

        if self.num_learning_morphs > 0:
            self.has_learning_morphs = True

    def _process_using_lemma(
        self,
        am_config: AnkiMorphsConfig,
        default_morph_priority: int,
        morph_priorities: dict[str, int],
        card_morphs: list[Morpheme],
    ) -> None:

        for morph in card_morphs:
            assert morph.highest_lemma_learning_interval is not None

            morph_priority = default_morph_priority

            key = morph.lemma + morph.lemma
            if key in morph_priorities:
                morph_priority = morph_priorities[key]

            self.total_priority_all_morphs += morph_priority

            if morph.highest_lemma_learning_interval == 0:
                self.unknown_morphs.append(morph)
                self.total_priority_unknown_morphs += morph_priority
            elif (
                morph.highest_lemma_learning_interval
                < am_config.interval_for_known_morphs
            ):
                self.num_learning_morphs += 1

    def _process_using_inflection(
        self,
        am_config: AnkiMorphsConfig,
        default_morph_priority: int,
        morph_priorities: dict[str, int],
        card_morphs: list[Morpheme],
    ) -> None:

        for morph in card_morphs:
            assert morph.highest_inflection_learning_interval is not None

            morph_priority = default_morph_priority

            key = morph.lemma + morph.inflection
            if key in morph_priorities:
                morph_priority = morph_priorities[key]

            self.total_priority_all_morphs += morph_priority

            if morph.highest_inflection_learning_interval == 0:
                self.unknown_morphs.append(morph)
                self.total_priority_unknown_morphs += morph_priority
            elif (
                morph.highest_inflection_learning_interval
                < am_config.interval_for_known_morphs
            ):
                self.num_learning_morphs += 1

    @staticmethod
    def get_unknown_inflections(
        card_morph_map_cache: dict[int, list[Morpheme]],
        card_id: int,
    ) -> set[str]:
        card_unknown_morphs: set[str] = set()
        try:
            card_morphs: list[Morpheme] = card_morph_map_cache[card_id]
            for morph in card_morphs:
                assert morph.highest_inflection_learning_interval is not None
                if morph.highest_inflection_learning_interval == 0:
                    card_unknown_morphs.add(morph.inflection)
                    # we don't want to do anything to cards that have multiple unknown morphs
                    if len(card_unknown_morphs) > 1:
                        break
        except KeyError:
            pass  # card does not have morphs or is buggy in some way

        return card_unknown_morphs

    @staticmethod
    def get_unknown_lemmas(
        card_morph_map_cache: dict[int, list[Morpheme]],
        card_id: int,
    ) -> set[str]:
        card_unknown_morphs: set[str] = set()
        try:
            card_morphs: list[Morpheme] = card_morph_map_cache[card_id]
            for morph in card_morphs:
                assert morph.highest_lemma_learning_interval is not None
                if morph.highest_lemma_learning_interval == 0:
                    card_unknown_morphs.add(morph.lemma)
                    # we don't want to do anything to cards that have multiple unknown morphs
                    if len(card_unknown_morphs) > 1:
                        break
        except KeyError:
            pass  # card does not have morphs or is buggy in some way

        return card_unknown_morphs
