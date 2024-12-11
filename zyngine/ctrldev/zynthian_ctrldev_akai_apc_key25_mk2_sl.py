#!/usr/bin/python3
# -*- coding: utf-8 -*-
import time
import signal
from bisect import bisect
from copy import deepcopy
from functools import partial
import multiprocessing as mp
from threading import Thread, RLock, Event
import liblo
from threading import Timer

from zynlibs.zynseq import zynseq
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
from .zynthian_ctrldev_akai_apc_key25_mk2_colors import *
from .zynthian_ctrldev_akai_apc_key25_mk2_brights import *
from .zynthian_ctrldev_akai_apc_key25_mk2_buttons import *

from typing import Dict, Any, Callable
from itertools import chain, islice
# from collections import defaultdict

import functools

COLS = 8
ROWS = 5
# LED states
LED_ON = 1

TRACK_COMMANDS = [2, 6, 7, 8, 13, 12, 16, 14]
TRACK_LEVELS = [
    "in_peak_meter",
    "rec_thresh",
    "input_gain",
    "wet",
    "dry",
    "feedback",
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
    SL_STATE_UNKNOWN: {"name": "unknown", "color": COLOR_DARK_GREY, "ledmode": LED_OFF},
    SL_STATE_OFF: {"name": "off", "color": COLOR_WHITE, "ledmode": LED_BRIGHT_100},
    SL_STATE_REC_STARTING: {
        "name": "waitstart",
        "color": COLOR_RED,
        "ledmode": LED_PULSING_16,
    },
    SL_STATE_RECORDING: {
        "name": "record",
        "color": COLOR_RED,
        "ledmode": LED_BRIGHT_100,
    },
    SL_STATE_REC_STOPPING: {
        "name": "waitstop",
        "color": COLOR_RED,
        "ledmode": LED_PULSING_8,
    },
    SL_STATE_PLAYING: {"name": "play", "color": COLOR_GREEN, "ledmode": LED_BRIGHT_100},
    SL_STATE_OVERDUBBING: {
        "name": "overdub",
        "color": COLOR_PURPLE,
        "ledmode": LED_BRIGHT_100,
    },
    SL_STATE_MULTIPLYING: {
        "name": "multiply",
        "color": COLOR_AMBER,
        "ledmode": LED_BRIGHT_100,
    },
    SL_STATE_INSERTING: {
        "name": "insert",
        "color": COLOR_PINK_WARM,
        "ledmode": LED_BRIGHT_100,
    },
    SL_STATE_REPLACING: {
        "name": "replace",
        "color": COLOR_PINK_LIGHT,
        "ledmode": LED_BRIGHT_100,
    },
    SL_STATE_SUBSTITUTING: {
        "name": "substitute",
        "color": COLOR_PINK,
        "ledmode": LED_BRIGHT_100,
    },
    SL_STATE_DELAYING: {"name": "delay", "color": COLOR_RED, "ledmode": LED_BRIGHT_10},
    SL_STATE_MUTED: {
        "name": "mute",
        "color": COLOR_DARK_GREEN,
        "ledmode": LED_BRIGHT_100,
    },
    SL_STATE_SCRATCHING: {
        "name": "scratch",
        "color": COLOR_BLUE,
        "ledmode": LED_BRIGHT_100,
    },
    SL_STATE_PLAYING_ONCE: {
        "name": "oneshot",
        "color": COLOR_LIME_DARK,
        "ledmode": LED_PULSING_8,
    },
    SL_STATE_PAUSED: {
        "name": "pause",
        "color": COLOR_GREEN_YELLOW,
        "ledmode": LED_BRIGHT_100,
    },
    SL_STATE_UNDO_ALL: {
        "name": "undo_all",
        "color": COLOR_DARK_GREY,
        "ledmode": LED_BRIGHT_100,
    },
    SL_STATE_UNDO: {
        "name": "undo_all",
        "color": COLOR_DARK_GREY,
        "ledmode": LED_BRIGHT_50,
    },
    SL_STATE_REDO: {
        "name": "redo",
        "color": COLOR_DARK_GREY,
        "ledmode": LED_BRIGHT_50,
    },
    SL_STATE_REDO_ALL: {
        "name": "redo_all",
        "color": COLOR_DARK_GREY,
        "ledmode": LED_BRIGHT_100,
    },
    SL_STATE_OFF_MUTED: {
        "name": "offmute",
        "color": COLOR_RED,
        "ledmode": LED_BRIGHT_100,
    },  # undocumented
    SL_STATE_TRIGGER_PLAY: {
        "name": "trigger_play",
        "color": COLOR_GREEN,
        "ledmode": LED_BRIGHT_100,
    },
}
SETTINGCOLORS = [
    COLOR_BLUE,
    COLOR_LIME,
    COLOR_GREEN,
    COLOR_DARK_GREEN,
    COLOR_PURPLE,
    COLOR_PINK_LIGHT,
    # -3 = internal,  -2 = midi, -1 = jack, 0 = none, # > 0 = loop number (1 indexed)
    [
        COLOR_WHITE,
        COLOR_ORANGE,
        COLOR_RED,
        COLOR_DARK_GREY,
        COLOR_BLUE,
        COLOR_BLUE_DARK,
    ],
    [COLOR_WHITE, COLOR_ORANGE, COLOR_BROWNISH_RED, COLOR_BLUE],
]
PATH_LOOP_OFFSET = ["device", "loopoffset"]
DEVICEMODES = ["loops", "sessionsave", "sessionload"]
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
matrixPadLedmode = {".": LED_BRIGHT_100, "_": LED_BRIGHT_10}
matrixPadColor = {".": COLOR_WHITE, "_": COLOR_DARK_GREY}

# Variables we do not want to store in state

show8ths = False
shifted = False


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


def over(lens_path, func, state):
    """Applies a function to the value at the specified lens path in the state."""
    # This is a simplified version; you would need to implement lens logic
    value = state
    for key in lens_path:
        value = value[key]
    new_value = func(value)
    d = state
    for key in lens_path[:-1]:
        d = d[key]
    d[lens_path[-1]] = new_value
    return state


def split_every(n, iterable):
    """Split an iterable into chunks of size n."""
    it = iter(iterable)
    while chunk := list(islice(it, n)):
        yield chunk


def overlay(*arrays):
    # Step 1: Split each array into chunks of 3
    split_arrays = [list(split_every(3, array)) for array in arrays]

    # Step 2: Concatenate all the arrays into a single list
    concatenated = list(chain.from_iterable(split_arrays))

    # Step 3: Remove duplicates based on the second element
    unique = {tuple(item): item for item in concatenated}.values()

    # Step 4: Sort by the second element
    sorted_unique = sorted(unique, key=lambda x: x[1])

    # Step 5: Flatten the list (if needed)
    flattened = list(chain.from_iterable(sorted_unique))

    return flattened


# PAD FUNCTIONS


def rowStartPad(y):
    return (ROWS - 1 - y) * COLS


def rowPads(track):
    padoffset = rowStartPad(track)
    return map(lambda n: n + padoffset, range(0, COLS))


# Pad coloring
def padBrightnessForLevel(num, level):
    pos = (num * level,)
    roundedpos = (pos // 1,)
    last = LED_BRIGHTS[((num - 1) * (pos - roundedpos)) // 1]
    return (
        lambda x: LED_BRIGHT_100
        if x < roundedpos
        else last
        if x == roundedpos
        else LED_BRIGHT_10
    )


def panPads(value):
    pos = (2 * (8 - 1) * value,)
    roundedpos = round(pos)
    extrapad = roundedpos % 2
    firstpad = (roundedpos / 2) // 1
    # Step 3: Remove duplicates based on the second element
    unique = {tuple(item): item for item in [firstpad, firstpad + extrapad]}.values()
    return unique


def get_cell_led_mode_fn(state: Dict[str, Any]) -> Callable:
    def cond_fn(track, y):
        # Check for device pan
        if "device" in state and "pan" in state["device"]:
            if track["channel_count"] == 2:
                pads_left = panPads(track["pan_1"])
                pads_right = panPads(track["pan_2"])
                both = set(pads_left) & set(pads_right)
                any_pads = set(pads_left) | set(pads_right)

                return lambda x: (
                    LED_BRIGHT_100
                    if x in both
                    else LED_BRIGHT_75
                    if x in any_pads
                    else LED_BRIGHT_25
                )
            pads = panPads(track["pan_1"])
            return lambda x: LED_BRIGHT_100 if x in pads else LED_BRIGHT_25

        # Check for track levels
        if showTrackLevels(state):

            def track_level_fn(track, i):
                return lambda xpad: (
                    padBrightnessForLevel(5, TRACK_LEVELS[xpad])(4 - i)
                )

            return track_level_fn(track, y)  # NO Example index

        # Check for device levels
        if "device" in state and "levels" in state["device"]:
            return lambda x: padBrightnessForLevel(8, track["wet"])

        # Default case
        state_value = track.get("state", SL_STATE_UNKNOWN)
        
        pos = 0 if track.get("loop_len", 0) == 0 else 8 * (track.get("loop_pos", 0) / track.get("loop_len", 1))
        rounded_pos = int(pos)
        # last = LED_BRIGHTS[
        #     min(3, int(7 * (pos - rounded_pos)))
        # ]  # Ensure index is within bounds
        led_mode = SL_STATES[state_value]["ledmode"]

        return lambda x: (
            LED_BRIGHT_100
            if led_mode == LED_BRIGHT_100 and x <= rounded_pos
            else LED_BRIGHT_25
            if led_mode == LED_BRIGHT_100
            else led_mode
        )

    return cond_fn


def get_cell_color_fn(state: Dict[str, Any]) -> Callable:
    def cond_fn(track):
        # Check for device pan
        if "device" in state and "pan" in state["device"]:
            if track["channel_count"] == 2:
                pads_left = panPads(track["pan_1"])
                pads_right = panPads(track["pan_2"])
                both = set(pads_left) & set(pads_right)
                any_pads = set(pads_left) | set(pads_right)

                return lambda x: (
                    COLOR_PURPLE
                    if x in both
                    else COLOR_RED
                    if x in pads_left
                    else COLOR_BLUE
                    if x in pads_right
                    else SL_STATES[track["state"]]["color"]
                )
            state_value = track.get("state", SL_STATE_UNKNOWN)
            return lambda x: SL_STATES[state_value]["color"]

        # Check for track levels
        if showTrackLevels(state):

            def track_level_fn(track, i):
                return lambda xpad: levelcolors[xpad]  # Example implementation

            return track_level_fn(track, 0)  # Example index

        # Check for device levels
        if "device" in state and "levels" in state["device"]:
            state_value = track.get("state", SL_STATE_UNKNOWN)
            return lambda x: (
                SL_STATES[state_value]["color"]
                if state_value == SL_STATE_UNKNOWN
                else COLOR_BLUE_LIGHT
                if state_value == SL_STATE_OFF
                else COLOR_BLUE
            )

        # Default case
        state_value = track.get("state", SL_STATE_UNKNOWN)
        return lambda x: SL_STATES[state_value]["color"]

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
        track = tracks.get(tracknum, {})
        cellLedModeFn = trackLedModeFn(track, y)
        cellColorFn = trackColorFn(track)

        state = track.get("state", SL_STATE_UNKNOWN)
        next_state = track.get("next_state")
        loop_len = track.get("loop_len")
        loop_pos = track.get("loop_pos")
        wet = track.get("wet")
        sync = track.get("sync")
        relative_sync = track.get("relative_sync")

        if not (set_syncs or showTrackLevels(storeState)) and y == 0:
            matrix.extend(toprow)
            continue

        if set_syncs and y == 0:
            padnums = rowPads(y)
            pads = []
            for x, pad in enumerate(padnums):
                pads.extend([LED_BRIGHT_50, pad, SETTINGCOLORS[x]])

            track1 = tracks.get(0, {})
            synccolor = SETTINGCOLORS[6][min(getGlob("sync_source", storeState) + 3, 5)]

            matrix.extend(
                [
                    LED_BRIGHT_100,
                    38,
                    synccolor,
                    LED_BRIGHT_100 if track1.get("quantize") else LED_BRIGHT_10,
                    39,
                    SETTINGCOLORS[7].get(track1.get("quantize"), SETTINGCOLORS[7][0]),
                    *pads,
                ]
            )
            continue

        try:
            if set_syncs:
                pads = [
                    (
                        LED_BRIGHT_100 if track.get(settings[x]) else LED_BRIGHT_10,
                        pad,
                        settingcolors[x][track.get(settings[x], 0)]
                        if isinstance(settingcolors[x], list)
                        else settingcolors[x],
                    )
                    for x, pad in enumerate(rowPads(y))
                ]
                matrix.extend(
                    [
                        LED_BRIGHT_75,
                        30,
                        COLOR_BROWN_LIGHT,
                        LED_BRIGHT_75,
                        31,
                        COLOR_BROWN_LIGHT,
                        *pads,
                    ]
                )
                continue

            for x, pad in enumerate(rowPads(y)):
                cell = [cellLedModeFn(x), pad, cellColorFn(x)]
                matrix.extend(cell)

        except Exception as e:
            print(e)
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


def get_eighths(show8ths, storeState):
    if show8ths:
        eighths = [
            item
            for pad in range(getGlob("eighth_per_cycle", storeState))
            for item in [LED_BRIGHT_100, pad, COLOR_BROWNISH_RED]
        ]
    else:
        eighths = []

    return eighths


# ACTION HELPERS


def globAction(setting, value):
    return {"type": "glob", "setting": setting, "value": value}


def deviceAction(setting, value):
    return {"type": "device", "setting": setting, "value": value}


# STATE HELPERS


def getDeviceMode(state):
    return path(["device", "mode"], state) or 0


def getDeviceSetting(setting, state):
    return path(["device", setting], state)


def getGlob(setting, state):
    return path(["glob", setting], state)


def getLoopoffset(state):
    return path(PATH_LOOP_OFFSET, state) or 1


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
    devicemode = getDeviceMode(state)
    loopoffset = getLoopoffset(state)
    set_syncs = syncMode(state)
    devicemode = max(0, getDeviceMode(state) or 0)
    levelmode = getDeviceSetting("levels", state) or 0
    panmode = getDeviceSetting("pan", state) or 0

    def ctrl_btn(btn):
        if btn == BTN_KNOB_CTRL_VOLUME:
            return [0x90, btn, levelmode]
        if btn == BTN_KNOB_CTRL_PAN:
            return [0x90, btn, panmode]  # @check Used to have to convert this to num
        if btn == BTN_KNOB_CTRL_SEND:
            return [0x90, btn, (set_syncs and 1) or 0]
        if btn == BTN_KNOB_CTRL_DEVICE:
            return [0x90, btn, devicemode]
        return []

    ctrl_keys = functools.reduce(
        lambda acc, btn: acc + ctrl_btn(btn), range(0x40, 0x48), []
    )

    if devicemode > 0:
        color = (
            COLOR_DARK_GREEN
            if DEVICEMODES[devicemode] == "sessionload"
            else COLOR_ORANGE
        )
        sessions = getDeviceSetting("sessions", state) or []
        sessionnums = functools.reduce(
            lambda acc, cur: acc + [LED_BRIGHT_100, int(cur[:-7]), color], sessions, []
        )

        def emptycellreducer(acc, cur):
            return acc + [LED_BRIGHT_25, cur, color]

        def emptyrowreducer(acc, cur):
            return acc + functools.reduce(emptycellreducer, rowPads(cur), [])

        emptycells = functools.reduce(emptyrowreducer, range(0, ROWS), [])
        return overlay(sessionnums, emptycells) + ctrl_keys

    tracks = state.get("tracks", [])
    toprow = (
        []
        if (set_syncs or showTrackLevels(state))
        else [
            [LED_BRIGHT_90, pad, SL_STATES[TRACK_COMMANDS[i]]["color"]]
            for i, pad in enumerate(rowPads(0))
        ]
    )
    toprow = list(chain.from_iterable(toprow))
    matrix = matrix_function(toprow, loopoffset, tracks, state, set_syncs)
    soft_keys = get_soft_keys(loopoffset, state)
    eighths = get_eighths(show8ths, state)

    pads = matrix + overlay(soft_keys, ctrl_keys)
    if len(pads):
        if shifted:
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
        print("\n=================================================================")
        print("APC Key 25 mk2 SL __init__ starting...")
        print(f"state_manager: {state_manager}")
        print(f"idev_in: {idev_in}, type: {type(idev_in)}")
        print(f"idev_out: {idev_out}, type: {type(idev_out)}")

        print("Calling parent class __init__...")
        # Call parent class initializer explicitly
        #        zynthian_ctrldev_base.__init__(self, state_manager, idev_in, idev_out)
        super().__init__(state_manager, idev_in, idev_out)

        print("Parent class __init__ completed")
        print(f"self.idev_out after parent init: {self.idev_out}")
        print("APC Key 25 mk2 SL __init__ completed")
        print("=================================================================\n")

        self._state_manager = state_manager
        self._init_complete = False
        self._shutting_down = False
        self._leds = None
        self.osc_server = None
        self.osc_target = None
        self._loop_states = {}
        self._init_time = 0

        self._leds = FeedbackLEDs(idev_out)
        self.loopcount = 0
        self.state = {}
        # Light up first button in each row
        self._leds.led_state(82, LED_ON)  # First snapshot
        self._leds.led_state(64, LED_ON)  # First zs3

        # if self._leds is None:
        #     print("Initializing LED controller...")
        #     self._leds = FeedbackLEDs(idev_out)
        #     print("LED controller initialized")

    def refresh(self):
        """Refresh device state"""
        # if self._try_connect_to_sooperlooper():
        #     self.update_loop_states()

    def init(self):
        print("Starting APC Key 25 mk2 sl init sequence")
        """Initialize the device"""
        if self._shutting_down:
            print("Skipping initialization - device is shutting down")
            return

        self._init_complete = False
        super().init()

        if not self._shutting_down:
            print("Initializing zynthian_ctrldev_akai_apc_key25...")

            # Initialize LED controller
            if self._leds is None:
                print("Initializing LED controller...")
                self._leds = FeedbackLEDs(self.idev_out)
                print("LED controller initialized")

            # Initialize OSC server
            try:
                print("Creating OSC server...")
                self.osc_server = liblo.ServerThread()
                self.osc_server_port = self.osc_server.get_port()
                self.osc_server_url = f"osc.udp://localhost:{self.osc_server_port}"
                print(f"OSC server initialized on port {self.osc_server_port}")

                # Register OSC methods
                print("Registering OSC methods...")
                self.osc_server.add_method("/error", "s", self._cb_osc_error)
                self.osc_server.add_method("/pong", "ssf", self._cb_osc_pong)
                self.osc_server.add_method("/info", "ssi", self._cb_osc_info)
                self.osc_server.add_method("/update", "isf", self._cb_osc_update)
                self.osc_server.add_method("/glob", "isf", self._cb_osc_glob)
                # self.osc_server.add_method("/sessions", "sf", self._cb_osc_sessions)
                self.osc_server.add_method(None, None, self._cb_osc_fallback)

                # Start the OSC server
                print("Starting OSC server...")
                self.osc_server.start()
                print("OSC server started successfully")

                print("Attempting to connect to SooperLooper...")
                # Start connection attempt timer
                self._init_time = time.time()
                self._try_connect_to_sooperlooper()

            except liblo.ServerError as err:
                print(f"Error initializing OSC: {err}")
                self.osc_server = None

    def end(self):
        super().end()

    def refresh(self):
        # PadMatrix is handled in volume/pan modes (when mixer handler is active)
        pass

    def midi_event(self, ev):
        pass

    def request_feedback(self, address, path, *args):
        self.osc_server.send(self.osc_target, address, *args, self.osc_server_url, path)

    def just_send(self, address, *args):
        self.osc_server.send(self.osc_target, address, *args)

    def range(self, start=0):
        return f"[{start}-{self.loopcount - 1}]"

    def _cb_osc_fallback(self, path, args, types, src):
        """Fallback callback for unhandled OSC messages"""
        print(f"Received unhandled OSC message: {path} {args}")

    def _cb_osc_error(self, path, args):
        """Error callback for errors on loading or saving sessions"""
        print(f"Error: {path} {args}")

    def _cb_osc_pong(self, path, args):
        """Callback for info messages from SooperLooper"""
        self.request_feedback("/register", "/info")
        self.handleInfo(args)
        self.register_update(self.range(0))
        self.just_send("/set", "smart_eighths", 0)

    def _cb_osc_info(self, path, args):
        """Callback for info messages from SooperLooper"""
        old_count = self.loopcount
        self.handleInfo(args)

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
        self.dispatch(globAction(ctrl, value))

    def _cb_osc_sessions(self, path, args):
        self.dispatch(deviceAction("sessions", args))

    def reducer(self, state=None, action=None):
        if state is None:
            state = {"tracks": []}

        if action is None:
            return state

        if action["type"] == "track":
            print(f"action {action}")
            return on_update_track(action, state)
        elif action["type"] == "empty-track":
            return assoc_path(state, ["tracks", action["value"]], {})
        elif action["type"] == "device":
            return assoc_path(state, ["device", action["setting"]], action["value"])
        elif action["type"] == "offsetUp":
            max_offset = 1  # ==> -1, which is all!
            return over(
                PATH_LOOP_OFFSET, lambda offset=1: min(offset + 1, max_offset), state
            )
        elif action["type"] == "offsetDown":
            min_offset = min(
                0, 4 - self.loopcount
            )  # Leave last (fifth) row for new loops
            return over(
                PATH_LOOP_OFFSET, lambda offset=1: max(offset - 1, min_offset), state
            )
        elif action["type"] == "glob":
            return assoc_path(state, ["glob", action["setting"]], action["value"])
        elif action["type"] == "batch":
            for batch_action in action["value"]:
                state = self.reducer(state, batch_action)
            return state
        else:
            return state

    def dispatch(self, action):
        print(f"type {type}; action {action}")
        self.state = self.reducer(self.state, action)
        pads = createAllPads(self.state)
        print(pads, len(pads))
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

    def get_initial_state(self, range):
        for ctrl in self.ctrls + self.auto_ctrls:
            self.request_feedback(f"/sl/{range}/get", "/update", ctrl)

        for ctrl in self.globs:
            self.request_feedback("/get", "/glob", ctrl)

    def handleInfo(self, args):
        try:
            if len(args) >= 3:
                hosturl, version, loopcount = args[:3]
                self.loopcount = loopcount
        except Exception as e:
            print(f"Error in info callback: {e}")

        # @todo: from zynthian_ctrldev_akai_apc_key25.py: factor out, use in zynthian_engine_sooperlooper too?

    def _try_connect_to_sooperlooper(self):
        """Attempt to connect to SooperLooper via OSC after initial delay"""
        if self._init_complete:
            return True

        # Check if enough time has passed since initialization
        elapsed = time.time() - self._init_time
        if elapsed < 20:
            print(f"Waiting for sooperlooper to start... ({elapsed:.1f}s)")
            # Schedule next attempt
            Timer(1.0, self._try_connect_to_sooperlooper).start()
            return False

        if self.osc_server is None:
            print("OSC server not initialized")
            return False

        try:
            print(f"Attempting to connect to SooperLooper on port {self.SL_PORT}...")
            self.osc_target = liblo.Address(self.SL_PORT)
            print("Successfully connected to SooperLooper via OSC")
            print("Registering for automatic updates...")

            self.request_feedback("/ping", "/pong")
            self._init_complete = True

            return True
        except Exception as e:
            print(f"Failed to connect to SooperLooper: {e}")
            # Retry after delay if still within reasonable time
            if elapsed < 300:  # Try for up to 300 seconds
                print("Scheduling retry...")
                Timer(2.0, self._try_connect_to_sooperlooper).start()
            return False
