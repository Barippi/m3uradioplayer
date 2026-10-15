# m3uradioplayer

## Caution

100% Vibe Coding.

## Description

Windows: M3U Radio Player is Internet Radio Player supports mp3, AAC, OGG, FLAC and ASIO.

Linux: Supports mp3, AAC, OGG, FLAC and Pipewire.

## Screenshot

<img width="682" height="912" alt="image" src="https://github.com/user-attachments/assets/8b0d63bc-eac2-401e-811d-6da81c7470d6" />
<img width="810" height="1038" alt="スクリーンショット_20261016_020515" src="https://github.com/user-attachments/assets/fcff5cf2-bcf7-43bd-afa4-6ca1ee94960a" />


## Need

### Windows:

[bass.dll, bassasio.dll, bassflac.dll.](https://www.un4seen.com)
in same folder.

### Linux:

[libbass.so,libbassflac.so.](https://www.un4seen.com)
in same folder.

python3-tk

### Both:

[M3U files that wrote internet radio stations.](https://github.com/junguler/m3u-radio-music-playlists)

## How to use

### Windows:

In PowerShell,

```
python -m pip install tk
python .\m3uradioplayer.py
```

If you want exe file,

```
python -m pip install pyinstaller

python -m PyInstaller --noconsole --onefile `
  --name "M3U Radio Player" `
  --icon ".\m3u_radio_player.ico" `
  --add-binary ".\bass.dll;." `
  --add-binary ".\bassasio.dll;." `
  --add-binary ".\bassflac.dll;." `
  .\m3uradioplayer.py

```

### Linux:

In Terminal Emulator,

```
sudo apt install python3-tk
python3 m3uradioplayer.py
```

If you want executable file,

```
sudo apt install pipx

pipx ensurepath

source ~/.bashrc

pipx install pyinstaller

pyinstaller --noconsole --onefile \
  --name "m3u-radio-player" \
  --add-binary "./libbass.so:." \
  --add-binary "./libbassflac.so:." \
  --add-data "./m3u_radio_player.png:." \
  m3uradioplayer.py
```







