# Releasing the GUI builder

This project uses [Semantic Versioning](https://semver.org/) and
[Keep a Changelog](https://keepachangelog.com/). The version lives in exactly
one place — `builder/version.py` — and everything else (the GUI title bar, the
`.exe`, and the git tag) derives from it.

## Versioning rules

Given a version `MAJOR.MINOR.PATCH`:

- **MAJOR** — incompatible changes to the builder CLI/GUI or module format.
- **MINOR** — new functionality in a backward-compatible way (e.g. a new GUI
  feature or module).
- **PATCH** — backward-compatible bug fixes only.

## Cutting a release

1. **Bump the version.** Edit `builder/version.py` and set `__version__` to the
   new number.

2. **Update the changelog.** In `CHANGELOG.md`, move the items under
   `[Unreleased]` into a new dated section for the version, and add fresh
   `compare`/`releases` links at the bottom.

3. **Commit the two files together.**

   ```bash
   git add builder/version.py CHANGELOG.md
   git commit -m "release: v1.1.0"
   ```

4. **Push the commit** to the default branch.

   ```bash
   git push origin main
   ```

5. **Tag and push the tag.** The tag must be `v` + the exact version in
   `builder/version.py`; the release workflow fails the build if they differ.

   ```bash
   git tag v1.1.0
   git push origin v1.1.0
   ```

## What the tag triggers

Pushing a `v*` tag runs `.github/workflows/release-exe.yml`, which:

1. Checks out the repo on a Windows runner.
2. Verifies the tag matches `builder/version.py`.
3. Builds `dist/MMI3G-Toolkit-Builder.exe` with PyInstaller.
4. Uploads the `.exe` as a workflow artifact.
5. Creates (or updates) the GitHub release for the tag and attaches the `.exe`,
   with auto-generated release notes.

No manual upload step is needed — the release and its `.exe` appear on the
repository's **Releases** page a few minutes after the tag is pushed.

## Building the .exe locally

You do not need to tag to test the executable. From the repository root:

```powershell
./packaging/build_exe.ps1
```

This installs PyInstaller if necessary and writes
`dist/MMI3G-Toolkit-Builder.exe`. The build bundles the `modules/` and `core/`
directories, so the executable is self-contained and does not need the repo
checked out to run.

## Running the GUI from source

No build required:

```bash
python builder/gui.py
```

Tkinter ships with CPython on Windows and macOS. On Linux, install the distro
package (for example `sudo apt install python3-tk`).
