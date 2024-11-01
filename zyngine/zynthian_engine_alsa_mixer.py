# -*- coding: utf-8 -*-
# ******************************************************************************
# ZYNTHIAN PROJECT: Zynthian Engine (zynthian_engine_alsa_mixer)
#
# zynthian_engine implementation for Alsa Mixer
#
# Copyright (C) 2015-2024 Fernando Moyano <jofemodo@zynthian.org>
#
# ******************************************************************************
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of
# the License, or any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# For a full copy of the GNU General Public License see the LICENSE.txt file.
#
# ******************************************************************************

import os
import re
import copy
import logging
from subprocess import check_output, PIPE, DEVNULL, STDOUT
import alsaaudio
import numpy as np

from zyncoder.zyncore import lib_zyncore
from . import zynthian_engine
from . import zynthian_controller
from zyngui import zynthian_gui_config

# ------------------------------------------------------------------------------
# ALSA Mixer Engine Class
# ------------------------------------------------------------------------------


class zynthian_engine_alsa_mixer(zynthian_engine):

    sys_dir = os.environ.get('ZYNTHIAN_SYS_DIR', "/zynthian/zynthian-sys")
    soundcard_name = os.environ.get('SOUNDCARD_NAME', "Unknown")

    # ---------------------------------------------------------------------------
    # Controllers & Screens
    # ---------------------------------------------------------------------------

    _ctrl_screens = []

    # ----------------------------------------------------------------------------
    # Config variables
    # ----------------------------------------------------------------------------

    # ---------------------------------------------------------------------------
    # Translations by device
    # ---------------------------------------------------------------------------

    device_overrides = {
        "sndrpihifiberry": {
            "Digital_0_0_level": {"name": f"Output 1 level"},
            "Digital_0_1_level": {"name": f"Output 2 level"},
            "Digital_0_0_switch": {"name": f"Output 1 mute"},
            "Digital_0_1_switch": {"name": f"Output 2 mute"},
            "ADC_0_0_level": {"name": f"Input 1 level"}, 
            "ADC_0_1_level": {"name": f"Input 2 level"}, 
            "PGA_Gain_Left_0_0_enum": {"name":f"Input 1 Gain", "graph_path": ["PGA Gain Left", 0, 0, "enum", "input_0"], "group_symbol": "input"},
            "PGA_Gain_Right_0_0_enum": {"name":f"Input 2 Gain", "graph_path": ["PGA Gain Right", 0, 0, "enum", "input_1"], "group_symbol": "input"},
            "ADC_Left_Input_0_0_enum": {"name": f"Input 1 Mode", "labels": ["Disabled", "Unbalanced Mono TS", "Unbalanced Monoe TR", "Stereo TRS to Mono", "Balanced Mono TRS"], "graph_path": ["ADC", 0, 0, "enum", "input_0"], "group_symbol": "input"},
            "ADC_Right_Input_0_0_enum": {"name": f"Input 2 Mode", "labels": ["Disabled", "Unbalanced Mono TS", "Unbalanced Monoe TR", "Stereo TRS to Mono", "Balanced Mono TRS"], "graph_path": ["ADC", 0, 1, "enum", "input_1"], "group_symbol": "input"}
        },
        "US16x08": {}
    }

    if soundcard_name == "ZynADAC":
        device_overrides["sndrpihifiberry"]["ADC_Left_Input_0_0_enum"]["labels"] = ["Disabled", "Unbalanced Mono TR", "Unbalanced Monoe TS", "Stereo TRS to Mono", "Balanced Mono TRS"]
        device_overrides["sndrpihifiberry"]["ADC_Right_Input_0_0_enum"]["labels"] =  ["Disabled", "Unbalanced Mono TR", "Unbalanced Monoe TS", "Stereo TRS to Mono", "Balanced Mono TRS"]

    for i in range(16):
        device_overrides["US16x08"][f"EQ_{i}_0_switch"] = {"name": f"EQ {i + 1} enable", "group_symbol": f"eq{i}", "group_name": f"EQ {i + 1}", "graph_path": ["EQ", i, 0, "switch", f"input_{i}"], "display_priority": i}
        for j, param in enumerate(["High", "MidHigh", "MidLow", "Low"]):
            device_overrides["US16x08"][f"EQ_{param}_{i}_0_level"] = {"name": f"EQ {i + 1} {param.lower()} level", "group_symbol": f"eq{i}", "group_name": f"EQ {i + 1}", "labels": [f"{j}dB" for j in range(-12, 13)], "graph_path": [f"EQ {param}", i, 0, "level", f"input_{i}"], "display_priority": 21}
        device_overrides["US16x08"][f"EQ_High_Frequency_{i}_0_level"] = {"name": f"EQ {i + 1} high freq", "group_symbol": f"eq{i}", "group_name": f"EQ {i + 1}", "labels": [f"{j:.1f}kHz" for j in np.geomspace(1.7, 18, num=32)], "display_priority": 22}
        device_overrides["US16x08"][f"EQ_MidHigh_Frequency_{i}_0_level"] = {"name": f"EQ {i + 1} midhigh freq", "group_symbol": f"eq{i}", "group_name": f"EQ {i + 1}", "labels": [f"{int(j)}Hz" for j in np.geomspace(32, 18000, num=64)], "display_priority": 23}
        device_overrides["US16x08"][f"EQ_MidHigh_Q_{i}_0_level"] = {"name": f"EQ {i + 1} midhigh Q", "group_symbol": f"eq{i}", "group_name": f"EQ {i + 1}", "labels": ["0.25", "0.5", "1", "2", "4", "8", "16"], "display_priority": 24}
        device_overrides["US16x08"][f"EQ_MidLow_Frequency_{i}_0_level"] = {"name": f"EQ {i + 1} midlow freq", "group_symbol": f"eq{i}", "group_name": f"EQ {i + 1}", "labels": [f"{int(j)}Hz" for j in np.geomspace(32, 18000, num=64)], "display_priority": 25}
        device_overrides["US16x08"][f"EQ_MidLow_Q_{i}_0_level"] = {"name": f"EQ {i + 1} midlow Q", "group_symbol": f"eq{i}", "group_name": f"EQ {i + 1}", "labels": ["0.25", "0.5", "1", "2", "4", "8", "16"], "display_priority": 26}
        device_overrides["US16x08"][f"EQ_Low_Frequency_{i}_0_level"] = {"name": f"EQ {i + 1} low freq", "group_symbol": f"eq{i}", "group_name": f"EQ {i + 1}", "labels": [f"{int(j)}Hz" for j in np.geomspace(32, 16000, num=64)], "display_priority": 27}

        device_overrides["US16x08"][f"Compressor_{i}_0_switch"] = {"name": f"Compressor {i + 1} enable", "group_symbol": f"comp{i}", "group_name": f"Compressor {i + 1}", "graph_path": ["Compressor", i, 0, "switch", f"input_{i}"], "display_priority": i}
        device_overrides["US16x08"][f"Compressor_Threshold_{i}_0_level"] = {"name": f"Compressor {i + 1} threshold", "group_symbol": f"comp{i}", "group_name": f"Compressor {i + 1}", "labels": [f"{j}dB" for j in range(-32, 1)], "display_priority": 21}
        device_overrides["US16x08"][f"Compressor_Ratio_{i}_0_level"] = {"name": f"Compressor {i + 1} ratio", "group_symbol": f"comp{i}", "group_name": f"Compressor {i + 1}", "labels": ["1.0:1", "1.1:1", "1.3:1", "1.5:1", "1.7:1", "2.0:1", "2.5:1", "3.0:1", "3.5:1", "4:1", "5:1", "6:1", "8:1", "16:1", "inf:1"], "display_priority": 22}
        device_overrides["US16x08"][f"Compressor_Attack_{i}_0_level"] = {"name": f"Compressor {i + 1} attack", "group_symbol": f"comp{i}", "group_name": f"Compressor {i + 1}", "display_priority": 23}
        device_overrides["US16x08"][f"Compressor_Release_{i}_0_level"] = {"name": f"Compressor {i + 1} release", "group_symbol": f"comp{i}", "group_name": f"Compressor {i + 1}", "display_priority": 24}
        device_overrides["US16x08"][f"Compressor_{i}_0_level"] = {"name": f"Compressor {i + 1} gain", "group_symbol": f"comp{i}", "group_name": f"Compressor {i + 1}", "labels": [f"{j}dB" for j in range(21)], "display_priority": 25}

    # ---------------------------------------------------------------------------
    # Controllers & Screens
    # ---------------------------------------------------------------------------

    _ctrl_screens = []

    # ----------------------------------------------------------------------------
    # ZynAPI variables
    # ----------------------------------------------------------------------------

    zynapi_instance = None

    # ----------------------------------------------------------------------------
    # Initialization
    # ----------------------------------------------------------------------------

    def __init__(self, state_manager=None, proc=None):
        super().__init__(state_manager)

        self.type = "Mixer"
        self.name = "Audio Levels"
        self.nickname = "MX"

        self.processor = proc

        self.audio_out = []
        self.options['midi_chan'] = False
        self.options['replace'] = False

        self.zctrls = None
        self.get_soundcard_config()

    # ---------------------------------------------------------------------------
    # Processor Management
    # ---------------------------------------------------------------------------

    def get_path(self, processor):
        return self.name

    # ---------------------------------------------------------------------------
    # MIDI Channel Management
    # ---------------------------------------------------------------------------

    # ----------------------------------------------------------------------------
    # Bank Managament
    # ----------------------------------------------------------------------------

    def get_bank_list(self, processor=None):
        return [("", None, "", None)]

    def set_bank(self, processor, bank):
        return True

    # ----------------------------------------------------------------------------
    # Preset Managament
    # ----------------------------------------------------------------------------

    def get_preset_list(self, bank):
        return [("", None, "", None)]

    def set_preset(self, processor, preset, preload=False):
        return True

    def cmp_presets(self, preset1, preset2):
        return True

    # ----------------------------------------------------------------------------
    # Controllers Managament
    # ----------------------------------------------------------------------------

    def is_headphone_amp_interface_available(self):
        try:
            return callable(lib_zyncore.set_hpvol)
        except:
            return False

    def allow_rbpi_headphones(self):
        try:
            if not self.is_headphone_amp_interface_available() and self.rbpi_device_name and self.device_name != self.rbpi_device_name:
                return True
            else:
                return False
        except:
            logging.error("Error checking RBPi headphones")
            return False

    def get_controllers_dict(self, processor=None, ctrl_list=None):
        if ctrl_list == "*":
            ctrl_list = None
        elif ctrl_list is None:
            ctrl_list = copy.copy(self.ctrl_list)

        logging.debug(f"MIXER CTRL LIST: {ctrl_list}")

        ctrls = self.get_mixer_zctrls(self.device_name, ctrl_list)

        # Add HP amplifier interface if available
        try:
            if self.is_headphone_amp_interface_available():
                ctrls["Headphone"] = {
                    'name': "Headphone",
                    'graph_path': lib_zyncore.set_hpvol,
                    'value': lib_zyncore.get_hpvol(),
                    'value_min': 0,
                    'value_max': lib_zyncore.get_hpvol_max(),
                    'is_integer': True,
                    'group_symbol': "output",
                    'group_name': "Output levels"
                }
                logging.debug(
                    "Added zyncore Headphones Amplifier volume control")
        except Exception as e:
            logging.debug(f"Can't add zyncore Headphones Amplifier: {e}")

        # Add RBPi headphones if enabled and available...
        if self.allow_rbpi_headphones() and self.state_manager and self.state_manager.get_zynthian_config("rbpi_headphones"):
            try:
                hp_ctrls = self.get_mixer_zctrls(
                    self.rbpi_device_name, ["Headphone", "PCM"])
                if len(hp_ctrls) > 0:
                    ctrls |= hp_ctrls
                else:
                    raise Exception("RBPi Headphone volume control not found!")
            except Exception as e:
                logging.error(
                    f"Can't configure RBPi headphones volume control: {e}")

        # Sort ctrls to match the configured mixer control list
        """
        if ctrl_list and len(ctrl_list) > 0:
            sorted_ctrls = {}
            for symbol in ctrl_list:
                try:
                    sorted_ctrls[symbol] = ctrls[symbol]
                except:
                    pass
            ctrls = sorted_ctrls
        """

        if processor:
            self.zctrls = processor.controllers_dict
            # Remove controls that are no longer used
            for symbol in list(self.zctrls):
                d = True
                for ctrl in ctrls:
                    if symbol == ctrl:
                        d = False
                        break
                if d:
                    del self.zctrls[symbol]
        else:
            self.zctrls = {}

        # Add new controllers or reconfigure existing ones
        for symbol, config in ctrls.items():
            if symbol in self.zctrls:
                self.zctrls[symbol].set_options(config)
            self.zctrls[symbol] = zynthian_controller(self, symbol, config)

        # Generate control screens
        self._ctrl_screens = None
        self.generate_ctrl_screens(self.zctrls)

        return self.zctrls

    def get_mixer_zctrls(self, device_name=None, ctrl_list=None):
        _ctrls = {}
        if device_name:
            device = f"hw:{device_name}"
        else:
            device = self.device
        try:
            mixer_ctrl_names = sorted(set(alsaaudio.mixers(device=device)))
            for ctrl_name in mixer_ctrl_names:
                idx = 0
                try:
                    alsaaudio.Mixer(ctrl_name, 1, -1, device)
                    ctrl_array = True
                except:
                    ctrl_array = False
                while True:
                    # Iterate through all elements of array
                    try:
                        mixer_ctrl = alsaaudio.Mixer(ctrl_name, idx, -1, device)
                        switch_cap = mixer_ctrl.switchcap() # May be arbitrary switch, not necessarily mute
                        level_cap = mixer_ctrl.volumecap() # May be arbitrary level, not necessarily volume
                        enum_vals = mixer_ctrl.getenum()
                    except Exception as e:
                        break # exceeded index in array of controls
                    io_num = idx + 1
                    if "Playback Volume" in level_cap:
                        # Control supports control of an output level parameter
                        levels = mixer_ctrl.getvolume(alsaaudio.PCM_PLAYBACK, alsaaudio.VOLUME_UNITS_PERCENTAGE)
                        ctrl_multi = ctrl_array or len(levels) > 1
                        for chan, val in enumerate(levels):
                            ctrl_range = mixer_ctrl.getrange(alsaaudio.PCM_PLAYBACK, alsaaudio.VOLUME_UNITS_PERCENTAGE)
                            if ctrl_multi:
                                name = f"{ctrl_name} {io_num}"
                            else:
                                name = ctrl_name
                            is_toggle = mixer_ctrl.getrange(alsaaudio.PCM_PLAYBACK)[1] == 1
                            if is_toggle:
                                labels = ["off", "on"]
                            else:
                                labels = None
                            symbol = f"{ctrl_name.replace(' ', '_')}_{idx}_{chan}_level"
                            if ctrl_list and symbol not in ctrl_list:
                                io_num += 1
                                continue
                            if ctrl_name == "Headphone":
                                io_num = 0 # Clumsey but we are only guestimating here
                            _ctrls[symbol] = {
                                'name': name,
                                'graph_path': [ctrl_name, idx, chan, "level", f"output_{io_num - 1}"],
                                    'value': val,
                                    'value_min': ctrl_range[0],
                                    'value_max': ctrl_range[1],
                                    'is_toggle': is_toggle,
                                    'is_integer': True,
                                    'labels' : labels,
                                    'processor': self.processor,
                                    'group_symbol': "output",
                                    'group_name': "Output levels",
                                    'display_priority': 100000 + io_num
                                }
                            io_num += 1
                    elif "Capture Volume" in level_cap:
                        # Control supports control of an input level parameter
                        levels = mixer_ctrl.getvolume(alsaaudio.PCM_CAPTURE, alsaaudio.VOLUME_UNITS_PERCENTAGE)
                        ctrl_multi = ctrl_array or len(levels) > 1
                        for chan, val in enumerate(levels):
                            ctrl_range = mixer_ctrl.getrange(alsaaudio.PCM_CAPTURE, alsaaudio.VOLUME_UNITS_PERCENTAGE)
                            if ctrl_multi:
                                name = f"{ctrl_name} {io_num}"
                            else:
                                name = f"{ctrl_name}"
                            is_toggle = mixer_ctrl.getrange(alsaaudio.PCM_CAPTURE)[1] == 1
                            if is_toggle:
                                labels = ["off", "on"]
                            else:
                                labels = None
                            symbol = f"{ctrl_name.replace(' ', '_')}_{idx}_{chan}_level"
                            if ctrl_list and symbol not in ctrl_list:
                                io_num += 1
                                continue
                            _ctrls[symbol] = {
                                'name': name,
                                'graph_path': [ctrl_name,idx, chan, "level", f"input_{io_num - 1}"],
                                    'value': val,
                                    'value_min': ctrl_range[0],
                                    'value_max': ctrl_range[1],
                                    'is_toggle': is_toggle,
                                    'is_integer': True,
                                    'labels' : labels,
                                    'processor': self.processor,
                                    'group_symbol': "input",
                                    'group_name': "Input levels",
                                    'display_priority': 100000 + io_num
                                }
                            io_num += 1
                    elif "Volume" in level_cap:
                        # Control supports control of a misc? level parameter
                        levels = mixer_ctrl.getvolume(alsaaudio.PCM_PLAYBACK, alsaaudio.VOLUME_UNITS_PERCENTAGE)
                        ctrl_multi = ctrl_array or len(levels) > 1
                        for chan, val in enumerate(levels):
                            ctrl_range = mixer_ctrl.getrange(alsaaudio.PCM_PLAYBACK, alsaaudio.VOLUME_UNITS_PERCENTAGE)
                            if ctrl_multi:
                                name = f"{ctrl_name} {io_num}"
                            else:
                                name = f"{ctrl_name}"
                            is_toggle = mixer_ctrl.getrange(alsaaudio.PCM_PLAYBACK)[1] == 1
                            if is_toggle:
                                labels = ["off", "on"]
                            else:
                                labels = None
                            symbol = f"{ctrl_name.replace(' ', '_')}_{idx}_{chan}_level"
                            if ctrl_list and symbol not in ctrl_list:
                                io_num += 1
                                continue
                            _ctrls[symbol] = {
                                'name': name,
                                'graph_path': [ctrl_name,idx, chan, "level", "other"],
                                    'value': val,
                                    'value_min': ctrl_range[0],
                                    'value_max': ctrl_range[1],
                                    'is_toggle': is_toggle,
                                    'is_integer': True,
                                    'labels' : labels,
                                    'processor': self.processor,
                                    'group_symbol': "other",
                                    'group_name': "Other controls",
                                    'display_priority': 100000 + io_num
                                }
                            io_num += 1
                    io_num = idx + 1
                    if "Playback Mute" in switch_cap:
                        # Control supports control of an ouput switch parameter
                        mutes = mixer_ctrl.getmute()
                        ctrl_multi = ctrl_array or len(mutes) > 1
                        for chan, val in enumerate(mutes):
                            if ctrl_multi:
                                name = f"{ctrl_name} {io_num}"
                            else:
                                name = ctrl_name
                            symbol = f"{ctrl_name.replace(' ', '_')}_{idx}_{chan}_switch"
                            if ctrl_list and symbol not in ctrl_list:
                                io_num += 1
                                continue
                            _ctrls[symbol] = {
                                'name': name,
                                'graph_path': [ctrl_name, idx, chan, "switch", f"output_{io_num - 1}"],
                                    'value': val,
                                    'value_min': 0,
                                    'value_max': 1,
                                    'is_toggle': True,
                                    'is_integer': True,
                                    'labels': ["off", "on"],
                                    'processor': self.processor,
                                    'group_symbol': "output",
                                    'group_name': "Output levels",
                                    'display_priority': 100000 + io_num
                                }
                            io_num += 1
                    elif "Capture Mute" in switch_cap:
                        # Control supports control of an output switch parameter
                        mutes = mixer_ctrl.getrec()
                        ctrl_multi = ctrl_array or len(mutes) > 1
                        for chan, val in enumerate(mutes):
                            if ctrl_multi:
                                name = f"{ctrl_name} {io_num}"
                            else:
                                name = ctrl_name
                            symbol = f"{ctrl_name.replace(' ', '_')}_{idx}_{chan}_switch"
                            if ctrl_list and symbol not in ctrl_list:
                                io_num += 1
                                continue
                            _ctrls[symbol] = {
                                'name': name,
                                'graph_path': [ctrl_name, idx, chan, "switch", f"input_{io_num - 1}"],
                                    'value': val,
                                    'value_min': 0,
                                    'value_max': 1,
                                    'is_toggle': True,
                                    'is_integer': True,
                                    'labels': ["off", "on"],
                                    'processor': self.processor,
                                    'group_symbol': "input",
                                    'group_name': "Input levels",
                                    'display_priority': 100000 + io_num
                                }
                            io_num += 1
                    elif "Mute" in switch_cap:
                        # Control supports control of a misc? switch parameter
                        mutes = mixer_ctrl.getmute()
                        ctrl_multi = ctrl_array or len(mutes) > 1
                        for chan, val in enumerate(mutes):
                            if ctrl_multi:
                                name = f"{ctrl_name} {io_num}"
                            else:
                                name = ctrl_name
                            symbol = f"{ctrl_name.replace(' ', '_')}_{idx}_{chan}_switch"
                            if ctrl_list and symbol not in ctrl_list:
                                io_num += 1
                                continue
                            _ctrls[symbol] = {
                                'name': name,
                                'graph_path': [ctrl_name, idx, chan, "switch", "other"],
                                    'value': val,
                                    'value_min': 0,
                                    'value_max': 1,
                                    'is_toggle': True,
                                    'is_integer': True,
                                    'labels': ["off", "on"],
                                    'processor': self.processor,
                                    'group_symbol': "other",
                                    'group_name': "Other controls",
                                    'display_priority': 100000 + io_num
                                }
                            io_num += 1
                    io_num = idx + 1
                    if enum_vals:
                        # Control allows selection from a list
                        if ctrl_array:
                            name = f"{ctrl_name} {io_num}"
                        else:
                            name = ctrl_name
                        symbol = f"{ctrl_name.replace(' ', '_')}_{idx}_0_enum"
                        if ctrl_list and symbol not in ctrl_list:
                            idx += 1
                            continue
                        _ctrls[symbol] = {
                            'name': name,
                            'graph_path': [ctrl_name, idx, 0, "enum", "other"],
                            'labels': enum_vals[1],
                            'ticks': list(range(len(enum_vals[1]))),
                            'value': enum_vals[1].index(enum_vals[0]),
                            'value_min': 0,
                            'value_max': len(enum_vals[1]) - 1,
                            'is_toggle': False,
                            'is_integer': True,
                            'processor': self.processor,
                            'group_symbol': "other",
                            'group_name': "Other controls",
                            'display_priority': 100000 + io_num
                        }
                        io_num += 1
                    idx += 1

        except Exception as err:
            logging.error(err)

        # Apply soundcard specific overrides
        if self.device_name in self.device_overrides:
            for ctrl in self.device_overrides[self.device_name]:
                try:
                    _ctrls[ctrl] |= self.device_overrides[self.device_name][ctrl]
                except:
                    pass # There may be hidden controls

        return _ctrls

    def send_controller_value(self, zctrl):
        try:
            if callable(zctrl.graph_path):
                zctrl.graph_path(zctrl.value)
            else:
                name = zctrl.graph_path[0]
                idx = zctrl.graph_path[1]
                chan = zctrl.graph_path[2]
                type = zctrl.graph_path[3]
                if type == "level":
                    if zctrl.group_symbol == "output":
                        alsaaudio.Mixer(name, idx, -1, self.device).setvolume(zctrl.value, chan, alsaaudio.PCM_PLAYBACK, alsaaudio.VOLUME_UNITS_PERCENTAGE)
                    else:
                        alsaaudio.Mixer(name, idx, -1, self.device).setvolume(zctrl.value, chan, alsaaudio.PCM_CAPTURE, alsaaudio.VOLUME_UNITS_PERCENTAGE)
                elif type == "switch":
                        alsaaudio.Mixer(name, idx, -1, self.device).setmute(zctrl.value, chan)
                elif type == "enum":
                        alsaaudio.Mixer(name, idx, -1, self.device).setenum(zctrl.value)
        except Exception as err:
            logging.error(err)

    # ----------------------------------------------------------------------------
    # MIDI CC processing
    # ----------------------------------------------------------------------------

    def midi_control_change(self, chan, ccnum, val):
        for ch in range(0, 16):
            try:
                self.learned_cc[ch][ccnum].midi_control_change(val)
            except:
                pass

    # --------------------------------------------------------------------------
    # Special
    # --------------------------------------------------------------------------

    def get_soundcard_config(self):
        try:
            jack_opts = os.environ.get('JACKD_OPTIONS')
            res = re.compile(r" hw:([^\s]+) ").search(jack_opts)
            self.device_name = res.group(1)
        except:
            self.device_name = "0"
        self.device = f"hw:{self.device_name}"

        try:
            self.translations = self.translations_by_device[self.device_name]
        except:
            self.translations = {}

        try:
            cmd = self.sys_dir + "/sbin/get_rbpi_audio_device.sh"
            self.rbpi_device_name = check_output(
                cmd, shell=True).decode("utf-8")
        except:
            self.rbpi_device_name = None

        try:
            scmix = os.environ.get('SOUNDCARD_MIXER', "").replace("\\n", "")
            self.ctrl_list = [item.strip() for item in scmix.split(',')]
        except:
            self.ctrl_list = None

    # ---------------------------------------------------------------------------
    # API methods
    # ---------------------------------------------------------------------------

    @classmethod
    def init_zynapi_instance(cls):
        if not cls.zynapi_instance:
            cls.zynapi_instance = cls(None)
        else:
            logging.debug("\n\n********** REUSING INSTANCE ***********")

    @classmethod
    def refresh_zynapi_instance(cls):
        if cls.zynapi_instance:
            cls.zynapi_instance.stop()
            cls.zynapi_instance = cls(None)

    @classmethod
    def zynapi_get_controllers(cls, ctrl_list="*"):
        return cls.zynapi_instance.get_controllers_dict(None, ctrl_list)

    @classmethod
    def zynapi_get_device_name(cls):
        return cls.zynapi_instance.device_name

    @classmethod
    def zynapi_get_rbpi_device_name(cls):
        return cls.zynapi_instance.rbpi_device_name

# ******************************************************************************
