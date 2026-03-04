# main.py — Word Signer (Enhanced)
# GUI Tkinter dengan: dark mode, settings, zone preview, batch, preset TTD, progress bar

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from services.detector_service import detect_signature_zones
from services.injector_service import inject_signature
from services.converter_service import convert_to_pdf
from services.preset_service import load_preset, save_preset, load_settings, save_settings
from services.logger_service import log_success, log_error

# ─── Themes ────────────────────────────────────────────────
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


# ─── FileCard widget ─────────────────────────────────────────
class FileCard(tk.Frame):
    def __init__(self, master, label, accepted_ext, multi=False, app=None, **kwargs):
        self._app = app
        self._multi = multi
        self._label_text = label
        self.file_paths = []
        t = app.t if app else THEMES["light"]
        super().__init__(master, bg=t["surface"],
                         highlightbackground=t["border"], highlightthickness=1,
                         **kwargs)
        self._build(label, t)

    def _build(self, label, t):
        tk.Label(self, text=label.upper(), bg=t["surface"], fg=t["subtext"],
                 font=(FONT, 8, "bold")).pack(anchor="w", padx=14, pady=(12, 2))

        row = tk.Frame(self, bg=t["surface"])
        row.pack(fill="x", padx=14, pady=(0, 12))
        self._row = row

        self.name_label = tk.Label(row, text="Belum ada file dipilih",
                                   bg=t["surface"], fg=t["subtext"],
                                   font=(FONT, 10), anchor="w")
        self.name_label.pack(side="left", fill="x", expand=True)

        self.btn = tk.Button(row, text="Pilih file",
                             bg=t["btn_bg"], fg=t["accent"],
                             font=(FONT, 9), relief="flat",
                             highlightbackground=t["border"], highlightthickness=1,
                             padx=12, pady=4, cursor="hand2",
                             command=self._pick)
        self.btn.pack(side="right", padx=(8, 0))

    def _pick(self):
        t = self._app.t if self._app else THEMES["light"]
        ext_str = " ".join([f"*.{e}" for e in self.accepted_ext])
        if self._multi:
            paths = filedialog.askopenfilenames(
                filetypes=[("File", ext_str), ("All files", "*.*")]
            )
            if paths:
                self.file_paths = list(paths)
                n = len(paths)
                display = f"{n} file dipilih" if n > 1 else os.path.basename(paths[0])
                self.name_label.config(text=display, fg=t["text"])
                self.btn.config(text="Ganti file")
                self.config(highlightbackground=t["accent"])
        else:
            path = filedialog.askopenfilename(
                filetypes=[("File", ext_str), ("All files", "*.*")]
            )
            if path:
                self.file_paths = [path]
                self.name_label.config(text=os.path.basename(path), fg=t["text"])
                self.btn.config(text="Ganti file")
                self.config(highlightbackground=t["accent"])

    @property
    def accepted_ext(self):
        # accessed by _build which is called before subclass sets it
        return getattr(self, "_accepted_ext", [])

    @accepted_ext.setter
    def accepted_ext(self, value):
        self._accepted_ext = value

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

    def apply_theme(self, t):
        has_file = bool(self.file_paths)
        border = t["accent"] if has_file else t["border"]
        self.config(bg=t["surface"], highlightbackground=border)
        for child in self.winfo_children():
            if isinstance(child, tk.Label):
                child.config(bg=t["surface"])
            elif isinstance(child, tk.Frame):
                child.config(bg=t["surface"])
                for c in child.winfo_children():
                    if isinstance(c, tk.Label):
                        c.config(bg=t["surface"],
                                 fg=t["text"] if has_file else t["subtext"])
                    elif isinstance(c, tk.Button):
                        c.config(bg=t["btn_bg"], fg=t["accent"],
                                 highlightbackground=t["border"])


# override accepted_ext before build runs — patch in __init__
_orig_fc_init = FileCard.__init__


def _patched_fc_init(self, master, label, accepted_ext, multi=False, app=None, **kwargs):
    self._accepted_ext = accepted_ext
    _orig_fc_init(self, master, label, accepted_ext, multi=multi, app=app, **kwargs)


FileCard.__init__ = _patched_fc_init


# ─── Zone Preview Dialog ──────────────────────────────────────
class ZonePreviewDialog(tk.Toplevel):
    def __init__(self, master, zones, theme):
        super().__init__(master)
        self.title("Zona Tanda Tangan")
        self.resizable(False, False)
        self.grab_set()
        t = theme
        self.configure(bg=t["bg"])
        self.result = None
        self._vars = []
        self._build(zones, t)
        h = min(120 + len(zones) * 80 + 70, 600)
        self._center(master, 460, h)

    def _build(self, zones, t):
        tk.Label(self, text=f"Ditemukan {len(zones)} zona — pilih yang akan di TTD:",
                 bg=t["bg"], fg=t["text"],
                 font=(FONT, 10, "bold")).pack(anchor="w", padx=20, pady=(16, 8))

        # Scrollable list
        container = tk.Frame(self, bg=t["bg"])
        container.pack(fill="both", expand=True, padx=20)

        canvas = tk.Canvas(container, bg=t["bg"], highlightthickness=0)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=t["bg"])
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for zone in zones:
            var = tk.BooleanVar(value=True)
            self._vars.append(var)

            card = tk.Frame(inner, bg=t["surface"],
                            highlightbackground=t["border"], highlightthickness=1)
            card.pack(fill="x", pady=3, padx=(0, 4))

            tk.Checkbutton(card, variable=var, bg=t["surface"],
                           activebackground=t["surface"],
                           selectcolor=t["bg"],
                           command=self._update_btn).pack(side="left", padx=8, pady=10)

            info = tk.Frame(card, bg=t["surface"])
            info.pack(side="left", fill="x", expand=True, pady=6, padx=(0, 8))

            ctx = (zone["context"][:52] + "…") if len(zone["context"]) > 52 \
                else zone["context"] or "(paragraf kosong)"
            tk.Label(info, text=ctx, bg=t["surface"], fg=t["text"],
                     font=(FONT, 9), anchor="w").pack(anchor="w")

            conf = zone["confidence"]
            badge_clr = t["success"] if conf >= 0.7 else \
                        t["accent"] if conf >= 0.5 else t["subtext"]
            src = "📄 Paragraf" if zone["source"] == "paragraph" else "📋 Tabel"
            tk.Label(info,
                     text=f'{src}  ·  Keyword: {zone["keyword"] or "-"}  ·  '
                          f'Confidence: {conf:.0%}',
                     bg=t["surface"], fg=badge_clr,
                     font=(FONT, 8)).pack(anchor="w")

        # Footer
        footer = tk.Frame(self, bg=t["bg"])
        footer.pack(fill="x", padx=20, pady=(10, 16))

        tk.Button(footer, text="Batalkan", bg=t["surface"], fg=t["text"],
                  font=(FONT, 9), relief="flat", padx=14, pady=6, cursor="hand2",
                  command=self._cancel).pack(side="right", padx=(6, 0))

        self.ok_btn = tk.Button(footer, text=f"Proses ({len(zones)} zona dipilih)",
                                bg=t["accent"], fg="white",
                                font=(FONT, 9, "bold"), relief="flat",
                                padx=14, pady=6, cursor="hand2",
                                activebackground=t["accent_h"], activeforeground="white",
                                command=self._ok)
        self.ok_btn.pack(side="right")

    def _update_btn(self):
        n = sum(v.get() for v in self._vars)
        self.ok_btn.config(text=f"Proses ({n} zona dipilih)")

    def _ok(self):
        self.result = [i for i, v in enumerate(self._vars) if v.get()]
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()

    def _center(self, master, w, h):
        self.update_idletasks()
        mx = master.winfo_rootx() + (master.winfo_width() - w) // 2
        my = master.winfo_rooty() + (master.winfo_height() - h) // 2
        self.geometry(f"{w}x{h}+{mx}+{my}")


# ─── Settings Dialog ──────────────────────────────────────────
class SettingsDialog(tk.Toplevel):
    def __init__(self, master, settings, theme, on_save):
        super().__init__(master)
        self.title("Pengaturan")
        self.resizable(False, False)
        self.grab_set()
        self._on_save = on_save
        t = theme
        self.configure(bg=t["bg"])
        self._build(settings, t)
        self._center(master, 380, 240)

    def _build(self, settings, t):
        tk.Label(self, text="Pengaturan", bg=t["bg"], fg=t["text"],
                 font=(FONT, 11, "bold")).pack(anchor="w", padx=22, pady=(18, 12))

        grid = tk.Frame(self, bg=t["bg"])
        grid.pack(fill="x", padx=22)

        def row_label(r, text):
            tk.Label(grid, text=text, bg=t["bg"], fg=t["text"],
                     font=(FONT, 9), width=22, anchor="w").grid(
                row=r, column=0, sticky="w", pady=8)

        # Confidence threshold
        row_label(0, "Confidence Threshold")
        self._conf_var = tk.DoubleVar(value=settings.get("confidence_threshold", 0.4))
        tk.Scale(grid, from_=0.1, to=1.0, resolution=0.05, orient="horizontal",
                 variable=self._conf_var, bg=t["bg"], fg=t["text"],
                 troughcolor=t["surface"], highlightthickness=0,
                 length=180).grid(row=0, column=1, padx=8)

        # Signature width
        row_label(1, "Lebar TTD (inci)")
        self._width_var = tk.DoubleVar(value=settings.get("signature_width_inches", 1.5))
        tk.Scale(grid, from_=0.5, to=3.0, resolution=0.1, orient="horizontal",
                 variable=self._width_var, bg=t["bg"], fg=t["text"],
                 troughcolor=t["surface"], highlightthickness=0,
                 length=180).grid(row=1, column=1, padx=8)

        # Auto-open PDF
        row_label(2, "Auto-buka PDF selesai")
        self._auto_var = tk.BooleanVar(value=settings.get("auto_open_pdf", True))
        tk.Checkbutton(grid, variable=self._auto_var, bg=t["bg"],
                       activebackground=t["bg"],
                       selectcolor=t["surface"]).grid(row=2, column=1, sticky="w", padx=8)

        # Footer
        footer = tk.Frame(self, bg=t["bg"])
        footer.pack(fill="x", padx=22, pady=(14, 18))
        tk.Button(footer, text="Batal", bg=t["surface"], fg=t["text"],
                  font=(FONT, 9), relief="flat", padx=12, pady=6, cursor="hand2",
                  command=self.destroy).pack(side="right", padx=(6, 0))
        tk.Button(footer, text="Simpan", bg=t["accent"], fg="white",
                  font=(FONT, 9, "bold"), relief="flat", padx=16, pady=6,
                  cursor="hand2", activebackground=t["accent_h"],
                  activeforeground="white", command=self._save).pack(side="right")

    def _save(self):
        self._on_save({
            "confidence_threshold": round(self._conf_var.get(), 2),
            "signature_width_inches": round(self._width_var.get(), 1),
            "auto_open_pdf": self._auto_var.get(),
        })
        self.destroy()

    def _center(self, master, w, h):
        self.update_idletasks()
        mx = master.winfo_rootx() + (master.winfo_width() - w) // 2
        my = master.winfo_rooty() + (master.winfo_height() - h) // 2
        self.geometry(f"{w}x{h}+{mx}+{my}")


# ─── Main App ─────────────────────────────────────────────────
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Word Signer")
        self.root.resizable(False, False)

        self._settings = load_settings()
        self._dark = self._settings.get("dark_mode", False)
        self.t = THEMES["dark" if self._dark else "light"]
        self.root.configure(bg=self.t["bg"])

        self._build()
        self._center(490, 370)

        # Load preset TTD
        preset = load_preset()
        if preset:
            self.sig_card.set_path(preset)

    # ── Build UI ─────────────────────────────────────────────
    def _build(self):
        t = self.t

        # Header
        header = tk.Frame(self.root, bg=t["bg"])
        header.pack(fill="x", padx=24, pady=(20, 0))

        tk.Label(header, text="Word Signer", bg=t["bg"], fg=t["text"],
                 font=(FONT, 16, "bold")).pack(side="left")

        self._settings_btn = tk.Button(
            header, text="⚙", bg=t["bg"], fg=t["subtext"],
            font=("Segoe UI Emoji", 13), relief="flat", bd=0,
            cursor="hand2", padx=4,
            activebackground=t["bg"], activeforeground=t["text"],
            command=self._open_settings)
        self._settings_btn.pack(side="right", padx=(4, 0))

        self._theme_btn = tk.Button(
            header, text="🌙" if not self._dark else "☀️",
            bg=t["bg"], fg=t["subtext"],
            font=("Segoe UI Emoji", 13), relief="flat", bd=0,
            cursor="hand2", padx=4,
            activebackground=t["bg"], activeforeground=t["text"],
            command=self._toggle_theme)
        self._theme_btn.pack(side="right")

        tk.Label(self.root,
                 text="Tambahkan tanda tangan ke dokumen Word, lalu ekspor ke PDF.",
                 bg=t["bg"], fg=t["subtext"], font=(FONT, 9)).pack(
            anchor="w", padx=24, pady=(4, 0))

        # Divider
        tk.Frame(self.root, bg=t["border"], height=1).pack(fill="x", pady=(14, 0))

        # Cards
        body = tk.Frame(self.root, bg=t["bg"])
        body.pack(fill="x", padx=24, pady=14)

        self.docx_card = FileCard(body, "Dokumen Word  (pilih satu atau lebih)",
                                  ["docx"], multi=True, app=self)
        self.docx_card.pack(fill="x", pady=(0, 8))

        self.sig_card = FileCard(body, "Tanda Tangan",
                                 ["png", "jpg", "jpeg", "svg"], multi=False, app=self)
        self.sig_card.pack(fill="x")

        # Override sig_card pick to also save preset
        orig_pick = self.sig_card._pick

        def _sig_pick_with_preset():
            orig_pick()
            path = self.sig_card.get()
            if path:
                save_preset(path)

        self.sig_card._pick = _sig_pick_with_preset
        self.sig_card.btn.config(command=_sig_pick_with_preset)

        # Divider
        tk.Frame(self.root, bg=t["border"], height=1).pack(fill="x")

        # Progress bar (hidden initially)
        self._pb_frame = tk.Frame(self.root, bg=t["bg"], height=4)
        self._pb_frame.pack(fill="x", padx=24)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Accent.Horizontal.TProgressbar",
                        troughcolor=t["surface"],
                        background=t["accent"],
                        bordercolor=t["bg"],
                        lightcolor=t["accent"],
                        darkcolor=t["accent"])

        self._progress = ttk.Progressbar(
            self._pb_frame, mode="indeterminate", length=442,
            style="Accent.Horizontal.TProgressbar")
        self._pb_visible = False

        # Footer
        footer = tk.Frame(self.root, bg=t["bg"])
        footer.pack(fill="x", padx=24, pady=12)

        self._status = tk.Label(footer, text="", bg=t["bg"], fg=t["subtext"],
                                font=(FONT, 9))
        self._status.pack(side="left", anchor="center")

        self._run_btn = tk.Button(
            footer, text="Buat PDF",
            bg=t["accent"], fg="white",
            font=(FONT, 10, "bold"), relief="flat", cursor="hand2",
            padx=20, pady=8,
            activebackground=t["accent_h"], activeforeground="white",
            command=self._run)
        self._run_btn.pack(side="right")

    # ── Helpers ───────────────────────────────────────────────
    def _set_status(self, msg, color=None):
        self._status.config(text=msg, fg=color or self.t["subtext"])
        self.root.update()

    def _show_progress(self, show: bool):
        if show and not self._pb_visible:
            self._progress.pack(pady=(4, 0))
            self._progress.start(10)
            self._pb_visible = True
        elif not show and self._pb_visible:
            self._progress.stop()
            self._progress.pack_forget()
            self._pb_visible = False

    # ── Run pipeline ──────────────────────────────────────────
    def _run(self):
        t = self.t
        docx_files = self.docx_card.get_all()
        sig = self.sig_card.get()

        if not docx_files:
            self._set_status("Pilih file Word dulu.", t["error"])
            return
        if not sig:
            self._set_status("Pilih file tanda tangan dulu.", t["error"])
            return

        self._run_btn.config(state="disabled")
        self._show_progress(True)
        success_outputs = []

        try:
            selected_indices = None  # cached zone selection for batch

            for i, docx in enumerate(docx_files):
                prefix = f"[{i+1}/{len(docx_files)}] " if len(docx_files) > 1 else ""

                self._set_status(f"{prefix}Mendeteksi zona tanda tangan...")
                zones = detect_signature_zones(
                    docx,
                    confidence_threshold=self._settings.get("confidence_threshold", 0.4)
                )

                if not zones:
                    raise ValueError(
                        f"Zona TTD tidak ditemukan: {os.path.basename(docx)}"
                    )

                # Show zone preview only for first file (apply same selection to batch)
                if selected_indices is None:
                    self._show_progress(False)
                    dlg = ZonePreviewDialog(self.root, zones, t)
                    self.root.wait_window(dlg)
                    self._show_progress(True)

                    if dlg.result is None:
                        self._set_status("Dibatalkan.", t["subtext"])
                        return

                    selected_indices = dlg.result
                    if not selected_indices:
                        self._set_status("Tidak ada zona yang dipilih.", t["subtext"])
                        return

                selected_zones = [zones[j] for j in selected_indices
                                  if j < len(zones)]

                self._set_status(
                    f"{prefix}Menyisipkan TTD di {len(selected_zones)} zona...")
                signed = inject_signature(
                    docx, sig, selected_zones,
                    width_inches=self._settings.get("signature_width_inches", 1.5)
                )

                self._set_status(f"{prefix}Mengkonversi ke PDF...")
                pdf = convert_to_pdf(signed)

                output = docx.replace(".docx", "_signed.pdf")
                with open(output, "wb") as f:
                    f.write(pdf)

                log_success(docx, output, len(selected_zones))
                success_outputs.append(output)

        except ValueError as e:
            self._set_status(str(e), t["error"])
            log_error(docx_files[0] if docx_files else "", str(e))
            messagebox.showerror("Gagal", str(e))

        except Exception as e:
            self._set_status("Terjadi kesalahan.", t["error"])
            log_error(docx_files[0] if docx_files else "", str(e))
            messagebox.showerror("Error", str(e))

        finally:
            self._show_progress(False)
            self._run_btn.config(state="normal")

        if success_outputs:
            if len(success_outputs) == 1:
                out = success_outputs[0]
                self._set_status(f"✓ Selesai — {os.path.basename(out)}", t["success"])
                messagebox.showinfo("Selesai", f"PDF berhasil dibuat!\n\n{out}")
                if self._settings.get("auto_open_pdf", True):
                    os.startfile(out)
            else:
                self._set_status(
                    f"✓ {len(success_outputs)} file berhasil diproses!", t["success"])
                messagebox.showinfo(
                    "Selesai", f"{len(success_outputs)} PDF berhasil dibuat!")

    # ── Settings ──────────────────────────────────────────────
    def _open_settings(self):
        def on_save(new_settings):
            self._settings.update(new_settings)
            save_settings(self._settings)
        SettingsDialog(self.root, self._settings, self.t, on_save)

    # ── Dark mode toggle ──────────────────────────────────────
    def _toggle_theme(self):
        # Save current file selections
        docx_paths = self.docx_card.get_all()
        sig_path = self.sig_card.get()

        # Flip theme
        self._dark = not self._dark
        self.t = THEMES["dark" if self._dark else "light"]
        self._settings["dark_mode"] = self._dark
        save_settings(self._settings)

        # Rebuild UI
        for w in self.root.winfo_children():
            w.destroy()
        self.root.configure(bg=self.t["bg"])
        self._build()

        # Restore file selections
        t = self.t
        if docx_paths:
            self.docx_card.file_paths = docx_paths
            n = len(docx_paths)
            display = f"{n} file dipilih" if n > 1 else os.path.basename(docx_paths[0])
            self.docx_card.name_label.config(text=display, fg=t["text"])
            self.docx_card.btn.config(text="Ganti file")
            self.docx_card.config(highlightbackground=t["accent"])

        if sig_path:
            self.sig_card.file_paths = [sig_path]
            self.sig_card.name_label.config(
                text=f"★ {os.path.basename(sig_path)}", fg=t["accent"])
            self.sig_card.btn.config(text="Ganti file")
            self.sig_card.config(highlightbackground=t["accent"])

    # ── Window centering ──────────────────────────────────────
    def _center(self, w, h):
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()