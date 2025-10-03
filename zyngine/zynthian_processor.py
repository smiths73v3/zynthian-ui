# -*- coding: utf-8 -*-
# *****************************************************************************
# ZYNTHIAN PROJECT: Zynthian processor (zynthian_processor)
#
# zynthian processor
#
# Copyright (C) 2015-2023 Fernando Moyano <jofemodo@zynthian.org>
# Brian Walton <riban@zynthian.org>
#
# *****************************************************************************
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
# *****************************************************************************

import os
import copy
import logging
import traceback

# Zynthian specific modules
from zyncoder.zyncore import lib_zyncore


class zynthian_processor:

    # ---------------------------------------------------------------------------
    # Data dirs
    # ---------------------------------------------------------------------------

    data_dir = os.environ.get('ZYNTHIAN_DATA_DIR', "/zynthian/zynthian-data")
    my_data_dir = os.environ.get('ZYNTHIAN_MY_DATA_DIR', "/zynthian/zynthian-my-data")
    ex_data_dir = os.environ.get('ZYNTHIAN_EX_DATA_DIR', "/media/usb0")

    # ------------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------------

    def __init__(self, eng_code, eng_info, id=None):
        """ Create an instance of a processor

        A processor represents a block within a chain.
        It provides access to a worker engine
        eng_code : Short-code processor type
        eng_info : Dictionary with engine's info
        id : UID for processor (Default: None)
        """

        self.id = id
        self.eng_code = eng_code
        self.eng_info = eng_info
        self.type = eng_info["TYPE"]
        self.engine = None
        self.name = eng_info["NAME"]
        self.midi_chan = None
        self.midi_chan_engine = None
        self.jackname = None
        self.chain = None
        self.chain_id = None

        self.bank_list = []
        self.bank_index = 0
        self.bank_name = None
        self.bank_info = None
        self.bank_subdir_info = None
        self.bank_msb = 0
        # system, user, external => [offset, n]
        self.bank_msb_info = [[0, 0], [0, 0], [0, 0]]

        self.show_fav_presets = False
        self.preset_list = []
        self.preset_index = 0
        self.preset_name = None
        self.preset_info = None
        self.preset_subdir_info = None
        self.preset_bank_index = None
        self.preset_loaded = None

        self.preload_index = None
        self.preload_name = None
        self.preload_info = None

        self.controllers_dict = {}  # Map of zctrls indexed by symbol
        self.ctrl_screens_dict = {}
        self.current_screen_index = -1
        self.auto_save_bank = False
        self.midi_autolearn = True  # When true, auto-learn MIDI-CC based controllers

    def get_jackname(self, engine=False):
        """ Get the jackname for the processor's engine

        engine : True to get engine's raw jackname
        Returns : jackname as string

        """

        if not engine and self.jackname:
            return self.jackname
        if self.engine:
            return self.engine.get_jackname()
        return ''

    def set_engine(self, engine):
        """Set engine that this processor uses"""

        self.engine = engine
        self.engine.add_processor(self)

    def get_name(self):
        """Get name of processor"""

        if self.engine:
            return self.engine.get_name(self)

    def set_chain(self, chain):
        """Set the chain to which the processor belongs"""

        try:
            self.chain = chain
            self.chain_id = chain.chain_id
        except:
            self.chain = None
            self.chain_id = None

    def get_chain(self):
        """Get the chain to which the processor belongs, if any"""

        return self.chain

    def get_chain_id(self):
        """Get ID of the chain to which the processor belongs, if any"""

        return self.chain_id

    # ---------------------------------------------------------------------------
    # MIDI autolearn CC controllers
    # ---------------------------------------------------------------------------

    def set_midi_autolearn(self, midi_autolearn):
        self.midi_autolearn = midi_autolearn

    def get_midi_autolearn(self):
        return self.midi_autolearn

    # ---------------------------------------------------------------------------
    # MIDI Channel Management
    # ---------------------------------------------------------------------------

    def set_midi_chan(self, midi_chan):
        """Set processor (and its engines) MIDI channel

        midi_chan : MIDI channel 0..15 or None
        """

        self.midi_chan = midi_chan
        if self.engine:
            self.engine.set_midi_chan(self)
        if isinstance(midi_chan, int) and 0 <= midi_chan < 16:
            for zctrl in self.controllers_dict.values():
                zctrl.set_midi_chan(midi_chan)
            self.send_ctrlfb_midi_cc()

    def get_midi_chan(self):
        """Get MIDI channel (0..15 or None)

        TODO: Processors inherit MIDI channel from chain
        """
        return self.midi_chan

    # ---------------------------------------------------------------------------
    # Bank Management
    # ---------------------------------------------------------------------------

    def get_bank_list(self):
        self.bank_list = self.engine.get_bank_list(self)
        logging.info(f"Loaded {len(self.bank_list)} banks")
        # logging.debug(f"BANK LIST => \n{self.bank_list}")

        # Calculate info for bank_msb => Is this used by someone?
        i = 0
        # system, user, external => [offset, n]
        self.bank_msb_info = [[0, 0], [0, 0], [0, 0]]
        for bank in self.bank_list:
            if bank[0] is None or not isinstance(bank[0], str):
                continue
            if bank[0].startswith(self.ex_data_dir):
                self.bank_msb_info[0][0] += 1
                self.bank_msb_info[1][0] += 1
                self.bank_msb_info[2][1] += 1
                i += 1
            elif bank[0].startswith(self.my_data_dir):
                self.bank_msb_info[0][0] += 1
                self.bank_msb_info[1][1] += 1
                i += 1
            else:
                break
        self.bank_msb_info[0][1] = len(self.bank_list) - i

        # Add favourites virtual bank if there is some preset marked as favourite
        if self.engine.show_favs_bank and len(self.engine.get_preset_favs(self)) > 0:
            self.bank_list = [["*FAVS*", 0, "*** Favorites ***"]] + self.bank_list
            for i in range(3):
                self.bank_msb_info[i][0] += 1

        # logging.debug(f"BANK MSB INFO => \n{self.bank_msb_info}")
        return self.bank_list

    def reset_bank(self):
        """Reset bank to default (empty)"""

        self.bank_index = 0
        self.bank_name = None
        self.bank_info = None

    def set_bank(self, bank_index, set_engine=True):
        """Set processor's engine bank by index

        bank_index : Index of the bank to select
        set_engine : True to set engine's bank
        Returns : True if bank selected, None if more bank selection steps required or False on failure
        """

        if bank_index < len(self.bank_list):
            bank_name = self.bank_list[bank_index][2]

            if bank_name is None:
                return False

            if bank_index != self.bank_index or self.bank_name != bank_name:
                set_engine_needed = True
                logging.info(f"Bank selected: {bank_name} ({bank_index})")
            else:
                set_engine_needed = False
                logging.info(f"Bank already selected: {self.bank_name} ({bank_index})")

            self.bank_index = bank_index
            self.bank_name = bank_name
            self.bank_info = copy.deepcopy(self.bank_list[bank_index])

            if set_engine and set_engine_needed:
                return self.engine.set_bank(self, self.bank_info)
            else:
                return True

        return False

    def set_bank_by_info(self, bank_info, set_engine=True):
        try:
            self.bank_name = bank_info[2]
            self.bank_info = copy.deepcopy(bank_info)
            for i in range(len(self.bank_list)):
                if self.bank_name == self.bank_list[i][2]:
                    self.bank_index = i
                    break
        except:
            pass
        if set_engine:
            return self.engine.set_bank(self, self.bank_info)

    def set_bank_by_name(self, bank_name, set_engine=True):
        """Set processor's engine bank by name

        bank_name:- Name of bank to select
        set_engine : True to set engine's bank
        Returns : True on success
        #TODO Optimize search!!
        """

        for i in range(len(self.bank_list)):
            if bank_name == self.bank_list[i][2]:
                return self.set_bank(i, set_engine)
        return False

    # TODO Optimize search!!
    def set_bank_by_id(self, bank_id, set_engine=True):
        """Set processor's engine bank by id

        bank_id : ID of the bank to select
        set_engine : True to set engine's bank
        Returns : True if bank selected, None if more bank selection steps required or False on failure
        """

        for i in range(len(self.bank_list)):
            if bank_id == self.bank_list[i][0]:
                return self.set_bank(i, set_engine)
        return False

    def get_bank_name(self):
        """Get current bank name"""
        return self.bank_name

    def get_bank_index(self):
        """Get current bank index"""

        for index, bank_info in enumerate(self.bank_list):
            if self.bank_info and self.bank_info == bank_info:
                return index
        return self.bank_index  # TODO: can we lose or optimise this?

    # ---------------------------------------------------------------------------
    # Preset Management
    # ---------------------------------------------------------------------------

    def load_preset_list(self):
        """Load bank list for processor"""

        preset_list = []

        if self.show_fav_presets:
            for v in self.get_preset_favs().values():
                preset_list.append(v[1])
        elif self.bank_info:
            for preset in self.engine.get_preset_list(self.bank_info, self):
                if self.engine.is_preset_fav(preset):
                    preset[2] = "❤" + preset[2]
                preset_list.append(preset)
        else:
            return
        self.preset_list = preset_list
        logging.info(f"Loaded {len(self.preset_list)} presets")
        # logging.debug(f"PRESET LIST => \n{self.preset_list}")

    def reset_preset(self):
        """Reset preset to default (empty)"""
        logging.debug("PRESET RESET!")
        self.preset_index = 0
        self.preset_name = None
        self.preset_info = None


    def set_preset(self, preset_index, set_engine=True, force_set_engine=True):
        """Set the processor's engine preset

        preset_index : Index of preset or preset_info
        set_engine : True to set the engine preset???
        force_set_engine : True to force engine set???
        Returns : True on success
        """

        if isinstance(preset_index, int) and preset_index < len(self.preset_list):
            preset_id = str(self.preset_list[preset_index][0])
            preset_name = self.preset_list[preset_index][2]
            preset_info = copy.deepcopy(self.preset_list[preset_index])
        elif isinstance(preset_index, list):
            preset_info = copy.deepcopy(preset_index)
            preset_id = preset_info[0]
            preset_name = preset_info[2]
            preset_index = self.find_preset_index_by_id(preset_id)
        else:
            return False

        if not preset_name:
            return False

        # Remove favorite marker char
        if preset_name[0] == '❤':
            preset_name = preset_name[1:]

        # Check if preset is in favorites pseudo-bank and set real bank if needed
        if preset_id in self.engine.preset_favs:
            bank_name = self.engine.preset_favs[preset_id][0][2]
            if bank_name != self.bank_name:
                self.set_bank_by_name(bank_name)

        # Check if preset is already loaded
        if not force_set_engine and self.engine.cmp_presets(preset_info, self.preset_info):
            logging.info(f"Preset already selected: {preset_name} ({preset_index})")
            # Check if some other preset is preloaded
            if self.preload_info and not self.engine.cmp_presets(self.preload_info, self.preset_info):
                set_engine_needed = True
            else:
                set_engine_needed = False
        else:
            set_engine_needed = True
            logging.info(f"Preset selected: {preset_name} ({preset_index})")

        if preset_index is not None:
            self.preset_index = preset_index
        self.preset_name = preset_name
        self.preset_info = preset_info
        self.preset_bank_index = self.bank_index

        # Clean preload info
        self.preload_index = None
        self.preload_name = None
        self.preload_info = None

        if set_engine:
            if set_engine_needed:
                # self.load_ctrl_config()
                return self.engine.set_preset(self, self.preset_info)
            else:
                return False

        return True

    def set_preset_by_info(self, preset_info, set_engine=True, force_set_engine=True):
        return self.set_preset(preset_info, set_engine, force_set_engine)

    def set_preset_by_name(self, preset_name, set_engine=True, force_set_engine=True):
        """Set processor's engine preset by name

        preset_name : Name of preset to select
        set_engine : True to set engine's preset???
        force_set_engine : True to force setting engine's preset???
        TODO:Optimize search!!
        """
        if preset_name[0] == '❤':
            preset_name = preset_name[1:]
        for i in range(len(self.preset_list)):
            name_i = self.preset_list[i][2]
            try:
                if name_i[0] == '❤':
                    name_i = name_i[1:]
                if preset_name == name_i:
                    return self.set_preset(i, set_engine, force_set_engine)
            except:
                pass

        return False

    def set_preset_by_id(self, preset_id, set_engine=True, force_set_engine=True):
        """Set processor's engine preset by ID

        preset_id : ID of preset to select
        set_engine : True to set engine's preset???
        force_set_engine : True to force setting engine's preset???
        """

        index = self.find_preset_index_by_id(preset_id)
        if index is not None:
            return self.set_preset(index, set_engine, force_set_engine)
        else:
            return False

    # TODO Optimize search!!
    def find_preset_index_by_id(self, preset_id):
        """Returns preset index by ID

        preset_id : ID of preset to select
        TODO: Optimize search!!
        """

        for i in range(len(self.preset_list)):
            #logging.debug(f"{preset_id} == {self.preset_list[i][0]}")
            if preset_id == self.preset_list[i][0]:
                return i
        return None

    def preload_preset(self, preset_index):
        """Preload processor's engine preset by index

        preset_index : Index of preset
        Preloading request engine to temporarily load a preset
        """
        # Avoid preload on engines that take excessive time to load presets
        if self.engine.nickname in ['PD', 'MD']:
            return True
        if preset_index < len(self.preset_list):
            if (not self.preload_info and not self.engine.cmp_presets(self.preset_list[preset_index], self.preset_info)) or (self.preload_info and not self.engine.cmp_presets(self.preset_list[preset_index], self.preload_info)):
                self.preload_index = preset_index
                self.preload_name = self.preset_list[preset_index][2]
                self.preload_info = copy.deepcopy(
                    self.preset_list[preset_index])
                logging.info(f"Preset Preloaded: {self.preload_name} ({preset_index})")
                self.engine.set_preset(self, self.preload_info, True)
                return True
        return False

    def restore_preset(self):
        """Restore preset after temporary preload"""

        if self.preset_name is not None and self.preload_info is not None and not self.engine.cmp_presets(self.preload_info, self.preset_info):
            if self.preset_bank_index is not None and self.bank_index != self.preset_bank_index:
                self.set_bank(self.preset_bank_index, False)
            self.preload_index = None
            self.preload_name = None
            self.preload_info = None
            logging.info(f"Restore Preset: {self.preset_name} ({self.preset_index})")
            self.engine.set_preset(self, self.preset_info)
            return True
        return False

    def get_preset_name(self):
        """Get current preset name"""
        return self.preset_name

    def get_preset_index(self):
        """Get index of current preset"""
        return self.preset_index

    def get_preset_bank_index(self):
        """Get current preset's bank index"""
        return self.preset_bank_index

    def get_preset_bank_name(self):
        """Get current preset's bank name"""
        try:
            return self.bank_list[self.preset_bank_index][2].replace("> ", "")
        except:
            return None

    def toggle_preset_fav(self, preset):
        """Toggle preset's favourite state

        preset : Preset info (list)
        """

        self.engine.toggle_preset_fav(self, preset)
        if self.show_fav_presets and not len(self.get_preset_favs()):
            self.set_show_fav_presets(False)

    def remove_preset_fav(self, preset):
        """Remove preset from favourites

        preset : Preset info (list)
        """

        self.engine.remove_preset_fav(preset)
        if self.show_fav_presets and not len(self.get_preset_favs()):
            self.set_show_fav_presets(False)

    def get_preset_favs(self):
        """Get list of favourite preset info structures"""

        return self.engine.get_preset_favs(self)

    def set_show_fav_presets(self, flag=True):
        """Set/reset flag indicating whether to show preset favourites

        flag : True to enable show favourites
        TODO: Should this be in UI?
        """

        if flag and len(self.engine.get_preset_favs(self)):
            self.show_fav_presets = True
            # self.reset_preset()
        else:
            self.show_fav_presets = False

    def get_show_fav_presets(self):
        """Get the flag indicating whether to show preset favourites"""
        return self.show_fav_presets

    def toggle_show_fav_presets(self):
        """Toggle flag indicating whether to show preset favourites"""

        if self.show_fav_presets:
            self.set_show_fav_presets(False)
        else:
            self.set_show_fav_presets(True)
        return self.show_fav_presets

    # ---------------------------------------------------------------------------
    # Controllers Management
    # ---------------------------------------------------------------------------

    def refresh_controllers(self, params=None):
        """Refresh processor controllers configuration"""

        if params:
            self.engine.get_controllers_dict(self, params)
        else:
            self.engine.get_controllers_dict(self)
        self.init_ctrl_screens()

    def init_ctrl_screens(self):
        """Create controller screens from zynthian controller keys

        TODO: This should be in UI
        """

        # Build control screens ...
        self.ctrl_screens_dict = {}
        for cscr in self.engine._ctrl_screens:
            self.ctrl_screens_dict[cscr[0]] = self.build_ctrl_screen(cscr[1])

        # Set active the first screen
        if len(self.ctrl_screens_dict) > 0:
            if self.current_screen_index == -1:
                self.current_screen_index = 0
        else:
            self.current_screen_index = -1

    def get_ctrl_screens(self):
        """Get processor controller screens

        TODO: This should be in UI
        Returns : Dictionary of controller screen structures
        """

        return self.ctrl_screens_dict

    def get_ctrl_screen(self, key):
        """Get processor controller screen

        key : Screen key
        Returns : Controller screen structure
        TODO: This should be in UI
        """

        try:
            return self.ctrl_screens_dict[key]
        except:
            return None

    def get_current_screen_index(self):
        """Get index of last selected controller screen

        Returns : Index of screen
        TODO: This should be in UI
        """

        return self.current_screen_index

    def set_current_screen_index(self, screen_index):
        """Set index of last selected controller screen

        screen_index : Index of screen
        TODO: This should be in UI
        """
        self.current_screen_index = screen_index

    def build_ctrl_screen(self, ctrl_keys):
        """Build array of zynthian_controllers from list of keys

        ctrl_keys : List of controller keys (symbols)
        TODO: This should be in UI
        """

        zctrls = []
        for k in ctrl_keys:
            if k:
                try:
                    zctrls.append(self.controllers_dict[k])
                except:
                    logging.error("Controller %s is not defined" % k)
        return zctrls

    def send_controller_values(self):
        """Send all controller values to engines

           It should be called once when creating some processors that don't give controller feedback
           or when loading presets that modify these controller values without giving feedback.
           => fluidsynth, zynaddsubfx, linuxsampler, ...
        """

        for k, zctrl in self.controllers_dict.items():
            zctrl.send_value()

    def send_ctrl_midi_cc(self):
        """Send MIDI CC for all controllers

        TODO: When is this required? Fluidsynth, linuxsampler and others calls this during set_preset
        => It's used for setting MIDI controllers to a known value, avoiding "jumps" when moving knobs
        => It should be replaced by send_controllers() (see above) and called one-time when creating the processor
        """

        for k, zctrl in self.controllers_dict.items():
            mval = None
            if zctrl.midi_cc:
                mval = zctrl.get_ctrl_midi_val()
                zctrl.send_midi_cc(mval)
                # logging.debug("Sending MIDI CH{}#CC{}={} for {}".format(zctrl.midi_chan, zctrl.midi_cc, int(mval), k))
            if zctrl.midi_feedback:
                zctrl.send_midi_feedback(mval)

    def send_ctrlfb_midi_cc(self):
        """Send MIDI CC for all feeback controllers

        TODO: When is this required? Called by send_ctrl_midi_cc. Fluidsynth calls this during set_preset
        """

        for k, zctrl in self.controllers_dict.items():
            if zctrl.midi_feedback:
                zctrl.send_midi_feedback()
                # logging.debug("Sending MIDI FB CH{}#CC{}={} for {}".format(zctrl.midi_feedback[0], zctrl.midi_feedback[1], int(zctrl.value), k))

    def get_group_zctrls(self, group):
        zctrls = []
        for zctrl in self.controllers_dict.values():
            if zctrl.group_symbol == group:
                zctrls.append(zctrl)
        return zctrls

    # ----------------------------------------------------------------------------
    # MIDI processing
    # ----------------------------------------------------------------------------

    def midi_control_change(self, chan, ccnum, ccval):
        """Handle MIDI CC message

        chan : MIDI channel
        ccnum : CC number
         ccval : CC value
        """

        # logging.debug("Receving MIDI CH{}#CC{}={}".format(chan, ccnum, ccval))
        try:
            self.engine.midi_control_change(chan, ccnum, ccval)
        except:
            pass

    def midi_bank_msb(self, bank_msb):
        """Handle MIDI bank MSB message

        bank_msb : Bank MSB [0: sytem, 1: user, 2: external]
        """
        logging.debug(f"Received Bank MSB for CH#{self.midi_chan}: {bank_msb}")
        if 0 <= bank_msb <= 2:
            self.bank_msb = bank_msb

    def midi_bank_lsb(self, bank_lsb):
        """Handle MIDI bank LSB message

        bank_lsb : Bank LSB
        """
        info = self.bank_msb_info[self.bank_msb]
        logging.debug(f"Received Bank LSB for CH#{self.midi_chan}: {bank_lsb} => {info}")
        if bank_lsb < info[1]:
            logging.debug(f"MSB offset for CH#{self.midi_chan}: {info[0]}")
            self.set_show_fav_presets(False)
            self.set_bank(info[0] + bank_lsb)
            self.load_preset_list()
        else:
            logging.warning(f"Bank index {bank_lsb} doesn't exist for MSB {self.bank_msb} on CH#{self.midi_chan}")

    # ---------------------------------------------------------------------------
    # State Management
    # ---------------------------------------------------------------------------

    def get_state(self):
        """Get dictionary describing processor"""

        state = {
            "processor_type": self.engine.nickname,
            "bank_info": self.bank_info,
            "bank_subdir_info": self.bank_subdir_info,
            "preset_info": self.preset_info,
            "preset_subdir_info": self.preset_subdir_info,
            "show_fav_presets": self.show_fav_presets,  # TODO: GUI
            "controllers": {},
            "current_screen_index": self.current_screen_index  # TODO: GUI
        }
        # Get controller values
        for symbol in self.controllers_dict:
            state['controllers'][symbol] = self.controllers_dict[symbol].get_state()
        return state

    def set_state(self, state):
        """Configure processor from state model dictionary

        state : Processor state
        """

        if "bank_subdir_info" in state and state["bank_subdir_info"]:
            self.bank_subdir_info = state["bank_subdir_info"]
        try:
            self.get_bank_list()
        except:
            pass
        if "bank_info" in state and state["bank_info"]:
            try:
                self.set_bank_by_info(state["bank_info"])
            except:
                logging.exception(traceback.format_exc())

        if "preset_subdir_info" in state and state["preset_subdir_info"]:
            self.preset_subdir_info = state["preset_subdir_info"]
            logging.debug(f"PRESET SUBDIR => {self.preset_subdir_info}")
        try:
            self.load_preset_list()
        except:
            pass

        # Set preset
        if "preset_info" in state:
            try:
                res = self.set_preset(state["preset_info"], force_set_engine=False)
            except:
                res = False
                logging.exception(traceback.format_exc())
        else:
            res = False

        # Set controller values
        if "controllers" in state:
            # Flag controllers to avoid collisions from preset feedback values
            # It should be do it before setting the preset, but i need to know if preset has been changed,
            # so it's done after, but ASAP, to avoid tallies from setting preset arrive before
            if res:
                for symbol, ctrl_state in state["controllers"].items():
                    if "value" in ctrl_state:
                        try:
                            self.controllers_dict[symbol].set_ignore_engine_fb(2.0)
                            #logging.debug(f"Ignoring next engine FB for {symbol}")
                        except Exception as e:
                            logging.warning(f"Invalid controller for processor {self.get_basepath()}: {e}")

            # Set controller values
            for symbol, ctrl_state in state["controllers"].items():
                try:
                    zctrl = self.controllers_dict[symbol]
                    if "value" in ctrl_state:
                        zctrl.set_value(ctrl_state["value"], True)
                    if "midi_cc_momentary_switch" in ctrl_state:
                        zctrl.midi_cc_momentary_switch = ctrl_state['midi_cc_momentary_switch']
                    if "midi_cc_debounce" in ctrl_state:
                        zctrl.midi_cc_debounce = ctrl_state['midi_cc_debounce']
                except Exception as e:
                    logging.warning(f"Invalid controller for processor {self.get_basepath()}: {e}")

    def restore_state_legacy(self, state):
        """Restore legacy states from state

        TODO: Move this to snapshot handler
        """

        # Set legacy Note Range (BW compatibility)
        if isinstance(self.chain.zmop_index, int) and 'note_range' in state:
            nr = state['note_range']
            lib_zyncore.zmop_set_note_range_transpose(
                self.chain.zmop_index, nr['note_low'], nr['note_high'], nr['octave_trans'], nr['halftone_trans'])

    # ---------------------------------------------------------------------------
    # Path/Breadcrumb Strings
    # ---------------------------------------------------------------------------

    def get_path(self):
        """Get path (breadcrumb) string"""

        if self.preset_name:
            bank_name = self.get_preset_bank_name()
            if not bank_name:
                bank_name = "???"
            path = bank_name + "/" + self.preset_name
        else:
            path = self.bank_name
        return path

    def get_basepath(self):
        """Get base path string"""

        if self.engine:
            path = self.engine.get_path(self)
        else:
            path = "NONE"
        if isinstance(self.midi_chan, int):
            if 0 <= self.midi_chan < 16:
                path = f"{self.midi_chan + 1}#{path}"
            elif self.midi_chan == 0xffff:
                path = f"ALL#{path}"
        return path

    def get_basepath_subdir(self):
        """Get base bank path string"""

        path = self.get_basepath()
        # Get bank subdir path
        if self.bank_subdir_info:
            subpath = self.bank_subdir_info[2].replace("> ", "")
            sdi = self.bank_subdir_info[3]
            while sdi:
                subpath = sdi[2].replace("> ", "") + "/" + subpath
                sdi = sdi[3]
            path += " > " + subpath
        return path

    def get_bankpath(self):
        """Get bank path string"""

        path = self.get_basepath()
        subpath = self.get_subdir_path()
        if subpath:
            path += " > " + subpath
        return path

    def get_presetpath(self):
        """Get preset path string"""

        path = self.get_basepath()
        subpath = self.get_subdir_path()
        if self.preset_name:
            preset_name = self.preset_name.replace("> ", "")
            if subpath:
                # Avoid boring repetition in breadcrumbs
                if not subpath.endswith(preset_name):
                    subpath += "/" + preset_name
            else:
                subpath = preset_name
        if subpath:
            path += " > " + subpath
        return path

    def get_bank_subdir_path(self):
        if self.bank_subdir_info:
            subpath = self.bank_subdir_info[2].replace("> ", "")
            sdi = self.bank_subdir_info[3]
            while sdi:
                subpath = sdi[2].replace("> ", "") + "/" + subpath
                sdi = sdi[3]
        else:
            subpath = ""
        return subpath

    def get_preset_subdir_path(self):
        if self.preset_subdir_info:
            subpath = self.preset_subdir_info[2].replace("> ", "")
            sdi = self.preset_subdir_info[3]
            while sdi:
                subpath = sdi[2].replace("> ", "") + "/" + subpath
                sdi = sdi[3]
        else:
            subpath = ""
        return subpath

    def get_subdir_path(self):
        subdir_path = self.get_bank_subdir_path()
        if self.bank_name:
            bank_name = self.bank_name.replace("> ", "")
            if bank_name != "None" and not subdir_path.endswith(bank_name):
                if subdir_path:
                    subdir_path += "/" + bank_name
                else:
                    subdir_path = bank_name
        preset_subdir_path = self.get_preset_subdir_path()
        if preset_subdir_path:
            if subdir_path:
                subdir_path += "/" + preset_subdir_path
            else:
                subdir_path = preset_subdir_path
        return subdir_path

        # -----------------------------------------------------------------------------
