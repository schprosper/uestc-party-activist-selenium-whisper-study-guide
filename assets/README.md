# Launcher artwork

`scripts/simple_launcher.ps1` first looks for these optional local assets:

- `assets/launcher-icon.png`
- `assets/launcher-icon.jpg`
- `assets/launcher-icon.jpeg`
- `assets/launcher-icon.bmp`

For the requested GUI style, crop the provided picture to the non-text character/icon area and save it as `assets/launcher-icon.png`. If no image is present, the launcher draws a text-free dark/gold fallback icon.
