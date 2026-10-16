#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M3U Radio Player
Cross-platform internet radio player using BASS audio library.
Supports:
  - Windows: 標準 (DirectSound / BASS Direct), ASIO
  - Linux: PipeWire / ALSA
  - Multi-M3U playlist switching
  - Dynamic device switching across all audio endpoints
  - Pure software volume control (Never modifies OS / Hardware master volume)
  - Metadata decode with HTML entity unescaping & multi-charset fallback
"""

import sys
import os
import platform
import ctypes
from ctypes import wintypes
import urllib.request
import urllib.parse
import threading
import time
import html
import tkinter as tk
from tkinter import ttk, messagebox

# ==========================================
# プラットフォーム判定 & パス解決
# ==========================================
OS_NAME = platform.system()
IS_WINDOWS = OS_NAME == "Windows"
IS_LINUX = OS_NAME == "Linux"

def get_bundle_dir():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def get_app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

BUNDLE_DIR = get_bundle_dir()
APP_DIR = get_app_dir()

def find_binary(filename):
    candidates = [
        os.path.join(BUNDLE_DIR, filename),
        os.path.join(APP_DIR, filename),
        os.path.join(APP_DIR, "libs", filename),
        filename
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return filename

# ==========================================
# BASS 構造体 & 型定義
# ==========================================
B_BOOL = wintypes.BOOL if IS_WINDOWS else ctypes.c_bool
B_DWORD = wintypes.DWORD if IS_WINDOWS else ctypes.c_uint32
B_QWORD = ctypes.c_uint64

class BASS_DEVICEINFO(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char_p),
        ("driver", ctypes.c_char_p),
        ("flags", B_DWORD),
    ]

class BASS_CHANNELINFO(ctypes.Structure):
    _fields_ = [
        ("freq", B_DWORD),
        ("chans", B_DWORD),
        ("flags", B_DWORD),
        ("ctype", B_DWORD),
        ("origres", B_DWORD),
        ("plugin", ctypes.c_void_p),
        ("sample", ctypes.c_void_p),
        ("filename", ctypes.c_char_p),
    ]

BASS_CONFIG_NET_AGENT = 1
BASS_CONFIG_NET_PREBUF = 5
BASS_CONFIG_NET_BUFFER = 12
BASS_CONFIG_NET_PLAYLIST = 21
BASS_CONFIG_GVOL_STREAM = 5
BASS_CONFIG_DEV_DEFAULT = 18

BASS_STREAM_DECODE = 0x200000
BASS_STREAM_AUTOFREE = 0x40000
BASS_UNICODE = 0x80000000 if IS_WINDOWS else 0
BASS_SYNC_META = 4
BASS_SYNC_OGG_CHANGE = 12
BASS_TAG_META = 5
BASS_TAG_OGG = 2

# 属性定数
BASS_ATTRIB_FREQ = 1
BASS_ATTRIB_VOL = 2  # ソフトウェアチャンネル音量 (0.0 〜 1.0)

# ==========================================
# ライブラリの動的ロード
# ==========================================
bass = None
bassflac = None
bassasio = None

try:
    bass_lib_name = "bass.dll" if IS_WINDOWS else "libbass.so"
    bass_path = find_binary(bass_lib_name)
    bass = ctypes.WinDLL(bass_path) if IS_WINDOWS else ctypes.CDLL(bass_path)
except Exception as e:
    print(f"[Error] BASS ロード失敗: {e}")

try:
    flac_lib_name = "bassflac.dll" if IS_WINDOWS else "libbassflac.so"
    flac_path = find_binary(flac_lib_name)
    bassflac = ctypes.WinDLL(flac_path) if IS_WINDOWS else ctypes.CDLL(flac_path)
    if bass and bassflac:
        bass.BASS_PluginLoad.restype = ctypes.c_void_p
        if IS_WINDOWS:
            bass.BASS_PluginLoad.argtypes = [ctypes.c_wchar_p, B_DWORD]
            bass.BASS_PluginLoad(flac_path, BASS_UNICODE)
        else:
            bass.BASS_PluginLoad.argtypes = [ctypes.c_char_p, B_DWORD]
            bass.BASS_PluginLoad(flac_path.encode('utf-8'), 0)
except Exception as e:
    print(f"[Info] FLAC プラグイン未ロード: {e}")

if IS_WINDOWS:
    try:
        asio_path = find_binary("bassasio.dll")
        if os.path.exists(asio_path):
            bassasio = ctypes.WinDLL(asio_path)
    except Exception as e:
        print(f"[Info] BASSASIO 未ロード: {e}")

# ==========================================
# BASS 関数プロトタイプ定義
# ==========================================
if bass:
    bass.BASS_Init.restype = B_BOOL
    bass.BASS_Init.argtypes = [ctypes.c_int, B_DWORD, B_DWORD, ctypes.c_void_p, ctypes.c_void_p]
    bass.BASS_Free.restype = B_BOOL
    bass.BASS_SetDevice.restype = B_BOOL
    bass.BASS_SetDevice.argtypes = [B_DWORD]
    bass.BASS_GetDevice.restype = B_DWORD
    bass.BASS_GetDeviceInfo.restype = B_BOOL
    bass.BASS_GetDeviceInfo.argtypes = [B_DWORD, ctypes.POINTER(BASS_DEVICEINFO)]

    bass.BASS_SetConfig.restype = B_BOOL
    bass.BASS_SetConfig.argtypes = [B_DWORD, B_DWORD]
    bass.BASS_SetConfigPtr.restype = B_BOOL
    bass.BASS_SetConfigPtr.argtypes = [B_DWORD, ctypes.c_char_p]

    bass.BASS_StreamCreateURL.restype = B_DWORD
    bass.BASS_StreamCreateURL.argtypes = [ctypes.c_char_p, B_DWORD, B_DWORD, ctypes.c_void_p, ctypes.c_void_p]
    bass.BASS_StreamFree.restype = B_BOOL
    bass.BASS_StreamFree.argtypes = [B_DWORD]
    bass.BASS_ChannelPlay.restype = B_BOOL
    bass.BASS_ChannelPlay.argtypes = [B_DWORD, B_BOOL]
    bass.BASS_ChannelStop.restype = B_BOOL
    bass.BASS_ChannelStop.argtypes = [B_DWORD]
    bass.BASS_ChannelGetInfo.restype = B_BOOL
    bass.BASS_ChannelGetInfo.argtypes = [B_DWORD, ctypes.POINTER(BASS_CHANNELINFO)]
    bass.BASS_ChannelGetData.restype = B_DWORD
    bass.BASS_ChannelGetData.argtypes = [B_DWORD, ctypes.c_void_p, B_DWORD]

    bass.BASS_ChannelSetAttribute.restype = B_BOOL
    bass.BASS_ChannelSetAttribute.argtypes = [B_DWORD, B_DWORD, ctypes.c_float]

    bass.BASS_ChannelSetSync.restype = ctypes.c_void_p
    SYNCPROC = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, B_DWORD, B_DWORD, ctypes.c_void_p) if IS_WINDOWS else ctypes.CFUNCTYPE(None, ctypes.c_void_p, B_DWORD, B_DWORD, ctypes.c_void_p)
    bass.BASS_ChannelSetSync.argtypes = [B_DWORD, B_DWORD, B_QWORD, SYNCPROC, ctypes.c_void_p]

    bass.BASS_ChannelGetTags.restype = ctypes.c_char_p
    bass.BASS_ChannelGetTags.argtypes = [B_DWORD, B_DWORD]
    bass.BASS_ErrorGetCode.restype = ctypes.c_int

if bassasio:
    class BASS_ASIO_DEVICEINFO(ctypes.Structure):
        _fields_ = [("name", ctypes.c_char_p), ("driver", ctypes.c_char_p)]

    bassasio.BASS_ASIO_Init.restype = B_BOOL
    bassasio.BASS_ASIO_Init.argtypes = [ctypes.c_int, B_DWORD]
    bassasio.BASS_ASIO_Free.restype = B_BOOL
    bassasio.BASS_ASIO_Start.restype = B_BOOL
    bassasio.BASS_ASIO_Start.argtypes = [B_DWORD, B_DWORD]
    bassasio.BASS_ASIO_Stop.restype = B_BOOL
    bassasio.BASS_ASIO_SetRate.restype = B_BOOL
    bassasio.BASS_ASIO_SetRate.argtypes = [ctypes.c_double]
    bassasio.BASS_ASIO_ChannelReset.restype = B_BOOL
    bassasio.BASS_ASIO_ChannelReset.argtypes = [B_BOOL, ctypes.c_int, B_DWORD]
    bassasio.BASS_ASIO_ChannelEnableBASS.restype = B_BOOL
    bassasio.BASS_ASIO_ChannelEnableBASS.argtypes = [B_BOOL, B_DWORD, B_DWORD, B_BOOL]
    bassasio.BASS_ASIO_GetDeviceInfo.restype = B_BOOL
    bassasio.BASS_ASIO_GetDeviceInfo.argtypes = [B_DWORD, ctypes.POINTER(BASS_ASIO_DEVICEINFO)]

# ==========================================
# プレイリストパーサー (M3U)
# ==========================================
def parse_m3u(filepath):
    stations = []
    current_title = "Unknown Station"
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("#EXTINF:"):
                    parts = line.split(",", 1)
                    if len(parts) > 1:
                        current_title = parts[1].strip()
                elif not line.startswith("#"):
                    stations.append((current_title, line))
                    current_title = "Unknown Station"
    except Exception as e:
        print(f"M3U 読み込み失敗: {e}")
    return stations

# ==========================================
# メインアプリケーション GUI
# ==========================================
class M3URadioPlayer:
    def __init__(self, root):
        self.root = root
        self.root.title("M3U Radio Player")
        self.root.geometry("680x880")
        self.root.minsize(580, 640)

        self.load_icon()

        self.stream_handle = 0
        self.is_playing = False
        self.stations = []
        self.playlist_files = []
        self.current_active_device = None
        self.current_volume = 1.0  # デフォルトは 100%（0dB、減衰なし）

        self.init_audio_system()
        self.setup_ui()
        self.reload_playlists()

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def load_icon(self):
        icon_png_path = find_binary("m3u_radio_player.png")
        icon_ico_path = find_binary("m3u_radio_player.ico")

        if IS_WINDOWS and os.path.exists(icon_ico_path):
            try:
                self.root.iconbitmap(default=icon_ico_path)
                return
            except Exception:
                pass
        if os.path.exists(icon_png_path):
            try:
                img = tk.PhotoImage(file=icon_png_path)
                self.root.iconphoto(True, img)
            except Exception:
                pass

    def init_audio_system(self):
        if not bass:
            messagebox.showerror("Error", "BASS ライブラリが見つかりません。")
            return

        bass.BASS_SetConfig(BASS_CONFIG_NET_PLAYLIST, 1)

        # BASS 内部ストリーム音量の全体スケールのみ 100% (10000) に設定（OS音量は触らない）
        bass.BASS_SetConfig(BASS_CONFIG_GVOL_STREAM, 10000)

        try:
            bass.BASS_SetConfigPtr(BASS_CONFIG_NET_AGENT, b"Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
            bass.BASS_SetConfig(BASS_CONFIG_NET_BUFFER, 5000)
            bass.BASS_SetConfig(BASS_CONFIG_NET_PREBUF, 50)
        except Exception:
            pass

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding=12)
        main_frame.pack(fill=tk.BOTH, expand=True)

        out_box = ttk.LabelFrame(main_frame, text=" オーディオ出力エンジン & 出力先 ", padding=10)
        out_box.pack(fill=tk.X, pady=(0, 10))

        mode_frame = ttk.Frame(out_box)
        mode_frame.pack(fill=tk.X, pady=2)
        ttk.Label(mode_frame, text="出力モード:").pack(side=tk.LEFT, padx=(0, 6))

        self.mode_var = tk.StringVar()
        if IS_WINDOWS:
            modes = ["標準 (DirectSound / BASS Direct)"]
            if bassasio:
                modes.append("ASIO")
            self.mode_var.set("標準 (DirectSound / BASS Direct)")
        else:
            modes = ["PipeWire / ALSA"]
            self.mode_var.set("PipeWire / ALSA")

        self.mode_combo = ttk.Combobox(mode_frame, textvariable=self.mode_var, values=modes, state="readonly", width=28)
        self.mode_combo.pack(side=tk.LEFT)
        self.mode_combo.bind("<<ComboboxSelected>>", self.on_mode_changed)

        dev_frame = ttk.Frame(out_box)
        dev_frame.pack(fill=tk.X, pady=(6, 2))
        ttk.Label(dev_frame, text="出力デバイス:").pack(side=tk.LEFT, padx=(0, 6))

        self.device_combo = ttk.Combobox(dev_frame, state="readonly")
        self.device_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.device_combo.bind("<<ComboboxSelected>>", self.on_device_changed)

        self.update_device_list()

        status_box = ttk.LabelFrame(main_frame, text=" 再生ステータス ", padding=10)
        status_box.pack(fill=tk.X, pady=(0, 10))

        self.lbl_station = ttk.Label(status_box, text="未再生", font=("Segoe UI", 11, "bold"))
        self.lbl_station.pack(anchor=tk.W)

        self.lbl_track = ttk.Label(status_box, text="タイトル: ---", foreground="#1a73e8", font=("Segoe UI", 10))
        self.lbl_track.pack(anchor=tk.W, pady=2)

        self.lbl_info = ttk.Label(status_box, text="形式: --- | サンプリングレート: ---", foreground="#555555")
        self.lbl_info.pack(anchor=tk.W)

        list_box = ttk.LabelFrame(main_frame, text=" 放送局一覧 ", padding=8)
        list_box.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        pl_bar = ttk.Frame(list_box)
        pl_bar.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(pl_bar, text="プレイリスト:").pack(side=tk.LEFT, padx=(0, 6))

        self.pl_var = tk.StringVar()
        self.pl_combo = ttk.Combobox(pl_bar, textvariable=self.pl_var, state="readonly", width=30)
        self.pl_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.pl_combo.bind("<<ComboboxSelected>>", self.on_playlist_changed)

        tree_frame = ttk.Frame(list_box)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(tree_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree = ttk.Treeview(tree_frame, columns=("Title", "URL"), show="headings", yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.tree.yview)

        self.tree.heading("Title", text="ステーション名")
        self.tree.heading("URL", text="ストリーム URL")
        self.tree.column("Title", width=220, anchor=tk.W)
        self.tree.column("URL", width=380, anchor=tk.W)
        self.tree.pack(fill=tk.BOTH, expand=True)

        self.tree.bind("<Double-1>", lambda e: self.play_selected())

        # -----------------------------
        # 音量 & コントロールエリア
        # -----------------------------
        ctrl_frame = ttk.Frame(main_frame)
        ctrl_frame.pack(fill=tk.X, pady=(4, 0))

        self.btn_play = ttk.Button(ctrl_frame, text="▶ 再生", width=10, command=self.play_selected)
        self.btn_play.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_stop = ttk.Button(ctrl_frame, text="■ 停止", width=10, command=self.stop)
        self.btn_stop.pack(side=tk.LEFT, padx=(0, 12))

        ttk.Label(ctrl_frame, text="音量:").pack(side=tk.LEFT, padx=(0, 4))
        self.vol_scale = ttk.Scale(ctrl_frame, from_=0.0, to=1.0, value=1.0, command=self.on_volume_changed, length=140)
        self.vol_scale.pack(side=tk.LEFT, padx=(0, 6))

        self.lbl_vol = ttk.Label(ctrl_frame, text="100%", width=5)
        self.lbl_vol.pack(side=tk.LEFT)

        self.btn_reload = ttk.Button(ctrl_frame, text="プレイリスト再読込", command=self.reload_playlists)
        self.btn_reload.pack(side=tk.RIGHT)

    def on_volume_changed(self, val):
        self.current_volume = float(val)
        percent = int(self.current_volume * 100)
        self.lbl_vol.config(text=f"{percent}%")
        # BASS内部のストリームゲイン（BASS_ATTRIB_VOL）のみを変更（OSや機器の音量は一切変更しない）
        if self.stream_handle and bass:
            bass.BASS_ChannelSetAttribute(self.stream_handle, BASS_ATTRIB_VOL, ctypes.c_float(self.current_volume))

    def update_device_list(self):
        mode = self.mode_var.get()
        dev_names = []
        self.device_mapping = []
        seen_names = set()

        if IS_WINDOWS:
            if mode == "ASIO" and bassasio:
                info = BASS_ASIO_DEVICEINFO()
                idx = 0
                while bassasio.BASS_ASIO_GetDeviceInfo(idx, ctypes.byref(info)):
                    raw = info.name or b""
                    try:
                        dname = raw.decode('utf-8')
                    except UnicodeDecodeError:
                        dname = raw.decode('cp932', errors='ignore')

                    if dname not in seen_names:
                        seen_names.add(dname)
                        dev_names.append(dname)
                        self.device_mapping.append(idx)
                    idx += 1
            else:
                info = BASS_DEVICEINFO()
                idx = 1
                while bass.BASS_GetDeviceInfo(idx, ctypes.byref(info)):
                    is_enabled = bool(info.flags & 1)
                    if is_enabled:
                        raw = info.name or b""
                        try:
                            dname = raw.decode('utf-8')
                        except UnicodeDecodeError:
                            dname = raw.decode('cp932', errors='ignore')

                        if dname not in seen_names:
                            seen_names.add(dname)
                            dev_names.append(dname)
                            self.device_mapping.append(idx)
                    idx += 1
        else:
            dev_names = ["PipeWire / ALSA デフォルト出力"]
            self.device_mapping = [-1]

        if not dev_names:
            dev_names = ["既定のオーディオデバイス"]
            self.device_mapping = [-1]

        self.device_combo['values'] = dev_names

        default_idx = 0
        for i, name in enumerate(dev_names):
            if any(k in name for k in ["Digital Output", "SPDIF", "Realtek"]):
                default_idx = i
                break
        self.device_combo.current(default_idx)

    def on_mode_changed(self, event=None):
        self.update_device_list()
        if self.is_playing:
            self.play_selected()

    def on_device_changed(self, event=None):
        if self.is_playing:
            self.play_selected()

    def reload_playlists(self):
        self.playlist_files = []
        try:
            for f in sorted(os.listdir(APP_DIR)):
                if f.lower().endswith(".m3u"):
                    self.playlist_files.append(f)
        except Exception as e:
            print(f"プレイリストスキャンエラー: {e}")

        if self.playlist_files:
            self.pl_combo['values'] = self.playlist_files
            current = self.pl_var.get()
            if current not in self.playlist_files:
                self.pl_combo.current(0)
            self.load_active_playlist()
        else:
            self.pl_combo['values'] = ["M3Uファイルがありません"]
            self.pl_combo.current(0)
            for row in self.tree.get_children():
                self.tree.delete(row)
            self.tree.insert("", tk.END, values=("プレイリストがありません (*.m3uを配置)", ""))

    def on_playlist_changed(self, event=None):
        self.load_active_playlist()

    def load_active_playlist(self):
        for row in self.tree.get_children():
            self.tree.delete(row)

        fname = self.pl_var.get()
        target_path = os.path.join(APP_DIR, fname)
        if not os.path.exists(target_path):
            return

        self.stations = parse_m3u(target_path)
        for title, url in self.stations:
            self.tree.insert("", tk.END, values=(title, url))

        if self.stations:
            first = self.tree.get_children()[0]
            self.tree.selection_set(first)

    def stop(self):
        if self.stream_handle:
            if IS_WINDOWS and bassasio:
                bassasio.BASS_ASIO_Stop()
            bass.BASS_ChannelStop(self.stream_handle)
            bass.BASS_StreamFree(self.stream_handle)
            self.stream_handle = 0

        self.is_playing = False
        self.lbl_station.config(text="停止中")
        self.lbl_track.config(text="タイトル: ---")
        self.lbl_info.config(text="形式: --- | サンプリングレート: ---")

    def play_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        item = self.tree.item(sel[0])
        title, url = item['values']
        if not url:
            return

        self.lbl_station.config(text=f"接続中: {title} ...")
        threading.Thread(target=self._play_worker, args=(title, url), daemon=True).start()

    def _play_worker(self, title, url):
        self.stop()
        time.sleep(0.05)

        mode = self.mode_var.get()
        dev_idx = self.device_mapping[self.device_combo.current()] if self.device_mapping else -1

        use_asio = (IS_WINDOWS and mode == "ASIO")
        flags = BASS_STREAM_DECODE if use_asio else BASS_STREAM_AUTOFREE

        if not use_asio:
            target_device = dev_idx if dev_idx != -1 else -1

            if self.current_active_device != target_device:
                bass.BASS_Free()
                if not bass.BASS_Init(target_device, 44100, 0, None, None):
                    err = bass.BASS_ErrorGetCode()
                    if err != 14:
                        print(f"[Warn] BASS_Init failed: code {err}")
                self.current_active_device = target_device

            bass.BASS_SetDevice(target_device)
            # ※ BASS_SetVolume は呼ばない（Windows/機器側のマスター音量を変更しない）
        else:
            if self.current_active_device != -1:
                bass.BASS_Free()
                bass.BASS_Init(-1, 44100, 0, None, None)
                self.current_active_device = -1
            bass.BASS_SetDevice(-1)

        # BASS 全体ストリーム音量を 100% (10000) に維持
        bass.BASS_SetConfig(BASS_CONFIG_GVOL_STREAM, 10000)

        url_bytes = str(url).strip().encode('utf-8')
        handle = bass.BASS_StreamCreateURL(url_bytes, 0, flags, None, None)

        if not handle:
            err = bass.BASS_ErrorGetCode()
            self.root.after(0, lambda: self.lbl_station.config(text=f"接続失敗 (Error: {err})"))
            return

        self.stream_handle = handle
        self.is_playing = True

        # スライダーで指定されている内部ソフトウェア音量を適用
        bass.BASS_ChannelSetAttribute(handle, BASS_ATTRIB_VOL, ctypes.c_float(self.current_volume))

        self._setup_meta_sync(handle)

        info = BASS_CHANNELINFO()
        bass.BASS_ChannelGetInfo(handle, ctypes.byref(info))
        freq = info.freq
        chans = info.chans

        success = False

        if IS_WINDOWS and use_asio and bassasio:
            bassasio.BASS_ASIO_Free()
            if bassasio.BASS_ASIO_Init(dev_idx, 0):
                bassasio.BASS_ASIO_SetRate(ctypes.c_double(freq))
                bassasio.BASS_ASIO_ChannelReset(False, -1, 0)
                bassasio.BASS_ASIO_ChannelEnableBASS(False, 0, handle, True)
                success = bassasio.BASS_ASIO_Start(0, 0)
        else:
            if IS_LINUX:
                bass.BASS_SetConfig(BASS_CONFIG_DEV_DEFAULT, freq)

            success = bass.BASS_ChannelPlay(handle, False)

        if success:
            self.root.after(0, lambda: self.lbl_station.config(text=f"再生中: {title}"))
            self.root.after(0, lambda: self.lbl_info.config(text=f"Ch: {chans}ch | サンプリングレート: {freq} Hz"))
            self._update_meta_now(handle)
        else:
            self.root.after(0, lambda: self.lbl_station.config(text="出力デバイスの起動に失敗しました"))

    # ==========================================
    # メタデータ処理 (HTML実体参照解除 & 文字化け対応)
    # ==========================================
    def _setup_meta_sync(self, handle):
        def _sync_callback(sync_handle, channel, data, user):
            self.root.after(0, lambda: self._update_meta_now(channel))

        self._proc = SYNCPROC(_sync_callback)
        bass.BASS_ChannelSetSync(handle, BASS_SYNC_META, 0, self._proc, None)
        bass.BASS_ChannelSetSync(handle, BASS_SYNC_OGG_CHANGE, 0, self._proc, None)

    def _update_meta_now(self, handle):
        tag_meta = bass.BASS_ChannelGetTags(handle, BASS_TAG_META)
        if tag_meta:
            try:
                meta_str = ""
                for enc in ['utf-8', 'cp932', 'latin-1']:
                    try:
                        meta_str = tag_meta.decode(enc)
                        break
                    except UnicodeDecodeError:
                        continue

                if "StreamTitle='" in meta_str:
                    track = meta_str.split("StreamTitle='")[1].split("';")[0]
                    track = html.unescape(track).strip()
                    self.lbl_track.config(text=f"タイトル: {track}")
                    return
            except Exception as e:
                print(f"[Meta Error] {e}")

        tag_ogg = bass.BASS_ChannelGetTags(handle, BASS_TAG_OGG)
        if tag_ogg:
            try:
                ptr = tag_ogg
                comments = {}
                while True:
                    s = ctypes.string_at(ptr).decode('utf-8', errors='ignore')
                    if not s:
                        break
                    if "=" in s:
                        k, v = s.split("=", 1)
                        comments[k.upper()] = v
                    ptr += len(s.encode('utf-8')) + 1

                artist = html.unescape(comments.get("ARTIST", "")).strip()
                title = html.unescape(comments.get("TITLE", "")).strip()
                if artist and title:
                    self.lbl_track.config(text=f"タイトル: {artist} - {title}")
                    return
                elif title:
                    self.lbl_track.config(text=f"タイトル: {title}")
                    return
            except Exception:
                pass

    def on_closing(self):
        self.stop()
        if bass:
            bass.BASS_Free()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = M3URadioPlayer(root)
    root.mainloop()
