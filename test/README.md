# Tests

The testing framework is `Pytest` with these plugins:
- [pytest-qt](https://pypi.org/project/pytest-qt/): allows for writing tests for PyQt5, PyQt6, PySide2 and PySide6 applications.
- [pytest-xvfb](https://pypi.org/project/pytest-xvfb/): allows tests to be run without windows popping up during GUI tests or on systems without a display (like a CI).
- [pytest-expect](https://pypi.org/project/pytest-expect/): stores test expectations by saving the set of failing tests, allowing them to be marked as xfail when running them in future.
- [pytest-sugar](https://pypi.org/project/pytest-sugar/): showing failures and errors instantly, adding a progress bar, improving the test results, and making the output look better.
- [pytest-randomly](https://pypi.org/project/pytest-randomly/): randomly order tests and control random.seed.

Some default options are set in the `pyproject.toml` file under the `[tool.pytest.ini_options]` section.

## Running tests

From the project root folder you can run tests with the command `pytest`, and it will automatically gather and run all
the tests found in the `tests` directory.

You can restrict the tests to a specific file by appending the path(s) to the command, e.g:
```
pytest test/tests/recalc_test.py test/tests/review_test.py
```

You can also add "tags" to specific tests and run all the tests that have those tags. This is done by adding the
decorator `@pytest.mark.{tag}`, e.g. `@pytest.mark.external_morphemizers`, and you can then run those tests with the
command:
```
pytest -m external_morphemizers
```

> **Note**: the "tag" also has to be added to the "markers" list in `pyproject.toml` because we run tests with the
> `--strict-markers` argument.

You can specify how many fails the tests should abort after with the `--maxfail` argument, e.g:
```
pytest --maxfail=10
```

The `pytest-randomly` plugin runs the tests in a random order based on a seed. You can specify the seed:
```
pytest --randomly-seed=84903385
```

You can also rerun the last used seed:
```
pytest --randomly-seed=last
```

### Test coverage

Run: `pytest --cov=ankimorphs --cov-report html` and click on `index.html` in `htmlcov/`


## Card collections

Current card collections (test/data/card_collections):
- `lemma_evaluation_lemma_extra_fields_collection.anki2`
  - contains two "known" cards ("the", "man"), and then 9 cards with 4 lemmas and 9 inflections.
  this is used for testing if the inflections are given the scores of their respective lemmas and
  the inflections are skipped on review.
- `some_studied_lemmas_collection.anki2`
  - duplicate of `lemma_evaluation_lemma_extra_fields_collection.anki2`, but one card for each lemma
  has been studied, so the other cards that have those lemmas should contain no unknowns.
- `big_japanese_collection.anki2`
  - monolithic card collection (https://github.com/mortii/anki-decks)
- `ignore_names_txt_collection.anki2`
  - Contains one card that has two names, one of which is found in names.txt
- `known-morphs-collection.anki2`
  - contains one card with 7 morphs, 5 of which are found in the 'known-morphs-valid' directory
- `offset_new_cards_inflection_collection.anki2`
  - Contains two cards, both with "hello".
- `offset_new_cards_lemma_collection.anki2`
  - duplicate of `lemma_evaluation_lemma_extra_fields_collection.anki2`, but has used the `recalc_offset_new_cards` config option
- `some_studied_japanese_collection.anki2`
  - contains three cards:
    - one that has the tag 'am-known-manually'
    - one with a learning interval of 1 day
    - one with a learning interval of 30+ days
- `max_morph_priority_collection.anki2`
  - contains two cards, and uses the frequency file `ja_core_news_sm_freq_inflection_min_occurrence.csv`. One card
  has a morph that is found in the frequency file, the other card does not, which should give it a max morph priority value.

## Engineering and adding collections

1. create a new profile
2. create a new deck
3. create a new note type
4. add cards with the note type to the new deck
5. change the ankimorphs settings to fit the use case and recalc
6. exit anki/close the profile
7. extract the `collection.anki2` file from the profile directory and rename it
8. place the renamed collection file in `test/data/card_collections`
9. create a new config copy in `environment_setup_for_tests.py` and make any necessary adjustments

## Investigating collections

Basically reverse the steps in the section above, i.e:
1. extract the collection file you are interested
2. rename the collection to `collection.anki2`
3. place the file in the profile folder of a new anki profile
4. open the anki profile and the cards should be available for viewing
