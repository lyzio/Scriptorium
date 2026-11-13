# Building the Linux AppImage

Result: `dist/Scriptorum-<version>-linux-x86_64.AppImage` (about 230 MB), one file that runs on mainstream distributions without installing anything.

## 1. The build computer

**Which Linux.** An AppImage runs on Linux with the same or a newer C library (glibc) than the computer it was built on. Build on the oldest system you want to reach. **Ubuntu 22.04 is recommended** (glibc 2.35): the AppImage then runs on Ubuntu 22.04 and newer, Debian 12, Fedora 36 and newer, Linux Mint 21 and newer, and current Arch and openSUSE. Built on Ubuntu 24.04 it would need glibc 2.39 and refuse to start on 22.04. `build.py` says which glibc it is building for.

If your own computer runs something newer, use one of these for the build:
- **distrobox** (easiest, works on any distribution with podman or docker). Create the box once, then work inside it; your home folder is shared:

```
distrobox create --name sc2204 --image ubuntu:22.04
```

```
distrobox enter sc2204
```

- a virtual machine with Ubuntu 22.04 (GNOME Boxes, VirtualBox).

**Processor.** An x86_64 computer gives the x86_64 AppImage. An ARM computer gives an aarch64 AppImage, which needs glibc 2.39 or newer (PySide6 6.8.3 is built that way for ARM).

**Disk and network.** About 4 GB free. Internet the first time: about 600 MB of Python packages from pypi.org, and appimagetool (15 MB) from github.com, checked against its checksum in `kit.json`.

## 2. Install what the build needs (Ubuntu 22.04)

Python 3.13 is not in Ubuntu 22.04 itself; the deadsnakes archive provides it.

```
sudo apt update
```

```
sudo apt install software-properties-common
```

```
sudo add-apt-repository ppa:deadsnakes/ppa
```

```
sudo apt install python3.13 python3.13-venv
```

The system libraries that Qt needs. Most of them the AppImage carries inside, so the user does not need them; the last few (graphics, sound, fonts) every desktop already has, and the build needs them only for its start check:

```
sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libxcb-shape0 libxcb-xkb1 libnss3 libnspr4 libxkbfile1 libxcomposite1 libxdamage1 libxrandr2 libxtst6 libxshmfence1 libxi6 libxfixes3 libgl1 libegl1 libgbm1 libasound2 libfontconfig1 libdbus-1-3
```

On Fedora, for an aarch64 or a test build:

```
sudo dnf install python3.13 xcb-util-cursor libxkbcommon-x11 xcb-util-wm xcb-util-image xcb-util-keysyms xcb-util-renderutil nss nspr libxkbfile libXcomposite libXdamage libXrandr libXtst libxshmfence libXi libXfixes libglvnd-glx libglvnd-egl mesa-libgbm alsa-lib fontconfig dbus-libs
```

If the deadsnakes archive cannot be reached, `uv` installs a standalone Python 3.13 in your home folder instead: `pip install uv`, then `uv python install 3.13`, and use the `python3.13` it reports.

Then let the kit check the computer. Run it in the kit folder; it lists anything still missing with the command that installs it:

```
python3.13 build.py --check
```

## 3. Build

Unzip the build to package (for example `M6-0.6.5.zip` in `~/Downloads`), then in the kit folder:

```
./linux/build-linux.sh ~/Downloads/M6-0.6.5
```

Expect the seven steps, the three smoke-test lines each saying `pass`, and at the end `done …AppImage (… MB)`. Add `--tests` to run the app's automated tests in the build environment first.

## 4. What the AppImage uses from the user's computer

Only what every Linux desktop has and what must match the computer itself: glibc, the graphics driver (OpenGL, EGL, gbm, drm), sound (ALSA, PulseAudio), fontconfig and FreeType, X11/xcb or Wayland, D-Bus, GLib and the C++ runtime. Copies of these from the build computer would clash with the user's driver and desktop, so the build removes them ("left to the computer's own copies" in the log). Everything else is inside.

Two things on the user's side are handled for them:
- **FUSE.** An AppImage mounts itself with FUSE. Without it, `--appimage-extract-and-run` works; the install notes say so.
- **The Chromium sandbox.** Ubuntu 23.10 and newer only allow the sandbox to programs with their own AppArmor profile, which an AppImage cannot bring. `AppRun` notices this and turns the sandbox off there, or the window would stay empty. The pages are Scriptorum's own, under their script policy (F9).

## 5. Test it (T-REL-01, T-REL-02, T-REL-03)

On a clean computer (or a fresh virtual machine) of another distribution, with the network cable out:

```
chmod +x Scriptorum-*-linux-x86_64.AppImage
```

```
./Scriptorum-0.6.5-linux-x86_64.AppImage
```

The start-up window, then the main window. Open the example adventure from Help and export the adventure PDF. For the network check:

```
strace -f -e trace=connect -o net.log ./Scriptorum-0.6.5-linux-x86_64.AppImage
```

```
grep -E "AF_INET|AF_INET6" net.log
```

No output means pass.

## If something goes wrong

| Message | Cause and fix |
|---|---|
| `Python 3.13 is needed` | Run `build.py` with `python3.13` (section 2). |
| `system libraries … are missing` | Install the listed packages; the message gives the command. |
| `pyproject.toml does not pin …` | The app's pyproject.toml lacks an exact pin (`name==version`) for that library. From kit 1.0.2 the kit builds with exactly the versions the app pins, so there is nothing to change in the kit. |
| `the bundled modules hold no font files` | The folder was rebuilt from the project files, which have no fonts. Unzip the complete build zip instead. |
| `[smoke] start: FAIL, Python error at start` | A part of the app was not packed. The message names the module; tell the developer. |
| `the downloaded appimagetool does not match its checksum` | The download was damaged or changed. Delete `work/tools` and try again; if it repeats, do not continue. |
| The AppImage says `GLIBC_2.38 not found` on another computer | It was built on a newer system than that computer (section 1). |
