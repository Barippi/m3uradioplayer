# m3uradioplayer

## Caution

100% Vibe Coding.

## Need

[bass.dll, bassasio.dll, bassflac.dll.](https://www.un4seen.com)

## How to use

In PowerShell,

```python .\m3uradioplayer.py```

If you want exe file,

```
python -m pip install pyinstaller

python -m PyInstaller --noconsole --onefile --add-binary ".\bass.dll;." --add-binary ".\bassasio.dll;." --add-binary ".\bassflac.dll;." .\m3uradioplayer.py

```
