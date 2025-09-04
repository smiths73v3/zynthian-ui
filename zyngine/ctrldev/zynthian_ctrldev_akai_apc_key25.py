from zyngine.ctrldev.zynthian_ctrldev_akai_apc_key25_mk2 import \
    zynthian_ctrldev_akai_apc_key25_mk2, FeedbackLEDs

from zyngui import zynthian_gui_config

from zyncoder.zyncore import lib_zyncore
   # lib_zyncore.get_active_midi_chan() does not work

class zynthian_ctrldev_akai_apc_key25(zynthian_ctrldev_akai_apc_key25_mk2):

    dev_ids = ["APC Key 25 MIDI 1", "APC Key 25 IN 1"]
    driver_name = 'AKAI APC Key25'
    unroute_from_chains = True

    def _on_midi_event(self, ev):
        evtype = (ev[0] >> 4) & 0x0F
        channel = ev[0] & 0x0F

        # Direct keybed to chains
        if (channel == 1):
            chain = self.chain_manager.get_active_chain()
            # print(chain.midi_chan)
            # @todo: find out how to get 'last' active chain, for now: just back out.
            if chain.midi_chan is None:
                return
            status = (ev[0] & 0xF0) | chain.midi_chan
            self.zynseq.libseq.sendMidiCommand(status, ev[1], ev[2])
            if self._current_handler != self._stepseq_handler:
                return

        return super()._on_midi_event(ev)
