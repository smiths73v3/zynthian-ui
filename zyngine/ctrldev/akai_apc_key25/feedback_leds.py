from zyncoder.zyncore import lib_zyncore
from zyngine.ctrldev.zynthian_ctrldev_base_extended import RunTimer
from zyngine.ctrldev.akai_apc_key25.buttons import BUTTONS

# --------------------------------------------------------------------------
# Feedback LEDs controller
# --------------------------------------------------------------------------
class FeedbackLEDs:
    def __init__(self, idev):
        self._idev = idev
        self._state = {}
        self._timer = RunTimer()

    def all_off(self):
        self.control_leds_off()
        self.pad_leds_off()

    def control_leds_off(self):
        buttons = [
            BUTTONS.BTN_UP, BUTTONS.BTN_DOWN, BUTTONS.BTN_LEFT, BUTTONS.BTN_RIGHT, BUTTONS.BTN_KNOB_CTRL_VOLUME,
            BUTTONS.BTN_KNOB_CTRL_PAN, BUTTONS.BTN_KNOB_CTRL_SEND, BUTTONS.BTN_KNOB_CTRL_DEVICE,
            BUTTONS.BTN_SOFT_KEY_CLIP_STOP, BUTTONS.BTN_SOFT_KEY_MUTE, BUTTONS.BTN_SOFT_KEY_SOLO,
            BUTTONS.BTN_SOFT_KEY_REC_ARM, BUTTONS.BTN_SOFT_KEY_SELECT,
        ]
        for btn in buttons:
            self.led_off(btn)

    def pad_leds_off(self):
        buttons = [btn for btn in range(BUTTONS.BTN_PAD_START, BUTTONS.BTN_PAD_END + 1)]
        for btn in buttons:
            self.led_off(btn)

    def led_state(self, led, state):
        (self.led_on if state else self.led_off)(led)

    def led_off(self, led, overlay=False):
        self._timer.remove(led)
        lib_zyncore.dev_send_note_on(self._idev, 0, led, 0)
        if not overlay:
            self._state[led] = (0, 0)

    def led_on(self, led, color=1, brightness=0, overlay=False):
        self._timer.remove(led)
        lib_zyncore.dev_send_note_on(self._idev, brightness, led, color)
        if not overlay:
            self._state[led] = (color, brightness)

    def led_blink(self, led):
        self._timer.remove(led)
        lib_zyncore.dev_send_note_on(self._idev, 0, led, 2)

    def remove_overlay(self, led):
        old_state = self._state.get(led)
        if old_state:
            self.led_on(led, *old_state)
        else:
            self._timer.remove(led)
            lib_zyncore.dev_send_note_on(self._idev, 0, led, 0)

    def delayed(self, action, timeout, led, *args, **kwargs):
        action = getattr(self, action)
        self._timer.add(led, timeout, action, *args, **kwargs)

    def clear_delayed(self, led):
        self._timer.remove(led)
