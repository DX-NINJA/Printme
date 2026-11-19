"""Print Me - images aur PDF ko thumbnails, preview, layout ke saath print karo. By DM."""
import datetime
import io
import json
import math
import os
import queue
import re
import threading
import urllib.error
import urllib.request
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import pymupdf as fitz  # PyMuPDF (naya naam)
except ImportError:
    import fitz  # PyMuPDF (purana naam)
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageTk

try:
    import win32gui
    import win32print
    import win32ui
    from PIL import ImageWin
except ImportError:  # sirf Windows par available
    win32gui = win32print = win32ui = ImageWin = None

try:
    import winsound
except ImportError:
    winsound = None

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    DND_FILES = TkinterDnD = None

IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff", ".webp")
SUPPORTED = IMG_EXTS + (".pdf",)
RESAMPLE = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS

# name: (width_mm, height_mm, DMPAPER code; 0 = printer default)
PAPERS = {
    "Printer default": (210, 297, 0),
    "A4": (210, 297, 9),
    "A3": (297, 420, 8),
    "A5": (148, 210, 11),
    "Letter": (216, 279, 1),
    "Legal": (216, 356, 5),
}
# name: (columns, rows) portrait page ke liye
LAYOUTS = {
    "1 per page": (1, 1),
    "2 per page": (1, 2),
    "4 per page (2x2)": (2, 2),
    "6 per page (2x3)": (2, 3),
    "8 per page (2x4)": (2, 4),
    "9 per page (3x3)": (3, 3),
}
ORIENTATIONS = ["Auto", "Portrait", "Landscape"]
FIT_MODES = ["Fit to page", "Fill page (crop)", "Original size"]
CAPTIONS = ["None", "File name", "Date"]
SORTS = ["Name", "Date", "Size"]

DEFAULTS = {
    "printer": "", "paper": "Printer default", "orientation": "Auto",
    "layout": "1 per page", "fit": "Fit to page", "copies": 1, "margin": 5,
    "bw": False, "border": False, "cutlines": False, "caption": "None",
    "recursive": False, "sort": "Name", "sort_desc": False,
    "theme": "Light", "after_print": "Ask me", "confirm": True, "beep": True,
    "remember": True, "quality": "Normal", "auto_update": True, "last_dir": "",
}


APP_NAME = "Print Me"
TAGLINE = "Images & PDF printing, made easy"
CREDIT = "Made by DM"
APP_VERSION = "1.0.0"
# Website ki REPO line jaisi hi: "github-username/repository-naam". Update check aur About ke links iske liye.
GITHUB_REPO = "YOUR-USERNAME/printme"
QUALITY = {"Draft": (2000, 150), "Normal": (3000, 300), "High": (4500, 450)}  # (print pixel limit, PDF dpi)
AFTER_PRINT = ["Ask me", "Always clear", "Never clear"]
LIGHT = {"fg": "#000000", "muted": "#666666", "field": "#ffffff", "sel": "#0078d7"}
DARK = {"bg": "#1b1a33", "panel": "#25243f", "field": "#2c2b4a", "btn": "#35346a", "btn_hi": "#4743a8",
        "fg": "#e9e9ff", "muted": "#9a9cc4", "line": "#3d3c66", "sel": "#4b3fb0", "accent": "#6c5ce7",
        "cy": "#22d3ee"}


def repo_ready():
    return "/" in GITHUB_REPO and not GITHUB_REPO.startswith("YOUR-USERNAME")


def releases_url():
    return f"https://github.com/{GITHUB_REPO}/releases/latest" if repo_ready() else ""


def website_url():
    if not repo_ready():
        return ""
    user, name = GITHUB_REPO.split("/", 1)
    return f"https://{user}.github.io/{name}/"


def parse_ver(v):
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums[:4]) or (0,)


def fetch_latest():
    """GitHub se latest release ka version number laao (koi file upload nahi hoti)."""
    req = urllib.request.Request(
        f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
        headers={"User-Agent": "PrintMe-UpdateCheck", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.load(r)
    return {"tag": data.get("tag_name", ""), "url": data.get("html_url") or releases_url(),
            "notes": (data.get("body") or "").strip()}


def make_logo(size=256):
    """Print Me ka logo (printer icon, gradient rounded square). Code se banta hai."""
    S = 512
    c1, c2 = (108, 92, 231), (0, 180, 219)          # purple -> cyan
    grad = Image.linear_gradient("L").resize((S, S))
    bg = Image.composite(Image.new("RGB", (S, S), c2), Image.new("RGB", (S, S), c1), grad)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.22), fill=255)
    img = bg.convert("RGBA")
    img.putalpha(mask)
    d = ImageDraw.Draw(img)
    ink, line, lw = (52, 48, 160), (150, 158, 214), int(S * 0.014)

    def box(x0, y0, x1, y1):
        return [int(S * x0), int(S * y0), int(S * x1), int(S * y1)]

    d.rounded_rectangle(box(0.30, 0.14, 0.70, 0.42), radius=int(S * 0.025),
                        fill="white", outline=ink, width=lw)                     # upar ka paper
    d.rounded_rectangle(box(0.14, 0.36, 0.86, 0.70), radius=int(S * 0.07),
                        fill="white", outline=ink, width=lw)                     # printer body
    d.ellipse(box(0.72, 0.45, 0.78, 0.51), fill=(0, 190, 140))                  # green light
    d.rounded_rectangle(box(0.22, 0.46, 0.50, 0.50), radius=int(S * 0.02), fill=line)
    d.rectangle(box(0.28, 0.58, 0.72, 0.88), fill="white", outline=ink, width=lw)  # nikla hua paper
    for y in (0.65, 0.72, 0.79):
        d.line(box(0.34, y, 0.66, y), fill=line, width=int(S * 0.016))
    return img.resize((size, size), Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS)


# ----------------------------------------------------------------- settings
def settings_file():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, "PrintMe")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "settings.json")


def load_settings():
    cfg = dict(DEFAULTS)
    try:
        with open(settings_file(), encoding="utf-8") as f:
            saved = json.load(f)
        for k, v in saved.items():
            if k in DEFAULTS and type(v) is type(DEFAULTS[k]):
                cfg[k] = v
    except Exception:
        pass
    if cfg["paper"] not in PAPERS: cfg["paper"] = DEFAULTS["paper"]
    if cfg["layout"] not in LAYOUTS: cfg["layout"] = DEFAULTS["layout"]
    if cfg["orientation"] not in ORIENTATIONS: cfg["orientation"] = DEFAULTS["orientation"]
    if cfg["fit"] not in FIT_MODES: cfg["fit"] = DEFAULTS["fit"]
    if cfg["caption"] not in CAPTIONS: cfg["caption"] = DEFAULTS["caption"]
    if cfg["sort"] not in SORTS: cfg["sort"] = DEFAULTS["sort"]
    if cfg["theme"] not in ("Light", "Dark"): cfg["theme"] = DEFAULTS["theme"]
    if cfg["after_print"] not in AFTER_PRINT: cfg["after_print"] = DEFAULTS["after_print"]
    if cfg["quality"] not in QUALITY: cfg["quality"] = DEFAULTS["quality"]
    return cfg


def save_settings(cfg):
    try:
        with open(settings_file(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


# ------------------------------------------------------------ file handling
def collect_files(paths, recursive):
    out = []
    for p in paths:
        if os.path.isdir(p):
            if recursive:
                for root, _, files in os.walk(p):
                    out.extend(os.path.join(root, f) for f in files)
            else:
                out.extend(os.path.join(p, f) for f in os.listdir(p))
        else:
            out.append(p)
    return [os.path.normpath(f) for f in out
            if os.path.isfile(f) and f.lower().endswith(SUPPORTED)]


def make_item(path):
    st = os.stat(path)
    item = {"path": path, "checked": True, "mtime": st.st_mtime, "size": st.st_size}
    if path.lower().endswith(".pdf"):
        with fitz.open(path) as d:
            n = d.page_count
        if n < 1:
            raise ValueError("PDF me page nahi hain")
        item.update(kind="pdf", pages=n, info=f"PDF, {n} page" + ("s" if n > 1 else ""))
    else:
        with Image.open(path) as im:
            w, h = im.size
        item.update(kind="img", pages=1, info=f"{w} x {h}")
    return item


def to_rgb(im):
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, "white")
        bg.paste(im, mask=im.split()[3])
        return bg
    return im.convert("RGB")


def load_unit(unit, long_px):
    """unit = (path, page or None). Return (RGB image, physical width mm, height mm)."""
    path, page = unit
    if page is None:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            dpi = 96.0
            try:
                v = im.info.get("dpi")
                if v and float(v[0]) > 1:
                    dpi = float(v[0])
            except Exception:
                pass
            pw, ph = im.width / dpi * 25.4, im.height / dpi * 25.4
            im.thumbnail((long_px, long_px))
            return to_rgb(im), pw, ph
    with fitz.open(path) as d:
        p = d[page]
        r = p.rect
        z = long_px / max(r.width, r.height)
        pix = p.get_pixmap(matrix=fitz.Matrix(z, z), alpha=False)
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        return im, r.width / 72 * 25.4, r.height / 72 * 25.4


# ----------------------------------------------------------------- layout
_fonts = {}


def get_font(size):
    if size not in _fonts:
        for name in ("arial.ttf", "DejaVuSans.ttf"):
            try:
                _fonts[size] = ImageFont.truetype(name, size)
                break
            except Exception:
                pass
        else:
            try:
                _fonts[size] = ImageFont.load_default(size)
            except TypeError:
                _fonts[size] = ImageFont.load_default()
    return _fonts[size]


def grid_for(s):
    cols, rows = LAYOUTS[s["layout"]]
    if s["orientation"] == "Landscape":
        cols, rows = rows, cols
    return cols, rows


def paper_mm(s):
    w, h = PAPERS[s["paper"]][:2]
    if s["orientation"] == "Landscape":
        w, h = h, w
    return w, h


def caption_text(unit, mode):
    path, page = unit
    if mode == "File name":
        t = os.path.basename(path)
        return t + (f" (p{page + 1})" if page is not None else "")
    if mode == "Date":
        return datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%d-%m-%Y")
    return ""


def compose_sheet(units, loader, W, H, mm_w, mm_h, s, errors=None):
    sheet = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(sheet)
    ppm = W / mm_w  # pixels per mm
    cols, rows = grid_for(s)
    margin = s["margin"] * ppm
    gap = 2 * ppm if cols * rows > 1 else 0
    cell_w = (W - 2 * margin - (cols - 1) * gap) / cols
    cell_h = (H - 2 * margin - (rows - 1) * gap) / rows
    cap_h = 5 * ppm if s["caption"] != "None" else 0
    font = get_font(max(8, int(2.8 * ppm)))
    fit = s["fit"]
    original, fill = fit.startswith("Original"), fit.startswith("Fill")

    for i, unit in enumerate(units[:cols * rows]):
        r, c = divmod(i, cols)
        x0 = margin + c * (cell_w + gap)
        y0 = margin + r * (cell_h + gap)
        aw, ah = cell_w, cell_h - cap_h
        if aw < 8 or ah < 8:
            continue
        if s["cutlines"]:
            d.rectangle([x0, y0, x0 + cell_w, y0 + cell_h], outline=(150, 150, 150))
        try:
            want = 4000 if original else min(4000, int(max(aw, ah) * (3 if fill else 1.3)))
            im, pw, ph = loader(unit, max(want, 16))
        except Exception as e:
            if errors is not None:
                errors.append(f"{os.path.basename(unit[0])}: {e}")
            continue
        if s["bw"]:
            im = im.convert("L").convert("RGB")
        if not original and (im.width > im.height) != (aw > ah):
            im = im.rotate(90, expand=True)

        if fill:
            sc = max(aw / im.width, ah / im.height)
            nw, nh = max(1, round(im.width * sc)), max(1, round(im.height * sc))
            im = im.resize((nw, nh), RESAMPLE)
            left, top = (nw - int(aw)) // 2, (nh - int(ah)) // 2
            im = im.crop((left, top, left + int(aw), top + int(ah)))
            nw, nh = im.size
        else:
            if original:
                nw, nh = pw * ppm, ph * ppm
                if nw > aw or nh > ah:
                    k = min(aw / nw, ah / nh)
                    nw, nh = nw * k, nh * k
            else:
                k = min(aw / im.width, ah / im.height)
                nw, nh = im.width * k, im.height * k
            nw, nh = max(1, round(nw)), max(1, round(nh))
            im = im.resize((nw, nh), RESAMPLE)

        px = round(x0 + (aw - nw) / 2)
        py = round(y0 + (ah - nh) / 2)
        sheet.paste(im, (px, py))
        if s["border"]:
            d.rectangle([px, py, px + nw - 1, py + nh - 1], outline=(0, 0, 0),
                        width=max(1, round(0.25 * ppm)))
        if cap_h:
            text = caption_text(unit, s["caption"])
            trimmed = False
            while len(text) > 3 and d.textlength(text, font=font) > aw:
                text, trimmed = text[:-1], True
            if trimmed:
                text = text[:-1] + ".."
            tw = d.textlength(text, font=font)
            d.text((x0 + (aw - tw) / 2, y0 + ah + cap_h * 0.15), text,
                   fill=(0, 0, 0), font=font)
    return sheet


def chunks(units, per):
    return [units[i:i + per] for i in range(0, len(units), per)]


# ------------------------------------------------------------------- jobs
def make_dc(printer, s):
    if win32print is None:
        raise RuntimeError("Printing sirf Windows par chalti hai.")
    code = PAPERS[s["paper"]][2]
    h = win32print.OpenPrinter(printer)
    try:
        dm = win32print.GetPrinter(h, 2)["pDevMode"]
    finally:
        win32print.ClosePrinter(h)
    if dm is None:
        dc = win32ui.CreateDC()
        dc.CreatePrinterDC(printer)
        return dc
    if code:
        dm.PaperSize = code
        dm.Fields |= 0x2      # DM_PAPERSIZE
    dm.Orientation = 2 if s["orientation"] == "Landscape" else 1
    dm.Fields |= 0x1          # DM_ORIENTATION
    dm.Color = 1 if s["bw"] else 2
    dm.Fields |= 0x800        # DM_COLOR
    return win32ui.CreateDCFromHandle(win32gui.CreateDC("WINSPOOL", printer, dm))


def run_print(units, s, printer, progress, cancel, errors):
    dc = make_dc(printer, s)
    try:
        W, H = dc.GetDeviceCaps(8), dc.GetDeviceCaps(10)       # printable pixels
        mm_w, mm_h = dc.GetDeviceCaps(4), dc.GetDeviceCaps(6)   # size in mm
        k = min(1.0, QUALITY[s.get("quality", "Normal")][0] / max(W, H))
        cw, ch = int(W * k), int(H * k)
        sheets = chunks(units, math.prod(grid_for(s)))
        dc.StartDoc("Print Me")
        try:
            for i, part in enumerate(sheets):
                if cancel.is_set():
                    dc.AbortDoc()
                    return False
                img = compose_sheet(part, load_unit, cw, ch, mm_w, mm_h, s, errors)
                dc.StartPage()
                ImageWin.Dib(img).draw(dc.GetHandleOutput(), (0, 0, W, H))
                dc.EndPage()
                progress(i + 1, len(sheets))
            dc.EndDoc()
        except Exception:
            try:
                dc.AbortDoc()
            except Exception:
                pass
            raise
        return True
    finally:
        dc.DeleteDC()


def run_save_pdf(units, s, out_path, progress, cancel, errors):
    mm_w, mm_h = paper_mm(s)
    dpi = QUALITY[s.get("quality", "Normal")][1]
    W, H = int(mm_w / 25.4 * dpi), int(mm_h / 25.4 * dpi)
    sheets = chunks(units, math.prod(grid_for(s)))
    doc = fitz.open()
    for i, part in enumerate(sheets):
        if cancel.is_set():
            doc.close()
            return False
        img = compose_sheet(part, load_unit, W, H, mm_w, mm_h, s, errors)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=92)
        page = doc.new_page(width=mm_w / 25.4 * 72, height=mm_h / 25.4 * 72)
        page.insert_image(page.rect, stream=buf.getvalue())
        progress(i + 1, len(sheets))
    doc.save(out_path)
    doc.close()
    return True


# -------------------------------------------------------------------- GUI
class App:
    def __init__(self):
        self.root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()
        self.root.title(f"{APP_NAME}  -  {CREDIT}")
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = min(1300, sw - 30), min(760, sh - 90)          # chhoti screen (1366x768) par bhi fit
        self.root.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 3)}")
        self.root.minsize(min(1100, sw - 30), min(600, sh - 90))
        self.cfg = load_settings()
        st = ttk.Style()
        self.default_theme = st.theme_use()
        self.light_bg = st.lookup("TFrame", "background") or "#f0f0f0"
        self.colors = {**LIGHT, "bg": self.light_bg}
        self.settings_win, self.nb, self.latest = None, None, None
        self.last_dir = self.cfg["last_dir"]
        self.logo_small = ImageTk.PhotoImage(make_logo(44))
        try:
            self.root.iconphoto(True, ImageTk.PhotoImage(make_logo(64)))
        except Exception:
            pass
        self.items, self.by_iid, self.thumbs = [], {}, {}
        self.thumb_queue = []
        self.counter = 0
        self.q = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.job_label = ""
        self.job_kind = ""
        self.sheet_idx = 0
        self.preview_after = None
        self.preview_photo = None
        self.blank = ImageTk.PhotoImage(Image.new("RGB", (48, 48), "#e8e8e8"))
        self.build_ui()
        self.apply_theme()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.poll_id = self.root.after(100, self.poll)
        if self.v_autoupd.get() and repo_ready():
            self.root.after(2500, lambda: self.check_updates(False))

    # ---- UI
    def build_ui(self):
        c = self.cfg
        self.v_printer = tk.StringVar(value=c["printer"])
        self.v_paper = tk.StringVar(value=c["paper"])
        self.v_orient = tk.StringVar(value=c["orientation"])
        self.v_layout = tk.StringVar(value=c["layout"])
        self.v_fit = tk.StringVar(value=c["fit"])
        self.v_caption = tk.StringVar(value=c["caption"])
        self.v_copies = tk.IntVar(value=c["copies"])
        self.v_margin = tk.IntVar(value=c["margin"])
        self.v_bw = tk.BooleanVar(value=c["bw"])
        self.v_border = tk.BooleanVar(value=c["border"])
        self.v_cut = tk.BooleanVar(value=c["cutlines"])
        self.v_recursive = tk.BooleanVar(value=c["recursive"])
        self.v_sort = tk.StringVar(value=c["sort"])
        self.v_desc = tk.BooleanVar(value=c["sort_desc"])
        self.v_theme = tk.StringVar(value=c["theme"])
        self.v_afterprint = tk.StringVar(value=c["after_print"])
        self.v_confirm = tk.BooleanVar(value=c["confirm"])
        self.v_beep = tk.BooleanVar(value=c["beep"])
        self.v_remember = tk.BooleanVar(value=c["remember"])
        self.v_quality = tk.StringVar(value=c["quality"])
        self.v_autoupd = tk.BooleanVar(value=c["auto_update"])
        self.v_update_status = tk.StringVar(value="Not checked yet.")
        self.status = tk.StringVar(value="Folder ya files add kijiye (ya drag & drop karein).")

        root = self.root
        root.columnconfigure(0, weight=3, minsize=420)
        root.columnconfigure(1, weight=0)
        root.columnconfigure(2, weight=2, minsize=330)
        root.rowconfigure(1, weight=1)

        # --- header: logo + naam
        head = tk.Frame(root, bg="#2d2a6e")
        head.grid(row=0, column=0, columnspan=3, sticky="ew")
        tk.Label(head, image=self.logo_small, bg="#2d2a6e").pack(side="left", padx=(14, 10), pady=8)
        tk.Label(head, text=APP_NAME, bg="#2d2a6e", fg="white",
                 font=("Segoe UI", 20, "bold")).pack(side="left")
        tk.Label(head, text=TAGLINE, bg="#2d2a6e", fg="#b9b6f0",
                 font=("Segoe UI", 10)).pack(side="left", padx=14, pady=(8, 0))
        tk.Label(head, text=CREDIT, bg="#2d2a6e", fg="#ffffff",
                 font=("Segoe UI", 10, "bold")).pack(side="right", padx=16)
        btn_style = dict(fg="white", relief="flat", bd=0, padx=14, pady=5, cursor="hand2",
                         font=("Segoe UI", 10, "bold"), activeforeground="white")
        self.settings_btn = tk.Button(head, text="⚙  Settings", command=self.open_settings,
                                      bg="#4a46a8", activebackground="#6a65d8", **btn_style)
        self.settings_btn.pack(side="right", padx=(0, 4), pady=10)
        self.update_btn = tk.Button(head, text="", bg="#16a34a", activebackground="#22c55e", **btn_style)  # update milne par dikhega

        # --- left: file list
        left = ttk.Frame(root, padding=8)
        left.grid(row=1, column=0, sticky="nsew")
        left.rowconfigure(2, weight=1)
        left.columnconfigure(0, weight=1)
        bar = ttk.Frame(left)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        for i in range(3):
            bar.columnconfigure(i, weight=1)
        for i, (text, cmd) in enumerate((
                ("Add Folder", self.add_folder), ("Add Files", self.add_files),
                ("Clear All", self.clear_all),
                ("Select All", lambda: self.set_all(True)),
                ("Select None", lambda: self.set_all(False)),
                ("Remove Selected", self.remove_selected))):
            ttk.Button(bar, text=text, command=cmd).grid(
                row=i // 3, column=i % 3, sticky="ew", padx=2, pady=2)
        bar2 = ttk.Frame(left)
        bar2.grid(row=1, column=0, columnspan=2, sticky="ew", pady=6)
        ttk.Checkbutton(bar2, text="Include subfolders", variable=self.v_recursive).pack(side="left")
        ttk.Label(bar2, text="  Sort:").pack(side="left")
        ttk.Combobox(bar2, textvariable=self.v_sort, values=SORTS, state="readonly",
                     width=7).pack(side="left", padx=4)
        ttk.Checkbutton(bar2, text="Z-A / New-Old", variable=self.v_desc).pack(side="left")

        style = ttk.Style()
        style.configure("Thumb.Treeview", rowheight=54)
        self.tree = ttk.Treeview(left, style="Thumb.Treeview", columns=("use", "name", "info"),
                                 show="tree headings", selectmode="extended")
        self.tree.heading("#0", text="Preview")
        self.tree.heading("use", text="Print")
        self.tree.heading("name", text="File")
        self.tree.heading("info", text="Info")
        self.tree.column("#0", width=70, stretch=False)
        self.tree.column("use", width=46, stretch=False, anchor="center")
        self.tree.column("name", width=150)
        self.tree.column("info", width=115, stretch=False)
        sb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=2, column=0, sticky="nsew")
        sb.grid(row=2, column=1, sticky="ns")
        self.tree.bind("<Button-1>", self.on_tree_click)
        self.tree.bind("<Delete>", lambda e: self.remove_selected())
        if TkinterDnD:
            for w in (self.tree, root):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", lambda e: self.add_paths(self.root.tk.splitlist(e.data)))

        # --- middle: settings
        mid = ttk.LabelFrame(root, text="Print settings", padding=10)
        mid.grid(row=1, column=1, sticky="ns", padx=4, pady=8)
        mid.columnconfigure(1, weight=1)
        printers = self.list_printers()
        if self.v_printer.get() not in printers:
            self.v_printer.set(self.default_printer(printers))
        row = 0
        for label, var, values in (
                ("Printer", self.v_printer, printers), ("Paper size", self.v_paper, list(PAPERS)),
                ("Orientation", self.v_orient, ORIENTATIONS), ("Layout", self.v_layout, list(LAYOUTS)),
                ("Fit mode", self.v_fit, FIT_MODES), ("Caption", self.v_caption, CAPTIONS)):
            ttk.Label(mid, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Combobox(mid, textvariable=var, values=values, state="readonly",
                         width=20).grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=4)
            row += 1
        ttk.Label(mid, text="Copies (each image)").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Spinbox(mid, from_=1, to=99, textvariable=self.v_copies, width=6).grid(
            row=row, column=1, sticky="w", padx=(8, 0))
        row += 1
        ttk.Label(mid, text="Margin (mm)").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Spinbox(mid, from_=0, to=40, textvariable=self.v_margin, width=6).grid(
            row=row, column=1, sticky="w", padx=(8, 0))
        row += 1
        for text, var in (("Black & White", self.v_bw), ("Border around image", self.v_border),
                          ("Cut lines (cells)", self.v_cut)):
            ttk.Checkbutton(mid, text=text, variable=var).grid(
                row=row, column=0, columnspan=2, sticky="w", pady=2)
            row += 1

        # --- right: preview
        right = ttk.LabelFrame(root, text="Preview", padding=8)
        right.grid(row=1, column=2, sticky="nsew", padx=(4, 8), pady=8)
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        self.preview_cv = tk.Canvas(right, highlightthickness=0, width=300, height=300,
                                    bg=ttk.Style().lookup("TFrame", "background") or "#d9d9d9")
        self.preview_cv.grid(row=0, column=0, columnspan=3, sticky="nsew")
        self.preview_cv.bind("<Configure>", self.schedule_preview)
        ttk.Button(right, text="<  Prev", command=lambda: self.move_sheet(-1)).grid(row=1, column=0, pady=6)
        self.sheet_lbl = ttk.Label(right, text="")
        self.sheet_lbl.grid(row=1, column=1)
        ttk.Button(right, text="Next  >", command=lambda: self.move_sheet(1)).grid(row=1, column=2, pady=6)

        # --- bottom
        bottom = ttk.Frame(root, padding=(8, 0, 8, 8))
        bottom.grid(row=2, column=0, columnspan=3, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        ttk.Label(bottom, textvariable=self.status).grid(row=0, column=0, sticky="w")
        ttk.Label(bottom, text=f"{APP_NAME}  |  {CREDIT}", foreground="#6c5ce7").grid(
            row=0, column=1, columnspan=3, sticky="e")
        self.pbar = ttk.Progressbar(bottom, mode="determinate")
        self.pbar.grid(row=1, column=0, sticky="ew", pady=4, padx=(0, 8))
        self.btn_print = ttk.Button(bottom, text="Print", command=self.start_print)
        self.btn_pdf = ttk.Button(bottom, text="Save as PDF", command=self.start_pdf)
        self.btn_cancel = ttk.Button(bottom, text="Cancel", command=self.cancel.set, state="disabled")
        self.btn_print.grid(row=1, column=1, padx=2)
        self.btn_pdf.grid(row=1, column=2, padx=2)
        self.btn_cancel.grid(row=1, column=3, padx=2)

        for v in (self.v_printer, self.v_paper, self.v_orient, self.v_layout, self.v_fit,
                  self.v_caption, self.v_copies, self.v_margin, self.v_bw, self.v_border, self.v_cut):
            v.trace_add("write", self.schedule_preview)
        for v in (self.v_sort, self.v_desc):
            v.trace_add("write", lambda *a: (self.refresh_tree(), self.schedule_preview()))
        self.v_theme.trace_add("write", self.apply_theme)

    # ---- printers
    @staticmethod
    def list_printers():
        if win32print is None:
            return ["(Windows required)"]
        try:
            return [p[2] for p in win32print.EnumPrinters(2 | 4)] or ["(no printer found)"]
        except Exception:
            return ["(no printer found)"]

    @staticmethod
    def default_printer(printers):
        try:
            return win32print.GetDefaultPrinter()
        except Exception:
            return printers[0]

    # ---- settings snapshot
    def settings(self):
        def num(var, default, lo, hi):
            try:
                return max(lo, min(hi, int(var.get())))
            except (tk.TclError, ValueError):
                return default
        return {
            "printer": self.v_printer.get(), "paper": self.v_paper.get(),
            "orientation": self.v_orient.get(), "layout": self.v_layout.get(),
            "fit": self.v_fit.get(), "caption": self.v_caption.get(),
            "copies": num(self.v_copies, 1, 1, 99), "margin": num(self.v_margin, 5, 0, 40),
            "bw": self.v_bw.get(), "border": self.v_border.get(), "cutlines": self.v_cut.get(),
            "recursive": self.v_recursive.get(), "sort": self.v_sort.get(),
            "sort_desc": self.v_desc.get(),
            "theme": self.v_theme.get(), "after_print": self.v_afterprint.get(),
            "confirm": self.v_confirm.get(), "beep": self.v_beep.get(),
            "remember": self.v_remember.get(), "quality": self.v_quality.get(),
            "auto_update": self.v_autoupd.get(),
            "last_dir": self.last_dir if self.v_remember.get() else "",
        }

    def dialog_kw(self):
        """Pichla folder yaad rakhna (agar setting on hai)."""
        if self.v_remember.get() and self.last_dir and os.path.isdir(self.last_dir):
            return {"initialdir": self.last_dir}
        return {}

    # ---- file list
    def add_folder(self):
        d = filedialog.askdirectory(title="Images / PDF wala folder chuniye", **self.dialog_kw())
        if d:
            self.add_paths([d])

    def add_files(self):
        fs = filedialog.askopenfilenames(
            title="Files chuniye",
            filetypes=[("Images & PDF", " ".join("*" + e for e in SUPPORTED)), ("All", "*.*")],
            **self.dialog_kw())
        if fs:
            self.add_paths(fs)

    def add_paths(self, paths):
        if paths:
            first = os.path.normpath(str(paths[0]))
            self.last_dir = first if os.path.isdir(first) else os.path.dirname(first)
        files = collect_files(paths, self.v_recursive.get())
        existing = {it["path"] for it in self.items}
        added, bad = 0, []
        for f in files:
            if f in existing:
                continue
            try:
                it = make_item(f)
            except Exception:
                bad.append(os.path.basename(f))
                continue
            self.counter += 1
            it["iid"] = f"i{self.counter}"
            self.items.append(it)
            self.by_iid[it["iid"]] = it
            existing.add(f)
            self.thumb_queue.append(it)
            added += 1
        self.refresh_tree()
        self.kick_thumbs()
        self.schedule_preview()
        msg = f"{added} files add hui."
        if not files:
            msg = "Koi image/PDF nahi mili."
        if bad:
            msg += f" {len(bad)} file khul nahi saki (corrupt/password wali)."
        self.status.set(msg)

    def sort_items(self):
        key = {"Name": lambda i: os.path.basename(i["path"]).lower(),
               "Date": lambda i: i["mtime"], "Size": lambda i: i["size"]}[self.v_sort.get()]
        self.items.sort(key=key, reverse=self.v_desc.get())

    def refresh_tree(self):
        self.sort_items()
        self.tree.delete(*self.tree.get_children())
        for it in self.items:
            self.tree.insert("", "end", iid=it["iid"],
                             image=self.thumbs.get(it["path"], self.blank),
                             values=("☑" if it["checked"] else "☐",
                                     os.path.basename(it["path"]), it["info"]))
        self.update_status()

    def on_tree_click(self, e):
        if self.tree.identify_region(e.x, e.y) == "cell" and self.tree.identify_column(e.x) == "#1":
            iid = self.tree.identify_row(e.y)
            it = self.by_iid.get(iid)
            if it:
                it["checked"] = not it["checked"]
                self.tree.set(iid, "use", "☑" if it["checked"] else "☐")
                self.update_status()
                self.schedule_preview()

    def set_all(self, state):
        for it in self.items:
            it["checked"] = state
        self.refresh_tree()
        self.schedule_preview()

    def remove_selected(self):
        for iid in self.tree.selection():
            it = self.by_iid.pop(iid, None)
            if it:
                self.items.remove(it)
        self.refresh_tree()
        self.schedule_preview()

    def clear_all(self):
        self.pbar["value"] = 0
        self.sheet_idx = 0
        self.items.clear()
        self.by_iid.clear()
        self.thumb_queue.clear()
        self.refresh_tree()
        self.schedule_preview()

    # ---- thumbnails (chhote chunks me, taaki UI na ruke)
    def kick_thumbs(self):
        self.root.after(5, self.thumb_step)

    def thumb_step(self):
        for _ in range(3):
            if not self.thumb_queue:
                return
            it = self.thumb_queue.pop(0)
            try:
                page = 0 if it["kind"] == "pdf" else None
                im, _, _ = load_unit((it["path"], page), 96)
                im.thumbnail((48, 48))
                ph = ImageTk.PhotoImage(im)
                self.thumbs[it["path"]] = ph
                if self.tree.exists(it["iid"]):
                    self.tree.item(it["iid"], image=ph)
            except Exception:
                pass
        if self.thumb_queue:
            self.root.after(10, self.thumb_step)

    # ---- units & preview
    def build_units(self, s):
        units = []
        for it in self.items:
            if not it["checked"]:
                continue
            if it["kind"] == "pdf":
                units.extend([(it["path"], p) for p in range(it["pages"])] * s["copies"])
            else:
                units.extend([(it["path"], None)] * s["copies"])
        return units

    def update_status(self):
        s = self.settings()
        units = self.build_units(s)
        per = math.prod(grid_for(s))
        sheets = math.ceil(len(units) / per) if units else 0
        sel = sum(it["checked"] for it in self.items)
        if not self.busy:
            self.status.set(f"{len(self.items)} files, {sel} selected  ->  "
                            f"{len(units)} pages  ->  {sheets} sheets")

    def schedule_preview(self, *_):
        if self.preview_after:
            self.root.after_cancel(self.preview_after)
        self.preview_after = self.root.after(250, self.update_preview)

    def move_sheet(self, d):
        self.sheet_idx += d
        self.update_preview()

    def update_preview(self):
        self.preview_after = None
        s = self.settings()
        self.update_status()
        units = self.build_units(s)
        per = math.prod(grid_for(s))
        n = math.ceil(len(units) / per) if units else 0
        cv = self.preview_cv
        cv_w, cv_h = max(cv.winfo_width(), 120), max(cv.winfo_height(), 120)
        cv.delete("all")
        if n == 0:
            cv.create_text(cv_w // 2, cv_h // 2, text="Preview yaha dikhega", fill=self.colors["muted"])
            self.preview_photo = None
            self.sheet_lbl.configure(text="")
            return
        self.sheet_idx = max(0, min(self.sheet_idx, n - 1))
        mm_w, mm_h = paper_mm(s)
        k = min((cv_w - 16) / mm_w, (cv_h - 16) / mm_h)
        W, H = max(60, int(mm_w * k)), max(60, int(mm_h * k))
        part = units[self.sheet_idx * per:(self.sheet_idx + 1) * per]
        img = compose_sheet(part, load_unit, W, H, mm_w, mm_h, s)
        img = ImageOps.expand(img, border=1, fill="#888888")
        self.preview_photo = ImageTk.PhotoImage(img)
        cv.create_image(cv_w // 2, cv_h // 2, image=self.preview_photo)
        self.sheet_lbl.configure(text=f"Sheet {self.sheet_idx + 1} / {n}   ({len(units)} pages total)")

    # ---- theme
    @staticmethod
    def walk(w):
        for ch in w.winfo_children():
            yield ch
            yield from App.walk(ch)

    def apply_theme(self, *_):
        st = ttk.Style()
        if self.v_theme.get() == "Dark":
            c = self.colors = dict(DARK)
            st.theme_use("clam")
            st.configure(".", background=c["bg"], foreground=c["fg"], fieldbackground=c["field"],
                         troughcolor=c["panel"], bordercolor=c["line"], lightcolor=c["bg"],
                         darkcolor=c["bg"], focuscolor=c["bg"], insertcolor=c["fg"])
            st.configure("TLabelframe", background=c["bg"], bordercolor=c["line"])
            st.configure("TLabelframe.Label", background=c["bg"], foreground=c["cy"])
            st.configure("TButton", background=c["btn"], foreground=c["fg"], bordercolor=c["line"], padding=4)
            st.map("TButton", background=[("active", c["btn_hi"]), ("disabled", c["panel"])],
                   foreground=[("disabled", c["muted"])])
            for name in ("TCheckbutton", "TRadiobutton"):
                st.configure(name, background=c["bg"], foreground=c["fg"])
                st.map(name, indicatorcolor=[("selected", c["accent"]), ("!selected", c["field"])],
                       background=[("active", c["bg"])])
            st.configure("TCombobox", fieldbackground=c["field"], background=c["btn"], foreground=c["fg"],
                         arrowcolor=c["fg"], bordercolor=c["line"])
            st.map("TCombobox", fieldbackground=[("readonly", c["field"])],
                   foreground=[("readonly", c["fg"])], selectbackground=[("readonly", c["field"])],
                   selectforeground=[("readonly", c["fg"])])
            st.configure("TSpinbox", fieldbackground=c["field"], background=c["btn"], foreground=c["fg"],
                         arrowcolor=c["fg"], bordercolor=c["line"])
            st.configure("Treeview", background=c["field"], fieldbackground=c["field"], foreground=c["fg"],
                         bordercolor=c["line"])
            st.map("Treeview", background=[("selected", c["sel"])], foreground=[("selected", "#ffffff")])
            st.configure("Treeview.Heading", background=c["btn"], foreground=c["fg"], bordercolor=c["line"],
                         relief="flat")
            st.map("Treeview.Heading", background=[("active", c["btn_hi"])])
            st.configure("TProgressbar", background=c["accent"], troughcolor=c["panel"], bordercolor=c["line"])
            st.configure("TScrollbar", background=c["btn"], troughcolor=c["panel"], arrowcolor=c["fg"],
                         bordercolor=c["line"])
            st.configure("TNotebook", background=c["bg"], bordercolor=c["line"])
            st.configure("TNotebook.Tab", background=c["panel"], foreground=c["muted"], padding=(14, 6))
            st.map("TNotebook.Tab", background=[("selected", c["bg"])], foreground=[("selected", c["fg"])])
            st.configure("TSeparator", background=c["line"])
        else:
            c = self.colors = {**LIGHT, "bg": self.light_bg}
            st.theme_use(self.default_theme)
        st.configure("Thumb.Treeview", rowheight=54)
        self.root.configure(bg=c["bg"])
        self.preview_cv.configure(bg=c["bg"])
        if self.settings_win is not None and self.settings_win.winfo_exists():
            self.settings_win.configure(bg=c["bg"])
        self.style_popdowns()
        self.schedule_preview()

    def style_popdowns(self):
        """Combobox ki khulne wali list ke rang (dark mode ke liye)."""
        c = self.colors
        for top in (self.root, self.settings_win):
            if top is None or not top.winfo_exists():
                continue
            for w in self.walk(top):
                if isinstance(w, ttk.Combobox):
                    try:
                        pd = self.root.tk.eval(f"ttk::combobox::PopdownWindow {w}")
                        self.root.tk.call(f"{pd}.f.l", "configure", "-background", c["field"],
                                          "-foreground", c["fg"], "-selectbackground", c["sel"],
                                          "-selectforeground", "#ffffff")
                    except tk.TclError:
                        pass

    def beep(self):
        if self.v_beep.get() and winsound is not None:
            try:
                winsound.MessageBeep()
            except Exception:
                pass

    # ---- updates
    def check_updates(self, manual):
        if not repo_ready():
            self.v_update_status.set("Update server not set up yet.")
            if manual:
                messagebox.showinfo("Check for updates",
                                    "Update checking abhi set nahi hua.\n\n"
                                    "(Developer: print_images.py me GITHUB_REPO apne GitHub repo se badlein.)",
                                    parent=self.settings_win or self.root)
            return
        self.v_update_status.set("Checking...")

        def work():
            try:
                self.q.put(("update", fetch_latest(), manual))
            except Exception as e:
                self.q.put(("update_err", e, manual))
        threading.Thread(target=work, daemon=True).start()

    def on_update_result(self, info, manual):
        parent = self.settings_win if (self.settings_win and self.settings_win.winfo_exists()) else self.root
        tag = info.get("tag") or "?"
        if parse_ver(tag) > parse_ver(APP_VERSION):
            self.latest = info
            self.v_update_status.set(f"New version available: {tag}  (you have {APP_VERSION})")
            self.update_btn.configure(text=f"⬆  Update available: {tag}",
                                      command=lambda: webbrowser.open(info["url"]))
            self.update_btn.pack(side="right", padx=(0, 8), pady=10)
            if manual:
                notes = info.get("notes", "")[:400]
                if messagebox.askyesno("Update available",
                                       f"Print Me {tag} available hai (aapke paas {APP_VERSION} hai).\n\n"
                                       f"{notes}\n\nDownload page kholein?", parent=parent):
                    webbrowser.open(info["url"])
        else:
            self.v_update_status.set(f"You're up to date (v{APP_VERSION}).")
            if manual:
                messagebox.showinfo("Check for updates", f"Aap latest version chala rahe hain (v{APP_VERSION}).",
                                    parent=parent)

    def on_update_error(self, err, manual):
        parent = self.settings_win if (self.settings_win and self.settings_win.winfo_exists()) else self.root
        if isinstance(err, urllib.error.HTTPError) and err.code == 404:
            text = "Abhi tak koi release publish nahi hui."
        else:
            text = "Update check nahi ho paya. Internet check karke dobara try karein."
        self.v_update_status.set(text)
        if manual:
            messagebox.showinfo("Check for updates", text, parent=parent)

    # ---- settings window
    def var_map(self):
        return {"paper": self.v_paper, "orientation": self.v_orient, "layout": self.v_layout, "fit": self.v_fit,
                "caption": self.v_caption, "copies": self.v_copies, "margin": self.v_margin, "bw": self.v_bw,
                "border": self.v_border, "cutlines": self.v_cut, "recursive": self.v_recursive,
                "sort": self.v_sort, "sort_desc": self.v_desc, "theme": self.v_theme,
                "after_print": self.v_afterprint, "confirm": self.v_confirm, "beep": self.v_beep,
                "remember": self.v_remember, "quality": self.v_quality, "auto_update": self.v_autoupd}

    def reset_settings(self):
        if not messagebox.askyesno("Reset", "Saari settings default par wapas karein?", parent=self.settings_win):
            return
        for key, var in self.var_map().items():
            var.set(DEFAULTS[key])
        self.last_dir = ""

    def open_settings_folder(self):
        try:
            os.startfile(os.path.dirname(settings_file()))
        except Exception:
            messagebox.showinfo("Settings folder", os.path.dirname(settings_file()), parent=self.settings_win)

    def open_settings(self, tab=0):
        w = self.settings_win
        if w is not None and w.winfo_exists():
            w.lift()
            self.nb.select(tab)
            return
        w = self.settings_win = tk.Toplevel(self.root)
        w.title(f"{APP_NAME} - Settings")
        w.transient(self.root)
        w.resizable(False, False)
        w.configure(bg=self.colors["bg"])
        w.geometry(f"620x560+{self.root.winfo_rootx() + 80}+{self.root.winfo_rooty() + 50}")
        nb = self.nb = ttk.Notebook(w)
        nb.pack(fill="both", expand=True, padx=12, pady=(12, 6))
        ttk.Button(w, text="Close", command=w.destroy).pack(anchor="e", padx=12, pady=(0, 12))
        self.tab_general(nb)
        self.tab_printing(nb)
        self.tab_updates(nb)
        self.tab_about(nb)
        nb.select(tab)
        self.style_popdowns()

    def tab_general(self, nb):
        f = ttk.Frame(nb, padding=20)
        nb.add(f, text="General")
        f.columnconfigure(1, weight=1)
        ttk.Label(f, text="Theme").grid(row=0, column=0, sticky="w", pady=8)
        box = ttk.Frame(f)
        box.grid(row=0, column=1, sticky="w", padx=10)
        for t in ("Light", "Dark"):
            ttk.Radiobutton(box, text=t, value=t, variable=self.v_theme).pack(side="left", padx=(0, 16))
        ttk.Label(f, text="After printing").grid(row=1, column=0, sticky="w", pady=8)
        ttk.Combobox(f, textvariable=self.v_afterprint, values=AFTER_PRINT, state="readonly",
                     width=22).grid(row=1, column=1, sticky="w", padx=10)
        for i, (text, var) in enumerate((
                ("Ask for confirmation before printing", self.v_confirm),
                ("Play a sound when printing / saving finishes", self.v_beep),
                ("Remember the last folder I used", self.v_remember))):
            ttk.Checkbutton(f, text=text, variable=var).grid(row=2 + i, column=0, columnspan=2, sticky="w", pady=5)
        ttk.Separator(f).grid(row=5, column=0, columnspan=2, sticky="ew", pady=18)
        row = ttk.Frame(f)
        row.grid(row=6, column=0, columnspan=2, sticky="w")
        ttk.Button(row, text="Open settings folder", command=self.open_settings_folder).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Reset all settings", command=self.reset_settings).pack(side="left")

    def tab_printing(self, nb):
        f = ttk.Frame(nb, padding=20)
        nb.add(f, text="Printing")
        f.columnconfigure(1, weight=1)
        ttk.Label(f, text="Print quality").grid(row=0, column=0, sticky="w", pady=8)
        ttk.Combobox(f, textvariable=self.v_quality, values=list(QUALITY), state="readonly",
                     width=22).grid(row=0, column=1, sticky="w", padx=10)
        ttk.Label(f, text="Draft = fastest, smaller files.   Normal = recommended.\n"
                          "High = sharpest output, slower and bigger PDF files.",
                  foreground=self.colors["muted"], justify="left").grid(row=1, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(f, text="Include subfolders when adding a folder", variable=self.v_recursive).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(18, 5))
        ttk.Label(f, text="Default sort").grid(row=3, column=0, sticky="w", pady=8)
        sort_box = ttk.Frame(f)
        sort_box.grid(row=3, column=1, sticky="w", padx=10)
        ttk.Combobox(sort_box, textvariable=self.v_sort, values=SORTS, state="readonly", width=10).pack(side="left")
        ttk.Checkbutton(sort_box, text="Reverse order", variable=self.v_desc).pack(side="left", padx=12)
        ttk.Label(f, text="Tip: paper size, layout, copies, captions and other print options are on the main screen "
                          "and are remembered automatically.",
                  foreground=self.colors["muted"], wraplength=520, justify="left").grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(24, 0))

    def tab_updates(self, nb):
        f = ttk.Frame(nb, padding=20)
        nb.add(f, text="Updates")
        ttk.Label(f, text=f"Current version:  {APP_VERSION}", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(f, textvariable=self.v_update_status, wraplength=520).pack(anchor="w", pady=(8, 14))
        row = ttk.Frame(f)
        row.pack(anchor="w")
        ttk.Button(row, text="Check for updates now", command=lambda: self.check_updates(True)).pack(
            side="left", padx=(0, 8))
        ttk.Button(row, text="Open releases page",
                   command=lambda: webbrowser.open(releases_url()) if repo_ready() else self.check_updates(True)
                   ).pack(side="left")
        ttk.Checkbutton(f, text="Check for updates automatically when Print Me starts",
                        variable=self.v_autoupd).pack(anchor="w", pady=(22, 4))
        ttk.Label(f, text="An update check only asks GitHub for the latest version number. "
                          "Your files are never uploaded.",
                  foreground=self.colors["muted"], wraplength=520, justify="left").pack(anchor="w", pady=(6, 0))

    def tab_about(self, nb):
        f = ttk.Frame(nb, padding=20)
        nb.add(f, text="About Us")
        self.logo_about = ImageTk.PhotoImage(make_logo(96))
        ttk.Label(f, image=self.logo_about).pack(pady=(4, 6))
        ttk.Label(f, text=APP_NAME, font=("Segoe UI", 20, "bold")).pack()
        ttk.Label(f, text=f"Version {APP_VERSION}", foreground=self.colors["muted"]).pack()
        ttk.Label(f, text=TAGLINE, font=("Segoe UI", 10, "italic")).pack(pady=(4, 10))
        ttk.Label(f, justify="center", wraplength=520,
                  text="Print Me helps you bulk print whole folders of photos and PDFs in a few clicks, "
                       "with live preview, multiple-per-page layouts, copies, captions, borders and cut lines.\n\n"
                       "Your files stay on your computer. The only internet use is the optional update check.").pack()
        ttk.Label(f, text=CREDIT, font=("Segoe UI", 12, "bold")).pack(pady=(14, 8))
        row = ttk.Frame(f)
        row.pack()
        site = website_url()
        b1 = ttk.Button(row, text="Visit website", command=lambda: webbrowser.open(site))
        b2 = ttk.Button(row, text="Download page", command=lambda: webbrowser.open(releases_url()))
        b1.pack(side="left", padx=4)
        b2.pack(side="left", padx=4)
        if not site:
            b1.state(["disabled"])
            b2.state(["disabled"])
        ttk.Label(f, foreground=self.colors["muted"], justify="center", wraplength=520,
                  text=f"© {datetime.date.today().year} DM. All rights reserved.\n"
                       "Built with Python, Tkinter, Pillow, PyMuPDF and pywin32.").pack(pady=(14, 0))

    # ---- jobs
    def start_print(self):
        s = self.settings()
        units = self.build_units(s)
        if not units:
            messagebox.showinfo("Print", "Pehle kuch images/PDF select kijiye.")
            return
        printer = s["printer"]
        if printer.startswith("("):
            messagebox.showerror("Print", "Koi printer nahi mila.")
            return
        sheets = math.ceil(len(units) / math.prod(grid_for(s)))
        if self.v_confirm.get() and not messagebox.askyesno(
                "Print", f"{len(units)} pages ({sheets} sheets) '{printer}' par print honge.\n\nContinue?"):
            return
        self.job_kind = "print"
        self.job_label = f"{sheets} sheets print ho gayi."
        self.run_job(lambda errs: run_print(units, s, printer, self.on_progress, self.cancel, errs))

    def start_pdf(self):
        s = self.settings()
        units = self.build_units(s)
        if not units:
            messagebox.showinfo("PDF", "Pehle kuch images/PDF select kijiye.")
            return
        out = filedialog.asksaveasfilename(title="PDF kaha save karni hai?",
                                           defaultextension=".pdf", filetypes=[("PDF", "*.pdf")],
                                           **self.dialog_kw())
        if not out:
            return
        self.job_kind = "pdf"
        self.job_label = f"PDF save ho gayi:\n{out}"
        self.run_job(lambda errs: run_save_pdf(units, s, out, self.on_progress, self.cancel, errs))

    def run_job(self, fn):
        self.cancel.clear()
        self.set_busy(True)
        self.pbar["value"] = 0

        def work():
            errs = []
            try:
                self.q.put(("done", fn(errs), errs))
            except Exception as e:
                self.q.put(("fail", str(e)))
        threading.Thread(target=work, daemon=True).start()

    def on_progress(self, i, n):
        self.q.put(("progress", i, n))

    def set_busy(self, busy):
        self.busy = busy
        self.btn_print.configure(state="disabled" if busy else "normal")
        self.btn_pdf.configure(state="disabled" if busy else "normal")
        self.btn_cancel.configure(state="normal" if busy else "disabled")
        if not busy:
            self.update_status()

    def poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if msg[0] == "progress":
                    self.pbar["maximum"], self.pbar["value"] = msg[2], msg[1]
                    self.status.set(f"Working... {msg[1]} / {msg[2]} sheets")
                elif msg[0] == "done":
                    self.set_busy(False)
                    if msg[1]:
                        self.beep()
                    text = self.job_label if msg[1] else "Cancel kar diya gaya."
                    if msg[2]:
                        text += "\n\nYe files skip hui:\n" + "\n".join(msg[2][:15])
                    if msg[1] and self.job_kind == "print":
                        # print ke baad list clear karne ka option (Settings > General me badal sakte hain)
                        mode = self.v_afterprint.get()
                        if mode == "Always clear":
                            self.clear_all()
                            messagebox.showinfo("Print complete", text + "\n\nList clear kar di gayi.")
                        elif mode == "Never clear":
                            messagebox.showinfo("Print complete", text)
                        elif messagebox.askyesno(
                                "Print complete",
                                text + "\n\nList clear kar dein? (naye files add karne ke liye)"):
                            self.clear_all()
                    else:
                        messagebox.showinfo("Done", text)
                elif msg[0] == "fail":
                    self.set_busy(False)
                    messagebox.showerror("Error", msg[1])
                elif msg[0] == "update":
                    self.on_update_result(msg[1], msg[2])
                elif msg[0] == "update_err":
                    self.on_update_error(msg[1], msg[2])
        except queue.Empty:
            pass
        self.poll_id = self.root.after(100, self.poll)

    def on_close(self):
        self.cancel.set()
        save_settings(self.settings())
        for aid in (self.poll_id, self.preview_after):
            if aid:
                try:
                    self.root.after_cancel(aid)
                except Exception:
                    pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
