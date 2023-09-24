# TODO: importlib is seemingly used to patch over and disguise veeeeery bad bugs... remove its usages and fix the bugs
import importlib

from aqt import gui_hooks, mw
from aqt.browser import Browser
from aqt.qt import QAction, QMenu  # pylint:disable=no-name-in-module
from aqt.reviewer import Reviewer
from aqt.utils import tooltip

from ankimorphs import (
    browser_utils,
    graphs,
    manager,
    morph_stats,
    preferencesDialog,
    readability,
    recalc,
    reviewing_utils,
)
from ankimorphs.mecab_wrapper import get_morphemes_mecab
from ankimorphs.morph_db import MorphDb
from ankimorphs.preferences import get_preference

# A bug in the anki module leads to cyclic imports if these are placed higher
import anki.stats  # isort:skip pylint:disable=wrong-import-order
from anki import hooks  # isort:skip pylint:disable=wrong-import-order

TOOL_MENU = "morphman_tool_menu"
BROWSE_MENU = "morphman_browse_menu"
CONTEXT_MENU = "morphman_context_menu"


def main():
    # Support anki version 2.1.50 and above
    # Hooks should be placed in the order they are executed!

    # Adds the 'U: A:' to the toolbar
    gui_hooks.top_toolbar_did_init_links.append(add_morph_stats_to_toolbar)

    # TODO: create dbs if they don't exist to prevent bugs
    # gui_hooks.profile_did_open.append(init_dbs)

    # Update the toolbar stats
    gui_hooks.profile_did_open.append(redraw_toolbar_wrapper)

    gui_hooks.profile_did_open.append(init_tool_menu_and_actions)
    gui_hooks.profile_did_open.append(replace_reviewer_functions)
    gui_hooks.profile_did_open.append(init_browser_menus_and_actions)

    # See morph stats by holding 'Shift'-key while pressing 'Stats' in toolbar
    gui_hooks.profile_did_open.append(add_morph_stats_to_ease_graph)

    # This stores the focus morphs seen today, necessary for the respective skipping option to work
    gui_hooks.reviewer_did_answer_card.append(mark_morph_seen_wrapper)


def redraw_toolbar_wrapper():
    # wrapping this makes testing easier because we don't have to mock mw
    mw.toolbar.draw()


def init_tool_menu_and_actions():
    for action in mw.form.menuTools.actions():
        if action.objectName() == TOOL_MENU:
            return  # prevents duplicate menus on profile-switch

    recalc_action = create_recalc_action()
    preferences_action = create_preferences_action()
    database_manager_action = create_database_manager_action()
    readability_analyzer_action = create_readability_analyzer_action()

    morphman_tool_menu = create_morphman_tool_menu()
    morphman_tool_menu.addAction(recalc_action)
    morphman_tool_menu.addAction(preferences_action)
    morphman_tool_menu.addAction(database_manager_action)
    morphman_tool_menu.addAction(readability_analyzer_action)

    test_action = create_test_action()
    morphman_tool_menu.addAction(test_action)


def init_browser_menus_and_actions() -> None:
    view_action = create_view_morphs_action()
    learn_now_action = create_learn_now_action()
    browse_morph_action = create_browse_morph_action()
    already_known_tagger_action = create_already_known_tagger_action()

    def setup_browser_menu(_browser: Browser):
        browser_utils.browser = _browser

        for action in browser_utils.browser.form.menubar.actions():
            if action.objectName() == BROWSE_MENU:
                return  # prevents duplicate menus on profile-switch

        morphman_browse_menu = QMenu("MorphMan", mw)
        morphman_browse_menu_creation_action = (
            browser_utils.browser.form.menubar.addMenu(morphman_browse_menu)
        )
        morphman_browse_menu_creation_action.setObjectName(BROWSE_MENU)

        morphman_browse_menu.addAction(view_action)
        morphman_browse_menu.addAction(learn_now_action)
        morphman_browse_menu.addAction(browse_morph_action)
        morphman_browse_menu.addAction(already_known_tagger_action)

    def setup_context_menu(_browser: Browser, context_menu: QMenu):
        for action in context_menu.actions():
            if action.objectName() == CONTEXT_MENU:
                return  # prevents duplicate menus on profile-switch

        context_menu_creation_action = context_menu.insertSeparator(view_action)
        context_menu.addAction(view_action)
        context_menu.addAction(learn_now_action)
        context_menu.addAction(browse_morph_action)
        context_menu.addAction(already_known_tagger_action)
        context_menu_creation_action.setObjectName(CONTEXT_MENU)

    gui_hooks.browser_menus_did_init.append(setup_browser_menu)

    gui_hooks.browser_will_show_context_menu.append(setup_context_menu)


def mark_morph_seen_wrapper(reviewer: Reviewer, card, ease):
    reviewing_utils.mark_morph_seen(card.note())


def replace_reviewer_functions() -> None:
    # This skips the cards the user specified in preferences GUI
    Reviewer.nextCard = hooks.wrap(
        Reviewer.nextCard, reviewing_utils.my_next_card, "around"
    )

    # Automatically highlights morphs on cards if the respective note stylings are present
    hooks.field_filter.append(reviewing_utils.highlight)

    Reviewer._shortcutKeys = hooks.wrap(
        Reviewer._shortcutKeys, reviewing_utils.my_reviewer_shortcut_keys, "around"
    )


def add_morph_stats_to_toolbar(links, toolbar) -> None:
    unique_name, unique_details = morph_stats.get_unique_morph_toolbar_stats()
    all_name, all_details = morph_stats.get_all_morph_toolbar_stats()
    links.append(
        toolbar.create_link(
            "morph",
            unique_name,
            morph_stats.on_morph_stats_clicked,
            tip=unique_details,
            id="morph",
        )
    )
    links.append(
        toolbar.create_link(
            "morph2",
            all_name,
            morph_stats.on_morph_stats_clicked,
            tip=all_details,
            id="morph2",
        )
    )


def add_morph_stats_to_ease_graph() -> None:
    anki.stats.CollectionStats.easeGraph = hooks.wrap(
        anki.stats.CollectionStats.easeGraph, morph_graphs_wrapper, "around"
    )


def create_morphman_tool_menu() -> QMenu:
    assert mw is not None
    morphman_tool_menu = QMenu("MorphMan", mw)
    morphman_tool_menu_creation_action = mw.form.menuTools.addMenu(morphman_tool_menu)
    morphman_tool_menu_creation_action.setObjectName(TOOL_MENU)
    return morphman_tool_menu


def create_recalc_action() -> QAction:
    action = QAction("&Recalc", mw)
    action.setStatusTip("Recalculate all.db, note fields, and new card ordering")
    action.setShortcut("Ctrl+M")
    action.triggered.connect(recalc.main)
    return action


def create_preferences_action() -> QAction:
    action = QAction("&Preferences", mw)
    action.setStatusTip("Change inspected cards, fields and tags")
    action.setShortcut("Ctrl+O")
    action.triggered.connect(preferencesDialog.main)
    return action


def create_database_manager_action() -> QAction:
    action = QAction("&Database Manager", mw)
    action.setStatusTip(
        "Open gui manager to inspect, compare, and analyze MorphMan DBs"
    )
    action.setShortcut("Ctrl+D")
    action.triggered.connect(manager.main)
    return action


def create_readability_analyzer_action() -> QAction:
    action = QAction("Readability &Analyzer", mw)
    action.setStatusTip("Check readability and build frequency lists")
    action.setShortcut("Ctrl+A")
    action.triggered.connect(readability.main)
    return action


def create_learn_now_action():
    action = QAction("&Learn Card Now", mw)
    action.setStatusTip("Immediately review the selected new cards")
    action.setShortcut(get_preference("set learn now key"))
    action.triggered.connect(browser_utils.run_learn_card_now)
    return action


def create_browse_morph_action():
    action = QAction("&Browse Same Morphs", mw)
    action.setStatusTip("Browse all notes containing the morphs from selected notes")
    action.setShortcut(get_preference("browse same focus key"))
    action.triggered.connect(browser_utils.run_browse_morph)
    return action


def create_view_morphs_action() -> QAction:
    action = QAction("&View Morphemes", mw)
    action.setStatusTip("View Morphemes for selected note")
    action.setShortcut(get_preference("set view morphemes key"))
    action.triggered.connect(browser_utils.run_view_morphs)
    return action


def create_already_known_tagger_action():
    action = QAction("&Tag As Known", mw)
    action.setStatusTip("Tag all selected cards as already known")
    action.setShortcut(get_preference("set known and skip key"))
    action.triggered.connect(browser_utils.run_already_known_tagger)
    return action


def create_test_action() -> QAction:
    action = QAction("&Test", mw)
    action.setStatusTip("Recalculate all.db, note fields, and new card ordering")
    action.setShortcut("Ctrl+T")
    action.triggered.connect(test_function)
    return action


def morph_graphs_wrapper(*args, **kwargs):
    importlib.reload(graphs)
    return graphs.morph_graphs(args, kwargs)


def test_function() -> None:
    # known_db = MorphDb(get_preference("path_known"), ignore_errors=True)
    #
    # for group in known_db.groups.values():
    #     for _morph in group:
    #         print("morph: ", _morph.inflected)
    #     print("group break\n")

    mw.toolbar.draw()


main()
