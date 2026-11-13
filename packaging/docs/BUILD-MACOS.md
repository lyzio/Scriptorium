# Building the macOS .dmg

Result: `dist/Scriptorum-<version>-macos-arm64.dmg` on a Mac with Apple silicon, or `…-macos-x86_64.dmg` for Intel Macs. Each runs on macOS 12 (Monterey) or newer (D2).

## 1. The build computer

- **A Mac with macOS 12 or newer.** The build may run on a newer macOS than the users have: the app still asks only for macOS 12.
- **Python 3.13 from python.org**, the "macOS 64-bit universal2 installer". Not Homebrew's Python: Homebrew builds Python for the Mac it runs on, and the app would then need that macOS version or newer.
- **Nothing else.** `codesign`, `hdiutil` and `ditto` are part of macOS. No Xcode, no Apple developer account.
- About 4 GB free disk, and internet the first time (about 600 MB of Python packages from pypi.org).

Install Python 3.13 from https://www.python.org/downloads/macos/ (the newest 3.13.x, universal2 installer). Then, in Terminal, in the kit folder, check that it is the one found:

```
python3.13 --version
```

Expect `Python 3.13.x`. Then let the kit check the computer:

```
python3.13 build.py --check
```

## 2. Which processor

| Build on | Gives | For |
|---|---|---|
| Mac with Apple silicon | `…-macos-arm64.dmg` | Macs with M1 and later |
| Intel Mac | `…-macos-x86_64.dmg` | Intel Macs |
| Mac with Apple silicon, under Rosetta | `…-macos-x86_64.dmg` | Intel Macs |

Qt is universal, but Typst's package comes in one version per processor, so each processor gets its own .dmg. To make the Intel one on an Apple silicon Mac, install Rosetta once (`softwareupdate --install-rosetta`) and run the build through it; the universal2 python.org Python runs as Intel then, and the kit keeps that build's files apart:

```
arch -x86_64 /usr/local/bin/python3.13 build.py ~/Downloads/M6-0.6.5
```

## 3. Build

Unzip the build to package (for example `M6-0.6.5.zip` in `~/Downloads`), then in the kit folder:

```
./macos/build-macos.sh ~/Downloads/M6-0.6.5
```

Expect the seven steps, three smoke-test lines saying `pass`, the signature check, and at the end `done …dmg (… MB)`. Add `--tests` to run the app's automated tests first.

The .dmg holds `Scriptorum.app`, a shortcut to Applications and `Read me first.txt` (the install notes). The app declares `.scav` and `.scmod` as its document types with their own icons.

## 4. Signing

The app is not signed with a paid Apple certificate (D6). It gets an *ad-hoc* signature, which is free: a Mac with Apple silicon refuses to run a program with no signature at all. Because it is not notarised, macOS asks the user to confirm it on the first start. The install notes (`user-docs/INSTALL-macOS.txt`) explain how, for macOS 15 and newer (System Settings › Privacy & Security › Open Anyway) and for macOS 12 to 14 (right-click › Open).

## 5. Test it (T-REL-01, T-REL-02, T-REL-03)

Best on another Mac, or a second user account, with Wi-Fi off. Copy the .dmg there by USB or AirDrop (a download from a browser sets the quarantine flag that users will see; AirDrop does too, which is the point of the test).

1. Open the .dmg, drag Scriptorum to Applications, follow the first-start steps in `Read me first.txt`.
2. The start-up window, then the main window. Open the example adventure from Help and export the adventure PDF.
3. Network check: start Scriptorum, then in Terminal:

```
lsof -i -n -P | grep -i scriptor
```

No output means pass.

4. Double-click a `.scav` and a `.scmod` file in Finder; each has its own icon. (Opening them needs the app change listed in the kit's README.)

## If something goes wrong

| Message | Cause and fix |
|---|---|
| `Python 3.13 is needed` | Install Python 3.13 from python.org (section 1). |
| `pyproject.toml does not pin …` | The app's pyproject.toml lacks an exact pin (`name==version`) for that library. From kit 1.0.2 the kit builds with exactly the versions the app pins, so there is nothing to change in the kit. |
| `[smoke] start: FAIL …` | A part of the app was not packed, or the app did not start. The message names the reason; tell the developer. |
| `codesign … failed` | Run the build again; if it repeats, delete `work/` and build once more. |
| "Scriptorum is damaged and can't be opened" on another Mac | The ad-hoc signature was broken after the build, usually by copying the app with a tool that drops extended attributes. Copy the .dmg itself, not the app. |
