Scriptorum 0.5.3 for Linux
==========================

Requirements
  - A 64-bit Linux desktop (x86_64 or aarch64) from about 2022 or later
    (Ubuntu 22.04+, Debian 12+, Fedora 38+, Arch, openSUSE Tumbleweed ...).
  - Python 3.11, 3.12 or 3.13 with the venv module.
  - An internet connection the first time (about 250 MB of Qt is downloaded).

Install
  1. Unpack:            tar xzf Scriptorum-0.5.3-linux.tar.gz
  2. Go into the folder: cd Scriptorum-0.5.3-linux
  3. Run:                ./setup.sh

  Everything goes into your own home folder:
    ~/.local/share/scriptorum-app/venv     the app and its packages
    ~/.local/bin/scriptorum                the command
    a menu entry "Scriptorum", and .scav files open in Scriptorum

Start
  From the applications menu, or type:  scriptorum
  Sample adventures: ~/.local/share/scriptorum-app/samples

If the window does not open
  Run "scriptorum" in a terminal and read the message. The usual cause is a
  missing Qt system library:
    Ubuntu/Debian: sudo apt install libxcb-cursor0 libnss3 libxkbcommon-x11-0
    Fedora:        sudo dnf install xcb-util-cursor nss libxkbcommon-x11
    Arch:          sudo pacman -S xcb-util-cursor nss libxkbcommon-x11
  On Wayland you can also try:  QT_QPA_PLATFORM=xcb scriptorum

Update
  Unpack the newer kit and run its ./setup.sh. Your adventures are untouched.

Remove
  ./uninstall.sh   (your .scav files are left alone; so is the data folder
                    ~/.local/share/scriptorum with modules and settings)

Licence: GPL-3.0-or-later. Bundled fonts: Homemade Apple (Apache 2.0),
Pinyon Script (SIL OFL 1.1).
