# m3uradioplayer

## Caution

100% Vibe Coding.

## Description

Windows Edition: M3U Radio Player is Internet Radio Player supports mp3, AAC, OGG, FLAC and ASIO.

Linux Edition: Suppots mp3, AAC, OGG, FLAC and Pipewire.

## Need

### Windows:

[bass.dll, bassasio.dll, bassflac.dll.](https://www.un4seen.com)
in same folder.

### Linux:

[bass.so,bassflac.so.](https://www.un4seen.com)
in same folder.

python3-tk

### Both:

[M3U files that wrote internet radio stations.](https://github.com/junguler/m3u-radio-music-playlists)

## How to use

### Windows:

In PowerShell,

```
python .\m3uradioplayer-w.py
```

If you want exe file,

```
python -m pip install pyinstaller

python -m PyInstaller --noconsole --onefile --add-binary ".\bass.dll;." --add-binary ".\bassasio.dll;." --add-binary ".\bassflac.dll;." .\m3uradioplayer-w.py

```

### Linux:

In Terminal Emulator,

```
python3 m3uradioplayer-l.py
```








