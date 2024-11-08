#!/usr/bin/python3
# -*- coding: utf-8 -*-
# ******************************************************************************
# ZYNTHIAN PROJECT: Zynthian GUI
#
# Zynthian Touchkeypad Label Configuration GUI Class
#
# Copyright (C) 2024 Pavel Vondřička <pavel.vondricka@ff.cuni.cz>
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
import logging
from time import sleep
from threading import Thread
from subprocess import check_output

# Zynthian specific modules
import zynconf
from zyngui import zynthian_gui_config
from zyngui.zynthian_gui_selector import zynthian_gui_selector

# ------------------------------------------------------------------------------
# Zynthian Touchkeypad Label Configuration GUI Class
# -----------------------------------------------------------------------------

class zynthian_gui_touchkeypad_labels(zynthian_gui_selector):

    def __init__(self):
        super().__init__('Touchkeypad F-key labels', True)
        self.list_data = []

    def build_view(self):
        return super().build_view()

    def fill_list(self):
        self.list_data = []
        if zynthian_gui_config.touch_keypad:
            for i in range(8):
                label = zynthian_gui_config.touch_keypad.get_fkey_label(i)
                self.list_data.append((self.edit_label, i, f"F{i+1}: {label}"))
        super().fill_list()

    def select_action(self, i, t='S'):
        if callable(self.list_data[i][0]):
            self.list_data[i][0](self.list_data[i][1])

    def edit_label(self, n):
        label = zynthian_gui_config.touch_keypad.get_fkey_label(n)
        self.zyngui.show_keyboard(self.rename_label, label)

    def rename_label(self, new_label):
        n = self.list_data[self.index][1]
        zynthian_gui_config.touch_keypad.set_fkey_label(n, new_label)
        self.update_list()

# ------------------------------------------------------------------------------
