#!/usr/bin/env python3
"""
MMI3G-Toolkit SD Card Builder - Graphical front end.

A Tkinter GUI over the toolkit. It is organised into tabs by task:

  * SD-Karte       - pick modules (grouped by category) and build an SD card.
  * Firmware-Tools - run the tools/*.py firmware utilities with arguments.
  * Splash-Screen  - convert any image into an 800x480 startup_generic.png.
  * Release / Git  - show the version, open the changelog, and drive the
                     git + release workflow (commit / tag / push).

The SD-Karte tab and the GUI itself need nothing beyond the Python standard
library. The Splash tab needs Pillow; the Firmware and Release tabs only work
from a source checkout (not from the frozen .exe) and degrade gracefully when
unavailable.

Run:
    python builder/gui.py
"""

import contextlib
import glob
import os
import queue
import subprocess
import sys
import threading
import time
import traceback

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# Make sibling modules importable whether launched as a script or a module.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import build_sd  # noqa: E402  (path tweaked above)

try:
    from version import __version__
    try:
        from version import __codename__
    except ImportError:
        __codename__ = ""
except ImportError:  # pragma: no cover - fallback if version.py is missing
    __version__ = "dev"
    __codename__ = ""

try:
    from PIL import Image, ImageTk  # type: ignore
    _HAVE_PIL = True
except ImportError:  # pragma: no cover - Pillow optional
    _HAVE_PIL = False

FROZEN = getattr(sys, "frozen", False)
REPO_ROOT = os.path.dirname(SCRIPT_DIR)

# Base folder that holds bundled data. When frozen, PyInstaller extracts
# modules/, core/, tools/ and builder/ under sys._MEIPASS; from source it is
# the repository root. Used to locate the firmware tools at runtime.
DATA_BASE = getattr(sys, "_MEIPASS", REPO_ROOT) if FROZEN else REPO_ROOT

ASSETS_DIR = os.path.join(DATA_BASE, "assets")
ICON_ICO = os.path.join(ASSETS_DIR, "icon.ico")
ICON_PNG = os.path.join(ASSETS_DIR, "icon.png")

SPLASH_W, SPLASH_H = 800, 480

# Short German one-line descriptions per firmware tool. Shown above the tool's
# own docstring. Keyed by the discovery label ("tools/<file>.py").
TOOL_BLURBS = {
    "tools/build_ifs.py": "Baut ein QNX-IFS-Image aus einem Verzeichnisbaum.",
    "tools/eol_modifier.py": "EOL-Feature-Flags in lsd.jxe anzeigen/ändern "
                             "(Google Earth, Online-Dienste freischalten).",
    "tools/extract_f3s_efs.py": "Extrahiert Dateien aus unkomprimiertem "
                                "MMI3G-EFS-Image.",
    "tools/extract_jars_from_efs.py": "Zieht JAR-Dateien aus einem EFS-Image.",
    "tools/extract_qnx_ifs.py": "Extrahiert Dateien aus einem QNX-IFS (.ifs).",
    "tools/gemmi_tile_proxy.py": "GEMMI-Kachel-Proxy (eigener dbRoot, lokaler "
                                 "Server) - langläufig, mit Ctrl-C/Stop beenden.",
    "tools/inflate_ifs.py": "Dekomprimiert ein komprimiertes QNX-IFS "
                            "(optional extrahieren).",
    "tools/inflate_qnx.py": "Entpackt QNX-Deflate-Dateien.",
    "tools/mu_crc_patcher.py": "Berechnet metainfo2.txt-Prüfsummen eines "
                               "geänderten Firmware-Images neu.",
    "tools/mu_repack.py": "Komplette Firmware-Modifikations-Pipeline in einem "
                          "Befehl (inflate -> patch -> repack -> CRC).",
    "tools/patch_ifs.py": "Ersetzt Dateien in einem dekomprimierten QNX-IFS.",
    "tools/prepare_fsc_deploy.py": "Erzeugt Deploy-Dateien für den "
                                   "FSC-Signatur-Bypass.",
    "tools/repack_ifs.py": "Rekomprimiert ein dekomprimiertes QNX-IFS "
                           "(byte-identisch zu Harman).",
    "tools/retrofit.py": "Wendet DrGER2-Korrekturen auf Modul-Skripte an.",
    "tools/rns850_efs_patcher.py": "RNS-850 EFS-Binär-Patch für FSC-Bypass.",
    "tools/rns850_fsc_patcher.py": "BouncyCastle FSC-Signatur-Bypass für VW "
                                   "RNS-850.",
    "tools/verify_stubs_vs_dsi.py": "Vergleicht Stub-Dateien gegen die "
                                    "DSI-Definitionen.",
    "tools/walk_f3s_efs.py": "Listet/extrahiert den Inhalt eines F3S-EFS-Images.",
    "builder/generate_manifest.py": "Erzeugt docs/app/manifest.json aus dem "
                                    "modules/-Baum (für die Web-App).",
}

# Schritt-für-Schritt-Anleitung je Firmware-Werkzeug. Wird im eigenen
# Anleitungs-Fenster unter Kurzbeschreibung + Original-Hinweisen angezeigt.
# Keyed wie TOOL_BLURBS ("tools/<file>.py").
TOOL_HELP = {
    "tools/build_ifs.py":
        "Baut aus einem extrahierten Dateibaum wieder ein (dekomprimiertes) "
        "QNX-IFS.\n\n"
        "1. Vorher mit inflate_ifs.py --extract einen Baum erzeugen.\n"
        "2. Dateien im Baum ändern/hinzufügen/löschen.\n"
        "3. Argumente setzen: --reference <orig_decomp.ifs> --tree <baum/> "
        "--output <neu_decomp.ifs>\n"
        "4. Danach mit repack_ifs.py komprimieren und mu_crc_patcher.py die "
        "CRCs neu rechnen.\n\n"
        "Die Referenz-IFS liefert den Boot-/Startup-Teil, der nicht neu "
        "erzeugt werden kann.",
    "tools/eol_modifier.py":
        "Zeigt und ändert EOL-Feature-Flags in lsd.jxe (z. B. Google Earth "
        "freischalten).\n\n"
        "Ansehen:\n"
        "  <lsd.jxe> --list                (Master-EOL-Flags)\n"
        "  <lsd.jxe> --show-variant        (aktive Varianten-Overlays)\n"
        "  <lsd.jxe> --list-variants       (verfügbare Varianten-Bundles)\n\n"
        "Ändern:\n"
        "  <lsd.jxe> --output modified_lsd.jxe --enable EOLFLAG_GOOGLE_EARTH\n\n"
        "Danach mit patch_ifs.py --replace lsd/lsd.jxe=modified_lsd.jxe ins "
        "IFS zurückschreiben.\n\n"
        "WARNUNG: Nur Features aktivieren, die das Fahrzeug wirklich hat - "
        "sonst Fehlermeldungen/Instabilität.",
    "tools/extract_f3s_efs.py":
        "Extrahiert Dateien aus einem unkomprimierten MMI3G-EFS-Image "
        "(efs-system.efs, Varianten 41/51).\n\n"
        "1. --list zum Ansehen des Inhalts.\n"
        "2. <image> <ausgabeordner> extrahiert alles.\n"
        "3. --only <text> beschränkt auf passende Pfade.\n\n"
        "Variante 61 ist komprimiert und wird hier NICHT unterstützt.",
    "tools/extract_jars_from_efs.py":
        "Zieht eingebettete JAR-Dateien (dsi.jar, osgi.jar, lsd.jxe u. a.) "
        "aus einem rohen efs-system.efs.\n\n"
        "Aufruf: <efs-system.efs> <ausgabeordner>\n\n"
        "Sucht ZIP-Signaturen im Image. Erwartet ~15-25 Dateien.",
    "tools/extract_qnx_ifs.py":
        "Extrahiert Dateien aus einem bereits dekomprimierten QNX-IFS "
        "(.ifs).\n\n"
        "1. --list listet nur auf.\n"
        "2. <image> <ausgabeordner> extrahiert mit Pfadstruktur.\n"
        "3. --only <text> filtert nach Pfad.\n\n"
        "Hinweis: Komprimierte IFS zuerst mit inflate_ifs.py entpacken.",
    "tools/gemmi_tile_proxy.py":
        "Lokaler GEMMI-Kachel-Proxy (eigener dbRoot) für Google-Earth-"
        "Analyse.\n\n"
        "Langläufiger Server - startet und bleibt offen. Mit Stop (bzw. "
        "Ctrl-C) beenden.\n\n"
        "Braucht dbRoot_custom.bin und auth_resp*.bin im tools/-Ordner.",
    "tools/inflate_ifs.py":
        "Dekomprimiert ein komprimiertes QNX-IFS (ifs-root.ifs) und "
        "extrahiert optional.\n\n"
        "Nur entpacken:  <ifs-root.ifs> -o ifs-root.decomp\n"
        "Entpacken + extrahieren:  <ifs-root.ifs> --extract outdir/\n\n"
        "Braucht gcc + libucl; ohne diese --container nutzen (podman/docker) "
        "oder das automatische Fallback.",
    "tools/inflate_qnx.py":
        "Entpackt einzelne QNX-'iwlyfmbp'-Deflate-Dateien zu nutzbaren "
        "ELF-Binaries.\n\n"
        "Einzeldatei:  <input.bin> <output.bin>\n"
        "Ganzer Ordner:  --recurse <ordner/>  (mit --inplace ersetzen)\n\n"
        "Für Dateien, die extract_f3s_efs.py mit dem Magic 'iwlyfmbp' "
        "ausgibt.",
    "tools/mu_crc_patcher.py":
        "Rechnet die metainfo2.txt-Prüfsummen eines geänderten "
        "Firmware-Images neu, damit SWDL es akzeptiert.\n\n"
        "Aufruf:\n"
        "  --metainfo <metainfo2.txt> --file <geändertes_image> "
        "--section '<Abschnittsname>'\n\n"
        "Mit --dry-run erst anzeigen, was geändert würde. Es gibt KEINE "
        "kryptografischen Signaturen auf den Images, nur CRC32.",
    "tools/mu_repack.py":
        "Komplette Firmware-Pipeline in einem Befehl: entpacken, patchen, "
        "neu packen, CRC.\n\n"
        "Interaktiv (Arbeitsordner zum Bearbeiten):\n"
        "  --mu-archive <datei.tar> --variant 41 --workdir ./work\n\n"
        "Direkt patchen:\n"
        "  --mu-archive <datei.tar> --variant 41 "
        "--replace /usr/apps/MMI3GApplication=./mod --output ./patched/\n\n"
        "Entweder --mu-archive oder --mu-dir angeben, dazu immer --variant.",
    "tools/patch_ifs.py":
        "Ersetzt Dateien in einem dekomprimierten QNX-IFS.\n\n"
        "1. --list zeigt alle Dateien im IFS.\n"
        "2. <input_decomp.ifs> <output.ifs> "
        "--replace <ifs-pfad>=<lokale_datei>  (mehrfach möglich)\n"
        "3. Danach repack_ifs.py + mu_crc_patcher.py.\n\n"
        "Beispiel: --replace lsd/lsd.jxe=./modified_lsd.jxe",
    "tools/prepare_fsc_deploy.py":
        "Erzeugt die Deploy-Dateien für den FSC-Signatur-Bypass auf eine "
        "USB-/SD-Karte.\n\n"
        "Aufruf:  <efs-system.efs> --output <karten-wurzel>\n\n"
        "Schreibt nur in den Ausgabeordner; am Gerät passiert nichts, bis die "
        "Karte eingesteckt wird.",
    "tools/repack_ifs.py":
        "Komprimiert ein dekomprimiertes QNX-IFS wieder (byte-identisch zu "
        "Harman möglich).\n\n"
        "Aufruf:  <input_decomp.ifs> <output_comp.ifs>\n"
        "Bit-identisch:  --reference <orig_komprimiert.ifs>\n\n"
        "--chunk-size nicht über 63000 setzen (u16-Überlauf).",
    "tools/retrofit.py":
        "Wendet die DrGER2-Korrekturen auf alle Modul-Skripte unter modules/ "
        "an (platform.sh-Block + mmi_logstamp).\n\n"
        "Ohne Argumente aufrufen - läuft über den ganzen modules/-Baum.\n\n"
        "Idempotent: bereits angepasste Dateien werden übersprungen. Nur im "
        "Quell-Checkout sinnvoll.",
    "tools/rns850_efs_patcher.py":
        "RNS-850/MMI3G: 1-Byte-FSC-Bypass direkt im efs-system.efs.\n\n"
        "  --analyze   Patch-Stellen zeigen (ändert nichts)\n"
        "  --verify    prüfen, ob schon gepatcht\n"
        "  --patch     Patch anwenden  (optional -o <ausgabedatei>)\n\n"
        "Ändert ein Byte in SignatureBlockProcessor.class und korrigiert die "
        "ZIP-CRCs.",
    "tools/rns850_fsc_patcher.py":
        "BouncyCastle-FSC-Signatur-Bypass für VW RNS-850 (Touareg/Phaeton, "
        "teilt die Plattform mit MMI3G).\n\n"
        "  <efs-system.efs> --analyze         Patch-Punkt finden\n"
        "  <efs-system.efs> --extract-class   Klasse extrahieren + patchen\n"
        "  --output <ordner>                  Zielordner festlegen",
    "tools/verify_stubs_vs_dsi.py":
        "Vergleicht die eigenen Per3Reader-Stubs gegen die echten "
        "Interface-Definitionen in dsi.jar.\n\n"
        "Aufruf:  <dsi.jar>\n\n"
        "Zeigt fehlende Methoden an (die zählen - sonst AbstractMethodError "
        "beim Laden). Braucht 'javap' auf dem PATH (JDK).",
    "tools/walk_f3s_efs.py":
        "Listet/durchläuft ein F3S-EFS-Image (unkomprimiert, Variante "
        "41/51).\n\n"
        "  <image>                       Standardübersicht\n"
        "  <image> --format detailed     ausführlich\n"
        "  --filter <text>               nur passende Namen\n"
        "  --show <n>                    max. n Einträge",
    "builder/generate_manifest.py":
        "Erzeugt docs/app/manifest.json aus dem modules/-Baum für die "
        "Web-App.\n\n"
        "Ohne Argumente aufrufen. Nach jeder Modul-Änderung neu laufen "
        "lassen, damit die Web-App die aktuelle Modulliste zeigt.",
}

# Zusätzliche, modulspezifische Nutzungshinweise. Fehlt ein Eintrag, wird nur
# die generische Anleitung aus den module.json-Feldern gezeigt.
MODULE_HELP = {
    "google-earth":
        "Bestätigt funktionierend. Baut eine SD-Karte, die am Auto einen "
        "lokalen Proxy startet und Satellitenbilder von kh.google.com per "
        "HTTP nachlädt. Kein PC nötig.",
    "gem-activator":
        "Schaltet das Green Engineering Menu (GEM) frei - Grundlage für viele "
        "andere Module. Standalone, ohne VCDS.",
    "splash-screen":
        "Eigenes Boot-Logo. Bild am besten vorher im Tab 'Splash-Screen' zu "
        "startup_generic.png (800x480) umwandeln, nach splashscreens/ legen, "
        "dann dieses Modul bauen.",
    "usb-net":
        "Universeller ASIX-USB-Ethernet-Treiber für MMI3G+/RNS-850. Ersetzt "
        "das veraltete 'lte-setup'.",
    "lte-setup":
        "VERALTET - stattdessen 'usb-net' verwenden.",
    "per3-reader":
        "Installiert ein OSGi-Bundle, das beim MMI-Boot DSI-Persistenzwerte "
        "ausliest. Nach dem Bauen die SD einstecken und neu starten.",
    "system-info":
        "Tiefer Forensik-Dump (Identität, Aktivierungen, Schlüssel, "
        "Persistenz, Logs) auf die SD. Schreibt nichts in den Flash.",
    "variant-dump":
        "Liest Train, MU-Version/Variante, Region, Kernel, HDD-Layout und "
        "FSC-Status aus. Guter erster Schritt zur Identifikation des Geräts.",
}


def _fix_frozen_data_dirs():
    """When bundled as a PyInstaller .exe, repoint build_sd at bundled data.

    The packaging step (packaging/mmi3g-gui.spec) ships modules/ and core/
    next to the frozen code inside sys._MEIPASS. build_sd computes those paths
    at import time from __file__, which is meaningless once frozen, so override
    the module-level globals it actually reads.
    """
    if not FROZEN:
        return
    base = getattr(sys, "_MEIPASS", SCRIPT_DIR)
    build_sd.MODULES_DIR = os.path.join(base, "modules")
    build_sd.CORE_DIR = os.path.join(base, "core")


_fix_frozen_data_dirs()


# Order statuses from most to least trustworthy so each list reads top-down.
STATUS_ORDER = {
    "tested": 0, "ready": 1, "alpha": 2,
    "design": 3, "planned": 4, "deprecated": 5,
}

# Statuses that `--all` builds. Mirrors build_sd.main()'s status == 'ready'.
BUILDABLE_STATUSES = {"ready"}

# Category tab order. Modules are sorted into these by _category_of().
CATEGORY_ORDER = ["Diagnose", "Google Earth", "Netzwerk", "System & Medien", "Sonstige"]


def _category_of(name: str) -> str:
    """Bucket a module into a category tab by keyword, newest-safe."""
    n = name.lower()
    if "gemmi" in n or "google-earth" in n:
        return "Google Earth"
    if any(k in n for k in ("can", "dtc", "diag", "variant", "region",
                            "map-parser", "long-coding", "gauges", "per3",
                            "system-info")):
        return "Diagnose"
    if any(k in n for k in ("lte", "dns", "usb-net", "usb-net")):
        return "Netzwerk"
    if any(k in n for k in ("jvm", "persistence", "password", "gem-activator",
                            "nav", "game", "splash")):
        return "System & Medien"
    return "Sonstige"


# Sentinel pushed on the queue when a background job ends.
_BUILD_DONE = object()


class _StreamRedirector:
    """File-like object that pushes writes onto a thread-safe queue."""

    def __init__(self, sink: "queue.Queue"):
        self._sink = sink

    def write(self, text):
        if text:
            self._sink.put(text)

    def flush(self):
        pass


class _Tooltip:
    """Small hover tooltip for any widget."""

    def __init__(self, widget, text: str, delay: int = 450):
        self.widget = widget
        self.text = text
        self.delay = delay
        self._after = None
        self._tip = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _e=None):
        self._cancel()
        self._after = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self._after:
            self.widget.after_cancel(self._after)
            self._after = None

    def _show(self):
        if self._tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self._tip, text=self.text, justify="left",
                 background="#ffffe0", relief="solid", borderwidth=1,
                 wraplength=360, padx=6, pady=3).pack()

    def _hide(self, _e=None):
        self._cancel()
        if self._tip:
            self._tip.destroy()
            self._tip = None


def _make_scrollable(parent):
    """Return an inner frame inside a vertical-scroll canvas in `parent`."""
    canvas = tk.Canvas(parent, highlightthickness=0)
    scroll = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    inner = ttk.Frame(canvas)
    inner.bind("<Configure>",
               lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
    win = canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.bind("<Configure>",
                lambda e: canvas.itemconfigure(win, width=e.width))
    canvas.configure(yscrollcommand=scroll.set)
    canvas.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")
    canvas.bind_all("<MouseWheel>",
                    lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))
    return inner


class BuilderGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        _cn = f" ({__codename__})" if __codename__ else ""
        root.title(f"MMI3G-Toolkit SD Card Builder  v{__version__}{_cn}")
        root.minsize(820, 640)
        self._app_icon = None  # keep PhotoImage alive
        _apply_window_icon(root)
        self._app_icon = _load_icon_image()

        self.modules = {}
        self.selected = set()      # selected module names
        self.item_name = {}        # tree item id -> module name
        self.name_item = {}        # module name -> tree item id
        self.platform_var = tk.StringVar(value="(any)")
        self.output_var = tk.StringVar(value=os.path.abspath("./sdcard"))
        self._log_queue: "queue.Queue" = queue.Queue()
        self._busy = False
        self._action_buttons = []
        self._preview_img = None  # keep splash preview from being GC'd

        self._build_menubar()
        self._build_notebook()
        self._build_log()
        self._reload_modules()
        self._pump_log()

    # ---- menubar / about -------------------------------------------------

    def _build_menubar(self):
        menubar = tk.Menu(self.root)
        info = tk.Menu(menubar, tearoff=0)
        info.add_command(label="Über…", command=self._show_about)
        info.add_command(label="Anleitung (README)…",
                         command=lambda: self._open_url(
                             "https://github.com/nirvananils/MMI3G-Toolkit"
                             "#readme"))
        info.add_command(label="Changelog…", command=self._open_changelog)
        info.add_separator()
        info.add_command(label="GitHub-Repository…",
                         command=lambda: self._open_url(
                             "https://github.com/nirvananils/MMI3G-Toolkit"))
        info.add_command(label="Releases…",
                         command=lambda: self._open_url(
                             "https://github.com/nirvananils/MMI3G-Toolkit"
                             "/releases"))
        info.add_separator()
        info.add_command(label="Lizenz (MIT)…", command=self._show_license)
        menubar.add_cascade(label="Info", menu=info)
        self.root.config(menu=menubar)

    def _open_url(self, url):
        import webbrowser
        webbrowser.open(url)

    def _show_license(self):
        path = os.path.join(DATA_BASE, "LICENSE")
        text = "MIT License"
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            pass
        self._text_dialog("Lizenz", text)

    def _show_about(self):
        win = tk.Toplevel(self.root)
        win.title("Über MMI3G-Toolkit")
        win.resizable(False, False)
        win.transient(self.root)
        _apply_window_icon(win)
        frm = ttk.Frame(win, padding=16)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="MMI3G-Toolkit SD Card Builder",
                  font=("", 13, "bold")).pack(anchor="w")
        _cn = f"  –  {__codename__}" if __codename__ else ""
        ttk.Label(frm, text=f"Version {__version__}{_cn}").pack(anchor="w")
        ttk.Separator(frm, orient="horizontal").pack(fill="x", pady=8)
        about = (
            "Modulares SD-Karten-Toolkit für Audi/VW MMI 3G, 3G+ und "
            "RNS-850 Infotainment.\n\n"
            "GUI über den Python-Builder: Module wählen, SD-Karte bauen, "
            "Firmware-Werkzeuge ausführen, Splash-Screen erzeugen.\n\n"
            "Basiert auf Community-Forschung (DrGER2, jilleb u. a.). "
            "Kein Bezug zu Audi, Volkswagen oder Harman Becker.\n\n"
            "Dank an die Plauderecke-Community für Austausch und Tests.\n\n"
            "Nutzung auf eigene Gefahr. Lizenz: MIT."
        )
        ttk.Label(frm, text=about, wraplength=420, justify="left").pack(
            anchor="w")
        linkrow = ttk.Frame(frm)
        linkrow.pack(anchor="w", pady=(10, 0))
        ttk.Button(linkrow, text="GitHub", command=lambda: self._open_url(
            "https://github.com/nirvananils/MMI3G-Toolkit")).pack(side="left")
        ttk.Button(linkrow, text="Schließen", command=win.destroy).pack(
            side="left", padx=6)

    def _text_dialog(self, title, text):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.transient(self.root)
        t = tk.Text(win, wrap="word", width=80, height=28)
        t.insert("1.0", text)
        t.config(state="disabled")
        sc = ttk.Scrollbar(win, command=t.yview)
        t.configure(yscrollcommand=sc.set)
        t.pack(side="left", fill="both", expand=True)
        sc.pack(side="right", fill="y")

    def _help_window(self, title, text):
        """Open a standalone, scrollable help/instruction window.

        Used for the per-module and per-tool "Anleitung" buttons so each
        description + how-to appears in its own window.
        """
        win = tk.Toplevel(self.root)
        win.title(title)
        win.transient(self.root)
        _apply_window_icon(win)
        win.geometry("640x480")
        head = ttk.Frame(win, padding=(12, 10, 12, 4))
        head.pack(fill="x")
        if self._app_icon is not None:
            tk.Label(head, image=self._app_icon).pack(side="left", padx=(0, 10))
        ttk.Label(head, text=title, font=("", 13, "bold"),
                  wraplength=520, justify="left").pack(side="left", anchor="w")
        ttk.Separator(win, orient="horizontal").pack(fill="x")
        body = ttk.Frame(win, padding=10)
        body.pack(fill="both", expand=True)
        t = tk.Text(body, wrap="word", background="#f6f6f6", relief="flat",
                    padx=8, pady=8)
        sc = ttk.Scrollbar(body, command=t.yview)
        t.configure(yscrollcommand=sc.set)
        t.insert("1.0", text)
        t.config(state="disabled")
        t.pack(side="left", fill="both", expand=True)
        sc.pack(side="right", fill="y")
        ttk.Button(win, text="Schließen", command=win.destroy).pack(
            anchor="e", padx=12, pady=(0, 10))

    # ---- top-level layout ------------------------------------------------

    def _build_notebook(self):
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=8, pady=(8, 4))

        self.tab_sd = ttk.Frame(self.nb)
        self.tab_fw = ttk.Frame(self.nb)
        self.tab_splash = ttk.Frame(self.nb)
        self.tab_rel = ttk.Frame(self.nb)
        self.nb.add(self.tab_sd, text="SD-Karte")
        self.nb.add(self.tab_fw, text="Firmware-Tools")
        self.nb.add(self.tab_splash, text="Splash-Screen")
        self.nb.add(self.tab_rel, text="Release / Git")

        self._build_sd_tab()
        self._build_firmware_tab()
        self._build_splash_tab()
        self._build_release_tab()

    def _build_log(self):
        logframe = ttk.LabelFrame(self.root, text="Log", padding=6)
        logframe.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.log = tk.Text(logframe, height=9, wrap="word", state="disabled")
        logscroll = ttk.Scrollbar(logframe, command=self.log.yview)
        self.log.configure(yscrollcommand=logscroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        logscroll.pack(side="right", fill="y")

    # ---- SD-Karte tab ----------------------------------------------------

    def _build_sd_tab(self):
        t = self.tab_sd
        top = ttk.Frame(t, padding=(8, 8, 8, 4))
        top.pack(fill="x")

        ttk.Label(top, text="Zielplattform:").grid(row=0, column=0, sticky="w")
        platforms = ["(any)"] + list(build_sd.SUPPORTED_PLATFORMS)
        combo = ttk.Combobox(top, textvariable=self.platform_var,
                             values=platforms, state="readonly", width=14)
        combo.grid(row=0, column=1, sticky="w", padx=(6, 20))
        combo.bind("<<ComboboxSelected>>", lambda _e: self._apply_filter())

        ttk.Label(top, text="Ausgabeordner:").grid(row=0, column=2, sticky="w")
        ttk.Entry(top, textvariable=self.output_var, width=38).grid(
            row=0, column=3, sticky="we", padx=6)
        ttk.Button(top, text="Durchsuchen...", command=self._choose_output).grid(
            row=0, column=4, sticky="w")
        top.columnconfigure(3, weight=1)

        helpers = ttk.Frame(t, padding=(8, 0))
        helpers.pack(fill="x")
        ttk.Button(helpers, text="Baubare wählen",
                   command=self._select_buildable).pack(side="left")
        ttk.Button(helpers, text="Alle sichtbaren",
                   command=lambda: self._set_all_visible(True)).pack(
            side="left", padx=6)
        ttk.Button(helpers, text="Auswahl leeren",
                   command=lambda: self._set_all_visible(False)).pack(side="left")
        self.count_label = ttk.Label(helpers, text="")
        self.count_label.pack(side="right")

        ttk.Label(t, text="Klick auf ☐/☑ oder Leertaste wählt ein Modul. "
                         "Kategorien aufklappbar.", foreground="#555",
                  padding=(8, 2)).pack(anchor="w")

        # Treeview: categories as parent rows, modules as children.
        treewrap = ttk.Frame(t)
        treewrap.pack(fill="both", expand=True, padx=8, pady=(4, 6))
        cols = ("status", "compatible")
        self.tree = ttk.Treeview(treewrap, columns=cols, show="tree headings",
                                 selectmode="browse")
        self.tree.heading("#0", text="Modul")
        self.tree.heading("status", text="Status")
        self.tree.heading("compatible", text="Kompatibel")
        self.tree.column("#0", width=300, stretch=False)
        self.tree.column("status", width=90, anchor="center", stretch=False)
        self.tree.column("compatible", width=220, stretch=True)
        tscroll = ttk.Scrollbar(treewrap, orient="vertical",
                                command=self.tree.yview)
        self.tree.configure(yscrollcommand=tscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tscroll.pack(side="right", fill="y")
        self.tree.tag_configure("category", font=("", 10, "bold"))
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<space>", self._on_tree_space)
        self.tree.bind("<Double-Button-1>", self._on_tree_double)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        # Detail panel below the tree.
        det = ttk.LabelFrame(t, text="Details", padding=6)
        det.pack(fill="x", padx=8, pady=(0, 6))
        self.detail = tk.Text(det, height=4, wrap="word", state="disabled",
                              background="#f6f6f6")
        self.detail.pack(fill="x")
        self._current_module = None
        self.btn_mod_help = ttk.Button(
            det, text="Anleitung zu diesem Modul…", state="disabled",
            command=self._show_module_help)
        self.btn_mod_help.pack(anchor="w", pady=(6, 0))
        _Tooltip(self.btn_mod_help,
                 "Öffnet Beschreibung + Anleitung des gewählten Moduls in "
                 "einem eigenen Fenster.")

        actions = ttk.Frame(t, padding=(8, 0, 8, 8))
        actions.pack(fill="x")
        b1 = ttk.Button(actions, text="Auswahl bauen", command=self._build_selected)
        b1.pack(side="left")
        _Tooltip(b1, "Baut eine SD-Karte mit den gewählten Modulen in den "
                     "Ausgabeordner.")
        b2 = ttk.Button(actions, text="Deinstall-SD bauen",
                        command=self._build_uninstall)
        b2.pack(side="left", padx=6)
        _Tooltip(b2, "Baut eine SD-Karte, die beim Einstecken alle Module vom "
                     "MMI entfernt.")
        b3 = ttk.Button(actions, text="Module neu laden",
                        command=self._reload_modules)
        b3.pack(side="left")
        _Tooltip(b3, "Liest den Ordner modules/ neu ein.")
        self._action_buttons += [b1, b2, b3]

    def _reload_modules(self):
        if self._busy:
            return
        try:
            self.modules = build_sd.find_modules()
        except build_sd.ModuleConfigError as exc:
            messagebox.showerror("Modulfehler", str(exc))
            self.modules = {}
        # Drop selections for modules that no longer exist.
        self.selected &= set(self.modules)
        self._populate_tree()

    def _populate_tree(self):
        self.tree.delete(*self.tree.get_children())
        self.item_name.clear()
        self.name_item.clear()
        if not self.modules:
            self._update_count()
            self._show_detail("Keine Module gefunden. Fehlt der Ordner modules/?")
            return

        platform = self._current_platform()
        by_cat = {}
        for name, meta in self.modules.items():
            if not build_sd.module_is_compatible(meta, platform):
                continue
            by_cat.setdefault(_category_of(name), []).append(name)

        for cat in CATEGORY_ORDER:
            names = by_cat.get(cat)
            if not names:
                continue
            parent = self.tree.insert("", "end", text=f"{cat}  ({len(names)})",
                                      open=True, tags=("category",))
            names.sort(key=lambda nm: (STATUS_ORDER.get(
                self.modules[nm].get("status", ""), 9), nm))
            for name in names:
                meta = self.modules[name]
                item = self.tree.insert(
                    parent, "end",
                    text=self._row_text(name),
                    values=(meta.get("status", "?"),
                            ", ".join(meta.get("compatible", []))))
                self.item_name[item] = name
                self.name_item[name] = item
        self._update_count()

    def _row_text(self, name):
        glyph = "☑" if name in self.selected else "☐"  # ☑ / ☐
        return f"{glyph} {name}"

    def _refresh_row(self, name):
        item = self.name_item.get(name)
        if item:
            self.tree.item(item, text=self._row_text(name))

    def _current_platform(self):
        p = self.platform_var.get()
        return None if p == "(any)" else p

    def _apply_filter(self):
        # Rebuild the tree for the new platform; selection set is preserved,
        # but anything now hidden is dropped so it is never built.
        visible = set(self._visible_modules())
        self.selected &= visible
        self._populate_tree()

    def _visible_modules(self):
        platform = self._current_platform()
        return [n for n, m in self.modules.items()
                if build_sd.module_is_compatible(m, platform)]

    def _update_count(self):
        visible = set(self._visible_modules())
        self.count_label.config(
            text=f"{len(self.selected & visible)} gewählt / {len(visible)} sichtbar")

    def _toggle(self, name):
        if name in self.selected:
            self.selected.discard(name)
        else:
            self.selected.add(name)
        self._refresh_row(name)
        self._update_count()

    def _on_tree_click(self, event):
        # Ignore clicks on the expand/collapse indicator.
        if self.tree.identify_element(event.x, event.y) == "Treeitem.indicator":
            return
        row = self.tree.identify_row(event.y)
        name = self.item_name.get(row)
        if name and self.tree.identify_column(event.x) == "#0":
            self._toggle(name)

    def _on_tree_double(self, event):
        row = self.tree.identify_row(event.y)
        name = self.item_name.get(row)
        if name:
            self._toggle(name)
            return "break"

    def _on_tree_space(self, _event):
        name = self.item_name.get(self.tree.focus())
        if name:
            self._toggle(name)
            return "break"

    def _on_tree_select(self, _event):
        name = self.item_name.get(self.tree.focus())
        self._current_module = name
        self.btn_mod_help.config(state=("normal" if name else "disabled"))
        if not name:
            self._show_detail("")
            return
        meta = self.modules[name]
        parts = [
            f"{name}  -  Status: {meta.get('status', '?')}",
            f"Kompatibel: {', '.join(meta.get('compatible', []))}",
            meta.get("description", ""),
        ]
        prereq = meta.get("prereq")
        if prereq:
            parts.append(f"Benötigt zuerst: {prereq}")
        self._show_detail("\n".join(p for p in parts if p))

    def _show_detail(self, text):
        self.detail.config(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("end", text)
        self.detail.config(state="disabled")

    def _module_help_text(self, name):
        """Build the per-module description + how-to shown in its own window."""
        meta = self.modules.get(name, {})
        lines = []
        desc = meta.get("description", "").strip()
        if desc:
            lines.append("BESCHREIBUNG")
            lines.append(desc)
            lines.append("")
        lines.append("ECKDATEN")
        lines.append(f"  Status:      {meta.get('status', '?')}")
        lines.append(f"  Kompatibel:  {', '.join(meta.get('compatible', [])) or '-'}")
        lines.append(f"  Eigenständig: "
                     f"{'ja' if meta.get('standalone') else 'nein / Teil einer Kette'}")
        prereq = meta.get("prereq")
        if prereq:
            lines.append(f"  Benötigt zuerst: {prereq}")
        if meta.get("run_script"):
            sd = meta.get("script_dir") or ""
            lines.append(f"  Startskript: {sd}/{meta['run_script']}".replace("//", "/"))
        scripts = meta.get("scripts")
        if scripts:
            lines.append("  Skripte:")
            for s in scripts:
                lines.append(f"    - {s}")
        notes = meta.get("notes")
        if notes:
            lines.append("")
            lines.append("HINWEISE")
            lines.append(f"  {notes}")
        extra = MODULE_HELP.get(name)
        if extra:
            lines.append("")
            lines.append("WICHTIG")
            lines.append(extra)
        lines.append("")
        lines.append("ANLEITUNG")
        if prereq:
            lines.append(f"1. Erst das Voraussetzungs-Modul '{prereq}' mit "
                         "wählen (wird beim Bauen automatisch ergänzt).")
        lines.append(f"{2 if prereq else 1}. Modul links anhaken (☑).")
        lines.append(f"{3 if prereq else 2}. Ausgabeordner wählen und "
                     "'Auswahl bauen' klicken.")
        lines.append(f"{4 if prereq else 3}. Inhalt des Ausgabeordners auf eine "
                     "FAT32-SD-Karte kopieren.")
        lines.append(f"{5 if prereq else 4}. SD ins MMI stecken; das Skript "
                     "läuft automatisch. Log/Ausgabe landet auf der Karte.")
        if meta.get("installs_to_flash"):
            lines.append("")
            lines.append("ACHTUNG: Dieses Modul schreibt in den Flash des "
                         "Geräts. Vorher 'Deinstall-SD' und ein Backup "
                         "bereithalten.")
        return "\n".join(lines)

    def _show_module_help(self):
        name = self._current_module
        if not name or name not in self.modules:
            return
        self._help_window(f"Modul: {name}", self._module_help_text(name))

    def _set_all_visible(self, value: bool):
        for name in self._visible_modules():
            if value:
                self.selected.add(name)
            else:
                self.selected.discard(name)
            self._refresh_row(name)
        self._update_count()

    def _select_buildable(self):
        for name in self._visible_modules():
            if self.modules[name].get("status") in BUILDABLE_STATUSES:
                self.selected.add(name)
            else:
                self.selected.discard(name)
            self._refresh_row(name)
        self._update_count()

    def _choose_output(self):
        chosen = filedialog.askdirectory(
            title="Ausgabeordner wählen (SD-Karten-Wurzel)",
            initialdir=self.output_var.get() or ".")
        if chosen:
            self.output_var.set(chosen)

    def _output_dir(self):
        return self.output_var.get().strip() or "./sdcard"

    def _build_selected(self):
        selected = [n for n in self._visible_modules() if n in self.selected]
        if not selected:
            messagebox.showwarning("Nichts gewählt",
                                   "Mindestens ein Modul wählen.")
            return
        platform = self._current_platform()
        try:
            resolved, auto_added = build_sd.resolve_selected_modules(
                selected, self.modules, target_platform=platform)
        except build_sd.ModuleConfigError as exc:
            messagebox.showerror("Auswahlfehler", str(exc))
            return
        if auto_added:
            lines = "\n".join(f"  {p}  (benötigt von {d})" for p, d in auto_added)
            if not messagebox.askokcancel(
                    "Voraussetzungen",
                    "Diese Voraussetzungs-Module werden mitgebaut:\n\n" + lines):
                return
        out = self._ensure_output()
        if out is None:
            return
        self._run_build(lambda: build_sd.build_sd(resolved, self.modules, out))

    def _build_uninstall(self):
        if not messagebox.askokcancel(
                "Deinstall-SD bauen",
                "SD-Karte bauen, die beim Einstecken alle Toolkit-Module vom "
                "MMI entfernt?\n\nSchreibt jetzt nur Dateien in den "
                "Ausgabeordner; am Auto passiert nichts, bis die Karte "
                "eingesteckt wird."):
            return
        out = self._ensure_output()
        if out is None:
            return
        self._run_build(lambda: build_sd.build_uninstall_sd(out))

    def _ensure_output(self):
        out = self._output_dir()
        try:
            os.makedirs(out, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("Ausgabeordner", f"Nicht nutzbar: {out}\n{exc}")
            return None
        return out

    def _run_build(self, fn):
        out = self._output_dir()
        self._log(f"\n=== Build -> {os.path.abspath(out)} ===\n")

        def work():
            redirect = _StreamRedirector(self._log_queue)
            with contextlib.redirect_stdout(redirect), \
                    contextlib.redirect_stderr(redirect):
                fn()
            self._log_queue.put("\n[DONE] Build fertig.\n")

        self._dispatch(work)

    # ---- Firmware-Tools tab ---------------------------------------------

    def _build_firmware_tab(self):
        t = self.tab_fw
        pad = ttk.Frame(t, padding=10)
        pad.pack(fill="both", expand=True)

        ttk.Label(pad, text="Firmware-Werkzeuge - fortgeschritten. Arbeiten auf "
                            "Dateien, die du als Argumente angibst.",
                  foreground="#a00", wraplength=760).pack(anchor="w")

        self.tools = self._discover_tools()
        self._tool_doc_cache = {}
        if not self.tools:
            ttk.Label(pad, text="Keine Tools gefunden.").pack(anchor="w", pady=12)
            return

        # --- Auto-pipeline: point at a firmware folder, run matching tools ---
        auto = ttk.LabelFrame(pad, text="Auto-Analyse (optional)", padding=8)
        auto.pack(fill="x", pady=(10, 4))
        self.fw_dir_var = tk.StringVar(value="")
        self.fw_out_var = tk.StringVar(value="")

        r1 = ttk.Frame(auto)
        r1.pack(fill="x")
        ttk.Label(r1, text="Firmware-Ordner:", width=16).pack(side="left")
        ttk.Entry(r1, textvariable=self.fw_dir_var).pack(
            side="left", fill="x", expand=True, padx=6)
        ttk.Button(r1, text="...", width=3, command=self._pick_fw_dir).pack(
            side="left")

        r2 = ttk.Frame(auto)
        r2.pack(fill="x", pady=(4, 0))
        ttk.Label(r2, text="Ausgabeordner:", width=16).pack(side="left")
        ttk.Entry(r2, textvariable=self.fw_out_var).pack(
            side="left", fill="x", expand=True, padx=6)
        ttk.Button(r2, text="...", width=3, command=self._pick_fw_out).pack(
            side="left")

        r3 = ttk.Frame(auto)
        r3.pack(fill="x", pady=(6, 0))
        ba = ttk.Button(r3, text="Erkennen & alle passenden Tools anwenden",
                        command=self._run_auto)
        ba.pack(side="left")
        _Tooltip(ba, "Durchsucht den Ordner nach .ifs / .efs / lsd.jxe / "
                     "dsi.jar / metainfo2.txt und ordnet jedem die passenden "
                     "Analyse-/Extraktions-Tools zu. Patcher (FSC-Bypass, "
                     "patch_ifs, mu_repack) bleiben manuell.")
        self._action_buttons.append(ba)
        ttk.Label(auto, text="Leer lassen = Einzel-Werkzeug unten nutzen.",
                  foreground="#555").pack(anchor="w", pady=(4, 0))

        ttk.Separator(pad, orient="horizontal").pack(fill="x", pady=8)
        ttk.Label(pad, text="Einzelnes Werkzeug:", font=("", 10, "bold")).pack(
            anchor="w")

        row = ttk.Frame(pad)
        row.pack(fill="x", pady=(10, 4))
        ttk.Label(row, text="Werkzeug:").pack(side="left")
        self.tool_var = tk.StringVar(value=self.tools[0][0])
        combo = ttk.Combobox(row, textvariable=self.tool_var,
                             values=[label for label, _ in self.tools],
                             state="readonly", width=40)
        combo.pack(side="left", padx=6)
        combo.bind("<<ComboboxSelected>>", lambda _e: self._show_tool_doc())
        bdoc = ttk.Button(row, text="Anleitung öffnen…",
                          command=self._show_tool_help)
        bdoc.pack(side="left")
        _Tooltip(bdoc, "Öffnet Beschreibung + Schritt-für-Schritt-Anleitung "
                       "des gewählten Werkzeugs in einem eigenen Fenster.")

        # Description + instructions panel.
        docframe = ttk.LabelFrame(pad, text="Beschreibung & Anleitung", padding=6)
        docframe.pack(fill="both", expand=True, pady=6)
        self.tool_doc = tk.Text(docframe, height=10, wrap="word", state="disabled",
                                background="#f6f6f6")
        dscroll = ttk.Scrollbar(docframe, command=self.tool_doc.yview)
        self.tool_doc.configure(yscrollcommand=dscroll.set)
        self.tool_doc.pack(side="left", fill="both", expand=True)
        dscroll.pack(side="right", fill="y")

        argrow = ttk.Frame(pad)
        argrow.pack(fill="x", pady=4)
        ttk.Label(argrow, text="Argumente:").pack(side="left")
        self.tool_args = tk.StringVar(value="")
        ttk.Entry(argrow, textvariable=self.tool_args).pack(
            side="left", fill="x", expand=True, padx=6)

        btns = ttk.Frame(pad)
        btns.pack(fill="x", pady=8)
        bh = ttk.Button(btns, text="--help (volle Optionen)",
                        command=lambda: self._run_tool(True))
        bh.pack(side="left")
        br = ttk.Button(btns, text="Ausführen", command=lambda: self._run_tool(False))
        br.pack(side="left", padx=6)
        self._action_buttons += [bh, br]

        ttk.Label(pad, text="Tipp: --help zeigt die vollständige Optionsliste im "
                            "Log. Pfade mit Leerzeichen in \"...\" setzen.",
                  foreground="#555").pack(anchor="w", pady=(6, 0))
        self._show_tool_doc()

    def _discover_tools(self):
        items = []
        for p in sorted(glob.glob(os.path.join(DATA_BASE, "tools", "*.py"))):
            items.append((f"tools/{os.path.basename(p)}", p))
        gm = os.path.join(DATA_BASE, "builder", "generate_manifest.py")
        if os.path.isfile(gm):
            items.append(("builder/generate_manifest.py", gm))
        return items

    def _tool_docstring(self, path):
        """Read a tool's module docstring (cached), or '' if none."""
        if path in self._tool_doc_cache:
            return self._tool_doc_cache[path]
        import ast
        doc = ""
        try:
            with open(path, "r", encoding="utf-8") as f:
                doc = ast.get_docstring(ast.parse(f.read())) or ""
        except (OSError, SyntaxError):
            doc = ""
        self._tool_doc_cache[path] = doc.strip()
        return self._tool_doc_cache[path]

    def _show_tool_doc(self):
        label = self.tool_var.get()
        path = dict(self.tools).get(label, "")
        blurb = TOOL_BLURBS.get(label, "")
        doc = self._tool_docstring(path)
        parts = []
        if blurb:
            parts.append(blurb)
        if doc:
            parts.append("--- Original-Hinweise ---\n" + doc)
        parts.append('Für die vollständige Optionsliste "--help (volle '
                     'Optionen)" klicken.')
        self.tool_doc.config(state="normal")
        self.tool_doc.delete("1.0", "end")
        self.tool_doc.insert("end", "\n\n".join(parts))
        self.tool_doc.config(state="disabled")

    def _tool_help_text(self, label, path):
        """Build description + how-to + original notes for a firmware tool."""
        parts = []
        blurb = TOOL_BLURBS.get(label, "")
        if blurb:
            parts.append("BESCHREIBUNG")
            parts.append(blurb)
            parts.append("")
        howto = TOOL_HELP.get(label)
        if howto:
            parts.append("ANLEITUNG")
            parts.append(howto)
            parts.append("")
        doc = self._tool_docstring(path)
        if doc:
            parts.append("ORIGINAL-HINWEISE (Tool-Docstring)")
            parts.append(doc)
            parts.append("")
        parts.append("Argumente trägst du im Feld 'Argumente:' ein. Pfade mit "
                     "Leerzeichen in \"...\" setzen. '--help (volle Optionen)' "
                     "zeigt die komplette Optionsliste im Log.")
        return "\n".join(parts)

    def _show_tool_help(self):
        label = self.tool_var.get()
        path = dict(self.tools).get(label, "")
        self._help_window(f"Werkzeug: {label}",
                          self._tool_help_text(label, path))

    def _run_tool(self, help_only: bool):
        label = self.tool_var.get()
        path = dict(self.tools).get(label)
        if not path:
            return
        import shlex
        if help_only:
            args = ["--help"]
        else:
            args = shlex.split(self.tool_args.get(), posix=False)
        self._exec_tool_inprocess(label, path, args)

    def _exec_once(self, label, path, args):
        """Run one tool script in-process via runpy (synchronous).

        A subprocess is unavailable in the frozen .exe (sys.executable is the
        GUI exe, not a Python interpreter), so tools run inside this process.
        stdout/stderr are redirected to the log; SystemExit (argparse, --help,
        fatal errors) and any exception are caught so a batch run continues and
        the GUI survives. Call only from a worker thread.
        """
        import runpy
        tools_dir = os.path.dirname(path)
        self._log_queue.put(f"\n=== {label} {' '.join(args)} ===\n")
        redirect = _StreamRedirector(self._log_queue)
        old_argv = sys.argv
        added_path = tools_dir not in sys.path
        if added_path:
            sys.path.insert(0, tools_dir)  # let cross-tool imports resolve
        sys.argv = [path] + list(args)
        try:
            with contextlib.redirect_stdout(redirect), \
                    contextlib.redirect_stderr(redirect):
                try:
                    runpy.run_path(path, run_name="__main__")
                    self._log_queue.put("\n[DONE]\n")
                except SystemExit as exc:
                    code = exc.code if exc.code is not None else 0
                    self._log_queue.put(f"\n[exit {code}]\n")
                except Exception:  # noqa: BLE001 - keep batch going
                    self._log_queue.put("\n[ERROR]\n" + traceback.format_exc())
        finally:
            sys.argv = old_argv
            if added_path and tools_dir in sys.path:
                sys.path.remove(tools_dir)

    def _exec_tool_inprocess(self, label, path, args):
        self._dispatch(lambda: self._exec_once(label, path, args))

    def _tool_path(self, basename):
        for _label, p in self.tools:
            if os.path.basename(p) == basename:
                return p
        return None

    # ---- auto firmware pipeline -----------------------------------------

    def _pick_fw_dir(self):
        chosen = filedialog.askdirectory(
            title="Firmware-Ordner wählen",
            initialdir=self.fw_dir_var.get() or ".")
        if chosen:
            self.fw_dir_var.set(chosen)
            if not self.fw_out_var.get().strip():
                self.fw_out_var.set(os.path.join(chosen, "_toolkit_out"))

    def _pick_fw_out(self):
        chosen = filedialog.askdirectory(
            title="Ausgabeordner für Extraktion wählen",
            initialdir=self.fw_out_var.get() or ".")
        if chosen:
            self.fw_out_var.set(chosen)

    def _build_auto_plan(self, fw_dir, out_dir):
        """Scan fw_dir, map known files to analysis/extraction tool calls.

        Returns (plan, noted). plan is a list of (label, path, args) run in
        order. noted is a list of (reason, path) for files that were found but
        need a manual tool (patchers that require targets/flags).
        """
        plan = []
        noted = []

        def add(basename, args):
            p = self._tool_path(basename)
            if p:
                plan.append((basename, p, args))

        for root, _dirs, files in os.walk(fw_dir):
            for fn in sorted(files):
                full = os.path.join(root, fn)
                low = fn.lower()
                stem = os.path.splitext(fn)[0]
                if low.endswith(".ifs"):
                    add("inflate_ifs.py",
                        [full, "--extract", os.path.join(out_dir, "ifs-" + stem),
                         "--no-container-fallback"])
                elif low.endswith(".efs"):
                    add("walk_f3s_efs.py", [full, "--format", "detailed"])
                    add("extract_f3s_efs.py",
                        [full, os.path.join(out_dir, "efs-" + stem)])
                    add("extract_jars_from_efs.py",
                        [full, os.path.join(out_dir, "efs-jars-" + stem)])
                elif low == "lsd.jxe":
                    add("eol_modifier.py", [full, "--list"])
                    add("eol_modifier.py", [full, "--show-variant"])
                elif low == "dsi.jar":
                    add("verify_stubs_vs_dsi.py", [full])
                elif low == "metainfo2.txt":
                    noted.append(("metainfo2.txt (CRC/Repack manuell: mu_repack / "
                                  "mu_crc_patcher)", full))
        return plan, noted

    def _run_auto(self):
        fw = self.fw_dir_var.get().strip()
        if not fw or not os.path.isdir(fw):
            messagebox.showwarning("Firmware-Ordner",
                                   "Bitte einen gültigen Firmware-Ordner wählen.")
            return
        out = self.fw_out_var.get().strip() or os.path.join(fw, "_toolkit_out")
        plan, noted = self._build_auto_plan(fw, out)
        if not plan and not noted:
            messagebox.showinfo(
                "Auto-Analyse",
                "Keine bekannten Firmware-Dateien gefunden (.ifs, .efs, "
                "lsd.jxe, dsi.jar, metainfo2.txt).")
            return
        try:
            os.makedirs(out, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("Ausgabeordner", f"Nicht nutzbar: {out}\n{exc}")
            return

        def work():
            self._log_queue.put(
                f"\n##### Auto-Analyse: {fw}\n##### Ausgabe: {out}\n"
                f"##### {len(plan)} Schritt(e)\n")
            for i, (label, path, args) in enumerate(plan, 1):
                self._log_queue.put(f"\n----- Schritt {i}/{len(plan)} -----\n")
                self._exec_once(label, path, args)
            if noted:
                self._log_queue.put("\n##### Erkannt, aber manuell "
                                    "(Patcher brauchen Ziele/Flags):\n")
                for reason, p in noted:
                    self._log_queue.put(f"  - {p}\n    -> {reason}\n")
            self._log_queue.put("\n##### Auto-Analyse fertig.\n")

        self._dispatch(work)

    # ---- Splash-Screen tab ----------------------------------------------

    def _build_splash_tab(self):
        t = self.tab_splash
        pad = ttk.Frame(t, padding=10)
        pad.pack(fill="both", expand=True)

        if not _HAVE_PIL:
            ttk.Label(pad, text="Splash-Konverter braucht Pillow.\n"
                               "Installieren:  python -m pip install pillow",
                      foreground="#a00").pack(anchor="w", pady=12)
            return

        self.splash_src = tk.StringVar(value="")
        self.splash_zoom = tk.DoubleVar(value=1.0)

        row = ttk.Frame(pad)
        row.pack(fill="x")
        ttk.Button(row, text="Bild wählen...", command=self._pick_splash).pack(
            side="left")
        ttk.Label(row, textvariable=self.splash_src, foreground="#555").pack(
            side="left", padx=8)

        zrow = ttk.Frame(pad)
        zrow.pack(fill="x", pady=8)
        ttk.Label(zrow, text="Zoom:").pack(side="left")
        ttk.Scale(zrow, from_=0.5, to=3.0, variable=self.splash_zoom,
                  orient="horizontal", length=240,
                  command=lambda _v: self._render_splash_preview()).pack(
            side="left", padx=8)

        ttk.Label(pad, text=f"Ausgabe: {SPLASH_W}x{SPLASH_H} PNG "
                            "(startup_generic.png), schwarzer Rand, zentriert.",
                  foreground="#555").pack(anchor="w")

        self.splash_canvas = tk.Label(pad, background="#000", width=SPLASH_W // 2,
                                      height=SPLASH_H // 2)
        self.splash_canvas.pack(pady=10)

        bexp = ttk.Button(pad, text="startup_generic.png exportieren...",
                          command=self._export_splash)
        bexp.pack(anchor="w")
        self._action_buttons.append(bexp)

    def _pick_splash(self):
        path = filedialog.askopenfilename(
            title="Bild wählen",
            filetypes=[("Bilder", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"),
                       ("Alle Dateien", "*.*")])
        if path:
            self.splash_src.set(path)
            self._render_splash_preview()

    def _compose_splash(self):
        """Return an 800x480 RGB PIL image (cover-fit, centered, zoomed)."""
        path = self.splash_src.get()
        if not path or not os.path.isfile(path):
            return None
        img = Image.open(path).convert("RGB")
        zoom = max(0.1, float(self.splash_zoom.get()))
        iw, ih = img.size
        ia = iw / ih
        ma = SPLASH_W / SPLASH_H
        if ia > ma:
            dh = int(SPLASH_H * zoom)
            dw = int(dh * ia)
        else:
            dw = int(SPLASH_W * zoom)
            dh = int(dw / ia)
        resized = img.resize((max(1, dw), max(1, dh)), Image.LANCZOS)
        canvas = Image.new("RGB", (SPLASH_W, SPLASH_H), (0, 0, 0))
        canvas.paste(resized, ((SPLASH_W - dw) // 2, (SPLASH_H - dh) // 2))
        return canvas

    def _render_splash_preview(self):
        try:
            composed = self._compose_splash()
        except Exception as exc:  # noqa: BLE001
            self._log(f"[Splash] Fehler: {exc}\n")
            return
        if composed is None:
            return
        preview = composed.resize((SPLASH_W // 2, SPLASH_H // 2), Image.LANCZOS)
        self._preview_img = ImageTk.PhotoImage(preview)
        self.splash_canvas.config(image=self._preview_img, width=0, height=0)

    def _export_splash(self):
        try:
            composed = self._compose_splash()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Splash", f"Bild-Fehler: {exc}")
            return
        if composed is None:
            messagebox.showwarning("Splash", "Zuerst ein Bild wählen.")
            return
        path = filedialog.asksaveasfilename(
            title="Splash speichern", defaultextension=".png",
            initialfile="startup_generic.png",
            filetypes=[("PNG", "*.png")])
        if not path:
            return
        composed.save(path, "PNG")
        self._log(f"[Splash] gespeichert: {path}\n")
        messagebox.showinfo(
            "Splash",
            "startup_generic.png gespeichert.\n\nIn splashscreens/ auf die SD "
            "legen und das Modul splash-screen bauen.")

    # ---- Release / Git tab ----------------------------------------------

    def _build_release_tab(self):
        t = self.tab_rel
        pad = ttk.Frame(t, padding=10)
        pad.pack(fill="both", expand=True)

        ttk.Label(pad, text=f"Version (builder/version.py): {__version__}",
                  font=("", 11, "bold")).pack(anchor="w")
        ttk.Button(pad, text="CHANGELOG.md öffnen",
                   command=self._open_changelog).pack(anchor="w", pady=(6, 10))

        self._git_ok = (not FROZEN) and os.path.isdir(os.path.join(REPO_ROOT, ".git"))
        if not self._git_ok:
            ttk.Label(pad, text="Kein git-Repo im Checkout - Git-Aktionen "
                               "deaktiviert.", foreground="#555").pack(anchor="w")
            return

        ttk.Separator(pad, orient="horizontal").pack(fill="x", pady=8)
        ttk.Label(pad, text="Release-Ablauf (siehe docs/RELEASING.md): version.py "
                            "+ CHANGELOG committen, dann Tag v" + __version__ +
                            " pushen.", foreground="#555", wraplength=760).pack(
            anchor="w")

        crow = ttk.Frame(pad)
        crow.pack(fill="x", pady=8)
        ttk.Label(crow, text="Commit-Nachricht:").pack(side="left")
        self.commit_msg = tk.StringVar(value=f"release: v{__version__}")
        ttk.Entry(crow, textvariable=self.commit_msg).pack(
            side="left", fill="x", expand=True, padx=6)

        btns = ttk.Frame(pad)
        btns.pack(fill="x", pady=4)
        defs = [
            ("git status", self._git_status),
            ("version.py + CHANGELOG committen", self._git_commit),
            (f"Tag v{__version__} erzeugen", self._git_tag),
            ("Push (main)", self._git_push),
            (f"Push Tag v{__version__}", self._git_push_tag),
        ]
        for text, cmd in defs:
            b = ttk.Button(btns, text=text, command=cmd)
            b.pack(side="left", padx=(0, 6))
            self._action_buttons.append(b)

        ttk.Label(pad, text="Push ist unwiderruflich (verändert das Remote) und "
                            "fragt vorher nach.", foreground="#a00",
                  wraplength=760).pack(anchor="w", pady=(8, 0))

    def _open_changelog(self):
        path = os.path.join(REPO_ROOT, "CHANGELOG.md")
        if not os.path.isfile(path):
            messagebox.showwarning("Changelog", "CHANGELOG.md nicht gefunden.")
            return
        try:
            os.startfile(path)  # type: ignore[attr-defined]  (Windows)
        except AttributeError:
            self._run_subprocess(["git", "--no-pager", "show", "HEAD:CHANGELOG.md"],
                                 cwd=REPO_ROOT)

    def _git(self, *args, confirm=None):
        if confirm and not messagebox.askokcancel("Bestätigen", confirm):
            return
        self._run_subprocess(["git"] + list(args), cwd=REPO_ROOT)

    def _git_status(self):
        self._git("status", "--short", "--branch")

    def _git_commit(self):
        msg = self.commit_msg.get().strip() or f"release: v{__version__}"
        # Stage the two release files, then commit.
        def work():
            for argv in (["git", "add", "builder/version.py", "CHANGELOG.md"],
                         ["git", "commit", "-m", msg]):
                self._log_queue.put("$ " + " ".join(argv) + "\n")
                p = subprocess.run(argv, cwd=REPO_ROOT, capture_output=True,
                                   text=True)
                self._log_queue.put(p.stdout + p.stderr)
                if p.returncode != 0:
                    self._log_queue.put(f"[exit {p.returncode}]\n")
                    break
        self._dispatch(work)

    def _git_tag(self):
        self._git("tag", f"v{__version__}")

    def _git_push(self):
        self._git("push", "origin", "HEAD",
                  confirm="Commit nach origin pushen (verändert Remote)?")

    def _git_push_tag(self):
        self._git("push", "origin", f"v{__version__}",
                  confirm=f"Tag v{__version__} nach origin pushen? Löst den "
                          "EXE-Release-Workflow aus.")

    # ---- shared job dispatch + log --------------------------------------

    def _run_subprocess(self, argv, cwd=None):
        def work():
            self._log_queue.put("$ " + " ".join(str(a) for a in argv) + "\n")
            try:
                p = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True,
                                     bufsize=1)
            except FileNotFoundError as exc:
                self._log_queue.put(f"[ERROR] {exc}\n")
                return
            for line in p.stdout:
                self._log_queue.put(line)
            p.wait()
            self._log_queue.put(f"[exit {p.returncode}]\n")
        self._dispatch(work)

    def _dispatch(self, work):
        if self._busy:
            self._log("[busy] Vorheriger Job läuft noch.\n")
            return
        self._busy = True
        self._set_actions_enabled(False)

        def runner():
            try:
                work()
            except SystemExit as exc:  # build_sd calls sys.exit on fatal error
                self._log_queue.put(f"\n[FAILED] exit code {exc.code}\n")
            except Exception:  # noqa: BLE001 - surface any error in the log
                self._log_queue.put("\n[ERROR]\n" + traceback.format_exc())
            finally:
                self._log_queue.put(_BUILD_DONE)

        threading.Thread(target=runner, daemon=True).start()

    def _set_actions_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        for b in self._action_buttons:
            try:
                b.config(state=state)
            except tk.TclError:
                pass

    def _log(self, text: str):
        self.log.config(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.config(state="disabled")

    def _pump_log(self):
        try:
            while True:
                item = self._log_queue.get_nowait()
                if item is _BUILD_DONE:
                    self._busy = False
                    self._set_actions_enabled(True)
                else:
                    self._log(item)
        except queue.Empty:
            pass
        self.root.after(80, self._pump_log)


def _apply_window_icon(win):
    """Set the dino window/taskbar icon on a Tk root or Toplevel.

    Tries the .ico (best on Windows for the title bar + taskbar), then falls
    back to the .png via Pillow. Silently ignores any failure so a missing
    asset never breaks the GUI.
    """
    try:
        if os.path.isfile(ICON_ICO):
            win.iconbitmap(ICON_ICO)
            return
    except tk.TclError:
        pass
    img = _load_icon_image()
    if img is not None:
        try:
            win.iconphoto(True, img)
        except tk.TclError:
            pass


_ICON_CACHE = {}


def _load_icon_image():
    """Return a cached Tk PhotoImage of the dino icon, or None."""
    if "img" in _ICON_CACHE:
        return _ICON_CACHE["img"]
    img = None
    try:
        if _HAVE_PIL and os.path.isfile(ICON_PNG):
            img = ImageTk.PhotoImage(Image.open(ICON_PNG))
        elif os.path.isfile(ICON_PNG):
            img = tk.PhotoImage(file=ICON_PNG)
    except Exception:  # noqa: BLE001 - icon is optional
        img = None
    _ICON_CACHE["img"] = img
    return img


def _draw_dino(c):
    """Draw a friendly cartoon brontosaurus on a Tk canvas (no image asset)."""
    body = "#4caf50"
    dark = "#2e7d32"
    # tail
    c.create_polygon(60, 150, 150, 120, 150, 160, fill=body, outline=dark)
    # body
    c.create_oval(120, 100, 260, 185, fill=body, outline=dark, width=2)
    # neck
    c.create_polygon(230, 120, 300, 55, 318, 70, 255, 150,
                     fill=body, outline=dark, width=2, smooth=True)
    # head
    c.create_oval(292, 40, 345, 82, fill=body, outline=dark, width=2)
    # eye
    c.create_oval(322, 52, 332, 62, fill="#fff", outline=dark)
    c.create_oval(326, 55, 331, 60, fill="#000")
    # smile
    c.create_arc(300, 58, 330, 80, start=200, extent=120, style="arc",
                 outline=dark, width=2)
    # back spikes
    for sx in range(140, 250, 22):
        c.create_polygon(sx, 103, sx + 12, 103, sx + 6, 88,
                         fill=dark, outline=dark)
    # legs
    for lx in (140, 185, 215, 245):
        c.create_rectangle(lx, 175, lx + 16, 205, fill=body, outline=dark)
    # ground
    c.create_line(40, 206, 350, 206, fill="#9ccc9c", width=3)


# Minimum time the startup splash stays visible, in seconds.
SPLASH_MIN_S = 2.5


def _show_splash(root):
    """Startup splash: dinosaur + heading, auto-closes; click to skip."""
    sp = tk.Toplevel(root)
    sp.overrideredirect(True)
    try:
        sp.attributes("-topmost", True)
    except tk.TclError:
        pass
    W, H = 440, 360
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    sp.geometry(f"{W}x{H}+{(sw - W) // 2}+{(sh - H) // 2}")
    bg = "#eaf7ea"
    frm = tk.Frame(sp, bg=bg, bd=2, relief="raised")
    frm.pack(fill="both", expand=True)
    tk.Label(frm, text="Viel Spaß mit den Dinosauriern", bg=bg, fg="#1b5e20",
             font=("", 15, "bold")).pack(pady=(16, 8))
    canvas = tk.Canvas(frm, width=380, height=220, bg=bg, highlightthickness=0)
    canvas.pack()
    _draw_dino(canvas)
    sub = f"v{__version__}"
    if __codename__:
        sub += f" – {__codename__}"
    tk.Label(frm, text=sub, bg=bg, fg="#555").pack(pady=(6, 4))
    tk.Label(frm, text="(klicken zum Überspringen)", bg=bg, fg="#999",
             font=("", 8)).pack()
    sp.bind("<Button-1>", lambda _e: sp.destroy())
    # Force the splash to the front: a freshly started process does not
    # always get the foreground on Windows, and the borderless window has no
    # taskbar entry to recover it from.
    sp.deiconify()
    sp.lift()
    try:
        sp.focus_force()
    except tk.TclError:
        pass
    sp.update()
    if not sp.winfo_ismapped():
        # Some window managers refuse to map a borderless window; fall back
        # to a normal decorated one so the dino is still shown.
        sp.overrideredirect(False)
        sp.title("MMI3G-Toolkit")
        _apply_window_icon(sp)
        sp.deiconify()
        sp.lift()
        sp.update()
    return sp


def main():
    root = tk.Tk()
    try:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except tk.TclError:
        pass
    root.withdraw()
    splash = _show_splash(root)
    shown_at = time.monotonic()

    def _build():
        BuilderGUI(root)
        # Building the GUI must not reveal the main window early.
        root.withdraw()
        # Keep the splash up for SPLASH_MIN_S after it appeared, however long
        # the GUI took to build.
        remaining = SPLASH_MIN_S - (time.monotonic() - shown_at)
        root.after(max(0, int(remaining * 1000)), _finish)

    def _finish():
        if splash.winfo_exists():
            splash.destroy()
        root.deiconify()
        root.lift()

    # Let the event loop paint the splash before the (slower) GUI build.
    root.after(50, _build)
    root.mainloop()


if __name__ == "__main__":
    main()
