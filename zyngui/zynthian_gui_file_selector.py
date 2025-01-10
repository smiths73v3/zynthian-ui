#!/usr/bin/python3
# -*- coding: utf-8 -*-
# ******************************************************************************
# ZYNTHIAN PROJECT: Zynthian GUI
#
# Zynthian GUI File Selector Class
#
# Copyright (C) 2015-2025 Fernando Moyano <jofemodo@zynthian.org>
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

# Zynthian specific modules
from zyngine.zynthian_engine import zynthian_engine
from zyngui.zynthian_gui_selector import zynthian_gui_selector

# ------------------------------------------------------------------------------
# Zynthian File Selector GUI Class
# ------------------------------------------------------------------------------


class zynthian_gui_file_selector(zynthian_gui_selector):

    def __init__(self):
        self.cb_func = None
        self.root_dirs = []
        self.fexts = []
        self.path = None
        self.dirpath = None
        super().__init__('File', True)

    def config(self, cb_func, root_dirs, fexts, path=None):
        self.cb_func = cb_func
        self.root_dirs = root_dirs
        self.fexts = fexts
        if path:
            self.path = path
        else:
            self.path = None
        self.dirpath = self.get_dirpath(self.path)
        self.set_select_path()

    def get_dirpath(self, path):
        if path:
            if os.path.isfile(path):
                (dirpath, fname) = os.path.split(path)
                return dirpath
            elif os.path.isdir(path):
                return path

    def fill_list(self):
        if self.dirpath:
            self.list_data = zynthian_engine.get_filelist(self.dirpath, self.fexts)
        else:
            self.list_data = zynthian_engine.get_bank_dirlist(recursion=0, fexts=self.fexts, root_bank_dirs=self.root_dirs)
        super().fill_list()

    def show(self):
        #if len(self.list_data) > 0:
        super().show()

    def select_action(self, i, t='S'):
        if self.list_data and i < len(self.list_data):
            path = self.list_data[i][0]
            if os.path.isdir(path):
                self.path = path
                self.dirpath = self.get_dirpath(path)
                self.update_list()
                self.set_select_path()
            elif os.path.isfile(path):
                self.path = path
                self.cb_func(path)
                self.zyngui.close_screen()
            else:
                self.zyngui.close_screen()

    def back_action(self):
        if self.dirpath:
            self.dirpath = None
            self.update_list()
            self.set_select_path()
            return True
        return False

    def set_selector(self, zs_hidden=False):
        super().set_selector(zs_hidden)

    def set_select_path(self):
        if self.dirpath:
            parts = os.path.split(self.dirpath)
            self.select_path.set(f"File Selector> {parts[1]}")
        else:
            self.select_path.set("File Selector")

# -------------------------------------------------------------------------------
