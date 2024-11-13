#!/usr/bin/python3
# -*- coding: utf-8 -*-
# ******************************************************************************
# ZYNTHIAN PROJECT: Zynthian Control Device Driver
#
# Zynthian Control Device Driver for "Mackie Control Protocol"
#
# Copyright (C) 2024 Fernando Moyano <jofemodo@zynthian.org>
#                    Christopher Matthews <chris@matthewsnet.de>
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
from time import sleep

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
Add Settings for different devices so that the code remains universal
Add Zynthian dedicated "screen_*****" switches 
Add the four Encoders when in editing screens
Adding and Removing Chains are automatically updated in the controller
Add transport controls
Edit the chain parameters via the "Encoder Assigned" feature
"""


class zynthian_ctrldev_mackiecontrol(zynthian_ctrldev_zynmixer):
	dev_ids = ["X-Touch IN 1"]

	midi_chan = 0x0  # zero is the default don't change
	sysex_answer_cb = None

	rec_mode = 0
	shift = False  # TODO I don't think I need this, check...

	arrow_left_ccnum = 98
	arrow_right_ccnum = 99
	arrow_up_ccnum = 96
	arrow_down_ccnum = 97
	arrow_middle_ccnum = 100
	scroll_encoder = 60
	scrub_ccnum = 101
	bank_left_ccnum = 46
	bank_right_ccnum = 47
	channel_left_ccnum = 48
	channel_right_ccnum = 49

	# Encoder Assign Buttons and (LEDs not used at the moment)
	encoder_assign_dict = {
		51: 'global_view',
		40: 'assign_track',
		42: 'assign_pan',
		44: 'assign_eq',
		41: 'assign_send',
		43: 'assign_plugin',
		45: 'assign_inst'
	}
	encoder_assign_dict_rev = {value: key for key, value in encoder_assign_dict.items()}


	# TODO transport not enabled
	transport_frwd_ccnum = 91
	transport_ffwd_ccnum = 92
	transport_stop_ccnum = 93
	transport_play_ccnum = 94
	transport_rec_ccnum = 95

	# channel buttons and encoders
	solo_ccnums = [8, 9, 10, 11, 12, 13, 14, 15]  # SOLO buttons
	mute_ccnums = [16, 17, 18, 19, 20, 21, 22, 23]  # Mute buttons
	rec_ccnums = [0, 1, 2, 3, 4, 5, 6, 7]  # rec buttons
	select_ccnums = [24, 25, 26, 27, 28, 29, 30, 31]  # select buttons
	knobs_ccnum = [16, 17, 18, 19, 20, 21, 22, 23]  # this is different with encoders
	faders_ccnum = [104, 105, 106, 107, 108, 109, 110, 111, 112]  # faders use pitchbend on different midi channels
	encoders_ccnum = [16, 17, 18, 19, 20, 21, 22, 23]

	# Mackie Device Features - Settings as default for X-touch
	device_settings = {
		'number_of_strips': 8,
		'masterfader': True,
		'timecode_display': True,
		'two_character_display': True,
		'extenders': 0,
		'master_position': 0,
		'global_controls': True,
		'jog_wheel': True,
		'touch_sense_faders': True,
		'has_seperate_meters': True,
		'xtouch': True
	}

	# My globals some perhaps temp and to be reviewed
	ZMOP_DEV0 = 19  # no dev_send_pitchbend_change in zynmidirouter had to use zmop_send_pitchbend_change instead
	fader_touch_active = [False, False, False, False, False, False, False, False, False]
	max_fader_value = 16383.0  # I think this is default Mackie
	first_zyn_channel_fader = 0  # To be able to scroll around the channels
	encoder_assign = 'global_view'  # Set as default
	gui_screen = 'audio_mixer'  # Set as default
	fader_view = {'audio': True, 'midi': True, 'synth': True}

	# Function to initialise class
	def __init__(self, state_manager, idev_in, idev_out=None):
		super().__init__(state_manager, idev_in, idev_out)

	def _on_gui_show_screen(self,  **kwargs):
		logging.debug(f'got screen change: {kwargs}')
		if 'screen' in kwargs.keys():
			self.gui_screen = kwargs['screen']
		self.refresh()  # I'm using the screen change signal to refresh all channels particularly at the beginning

	def send_syx(self, data='00'):
		msg = bytes.fromhex(f"F0 00 00 66 14 {data} f7")
		lib_zyncore.dev_send_midi_event(self.idev_out, msg, len(msg))

	# This is unnecessary, I've left it in just in case
	def init_lcd_text(self,):
		data_top = ['12', '00']
		data_bottom = []
		for i in range(0, 8):
			text_top = f'CH {i}'
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
		for letter in list(text.center(7)):
			hex = letter.encode('utf-8').hex()
			data.append(hex)
		self.send_syx(data=' '.join(data))

	def update_top_lcd_text(self, channel, top_text=''):
		pos_top = ['00', '07', '0e', '15', '1c', '23', '2a', '31']
		self.update_lcd_text(pos_top[channel], top_text)

	def update_bottom_lcd_text(self, channel, bottom_text=''):
		pos_bottom = ['38', '3f', '46', '4d', '54', '5b', '62', '69']
		self.update_lcd_text(pos_bottom[channel], bottom_text)

	def init(self):
		# Enable LED control
		# Register signals
		zynsigman.register_queued(zynsigman.S_GUI, zynsigman.SS_GUI_SHOW_SCREEN, self._on_gui_show_screen)
		# zynsigman.register_queued(zynsigman.S_AUDIO_PLAYER, self.state_manager.SS_AUDIO_PLAYER_STATE, self.refresh_audio_transport)
		# zynsigman.register_queued(zynsigman.S_AUDIO_RECORDER, self.state_manager.SS_AUDIO_RECORDER_STATE, self.refresh_audio_transport)
		# zynsigman.register_queued(zynsigman.S_STATE_MAN, self.state_manager.SS_MIDI_PLAYER_STATE, self.refresh_midi_transport)
		# zynsigman.register_queued(zynsigman.S_STATE_MAN, self.state_manager.SS_MIDI_RECORDER_STATE, self.refresh_midi_transport)
		super().init()

	def end(self):
		super().end()
		# Unregister signals
		zynsigman.unregister(zynsigman.S_GUI, zynsigman.SS_GUI_SHOW_SCREEN, self._on_gui_show_screen)
		# zynsigman.unregister(zynsigman.S_AUDIO_PLAYER, self.state_manager.SS_AUDIO_PLAYER_STATE, self.refresh_audio_transport)
		# zynsigman.unregister(zynsigman.S_AUDIO_RECORDER, self.state_manager.SS_AUDIO_RECORDER_STATE, self.refresh_audio_transport)
		# zynsigman.unregister(zynsigman.S_STATE_MAN, self.state_manager.SS_MIDI_PLAYER_STATE, self.refresh_midi_transport)
		# zynsigman.unregister(zynsigman.S_STATE_MAN, self.state_manager.SS_MIDI_RECORDER_STATE, self.refresh_midi_transport)

	# TODO later
	"""
	def refresh_audio_transport(self, **kwargs):
		if self.shift:
			return
		# REC Button
		if self.state_manager.audio_recorder.rec_proc:
			lib_zyncore.dev_send_ccontrol_change(self.idev_out, self.midi_chan, self.transport_rec_ccnum, 0x7F)
		else:
			lib_zyncore.dev_send_ccontrol_change(self.idev_out, self.midi_chan, self.transport_rec_ccnum, 0)
		# STOP button
		lib_zyncore.dev_send_ccontrol_change(self.idev_out, self.midi_chan, self.transport_stop_ccnum, 0)
		# PLAY button:
		if self.state_manager.status_audio_player:
			lib_zyncore.dev_send_ccontrol_change(self.idev_out, self.midi_chan, self.transport_play_ccnum, 0x7F)
		else:
			lib_zyncore.dev_send_ccontrol_change(self.idev_out, self.midi_chan, self.transport_play_ccnum, 0)

	# TODO keep but edit - called from refresh
	def refresh_midi_transport(self, **kwargs):
		if not self.shift:
			return
		# REC Button
		if self.state_manager.status_midi_recorder:
			lib_zyncore.dev_send_ccontrol_change(self.idev_out, self.midi_chan, self.transport_rec_ccnum, 0x7F)
		else:
			lib_zyncore.dev_send_ccontrol_change(self.idev_out, self.midi_chan, self.transport_rec_ccnum, 0)
		# STOP button
		lib_zyncore.dev_send_ccontrol_change(self.idev_out, self.midi_chan, self.transport_stop_ccnum, 0)
		# PLAY button:
		if self.state_manager.status_midi_player:
			lib_zyncore.dev_send_ccontrol_change(self.idev_out, self.midi_chan, self.transport_play_ccnum, 0x7F)
		else:
			lib_zyncore.dev_send_ccontrol_change(self.idev_out, self.midi_chan, self.transport_play_ccnum, 0)
	"""

	def get_lcd_bottom_text(self, channel, chain):
		logging.debug(f'get_lcd_bottom_text: channel:{channel}')
		bottom_text = ''
		if self.encoder_assign == 'global_view':
			# global_view - Get channel Name
			try:
				bottom_text = chain.get_title()
			except:
				bottom_text = ''
			logging.debug(f'Get Title:   {bottom_text}')
		elif self.encoder_assign == 'assign_pan':  # Get Balance Value
			balance_value = self.zynmixer.get_balance(channel + self.first_zyn_channel_fader)
			bottom_text = f'{round(balance_value * 100, 0)}%'
		return bottom_text

	# Update LED and Fader status for a single strip
	def update_mixer_strip(self, chan, symbol, value):
		logging.debug(f"update_mixer_strip made chan: {chan} symbol: {symbol} value: {value} ")
		if self.idev_out is None:
			return
		chain_id = self.chain_manager.get_chain_id_by_mixer_chan(chan)
		if chain_id:
			if chain_id == 0 and symbol == "level" and self.device_settings['masterfader']:  # Refresh Master Channel Fader
				if not self.fader_touch_active[8]:
					lib_zyncore.zmop_send_pitchbend_change(self.ZMOP_DEV0 + self.idev_out, 8, int(value * self.max_fader_value))
				return
			else:
				if not (chain_id == 0 and self.device_settings['masterfader']):
					col = self.chain_manager.get_chain_index(chain_id)
					col -= self.first_zyn_channel_fader
					if 0 <= col < self.device_settings['number_of_strips']:
						logging.debug(f'update_mixer_strip chain_id: {chain_id}')
						if symbol == "mute":
							lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, self.mute_ccnums[col], value * 0x7F)
						elif symbol == "solo":
							lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, self.solo_ccnums[col], value * 0x7F)
						elif symbol == "rec":
							lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, self.rec_ccnums[col], value * 0x7F)
						elif symbol == "balance":
							if self.encoder_assign == "assign_pan":
								self.update_bottom_lcd_text(col, f'{int(value * 100)}%')
						elif symbol == "level":
							if not self.fader_touch_active[col]:
								lib_zyncore.zmop_send_pitchbend_change(self.ZMOP_DEV0 + self.idev_out, col, int(value * self.max_fader_value))

	# Update LED status for active chain
	def update_mixer_active_chain(self, active_chain):
		logging.debug(f"update_mixer_active_chain active_chain: {active_chain} ")
		# Set "assign 7-Seg LED Number"
		if active_chain == 0:
			left_led, right_led = [77-48, 77-48]
		else:
			left_led, right_led = list(f"{active_chain:02}")
		lib_zyncore.dev_send_ccontrol_change(self.idev_out, self.midi_chan, 75, int(left_led) + 48)
		lib_zyncore.dev_send_ccontrol_change(self.idev_out, self.midi_chan, 74, int(right_led) + 48)

		# Set correct select led, if within the mixer range
		for i in range(0, self.device_settings['number_of_strips']):
			sel = 0
			try:
				chain_id = self.chain_manager.ordered_chain_ids[i + self.first_zyn_channel_fader]  # TODO Add filtered functionality
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

		# Strips Leds, Faders and Displays
		col0 = self.first_zyn_channel_fader
		for i in range(0, self.device_settings['number_of_strips']):
			logging.debug(f'refresh:  strip= {i}')
			rec = 0
			mute = 0
			solo = 0
			sel = 0
			top_text = ''
			bottom_text = ''
			zyn_volume = 0

			chain = self.chain_manager.get_chain_by_position(col0 + i, **self.fader_view)  # TODO Add Midi, Synth, Audio filters

			if chain:
				if chain.chain_id == 0 and self.device_settings['masterfader']:
					zyn_volume_main = self.zynmixer.get_level(255)  # TODO review
					lib_zyncore.zmop_send_pitchbend_change(self.ZMOP_DEV0 + self.idev_out, 8, int(zyn_volume_main * self.max_fader_value))

				else:
					logging.debug(f'refresh:  title= {chain.get_title()}')

					if chain.mixer_chan is not None:
						mute = self.zynmixer.get_mute(chain.mixer_chan) * 0x7F
						solo = self.zynmixer.get_solo(chain.mixer_chan) * 0x7F

					# LEDs
					if chain.mixer_chan is not None:
						rec = self.state_manager.audio_recorder.is_armed(chain.mixer_chan) * 0x7F

					# Select LED
					if chain == self.chain_manager.get_active_chain():
						sel = 0x7F

					# Chain LCD-Displays
					top_text = f'CH {i + 1 + self.first_zyn_channel_fader}'
					bottom_text = self.get_lcd_bottom_text(i, chain)

					# Chain Volume
					if chain.is_audio() or chain.synth_slots:
						zyn_volume = self.zynmixer.get_level(chain.mixer_chan)

				logging.debug(f'i: {i}, sel:{sel}, rec:{rec}, solo:{solo}, mute:{mute}, vol:{zyn_volume}')

			lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, self.mute_ccnums[i], mute)
			lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, self.solo_ccnums[i], solo)
			lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, self.rec_ccnums[i], rec)
			lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, self.select_ccnums[i], sel)
			self.update_top_lcd_text(i, top_text=top_text)
			self.update_bottom_lcd_text(i, bottom_text)
			lib_zyncore.zmop_send_pitchbend_change(self.ZMOP_DEV0 + self.idev_out, i, int(zyn_volume * self.max_fader_value))

	def get_mixer_chan_from_device_col(self, col):
		chain = self.chain_manager.get_chain_by_position(col, **self.fader_view)
		if chain is not None:
			if not (self.device_settings['masterfader'] and chain.chain_id == 0):
				if chain.is_audio() or chain.synth_slots:
					return chain.mixer_chan
		return None

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
				channel_count = self.chain_manager.get_chain_count()
				if fader_channel == 8 and self.device_settings['masterfader']:  # Master Channel
					self.zynmixer.set_level(255, zyn_vol_level)
				else:
					# TODO add midi, synth, audio filers
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
					# Encoders
					encoder_num = ccnum - self.encoders_ccnum[0] + self.first_zyn_channel_fader
					if encoder_num < self.chain_manager.get_chain_count() - 1:

						if self.encoder_assign == 'global_view' or self.encoder_assign == 'assign_pan':
							# Function Panning
							balance_value = self.zynmixer.get_balance(encoder_num)
							if ccval > 64:  # Encoder turned left
								new_balance_value = round(balance_value - (ccval - 64) / 100.0, 2)
								if new_balance_value < -1.0:
									new_balance_value = -1.0
							else: # Encoder turned right
								new_balance_value = balance_value + ccval / 100.0
								if new_balance_value > 1.0:
									new_balance_value = 1.0
							self.zynmixer.set_balance(encoder_num, new_balance_value, True)
							if self.encoder_assign == 'assign_pan':
								self.update_bottom_lcd_text(encoder_num, f'{round(new_balance_value * 100, 0)}%')
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

			# Encoders Assign
			elif ccnum in self.encoder_assign_dict.keys():
				if ccval == 127:
					self.encoder_assign = self.encoder_assign_dict[ccnum]
					self.refresh()
				return True

			# Arrow Keys TODO as above perhaps change to dictionary
			elif ccnum == self.arrow_left_ccnum:  # done
				if ccval == 127:
					self.state_manager.send_cuia("ARROW_LEFT")
				return True
			elif ccnum == self.arrow_right_ccnum:  # done
				if ccval == 127:
					self.state_manager.send_cuia("ARROW_RIGHT")
				return True
			elif ccnum == self.arrow_up_ccnum:  # done
				if ccval == 127:
					self.state_manager.send_cuia("ARROW_UP")
				return True
			elif ccnum == self.arrow_down_ccnum:  # done
				if ccval == 127:
					self.state_manager.send_cuia("ARROW_DOWN")
				return True

			elif ccnum == self.arrow_middle_ccnum:  # done
				if ccval == 127:
					self.state_manager.send_cuia("ZYNSWITCH", params=["3", "P"])
				elif ccval == 64:
					self.state_manager.send_cuia("ZYNSWITCH", params=["3", "R"])
				return True
			elif ccnum == self.scrub_ccnum:  # done
				if ccval == 127:
					self.state_manager.send_cuia("BACK")
					self.refresh()
				return True

			elif ccnum == self.bank_left_ccnum:
				if ccval == 127:
					if self.first_zyn_channel_fader > 0:
						self.first_zyn_channel_fader -= self.device_settings['number_of_strips']
						if self.first_zyn_channel_fader < 0:
							self.first_zyn_channel_fader = 0
						self.refresh()
				return True
			elif ccnum == self.bank_right_ccnum:
				if ccval == 127:  # TODO This will not work if it goes over 16 channels
					self.first_zyn_channel_fader = self.device_settings['number_of_strips']
					self.refresh()
				return True
			elif ccnum == self.channel_left_ccnum:
				if ccval == 127:
					if self.first_zyn_channel_fader > 0:
						self.first_zyn_channel_fader -= 1
						self.refresh()
				return True
			elif ccnum == self.channel_right_ccnum:
				if ccval == 127:
					if self.first_zyn_channel_fader < self.chain_manager.get_chain_count() - 9:
						self.first_zyn_channel_fader += 1
						self.refresh()
				return True

			# Transport Keys
			elif ccnum == self.transport_play_ccnum:
				if ccval > 0:
					if self.shift:
						self.state_manager.send_cuia("TOGGLE_MIDI_PLAY")
					else:
						self.state_manager.send_cuia("TOGGLE_AUDIO_PLAY")
				return True
			elif ccnum == self.transport_rec_ccnum:
				if ccval > 0:
					if self.shift:
						self.state_manager.send_cuia("TOGGLE_MIDI_RECORD")
					else:
						self.state_manager.send_cuia("TOGGLE_AUDIO_RECORD")
				return True
			elif ccnum == self.transport_stop_ccnum:
				if ccval > 0:
					if self.shift:
						self.state_manager.send_cuia("STOP_MIDI_PLAY")
					else:
						self.state_manager.send_cuia("STOP_AUDIO_PLAY")
				return True

			elif ccnum in self.mute_ccnums:
				if ccval == 127:
					col = self.mute_ccnums.index(ccnum)
					chain = self.chain_manager.get_chain_by_position(col + self.first_zyn_channel_fader, **self.fader_view)
					mixer_chan = chain.mixer_chan
					if mixer_chan is not None:
						if not (chain.chain_id == 0 and self.device_settings['masterfader']):
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
			elif ccnum in self.solo_ccnums:
				if ccval == 127:
					col = self.solo_ccnums.index(ccnum)
					chain = self.chain_manager.get_chain_by_position(col + self.first_zyn_channel_fader, **self.fader_view)
					mixer_chan = chain.mixer_chan
					if mixer_chan is not None:
						if chain.chain_id != 0:  # The Master Channel Solo button doesn't work, also makes no sense
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
			elif ccnum in self.select_ccnums:
				if ccval == 127:
					col = self.select_ccnums.index(ccnum)
					self.chain_manager.set_active_chain_by_index(col + self.first_zyn_channel_fader)
				return True
			elif ccnum in self.rec_ccnums:
				if ccval == 127:
					col = self.rec_ccnums.index(ccnum)
					chain = self.chain_manager.get_chain_by_position(col + self.first_zyn_channel_fader, **self.fader_view)
					mixer_chan = chain.mixer_chan
					if not (chain.chain_id == 0 and self.device_settings['masterfader']):
						if mixer_chan is not None:
							self.state_manager.audio_recorder.toggle_arm(mixer_chan)
							# Send LED feedback
							if self.idev_out is not None:
								val = self.state_manager.audio_recorder.is_armed(mixer_chan) * 0x7F
								lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, ccnum, val)
					elif self.idev_out is not None:
						lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, ccnum, 0)
				return True

			# Faders just get if the fader is touched information
			elif ccnum in self.faders_ccnum:
				col = self.faders_ccnum.index(ccnum)
				if ccval == 127:
					self.fader_touch_active[col] = True
				elif ccval == 64:
					self.fader_touch_active[col] = False
					if col == 8 and self.device_settings['masterfader']:
						zyn_volume = self.zynmixer.get_level(255)
					else:
						mixer_chan = self.get_mixer_chan_from_device_col(col + self.first_zyn_channel_fader)
						logging.debug(f'event chain.mixer_chan:{mixer_chan}')
						zyn_volume = 0
						if mixer_chan is not None:
							zyn_volume = self.zynmixer.get_level(mixer_chan)
					lib_zyncore.zmop_send_pitchbend_change(self.ZMOP_DEV0 + self.idev_out, col, int(zyn_volume * self.max_fader_value))
				return True

		# SysEx
		elif ev[0] == 0xF0:
			if callable(self.sysex_answer_cb):
				self.sysex_answer_cb(ev)
			else:
				logging.debug(f"Received SysEx (unprocessed) => {ev.hex(' ')}")
			return True

	# Light-Off all LEDs
	def light_off(self):
		logging.debug(f"~~~ light_off ~~~")
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
		# TODO check below
		"""
		for ccnum in [41, 42, 43, 44, 45, 46, 58, 59, 60, 61, 62]:
			lib_zyncore.dev_send_note_on(self.idev_out, self.midi_chan, ccnum, 0)
		"""
# ------------------------------------------------------------------------------
