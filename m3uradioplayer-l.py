#!/usr/bin/env python3

import os

import sys

import glob

import json

import urllib.request

import threading

import ctypes

import tkinter as tk

from tkinter import ttk, messagebox, filedialog



def get_base_dir():

    return os.path.dirname(os.path.abspath(__file__))



base_dir = get_base_dir()



# ==========================================

# 構造体・コールバック型定義

# ==========================================

class BASS_CHANNELINFO(ctypes.Structure):

    _fields_ = [

        ("freq", ctypes.c_uint32),

        ("chans", ctypes.c_uint32),

        ("flags", ctypes.c_uint32),

        ("ctype", ctypes.c_uint32),

        ("origres", ctypes.c_uint32),

        ("plugin", ctypes.c_uint32),

        ("sample", ctypes.c_uint32),

        ("filename", ctypes.c_char_p),

    ]



FILECLOSEPROC = ctypes.CFUNCTYPE(None, ctypes.c_void_p)

FILELENPROC = ctypes.CFUNCTYPE(ctypes.c_uint64, ctypes.c_void_p)

FILEREADPROC = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p)

FILESEEKPROC = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_uint64, ctypes.c_void_p)



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



BASS_STREAM_STATUS = 0x800000

STREAMFILE_BUFFER = 1



BASS_TAG_OGG = 2

BASS_TAG_ICY = 4

BASS_TAG_META = 5



# ==========================================

# Linux 用 .so ライブラリのロード

# ==========================================

libbass_path = os.path.join(base_dir, "libbass.so")

libbassflac_path = os.path.join(base_dir, "libbassflac.so")



try:

    # Linux では CDLL を使用

    bass = ctypes.CDLL(libbass_path)

    bassflac = ctypes.CDLL(libbassflac_path) if os.path.exists(libbassflac_path) else None

except Exception as e:

    root = tk.Tk()

    root.withdraw()

    messagebox.showerror(

        "ライブラリエラー",

        f"BASS共有ライブラリ (libbass.so) の読み込みに失敗しました。\n"

        f"探索先: {base_dir}\n\n詳細: {e}"

    )

    sys.exit(1)



# BASS 関数定義

bass.BASS_Init.restype = ctypes.c_bool

bass.BASS_Init.argtypes = [ctypes.c_int, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p]



bass.BASS_SetConfig.restype = ctypes.c_bool

bass.BASS_SetConfig.argtypes = [ctypes.c_uint32, ctypes.c_uint32]



bass.BASS_ErrorGetCode.restype = ctypes.c_int

bass.BASS_ErrorGetCode.argtypes = []



bass.BASS_PluginLoad.restype = ctypes.c_uint32

bass.BASS_PluginLoad.argtypes = [ctypes.c_char_p, ctypes.c_uint32]



bass.BASS_StreamCreateURL.restype = ctypes.c_uint32

bass.BASS_StreamCreateURL.argtypes = [ctypes.c_char_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p]



bass.BASS_StreamCreateFileUser.restype = ctypes.c_uint32

bass.BASS_StreamCreateFileUser.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(BASS_FILEPROCS), ctypes.c_void_p]



bass.BASS_StreamFree.restype = ctypes.c_bool

bass.BASS_StreamFree.argtypes = [ctypes.c_uint32]



bass.BASS_ChannelPlay.restype = ctypes.c_bool

bass.BASS_ChannelPlay.argtypes = [ctypes.c_uint32, ctypes.c_bool]



bass.BASS_ChannelStop.restype = ctypes.c_bool

bass.BASS_ChannelStop.argtypes = [ctypes.c_uint32]



bass.BASS_ChannelGetInfo.restype = ctypes.c_bool

bass.BASS_ChannelGetInfo.argtypes = [ctypes.c_uint32, ctypes.POINTER(BASS_CHANNELINFO)]



bass.BASS_ChannelGetTags.restype = ctypes.c_void_p

bass.BASS_ChannelGetTags.argtypes = [ctypes.c_uint32, ctypes.c_uint32]



bass.BASS_Free.restype = ctypes.c_bool

bass.BASS_Free.argtypes = []



# ==========================================

# GUI アプリ本体

# ==========================================

class LinuxRadioPlayer:

    def __init__(self, root):

        self.root = root

        self.root.title("M3U Radio Player (Linux)")

        self.root.geometry("650x760")



        self.base_dir = base_dir

        self.current_m3u_path = None

        self.m3u_files = {}

        self.stream_handle = 0

        self.current_url = ""

        self.current_title = ""



        self.http_response = None

        self.stop_stream_flag = False



        # BASS 初期化（デバイス -1: 既定の ALSA / PulseAudio -> PipeWire）

        if not bass.BASS_Init(-1, 48000, 0, None, None):

            print(f"BASS_Init 失敗: エラーコード {bass.BASS_ErrorGetCode()}")



        bass.BASS_SetConfig(BASS_CONFIG_NET_TIMEOUT, 15000)

        bass.BASS_SetConfig(BASS_CONFIG_NET_BUFFER, 5000)

        bass.BASS_SetConfig(BASS_CONFIG_NET_PREBUF, 50)

        bass.BASS_SetConfig(BASS_CONFIG_NET_META, 1)



        # FLAC プラグインのロード

        self.flac_loaded = False

        if os.path.exists(libbassflac_path):

            plugin = bass.BASS_PluginLoad(libbassflac_path.encode("utf-8"), 0)

            if plugin != 0:

                self.flac_loaded = True



        # コールバック保持（GC防止）

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

        self.refresh_m3u_list()

        self.poll_metadata()



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



        # 2. 再生情報（曲名強調）

        info_frame = ttk.LabelFrame(self.root, text="Now Playing", padding=12)

        info_frame.pack(fill=tk.X, padx=10, pady=5)



        self.track_label = ttk.Label(

            info_frame,

            text="再生待機中",

            font=("Sans", 15, "bold"),

            foreground="#004488",

            wraplength=600

        )

        self.track_label.pack(anchor="w", pady=(0, 4))



        self.station_label = ttk.Label(

            info_frame,

            text="局: 停止中",

            font=("Sans", 9),

            foreground="#555555"

        )

        self.station_label.pack(anchor="w")



        # 3. ステーション一覧

        list_frame = ttk.LabelFrame(self.root, text="ステーション一覧", padding=8)

        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)



        self.tree = ttk.Treeview(list_frame, columns=("URL",), selectmode="browse")

        self.tree.heading("#0", text="局名")

        self.tree.heading("URL", text="ストリームURL")

        self.tree.column("#0", width=220)

        self.tree.column("URL", width=380)

        self.tree.pack(fill=tk.BOTH, expand=True)



        self.tree.bind("<<TreeviewSelect>>", self.on_select)



        # 4. 操作バー

        ctrl_frame = ttk.Frame(self.root, padding=5)

        ctrl_frame.pack(fill=tk.X, padx=10, pady=5)



        flac_status = "FLAC有効" if self.flac_loaded else "FLAC未認識"

        self.status_lbl = ttk.Label(ctrl_frame, text=f"出力: PipeWire/ALSA | {flac_status}", foreground="#007700")

        self.status_lbl.pack(side=tk.LEFT, padx=5)



        self.stop_btn = ttk.Button(ctrl_frame, text="停止", width=10, command=self.stop)

        self.stop_btn.pack(side=tk.RIGHT, padx=5)



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



        flags = BASS_STREAM_STATUS

        self.stream_handle = 0



        # Radio Paradise または FLAC 局の場合は、Python経由でヘッダーを偽装して接続

        if is_rp or "flac" in target_url.lower():

            try:

                headers = {

                    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko)',

                    'Icy-MetaData': '1'

                }

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



        # PipeWire (ALSA/Pulse) で再生開始

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



        # 3. BASS_TAG_ICY

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
            bass.BASS_ChannelStop(self.stream_handle)
            bass.BASS_StreamFree(self.stream_handle)
            self.stream_handle = 0



        self.current_url = ""
        self.current_title = ""
        self.station_label.config(text="局: 停止中")
        self.track_label.config(text="停止中")



    def on_closing(self):
        self.stop()
        bass.BASS_Free()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = LinuxRadioPlayer(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

