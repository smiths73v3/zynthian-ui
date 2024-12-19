#!/usr/bin/python3
# -*- coding: utf-8 -*-
import logging
from os import listdir
from os.path import isfile, join
import time
import signal
import random
from bisect import bisect
from copy import deepcopy
from functools import partial
import multiprocessing as mp
from threading import Thread, RLock, Event
import liblo
from threading import Timer

from zyncoder.zyncore import lib_zyncore
from zyngine.zynthian_signal_manager import zynsigman
from zynconf import ServerPort
from zyngine.zynthian_engine_sooperlooper import *
from .zynthian_ctrldev_base import zynthian_ctrldev_base
from .zynthian_ctrldev_base_extended import (
    RunTimer,
    KnobSpeedControl,
    ButtonTimer,
    CONST,
)
from .zynthian_ctrldev_akai_apc_key25_mk2_feedback_leds import FeedbackLEDs
from .zynthian_ctrldev_akai_apc_key25_mk2_colors import COLORS
from .zynthian_ctrldev_akai_apc_key25_mk2_brights import (BRIGHTS, LED_BRIGHTS)
from .zynthian_ctrldev_akai_apc_key25_mk2_buttons import BUTTONS

from typing import Dict, Any, Callable
from itertools import chain, islice
# from collections import defaultdict

import functools

COLS = 8
ROWS = 5
KNOBS_PER_ROW = 4
# LED states
LED_ON = 1
EV_NOTE_ON = 0x09
EV_NOTE_OFF = 0x08
EV_CC = 0x0B


TRACK_COMMANDS = [2, 6, 7, 8, 13, 12, 16, 14]
TRACK_LEVELS = [
    "in_peak_meter",
    "rec_thresh",
    "input_gain",
    "wet",
    "dry",
    "feedback",
    "none",
    "none",
]
LEVEL_COLORS = [
    COLORS.COLOR_RED,
    COLORS.COLOR_RED,
    COLORS.COLOR_LIME,
    COLORS.COLOR_BLUE,
    COLORS.COLOR_DARK_GREY,
    COLORS.COLOR_PURPLE,
    COLORS.COLOR_WHITE,
    COLORS.COLOR_WHITE,
]
# @todo factor out this from here and zynthian_engine_sooperlooper?
# ------------------------------------------------------------------------------
# Sooper Looper State Codes
# ------------------------------------------------------------------------------

# From sooperlooper engine
SL_STATE_UNKNOWN = -1
SL_STATE_OFF = 0
SL_STATE_REC_STARTING = 1
SL_STATE_RECORDING = 2
SL_STATE_REC_STOPPING = 3
SL_STATE_PLAYING = 4
SL_STATE_OVERDUBBING = 5
SL_STATE_MULTIPLYING = 6
SL_STATE_INSERTING = 7
SL_STATE_REPLACING = 8
SL_STATE_DELAYING = 9
SL_STATE_MUTED = 10
SL_STATE_SCRATCHING = 11
SL_STATE_PLAYING_ONCE = 12
SL_STATE_SUBSTITUTING = 13
SL_STATE_PAUSED = 14
SL_STATE_UNDO_ALL = 15
SL_STATE_TRIGGER_PLAY = 16
SL_STATE_UNDO = 17
SL_STATE_REDO = 18
SL_STATE_REDO_ALL = 19
SL_STATE_OFF_MUTED = 20
SL_STATES = {
    SL_STATE_UNKNOWN: {"name": "unknown", "color": COLORS.COLOR_BLACK, "ledmode": BRIGHTS.LED_OFF},
    SL_STATE_OFF: {"name": "off", "color": COLORS.COLOR_WHITE, "ledmode": BRIGHTS.LED_BRIGHT_100},
    SL_STATE_REC_STARTING: {
        "name": "waitstart",
        "color": COLORS.COLOR_RED,
        "ledmode": BRIGHTS.LED_PULSING_16,
    },
    SL_STATE_RECORDING: {
        "name": "record",
        "color": COLORS.COLOR_RED,
        "ledmode": BRIGHTS.LED_BRIGHT_100,
    },
    SL_STATE_REC_STOPPING: {
        "name": "waitstop",
        "color": COLORS.COLOR_RED,
        "ledmode": BRIGHTS.LED_PULSING_8,
    },
    SL_STATE_PLAYING: {"name": "play", "color": COLORS.COLOR_GREEN, "ledmode": BRIGHTS.LED_BRIGHT_100},
    SL_STATE_OVERDUBBING: {
        "name": "overdub",
        "color": COLORS.COLOR_PURPLE,
        "ledmode": BRIGHTS.LED_BRIGHT_100,
    },
    SL_STATE_MULTIPLYING: {
        "name": "multiply",
        "color": COLORS.COLOR_AMBER,
        "ledmode": BRIGHTS.LED_BRIGHT_100,
    },
    SL_STATE_INSERTING: {
        "name": "insert",
        "color": COLORS.COLOR_PINK_WARM,
        "ledmode": BRIGHTS.LED_BRIGHT_100,
    },
    SL_STATE_REPLACING: {
        "name": "replace",
        "color": COLORS.COLOR_PINK_LIGHT,
        "ledmode": BRIGHTS.LED_BRIGHT_100,
    },
    SL_STATE_SUBSTITUTING: {
        "name": "substitute",
        "color": COLORS.COLOR_PINK,
        "ledmode": BRIGHTS.LED_BRIGHT_100,
    },
    SL_STATE_DELAYING: {"name": "delay", "color": COLORS.COLOR_RED, "ledmode": BRIGHTS.LED_BRIGHT_10},
    SL_STATE_MUTED: {
        "name": "mute",
        "color": COLORS.COLOR_DARK_GREEN,
        "ledmode": BRIGHTS.LED_BRIGHT_100,
    },
    SL_STATE_SCRATCHING: {
        "name": "scratch",
        "color": COLORS.COLOR_BLUE,
        "ledmode": BRIGHTS.LED_BRIGHT_100,
    },
    SL_STATE_PLAYING_ONCE: {
        "name": "oneshot",
        "color": COLORS.COLOR_LIME_DARK,
        "ledmode": BRIGHTS.LED_PULSING_8,
    },
    SL_STATE_PAUSED: {
        "name": "pause",
        "color": COLORS.COLOR_GREEN_YELLOW,
        "ledmode": BRIGHTS.LED_BRIGHT_100,
    },
    SL_STATE_UNDO_ALL: {
        "name": "undo_all",
        "color": COLORS.COLOR_DARK_GREY,
        "ledmode": BRIGHTS.LED_BRIGHT_100,
    },
    SL_STATE_UNDO: {
        "name": "undo_all",
        "color": COLORS.COLOR_DARK_GREY,
        "ledmode": BRIGHTS.LED_BRIGHT_50,
    },
    SL_STATE_REDO: {
        "name": "redo",
        "color": COLORS.COLOR_DARK_GREY,
        "ledmode": BRIGHTS.LED_BRIGHT_50,
    },
    SL_STATE_REDO_ALL: {
        "name": "redo_all",
        "color": COLORS.COLOR_DARK_GREY,
        "ledmode": BRIGHTS.LED_BRIGHT_100,
    },
    SL_STATE_OFF_MUTED: {
        "name": "offmute",
        "color": COLORS.COLOR_RED,
        "ledmode": BRIGHTS.LED_BRIGHT_100,
    },  # undocumented
    SL_STATE_TRIGGER_PLAY: {
        "name": "trigger_play",
        "color": COLORS.COLOR_GREEN,
        "ledmode": BRIGHTS.LED_BRIGHT_100,
    },
}

SETTINGS = [
    "sync",
    "relative_sync",
    "playback_sync",
    "mute_quantized",
    "overdub_quantized",
    "replace_quantized",
    None,
    None,  # "quantize",
]

SETTINGCOLORS = [
    COLORS.COLOR_BLUE,
    COLORS.COLOR_LIME,
    COLORS.COLOR_GREEN,
    COLORS.COLOR_DARK_GREEN,
    COLORS.COLOR_PURPLE,
    COLORS.COLOR_PINK_LIGHT,
    # -3 = internal,  -2 = midi, -1 = jack, 0 = none, # > 0 = loop number (1 indexed)
    [
        COLORS.COLOR_WHITE,
        COLORS.COLOR_ORANGE,
        COLORS.COLOR_RED,
        COLORS.COLOR_DARK_GREY,
        COLORS.COLOR_BLUE,
        COLORS.COLOR_BLUE_DARK,
    ],
    [COLORS.COLOR_WHITE, COLORS.COLOR_ORANGE, COLORS.COLOR_BROWNISH_RED, COLORS.COLOR_BLUE],
]
PATH_LOOP_OFFSET = ["device", "loopoffset"]
DEVICEMODES = ["loops", "sessionsave", "sessionload"]
LEVELMODES = [None, "all", "selected"]
CHARS = {
    1: ["_._", ".._", "_._", "_._", "..."],
    2: ["_._", "._.", "__.", "_._", "..."],
    3: ["...", "__.", "_._", "__.", ".._"],
    4: [".__", "._.", "...", "__.", "__."],
    5: ["...", ".__", "...", "__.", "..."],
    6: ["_._", ".__", "...", "._.", "..."],
    7: ["...", "__.", "_._", "_._", ".__"],
    8: ["...", "._.", "...", "._.", "..."],
    9: ["_._", "._.", "...", "__.", "..."],
    0: ["_._", "._.", "._.", "._.", "_._"],
}
matrixPadLedmode = {".": BRIGHTS.LED_BRIGHT_100, "_": BRIGHTS.LED_BRIGHT_10}
matrixPadColor = {".": COLORS.COLOR_WHITE, "_": COLORS.COLOR_DARK_GREY}

# Some 'functional' code (well, not really)
def path(keys, obj):
    """Retrieve the value at the specified path in a nested dictionary."""
    for key in keys:
        if isinstance(obj, dict) and key in obj:
            obj = obj[key]
        else:
            return None  # Return None if the key does not exist
    return obj


def assoc_path(state, path, value):
    """Associates a value at a given path in a dictionary."""
    d = state
    for key in path[:-1]:
        d = d.setdefault(key, {})
    d[path[-1]] = value
    return state


# def over(lens_path, func, state):
#     """Applies a function to the value at the specified lens path in the state."""
#     # This is a simplified version; you would need to implement lens logic
#     value = state
#     for key in lens_path:
#         value = value.get(key)
#     new_value = func(value)
#     d = state
#     for key in lens_path[:-1]:
#         d = d[key]
#     d[lens_path[-1]] = new_value
#     return state


def split_every(n, iterable):
    """Split an iterable into chunks of size n."""
    it = iter(iterable)
    while chunk := list(islice(it, n)):
        yield chunk


def overlay(*arrays):
    # logging.debug(f"arrays {arrays}")

    # Step 1: Split each array into chunks of 3
    split_arrays = [list(split_every(3, array)) for array in arrays]
    # logging.debug(f"split {split_arrays}")

    # Step 2: Concatenate all the arrays into a single list
    concatenated = list(chain.from_iterable(split_arrays))
    # logging.debug(f"concatenated {concatenated}")

    # Step 3: Remove duplicates based on the second element
    # unique = {tuple(item): item for item in concatenated}.values()
    # unique = {tuple(map(tuple, item)): item for item in concatenated}.values()
    unique = []
    seen = set()
    for item in concatenated:
        second_item = item[1]
        if second_item not in seen:
            unique.append(item)
            seen.add(second_item)

    # logging.debug(f"unique {unique}")
    # Step 4: Sort by the second element
    sorted_unique = sorted(unique, key=lambda x: x[1])

    # Step 5: Flatten the list (if needed)
    flattened = list(chain.from_iterable(sorted_unique))

    return flattened


def list_get(lst, index, default=None):
    """Return the element at the specified index, or default if the index is out of range."""
    try:
        if 0 <= index and index < len(lst):
            return lst[index]
        return default
    except KeyError as e:
        return default


def cycle(from_val, to, cur):
    return (cur - from_val + 1) % (to - from_val + 1) + from_val
    # check whether it is the same
    delta0 = -from_val
    to0 = to + delta0
    cur0 = cur + delta0
    newVal0 = (cur0 + 1) % (to0 + 1)
    return newVal0 - delta0


# PAD FUNCTIONS


def rowStartPad(y):
    return (ROWS - 1 - y) * COLS


def rowPads(track):
    padoffset = rowStartPad(track)
    return map(lambda n: n + padoffset, range(0, COLS))


def padRow(pad):
    return range(ROWS - 1, -1, -1).index((pad / COLS) // 1)


def shiftedTrack(track, offset):
    return track - offset


# Pad coloring
def padBrightnessForLevel(num, level):
    pos = num * level
    # logging.debug(f"{pos}--{num}--{level}")
    roundedpos = pos // 1
    index = (num - 1) * (pos - roundedpos) // 1
    last = LED_BRIGHTS[int(index)]
    return (
        lambda x: BRIGHTS.LED_BRIGHT_100
        if x < roundedpos
        else last
        if x == roundedpos
        else BRIGHTS.LED_BRIGHT_10
    )


def panPads(value):
    pos = 2 * (COLS - 1) * value
    roundedpos = pos // 1
    extrapad = roundedpos % 2
    firstpad = (roundedpos / 2) // 1
    # Step 3: Remove duplicates based on the second element
    if firstpad == extrapad + firstpad:
        return [firstpad]
    return [firstpad, firstpad + extrapad]
    # unique = {tuple(item): item for item in [firstpad, firstpad + extrapad]}.values()
    # return unique


def get_cell_led_mode_fn(state: Dict[str, Any]) -> Callable:
    def cond_fn(track, y):
        # Check for device pan
        if getDeviceSetting("pan", state):
            channels = track.get("channel_count")
            if channels is None:
                return lambda x: BRIGHTS.LED_BRIGHT_10
            if channels == 2:
                pads_left = panPads(track["pan_1"])
                pads_right = panPads(track["pan_2"])
                both = set(pads_left) & set(pads_right)
                any_pads = set(pads_left) | set(pads_right)

                return lambda x: (
                    BRIGHTS.LED_BRIGHT_100
                    if x in both
                    else BRIGHTS.LED_BRIGHT_75
                    if x in any_pads
                    else BRIGHTS.LED_BRIGHT_25
                )
            pads = panPads(track.get("pan_1", []))
            return lambda x: BRIGHTS.LED_BRIGHT_100 if x in pads else BRIGHTS.LED_BRIGHT_25

        # Check for track levels
        if showTrackLevels(state):
            tracknum = getGlob("selected_loop_num", state)
            theTrack = (
                state.glob
                if tracknum == -1
                else state.get("tracks", {}).get(tracknum, {})
            )
            # level = theTrack[key]

            def track_level_fn(track, i):
                return lambda xpad: (
                    padBrightnessForLevel(ROWS, theTrack.get(TRACK_LEVELS[xpad], 0))(
                        ROWS - 1 - i
                    )
                )

            return track_level_fn(None, y)  # NO Example index

        # Check for device levels
        if getDeviceSetting("levels", state):
            return lambda x: padBrightnessForLevel(COLS, track.get("wet", 0))(x)

        # Default case
        state_value = track.get("state", SL_STATE_UNKNOWN)
        if state_value == SL_STATE_UNKNOWN:
            return lambda x: 0x80
        pos = (
            0
            if track.get("loop_len", 0) == 0
            else 8 * (track.get("loop_pos", 0) / track.get("loop_len", 1))
        )

        rounded_pos = int(pos)
        # last = LED_BRIGHTS[
        #     min(3, int(7 * (pos - rounded_pos)))
        # ]  # Ensure index is within bounds
        led_mode = SL_STATES[state_value]["ledmode"]

        return lambda x: (
            BRIGHTS.LED_BRIGHT_100
            if led_mode == BRIGHTS.LED_BRIGHT_100 and x <= rounded_pos
            else BRIGHTS.LED_BRIGHT_25
            if led_mode == BRIGHTS.LED_BRIGHT_100
            else led_mode
        )

    return cond_fn


def get_cell_color_fn(state: Dict[str, Any]) -> Callable:
    def cond_fn(track):
        # Check for device pan
        if getDeviceSetting("pan", state):
            channels = track.get("channel_count")
            track_state = track.get("state", SL_STATE_UNKNOWN)
            if channels is None:
                return lambda x: SL_STATES[track_state]["color"]
            if channels == 2:
                pads_left = panPads(track["pan_1"])
                pads_right = panPads(track["pan_2"])
                both = set(pads_left) & set(pads_right)
                # any_pads = set(pads_left) | set(pads_right)

                return lambda x: (
                    COLORS.COLOR_PURPLE
                    if x in both
                    else COLORS.COLOR_RED
                    if x in pads_left
                    else COLORS.COLOR_BLUE
                    if x in pads_right
                    else SL_STATES[track_state]["color"]
                )
            return lambda x: SL_STATES[track_state]["color"]

        # Check for selected loop levels
        if showTrackLevels(state):

            def track_level_fn(track, i):
                return lambda xpad: LEVEL_COLORS[xpad]  # Example implementation

            return track_level_fn(track, 0)  # Example index

        # Check for wet for loops on page
        if getDeviceSetting("levels", state):
            state_value = track.get("state", SL_STATE_UNKNOWN)
            return lambda x: (
                SL_STATES[state_value]["color"]
                if state_value == SL_STATE_UNKNOWN
                else COLORS.COLOR_BLUE_LIGHT
                if state_value == SL_STATE_OFF
                else COLORS.COLOR_BLUE
            )

        # Default case
        state_value = track.get("state", SL_STATE_UNKNOWN)
        statespec = SL_STATES[state_value]
        statecolor = statespec["color"]
        return lambda x: statecolor

    return cond_fn


def make_loopnum_overlay(char, col=0):
    spec = CHARS.get(char)
    if not spec:
        return []

    overlay = []
    for rownum, charSpec in enumerate(spec):
        startPad = rowStartPad(rownum) + col
        for i, boolish in enumerate(charSpec):
            pad = startPad + i
            overlay.extend([matrixPadLedmode[boolish], pad, matrixPadColor[boolish]])

    return overlay


def matrix_function(toprow, loopoffset, tracks, storeState, set_syncs):
    matrix = []
    trackLedModeFn = get_cell_led_mode_fn(storeState)
    trackColorFn = get_cell_color_fn(storeState)

    for y in range(ROWS):  # Equivalent to [0, 1, 2, 3, 4]
        tracknum = y - loopoffset
        track = list_get(tracks, tracknum, {})
        cellLedModeFn = trackLedModeFn(track, y)
        cellColorFn = trackColorFn(track)

        # state = track.get("state", SL_STATE_UNKNOWN)
        # next_state = track.get("next_state")
        # loop_len = track.get("loop_len")
        # loop_pos = track.get("loop_pos")
        # wet = track.get("wet")
        # sync = track.get("sync")
        # relative_sync = track.get("relative_sync")

        if not (set_syncs or showTrackLevels(storeState)) and y == 0:
            matrix.extend(toprow)
            # logging.debug(f"matrci with top row {matrix}")
            continue
        if set_syncs and y == 0:
            padnums = range(32, 38)  # rowPads(y)
            pads = []
            for x, pad in enumerate(padnums):
                pads.extend([BRIGHTS.LED_BRIGHT_50, pad, SETTINGCOLORS[x]])

            track1 = tracks.get(0, {})
            synccolor = SETTINGCOLORS[6][
                int(min((getGlob("sync_source", storeState) or 0) + 3, 5))
            ]

            matrix.extend(
                [
                    BRIGHTS.LED_BRIGHT_100,
                    38,
                    synccolor,
                    BRIGHTS.LED_BRIGHT_100 if track1.get("quantize") else BRIGHTS.LED_BRIGHT_10,
                    39,
                    list_get(
                        SETTINGCOLORS[7],
                        int(track1.get("quantize")),
                        SETTINGCOLORS[7][0],
                    ),
                    *pads,
                ]
            )
            continue

        try:
            if set_syncs:
                pads = [
                    [
                        BRIGHTS.LED_BRIGHT_100 if track.get(SETTINGS[x]) else BRIGHTS.LED_BRIGHT_10,
                        pad,
                        SETTINGCOLORS[x][int(track.get(SETTINGS[x], 0))]
                        if isinstance(SETTINGCOLORS[x], list)
                        else SETTINGCOLORS[x],
                    ]
                    for x, pad in enumerate(rowPads(y))
                ]
                
                matrix.extend(
                    [
                        BRIGHTS.LED_BRIGHT_75,
                        30,
                        COLORS.COLOR_BROWN_LIGHT,
                        BRIGHTS.LED_BRIGHT_75,
                        31,
                        COLORS.COLOR_BROWN_LIGHT,
                    ]
                )
                for pad in pads:
                    matrix.extend(pad)
                continue

            for x, pad in enumerate(rowPads(y)):
                cell = [cellLedModeFn(x), pad, cellColorFn(x)]
                matrix.extend(cell)

        except Exception as e:
            logging.debug("Caught an exception:", e)
            raise
            return []

    return matrix


def get_soft_keys(loopoffset, storeState):
    soft_keys = []

    for y in range(5):  # Equivalent to [0, 1, 2, 3, 4]
        tracknum = -1 if y == 0 else y - loopoffset
        selected_loop_num = getGlob("selected_loop_num", storeState)

        soft_keys.extend(
            [
                0x90,
                0x52 + y,
                0x02
                if tracknum == selected_loop_num and showTrackLevels(storeState)
                else (0x01 if tracknum == selected_loop_num else 0),
            ]
        )

    return soft_keys


def get_eighths(storeState):
    if getDeviceSetting("show8ths", storeState):
        eighths = [
            item
            for pad in range(getGlob("eighth_per_cycle", storeState))
            for item in [BRIGHTS.LED_BRIGHT_100, pad, COLORS.COLOR_BROWNISH_RED]
        ]
    else:
        eighths = []

    return eighths


# ACTION HELPERS


def globAction(setting, value):
    return {"type": "glob", "setting": setting, "value": value}


def deviceAction(setting, value):
    return {"type": "device", "setting": setting, "value": value}


def batchAction(actions):
    return {"type": "batch", "value": actions}


def trackAction(track, ctrl, value):
    return {
        "type": "track",
        "track": track,
        "ctrl": ctrl,
        "value": value,
    }


# STATE HELPERS


def getDeviceMode(state):
    return path(["device", "mode"], state) or 0


def getDeviceSetting(setting, state):
    return path(["device", setting], state)


def getGlob(setting, state):
    return path(["glob", setting], state)


def getLoopoffset(state):
    offset = path(PATH_LOOP_OFFSET, state)
    return 1 if offset is None else offset


def showTrackLevels(state):
    level_mode = getDeviceSetting("levels", state)
    if not level_mode:
        return False
    selected_loop_num = getGlob("selected_loop_num", state)
    if selected_loop_num is None:
        return False
    return 1 < level_mode and -2 < selected_loop_num


def syncMode(state):
    return path(["device", "sync"], state)


# Reduce function
def on_update_track(action, state):
    track = action.get("track")
    ctrl = action.get("ctrl")
    value = action.get("value")
    return assoc_path(state, ["tracks", track, ctrl], value)


# Create the FULL MIDI LED LAYOUT
def createAllPads(state):
    loopoffset = getLoopoffset(state)
    set_syncs = syncMode(state)
    devicemode = max(0, getDeviceMode(state) or 0)
    levelmode = getDeviceSetting("levels", state) or 0
    panmode = getDeviceSetting("pan", state) or False

    def ctrl_btn(btn):
        if btn == BUTTONS.BTN_KNOB_CTRL_VOLUME:
            return [0x90, btn, levelmode]
        if btn == BUTTONS.BTN_KNOB_CTRL_PAN:
            return [
                0x90,
                btn,
                1 if panmode else 0,
            ]  # @check Used to have to convert this to num
        if btn == BUTTONS.BTN_KNOB_CTRL_SEND:
            return [0x90, btn, 1 if set_syncs else 0]
        if btn == BUTTONS.BTN_KNOB_CTRL_DEVICE:
            return [0x90, btn, devicemode]
        return []

    ctrl_keys = functools.reduce(
        lambda acc, btn: acc + ctrl_btn(btn), range(0x40, 0x48), []
    )

    if devicemode > 0:
        color = (
            COLORS.COLOR_DARK_GREEN
            if DEVICEMODES[devicemode] == "sessionload"
            else COLORS.COLOR_ORANGE
        )
        sessions = getDeviceSetting("sessions", state) or []
        sessionnums = functools.reduce(
            lambda acc, cur: acc + [BRIGHTS.LED_BRIGHT_100, int(cur[:-7]), color], sessions, []
        )

        def emptycellreducer(acc, cur):
            return acc + [BRIGHTS.LED_BRIGHT_25, cur, color]

        def emptyrowreducer(acc, cur):
            return acc + functools.reduce(emptycellreducer, rowPads(cur), [])

        emptycells = functools.reduce(emptyrowreducer, range(0, ROWS), [])
        return overlay(sessionnums, emptycells) + ctrl_keys

    tracks = state.get("tracks", [])
    toprow = (
        []
        if (set_syncs or showTrackLevels(state))
        else [
            [BRIGHTS.LED_BRIGHT_90, pad, SL_STATES[TRACK_COMMANDS[i]]["color"]]
            for i, pad in enumerate(rowPads(0))
        ]
    )
    toprow = list(chain.from_iterable(toprow))
    matrix = matrix_function(toprow, loopoffset, tracks, state, set_syncs)
    # mlen = len(matrix) / 3
    # logging.debug(f"{mlen}")
    #return matrix
    soft_keys = get_soft_keys(loopoffset, state)
    eighths = get_eighths(state)
    # logging.debug(f"softkeys{soft_keys}")
    # logging.debug(f"ctrl_keys{ctrl_keys}")
    # logging.debug(f"matrix{matrix}")
    pads = matrix + overlay(soft_keys, ctrl_keys)
    if len(pads):
        if getDeviceSetting("shifted", state):
            firstLoop = 2 - loopoffset
            if firstLoop > 9 and firstLoop < 100:
                return overlay(
                    make_loopnum_overlay((firstLoop / 10) // 1, 2),
                    make_loopnum_overlay(firstLoop % 10, 5),
                    pads,
                )
            else:
                return overlay(make_loopnum_overlay(firstLoop, 5), pads)
        else:
            return overlay(eighths, pads)


class ButtonAutoLatch:
    PT_BOLD_TIME = 0.3 * 1000

    def __init__(self):
        self._hits = {}

    def performance_now(self):
        # Implement a method to return the current time in milliseconds
        import time

        return time.time() * 1000

    def feed(self, note, evtype):
        last = self._hits.get(note)
        now = (
            self.performance_now()
        )  # Assuming you have a method to get the current time

        # If note_on, return true
        if evtype == EV_NOTE_ON:
            if last:
                del self._hits[note]
                return False
            # Turn on
            self._hits[note] = now
            return True

        if evtype == EV_NOTE_OFF:
            if note not in self._hits:
                return False
            else:
                if now - last < self.PT_BOLD_TIME:
                    return True
                    # leave on
                else:
                    del self._hits[note]
                    return False
                    # turn off

        raise ValueError("ButtonAutoLatch only meant for NOTE_ON and NOTE_OFF events")


# zynthian_ctrldev_akai_apc_key25_mk2_sl
class zynthian_ctrldev_akai_apc_key25_mk2_sl(
    zynthian_ctrldev_base  # zynthian_ctrldev_zynmixer, zynthian_ctrldev_zynpad
):
    """Zynthian Controller Device: Akai APC Key 25 SL"""

    dev_ids = ["APC Key 25 mk2 MIDI 2", "APC Key 25 mk2 IN 2"]

    ctrls = [
        "channel_count",  # undocumented
        "wet",
        "dry",
        "pan_1",
        "pan_2",
        "pan_3",
        "pan_4",
        "feedback",
        "input_gain",
        "rec_thresh",
        "sync",
        "relative_sync",
        "quantize",
        "playback_sync",
        "mute_quantized",
        "overdub_quantized",
        "replace_quantized",
        "reverse",
    ]
    auto_ctrls = [
        "state",
        "next_state",
        "loop_pos",
        "loop_len",
    ]
    globs = [
        "sync_source",
        "selected_loop_num",
        "eighth_per_cycle",
        "wet",
        "dry",
        "input_gain",
    ]

    @classmethod
    def get_autoload_flag(cls):
        return True

    SL_PORT = zynthian_engine_sooperlooper.SL_PORT
    # OSC_SL_PORT = ServerPort["sooperlooper_osc"] # 9951
    # OSC_SL_HOST = "127.0.0.1"; # Unnecessary

    SL_SESSION_PATH = "/zynthian/zynthian-my-data/presets/sooperlooper/"

    def __init__(
        self, state_manager=None, idev_in=None, idev_out=None, *args, **kwargs
    ):
        """Initialize the controller with required parameters"""
        logging.debug("\n=================================================================")
        logging.debug("APC Key 25 mk2 SL __init__ starting...")
        logging.debug(f"state_manager: {state_manager}")
        logging.debug(f"idev_in: {idev_in}, type: {type(idev_in)}")
        logging.debug(f"idev_out: {idev_out}, type: {type(idev_out)}")

        logging.debug("Calling parent class __init__...")
        # Call parent class initializer explicitly
        #        zynthian_ctrldev_base.__init__(self, state_manager, idev_in, idev_out)
        super().__init__(state_manager, idev_in, idev_out)

        logging.debug("Parent class __init__ completed")
        logging.debug(f"self.idev_out after parent init: {self.idev_out}")
        logging.debug("APC Key 25 mk2 SL __init__ completed")
        logging.debug("=================================================================\n")
        self._knobs_ease = KnobSpeedControl()
        self._auto_latch = ButtonAutoLatch()
        self._state_manager = state_manager
        self._init_complete = False
        self._shutting_down = False
        self._leds = None
        self.osc_server = None
        self.osc_target = None
        self._loop_states = {}
        self._init_time = 0
        self.dosolo = False
        self.domute = False
        self.undoing = False
        self.redoing = False
        self.force_alt1 = False

        self._leds = FeedbackLEDs(idev_out)
        self.loopcount = 0
        self.state = {}
        self._leds.all_off()
        # Light up first button in each row
        # self._leds.led_state(82, LED_ON)  # First snapshot
        # self._leds.led_state(64, LED_ON)  # First zs3

        # if self._leds is None:
        #     logging.debug("Initializing LED controller...")
        #     self._leds = FeedbackLEDs(idev_out)
        #     logging.debug("LED controller initialized")

    def refresh(self):
        """Refresh device state"""
        # if self._try_connect_to_sooperlooper():
        #     self.update_loop_states()

    def init(self):
        logging.debug("Starting APC Key 25 mk2 sl init sequence")
        """Initialize the device"""
        if self._shutting_down:
            logging.debug("Skipping initialization - device is shutting down")
            return

        self._init_complete = False
        super().init()

        if not self._shutting_down:
            logging.debug("Initializing zynthian_ctrldev_akai_apc_key25...")

            # Initialize LED controller
            if self._leds is None:
                logging.debug("Initializing LED controller...")
                self._leds = FeedbackLEDs(self.idev_out)
                logging.debug("LED controller initialized")

            # Initialize OSC server
            try:
                logging.debug("Creating OSC server...")
                self.osc_server = liblo.ServerThread()
                self.osc_server_port = self.osc_server.get_port()
                self.osc_server_url = f"osc.udp://localhost:{self.osc_server_port}"
                logging.debug(f"OSC server initialized on port {self.osc_server_port}")

                # Register OSC methods
                logging.debug("Registering OSC methods...")
                self.osc_server.add_method("/error", "s", self._cb_osc_error)
                self.osc_server.add_method("/pong", "ssi", self._cb_osc_pong)
                self.osc_server.add_method("/info", "ssi", self._cb_osc_info)
                self.osc_server.add_method("/update", "isf", self._cb_osc_update)
                self.osc_server.add_method("/glob", "isf", self._cb_osc_glob)
                # self.osc_server.add_method("/sessions", "sf", self._cb_osc_sessions)
                self.osc_server.add_method(None, None, self._cb_osc_fallback)

                # Start the OSC server
                logging.debug("Starting OSC server...")
                self.osc_server.start()
                logging.debug("OSC server started successfully")

                logging.debug("Attempting to connect to SooperLooper...")
                # Start connection attempt timer
                self._init_time = time.time()
                self._try_connect_to_sooperlooper()

            except liblo.ServerError as err:
                logging.debug(f"Error initializing OSC: {err}")
                self.osc_server = None

    def end(self):
        super().end()

    def refresh(self):
        # PadMatrix is handled in volume/pan modes (when mixer handler is active)
        pass

    def deviceModeName(self):
        faux_devmodes = DEVICEMODES + ["off"]
        return faux_devmodes[getDeviceMode(self.state)]

    def increase(self, delta, ctrl, track, loopnum):
        curval = track.get(ctrl)
        if curval is None:
            return
        # Calculate the new value, ensuring it stays within the range [0, 1]
        new_value = max(0, min(1, curval + delta * 0.1))
        self.just_send(f"/sl/{loopnum}/set", ("s", ctrl), ("f", new_value))

    def midi_event(self, event):
        evtype = (event[0] >> 4) & 0x0F
        button = event[1] & 0x7F
        if evtype == EV_CC:
            return self.cc_event(event)
        if (
            (evtype == EV_NOTE_OFF or evtype == EV_NOTE_ON)
            and button >= BUTTONS.BTN_PAD_START
            and button <= BUTTONS.BTN_PAD_END
        ):
            return self.pad_event(event)
        if button >= BUTTONS.BTN_KNOB_CTRL_VOLUME and button <= BUTTONS.BTN_KNOB_CTRL_DEVICE:
            return self.handle_mode_buttons(button, evtype)
        if (
            getDeviceSetting("shifted", self.state)
            and button >= BUTTONS.BTN_SOFT_KEY_CLIP_STOP
            and button <= BUTTONS.BTN_SOFT_KEY_SELECT
        ):
            return self.select_loop_for_button(button)
        self.handle_rest_of_buttons(button, evtype)
        pass

    def cc_event(self, event):
        ccnum = event[1] & 0x7F
        ccval = event[2] & 0x7F
        delta = self._knobs_ease.feed(
            ccnum, ccval, getDeviceSetting("shifted", self.state)
        )  # @todo: use self._is_shifted (or not at all?)
        if delta is None:
            return
        knobnum = ccnum - 48
        if showTrackLevels(self.state):
            if knobnum == 0:
                return
            level = TRACK_LEVELS[knobnum]
            if not level:
                return
            loopnum = getGlob("selected_loop_num", self.state)
            if loopnum == -1:
                return
            self.increase(delta, level, self.state["tracks"][loopnum], loopnum)
            return
        loopoffset = getLoopoffset(self.state)
        loopnum = (knobnum % KNOBS_PER_ROW) - (loopoffset - 1)
        tracks = self.state["tracks"]
        track = tracks.get(loopnum)
        if track is None:  # Check if track is None
            return None  # Or handle as needed
        funnum = knobnum // KNOBS_PER_ROW
        # todo: this could be larger than 1?
        funs = ["wet", "pan"]
        fun = funs[funnum]
        if fun == "pan":
            channel_count = int(track.get("channel_count", 0))
            for c in range(
                1, channel_count + 1
            ):  # Loop from 1 to channel_count inclusive
                ctrl = f"pan_{c}"
                if getDeviceSetting("shifted", self.state):
                    if c == 2 and channel_count == 2:
                        self.increase(-delta, ctrl, track, loopnum)
                    else:
                        self.increase(delta, ctrl, track, loopnum)
                else:
                    if channel_count == 2:
                        if c == 1:
                            if delta < 0 or track.get("pan_2", 0) >= 0.5:
                                self.increase(delta, ctrl, track, loopnum)
                        if c == 2:
                            if delta > 0 or track.get("pan_1", 0) <= 0.5:
                                self.increase(delta, ctrl, track, loopnum)
                    else:
                        self.increase(delta, ctrl, track, loopnum)
        else:
            self.increase(delta, fun, track, loopnum)
        pass

    def pad_event(self, event):
        if getDeviceSetting("pan", self.state):
            return
        evtype = (event[0] >> 4) & 0x0F
        pad = event[1] & 0x7F
        set_syncs = syncMode(self.state)
        row = padRow(pad)
        numpad = pad % COLS
        if set_syncs:
            # @todo: numpad 6 and row 2 and 3 would be better to get multiples of 8
            if row == 1 and numpad >= 6:
                show8ths = evtype == EV_NOTE_ON
                self.dispatch(deviceAction("show8ths", show8ths))
                if show8ths:
                    setting = "eighth_per_cycle"
                    oldvalue = getGlob(setting, self.state) or 16
                    value = max(2, oldvalue - 1) if numpad == 6 else oldvalue + 1
                    self.just_send("/set", ("s", setting), ("f", value))
                    self.dispatch(globAction(setting, value))
                return

            # Set 8ths directly
            if getDeviceSetting("show8ths", self.state) and (pad < 30 or (pad > 31 and pad < 40)):
                setting = "eighth_per_cycle"
                value = pad + 1
                self.just_send("/set", ("s", setting), ("f", value))
                self.dispatch(globAction(setting, value))
                return
        loopoffset = getLoopoffset(self.state)
        track = -1 if row == 0 else shiftedTrack(row, loopoffset)
        tracks = self.state["tracks"]
        stateTrack = None if track == -1 else path(["tracks", track], self.state)
        if evtype == EV_NOTE_ON:
            if set_syncs:
                return self.handle_syncs(numpad, track, stateTrack, tracks)
            if self.deviceModeName() == "sessionsave":
                return self.save_session(pad)
            if self.deviceModeName() == "sessionload":
                return self.load_session(pad)
            if pad <= (ROWS * COLS) and showTrackLevels(self.state):
                return self.handle_track_levels(numpad, row)
            if pad <= ((ROWS - 1) * COLS) and path(["device", "levels"], self.state):
                return self.handle_all_wet(numpad, track, tracks)
            if path(["device", "levels"], self.state):
                return self.handle_glob_wet(numpad)
            if track >= self.loopcount:
                return self.handle_loop_operations(numpad)
            if self.dosolo:
                return self.just_send(f"/sl/{track}/hit", ("s", "solo"))
            if self.domute:
                return self.just_send(f"/sl/{track}/hit", ("s", "mute"))
            if self.undoing and numpad <= 1:
                return self.just_send(f"/sl/{track}/hit", ("s", "undo_all"))
            if self.redoing and numpad >= 4:
                return self.just_send(f"/sl/{track}/hit", ("s", "redo_all"))
            if numpad == 0:
                return self.handle_rec_or_overdub(track, stateTrack)
            if numpad < 8:
                return self.handle_loop_actions(numpad, track)
        pass

    def handle_syncs(self, numpad: int, track: int, stateTrack: Dict[str, Any], tracks):
        if numpad < 6:
            if stateTrack is None:
                return
            setting = SETTINGS[numpad]
            self.just_send(
                f"/sl/{track}/set",
                setting,
                int(not stateTrack.get(setting, False)),  # Convert boolean to int
            )

        if track == -1 and numpad == 7:
            # NOTE: it seems just loop 1's setting is used for all
            quant = int(tracks[0].get("quantize", -1))  # Default to -1 if not found
            if quant is None:  # Check for NaN equivalent
                quant = -1
            self.just_send(f"/sl/{track}/set", "quantize", (quant + 1) % 4)

        if track == -1 and numpad == 6:
            # -3 = internal, -2 = midi, -1 = jack, 0 = none, # > 0 = loop number (1 indexed)
            setting = "sync_source"
            oldvalue = self.state.get("glob", {}).get(
                setting, -3
            )  # Default to -3 if not found
            if oldvalue is None:  # Check for NaN equivalent
                oldvalue = -4

            value = cycle(
                -3, self.loopcount, oldvalue
            )  # Assuming cycle is defined elsewhere
            self.just_send("/set", setting, value)
            self.dispatch(globAction(setting, value))

        return

    def handle_mode_buttons(self, button, evtype):
        if button == BUTTONS.BTN_KNOB_CTRL_VOLUME and evtype == EV_NOTE_ON:
            self.cycle_level_mode()
            return

        if button == BUTTONS.BTN_KNOB_CTRL_PAN:
            dopan = self._auto_latch.feed(button, evtype)
            self.dispatch(
                batchAction(
                    [
                        deviceAction("levels", 0),
                        deviceAction("pan", dopan),
                        deviceAction("sync", False),
                        deviceAction("mode", -1 if dopan else 0),
                    ]
                )
            )
            self.unregister_selected(["in_peak_meter"])
            return

        if button == BUTTONS.BTN_KNOB_CTRL_SEND:
            if evtype == EV_NOTE_OFF:
                return
            dosync = not getDeviceSetting("sync", self.state)
            self.dispatch(  #
                batchAction(
                    [
                        deviceAction("levels", 0),
                        deviceAction(
                            "pan", self._auto_latch.feed(BUTTONS.BTN_KNOB_CTRL_PAN, EV_NOTE_OFF)
                        ),
                        deviceAction("sync", dosync),
                        deviceAction("mode", -1 if dosync else 0),
                    ]
                )
            )
            self.unregister_selected(["in_peak_meter"])
            return

        if button == BUTTONS.BTN_KNOB_CTRL_DEVICE:
            if evtype == EV_NOTE_ON:
                self.cycle_device_mode()
            return

    def cycle_device_mode(self):
        state = self.state
        devicemode = getDeviceMode(state)
        logging.debug(f"{devicemode}")
        # logging.debug(f"{state}")
        devicemode = (devicemode + 1) % len(DEVICEMODES)

        self.dispatch(
            batchAction(
                [
                    deviceAction("levels", 0),
                    deviceAction(
                        "pan", self._auto_latch.feed(BUTTONS.BTN_KNOB_CTRL_PAN, EV_NOTE_OFF)
                    ),
                    deviceAction("sync", False),
                    deviceAction("mode", devicemode),
                ]
            )
        )

        if devicemode > 0:
            self.get_sessions()

        self.unregister_selected(
            ["in_peak_meter"]
        )  # Assuming unregister_selected is a method of self

    def cycle_level_mode(self):
        state = self.state
        level_mode = getDeviceSetting("levels", state) or 0

        level_mode = (level_mode + 1) % len(LEVELMODES)

        if level_mode != 0:
            if level_mode == 2:
                self.register_selected(
                    ["in_peak_meter"]
                )  # Assuming register_selected is a method of self

            self.dispatch(
                batchAction(
                    [
                        deviceAction("levels", level_mode),
                        deviceAction(
                            "pan", self._auto_latch.feed(BUTTONS.BTN_KNOB_CTRL_PAN, EV_NOTE_OFF)
                        ),
                        deviceAction("sync", False),
                        deviceAction("mode", -1),
                    ]
                )
            )
        else:
            self.dispatch(
                batchAction(
                    [deviceAction("levels", level_mode), deviceAction("mode", 0)]
                )
            )
            self.unregister_selected(
                ["in_peak_meter"]
            )  # Assuming unregister_selected is a method of self

    def select_loop_for_button(self, button):
        row = button - 0x52
        track = (
            -1 if row == 0 else shiftedTrack(row, getLoopoffset(self.state))
        )  # Assuming shifted_track is a method of self

        if track < self.loopcount:
            self.dispatch(globAction("selected_loop_num", track))
            self.just_send("/set", ("s", "selected_loop_num"), ("f", track))
        return

    def handle_rest_of_buttons(self, button, evtype):
        if button == BUTTONS.BTN_SHIFT:
            self.dispatch(deviceAction("shifted",  evtype == EV_NOTE_ON))
            return

        if button == BUTTONS.BTN_UNDO:
            self.undoing = evtype == EV_NOTE_ON
            return

        if button == BUTTONS.BTN_REDO:
            self.redoing = evtype == EV_NOTE_ON
            return

        if button == BUTTONS.BTN_TRACK_1:
            if evtype == EV_NOTE_ON and (getDeviceSetting("shifted", self.state) or syncMode(self.state)):
                self.shift_up()  # Assuming shift_up is a method of self
                return
            self.force_alt1 = evtype == EV_NOTE_ON
            return

        if button == BUTTONS.BTN_TRACK_2:
            if evtype == EV_NOTE_ON and (getDeviceSetting("shifted", self.state) or syncMode(self.state)):
                self.shift_down()  # Assuming shift_down is a method of self
            return

        if button == BUTTONS.BTN_SOFT_KEY_SOLO:
            self.dosolo = evtype == EV_NOTE_ON
            return

        if button == BUTTONS.BTN_SOFT_KEY_MUTE:
            self.domute = evtype == EV_NOTE_ON
            return

        if button == BUTTONS.BTN_STOP_ALL_CLIPS:
            # self.render_all_pads(state)  # Assuming render_all_pads is a method of self
            # @todo: simply turn all leds off
            self.request_feedback(
                "/ping", "/pong"
            )  # Assuming request_feedback is a method of self
            return
        return

    def get_sessions(self):
        mypath = zynthian_ctrldev_akai_apc_key25_mk2_sl.SL_SESSION_PATH
        onlyfiles = [f for f in listdir(mypath) if isfile(join(mypath, f)) and f.endswith('.slsess')]
        self.dispatch(deviceAction("sessions", onlyfiles))

    def load_session(self, pad):
        # Create the URI
        file_path = f"{self.SL_SESSION_PATH}{str(pad).zfill(2)}.slsess"

        # Send the session load request
        self.just_send("/load_session", file_path, self.osc_server_url, "/error")

        # Use time.sleep to mimic setTimeout
        time.sleep(1)  # Wait for 1 second
        self.request_feedback("/ping", "/pong")

    def save_session(self, pad):
        # Create the filepath
        file_path = f"{self.SL_SESSION_PATH}{str(pad).zfill(2)}.slsess"

        # Send the session load request
        self.just_send("/save_session", file_path, self.osc_server_url, "/error", 1)

        # Use time.sleep to mimic setTimeout
        time.sleep(1)  # Wait for 1 second
        self.get_sessions()

    def handle_track_levels(self, numpad, row):
        tracks = self.state.get("tracks")
        value = (ROWS - row) / ROWS
        trackno = getGlob("selected_loop_num", self.state)
        isglob = trackno == -1

        if isglob and (numpad < 2 or numpad > 4):
            return

        levelTrack = self.state["glob"] if isglob else tracks[trackno]
        if levelTrack is None:
            return

        ctrl = TRACK_LEVELS[numpad]
        storedValue = levelTrack.get(ctrl, 0)

        if round(storedValue * ROWS) == round(value * ROWS):
            value -= 1 / 10

        if round(storedValue * 100) == 10 and row == ROWS - 1:
            value = 0

        if isglob:
            self.dispatch(globAction(ctrl, value))
            self.just_send("/set", ("s", ctrl), ("f", value))
        else:
            self.dispatch(trackAction(trackno, ctrl, value))
            self.just_send(f"/sl/{trackno}/set", ("s", ctrl), ("f", value))

    def handle_all_wet(self, numpad, track, tracks):
        value = (numpad + 1) / COLS
        stateTrack = tracks.get(track)
        if not stateTrack:
            return

        storedValue = stateTrack.get("wet")

        if storedValue is None:
            return

        if storedValue == value:
            value -= 1 / (COLS * 2)

        if storedValue == 1 / (COLS * 2) and numpad == 0:
            value = 0

        self.dispatch(trackAction(track, "wet", value))
        self.just_send(f"/sl/{track}/set", ("s", "wet"), ("f", value))

    def handle_glob_wet(self, numpad):
        setting = "wet"
        value = (numpad + 1) / COLS
        storedValue = getGlob(setting, self.state)

        if storedValue == value:
            value -= 1 / (COLS * 2)

        self.dispatch(globAction(setting, value))
        self.just_send("/set", ("s", "wet"), ("f", value))

    def handle_loop_operations(self, numpad):
        if numpad <= 3:
            self.just_send(
                "/loop_add",
                ("i", (numpad + 1) % 4),  # mono - 4 channels, repeating
                ("f", 40),
            )
            return

        elif numpad >= 4:
            self.just_send(
                "/loop_del",
                ("i", -1),  # Last loop -- the only supported one
            )
            return

    def handle_rec_or_overdub(self, track, stateTrack):
        if track == -1:
            self.just_send(f"/sl/{track}/hit", ("s", "record_or_overdub"))
            return
        if stateTrack is None:
            return
        state = stateTrack.get("state", SL_STATE_UNKNOWN)
        if (
            state < SL_STATE_RECORDING
            or (not self.force_alt1 and state == SL_STATE_RECORDING)
            or (self.force_alt1 and state != SL_STATE_RECORDING)
        ):
            self.just_send(f"/sl/{track}/hit", ("s", "record"))
        else:
            self.just_send(f"/sl/{track}/hit", ("s", "overdub"))

    def handle_loop_actions(self, numpad, track):
        if numpad == 1:
            self.just_send(f"/sl/{track}/hit", ("s", "multiply"))
            return

        if numpad == 2:
            if self.undoing:
                self.just_send(f"/sl/{track}/hit", ("s", "undo"))
            else:
                self.just_send(f"/sl/{track}/hit", ("s", "insert"))
            return

        if numpad == 3:
            if self.redoing:
                self.just_send(f"/sl/{track}/hit", ("s", "redo"))
            else:
                self.just_send(f"/sl/{track}/hit", ("s", "replace"))
            return

        if numpad == 4:
            self.just_send(f"/sl/{track}/hit", ("s", "substitute"))
            return

        if numpad == 5:
            self.just_send(f"/sl/{track}/hit", ("s", "oneshot"))

        if numpad == 6:
            self.just_send(f"/sl/{track}/hit", ("s", "trigger"))

        if numpad == 7:
            if getDeviceSetting("shifted", self.state):
                self.just_send(
                    f"/sl/{track}/set", ("s", "delay_trigger"), ("f", random.random())
                )
            else:
                self.just_send(f"/sl/{track}/hit", ("s", "pause"))

    def request_feedback(self, address, path, *args):
        self.osc_server.send(self.osc_target, address, *args, self.osc_server_url, path)

    def just_send(self, address, *args):
        self.osc_server.send(self.osc_target, address, *args)

    def range(self, start=0):
        return f"[{start}-{self.loopcount - 1}]"

    def _cb_osc_fallback(self, path, args, types, src):
        """Fallback callback for unhandled OSC messages"""
        logging.debug(f"Received unhandled OSC message: {path} {args}")

    def _cb_osc_error(self, path, args):
        """Error callback for errors on loading or saving sessions"""
        logging.debug(f"Error: {path} {args}")

    def _cb_osc_pong(self, path, args):
        """Callback for info messages from SooperLooper"""
        self._init_complete = True
        self.request_feedback("/register", "/info")
        self.handleInfo(args)
        self.register_update(self.range(0))
        self.just_send("/set", "smart_eighths", 0)

    def shift_down(self):
        self.dispatch({"type": "offsetDown"})

    def shift_up(self):
        self.dispatch({"type": "offsetUp"})

    def _cb_osc_info(self, path, args):
        """Callback for info messages from SooperLooper"""
        old_count = int(self.loopcount)
        self.handleInfo(args)

        logging.debug(f"{old_count} => {self.loopcount}")
        if self.loopcount > old_count:
            for loop in range(old_count, self.loopcount):
                self.register_update(loop)
                self.just_send(f"/sl/{loop}/set", "sync", 1)
        if self.loopcount < old_count:
            for loop in range(self.loopcount, old_count):
                self.dispatch({"type": "empty-track", "value": loop})

    def _cb_osc_update(self, path, args, types, src):
        [track, ctrl, val] = args[:3]
        if ctrl == "in_peak_meter":
            self.dispatch(
                {
                    "type": "track",
                    "track": getGlob("selected_loop_num", self.state),
                    "ctrl": ctrl,
                    "value": val * 2,
                },
            )
        else:
            self.dispatch({"type": "track", "track": track, "ctrl": ctrl, "value": val})

    def _cb_osc_glob(self, path, args):
        [_, ctrl, value] = args[:3]
        if ctrl == "selected_loop_num":
            self.dispatch(globAction(ctrl, int(value)))
        elif ctrl == "sync_source":
            self.dispatch(globAction(ctrl, int(value)))
        elif ctrl == "eighth_per_cycle":
            self.dispatch(globAction(ctrl, int(value)))
        else:
            self.dispatch(globAction(ctrl, value))

    def _cb_osc_sessions(self, path, args):
        self.dispatch(deviceAction("sessions", args))

    def reducer(self, state=None, action=None):
        if state is None:
            state = {"tracks": []}

        if action is None:
            return state

        if action["type"] == "track":
            # logging.debug(f"action {action}")
            return on_update_track(action, state)
        elif action["type"] == "empty-track":
            return assoc_path(state, ["tracks", action["value"]], {})
        elif action["type"] == "device":
            return assoc_path(state, ["device", action["setting"]], action["value"])
        elif action["type"] == "offsetUp":
            max_offset = 1  # ==> -1, which is all!
            cur_offset = getLoopoffset(state)
            return assoc_path(state, PATH_LOOP_OFFSET, min(cur_offset + 1, max_offset))
        elif action["type"] == "offsetDown":
            min_offset = min(
                0, (ROWS - 1) - self.loopcount
            )  # Leave last (fifth) row for new loops
            cur_offset = getLoopoffset(state)
            return assoc_path(state, PATH_LOOP_OFFSET, max(cur_offset - 1, min_offset))
        elif action["type"] == "glob":
            return assoc_path(state, ["glob", action["setting"]], action["value"])
        elif action["type"] == "batch":
            for batch_action in action["value"]:
                state = self.reducer(state, batch_action)
            return state
        else:
            return state

    def dispatch(self, action):
        # logging.debug(f"type {type}; action {action}")
        self.state = self.reducer(self.state, action)
        pads = createAllPads(self.state)
        notes = split_every(3, pads)
        for pad in notes:
            if pad[0] == 0x80:
                # For some reason simply sending a note off does not work.
                # lib_zyncore.dev_send_midi_event(self.idev_out, bytes(pad), 3)
                # The following does work, but something tells me to stay with they ctrldev_base way
                # lib_zyncore.dev_send_note_on(self.idev, 0, pad[1], 0)
                self._leds.led_off(pad[1], False)
        # @todo remove those off pads from the bulk message.
        # logging.debug(pads, len(pads))
        msg = bytes(pads)
        lib_zyncore.dev_send_midi_event(self.idev_out, msg, len(msg))
        # NOW RENDER

    def register_update(self, range):
        for ctrl in self.ctrls:
            self.request_feedback(f"/sl/{range}/register_update", "/update", ctrl)

        for ctrl in self.auto_ctrls:
            self.request_feedback(
                f"/sl/{range}/register_auto_update", "/update", ctrl, 100
            )

        for ctrl in self.globs:
            self.request_feedback("/register_update", "/glob", ctrl)

        # Ensure to get initial state after a delay
        Timer(2.0, self.get_initial_state, args=(range,)).start()

    def register_selected(self, ctrls):
        for ctrl in ctrls:
            self.request_feedback(
                "/sl/-3/register_auto_update", "/update", ("s", ctrl), ("i", 100)
            )

    def unregister_selected(self, ctrls):
        for ctrl in ctrls:
            self.request_feedback(
                "/sl/-3/unregister_auto_update", "/update", ("s", ctrl)
            )

    def get_initial_state(self, range):
        for ctrl in self.ctrls + self.auto_ctrls:
            self.request_feedback(f"/sl/{range}/get", "/update", ctrl)

        for ctrl in self.globs:
            self.request_feedback("/get", "/glob", ctrl)

    def handleInfo(self, args):
        try:
            if len(args) >= 3:
                hosturl, version, loopcount = args[:3]
                self.loopcount = int(loopcount)
        except Exception as e:
            logging.error(f"Error in info callback: {e}")

        # @todo: from zynthian_ctrldev_akai_apc_key25.py: factor out, use in zynthian_engine_sooperlooper too?

    def _try_connect_to_sooperlooper(self):
        """Attempt to connect to SooperLooper via OSC after initial delay"""
        if self._init_complete:
            return True

        # Check if enough time has passed since initialization
        elapsed = time.time() - self._init_time
        if elapsed < 10:
            logging.debug(f"Waiting for sooperlooper to start... ({elapsed:.1f}s)")
            # Schedule next attempt
            Timer(1.0, self._try_connect_to_sooperlooper).start()
            return False

        if self.osc_server is None:
            logging.debug("OSC server not initialized")
            return False

        try:
            logging.debug(f"Attempting to connect to SooperLooper on port {self.SL_PORT}...")
            self.osc_target = liblo.Address(self.SL_PORT)
            # logging.debug("Successfully connected to SooperLooper via OSC")
            logging.debug(
                "Pinging SL.                                                                                                                                                                                                                                    ..."
            )
            self.request_feedback("/ping", "/pong")
            # self._init_complete = True
            Timer(2.0, self._try_connect_to_sooperlooper).start()
            return True

        except Exception as e:
            logging.debug(f"Failed to connect to SooperLooper: {e}")
            # Retry after delay if still within reasonable time
            # if elapsed < 300:  # Try for up to 300 seconds
            #     logging.debug("Scheduling retry...")
            # Just keep on trying
            Timer(2.0, self._try_connect_to_sooperlooper).start()
            return False
