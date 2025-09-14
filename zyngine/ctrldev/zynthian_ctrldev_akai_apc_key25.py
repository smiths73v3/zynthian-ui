from zyngine.ctrldev.zynthian_ctrldev_akai_apc_key25_mk2 import \
    zynthian_ctrldev_akai_apc_key25_mk2, NotePad, KNOB_1, KNOB_LAYER, KNOB_2, KNOB_SNAPSHOT, KNOB_3, \
KNOB_4,\
KNOB_5, KNOB_BACK,\
KNOB_6, KNOB_SELECT,\
KNOB_7,\
KNOB_8, \
MAX_STUTTER_DURATION, \
MAX_STUTTER_COUNT, \
LED_BRIGHT_10, \
LED_BRIGHT_100, \
EV_NOTE_OFF, \
EV_NOTE_ON, \
EV_CC, \
BTN_PAD_END, \
LED_PULSING_8



# from zyngui import zynthian_gui_config

from zyncoder.zyncore import lib_zyncore
   # lib_zyncore.get_active_midi_chan() does not work


# APC Key25 MK2 LED colors and modes


class COLORS:
    COLOR_BLACK = 0x00
    COLOR_DARK_GREY = 0x01
    COLOR_GREEN = COLOR_STATE_1 = COLOR_PLAYING = COLOR_ALT_OFF = COLOR_FN = 0x01
    COLOR_BLUE = 0x25
    COLOR_AQUA = 0x21
    COLOR_BLUE_DARK = 0x2D
    COLOR_BLUE_LIGHT = 0x24
    COLOR_WHITE = 0x03
    COLOR_EGYPT = 0x6C
    COLOR_ORANGE = 0x09
    COLOR_ORANGE_LIGHT = 0x08
    COLOR_AMBER = 0x54
    COLOR_RUSSET = 0x3D
    COLOR_PURPLE = 0x51
    COLOR_PINK = 0x39
    COLOR_PINK_LIGHT = 0x52
    COLOR_PINK_WARM = 0x38
    COLOR_LIME = 0x4B
    COLOR_LIME_DARK = 0x11
    COLOR_DARK_GREEN = 0x41
    COLOR_GREEN_YELLOW = 0x4A
    COLOR_BROWNISH_RED = 0x0A
    COLOR_BROWN_LIGHT = 0x7E
    SOFT_OFF = 0x00
    SOFT_ON = 0x01
    SOFT_BLINK = 0x02
    COLOR_RED = COLOR_STATE_2 = COLOR_ALT_ON = 0x03 # 0x05
    COLOR_BLUE_DARK = 0x05 # 0x2D
    COLOR_WHITE = 0x05 # 0x08
    COLOR_EGYPT = 0x6C
    COLOR_ORANGE = 0x09
    COLOR_AMBER = 0x54
    COLOR_RUSSET = 0x3D
    COLOR_PURPLE = 0x03 # 0x51
    COLOR_PINK = 0x39
    COLOR_PINK_LIGHT = 0x52
    COLOR_PINK_WARM = 0x38
    COLOR_YELLOW = COLOR_STATE_0 = 0x05 # 0x0D
    COLOR_LIME = 0x4B
    COLOR_LIME_DARK = 0x11
    COLOR_GREEN_YELLOW = 0x4A


class zynthian_ctrldev_akai_apc_key25(zynthian_ctrldev_akai_apc_key25_mk2):

    dev_ids = ["APC Key 25 MIDI 1", "APC Key 25 IN 1"]
    driver_name = 'AKAI APC Key25'
    unroute_from_chains = True
    on_notes = {}


    COLOR_SET = COLORS

    def _on_midi_event(self, ev):
        evtype = (ev[0] >> 4) & 0x0F
        channel = ev[0] & 0x0F
            
        # Direct keybed to chains
        if (channel == 1):
            if evtype == EV_NOTE_OFF:
                # get and use old midi_channel, iif any
                if ev[1] in self.on_notes:
                    midi_chan = self.on_notes[ev[1]]
                    status = (ev[0] & 0xF0) | midi_chan
                    del self.on_notes[ev[1]]
                    self.zynseq.libseq.sendMidiCommand(status, ev[1], ev[2])
                    return
            if evtype == EV_CC and ev[2] == 0:
                # get and use old midi_channel, iif any
                if 256 in self.on_notes:
                    midi_chan = self.on_notes[256]
                    status = (ev[0] & 0xF0) | midi_chan
                    del self.on_notes[256]
                    self.zynseq.libseq.sendMidiCommand(status, ev[1], ev[2])
                    return
            chain = self.chain_manager.get_active_chain()
            # print(chain.midi_chan)
            # @todo: find out how to get 'last' active chain, for now: just back out.
            if chain.midi_chan is None:
                return
            status = (ev[0] & 0xF0) | chain.midi_chan
            # save old MIDI channel in case switched to other
            if evtype == EV_NOTE_ON:
                self.on_notes[ev[1]] = chain.midi_chan
            if evtype == EV_CC:
                self.on_notes[256] = chain.midi_chan
            self.zynseq.libseq.sendMidiCommand(status, ev[1], ev[2])
            return

        return super()._on_midi_event(ev)

    class FeedbackLEDs(zynthian_ctrldev_akai_apc_key25_mk2.FeedbackLEDs):

        def led_on(self, led, color=1, brightness=0, overlay=False):
            self._timer.remove(led)
            mk1_brightness_100 = 0x00
            if brightness > 0x06:
                color += 1
            if led > BTN_PAD_END or brightness > 0x00:
                lib_zyncore.dev_send_note_on(self._idev, mk1_brightness_100, led, color)
            else:
                self.led_off(led, overlay)
                # lib_zyncore.dev_send_note_on(self._idev, mk1_brightness_100, led, color)
            if not overlay:
                self._state[led] = (color, brightness)
    
    class DeviceHandler(zynthian_ctrldev_akai_apc_key25_mk2.DeviceHandler):

        def cc_change(self, ccnum, ccval):
            #delta = self._knobs_ease.feed(ccnum, ccval, self._is_shifted)
            #if delta is None:
            #    return

            zynpot = {
                KNOB_LAYER: 0,
                KNOB_BACK: 1,
                KNOB_SNAPSHOT: 2,
                KNOB_SELECT: 3
            }.get(ccnum, None)
            if zynpot is None:
                return

            self._state_manager.send_cuia("ZYNPOT_ABS", [zynpot, ccval / 127])
        
    class MixerHandler(zynthian_ctrldev_akai_apc_key25_mk2.MixerHandler):

        def _update_control(self, type, ccnum, ccval, minv, maxv):
            if self._is_shifted:
                # Only main chain is handled with SHIFT, ignore the rest
                if ccnum != self.main_chain_knob:
                    return False
                mixer_chan = 255
            else:
                index = (ccnum - KNOB_1) + self._chains_bank * 8
                chain = self._chain_manager.get_chain_by_index(index)
                if chain is None or chain.chain_id == 0:
                    return False
                mixer_chan = chain.mixer_chan

            if type == "level":
                value = (ccval * 100 ) / 128
                set_value = self._zynmixer.set_level
            elif type == "balance":
                value = ((ccval * 100 ) / 64) - 100
                set_value = self._zynmixer.set_balance
            else:
                return False

            # NOTE: knobs are pots, not encoders (so ccval is absolute)
            value = max(minv, min(value, maxv))
            set_value(mixer_chan, value / 100)
            return True
        
    class PadMatrixHandler(zynthian_ctrldev_akai_apc_key25_mk2.PadMatrixHandler):
            # Just make a pattern...
            GROUP_COLORS = [
                0x03,
                0x05,
                0x01,
                0x03,
                0x05,
                0x01,
                0x03,
                0x05,
                0x01,
                0x03,
                0x05,
                0x01,
                0x03,
                0x05,
                0x01,
                0x03,
            ]
            BRIGHT_OFF = LED_BRIGHT_10

    class StepSeqHandler(zynthian_ctrldev_akai_apc_key25_mk2.StepSeqHandler):

        NOTE_PAGE_COLORS = [
            COLORS.COLOR_YELLOW,
            COLORS.COLOR_GREEN,
            COLORS.COLOR_RED,
            COLORS.COLOR_YELLOW,
        ]

        BRIGHT_FIRSTBEAT = LED_BRIGHT_100
        COLOR_FIRSTBEAT = COLORS.COLOR_YELLOW
        COLOR_BEAT = COLORS.COLOR_GREEN
        COLOR_VELOCITY = COLOR_CLEAR = COLOR_SELECTED = COLORS.COLOR_RED
        COLOR_COPY = COLORS.COLOR_YELLOW

        # NOTE: Do NOT change argument names here (is called using keyword args)
        def _on_midi_note_on(self, izmip, chan, note, vel):
            # Skip own device events / not assigning mode
            if (chan == 0 and izmip == self._own_device_id) or len(self._pressed_pads) == 0:
                return

            # If MIDI is playing, we need to ensure this note_on does come
            # from a device (i.e the user pressed it!).
            if izmip >= self._state_manager.get_zmip_seq_index():
                return

            for pad in self._pressed_pads:
                self._note_pads[pad] = NotePad(note, vel, 1.0)
            self.refresh()

        def _update_step_duration(self, step, duration):
            if self._selected_note is None:
                return

            note = self._selected_note.note
            max_duration = self._libseq.getSteps()
            # duration = self._libseq.getNoteDuration(step, note) + delta * 0.1
            duration = round(min(max_duration, max(0.1, duration)), 1)
            self._set_note_duration(step, note, duration)
            self._play_step(step)
            self.refresh(only_steps=True)

        def _update_step_velocity(self, step, velocity):
            if self._selected_note is None:
                return

            note = self._selected_note.note
            # velocity = self._libseq.getNoteVelocity(step, note) + delta
            velocity = min(127, max(10, velocity))
            self._libseq.setNoteVelocity(step, note, velocity)
            self._leds.led_on(self._pads[step], self.COLOR_VELOCITY, int((velocity * 6) / 127))
            self._play_step(step)

        def _update_step_stutter_count(self, step, count):
            if self._selected_note is None:
                return

            note = self._selected_note.note
            # count = self._libseq.getStutterCount(step, note) + delta
            count = min(MAX_STUTTER_COUNT, max(0, count))
            self._libseq.setStutterCount(step, note, count)
            self._play_step(step)

        def _update_step_stutter_duration(self, step, duration):
            if self._selected_note is None:
                return

            note = self._selected_note.note
            # duration = self._libseq.getStutterDur(step, note) + delta
            duration = min(MAX_STUTTER_DURATION, max(1, duration))
            self._libseq.setStutterDur(step, note, duration)
            self._play_step(step)

        def _update_note_pad_duration(self, pad, note_spec, duration):
            max_duration = self._libseq.getSteps()
            note_spec.duration = \
                round(min(max_duration, max(0.1, duration)), 1)
            self._play_note_pad(pad)

        def _update_note_pad_velocity(self, pad, note_spec, velocity):
            is_selected = note_spec == self._selected_note
            note_spec.velocity = min(127, max(10, velocity))
            self._play_note_pad(pad)

            color = self.NOTE_PAGE_COLORS[self._note_page_number]
            self._leds.led_on(pad, color, int((note_spec.velocity * 6) / 127))

            if is_selected:
                self._leds.delayed("led_on", 1000, pad, color, LED_PULSING_8)

        def _update_note_pad_stutter_count(self, pad, note_spec, stutter_count):
            note_spec.stutter_count = \
                min(MAX_STUTTER_COUNT, max(0, stutter_count))
            self._play_note_pad(pad)

        def _update_note_pad_stutter_duration(self, pad, note_spec, stutter_duration):
            note_spec.stutter_duration = \
                min(MAX_STUTTER_DURATION, max(0, stutter_duration))
            self._play_note_pad(pad)


        def cc_change(self, ccnum, ccval):
            
            if self._pressed_pads:
                if self._note_config is not None:
                    return False

                adjust_pad_func = {
                    KNOB_1: self._update_note_pad_duration,
                    KNOB_2: self._update_note_pad_velocity,
                    KNOB_3: self._update_note_pad_stutter_count,
                    KNOB_4: self._update_note_pad_stutter_duration,
                }.get(ccnum)
                adjust_step_func = {
                    KNOB_1: self._update_step_duration,
                    KNOB_2: self._update_step_velocity,
                    KNOB_3: self._update_step_stutter_count,
                    KNOB_4: self._update_step_stutter_duration,
                }.get(ccnum)

                step_pads = self._pads[:self._used_pads]
                self._pressed_pads_action = "knobs"
                for pad in self._pressed_pads:
                    if adjust_pad_func:
                        note_spec = self._note_pads.get(pad)
                        if note_spec is not None:
                            adjust_pad_func(pad, note_spec, ccval)
                            continue
                    if adjust_step_func:
                        try:
                            step = step_pads.index(pad)
                            adjust_step_func(step, ccval)
                            continue
                        except ValueError:
                            pass
                return True

            # Adjust tempo
            if ccnum == KNOB_1:
                self._show_screen_briefly(
                    screen="tempo", cuia="TEMPO", timeout=1500)
                val = 13.2 + ((ccval / 127) * (420 - 13.2))
                self._zynseq.set_tempo(val)

            # Update sequence's chain volume
            elif ccnum == KNOB_2:
                self._show_screen_briefly(
                    screen="audio_mixer", cuia="SCREEN_AUDIO_MIXER", timeout=1500)
                chain_id = self._get_chain_id_by_sequence(
                    self._zynseq.bank, self._selected_seq)
                chain = self._chain_manager.chains.get(chain_id)
                if chain is not None:
                    mixer_chan = chain.mixer_chan
                    level = max(
                        0, min(100, ccval / 1.27))
                    self._zynmixer.set_level(mixer_chan, level / 100)
