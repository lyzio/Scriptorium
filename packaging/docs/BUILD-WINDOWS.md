# Building the Windows setup program

Result: `dist\Scriptorum-<version>-windows-x64-setup.exe`. It installs Scriptorum for the current user without administrator rights (or for everyone, if chosen), registers `.scav` and `.scmod` with their own icons, and adds Scriptorum to the Start menu and to Settings › Apps for uninstalling.

## 1. The build computer

- **Windows 10 (1809 or newer) or Windows 11, 64-bit (x64).** An Arm Windows PC cannot build it: PySide6 6.8.3 has no Windows Arm packages. The x64 program does run on Arm Windows.
- **Python 3.13, 64-bit, from python.org**, with the `py` launcher (ticked by default in the installer).
- **Inno Setup 6**, free, which makes the setup program.
- About 4 GB free disk, and internet the first time (about 600 MB of Python packages from pypi.org).
- Put the kit in a short folder, for example `C:\scriptorum-packaging`. Qt's file names are long, and Windows still limits paths to 260 characters in some tools.

Install both programs in PowerShell with winget (or download them from python.org and jrsoftware.org):

```
winget install Python.Python.3.13
```

```
winget install JRSoftware.InnoSetup
```

Open a new PowerShell window afterwards, go to the kit folder, and let the kit check the computer:

```
cd C:\scriptorum-packaging
```

```
py -3.13 build.py --check
```

## 2. Build

Unzip the build to package (for example `M6-0.6.5.zip` in Downloads), then in the kit folder:

```
powershell -ExecutionPolicy Bypass -File windows\build-windows.ps1 $env:USERPROFILE\Downloads\M6-0.6.5
```

Expect the seven steps, three smoke-test lines saying `pass`, Inno Setup's output, and at the end `done …setup.exe (… MB)`. Add `--tests` to run the app's automated tests first. If Inno Setup is not found, give its place: `--iscc "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"`.

Windows Defender scans every new file, which makes the freeze step slower; that is normal. Now and then an antivirus program mistakes a freshly built PyInstaller program for a threat. If the build stops because a file vanished, allow the kit's folder in the antivirus and build again.

## 3. Unsigned

The setup program and the app are not signed with a paid certificate (D6). Windows SmartScreen shows "Windows protected your PC" when the setup program is first run; the user clicks **More info**, then **Run anyway**. The install notes (`user-docs/INSTALL-Windows.txt`) explain this, and the setup program shows them before installing.

## 4. Test it (T-REL-01, T-REL-02, T-REL-03)

On another Windows PC (or a Windows Sandbox or virtual machine) with the network off:

1. Run the setup program; get past SmartScreen; install for the current user.
2. Start Scriptorum from the Start menu. The start-up window, then the main window. Open the example adventure from Help and export the adventure PDF.
3. Network check: while Scriptorum runs, in PowerShell:

```
Get-NetTCPConnection -OwningProcess (Get-Process Scriptorum).Id -ErrorAction SilentlyContinue
```

No output means pass.

4. Double-click a `.scav` file (it opens in Scriptorum) and a `.scmod` file; each has its own icon in Explorer.
5. Uninstall from Settings › Apps; the file types are removed with it, and the adventures are untouched.

## If something goes wrong

| Message | Cause and fix |
|---|---|
| `Python 3.13 was not found` | Install Python 3.13 (section 1) and open a new PowerShell window. |
| `running scripts is disabled on this system` | Start the script as shown, with `-ExecutionPolicy Bypass`. |
| `Inno Setup 6 was not found` | Install it (section 1) or give `--iscc` with its path. |
| `pyproject.toml does not pin …` | The app's pyproject.toml lacks an exact pin (`name==version`) for that library. From kit 1.0.2 the kit builds with exactly the versions the app pins, so there is nothing to change in the kit. |
| `[smoke] start: FAIL …` | A part of the app was not packed, or the app did not start. The message names the reason; tell the developer. |
| A path error mentioning a very long file name | Move the kit to a short folder such as `C:\scriptorum-packaging`. |
