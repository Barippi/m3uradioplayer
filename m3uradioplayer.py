#!/usr/bin/env python3
import os
import sys
import glob
import json
import platform
import urllib.request
import threading
import ctypes
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"

# ==========================================
# パス解決
# ==========================================
def get_bundle_dir():
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def get_app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

bundle_dir = get_bundle_dir()
app_dir = get_app_dir()

def find_binary(filename):
    p1 = os.path.join(bundle_dir, filename)
    if os.path.exists(p1):
        return p1
    p2 = os.path.join(app_dir, filename)
    if os.path.exists(p2):
        return p2
    return p1

# ==========================================
# 呼出規約・型ラッパーの共通化
# ==========================================
if IS_WINDOWS:
    from ctypes import wintypes
    B_BOOL = wintypes.BOOL
    B_DWORD = wintypes.DWORD
    B_HWND = wintypes.HWND
    CALLBACK_TYPE = ctypes.WINFUNCTYPE
    load_lib = ctypes.WinDLL
else:
    B_BOOL = ctypes.c_bool
    B_DWORD = ctypes.c_uint32
    B_HWND = ctypes.c_void_p
    CALLBACK_TYPE = ctypes.CFUNCTYPE
    load_lib = ctypes.CDLL

# ==========================================
# 構造体・コールバック型定義
# ==========================================
class BASS_DEVICEINFO(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char_p),
        ("driver", ctypes.c_char_p),
        ("flags", B_DWORD),
    ]

class BASS_ASIO_DEVICEINFO(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char_p),
        ("driver", ctypes.c_char_p),
    ]

class BASS_CHANNELINFO(ctypes.Structure):
    _fields_ = [
        ("freq", B_DWORD),
        ("chans", B_DWORD),
        ("flags", B_DWORD),
        ("ctype", B_DWORD),
        ("origres", B_DWORD),
        ("plugin", B_DWORD),
        ("sample", B_DWORD),
        ("filename", ctypes.c_char_p),
    ]

FILECLOSEPROC = CALLBACK_TYPE(None, ctypes.c_void_p)
FILELENPROC = CALLBACK_TYPE(ctypes.c_uint64, ctypes.c_void_p)
FILEREADPROC = CALLBACK_TYPE(B_DWORD, ctypes.c_void_p, B_DWORD, ctypes.c_void_p)
FILESEEKPROC = CALLBACK_TYPE(B_BOOL, ctypes.c_uint64, ctypes.c_void_p)

class BASS_FILEPROCS(ctypes.Structure):
    _fields_ = [
        ("close", FILECLOSEPROC),
        ("length", FILELENPROC),
        ("read", FILEREADPROC),
        ("seek", FILESEEKPROC),
    ]

# 定数
BASS_CONFIG_NET_TIMEOUT = 11
BASS_CONFIG_NET_BUFFER = 12
BASS_CONFIG_NET_PREBUF = 21
BASS_CONFIG_NET_META = 22

BASS_STREAM_DECODE = 0x200000
BASS_STREAM_STATUS = 0x800000
STREAMFILE_BUFFER = 1

BASS_TAG_OGG = 2
BASS_TAG_ICY = 4
BASS_TAG_META = 5

# ==========================================
# 動的ライブラリロード
# ==========================================
bass_name = "bass.dll" if IS_WINDOWS else "libbass.so"
flac_name = "bassflac.dll" if IS_WINDOWS else "libbassflac.so"
asio_name = "bassasio.dll" if IS_WINDOWS else None

bass_path = find_binary(bass_name)
flac_path = find_binary(flac_name)
asio_path = find_binary(asio_name) if asio_name else None

try:
    bass = load_lib(bass_path)
    bassflac = load_lib(flac_path) if os.path.exists(flac_path) else None
    bassasio = load_lib(asio_path) if (IS_WINDOWS and os.path.exists(asio_path)) else None
except Exception as e:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "ライブラリエラー",
        f"オーディオエンジンの読み込みに失敗しました。\nOS: {platform.system()}\n詳細: {e}"
    )
    sys.exit(1)

# BASS 基本 API 定義
bass.BASS_Init.restype = B_BOOL
bass.BASS_Init.argtypes = [ctypes.c_int, B_DWORD, B_DWORD, B_HWND, ctypes.c_void_p]

bass.BASS_SetConfig.restype = B_BOOL
bass.BASS_SetConfig.argtypes = [B_DWORD, B_DWORD]

bass.BASS_ErrorGetCode.restype = ctypes.c_int
bass.BASS_ErrorGetCode.argtypes = []

bass.BASS_GetDeviceInfo.restype = B_BOOL
bass.BASS_GetDeviceInfo.argtypes = [B_DWORD, ctypes.POINTER(BASS_DEVICEINFO)]

bass.BASS_PluginLoad.restype = B_DWORD
bass.BASS_PluginLoad.argtypes = [ctypes.c_char_p, B_DWORD]

bass.BASS_StreamCreateURL.restype = B_DWORD
bass.BASS_StreamCreateURL.argtypes = [ctypes.c_char_p, B_DWORD, B_DWORD, ctypes.c_void_p, ctypes.c_void_p]

bass.BASS_StreamCreateFileUser.restype = B_DWORD
bass.BASS_StreamCreateFileUser.argtypes = [B_DWORD, B_DWORD, ctypes.POINTER(BASS_FILEPROCS), ctypes.c_void_p]

bass.BASS_StreamFree.restype = B_BOOL
bass.BASS_StreamFree.argtypes = [B_DWORD]

bass.BASS_ChannelPlay.restype = B_BOOL
bass.BASS_ChannelPlay.argtypes = [B_DWORD, B_BOOL]

bass.BASS_ChannelStop.restype = B_BOOL
bass.BASS_ChannelStop.argtypes = [B_DWORD]

bass.BASS_ChannelGetInfo.restype = B_BOOL
bass.BASS_ChannelGetInfo.argtypes = [B_DWORD, ctypes.POINTER(BASS_CHANNELINFO)]

bass.BASS_ChannelGetTags.restype = ctypes.c_void_p
bass.BASS_ChannelGetTags.argtypes = [B_DWORD, B_DWORD]

bass.BASS_Free.restype = B_BOOL
bass.BASS_Free.argtypes = []

# Windows 用 BASSASIO API 定義
if IS_WINDOWS and bassasio:
    bassasio.BASS_ASIO_GetDeviceInfo.restype = B_BOOL
    bassasio.BASS_ASIO_GetDeviceInfo.argtypes = [B_DWORD, ctypes.POINTER(BASS_ASIO_DEVICEINFO)]

    bassasio.BASS_ASIO_Init.restype = B_BOOL
    bassasio.BASS_ASIO_Init.argtypes = [B_DWORD, B_DWORD]

    bassasio.BASS_ASIO_Free.restype = B_BOOL
    bassasio.BASS_ASIO_Free.argtypes = []

    bassasio.BASS_ASIO_Start.restype = B_BOOL
    bassasio.BASS_ASIO_Start.argtypes = [B_DWORD, B_DWORD]

    bassasio.BASS_ASIO_Stop.restype = B_BOOL
    bassasio.BASS_ASIO_Stop.argtypes = []

    bassasio.BASS_ASIO_ChannelEnableBASS.restype = B_BOOL
    bassasio.BASS_ASIO_ChannelEnableBASS.argtypes = [B_BOOL, B_DWORD, B_DWORD, B_BOOL]

    bassasio.BASS_ASIO_ChannelReset.restype = B_BOOL
    bassasio.BASS_ASIO_ChannelReset.argtypes = [B_BOOL, ctypes.c_int, B_DWORD]

    bassasio.BASS_ASIO_SetRate.restype = B_BOOL
    bassasio.BASS_ASIO_SetRate.argtypes = [ctypes.c_double]

# ==========================================
# GUI アプリケーション本体
# ==========================================
class UnifiedRadioPlayer:
    def __init__(self, root):
        self.root = root
        self.root.title(f"M3U Radio Player ({platform.system()})")
        self.root.geometry("660x800")

        self.base_dir = app_dir
        self.current_m3u_path = None
        self.m3u_files = {}
        self.asio_devices = []
        self.current_device_id = -1
        self.stream_handle = 0
        self.current_station_name = ""
        self.current_url = ""
        self.current_title = ""

        self.http_response = None
        self.stop_stream_flag = False

        # 出力モード（Windows: asio/wasapi, Linux: pipewire）
        self.output_mode = tk.StringVar(value="asio" if IS_WINDOWS else "pipewire")

        # 1. BASS 初期化
        self.init_bass_engine()

        # 2. FLAC プラグインロード
        self.flac_loaded = False
        if os.path.exists(flac_path):
            encode_path = flac_path.encode("mbcs" if IS_WINDOWS else "utf-8")
            plugin = bass.BASS_PluginLoad(encode_path, 0)
            if plugin != 0:
                self.flac_loaded = True

        # コールバック保持
        self.file_close_proc = FILECLOSEPROC(self._cb_close)
        self.file_len_proc = FILELENPROC(self._cb_len)
        self.file_read_proc = FILEREADPROC(self._cb_read)
        self.file_seek_proc = FILESEEKPROC(self._cb_seek)
        self.file_procs = BASS_FILEPROCS(
            self.file_close_proc,
            self.file_len_proc,
            self.file_read_proc,
            self.file_seek_proc
        )

        self.create_widgets()

        if IS_WINDOWS and bassasio:
            self.load_asio_devices()

        self.refresh_m3u_list()
        self.poll_metadata()

    def init_bass_engine(self):
        """OSに応じた最適なオーディオデバイスで初期化"""
        bass.BASS_SetConfig(BASS_CONFIG_NET_TIMEOUT, 15000)
        bass.BASS_SetConfig(BASS_CONFIG_NET_BUFFER, 5000)
        bass.BASS_SetConfig(BASS_CONFIG_NET_PREBUF, 50)
        bass.BASS_SetConfig(BASS_CONFIG_NET_META, 1)

        if IS_WINDOWS:
            # WASAPI 共有用として既定の Windows デバイス (-1) で初期化
            bass.BASS_Init(-1, 44100, 0, None, None)
        else:
            # Linux: 有効な ALSA / PipeWire デバイスを検出して初期化
            init_ok = False
            info = BASS_DEVICEINFO()
            dev_idx = 1
            while bass.BASS_GetDeviceInfo(dev_idx, ctypes.byref(info)):
                if info.flags & 1:  # BASS_DEVICE_ENABLED
                    if bass.BASS_Init(dev_idx, 44100, 0, None, None):
                        init_ok = True
                        break
                dev_idx += 1
            if not init_ok:
                bass.BASS_Init(1, 44100, 0, None, None)

    def _cb_close(self, user):
        if self.http_response:
            try:
                self.http_response.close()
            except Exception:
                pass
            self.http_response = None

    def _cb_len(self, user):
        return 0

    def _cb_read(self, buffer, length, user):
        if self.stop_stream_flag or not self.http_response:
            return 0
        try:
            chunk = self.http_response.read(length)
            if not chunk:
                return 0
            ctypes.memmove(buffer, chunk, len(chunk))
            return len(chunk)
        except Exception:
            return 0

    def _cb_seek(self, offset, user):
        return False

    def create_widgets(self):
        # 1. プレイリスト選択
        m3u_frame = ttk.LabelFrame(self.root, text="プレイリスト (M3U)", padding=8)
        m3u_frame.pack(fill=tk.X, padx=10, pady=5)

        self.m3u_combo = ttk.Combobox(m3u_frame, state="readonly")
        self.m3u_combo.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(0, 5))
        self.m3u_combo.bind("<<ComboboxSelected>>", self.on_m3u_selected)

        browse_btn = ttk.Button(m3u_frame, text="参照...", width=7, command=self.browse_m3u_file)
        browse_btn.pack(side=tk.RIGHT, padx=(2, 0))

        reload_btn = ttk.Button(m3u_frame, text="再読込", width=7, command=self.refresh_m3u_list)
        reload_btn.pack(side=tk.RIGHT)

        # 2. オーディオ出力設定
        out_frame = ttk.LabelFrame(self.root, text="オーディオ出力設定", padding=8)
        out_frame.pack(fill=tk.X, padx=10, pady=5)

        if IS_WINDOWS:
            mode_box = ttk.Frame(out_frame)
            mode_box.pack(fill=tk.X, pady=(0, 6))

            ttk.Label(mode_box, text="出力モード:").pack(side=tk.LEFT, padx=(0, 10))

            rb_asio = ttk.Radiobutton(
                mode_box, text="ASIO (排他/ビットパーフェクト)", value="asio",
                variable=self.output_mode, command=self.on_mode_changed
            )
            rb_asio.pack(side=tk.LEFT, padx=5)

            rb_wasapi = ttk.Radiobutton(
                mode_box, text="WASAPI 共有モード", value="wasapi",
                variable=self.output_mode, command=self.on_mode_changed
            )
            rb_wasapi.pack(side=tk.LEFT, padx=5)

            self.asio_box = ttk.Frame(out_frame)
            self.asio_box.pack(fill=tk.X)

            ttk.Label(self.asio_box, text="ASIOドライバ:").pack(side=tk.LEFT, padx=(0, 5))
            self.device_combo = ttk.Combobox(self.asio_box, state="readonly")
            self.device_combo.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(0, 5))
            self.device_combo.bind("<<ComboboxSelected>>", self.on_device_selected)

            refresh_dev_btn = ttk.Button(self.asio_box, text="更新", width=7, command=self.load_asio_devices)
            refresh_dev_btn.pack(side=tk.RIGHT)
        else:
            linux_box = ttk.Frame(out_frame)
            linux_box.pack(fill=tk.X)
            ttk.Label(linux_box, text="バックエンド: PipeWire / ALSA 直結 (自動追従)").pack(side=tk.LEFT)

        # 3. Now Playing
        font_family = "Segoe UI" if IS_WINDOWS else "Sans"
        info_frame = ttk.LabelFrame(self.root, text="Now Playing", padding=12)
        info_frame.pack(fill=tk.X, padx=10, pady=5)

        self.track_label = ttk.Label(
            info_frame,
            text="再生待機中",
            font=(font_family, 15, "bold"),
            foreground="#004488",
            wraplength=610
        )
        self.track_label.pack(anchor="w", pady=(0, 4))

        self.station_label = ttk.Label(
            info_frame,
            text="局: 停止中",
            font=(font_family, 9),
            foreground="#555555"
        )
        self.station_label.pack(anchor="w")

        # 4. ステーション一覧
        list_frame = ttk.LabelFrame(self.root, text="ステーション一覧", padding=8)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.tree = ttk.Treeview(list_frame, columns=("URL",), selectmode="browse")
        self.tree.heading("#0", text="局名")
        self.tree.heading("URL", text="ストリームURL")
        self.tree.column("#0", width=220)
        self.tree.column("URL", width=390)
        self.tree.pack(fill=tk.BOTH, expand=True)

        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        # 5. 操作バー
        ctrl_frame = ttk.Frame(self.root, padding=5)
        ctrl_frame.pack(fill=tk.X, padx=10, pady=5)

        flac_status = "FLAC有効" if self.flac_loaded else "FLAC未認識"
        default_status = f"OS: {platform.system()} | {flac_status}"
        self.status_lbl = ttk.Label(ctrl_frame, text=default_status, foreground="#007700")
        self.status_lbl.pack(side=tk.LEFT, padx=5)

        self.stop_btn = ttk.Button(ctrl_frame, text="停止", width=10, command=self.stop)
        self.stop_btn.pack(side=tk.RIGHT, padx=5)

    def on_mode_changed(self):
        if not IS_WINDOWS:
            return
        mode = self.output_mode.get()
        if mode == "asio":
            self.device_combo.config(state="readonly")
            self.status_lbl.config(text="出力: ASIO (排他) モード", foreground="#007700")
        else:
            self.device_combo.config(state="disabled")
            self.status_lbl.config(text="出力: WASAPI 共有モード", foreground="#004488")

        if self.stream_handle and self.current_station_name and self.current_url:
            self.play(self.current_station_name, self.current_url)

    def load_asio_devices(self):
        if not (IS_WINDOWS and bassasio):
            return
        self.asio_devices.clear()
        device_names = []
        info = BASS_ASIO_DEVICEINFO()
        dev_idx = 0

        while bassasio.BASS_ASIO_GetDeviceInfo(dev_idx, ctypes.byref(info)):
            name = info.name.decode('shift_jis', errors='ignore') if info.name else f"Device {dev_idx}"
            self.asio_devices.append((dev_idx, name))
            device_names.append(name)
            dev_idx += 1

        if device_names:
            self.device_combo["values"] = device_names
            self.device_combo.current(0)
            self.init_asio_device(0)
        else:
            self.device_combo["values"] = ["ASIOドライバが見つかりません"]
            self.device_combo.current(0)

    def on_device_selected(self, event):
        idx = self.device_combo.current()
        if 0 <= idx < len(self.asio_devices):
            self.init_asio_device(self.asio_devices[idx][0])

    def init_asio_device(self, dev_id):
        if not (IS_WINDOWS and bassasio):
            return
        if self.current_device_id == dev_id:
            return

        bassasio.BASS_ASIO_Stop()
        bassasio.BASS_ASIO_Free()

        if bassasio.BASS_ASIO_Init(dev_id, 0):
            self.current_device_id = dev_id
            dev_name = self.asio_devices[dev_id][1]
            if self.output_mode.get() == "asio":
                self.status_lbl.config(text=f"ASIO: {dev_name} (接続)", foreground="#007700")

    def refresh_m3u_list(self):
        m3u_patterns = [
            os.path.join(self.base_dir, "*.m3u"),
            os.path.join(self.base_dir, "*.m3u8")
        ]
        found_files = []
        for pat in m3u_patterns:
            found_files.extend(glob.glob(pat))

        self.m3u_files.clear()
        display_names = []

        for path in sorted(found_files):
            filename = os.path.basename(path)
            self.m3u_files[filename] = path
            display_names.append(filename)

        if display_names:
            self.m3u_combo["values"] = display_names
            current_filename = os.path.basename(self.current_m3u_path) if self.current_m3u_path else None
            if current_filename in self.m3u_files:
                self.m3u_combo.set(current_filename)
            else:
                self.m3u_combo.current(0)
                self.load_stations_from_file(self.m3u_files[display_names[0]])
        else:
            self.m3u_combo["values"] = ["M3Uファイルがありません (参照から開く)"]
            self.m3u_combo.current(0)
            self.clear_station_list()

    def on_m3u_selected(self, event):
        selected_name = self.m3u_combo.get()
        if selected_name in self.m3u_files:
            self.load_stations_from_file(self.m3u_files[selected_name])

    def browse_m3u_file(self):
        file_path = filedialog.askopenfilename(
            title="M3Uプレイリストを開く",
            filetypes=[("M3U Playlist", "*.m3u;*.m3u8"), ("All Files", "*.*")]
        )
        if file_path:
            filename = os.path.basename(file_path)
            self.m3u_files[filename] = file_path
            current_values = list(self.m3u_combo["values"])
            if filename not in current_values:
                current_values.append(filename)
                self.m3u_combo["values"] = current_values
            self.m3u_combo.set(filename)
            self.load_stations_from_file(file_path)

    def load_stations_from_file(self, path):
        self.current_m3u_path = path
        stations = self.parse_m3u(path)

        self.clear_station_list()
        for name, url in stations:
            self.tree.insert("", tk.END, text=name, values=(url,))

    def clear_station_list(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def parse_m3u(self, path):
        stations = []
        current_name = "Unknown Station"
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("#EXTINF:"):
                        parts = line.split(",", 1)
                        if len(parts) > 1:
                            current_name = parts[1].strip()
                    elif not line.startswith("#"):
                        stations.append((current_name, line))
                        current_name = "Unknown Station"
        except Exception as e:
            messagebox.showerror("エラー", f"M3Uファイルの読み込みに失敗しました:\n{e}")
        return stations

    def on_select(self, event):
        selected_item = self.tree.selection()
        if not selected_item:
            return
        station_name = self.tree.item(selected_item[0])["text"]
        url = self.tree.item(selected_item[0])["values"][0]
        self.play(station_name, url)

    def play(self, station_name, url):
        self.stop()

        self.current_station_name = station_name
        self.station_label.config(text=f"局: {station_name}")
        self.track_label.config(text="接続中 (バッファリング)...")

        target_url = url.strip()
        is_rp = "radioparadise.com" in target_url

        if is_rp:
            if target_url.startswith("http://"):
                target_url = "https://" + target_url[7:]
            if target_url.endswith("m"):
                target_url = target_url[:-1]

        self.current_url = target_url
        self.current_title = ""
        self.stop_stream_flag = False

        use_asio = (IS_WINDOWS and self.output_mode.get() == "asio")

        flags = BASS_STREAM_STATUS
        if use_asio:
            flags |= BASS_STREAM_DECODE

        self.stream_handle = 0

        # Radio Paradise または FLAC 局の場合は、Python経由でヘッダーを偽装して接続
        if is_rp or "flac" in target_url.lower():
            try:
                ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' if IS_WINDOWS else 'Mozilla/5.0 (X11; Linux x86_64)'
                headers = {'User-Agent': ua, 'Icy-MetaData': '1'}
                req = urllib.request.Request(target_url, headers=headers)
                self.http_response = urllib.request.urlopen(req, timeout=10)

                self.stream_handle = bass.BASS_StreamCreateFileUser(
                    STREAMFILE_BUFFER,
                    flags,
                    ctypes.byref(self.file_procs),
                    None
                )
            except Exception as e:
                print(f"カスタムストリーム接続失敗: {e}")
                self.stream_handle = 0

        # 通常局、またはカスタム接続失敗時は標準 URL オープン
        if not self.stream_handle:
            self.stream_handle = bass.BASS_StreamCreateURL(
                target_url.encode("utf-8"),
                0,
                flags,
                None,
                None
            )

        if not self.stream_handle:
            err_code = bass.BASS_ErrorGetCode()
            messagebox.showerror(
                "再生エラー",
                f"ストリームを開けませんでした。\nエラーコード: {err_code}\nURL: {target_url}"
            )
            self.track_label.config(text="停止中")
            return

        info = BASS_CHANNELINFO()
        bass.BASS_ChannelGetInfo(self.stream_handle, ctypes.byref(info))

        # 出力振り分け
        if use_asio and bassasio:
            bassasio.BASS_ASIO_SetRate(ctypes.c_double(info.freq))
            bassasio.BASS_ASIO_ChannelReset(False, -1, 0)
            bassasio.BASS_ASIO_ChannelEnableBASS(False, 0, self.stream_handle, True)
            bassasio.BASS_ASIO_Start(0, 0)
        else:
            # Linux (PipeWire/ALSA) または Windows WASAPI共有モード
            bass.BASS_ChannelPlay(self.stream_handle, False)

        self.track_label.config(text="再生中 (曲名取得中...)")
        self.extract_metadata()

    def extract_metadata(self):
        if not self.stream_handle:
            return

        found_title = ""

        # 1. BASS_TAG_META (DI.FM, SomaFM などの ICY チャンク)
        meta_ptr = bass.BASS_ChannelGetTags(self.stream_handle, BASS_TAG_META)
        if meta_ptr:
            try:
                raw_meta = ctypes.string_at(meta_ptr).decode("utf-8", errors="ignore")
                for part in raw_meta.split(";"):
                    part = part.strip()
                    if part.startswith("StreamTitle='") and part.endswith("'"):
                        t = part[13:-1].strip()
                        if t:
                            found_title = t
                            break
            except Exception:
                pass

        # 2. BASS_TAG_OGG (Vorbis Comment)
        if not found_title:
            ogg_ptr = bass.BASS_ChannelGetTags(self.stream_handle, BASS_TAG_OGG)
            if ogg_ptr:
                try:
                    raw_bytes = ctypes.string_at(ogg_ptr, 4096)
                    entries = raw_bytes.split(b'\x00')
                    artist, title = "", ""
                    for entry in entries:
                        if not entry:
                            break
                        line = entry.decode("utf-8", errors="ignore")
                        if "=" in line:
                            k, v = line.split("=", 1)
                            if k.upper() == "TITLE":
                                title = v.strip()
                            elif k.upper() == "ARTIST":
                                artist = v.strip()

                    if artist and title:
                        found_title = f"{artist} - {title}"
                    elif title:
                        found_title = title
                except Exception:
                    pass

        # 3. BASS_TAG_ICY (フォールバック)
        if not found_title and not self.current_title:
            icy_ptr = bass.BASS_ChannelGetTags(self.stream_handle, BASS_TAG_ICY)
            if icy_ptr:
                try:
                    raw_icy = ctypes.string_at(icy_ptr, 2048)
                    for line in raw_icy.split(b'\x00'):
                        line_str = line.decode("utf-8", errors="ignore")
                        if line_str.lower().startswith("icy-name:"):
                            station_info = line_str.split(":", 1)[1].strip()
                            if station_info:
                                self.track_label.config(text=f"[{station_info}]")
                except Exception:
                    pass

        if found_title and found_title != self.current_title:
            self.current_title = found_title
            self.track_label.config(text=found_title)

        # 4. Radio Paradise 用 Web API
        if "radioparadise.com" in self.current_url:
            self.fetch_rp_metadata()

    def fetch_rp_metadata(self):
        def _fetch():
            chan = "0"
            if "mellow" in self.current_url:
                chan = "1"
            elif "rock" in self.current_url:
                chan = "2"
            elif "global" in self.current_url:
                chan = "3"

            api_url = f"https://api.radioparadise.com/api/now_playing?chan={chan}"
            try:
                req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=3) as res:
                    data = json.loads(res.read().decode('utf-8'))
                    artist = data.get("artist", "")
                    title = data.get("title", "")
                    if artist and title:
                        display = f"{artist} - {title}"
                        if display != self.current_title:
                            self.current_title = display
                            self.root.after(0, lambda: self.track_label.config(text=display))
            except Exception:
                pass

        threading.Thread(target=_fetch, daemon=True).start()

    def poll_metadata(self):
        if self.stream_handle:
            self.extract_metadata()
        self.root.after(1000, self.poll_metadata)

    def stop(self):
        self.stop_stream_flag = True
        if self.http_response:
            try:
                self.http_response.close()
            except Exception:
                pass
            self.http_response = None

        if self.stream_handle:
            if IS_WINDOWS and bassasio and self.output_mode.get() == "asio":
                bassasio.BASS_ASIO_Stop()
                bassasio.BASS_ASIO_ChannelReset(False, -1, 0)
            else:
                bass.BASS_ChannelStop(self.stream_handle)

            bass.BASS_StreamFree(self.stream_handle)
            self.stream_handle = 0

        self.current_url = ""
        self.current_title = ""
        self.station_label.config(text="局: 停止中")
        self.track_label.config(text="停止中")

    def on_closing(self):
        self.stop()
        if IS_WINDOWS and bassasio:
            bassasio.BASS_ASIO_Free()
        bass.BASS_Free()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = UnifiedRadioPlayer(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()
