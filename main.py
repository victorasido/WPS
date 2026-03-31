# main.py — Word Signer
# GUI Tkinter: dark mode, settings, zone preview, batch, preset TTD, progress bar
# Flow: DOCX → detect zones (keyword dari nama file) → convert to PDF → inject TTD

import os
import platform
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from services.detector_service import detect_signature_zones
from services.injector_service import inject_signature
from services.converter_service import convert_to_pdf
from services.preset_service import load_preset, save_preset, load_settings, save_settings
from services.logger_service import log_success, log_error

# ── Themes ────────────────────────────────────────────────────
THEMES = {
    "light": {
        "bg":       "#ffffff",
        "surface":  "#f7f7f8",
        "border":   "#e5e5e5",
        "accent":   "#2563eb",
        "accent_h": "#1d4ed8",
        "text":     "#111111",
        "subtext":  "#6b7280",
        "success":  "#16a34a",
        "error":    "#dc2626",
        "btn_bg":   "#ffffff",
    },
    "dark": {
        "bg":       "#0f172a",
        "surface":  "#1e293b",
        "border":   "#334155",
        "accent":   "#3b82f6",
        "accent_h": "#2563eb",
        "text":     "#f1f5f9",
        "subtext":  "#94a3b8",
        "success":  "#22c55e",
        "error":    "#f87171",
        "btn_bg":   "#1e293b",
    },
}

FONT = "Segoe UI"

APP_W           = 540
APP_H           = 420
SETTINGS_W      = 420
SETTINGS_H      = 260
ZONE_W          = 520
ZONE_MIN_H      = 320
ZONE_MAX_H      = 640
ZONE_PER_ITEM_H = 90

# Inject position → label yang ditampilkan di Zone Preview
INJECT_POS_LABEL = {
    "above_same":     "↑ atas (same cell)",
    "above_prev_row": "↑ atas (row sebelumnya)",
    "below_same":     "↓ bawah (same cell)",
    "below_next_row": "↓ bawah (row berikutnya)",
}


def open_file(path: str):
    """Buka file dengan default app, cross-platform."""
    system = platform.system()
    if system == "Windows":
        os.startfile(path)
    elif system == "Darwin":
        os.system(f'open "{path}"')
    else:
        os.system(f'xdg-open "{path}"')


# ── FileCard widget ───────────────────────────────────────────
class FileCard(tk.Frame):
    def __init__(self, master, label, accepted_ext, multi=False, app=None, **kwargs):
        self._app          = app
        self._multi        = multi
        self._accepted_ext = accepted_ext
        self.file_paths    = []
        t = app.t if app else THEMES["light"]
        super().__init__(master, bg=t["surface"],
                         highlightbackground=t["border"], highlightthickness=1,
                         **kwargs)
        self._build(label, t)

    def _build(self, label, t):
        tk.Label(self, text=label.upper(), bg=t["surface"], fg=t["subtext"],
                 font=(FONT, 8, "bold")).pack(anchor="w", padx=16, pady=(12, 2))
        row = tk.Frame(self, bg=t["surface"])
        row.pack(fill="x", padx=16, pady=(0, 12))
        self.name_label = tk.Label(row, text="Belum ada file dipilih",
                                   bg=t["surface"], fg=t["subtext"],
                                   font=(FONT, 10), anchor="w")
        self.name_label.pack(side="left", fill="x", expand=True)
        self.btn = tk.Button(row, text="Pilih file",
                             bg=t["btn_bg"], fg=t["accent"],
                             font=(FONT, 9), relief="flat",
                             highlightbackground=t["border"], highlightthickness=1,
                             padx=14, pady=5, cursor="hand2",
                             command=self._pick)
        self.btn.pack(side="right", padx=(10, 0))

    def _pick(self):
        t       = self._app.t if self._app else THEMES["light"]
        ext_str = " ".join([f"*.{e}" for e in self._accepted_ext])
        if self._multi:
            paths = filedialog.askopenfilenames(
                filetypes=[("File", ext_str), ("All files", "*.*")])
            if paths:
                self.file_paths = list(paths)
                n       = len(paths)
                display = f"{n} file dipilih" if n > 1 else os.path.basename(paths[0])
                self.name_label.config(text=display, fg=t["text"])
                self.btn.config(text="Ganti file")
                self.config(highlightbackground=t["accent"])
        else:
            path = filedialog.askopenfilename(
                filetypes=[("File", ext_str), ("All files", "*.*")])
            if path:
                self.file_paths = [path]
                self.name_label.config(text=os.path.basename(path), fg=t["text"])
                self.btn.config(text="Ganti file")
                self.config(highlightbackground=t["accent"])

    def set_path(self, path: str):
        t = self._app.t if self._app else THEMES["light"]
        self.file_paths = [path]
        self.name_label.config(text=f"★ {os.path.basename(path)}", fg=t["accent"])
        self.btn.config(text="Ganti file")
        self.config(highlightbackground=t["accent"])

    def get(self):
        return self.file_paths[0] if self.file_paths else None

    def get_all(self):
        return self.file_paths

    def restore(self, paths: list, t: dict):
        """Restore file selection setelah theme toggle."""
        if not paths:
            return
        self.file_paths = paths
        n = len(paths)
        self.name_label.config(
            text=f"{n} file dipilih" if n > 1 else os.path.basename(paths[0]),
            fg=t["text"],
        )
        self.btn.config(text="Ganti file")
        self.config(highlightbackground=t["accent"])

    def restore_sig(self, path: str, t: dict):
        """Restore signature file setelah theme toggle."""
        if not path:
            return
        self.file_paths = [path]
        self.name_label.config(text=f"★ {os.path.basename(path)}", fg=t["accent"])
        self.btn.config(text="Ganti file")
        self.config(highlightbackground=t["accent"])


# ── Zone Preview Dialog ───────────────────────────────────────
class ZonePreviewDialog(tk.Toplevel):
    def __init__(self, master, zones, keyword, theme):
        super().__init__(master)
        self.title("Zona Tanda Tangan")
        self.resizable(False, False)
        self.grab_set()
        self.lift()
        self.focus_force()
        self.configure(bg=theme["bg"])
        self.result = None
        self._vars  = []
        h = max(ZONE_MIN_H, min(180 + len(zones) * ZONE_PER_ITEM_H, ZONE_MAX_H))
        self._build(zones, keyword, theme)
        self._center(master, ZONE_W, h)

    def _build(self, zones, keyword, t):
        # Header
        hdr = tk.Frame(self, bg=t["bg"])
        hdr.pack(fill="x", padx=22, pady=(18, 4))
        tk.Label(hdr, text=f"Ditemukan {len(zones)} zona TTD",
                 bg=t["bg"], fg=t["text"],
                 font=(FONT, 10, "bold")).pack(side="left")

        # Keyword badge
        kw_frame = tk.Frame(hdr, bg=t["surface"],
                            highlightbackground=t["border"], highlightthickness=1)
        kw_frame.pack(side="right")
        tk.Label(kw_frame, text=f'🔑 keyword: "{keyword}"',
                 bg=t["surface"], fg=t["accent"],
                 font=(FONT, 8), padx=8, pady=3).pack()

        tk.Label(self, text="Pilih zona yang akan di-TTD:",
                 bg=t["bg"], fg=t["subtext"],
                 font=(FONT, 9)).pack(anchor="w", padx=22, pady=(0, 8))

        # Footer
        tk.Frame(self, bg=t["border"], height=1).pack(side="bottom", fill="x")
        footer = tk.Frame(self, bg=t["bg"])
        footer.pack(side="bottom", fill="x", padx=22, pady=14)

        tk.Button(footer, text="Batalkan",
                  bg=t["surface"], fg=t["text"], font=(FONT, 9), relief="flat",
                  padx=16, pady=7, cursor="hand2",
                  highlightbackground=t["border"], highlightthickness=1,
                  command=self._cancel).pack(side="right", padx=(8, 0))

        self.ok_btn = tk.Button(
            footer, text=f"Proses  ({len(zones)} zona dipilih)",
            bg=t["accent"], fg="white", font=(FONT, 9, "bold"), relief="flat",
            padx=16, pady=7, cursor="hand2",
            activebackground=t["accent_h"], activeforeground="white",
            command=self._ok)
        self.ok_btn.pack(side="right")

        # Scrollable zone list
        container = tk.Frame(self, bg=t["bg"])
        container.pack(side="top", fill="both", expand=True, padx=22, pady=(0, 4))

        canvas    = tk.Canvas(container, bg=t["bg"], highlightthickness=0)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        inner     = tk.Frame(canvas, bg=t["bg"])
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        for zone in zones:
            var = tk.BooleanVar(value=True)
            self._vars.append(var)

            card = tk.Frame(inner, bg=t["surface"],
                            highlightbackground=t["border"], highlightthickness=1)
            card.pack(fill="x", pady=4, padx=2)

            tk.Checkbutton(card, variable=var, bg=t["surface"],
                           activebackground=t["surface"], selectcolor=t["bg"],
                           command=self._update_btn).pack(side="left", padx=10, pady=12)

            info = tk.Frame(card, bg=t["surface"])
            info.pack(side="left", fill="x", expand=True, pady=8, padx=(0, 10))

            # Matched name / context
            matched = zone.get("matched_name") or zone.get("context") or "(ruang TTD)"
            matched_display = (matched[:55] + "…") if len(matched) > 55 else matched
            tk.Label(info, text=matched_display, bg=t["surface"], fg=t["text"],
                     font=(FONT, 9, "bold"), anchor="w").pack(anchor="w")

            # Metadata row: confidence + inject position + match tier
            conf     = zone["confidence"]
            conf_pct = f"{conf:.0%}"
            pos_lbl  = INJECT_POS_LABEL.get(zone.get("inject_position", ""), "")

            if conf >= 0.9:
                tier_lbl  = "exact"
                badge_clr = t["success"]
            elif conf >= 0.85:
                tier_lbl  = "case-insensitive"
                badge_clr = t["accent"]
            else:
                tier_lbl  = "partial"
                badge_clr = t["subtext"]

            meta = f"confidence {conf_pct}  ·  {tier_lbl}  ·  {pos_lbl}"
            tk.Label(info, text=meta, bg=t["surface"], fg=badge_clr,
                     font=(FONT, 8)).pack(anchor="w", pady=(3, 0))

    def _update_btn(self):
        n = sum(v.get() for v in self._vars)
        self.ok_btn.config(text=f"Proses  ({n} zona dipilih)")

    def _ok(self):
        self.result = [i for i, v in enumerate(self._vars) if v.get()]
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()

    def _center(self, master, w, h):
        self.update_idletasks()
        mx = master.winfo_rootx() + (master.winfo_width()  - w) // 2
        my = master.winfo_rooty() + (master.winfo_height() - h) // 2
        self.geometry(f"{w}x{h}+{mx}+{my}")


# ── Settings Dialog ───────────────────────────────────────────
class SettingsDialog(tk.Toplevel):
    def __init__(self, master, settings, theme, on_save):
        super().__init__(master)
        self.title("Pengaturan")
        self.resizable(False, False)
        self.grab_set()
        self._on_save = on_save
        self.configure(bg=theme["bg"])
        self._build(settings, theme)
        self._center(master, SETTINGS_W, SETTINGS_H)

    def _build(self, settings, t):
        tk.Label(self, text="Pengaturan", bg=t["bg"], fg=t["text"],
                 font=(FONT, 11, "bold")).pack(anchor="w", padx=24, pady=(20, 14))

        grid = tk.Frame(self, bg=t["bg"])
        grid.pack(fill="x", padx=24)

        def row_label(r, text):
            tk.Label(grid, text=text, bg=t["bg"], fg=t["text"],
                     font=(FONT, 9), width=24, anchor="w").grid(
                row=r, column=0, sticky="w", pady=10)

        # Confidence threshold
        row_label(0, "Confidence threshold")
        self._conf_var = tk.DoubleVar(value=settings.get("confidence_threshold", 0.4))
        conf_row = tk.Frame(grid, bg=t["bg"])
        conf_row.grid(row=0, column=1, sticky="w", padx=8)
        tk.Scale(conf_row, from_=0.1, to=1.0, resolution=0.05, orient="horizontal",
                 variable=self._conf_var, bg=t["bg"], fg=t["text"],
                 troughcolor=t["surface"], highlightthickness=0,
                 length=180, command=lambda v: conf_lbl.config(
                     text=f"{float(v):.2f}")).pack(side="left")
        conf_lbl = tk.Label(conf_row, text=f"{self._conf_var.get():.2f}",
                            bg=t["bg"], fg=t["subtext"], font=(FONT, 9), width=4)
        conf_lbl.pack(side="left")

        # Auto-buka PDF
        row_label(1, "Auto-buka PDF selesai")
        self._auto_var = tk.BooleanVar(value=settings.get("auto_open_pdf", True))
        tk.Checkbutton(grid, variable=self._auto_var, bg=t["bg"],
                       activebackground=t["bg"],
                       selectcolor=t["surface"]).grid(row=1, column=1, sticky="w", padx=8)

        # Last pages scan
        row_label(2, "Scan N halaman terakhir")
        self._pages_var = tk.IntVar(value=settings.get("last_pages_scan", 2))
        tk.Spinbox(grid, from_=1, to=10, textvariable=self._pages_var,
                   width=4, font=(FONT, 9),
                   bg=t["surface"], fg=t["text"],
                   highlightbackground=t["border"], relief="flat").grid(
            row=2, column=1, sticky="w", padx=8)

        tk.Frame(self, bg=t["border"], height=1).pack(fill="x", pady=(16, 0))
        footer = tk.Frame(self, bg=t["bg"])
        footer.pack(fill="x", padx=24, pady=14)

        tk.Button(footer, text="Batal", bg=t["surface"], fg=t["text"],
                  font=(FONT, 9), relief="flat", padx=14, pady=6, cursor="hand2",
                  highlightbackground=t["border"], highlightthickness=1,
                  command=self.destroy).pack(side="right", padx=(8, 0))

        tk.Button(footer, text="Simpan", bg=t["accent"], fg="white",
                  font=(FONT, 9, "bold"), relief="flat", padx=18, pady=6,
                  cursor="hand2", activebackground=t["accent_h"],
                  activeforeground="white", command=self._save).pack(side="right")

    def _save(self):
        self._on_save({
            "confidence_threshold": round(self._conf_var.get(), 2),
            "auto_open_pdf":        self._auto_var.get(),
            "last_pages_scan":      self._pages_var.get(),
        })
        self.destroy()

    def _center(self, master, w, h):
        self.update_idletasks()
        mx = master.winfo_rootx() + (master.winfo_width()  - w) // 2
        my = master.winfo_rooty() + (master.winfo_height() - h) // 2
        self.geometry(f"{w}x{h}+{mx}+{my}")


# ── Main App ──────────────────────────────────────────────────
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Word Signer")
        self.root.resizable(False, False)

        self._settings = load_settings()
        self._dark     = self._settings.get("dark_mode", False)
        self.t         = THEMES["dark" if self._dark else "light"]
        self.root.configure(bg=self.t["bg"])

        self._build()
        self._center(APP_W, APP_H)

        preset = load_preset()
        if preset and os.path.exists(preset):
            self.sig_card.set_path(preset)

    def _build(self):
        t = self.t

        # ── Header
        header = tk.Frame(self.root, bg=t["bg"])
        header.pack(fill="x", padx=26, pady=(22, 0))

        tk.Label(header, text="Word Signer", bg=t["bg"], fg=t["text"],
                 font=(FONT, 16, "bold")).pack(side="left")

        tk.Button(header, text="⚙", bg=t["bg"], fg=t["subtext"],
                  font=("Segoe UI Emoji", 13), relief="flat", bd=0,
                  cursor="hand2", padx=4,
                  activebackground=t["bg"], activeforeground=t["text"],
                  command=self._open_settings).pack(side="right", padx=(4, 0))

        tk.Button(header, text="🌙" if not self._dark else "☀️",
                  bg=t["bg"], fg=t["subtext"],
                  font=("Segoe UI Emoji", 13), relief="flat", bd=0,
                  cursor="hand2", padx=4,
                  activebackground=t["bg"], activeforeground=t["text"],
                  command=self._toggle_theme).pack(side="right")

        tk.Label(self.root,
                 text="Sisipkan tanda tangan ke dokumen Word, lalu ekspor ke PDF.",
                 bg=t["bg"], fg=t["subtext"],
                 font=(FONT, 9)).pack(anchor="w", padx=26, pady=(5, 0))

        tk.Frame(self.root, bg=t["border"], height=1).pack(fill="x", pady=(16, 0))

        # ── Body
        body = tk.Frame(self.root, bg=t["bg"])
        body.pack(fill="x", padx=26, pady=16)

        self.docx_card = FileCard(body, "Dokumen Word  (pilih satu atau lebih)",
                                  ["docx"], multi=True, app=self)
        self.docx_card.pack(fill="x", pady=(0, 10))

        self.sig_card = FileCard(body, "Tanda Tangan  (nama file = keyword pencarian)",
                                 ["png", "jpg", "jpeg", "svg"], multi=False, app=self)
        self.sig_card.pack(fill="x")

        # Wrap _pick untuk auto-save preset
        orig_pick = self.sig_card._pick
        def _sig_pick_with_preset():
            orig_pick()
            path = self.sig_card.get()
            if path:
                save_preset(path)
        self.sig_card._pick = _sig_pick_with_preset
        self.sig_card.btn.config(command=_sig_pick_with_preset)

        # Hint text di bawah sig card
        tk.Label(self.root,
                 text='Contoh: "firano.png" → cari kata firano di dokumen',
                 bg=t["bg"], fg=t["subtext"],
                 font=(FONT, 8)).pack(anchor="w", padx=26, pady=(2, 0))

        tk.Frame(self.root, bg=t["border"], height=1).pack(fill="x", pady=(12, 0))

        # ── Progress bar (hidden by default)
        self._pb_frame = tk.Frame(self.root, bg=t["bg"])
        self._pb_frame.pack(fill="x", padx=26)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Accent.Horizontal.TProgressbar",
                        troughcolor=t["surface"], background=t["accent"],
                        bordercolor=t["bg"], lightcolor=t["accent"],
                        darkcolor=t["accent"])
        self._progress   = ttk.Progressbar(self._pb_frame, mode="indeterminate",
                                            style="Accent.Horizontal.TProgressbar")
        self._pb_visible = False

        # ── Footer
        footer = tk.Frame(self.root, bg=t["bg"])
        footer.pack(fill="x", padx=26, pady=14)

        self._status = tk.Label(footer, text="", bg=t["bg"], fg=t["subtext"],
                                font=(FONT, 9))
        self._status.pack(side="left", anchor="center")

        self._run_btn = tk.Button(footer, text="Buat PDF",
                                  bg=t["accent"], fg="white",
                                  font=(FONT, 10, "bold"), relief="flat",
                                  cursor="hand2", padx=22, pady=9,
                                  activebackground=t["accent_h"],
                                  activeforeground="white",
                                  command=self._run)
        self._run_btn.pack(side="right")

    # ── Helpers ───────────────────────────────────────────────

    def _set_status(self, msg: str, color=None):
        self._status.config(text=msg, fg=color or self.t["subtext"])
        self.root.update()

    def _show_progress(self, show: bool):
        if show and not self._pb_visible:
            self._progress.pack(fill="x", pady=(6, 0))
            self._progress.start(10)
            self._pb_visible = True
        elif not show and self._pb_visible:
            self._progress.stop()
            self._progress.pack_forget()
            self._pb_visible = False

    def _keyword_from_sig(self, sig_path: str) -> str:
        """Ambil keyword dari nama file TTD (strip ekstensi)."""
        return os.path.splitext(os.path.basename(sig_path))[0]

    # ── Main run ──────────────────────────────────────────────

    def _run(self):
        t          = self.t
        docx_files = self.docx_card.get_all()
        sig        = self.sig_card.get()

        if not docx_files:
            self._set_status("Pilih file Word dulu.", t["error"]); return
        if not sig:
            self._set_status("Pilih file tanda tangan dulu.", t["error"]); return

        keyword = self._keyword_from_sig(sig)
        self._run_btn.config(state="disabled")
        self._show_progress(True)
        success_outputs = []

        try:
            # Zone preview dilakukan sekali di file pertama,
            # lalu selected_indices dipakai ulang untuk file berikutnya dalam batch.
            selected_indices: list | None = None

            for i, docx in enumerate(docx_files):
                prefix = f"[{i+1}/{len(docx_files)}] " if len(docx_files) > 1 else ""

                # 1. Detect zones
                self._set_status(
                    f'{prefix}Mencari "{keyword}" di {os.path.basename(docx)}...'
                )
                zones = detect_signature_zones(
                    docx, sig,
                    confidence_threshold=self._settings.get("confidence_threshold", 0.4),
                    last_pages=self._settings.get("last_pages_scan", 2),
                )

                if not zones:
                    raise ValueError(
                        f'Keyword "{keyword}" tidak ditemukan di:\n{os.path.basename(docx)}'
                    )

                # 2. Zone preview — hanya untuk file pertama di batch
                if selected_indices is None:
                    self._show_progress(False)
                    dlg = ZonePreviewDialog(self.root, zones, keyword, t)
                    self.root.wait_window(dlg)
                    self._show_progress(True)

                    if dlg.result is None:
                        self._set_status("Dibatalkan.", t["subtext"])
                        return
                    selected_indices = dlg.result
                    if not selected_indices:
                        self._set_status("Tidak ada zona dipilih.", t["subtext"])
                        return

                # Guard: jika file batch punya lebih sedikit zona, pakai yang ada
                selected_zones = [zones[j] for j in selected_indices if j < len(zones)]
                if not selected_zones:
                    selected_zones = zones  # fallback: pakai semua

                # 3. Convert DOCX → PDF
                self._set_status(f"{prefix}Mengkonversi ke PDF...")
                with open(docx, "rb") as f:
                    docx_bytes = f.read()
                pdf_bytes = convert_to_pdf(docx_bytes)

                # 4. Inject TTD ke PDF
                self._set_status(
                    f"{prefix}Menyisipkan TTD di {len(selected_zones)} zona..."
                )
                signed_pdf = inject_signature(pdf_bytes, sig, selected_zones)

                # 5. Simpan
                output = docx.replace(".docx", "_signed.pdf")
                with open(output, "wb") as f:
                    f.write(signed_pdf)

                log_success(docx, output, len(selected_zones))
                success_outputs.append(output)

        except ValueError as e:
            self._set_status(str(e), t["error"])
            log_error(docx_files[0] if docx_files else "", str(e))
            messagebox.showerror("Tidak Ditemukan", str(e))

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._set_status("Terjadi kesalahan.", t["error"])
            log_error(docx_files[0] if docx_files else "", str(e))
            messagebox.showerror("Error", str(e))

        finally:
            self._show_progress(False)
            self._run_btn.config(state="normal")

        if not success_outputs:
            return

        if len(success_outputs) == 1:
            out = success_outputs[0]
            self._set_status(f"✓ Selesai — {os.path.basename(out)}", t["success"])
            messagebox.showinfo("Selesai", f"PDF berhasil dibuat!\n\n{out}")
            if self._settings.get("auto_open_pdf", True):
                open_file(out)
        else:
            self._set_status(f"✓ {len(success_outputs)} file berhasil!", t["success"])
            out_list = "\n".join(os.path.basename(p) for p in success_outputs)
            messagebox.showinfo(
                "Selesai",
                f"{len(success_outputs)} PDF berhasil dibuat:\n\n{out_list}",
            )

    # ── Settings ──────────────────────────────────────────────

    def _open_settings(self):
        def on_save(s):
            self._settings.update(s)
            save_settings(self._settings)
        SettingsDialog(self.root, self._settings, self.t, on_save)

    # ── Theme toggle ──────────────────────────────────────────

    def _toggle_theme(self):
        # Simpan state sebelum rebuild
        docx_paths = self.docx_card.get_all()
        sig_path   = self.sig_card.get()

        self._dark                 = not self._dark
        self.t                     = THEMES["dark" if self._dark else "light"]
        self._settings["dark_mode"] = self._dark
        save_settings(self._settings)

        for w in self.root.winfo_children():
            w.destroy()
        self.root.configure(bg=self.t["bg"])
        self._build()

        # Restore state
        if docx_paths:
            self.docx_card.restore(docx_paths, self.t)
        if sig_path:
            self.sig_card.restore_sig(sig_path, self.t)

    # ── Window centering ──────────────────────────────────────

    def _center(self, w, h):
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth()  - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")


# ── Entry point ───────────────────────────────────────────────

def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()