# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- GUI reorganised into task tabs (`ttk.Notebook`): **SD-Karte**,
  **Firmware-Tools**, **Splash-Screen**, **Release / Git**.
- SD-Karte module picker is now a `ttk.Treeview` with categories as
  collapsible parent rows and a ☐/☑ selection column, plus a detail panel
  showing the focused module's status, compatibility and description. Replaces
  the previous checkbox list.
- **Info** menu bar with Über (About dialog), README, Changelog, GitHub,
  Releases and MIT license entries; hover tooltips on the main action buttons.
- Root launcher `mmi3g_toolkit.py` (`python mmi3g_toolkit.py`).
- Firmware-Tools auto-analysis: point at a firmware folder and the GUI scans
  it for known files (`.ifs`, `.efs`, `lsd.jxe`, `dsi.jar`, `metainfo2.txt`),
  maps each to the matching analysis/extraction tools, and runs them in order
  into an output folder. Patchers that need explicit targets stay manual.
- Version codename (`__codename__` in `builder/version.py`, "Dinosaurier
  Generation"), shown in the window title and About dialog.
- Startup splash screen with a cartoon dinosaur and the heading "Viel Spaß mit
  den Dinosauriern"; auto-closes, click to skip.
- Firmware-Tools tab runs any `tools/*.py` utility (plus
  `builder/generate_manifest.py`) with arguments and a `--help` button,
  streaming output into the shared log. Each tool shows a German description
  plus its own docstring in a description panel. Tools run in-process
  (`runpy`), so they work from the bundled `.exe` as well as from source; the
  `tools/` folder and `generate_manifest.py` are bundled into the executable.
- Splash-Screen tab converts any image into an 800x480 `startup_generic.png`
  (cover-fit, centered, zoom slider, live preview). Requires Pillow.
- Release / Git tab shows the version, opens the changelog, and drives the
  release workflow: stage `version.py` + `CHANGELOG.md`, commit, tag
  `v<version>`, and push (push actions confirm first).

## [1.1.0] - 2026-10-20

### Added
- Graphical SD-card builder (`builder/gui.py`), a Tkinter front end over the
  existing `build_sd.py`. It discovers modules, filters them by target
  platform, resolves prerequisites, and streams build output into a log pane.
  Requires only the Python standard library (Tkinter).
- `builder/version.py` as the single source of truth for the toolkit version,
  surfaced in the GUI title bar and used to stamp the Windows `.exe`.
- Windows packaging: PyInstaller spec (`packaging/mmi3g-gui.spec`) and a build
  script (`packaging/build_exe.ps1`) that produce a standalone
  `MMI3G-Toolkit-Builder.exe` with the `modules/` and `core/` data bundled.
- Release automation: `.github/workflows/release-exe.yml` builds the `.exe` on
  every `v*` tag and attaches it to the matching GitHub release.
- Release process documentation in `docs/RELEASING.md`.

## [1.0.0] - 2026-04-01

### Added
- Initial public toolkit: 26 modules, Python CLI builder (`build_sd.py`), web
  app, firmware tooling, and research documentation.

[Unreleased]: https://github.com/nirvananils/MMI3G-Toolkit/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/nirvananils/MMI3G-Toolkit/releases/tag/v1.1.0
[1.0.0]: https://github.com/nirvananils/MMI3G-Toolkit/releases/tag/v1.0.0
