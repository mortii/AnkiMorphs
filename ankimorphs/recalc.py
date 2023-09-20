# -*- coding: utf-8 -*-
import csv
import importlib
import io
import pprint
import time
import itertools

from functools import partial
from typing import Dict, Set, Union, Optional

import aqt.main
from anki.models import NotetypeDict, FieldDict
from aqt.utils import tooltip
from aqt.operations import QueryOp

from anki.tags import TagManager
from anki.utils import split_fields, join_fields, strip_html, int_time, field_checksum
from anki.collection import Collection

from ankimorphs.morphemes import Location, Morpheme
from ankimorphs.morphemes import MorphDb, AnkiDeck, getMorphemes
from ankimorphs.morphemizer import getMorphemizerByName
from ankimorphs.util import printf, mw, errorMsg, getFilterByMidAndTags, getReadEnabledModels, getModifyEnabledModels
from ankimorphs.preferences import get_preference, get_preferences
from ankimorphs.util_external import memoize
from ankimorphs.exceptions import NoteFilterFieldsException

from ankimorphs import morph_stats as stats
from ankimorphs import util


@memoize
def get_field_index(field_name, mid) -> Optional[int]:
    """
    Returns the index of a field in a model by its name.
    For example: we have the modelId of the card "Basic".
    The return value might be "1" for fieldName="Front" and
    "2" for fieldName="Back".
    """
    note_type: NotetypeDict = mw.col.models.get(mid)
    fields: dict[str, tuple[int, FieldDict]] = mw.col.models.field_map(note_type)

    try:
        return fields[field_name][1]["ord"]
    except KeyError:
        return None


def extractFieldData(field_name, fields, mid):
    # type: (str, str, str) -> str
    """
    :type field_name: The field name (like u'Expression')
    :type fields: A string containing all field data for the model (created by anki.utils.join_fields())
    :type mid: the modelId depicting the model for the "fields" data
    """
    idx = get_field_index(field_name, mid)
    return strip_html(split_fields(fields)[idx])


@memoize
def getSortFieldIndex(mid):
    return mw.col.models.get(mid)['sortf']


def set_field(model_id: int, all_fields_data: list[str], field_name: str, new_value: str) -> None:
    if field_name != "":
        index = get_field_index(field_name, model_id)
        if index is not None:
            all_fields_data[index] = new_value


def notesToUpdate(last_updated, included_mids):
    # returns list of (nid, mid, flds, guid, tags, maxmat) of
    # cards to analyze
    # ignoring cards that are leeches
    # 
    # leeches are cards have tag "Leech". Anki guarantees a space before and after
    #
    # the logic of the query is:
    #   include cards in the result that are
    #     non-suspended
    #      or
    #     are suspended and are not Leeches
    #
    # we build a predicate that we append to the where clause
    if get_preference('Option_IgnoreSuspendedLeeches'):
        filterSuspLeeches = "(c.queue <> -1 or (c.queue = -1 and not instr(tags, ' leech ')))"
    else:
        filterSuspLeeches = "TRUE"

    #
    # First find the cards to analyze
    #   then find the max maturity of those cards
    query = '''
        WITH notesToUpdate as (
            SELECT distinct n.id AS nid, mid, flds, guid, tags
            FROM notes n JOIN cards c ON (n.id = c.nid)
            WHERE mid IN ({0}) and (n.mod > {1} or c.mod > {1})
               and {2}) -- ignoring suspended leeches
        SELECT nid, mid, flds, guid, tags,
            max(case when ivl=0 and c.type=1 then 0.5 else ivl end) AS maxmat
        FROM notesToUpdate join cards c USING (nid)
        WHERE {2} -- ignoring suspended leeches
        GROUP by nid, mid, flds, guid, tags;
        '''.format(','.join([str(m) for m in included_mids]), last_updated, filterSuspLeeches)

    return mw.col.db.execute(query)


def make_all_db(all_db=None):
    # from . import config
    # importlib.reload(config)
    t_0, db, TAG = time.time(), mw.col.db, mw.col.tags

    mw.taskman.run_on_main(partial(mw.progress.start, label='Prep work for all.db creation', immediate=True))
    # for providing an error message if there is no note that is used for processing
    N_enabled_notes = 0

    if not all_db:
        all_db = MorphDb()

    # Recompute everything if preferences changed.
    last_preferences = all_db.meta.get('last_preferences', {})
    if not last_preferences == get_preferences():
        print("Preferences changed.  Recomputing all_db...")
        all_db = MorphDb()  # Clear all db
        last_updated = 0
    else:
        last_updated = all_db.meta.get('last_updated', 0)

    fidDb = all_db.fidDb()
    locDb = all_db.locDb(recalc=False)  # fidDb() already forces locDb recalc

    included_types, include_all = getReadEnabledModels()
    included_mids = [m['id'] for m in mw.col.models.all() if include_all or m['name'] in included_types]

    notes = notesToUpdate(last_updated, included_mids)
    N_notes = len(notes)

    print("notes to update:", N_notes)

    mw.taskman.run_on_main(mw.progress.finish)
    mw.taskman.run_on_main(partial(mw.progress.start, label='Generating all.db data', max=N_notes, immediate=True))

    for i, (nid, mid, flds, guid, tags, maxmat) in enumerate(notes):

        # if i % 500 == 0:
        mw.taskman.run_on_main(partial(mw.progress.update, value=i))

        ts = TAG.split(tags)
        mid_cfg = getFilterByMidAndTags(mid, ts)
        if mid_cfg is None:
            continue

        N_enabled_notes += 1

        mName = mid_cfg['Morphemizer']
        morphemizer = getMorphemizerByName(mName)

        C = partial(get_preference, model_id=mid)

        if C('ignore maturity'):
            maxmat = 0
        ts, alreadyKnownTag = TAG.split(tags), get_preference('Tag_AlreadyKnown')
        if alreadyKnownTag in ts:
            maxmat = max(maxmat, C('threshold_mature') + 1)

        for field_name in mid_cfg['Fields']:
            try:  # if doesn't have field, continue
                field_value = extractFieldData(field_name, flds, mid)
            except KeyError:
                continue
            except TypeError as error:
                mw.taskman.run_on_main(mw.progress.finish)
                note_type = mw.col.models.get(mid)['name']
                # This gets handled in the on_failure function
                raise NoteFilterFieldsException(field_name, note_type) from error

            assert maxmat is not None, "Maxmat should not be None"

            loc = fidDb.get((nid, guid, field_name), None)
            if not loc:
                loc = AnkiDeck(nid, field_name, field_value, guid, maxmat)
                ms = getMorphemes(morphemizer, field_value, ts)
                if ms:  # TODO: this needed? should we change below too then?
                    locDb[loc] = ms
            else:
                # mats changed -> new loc (new mats), move morphs
                if loc.fieldValue == field_value and loc.maturity != maxmat:
                    newLoc = AnkiDeck(nid, field_name, field_value, guid, maxmat)
                    locDb[newLoc] = locDb.pop(loc)
                # field changed -> new loc, new morphs
                elif loc.fieldValue != field_value:
                    newLoc = AnkiDeck(nid, field_name, field_value, guid, maxmat)
                    ms = getMorphemes(morphemizer, field_value, ts)
                    locDb.pop(loc)
                    locDb[newLoc] = ms

    # printf('Processed %d notes in %f sec' % (N_notes, time.time() - t_0))

    mw.taskman.run_on_main(partial(mw.progress.update, label='Creating all.db objects'))
    old_meta = all_db.meta
    all_db.clear()
    all_db.addFromLocDb(locDb)
    all_db.meta = old_meta
    mw.taskman.run_on_main(mw.progress.finish)
    return all_db


def filterDbByMat(db, mat):
    """Assumes safe to use cached locDb"""
    newDb = MorphDb()
    for loc, ms in db.locDb(recalc=False).items():
        if loc.maturity > mat:
            newDb.addMsL(ms, loc)
    return newDb


def updateNotes(allDb):
    t_0, now, db = time.time(), int_time(), mw.col.db

    TAG = mw.col.tags  # type: TagManager
    ds, note_id_morphman_index = [], {}

    mw.taskman.run_on_main(partial(mw.progress.start, label='Updating data', immediate=True))

    fidDb = allDb.fidDb(recalc=True)
    loc_db = allDb.locDb(recalc=False)  # type: Dict[Location, Set[Morpheme]]

    # read tag names
    compTag, vocabTag, freshTag, notReadyTag, alreadyKnownTag, priorityTag, tooShortTag, tooLongTag, frequencyTag = tagNames = get_preference(
        'Tag_Comprehension'), get_preference('Tag_Vocab'), get_preference('Tag_Fresh'), get_preference('Tag_NotReady'), get_preference(
        'Tag_AlreadyKnown'), get_preference('Tag_Priority'), get_preference('Tag_TooShort'), get_preference('Tag_TooLong'), get_preference('Tag_Frequency')
    TAG.register(tagNames)
    badLengthTag = get_preference('Tag_BadLength')

    # handle secondary databases
    mw.taskman.run_on_main(partial(mw.progress.update, label='Creating seen/known/mature from all.db'))

    seenDb = filterDbByMat(allDb, get_preference('threshold_seen'))
    knownDb = filterDbByMat(allDb, get_preference('threshold_known'))
    matureDb = filterDbByMat(allDb, get_preference('threshold_mature'))

    mw.taskman.run_on_main(partial(mw.progress.update, label='Loading priority.db'))
    priorityDb = MorphDb(get_preference('path_priority'), ignoreErrors=True)

    mw.taskman.run_on_main(partial(mw.progress.update, label='Loading frequency.txt'))

    frequencyListPath = get_preference('path_frequency')
    frequency_map = {}
    frequency_list_exists = False

    try:
        with io.open(frequencyListPath, encoding='utf-8-sig') as csvfile:
            csvreader = csv.reader(csvfile, delimiter="\t")
            rows = [row for row in csvreader]

            if rows[0][0] == "#study_plan_frequency":
                frequency_list_exists = True
                frequency_map = dict(
                    zip([Morpheme(row[0], row[1], row[2], row[3], row[4], row[5]) for row in rows[1:]],
                        itertools.count(0)))
            else:
                frequency_map = dict(zip([row[0] for row in rows], itertools.count(0)))

    except (FileNotFoundError, IndexError) as e:
        pass

    frequencyListLength = len(frequency_map)

    # prefetch cfg for fields
    field_focus_morph = get_preference('Field_FocusMorph')
    field_unknown_count = get_preference('Field_UnknownMorphCount')
    field_unmature_count = get_preference('Field_UnmatureMorphCount')
    field_morph_man_index = get_preference('Field_MorphManIndex')
    field_unknowns = get_preference('Field_Unknowns')
    field_unmatures = get_preference('Field_Unmatures')
    field_unknown_freq = get_preference('Field_UnknownFreq')
    field_focus_morph_pos = get_preference("Field_FocusMorphPos")

    skip_comprehension_cards = get_preference('Option_SkipComprehensionCards')
    skip_fresh_cards = get_preference('Option_SkipFreshVocabCards')

    # Find all morphs that changed maturity and the notes that refer to them.
    last_maturities = allDb.meta.get('last_maturities', {})
    new_maturities = {}
    refresh_notes = set()

    # Recompute everything if preferences changed.
    last_preferences = allDb.meta.get('last_preferences', {})
    if not last_preferences == get_preferences():
        print("Preferences changed.  Updating all notes...")
        last_updated = 0
    else:
        last_updated = allDb.meta.get('last_updated', 0)

    # Todo: Remove this forced 0 once we add checks for other changes like new frequency.txt files.
    last_updated = 0

    # If we're updating everything anyway, clear the notes set.
    if last_updated > 0:
        for m, locs in allDb.db.items():
            maturity_bits = 0
            if seenDb.matches(m):
                maturity_bits |= 1
            if knownDb.matches(m):
                maturity_bits |= 2
            if matureDb.matches(m):
                maturity_bits |= 4

            new_maturities[m] = maturity_bits

            if last_maturities.get(m, -1) != maturity_bits:
                for loc in locs:
                    if isinstance(loc, AnkiDeck):
                        refresh_notes.add(loc.noteId)

    included_types, include_all = getModifyEnabledModels()
    included_mids = [m['id'] for m in mw.col.models.all() if include_all or m['name'] in included_types]

    query = '''
        SELECT n.id as nid, mid, flds, guid, tags, max(c.type) AS maxtype
        FROM notes n JOIN cards c ON (n.id = c.nid)
        WHERE mid IN ({0}) and ( n.mod > {2} or n.id in ({1}) )
        GROUP by nid, mid, flds, guid, tags;
        '''.format(','.join([str(m) for m in included_mids]), ','.join([str(id) for id in refresh_notes]), last_updated)
    query_results = db.execute(query)

    N_notes = len(query_results)

    for i, (nid, mid, flds, guid, tags, maxtype) in enumerate(query_results):
        ts = TAG.split(tags)

        if i % 1000 == 0:
            mw.taskman.run_on_main(partial(mw.progress.update,
                                           label=f"Recalculated {i} of {N_notes} cards ",
                                           value=i,
                                           max=N_notes))

        notecfg = getFilterByMidAndTags(mid, ts)
        if notecfg is None or not notecfg['Modify']:
            continue

        # add bonus for morphs in priority.db and frequency.txt
        C = partial(get_preference, model_id=mid)

        frequencyBonus = C('frequency.txt bonus')
        if C('Option_AlwaysPrioritizeFrequencyMorphs'):
            noPriorityPenalty = C('no priority penalty')
        else:
            noPriorityPenalty = 0
        reinforceNewVocabWeight = C('reinforce new vocab weight')
        priorityDbWeight = C('priority.db weight')
        proper_nouns_known = get_preference('Option_ProperNounsAlreadyKnown')

        # Get all morphemes for note
        morphemes = set()
        for fieldName in notecfg['Fields']:
            try:
                loc = fidDb[(nid, guid, fieldName)]
                morphemes.update(loc_db[loc])
            except KeyError:
                continue

        # Determine un-seen/known/mature and i+N
        unseens, unknowns, unmatures, new_knowns = set(), set(), set(), set()
        for morpheme in morphemes:
            if proper_nouns_known and morpheme.isProperNoun():
                continue
            morpheme = morpheme.deinflected()
            if not seenDb.matches(morpheme):
                unseens.add(morpheme)
            if not knownDb.matches(morpheme):
                unknowns.add(morpheme)
            if not matureDb.matches(morpheme):
                unmatures.add(morpheme)
                if knownDb.matches(morpheme):
                    new_knowns.add(morpheme)

        # Determine MMI - Morph Man Index
        morphemes_amount = len(morphemes)
        unseens_amount = len(unseens)
        unknows_amount = len(unknowns)
        unmatures_amount = len(unmatures)

        # Set the mmi (due) on all cards to max by default to prevent buggy cards to showing up first
        # if a card already has this mmi (due) it won't update, so this will not have a negative impact on syncing.
        # card.due is converted to a signed 32-bit integer on the backend, so max value is 2147483647 before overflow
        morphman_index = 2147483647
        note_id_morphman_index[nid] = morphman_index

        # Bail early if card has more than 3 unknown morphs for lite update
        # TODO: Add to preferences GUI to make it adjustable
        if unknows_amount > 3:
            continue
        elif skip_comprehension_cards and unknows_amount == 0:
            continue

        is_priority = False
        is_frequency = False
        unknown_morph = None
        morph_frequency = 0
        usefulness = 0

        for unknown_morph in unknowns:
            morph_frequency += allDb.frequency(unknown_morph)

            if priorityDb.frequency(unknown_morph) > 0:
                is_priority = True
                usefulness += priorityDbWeight

            if frequency_list_exists:
                focus_morph_index = frequency_map.get(unknown_morph, -1)
            else:
                focus_morph_index = frequency_map.get(unknown_morph.base, -1)

            if focus_morph_index >= 0:
                is_frequency = True

                # The bigger this number, the lower mmi becomes
                usefulness += int(round(frequencyBonus * (1 - focus_morph_index / frequencyListLength)))

        # average frequency of unknowns (ie. how common the word is within your collection)
        F_k_avg = morph_frequency // unknows_amount if unknows_amount > 0 else morph_frequency
        usefulness += F_k_avg

        # add bonus for studying recent learned knowns (reinforce)
        for morpheme in new_knowns:
            locs = knownDb.getMatchingLocs(morpheme)
            if locs:
                ivl = min(1, max(loc.maturity for loc in locs))
                # TODO: maybe average this so it doesnt favor long sentences
                usefulness += reinforceNewVocabWeight // ivl

        if any(morpheme.pos == '動詞' for morpheme in unknowns):  # FIXME: this isn't working???
            usefulness += C('verb bonus')

        usefulness = 99999 - min(99999, usefulness)

        # difference from optimal length range (too little context vs long sentence)
        lenDiffRaw = min(morphemes_amount - C('min good sentence length'),
                         max(0, morphemes_amount - C('max good sentence length')))
        lenDiff = min(9, abs(lenDiffRaw))

        # Fill in various fields/tags on the note based on cfg
        fs = split_fields(flds)

        # clear any 'special' tags, the appropriate will be set in the next few lines
        ts = [t for t in ts if t not in (
            notReadyTag, compTag, vocabTag, freshTag)]

        # apply penalty for cards that aren't prioritized for learning
        if not (is_priority or is_frequency):
            usefulness += noPriorityPenalty

        # determine card type
        if unmatures_amount == 0:  # sentence comprehension card, m+0
            ts.append(compTag)
            if skip_comprehension_cards:
                usefulness += 1000000  # Add a penalty to put these cards at the end of the queue
        elif unknows_amount == 1:  # new vocab card, k+1
            ts.append(vocabTag)
            if maxtype == 0:  # Only update focus fields on 'new' card types.
                set_field(mid, fs, field_focus_morph, unknown_morph.base)
                set_field(mid, fs, field_focus_morph_pos, unknown_morph.pos)
        elif unknows_amount > 1:  # M+1+ and K+2+
            ts.append(notReadyTag)
            if maxtype == 0:  # Only update focus fields on 'new' card types.
                set_field(mid, fs, field_focus_morph, ', '.join([u.base for u in unknowns]))
                set_field(mid, fs, field_focus_morph_pos, ', '.join([u.pos for u in unknowns]))
        else:  # only case left: we have k+0, but m+1 or higher, so this card does not introduce a new vocabulary -> card for newly learned morpheme
            ts.append(freshTag)
            if skip_fresh_cards:
                usefulness += 1000000  # Add a penalty to put these cards at the end of the queue
            if maxtype == 0:  # Only update focus fields on 'new' card types.
                set_field(mid, fs, field_focus_morph, ', '.join([u.base for u in unmatures]))
                set_field(mid, fs, field_focus_morph_pos, ', '.join([u.pos for u in unmatures]))

        # calculate mmi
        morphman_index = 100000 * unknows_amount + 1000 * lenDiff + int(round(usefulness))
        if C('set due based on mmi'):
            note_id_morphman_index[nid] = morphman_index

        # set type agnostic fields
        set_field(mid, fs, field_unknown_count, '%d' % unknows_amount)
        set_field(mid, fs, field_unmature_count, '%d' % unmatures_amount)
        set_field(mid, fs, field_morph_man_index, '%d' % morphman_index)
        set_field(mid, fs, field_unknowns, ', '.join(u.base for u in unknowns))
        set_field(mid, fs, field_unmatures,
                  ', '.join(u.base for u in unmatures))
        set_field(mid, fs, field_unknown_freq, '%d' % F_k_avg)

        # remove deprecated tag
        if badLengthTag is not None and badLengthTag in ts:
            ts.remove(badLengthTag)

        # other tags
        if priorityTag in ts:
            ts.remove(priorityTag)
        if is_priority:
            ts.append(priorityTag)

        if frequencyTag in ts:
            ts.remove(frequencyTag)
        if is_frequency:
            ts.append(frequencyTag)

        if tooShortTag in ts:
            ts.remove(tooShortTag)
        if lenDiffRaw < 0:
            ts.append(tooShortTag)

        if tooLongTag in ts:
            ts.remove(tooLongTag)
        if lenDiffRaw > 0:
            ts.append(tooLongTag)

        # remove unnecessary tags
        if not get_preference('Option_SetNotRequiredTags'):
            unnecessary = [priorityTag, tooShortTag, tooLongTag]
            ts = [tag for tag in ts if tag not in unnecessary]

        # update sql db
        tags_ = TAG.join(ts)
        flds_ = join_fields(fs)
        if flds != flds_ or tags != tags_:  # only update notes that have changed
            csum = field_checksum(fs[0])
            sfld = strip_html(fs[getSortFieldIndex(mid)])
            ds.append(
                (tags_, flds_, sfld, csum, now, mw.col.usn(), nid))

    mw.taskman.run_on_main(partial(mw.progress.update, label='Updating anki database...'))
    mw.col.db.executemany(
        'update notes set tags=?, flds=?, sfld=?, csum=?, mod=?, usn=? where id=?', ds)

    # Now reorder new cards based on MMI
    mw.taskman.run_on_main(partial(mw.progress.update, label='Updating new card ordering...'))
    ds = []

    # "type = 0": new cards
    # "type = 1": learning cards [is supposed to be learning: in my case no learning card had this type]
    # "type = 2": review cards
    for (cid, nid, due) in db.execute('select id, nid, due from cards where type = 0'):
        if nid in note_id_morphman_index:  # owise it was disabled
            due_ = note_id_morphman_index[nid]
            if due != due_:  # only update cards that have changed
                ds.append((due_, now,
                           mw.col.usn(), cid))

    mw.col.db.executemany(
        'update cards set due=?, mod=?, usn=? where id=?', ds)

    mw.taskman.run_on_main(mw.reset)

    allDb.meta['last_preferences'] = get_preferences()
    allDb.meta['last_maturities'] = new_maturities
    allDb.meta['last_updated'] = int(time.time() + 0.5)

    # printf('Updated %d notes in %f sec' % (N_notes, time.time() - t_0))

    if get_preference('saveDbs'):
        mw.taskman.run_on_main(partial(mw.progress.update, label='Saving all/seen/known/mature dbs'))
        allDb.save(get_preference('path_all'))
        seenDb.save(get_preference('path_seen'))
        knownDb.save(get_preference('path_known'))
        matureDb.save(get_preference('path_mature'))
        # printf('Updated %d notes + saved dbs in %f sec' % (N_notes, time.time() - t_0))

    mw.taskman.run_on_main(mw.progress.finish)
    return knownDb


def main():

    print(f"recalc main pre, mw.inMainThread(): {mw.inMainThread()}")

    op = QueryOp(
        parent=mw,
        op=main_background_op,
        success=lambda t: tooltip("Finished Recalc"),  # t = return value of the op
    )

    # if with_progress() is not called, no progress window will be shown.
    # note: QueryOp.with_progress() was broken until Anki 2.1.50
    op.with_progress().run_in_background()
    op.failure(on_failure)


def main_background_op(collection: Collection):
    assert mw is not None

    print("running main")


    mw.taskman.run_on_main(partial(mw.progress.start, label='Loading existing all.db', immediate=True))
    current_all_db = util.get_all_db() if get_preference('loadAllDb') else None
    mw.taskman.run_on_main(mw.progress.finish)

    print("running main2")


    # update all.db
    allDb = make_all_db(current_all_db)

    print("running main3")


    # merge in external.db
    mw.taskman.run_on_main(partial(mw.progress.start, label='Merging ext.db', immediate=True))
    ext = MorphDb(get_preference('path_ext'), ignoreErrors=True)
    allDb.merge(ext)
    mw.taskman.run_on_main(mw.progress.finish)

    print("running main3.5")


    # TODO: 'Known' is a horrendously bad name for this db... it actually contains every morph that has ever been
    #  seen, so it is super misleading... rename it to something better like 'learned' or 'unmature'
    knownDb = updateNotes(allDb)

    print("running main4")


    # update stats and refresh display
    stats.update_stats(knownDb)

    print("running main5")


    mw.taskman.run_on_main(mw.toolbar.draw)

    # set global allDb
    util._allDb = allDb

    print("running main6")



def on_failure(_exception: Union[Exception, NoteFilterFieldsException]):
    if type(_exception) is NoteFilterFieldsException:
        errorMsg(
            f'Did not find a field called "{_exception.field_name}" in the Note Type "{_exception.note_type}"\n\n'
            f'Field names are case-sensitive!\n\n'
            f'Read the guide for more info:\n'
            f'https://mortii.github.io/MorphMan/user_guide/setup/preferences/note-filter.html '
        )
    else:
        raise _exception
