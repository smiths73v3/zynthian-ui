#!/usr/bin/python3
# -*- coding: utf-8 -*-
# ******************************************************************************
# ZYNTHIAN PROJECT: Zynthian Control Device Driver
#
# Zynthian Control Device Driver for "Mackie Control Protocol"
#
# Copyright (C) 2024 Christopher Matthews <chris@matthewsnet.de>
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

import logging
import os
import configparser
from pathlib import Path


# Zynthian specific modules
from zyncoder.zyncore import lib_zyncore
from zyngine.zynthian_signal_manager import zynsigman
from zyngine.ctrldev.zynthian_ctrldev_base import zynthian_ctrldev_zynmixer

# --------------------------------------------------------------------------
# Makiecontrol - Behringer X-Touch Integration
# --------------------------------------------------------------------------

# TODO list below
"""
Get dev_id and try and get a list of features
"""

default_mackie_myconfig = {
	'device_settings': {
		'number_of_strips': 8,
		'masterfader': True,
		'masterfader_strip_num': 8,
		'xtouch': True
	},
	'cuia_mappings': {
		'marker': 'SCREEN_MAIN_MENU',
		'nudge': 'SCREEN_ADMIN',
		'cycle': 'SCREEN_AUDIO_MIXER',
		'drop': 'SCREEN_SNAPSHOT',
		'replace': 'SCREEN_ZS3',
		'click': 'SCREEN_ALSA_MIXER',
		'solo': 'SCREEN_ZYNPAD',
		'f1': 'SCREEN_PATTERN_EDITOR',
		'f2': 'SCREEN_ARRANGER',
		'f3': 'SCREEN_ALSA_MIXER',
		'f4': 'SCREEN_MIDI_RECORDER',
		'f5': 'BANK_PRESET',
		'f6': 'CHAIN_CONTROL',
		'f7': 'ALL_NOTES_OFF',
		'f8': 'ALL_SOUNDS_OFF'
	}
}


def save_default_config(config_file, config_path):
	# Save to file
	Path(config_path).mkdir(parents=True, exist_ok=True)
	with open(config_file, "w") as f:
		config_object = configparser.ConfigParser()
		sections = default_mackie_myconfig.keys()
		for section in sections:
			config_object.add_section(section)
		for section in sections:
			inner_dict = default_mackie_myconfig[section]
			fields = inner_dict.keys()
			for field in fields:
				value = inner_dict[field]
				config_object.set(section, field, str(value))
		config_object.write(f)
	return default_mackie_myconfig


def update_configfile_with_missing_key(section, option, value, file):
	config = configparser.ConfigParser()
	config.read(file)
	config.set(section, option, value)
	with open(file, 'w') as configfile:
		config.write(configfile)


def load_my_mackie_config(file, path):
	config_object = configparser.ConfigParser()
	try:
		with open(file, "r") as f:
			config_object.read_file(f)
			myconfig = {s: dict(config_object.items(s)) for s in config_object.sections()}
			for section in default_mackie_myconfig.keys():
				for key in default_mackie_myconfig[section].keys():
					if key not in myconfig[section].keys():
						value = default_mackie_myconfig[section][key]
						update_configfile_with_missing_key(section, key, value, file)
					myconfig[section][key] = default_mackie_myconfig[section][key]
	except OSError:
		myconfig = save_default_config(file, path)
	return myconfig


class zynthian_ctrldev_mackiecontrol(zynthian_ctrldev_zynmixer):
	dev_ids = ["X-Touch IN 1"]

	midi_chan = 0x0  # zero is the default don't change
	sysex_answer_cb = None
	unroute_from_chains = True
	rec_mode = 0
	shift = False  # TODO I don't think I need this, check...

	mackie_config_path = f"{os.environ['ZYNTHIAN_MY_DATA_DIR']}/files/ctrldev"
	mackie_config_file = f"{mackie_config_path}/{Path(__file__).stem}.ini"
	my_settings = load_my_mackie_config(mackie_config_file, mackie_config_path)

	arrows_ccnum_dict = {
		98: 'ARROW_LEFT',
		99: 'ARROW_RIGHT',
		96: 'ARROW_UP',
		97: 'ARROW_DOWN',
		101: 'BACK'
	}

	# Encoder Assign Buttons and (LEDs not used at the moment)
	encoder_assign_dict = {
		40: 'assign_track',
		42: 'assign_pan',
		44: 'assign_eq',
		41: 'assign_send',
		43: 'assign_plugin',
		45: 'assign_inst'
	}
	encoder_assign_dict_rev = {value: key for key, value in encoder_assign_dict.items()}

	strip_view_assign_dict = {
		51: 'global_view',
		62: 'midi',
		63: 'inputs',
		64: 'audio',
		65: 'inst',
		66: 'aux',
		67: 'busses',
		68: 'outputs',
		69: 'user'
	}
	strip_view_dict_rev = {value: key for key, value in strip_view_assign_dict.items()}

	device_settings = {
		'number_of_strips': int(my_settings['device_settings']['number_of_strips']),
		'masterfader': bool(my_settings['device_settings']['masterfader']),
		'masterfader_strip_num': int(my_settings['device_settings']['masterfader_strip_num']),
		'xtouch': bool(my_settings['device_settings']['xtouch'])
	}
	cuia_mappings = my_settings['cuia_mappings']

	mackie_buttons = {
		84: 'marker',
		85: 'nudge',
		86: 'cycle',
		87: 'drop',
		88: 'replace',
		89: 'click',
		90: 'solo',
		54: 'f1',
		55: 'f2',
		56: 'f3',
		57: 'f4',
		58: 'f5',
		59: 'f6',
		60: 'f7',
		61: 'f8',
	}

	scroll_encoder = 60
	bank_left_ccnum = 46
	bank_right_ccnum = 47
	channel_left_ccnum = 48
	channel_right_ccnum = 49
	select_ccnum = 100
	shift_ccnum = 70

	# TODO transport not enabled
	transport_frwd_ccnum = 91
	transport_ffwd_ccnum = 92
	transport_stop_ccnum = 93
	transport_play_ccnum = 94
	transport_rec_ccnum = 95

	# strip buttons and encoders
	rec_ccnums = [0, 1, 2, 3, 4, 5, 6, 7]  # rec buttons
	solo_ccnums = [8, 9, 10, 11, 12, 13, 14, 15]  # SOLO buttons
	mute_ccnums = [16, 17, 18, 19, 20, 21, 22, 23]  # Mute buttons
	encoders_ccnum = [16, 17, 18, 19, 20, 21, 22, 23]
	encoders_press_ccnum = [32, 33, 34, 35, 36, 37, 38, 39]
	select_ccnums = [24, 25, 26, 27, 28, 29, 30, 31]  # select buttons
	faders_ccnum = [104, 105, 106, 107, 108, 109, 110, 111, 112]  # faders use pitchbend on different midi channels

	# My globals some perhaps temp and to be reviewed
	ZMOP_DEV0 = 19  # no dev_send_pitchbend_change in zynmidirouter had to use zmop_send_pitchbend_change instead
	fader_touch_active = [False, False, False, False, False, False, False, False, False]
	max_fader_value = 16383.0  # I think this is default Mackie
	first_zyn_channel_fader = 0  # To be able to scroll around the channels
	encoder_assign = 'global_view'  # Set as default
	strip_view = 'global_view'  # Set default
	gui_screen = 'audio_mixer'  # Set as default, it's needed to correct an issue when starting  up

	# Function to initialise class
	def __init__(self, state_manager, idev_in, idev_out=None):
		super().__init__(state_manager, idev_in, idev_out)

	def _on_gui_show_screen(self, **kwargs):
		logging.debug(f'got screen change: {kwargs}')
		if 'screen' in kwargs.keys():
			self.gui_screen = kwargs['screen']
		self.refresh()  # I'm using the screen change signal to refresh all channels particularly at the beginning

	def send_syx(self, data='00'):
		msg = bytes.fromhex(f"F0 00 00 66 14 {data} f7")
		lib_zyncore.dev_send_midi_event(self.idev_out, msg, len(msg))

	# This is unnecessary, I've left it in just in case
	def delete_lcd_text(self):
		data_top = ['12', '00']
		data_bottom = []
		for i in range(0, 8):
			text_top = ''
			for letter in list(text_top.center(7)):
				hex = letter.encode('utf-8').hex()
				data_top.append(hex)
			text_bottom = ''
			for letter in list(text_bottom.center(7)):
				hex = letter.encode('utf-8').hex()
				data_bottom.append(hex)
		data = data_top + data_bottom
		self.send_syx(data=' '.join(data))

	def update_lcd_text(self, pos, text):
		data = ['12', pos]
		for num in range(7):  # Make sure that only 7 letters are used
			letter = list(text.center(7))[num]
			hex = letter.encode('utf-8').hex()
			data.append(hex)
		self.send_syx(data=' '.join(data))

	def update_top_lcd_text(self, channel, top_text=''):
		pos_top = ['00', '07', '0e', '15', '1c', '23', '2a', '31']
		self.update_lcd_text(pos_top[channel], top_text)

	def gernerate_top_lcd_text(self):
		if self.encoder_assign == 'assign_pan':
			for i in range(self.device_settings['number_of_strips']):
				self.update_top_lcd_text(i, top_text='PAN')
		else:  # "global_view"
			for i in range(self.device_settings['number_of_strips']):
				if i < 4:
					self.update_top_lcd_text(i, top_text='       ')
				else:
					self.update_top_lcd_text(i, top_text=f'ZYNPOT{i-4}')

	def update_bottom_lcd_text(self, channel, bottom_text=''):
		pos_bottom = ['38', '3f', '46', '4d', '54', '5b', '62', '69']
		self.update_lcd_text(pos_bottom[channel], bottom_text)

	def get_master_chain_audio_channel(self):
		master_chain = self.chain_manager.get_chain(0)
		if master_chain is not None:
			return master_chain.mixer_chan
		else:
			return 255

	def get_ordered_chain_ids_filtered(self):
		chain_ids = list(self.chain_manager.ordered_chain_ids)
		if self.device_settings['masterfader']:
			try:
				chain_ids.pop()
			except:
				pass
		if self.strip_view == 'global_view':
			return chain_ids
		ordered_chain_ids_filtered = []
		for chain_id in chain_ids:
			chain = self.chain_manager.chains[chain_id]
			if self.strip_view == 'midi' and chain.is_midi() and not chain.is_synth():
				logging.debug(f'Got midi only')
				ordered_chain_ids_filtered.append(chain_id)
			elif self.strip_view == 'audio' and chain.is_audio() and not chain.is_synth():
				logging.debug(f'Got audio only')
				ordered_chain_ids_filtered.append(chain_id)
			elif self.strip_view == 'inst' and chain.is_synth():
				logging.debug(f'Got synth only')
				ordered_chain_ids_filtered.append(chain_id)
		return ordered_chain_ids_filtered

	def get_chain_by_position(self, pos):
		ordered_chain_ids_filtered = self.get_ordered_chain_ids_filtered()
		if pos < len(ordered_chain_ids_filtered):
			return self.chain_manager.chains[ordered_chain_ids_filtered[pos]]
		else:
			return None

	def get_mixer_chan_from_device_col(self, col):
		chain = self.get_chain_by_position(col)
		if chain is not None:
			if chain.is_audio() or chain.synth_slots:
				return chain.mixer_chan
		return None

	def init(self):
		self.sleep_off()  # Added this to perhaps stop losing the other registered signals
		# Register signals
		zynsigman.register_queued(zynsigman.S_GUI, zynsigman.SS_GUI_SHOW_SCREEN, self._on_gui_show_screen)
		zynsigman.register_queued(zynsigman.S_AUDIO_PLAYER, self.state_manager.SS_AUDIO_PLAYER_STATE, self.refresh_audio_transport)
		zynsigman.register_queued(zynsigman.S_AUDIO_RECORDER, self.state_manager.SS_AUDIO_RECORDER_STATE, self.refresh_audio_transport)
		zynsigman.register_queued(zynsigman.S_STATE_MAN, self.state_manager.SS_MIDI_PLAYER_STATE, self.refresh_midi_transport)
		zynsigman.register_queued(zynsigman.S_STATE_MAN, self.state_manager.SS_MIDI_RECORDER_STATE, self.refresh_midi_transport)
		super().init()

	def end(self):
		super().end()
		zynsigman.unregister(zynsigman.S_GUI, zynsigman.SS_GUI_SHOW_SCREEN, self._on_gui_show_screen)
		zynsigman.unregister(zynsigman.S_AUDIO_PLAYER, self.state_manager.SS_AUDIO_PLAYER_STATE, self.refresh_audio_transport)
		zynsigman.unregister(zynsigman.S_AUDIO_RECORDER, self.state_manager.SS_AUDIO_RECORDER_STATE, self.refresh_audio_transport)
		zynsigman.unregister(zynsigman.S_STATE_MAN, self.state_manager.SS_MIDI_PLAYER_STATE, self.refresh_midi_transport)
		zynsigman.unregister(zynsigman.S_STATE_MAN, self.state_manager.SS_MIDI_RECORDER_STATE, self.refresh_midi_transport)

	def refresh_audio_transport(self, **kwargs):
		if self.shift:
			return
		# REC Button
		if self.state_manager.audio_recorder.rec_proc:
			lib_zyncore.dev_send_note_on(
				self.idev_out, self.midi_chan, self.transport_rec_ccnum, 127)
			lib_zyncore.dev_send_note_on(
				self.idev_out, self.midi_chan, self.transport_play_ccnum, 127)
			lib_zyncore.dev_send_note_on(
				self.idev_out, self.midi_chan, self.transport_stop_ccnum, 0)
			return
		else:
			lib_zyncore.dev_send_note_on(
				self.idev_out, self.midi_chan, self.transport_rec_ccnum, 0)
			lib_zyncore.dev_send_note_on(
				self.idev_out, self.midi_chan, self.transport_stop_ccnum, 127)
		# PLAY button:
		if self.state_manager.status_audio_player:
			lib_zyncore.dev_send_note_on(
				self.idev_out, self.midi_chan, self.transport_play_ccnum, 127)
			lib_zyncore.dev_send_note_on(
				self.idev_out, self.midi_chan, self.transport_stop_ccnum, 0)
			return
		else:
			lib_zyncore.dev_send_note_on(
				self.idev_out, self.midi_chan, self.transport_play_ccnum, 0)
			lib_zyncore.dev_send_note_on(
				self.idev_out, self.midi_chan, self.transport_stop_ccnum, 127)
		# STOP button
		lib_zyncore.dev_send_note_on(
			self.idev_out, self.midi_chan, self.transport_stop_ccnum, 127)


	def refresh_midi_transport(self, **kwargs):
		if not self.shift:
			return
		# REC Button
		if self.state_manager.status_midi_recorder:
			lib_zyncore.dev_send_note_on(
				self.idev_out, self.midi_chan, self.transport_rec_ccnum, 127)
			lib_zyncore.dev_send_note_on(
				self.idev_out, self.midi_chan, self.transport_play_ccnum, 127)
			lib_zyncore.dev_send_note_on(
				self.idev_out, self.midi_chan, self.transport_stop_ccnum, 0)
			return
		else:
			lib_zyncore.dev_send_note_on(
				self.idev_out, self.midi_chan, self.transport_rec_ccnum, 0)
			lib_zyncore.dev_send_note_on(
				self.idev_out, self.midi_chan, self.transport_stop_ccnum, 127)

		# PLAY button:
		if self.state_manager.status_midi_player:
			lib_zyncore.dev_send_note_on(
				self.idev_out, self.midi_chan, self.transport_play_ccnum, 127)
			lib_zyncore.dev_send_note_on(
				self.idev_out, self.midi_chan, self.transport_stop_ccnum, 0)
			return
		else:
			lib_zyncore.dev_send_note_on(
				self.idev_out, self.midi_chan, self.transport_play_ccnum, 0)
			lib_zyncore.dev_send_note_on(
				self.idev_out, self.midi_chan, self.transport_stop_ccnum, 127)
		# STOP button
		lib_zyncore.dev_send_note_on(
			self.idev_out, self.midi_chan, self.transport_stop_ccnum, 127)

	def get_lcd_bottom_text(self, channel, chain):
		# logging.debug(f'get_lcd_bottom_text: channel:{channel}')
		bottom_text = ''
		if self.encoder_assign == 'global_view':
			# global_view - Get channel Name
			try:
				bottom_text = chain.get_title()
			except:
				bottom_text = ''
			# logging.debug(f'Get Title:   {bottom_text}')
		elif self.encoder_assign == 'assign_pan':  # Get Balance Value
			balance_value = self.zynmixer.get_balance(channel + self.first_zyn_channel_fader)
			bottom_text = f'{round(balance_value * 100, 0)}%'
		return bottom_text

	# Update LED and Fader status for a single strip
	def update_mixer_strip(self, chan, symbol, value):
		# logging.debug(f"update_mixer_strip made chan: {chan} symbol: {symbol} value: {value} ")
		if self.idev_out is None:
			return

		chain_id = self.chain_manager.get_chain_id_by_mixer_chan(chan)
		# logging.debug(f'chain_id: {chain_id}')
		if chain_id is not None:
			# Master Strip Level
			if chain_id == 0 and symbol == "level" and self.device_settings['masterfader']:
				if not self.fader_touch_active[self.device_settings['masterfader_strip_num']]:
					lib_zyncore.zmop_send_pitchbend_change(self.ZMOP_DEV0 + self.idev_out,
														   self.device_settings['masterfader_strip_num'],
														   int(value * self.max_fader_value))
				return
			else:
				if not (chain_id == 0 and self.device_settings['masterfader']):
					col = self.chain_manager.get_chain_index(chain_id)
					col -= self.first_zyn_channel_fader
					if 0 <= col < self.device_settings['number_of_strips']:
						# logging.debug(f'update_mixer_strip chain_id: {chain_id}')
						if symbol == "mute":
							lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, self.mute_ccnums[col],
														 value * 0x7F)
						elif symbol == "solo":
							lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, self.solo_ccnums[col],
														 value * 0x7F)
						elif symbol == "rec":
							lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, self.rec_ccnums[col],
														 value * 0x7F)
						elif symbol == "balance":
							if self.encoder_assign == "assign_pan":
								self.update_bottom_lcd_text(col, f'{int(value * 100)}%')
						elif symbol == "level":
							if not self.fader_touch_active[col]:
								lib_zyncore.zmop_send_pitchbend_change(self.ZMOP_DEV0 + self.idev_out, col,
																	   int(value * self.max_fader_value))

	# Update LED status for active chain
	def update_mixer_active_chain(self, active_chain):
		# logging.debug(f"update_mixer_active_chain active_chain: {active_chain} ")
		# Set "assign 7-Seg LED Number"
		if active_chain == 0:
			left_led, right_led = [77 - 48, 77 - 48]
		else:
			left_led, right_led = list(f"{active_chain:02}")
		lib_zyncore.dev_send_ccontrol_change(self.idev_out, self.midi_chan, 75, int(left_led) + 48)
		lib_zyncore.dev_send_ccontrol_change(self.idev_out, self.midi_chan, 74, int(right_led) + 48)

		# Set correct select led, if within the mixer range
		for i in range(0, self.device_settings['number_of_strips']):
			sel = 0
			try:
				# logging.debug(f'strip_view: {self.strip_view}')
				ordered_chain_ids_filtered = self.get_ordered_chain_ids_filtered()
				# logging.debug(f'ordered_chain_ids_filtered: {ordered_chain_ids_filtered}')
				chain_id = ordered_chain_ids_filtered[i + self.first_zyn_channel_fader]
				if chain_id == active_chain:
					sel = 0x7F
					if active_chain == 0 and self.device_settings['masterfader']:
						sel = 0
			except:
				sel = 0
			lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, self.select_ccnums[i], sel)

	# Update full LED, Faders and Display status
	def refresh(self):
		logging.debug(f"~~~ refresh ~~~")
		if self.idev_out is None:
			return

		# Set Encoder Assign Selected Button LED - Global View, Tracks, PAN, etc
		for key, value in self.encoder_assign_dict_rev.items():
			if self.encoder_assign == key:
				lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, value, 127)
			else:
				lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, value, 0)

		# Set Fader Strip View Buttons
		for key, value in self.strip_view_dict_rev.items():
			if self.strip_view == key:
				lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, value, 127)
			else:
				lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, value, 0)

		# Master Channel Strip
		if self.device_settings['masterfader']:
			master_chain = self.chain_manager.get_chain(0)
			if master_chain is not None:
				zyn_volume_main = self.zynmixer.get_level(master_chain.mixer_chan)  # The Master Chain doesn't have a mixer_chan defined
				# logging.debug(f'Master Channel Volume Level: {zyn_volume_main}')
				lib_zyncore.zmop_send_pitchbend_change(
					self.ZMOP_DEV0 + self.idev_out,
					self.device_settings['masterfader_strip_num'],
					int(zyn_volume_main * self.max_fader_value)
				)

		# Strips Leds, Faders and Displays
		col0 = self.first_zyn_channel_fader
		self.gernerate_top_lcd_text()
		if self.shift:
			lib_zyncore.dev_send_note_on(
				self.idev_out, self.midi_chan, self.shift_ccnum, 127)
			self.refresh_midi_transport()
		else:
			lib_zyncore.dev_send_note_on(
				self.idev_out, self.midi_chan, self.shift_ccnum, 0)
			self.refresh_audio_transport()

		for i in range(0, self.device_settings['number_of_strips']):
			# logging.debug(f'refresh:  strip= {i}')
			rec = 0
			mute = 0
			solo = 0
			sel = 0
			bottom_text = '       '
			zyn_volume = 0

			chain = self.get_chain_by_position(col0 + i)

			if chain is not None:
				# logging.debug(f'refresh:  title= {chain.get_title()}')

				if chain.mixer_chan is not None:
					mute = self.zynmixer.get_mute(chain.mixer_chan) * 0x7F
					solo = self.zynmixer.get_solo(chain.mixer_chan) * 0x7F

				# LEDs
				if chain.mixer_chan is not None:
					rec = self.state_manager.audio_recorder.is_armed(chain.mixer_chan) * 0x7F

				# Select LED and Left/Right LED Chain Number
				if chain == self.chain_manager.get_active_chain():
					sel = 0x7F
					if chain.chain_id == 0:
						left_led, right_led = [77 - 48, 77 - 48]
					else:
						left_led, right_led = list(f"{chain.chain_id:02}")
					lib_zyncore.dev_send_ccontrol_change(self.idev_out, self.midi_chan, 75, int(left_led) + 48)
					lib_zyncore.dev_send_ccontrol_change(self.idev_out, self.midi_chan, 74, int(right_led) + 48)

				# Chain LCD-Displays
				top_text = f'CH {i + 1 + self.first_zyn_channel_fader}'
				bottom_text = self.get_lcd_bottom_text(i, chain)

				# Chain Volume
				if chain.is_audio() or chain.synth_slots:
					zyn_volume = self.zynmixer.get_level(chain.mixer_chan)
					if zyn_volume == None:
						zyn_volume = 0

				# logging.debug(f'i: {i}, sel:{sel}, rec:{rec}, solo:{solo}, mute:{mute}, vol:{zyn_volume}')

			lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, self.mute_ccnums[i], mute)
			lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, self.solo_ccnums[i], solo)
			lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, self.rec_ccnums[i], rec)
			lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, self.select_ccnums[i], sel)
			self.update_bottom_lcd_text(i, bottom_text)
			lib_zyncore.zmop_send_pitchbend_change(self.ZMOP_DEV0 + self.idev_out, i,
												   int(zyn_volume * self.max_fader_value))

	def midi_event(self, ev):
		logging.debug(f"midid_event: {ev} ")
		evtype = (ev[0] >> 4) & 0x0F

		# Faders
		if evtype == 14:
			fader_channel = ev[0] - 0xE0
			logging.debug(f'midi_event fader_channel: {fader_channel}')
			if self.fader_touch_active[fader_channel]:
				logging.debug(f'{self.fader_touch_active}')
				mackie_vol_level = (ev[2] * 256 + ev[1])
				if self.device_settings['xtouch']:
					mackie_vol_level = mackie_vol_level / 2
				zyn_vol_level = mackie_vol_level / self.max_fader_value
				if fader_channel == self.device_settings['masterfader_strip_num'] and self.device_settings['masterfader']:
					self.zynmixer.set_level(self.get_master_chain_audio_channel(), zyn_vol_level)
				else:
					mixer_chan = self.get_mixer_chan_from_device_col(fader_channel + self.first_zyn_channel_fader)
					if mixer_chan is not None:
						self.zynmixer.set_level(mixer_chan, zyn_vol_level)
			return True

		elif ev[0] != 0xF0:
			ccnum = ev[1] & 0x7F
			ccval = ev[2] & 0x7F
			logging.debug(f"midid_event - evtype:{evtype} ccnum:{ccnum} ccval:{ccval}")

			# Encoders
			if evtype == 11:
				if ccnum in self.encoders_ccnum:
					# Encoders Zynthian 1 to 8
					if self.encoder_assign == 'global_view':
						if ccnum in self.encoders_ccnum[-4:]:  # last 4 encoders
							encoder_num = self.encoders_ccnum.index(ccnum)
							logging.debug(f'ccnum: {ccnum} - encoder: {encoder_num-4}')
							if ccval > 64:  # Encoder turned left
								for interation in range(ccval - 64):
									self.state_manager.send_cuia("ZYNPOT", params=[encoder_num-4, -1])
							else:  # Encoder turned rigth
								for interation in range(ccval):
									self.state_manager.send_cuia("ZYNPOT", params=[encoder_num-4, 1])
						return True


					# Encoder PAN
					if self.encoder_assign == 'assign_pan':
						encoder_num = ccnum - self.encoders_ccnum[0] + self.first_zyn_channel_fader
						if encoder_num < self.chain_manager.get_chain_count() - 1:
							balance_value = self.zynmixer.get_balance(encoder_num)
							if ccval > 64:  # Encoder turned left
								new_balance_value = round(balance_value - (ccval - 64) / 100.0, 2)
								if new_balance_value < -1.0:
									new_balance_value = -1.0
							else:  # Encoder turned right
								new_balance_value = balance_value + ccval / 100.0
								if new_balance_value > 1.0:
									new_balance_value = 1.0
							self.zynmixer.set_balance(encoder_num, new_balance_value, True)
							if self.encoder_assign == 'assign_pan':
								self.update_bottom_lcd_text(encoder_num, f'{round(new_balance_value * 100, 0)}%')
						return True
					return True

				elif ccnum == self.scroll_encoder:
					if ccval > 64:
						for i in range(ccval - 64):
							if self.gui_screen in ['audio_mixer']:
								self.state_manager.send_cuia("ARROW_LEFT")
							else:
								self.state_manager.send_cuia('ARROW_UP')
					else:
						for i in range(ccval):
							if self.gui_screen in ['audio_mixer']:
								self.state_manager.send_cuia('ARROW_RIGHT')
							else:
								self.state_manager.send_cuia('ARROW_DOWN')
					return True
				return True

			# Strip View
			elif ccnum in self.strip_view_assign_dict.keys():
				if ccval == 127:
					self.strip_view = self.strip_view_assign_dict[ccnum]
					self.refresh()
				return True

			# Encoder Buttons
			elif ccnum in self.encoders_press_ccnum:
				# Encoder Buttons Zynthian 1 to 8
				logging.debug(f'midi_event DEBUG: ccnum:{ccnum}, ccval:{ccval}')
				if self.encoder_assign == 'global_view':
					logging.debug(f'midi_event DEBUG global_view ccnum:{ccnum}, ccval:{ccval}')
					if ccnum in self.encoders_press_ccnum[-4:]:  # last 4 encoders
						encoder_num = self.encoders_press_ccnum.index(ccnum)
						if ccval == 127:
							logging.debug(f'mdid_event DEBUG: ccnum:{ccnum}, ccval:{ccval}, encoder_num:{encoder_num}')
							self.state_manager.send_cuia("ZYNSWITCH", params=[encoder_num - 4, 'P'])
						else:
							self.state_manager.send_cuia("ZYNSWITCH", params=[encoder_num - 4, 'R'])


			# Shift Key
			elif ccnum == self.shift_ccnum:
				if ccval == 127:
					self.shift = not self.shift
					logging.debug(f"midid_event SHIFT: {self.shift}")
					self.rec_mode = self.shift
					self.refresh()
				return True

			# Encoders Assign
			elif ccnum in self.encoder_assign_dict.keys():
				if ccval == 127:
					if self.encoder_assign == self.encoder_assign_dict[ccnum]:
						self.encoder_assign = 'global_view'
					else:
						self.encoder_assign = self.encoder_assign_dict[ccnum]
					self.refresh()
				return True

			# Zynthian Buttons
			elif ccnum in self.mackie_buttons.keys():
				if ccval == 127:
					self.state_manager.send_cuia(self.cuia_mappings[self.mackie_buttons[ccnum]])
				return True

			# Arrow Keys
			elif ccnum in self.arrows_ccnum_dict.keys():  # done
				if ccval == 127:
					self.state_manager.send_cuia(self.arrows_ccnum_dict[ccnum])
				return True

			# Select Key
			if ccnum == self.select_ccnum:
				if ccval == 127:
					self.state_manager.send_cuia("ZYNSWITCH", params=["3", "P"])
				else:
					self.state_manager.send_cuia("ZYNSWITCH", params=["3", "R"])

			# Move Fader positions
			elif ccnum == self.bank_left_ccnum:
				if ccval == 127:
					if self.first_zyn_channel_fader > 0:
						self.first_zyn_channel_fader -= self.device_settings['number_of_strips']
						if self.first_zyn_channel_fader < 0:
							self.first_zyn_channel_fader = 0
						self.refresh()
				return True
			elif ccnum == self.bank_right_ccnum:
				if ccval == 127:
					# TODO: The calculation seems not to correctly work, rework!
					for n in range(1, int(len(self.get_ordered_chain_ids_filtered()) / self.device_settings[
						'number_of_strips'] + 1)):
						if self.first_zyn_channel_fader < self.device_settings['number_of_strips'] * n:
							self.first_zyn_channel_fader = self.device_settings['number_of_strips'] * n
							self.refresh()
							return True
				return True
			elif ccnum == self.channel_left_ccnum:
				if ccval == 127:
					if self.first_zyn_channel_fader > 0:
						self.first_zyn_channel_fader -= 1
						self.refresh()
				return True
			elif ccnum == self.channel_right_ccnum:
				if ccval == 127:
					if self.first_zyn_channel_fader < len(self.get_ordered_chain_ids_filtered()) - self.device_settings[
						'number_of_strips']:
						self.first_zyn_channel_fader += 1
						self.refresh()
				return True

			# Transport Keys
			elif ccnum == self.transport_play_ccnum:
				if ccval == 127:
					if self.shift:
						self.state_manager.send_cuia("TOGGLE_MIDI_PLAY")
					else:
						self.state_manager.send_cuia("TOGGLE_AUDIO_PLAY")
				return True
			elif ccnum == self.transport_rec_ccnum:
				if ccval == 127:
					if self.shift:
						self.state_manager.send_cuia("TOGGLE_MIDI_RECORD")
					else:
						self.state_manager.send_cuia("TOGGLE_AUDIO_RECORD")
				return True
			elif ccnum == self.transport_stop_ccnum:
				if ccval == 127:
					if self.shift:
						self.state_manager.send_cuia("STOP_MIDI_PLAY")
						self.state_manager.send_cuia("STOP_MIDI_RECORD")
					else:
						self.state_manager.send_cuia("STOP_AUDIO_PLAY")
						self.state_manager.send_cuia("STOP_AUDIO_RECORD")
				return True

			# Strip Buttons Mute
			elif ccnum in self.mute_ccnums:
				if ccval == 127:
					col = self.mute_ccnums.index(ccnum)
					chain = self.get_chain_by_position(col + self.first_zyn_channel_fader)
					mixer_chan = chain.mixer_chan
					if mixer_chan is not None:
						if self.zynmixer.get_mute(mixer_chan):
							val = 0
						else:
							val = 1
						self.zynmixer.set_mute(mixer_chan, val, True)
						if self.idev_out is not None:
							lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, ccnum, val * 0x7F)
					elif self.idev_out is not None:
						lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, ccnum, 0)
				return True

			# Strip Buttons Solo
			elif ccnum in self.solo_ccnums:
				if ccval == 127:
					col = self.solo_ccnums.index(ccnum)
					chain = self.get_chain_by_position(col + self.first_zyn_channel_fader)
					mixer_chan = chain.mixer_chan
					if mixer_chan is not None:
						if self.zynmixer.get_solo(mixer_chan):
							val = 0
						else:
							val = 1
						self.zynmixer.set_solo(mixer_chan, val, True)
						if self.idev_out is not None:
							lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, ccnum, val * 0x7F)
					elif self.idev_out is not None:
						lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, ccnum, 0)
				return True

			# Strip Buttons Select
			elif ccnum in self.select_ccnums:
				if ccval == 127:
					col = self.select_ccnums.index(ccnum)
					chain = self.get_chain_by_position(col + self.first_zyn_channel_fader)
					self.chain_manager.set_active_chain_by_id(chain_id=chain.chain_id)
				return True
			# Strip Buttons Record
			elif ccnum in self.rec_ccnums:
				if ccval == 127:
					col = self.rec_ccnums.index(ccnum)
					chain = self.get_chain_by_position(col + self.first_zyn_channel_fader)
					mixer_chan = chain.mixer_chan
					if mixer_chan is not None:
						self.state_manager.audio_recorder.toggle_arm(mixer_chan)
						# Send LED feedback
						if self.idev_out is not None:
							val = self.state_manager.audio_recorder.is_armed(mixer_chan) * 0x7F
							lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, ccnum, val)
				return True

			# Faders touched information
			elif ccnum in self.faders_ccnum:
				col = self.faders_ccnum.index(ccnum)
				if ccval == 127:
					self.fader_touch_active[col] = True
				elif ccval == 64:
					self.fader_touch_active[col] = False
					if col == self.device_settings['masterfader_strip_num'] and self.device_settings['masterfader']:
						zyn_volume = self.zynmixer.get_level(self.get_master_chain_audio_channel())
					else:
						mixer_chan = self.get_mixer_chan_from_device_col(col + self.first_zyn_channel_fader)
						# logging.debug(f'event chain.mixer_chan:{mixer_chan}')
						zyn_volume = 0
						if mixer_chan is not None:
							zyn_volume = self.zynmixer.get_level(mixer_chan)
					lib_zyncore.zmop_send_pitchbend_change(self.ZMOP_DEV0 + self.idev_out, col,
														   int(zyn_volume * self.max_fader_value))
				return True
			else:
				return True

		# SysEx
		elif ev[0] == 0xF0:
			if callable(self.sysex_answer_cb):
				self.sysex_answer_cb(ev)
			else:
				logging.debug(f"Received SysEx (unprocessed) => {ev.hex(' ')}")
			return True

		return True

	# Light-Off all LEDs
	def light_off(self):
		# logging.debug(f"~~~ light_off ~~~")
		if self.idev_out is None:
			return

		for ccnum in self.mute_ccnums:
			lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, ccnum, 0)
		for ccnum in self.solo_ccnums:
			lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, ccnum, 0)
		for ccnum in self.rec_ccnums:
			lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, ccnum, 0)
		for ccnum in self.select_ccnums:
			lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, ccnum, 0)
		for ccnum in self.encoder_assign_dict.keys():
			lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, ccnum, 0)
		for ccnum in self.strip_view_assign_dict.keys():
			lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, ccnum, 0)
		for i in range(self.device_settings['number_of_strips']):
			lib_zyncore.zmop_send_pitchbend_change(self.ZMOP_DEV0 + self.idev_out, i, 0)
		self.delete_lcd_text()
		# Left and Right LED Display
		lib_zyncore.dev_send_ccontrol_change(self.idev_out, self.midi_chan, 75, 0)
		lib_zyncore.dev_send_ccontrol_change(self.idev_out, self.midi_chan, 74, 0)
		if self.device_settings['masterfader']:
			lib_zyncore.zmop_send_pitchbend_change(self.ZMOP_DEV0 + self.idev_out, self.device_settings['number_of_strips'], 0)


# ------------------------------------------------------------------------------
