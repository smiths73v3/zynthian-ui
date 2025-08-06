# -*- coding: utf-8 -*-
# ******************************************************************************
# ZYNTHIAN PROJECT: Zynthian Engine (zynthian_engine_inetradio)
#
# zynthian_engine implementation for internet radio streamer
#
# Copyright (C) 2022-2025 Brian Walton <riban@zynthian.org>
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

from collections import OrderedDict
import logging
import json
from subprocess import Popen, STDOUT, PIPE
import socket
from threading import Thread, Timer
from os.path import basename
from os import listdir
from time import sleep, monotonic

from . import zynthian_engine
import zynautoconnect


# ------------------------------------------------------------------------------
# Internet Radio Engine Class
# ------------------------------------------------------------------------------


class zynthian_engine_inet_radio(zynthian_engine):

    # ---------------------------------------------------------------------------
    # Config variables
    # ---------------------------------------------------------------------------

    # ---------------------------------------------------------------------------
    # Initialization
    # ---------------------------------------------------------------------------

    def __init__(self, zyngui=None):
        super().__init__(zyngui)
        self.name = "InternetRadio"
        self.nickname = "IR"
        self.jackname = "inetradio"
        self.type = "Audio Generator"

        self.preset = None # Currently selected preset
        self.preset2bank = [] # List of (bank index, preset index, preset name) for prev/next optimisation
        self.preset_i = 0 # Index of current preset in preset2bank list
        self.pending_preset_i = 0 # Index of preselected pending preset
        self.pending_preset_ts = 0 # Timeout to select pending preset
        self.client = None # Telnet client to vlc
        self.connect_timer = None # Timer to trigger autoconnect

        self.monitors_dict = OrderedDict()
        self.monitors_dict['reset'] = True
        self.monitors_dict['title'] = ""
        self.monitors_dict['info'] = ""
        self.monitors_dict['channels'] = ""
        self.monitors_dict['codec'] = ""
        self.monitors_dict['bitrate'] = ""
        self.monitors_dict['url'] = ""
        self.monitors_dict['reset'] = False
        self.custom_gui_fpath = "/zynthian/zynthian-ui/zyngui/zynthian_widget_inet_radio.py"

        self.command = ["vlc",
                        "--intf", "telnet",
                        "--telnet-password", "zynthian",
                        "--aout", "jack",
                        "--jack-connect-regex", ":::",
                        "--jack-name", self.jackname,
                        "--no-audio-time-stretch"
                        ]

        # MIDI Controllers
        self._ctrls = [
            ['volume', None, 80, 100],
            ['stream', None, 'streaming', ['stopped', 'streaming']],
            ['prev/next', None, '<>', ['<', '<>', '>']],
            ['pause', None, 'playing', ['paused', 'playing']],
            ['random', None, 'off', ['off', 'on']]
        ]

        # Controller Screens
        self._ctrl_screens = [
            ['main', ['volume', 'stream', 'prev/next', 'pause']]
        ]

        self.start()

    # ---------------------------------------------------------------------------
    # Subproccess Management & IPC
    # ---------------------------------------------------------------------------

    def add_processor(self, processor):
        return super().add_processor(processor)

    def start(self):
        if not self.proc:
            logging.info("Starting Engine {}".format(self.name))
            try:
                logging.debug("Command: {}".format(self.command))
                # Turns out that environment's PWD is not set automatically
                # when cwd is specified for pexpect.spawn(), so do it here.
                if self.command_cwd:
                    self.command_env['PWD'] = self.command_cwd
                # Setting cwd is because we've set PWD above. Some engines doesn't
                # care about the process's cwd, but it is more consistent to set
                # cwd when PWD has been set.
                self.command_env['DISPLAY'] = ":-1" # Disable display of GUI to enable CLI
                self.proc = Popen(self.command, env=self.command_env, cwd=self.command_cwd, shell=False,
                                  text=True, bufsize=1, stdout=PIPE, stderr=STDOUT, stdin=PIPE)
                sleep(1)
                self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.client.setblocking(False)
                self.client.settimeout(1)
                self.client.connect(("localhost", 4212)) #TODO Assign port in config
                self.client.recv(4096)
                self.client.send("zynthian\n".encode())
                self.start_proc_poll_thread()
                
            except Exception as err:
                logging.error(
                    "Can't start engine {} => {}".format(self.name, err))

    def stop(self):
        if self.proc:
            try:
                logging.info("Stopping Engine " + self.name)
                self.proc_cmd("shutdown")
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=5)
                except:
                    self.proc.kill()
                self.proc = None
            except Exception as err:
                logging.error(f"Can't stop engine {self.name} => {err}")

    def start_proc_poll_thread(self):
        self.proc_poll_thread = Thread(target=self.proc_poll_thread_task, args=())
        self.proc_poll_thread.name = f"proc_poll_{self.jackname}"
        self.proc_poll_thread.daemon = True  # thread dies with the program
        self.proc_poll_thread.start()

    def proc_cmd(self, cmd):
        if self.client:
            self.client.send(f"{cmd}\n".encode())

    def proc_poll_thread_task(self):
        last_status = 0
        last_info = 0
        line = ""
        while self.proc.poll() is None:
            now = monotonic()
            if self.preset_i == self.pending_preset_i:
                if now > last_info + 5:
                    self.proc_cmd("info")
                    last_info = now
                if now > last_status + 1:
                    self.proc_cmd("status")
                    last_status = now
            buffer = bytes()
            while True:
                try:
                    buffer += self.client.recv(1024)
                except TimeoutError:
                    break
            if buffer:
                for i, c in enumerate(buffer):
                    if c == 13:
                        # newline
                        self.proc_poll_parse_line(line)
                        line = ""
                        buffer = buffer[i:]
                    elif c < 32 or c > 126:
                        continue
                    else:
                        line += chr(c)
                if line:
                    self.proc_poll_parse_line(line)
            if self.pending_preset_i != self.preset_i and now > self.pending_preset_ts:
                self.processors[0].set_bank(self.preset2bank[self.pending_preset_i][0])
                self.processors[0].load_preset_list()
                self.processors[0].set_preset(self.preset2bank[self.pending_preset_i][1])

    def reset_monitors(self, reset_title=False):
        for key in self.monitors_dict:
            if reset_title or key != "title":
                self.monitors_dict[key] = ""

    def proc_poll_parse_line(self, line):
        if line.startswith(">"):
            line = line[1:]
        line = line.strip()
        if line.startswith("| now_playing:"):
            value = line[14:]
            try:
                x = value.strip().split("~")
                self.monitors_dict['info'] = "\n".join(x[:4])
            except:
                self.monitors_dict['info'] = ""
        elif line.startswith("| filename:"):
            if not self.preset[1] and not self.monitors_dict["info"]:
                self.monitors_dict["info"] = basename(line[11:].strip())
        elif line.startswith("( new input:"):
            url = line[12:-1].strip()
            if self.monitors_dict["url"] != url:
                self.delayed_connect_outputs()
                self.reset_monitors()
            self.monitors_dict["url"] = url
            self.monitors_dict["reset"] = True
        elif line.startswith("| album:"):
            self.monitors_dict["info"] = f"{line[8:].strip()}\n\n"
        elif line.startswith("| artist:"):
            self.monitors_dict["info"] += f"{line[9:].strip()}\n"
        else:
            for key in ("title", "Name", "Genre", "Website", "Bitrate", "Channels", "Sample rate", "Codec"):
                if line.startswith(f"| {key}:"):
                    try:
                        self.monitors_dict[key.lower()] = line.split(":")[1].strip()
                    except:
                        pass
                    break


    # ---------------------------------------------------------------------------
    # Processor Management
    # ---------------------------------------------------------------------------

    # ---------------------------------------------------------------------------
    # MIDI Channel Management
    # ---------------------------------------------------------------------------

    # ---------------------------------------------------------------------------
    # Bank Management
    # ---------------------------------------------------------------------------

    def get_bank_list(self, processor=None):
        try:
            with open(self.my_data_dir + "/presets/inet_radio/presets.json", "r") as f:
                self.presets = json.load(f)
        except:
            # Preset file missing or corrupt
            self.presets = {
                "Ambient": [
                    ["http://relax.stream.publicradio.org/relax.mp3",
                        0, "Relax"],
                    ["https://peacefulpiano.stream.publicradio.org/peacefulpiano.aac",
                     0, "Peaceful Piano", "aac", ""],
                    ["http://mp3stream4.abradio.cz/chillout128.mp3",
                     0, "Radio Chillout - ABradio"],
                    ["http://afera.com.pl/afera128.pls",
                     0, "Radio Afera"],
                    ["http://192.111.140.6:8021/listen.pls",
                     0, "Childside Radio"],
                    ["http://usa14.fastcast4u.com/proxy/chillmode",
                     0, "Chillmode Radio"],
                    ["https://radio.streemlion.com:3590/stream", 0, "Nordic Lodge Copenhagen"]
                ],
                "Classical": [
                    ["http://66.42.114.24:8000/live", 0,
                        "Classical Oasis"],
                    ["https://chambermusic.stream.publicradio.org/chambermusic.aac",
                     0, "Chamber Music", "aac", ""],
                    ["https://live.amperwave.net/playlist/mzmedia-cfmzfmmp3-ibc2.m3u", 0, "The New Classical FM"],
                    ["https://audio-mp3.ibiblio.org/wdav-112k", 0, "WDAV Classical: Mozart Café"],
                    ["https://cast1.torontocast.com:2085/stream", 0, "KISS Classical"]
                ],
                "Techno, Trance, House, D&B": [
                    ["https://fr1-play.adtonos.com/8105/psystation-minimal", 0, "PsyStation - Minimal Techno"],
                    ["https://strw3.openstream.co/940", 0, "Minimal & Techno on MixLive.ie"],
                    ["http://stream.radiosputnik.nl:8002/",
                     0, "Radio Sputnik"],
                    ["http://streaming05.liveboxstream.uk:8047/",
                     0, "Select Radio"],
                    ["http://listener3.mp3.tb-group.fm/clt.mp3",
                     0, "ClubTime.FM"],
                    #["http://stream3.jungletrain.net:8000 /;", 0,
                    # "jungletrain.net - 24/7 D&B&J"]
                ],
                "Hiphop, R&B, Trap": [
                    ["https://hiphop24.stream.laut.fm/hiphop24", 0, "HipHop24"],
                    ["http://streams.90s90s.de/hiphop/mp3-192/",
                     0, "90s90s HipHop"],
                    ["https://streams.80s80s.de/hiphop/mp3-192/",
                     0, "80s80s HipHop"],
                    ["http://stream.jam.fm/jamfm-bl/mp3-192/",
                     0, "JAM FM Black Label"],
                    ["http://channels.fluxfm.de/boom-fm-classics/stream.mp3",
                     0, "HipHop Classics"],
                    ["https: // finesthiphopradio.stream.laut.fm / finesthiphopradio", 0, "Finest HipHop Radio"],
                    ["https://stream.bigfm.de/oldschoolrap/mp3-128/", 0, "bigFM OLDSCHOOL RAP & HIP-HOP"]
                ],
                "Funk & Soul": [
                    ["https://funk.stream.laut.fm/funk", 0, "The roots of Funk"],
                    ["http://radio.pro-fhi.net:2199/rqwrejez.pls", 0, "Funk Power Radio"],
                    ["http://listento.thefunkstation.com:8000",
                     0, "The Funk Station"],
                    #["https://scdn.nrjaudio.fm/adwz1/fr/30607/mp3_128.mp3",
                    # 0, "Nostalgie Funk"],
                    ["http://funkyradio.streamingmedia.it/play.mp3",
                     0, "Funky Radio"],
                    ["http://listen.shoutcast.com/a-afunk",
                     0, "Anthology Funk"]
                ],
                "Reggae, Afrobeat, World music": [
                    ["http://ais.rastamusic.com/rastamusic.mp3",
                        0, "Rastamusic Reggae Radio "],
                    ["https://ais-sa2.cdnstream1.com/2294_128.mp3",
                     0, "Big Reggae Mix"],
                    ["http://hd.lagrosseradio.info/lagrosseradio-reggae-192.mp3",
                     0, "La Grosse Radio Reggae"],
                    ["http://api.somafm.com/reggae.pls", 0,
                     "SomaFM: Heavyweight Reggae"],
                    ["http://stream.zenolive.com/n164uxfk8neuv",
                     0, "UbuntuFM Reggae Radio"],
                    ["http://152.228.170.37:8000", 0,
                     "AfroBeats FM"],
                    ["https://wdr-cosmo-afrobeat.icecastssl.wdr.de/wdr/cosmo/afrobeat/mp3/128/stream.mp3",
                     0, "WDR Cosmo - Afrobeat"],
                    ["http://stream.zenolive.com/erfqvd71nd5tv",
                     0, "Rainbow Radio"],
                    ["http://usa6.fastcast4u.com:5374/", 0,
                     "Rainbow Radio - UK"],
                    ["http://topjam.ddns.net:8100/", 0,
                     "TOP JAM Radio Reggae Dancehall"],
                    ["http://stream.jam.fm/jamfm_afrobeats/mp3-192/",
                     0, "JAM FM Afrobeats"]
                ],
                "Jazz & Blues": [
                    ["http://jazzblues.ice.infomaniak.ch/jazzblues-high.mp3",
                        0, "Jazz Blues"],
                    ["http://live.amperwave.net/direct/ppm-jazz24mp3-ibc1",
                     0, "Jazz24 - KNKX-HD2"],
                    # Silent stream ["http://stream.sublime.nl/web24_mp3",
                    # 0, "Sublime Classics"],
                    ["http://jazz-wr01.ice.infomaniak.ch/jazz-wr01-128.mp3",
                     0, "JAZZ RADIO CLASSIC JAZZ"],
                    ["http://jzr-piano.ice.infomaniak.ch/jzr-piano.mp3",
                     0, "JAZZ RADIO PIANO JAZZ"],
                    ["http://stream.radio.co/s7c1ea5960/listen",
                     0, "Capital Jazz Radio"],
                    ["http://radio.wanderingsheep.tv:8000/jazzcafe",
                     0, "Jazz Cafe"],
                    ["https://jazz.stream.laut.fm/jazz",
                     0, "Ministry of Soul"],
                    ["https://stream.spreeradio.de/deluxe/mp3-192/",
                     0, "105‘5 Spreeradio Deluxe"]
                ],
                "Latin & Afrocuban": [
                    ["https://ny.mysonicserver.com/9918/stream",
                        0, "La esquina del guaguanco"],
                    ["http://tropicalisima.net:8020", 0,
                     "Tropicalisima FM Salsa"],
                    ["https://salsa.stream.laut.fm/salsa",
                     0, "Salsa"],
                    ["http://95.216.22.117:8456/stream",
                     0, "Hola NY Salsa"],
                    ["http://stream.zeno.fm/r82w6dp09vzuv",
                     0, "Salseros"],
                    ["http://stream.zenolive.com/tgzmw19rqrquv",
                     0, "Salsa.fm"],
                    ["http://stream.zenolive.com/u27pdewuq74tv",
                     0, "Salsa Gorda Radio"],
                    #["https://salsa-high.rautemusik.fm/", 0, "RauteMusik SALSA"],
                    ["https://centova.streamingcastrd.net/proxy/bastosalsa/stream", 0, "Basto Salsa Radio"],
                    ["https://usa15.fastcast4u.com/proxy/erenteri", 0, "Radio Salsa Online"],
                    #["https://cloudstream2036.conectarhosting.com:8242", 0, "La Makina del Sabor"],
                    #["https://cloudstream2032.conectarhosting.com/8122/stream", 0, "Salsa Magistral"],
                    ["https://cloud8.vsgtech.co/8034/stream", 0, "Viva la salsa"],
                    ["https://cast1.my-control-panel.com/proxy/salsason/stream", 0, "Salsa con Timba"],
                ],
                "Pop & Rock": [
                    ["http://icy.unitedradio.it/VirginRock70.mp3",
                        0, "Virgin Rock 70's"],
                    ["http://sc3.radiocaroline.net:8030/listen.m3u",
                     0, "Radio Caroline"]
                ],
                "Miscellaneous": [
                    ["http://stream.radiotime.com/listen.m3u?streamId=10555650",
                        0, "FIP"],
                    ["http://icecast.radiofrance.fr/fipgroove-hifi.aac",
                     0, "FIP Groove", "aac", ""],
                    ["http://direct.fipradio.fr/live/fip-webradio4.mp3",
                     0, "FIP Radio 4"],
                ],
                "BBC": [
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_01505109/live/ww/bbc_radio_one/bbc_radio_one.isml/bbc_radio_one-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio 1"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_92079267/live/ww/bbc_1xtra/bbc_1xtra.isml/bbc_1xtra-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio 1Xtra"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_62063831/live/ww/bbc_radio_one_dance/bbc_radio_one_dance.isml/bbc_radio_one_dance-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio 1 Dance"
                    ],
                    [
                        "http://as-hls-uk-live.akamaized.net/pool_11351741/live/uk/bbc_radio_one_anthems/bbc_radio_one_anthems.isml/bbc_radio_one_anthems-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio 1 Anthems (UK Only)"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_74208725/live/ww/bbc_radio_two/bbc_radio_two.isml/bbc_radio_two-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio 2"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_23461179/live/ww/bbc_radio_three/bbc_radio_three.isml/bbc_radio_three-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio 3"
                    ],
                    [
                        "http://as-hls-uk-live.akamaized.net/pool_30624046/live/uk/bbc_radio_three_unwind/bbc_radio_three_unwind.isml/bbc_radio_three_unwind-audio%3d320000.norewind.m3u8",
                        0,
                        "BBC Radio 3 Unwind (UK Only)"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_55057080/live/ww/bbc_radio_fourfm/bbc_radio_fourfm.isml/bbc_radio_fourfm-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio 4"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_26173715/live/ww/bbc_radio_four_extra/bbc_radio_four_extra.isml/bbc_radio_four_extra-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio 4 Extra"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_89021708/live/ww/bbc_radio_five_live/bbc_radio_five_live.isml/bbc_radio_five_live-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio 5 Live"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_81827798/live/ww/bbc_6music/bbc_6music.isml/bbc_6music-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio 6 Music"
                    ],
                    [
                        "http://as-hls-uk-live.akamaized.net/pool_47700285/live/uk/bbc_radio_five_live_sports_extra/bbc_radio_five_live_sports_extra.isml/bbc_radio_five_live_sports_extra-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Sports Extra (UK Only)"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_22108647/live/ww/bbc_asian_network/bbc_asian_network.isml/bbc_asian_network-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Asian Network"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_87948813/live/ww/bbc_world_service/bbc_world_service.isml/bbc_world_service-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC World Service (English)"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_79805333/live/ww/bbc_radio_coventry_warwickshire/bbc_radio_coventry_warwickshire.isml/bbc_radio_coventry_warwickshire-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC CWR"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_23657270/live/ww/bbc_radio_essex/bbc_radio_essex.isml/bbc_radio_essex-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Essex"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_80112859/live/ww/bbc_radio_hereford_worcester/bbc_radio_hereford_worcester.isml/bbc_radio_hereford_worcester-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Hereford & Worcester"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_64162474/live/ww/bbc_radio_berkshire/bbc_radio_berkshire.isml/bbc_radio_berkshire-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Berkshire"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_41858929/live/ww/bbc_radio_bristol/bbc_radio_bristol.isml/bbc_radio_bristol-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Bristol"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_21074581/live/ww/bbc_radio_cambridge/bbc_radio_cambridge.isml/bbc_radio_cambridge-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Cambridge"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_72477894/live/ww/bbc_radio_cornwall/bbc_radio_cornwall.isml/bbc_radio_cornwall-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Cornwall"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_85294020/live/ww/bbc_radio_cumbria/bbc_radio_cumbria.isml/bbc_radio_cumbria-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Cumbria"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_24792333/live/ww/bbc_radio_cymru/bbc_radio_cymru.isml/bbc_radio_cymru-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Cymru"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_98610936/live/ww/bbc_radio_cymru_2/bbc_radio_cymru_2.isml/bbc_radio_cymru_2-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Cymru 2"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_63732303/live/ww/bbc_radio_derby/bbc_radio_derby.isml/bbc_radio_derby-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Derby"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_08856933/live/ww/bbc_radio_devon/bbc_radio_devon.isml/bbc_radio_devon-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Devon"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_43178797/live/ww/bbc_radio_foyle/bbc_radio_foyle.isml/bbc_radio_foyle-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Foyle"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_74607547/live/ww/bbc_radio_gloucestershire/bbc_radio_gloucestershire.isml/bbc_radio_gloucestershire-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Gloucestershire"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_65313722/live/ww/bbc_radio_guernsey/bbc_radio_guernsey.isml/bbc_radio_guernsey-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Guernsey"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_43379345/live/ww/bbc_radio_humberside/bbc_radio_humberside.isml/bbc_radio_humberside-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Humberside"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_14000630/live/ww/bbc_radio_jersey/bbc_radio_jersey.isml/bbc_radio_jersey-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Jersey"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_17754185/live/ww/bbc_radio_kent/bbc_radio_kent.isml/bbc_radio_kent-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Kent"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_98146551/live/ww/bbc_radio_lancashire/bbc_radio_lancashire.isml/bbc_radio_lancashire-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Lancashire"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_50115440/live/ww/bbc_radio_leeds/bbc_radio_leeds.isml/bbc_radio_leeds-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Leeds"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_04542919/live/ww/bbc_radio_leicester/bbc_radio_leicester.isml/bbc_radio_leicester-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Leicester"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_77667780/live/ww/bbc_radio_lincolnshire/bbc_radio_lincolnshire.isml/bbc_radio_lincolnshire-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Lincolnshire"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_98137350/live/ww/bbc_london/bbc_london.isml/bbc_london-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio London"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_25317916/live/ww/bbc_radio_manchester/bbc_radio_manchester.isml/bbc_radio_manchester-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Manchester"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_46699767/live/ww/bbc_radio_merseyside/bbc_radio_merseyside.isml/bbc_radio_merseyside-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Merseyside"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_01935182/live/ww/bbc_radio_nan_gaidheal/bbc_radio_nan_gaidheal.isml/bbc_radio_nan_gaidheal-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio nan G\u00e0idheal"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_46887953/live/ww/bbc_radio_newcastle/bbc_radio_newcastle.isml/bbc_radio_newcastle-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Newcastle"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_61510571/live/ww/bbc_radio_norfolk/bbc_radio_norfolk.isml/bbc_radio_norfolk-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Norfolk"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_73827654/live/ww/bbc_radio_northampton/bbc_radio_northampton.isml/bbc_radio_northampton-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Northampton"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_96088503/live/ww/bbc_radio_nottingham/bbc_radio_nottingham.isml/bbc_radio_nottingham-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Nottingham"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_50082558/live/ww/bbc_radio_orkney/bbc_radio_orkney.isml/bbc_radio_orkney-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Orkney"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_19212690/live/ww/bbc_radio_oxford/bbc_radio_oxford.isml/bbc_radio_oxford-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Oxford"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_43322914/live/ww/bbc_radio_scotland_fm/bbc_radio_scotland_fm.isml/bbc_radio_scotland_fm-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Scotland FM"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_59378121/live/ww/bbc_radio_scotland_mw/bbc_radio_scotland_mw.isml/bbc_radio_scotland_mw-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Scotland MW"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_19967704/live/ww/bbc_radio_sheffield/bbc_radio_sheffield.isml/bbc_radio_sheffield-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Sheffield"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_83478576/live/ww/bbc_radio_shropshire/bbc_radio_shropshire.isml/bbc_radio_shropshire-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Shropshire"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_11685351/live/ww/bbc_radio_solent/bbc_radio_solent.isml/bbc_radio_solent-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Solent"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_48517520/live/ww/bbc_radio_solent_west_dorset/bbc_radio_solent_west_dorset.isml/bbc_radio_solent_west_dorset-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Solent West Dorset"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_00727706/live/ww/bbc_radio_somerset_sound/bbc_radio_somerset_sound.isml/bbc_radio_somerset_sound-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Somerset Sound"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_34849862/live/ww/bbc_radio_stoke/bbc_radio_stoke.isml/bbc_radio_stoke-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Stoke"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_18067288/live/ww/bbc_radio_suffolk/bbc_radio_suffolk.isml/bbc_radio_suffolk-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Suffolk"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_27374427/live/ww/bbc_radio_surrey/bbc_radio_surrey.isml/bbc_radio_surrey-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Surrey"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_76643803/live/ww/bbc_radio_sussex/bbc_radio_sussex.isml/bbc_radio_sussex-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Sussex"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_08918172/live/ww/bbc_tees/bbc_tees.isml/bbc_tees-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Tees"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_31244774/live/ww/bbc_radio_ulster/bbc_radio_ulster.isml/bbc_radio_ulster-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Ulster"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_97517794/live/ww/bbc_radio_wales_fm/bbc_radio_wales_fm.isml/bbc_radio_wales_fm-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Wales"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_44240917/live/ww/bbc_radio_wiltshire/bbc_radio_wiltshire.isml/bbc_radio_wiltshire-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio Wiltshire"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_05353924/live/ww/bbc_wm/bbc_wm.isml/bbc_wm-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio WM"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_90848428/live/ww/bbc_radio_york/bbc_radio_york.isml/bbc_radio_york-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Radio York"
                    ],
                    [
                        "http://as-hls-ww-live.akamaized.net/pool_69997923/live/ww/bbc_three_counties_radio/bbc_three_counties_radio.isml/bbc_three_counties_radio-audio%3d96000.norewind.m3u8",
                        0,
                        "BBC Three Counties Radio"
                    ]
                ]
            }
            """
            # Write default preset file
            json_obj = json.dumps(self.presets, indent=4)
            with open(self.my_data_dir + "/presets/inet_radio/presets.json", "w") as f:
                f.write(json_obj)
            """

        self.banks = []
        self.preset2bank = []
        for bank_i, bank in enumerate(self.presets):
            self.banks.append([bank, None, bank, None])
            for preset_i, preset in enumerate(self.presets[bank]):
                self.preset2bank.append((bank_i, preset_i, preset[2]))

        playlists = []
        for file in listdir(f"{self.my_data_dir}/capture"):
            if file[-4:].lower() in (".m3u", ".pls"):
                playlists.append([f"{self.my_data_dir}/capture/{file}", 1, file[:-4]])
        if playlists:
            self.presets["Playlists"] = playlists
            self.banks.append(["Playlists", None, "Playlists", None])

        return self.banks

    # ---------------------------------------------------------------------------
    # Preset Management
    # ---------------------------------------------------------------------------

    def get_preset_list(self, bank):
        presets = []
        for preset in self.presets[bank[0]]:
            presets.append(preset)
        return presets

    def set_preset(self, processor, preset, preload=False):
        self.preset = preset
        for self.preset_i, config in enumerate(self.preset2bank):
            if config[0] == processor.bank_index and config[1] == processor.preset_index:
                break
        self.pending_preset_i = self.preset_i
        self.proc_cmd("clear")
        self.proc_cmd(f"add {preset[0]}")
        self.monitors_dict['title'] = preset[2]
        if preset[1]:
            self._ctrl_screens = [
                ['main', ['volume', 'stream', 'prev/next', 'pause']],
                ['playlist', ['random']]
            ]
        else:
            self._ctrl_screens = [['main', ['volume', 'stream', 'prev/next']]]
        processor.refresh_controllers()
        self.reset_monitors()
        self.delayed_connect_outputs()

    def delayed_connect_outputs(self):
        """ Trigger background delayed audio autoconnect, incase other mechanisms fail"""
        sleep(0.2)
        zynautoconnect.request_audio_connect(True)
        if self.connect_timer:
            self.connect_timer.cancel()
        self.connect_timer = Timer(2, zynautoconnect.audio_autoconnect)
        self.connect_timer.start()
        
    # ----------------------------------------------------------------------------
    # Controllers Management
    # ----------------------------------------------------------------------------

    def send_controller_value(self, zctrl):
        if self.proc is None:
            return
        if zctrl.symbol == "volume":
                self.proc_cmd(f"volume {zctrl.value * 3}")
        elif zctrl.symbol == "prev/next":
            value = zctrl.value - 1
            zctrl.set_value(1, False)
            if self.preset:
                if self.preset[1]:
                    if value > 0:
                        self.proc_cmd(f"next")
                    elif value < 0:
                        self.proc_cmd(f"prev")
                    self.reset_monitors(True)
                    self.proc_cmd("info")
                    sleep(0.2)
                    zynautoconnect.request_audio_connect(True)
                    self.delayed_connect_outputs()
                else:
                    pending_preset = self.pending_preset_i + value
                    if pending_preset < 0 or pending_preset >= len(self.preset2bank):
                        return
                    self.pending_preset_i = pending_preset
                    self.pending_preset_ts = monotonic() + 1
                    self.monitors_dict['title'] = f"<{self.preset2bank[self.pending_preset_i][2]}>"
                    self.monitors_dict['reset'] = True
                    return
        elif zctrl.symbol == "stream":
            if zctrl.value:
                self.proc_cmd("play")
                self.monitors_dict["url"] = ""
                self.delayed_connect_outputs()
            else:
                self.proc_cmd("stop")
        elif zctrl.symbol == "pause":
            # Cannot set absolute pause mode so force pause then toggle
            if zctrl.value:
                self.proc_cmd("play")
            else:
                self.proc_cmd("pause")
        elif zctrl.symbol == "random":
            if zctrl.value:
                self.proc_cmd("random on")
            else:
                self.proc_cmd("random off")
        return

    def get_monitors_dict(self):
        return self.monitors_dict

    # ---------------------------------------------------------------------------
    # Specific functions
    # ---------------------------------------------------------------------------

    # ---------------------------------------------------------------------------
    # API methods
    # ---------------------------------------------------------------------------

# ******************************************************************************
