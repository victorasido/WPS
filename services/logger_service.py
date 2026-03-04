# logger_service.py
# Log history operasi TTD ke AppData\WordSigner\history.log

import os
from datetime import datetime

APP_DIR = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "WordSigner")
LOG_FILE = os.path.join(APP_DIR, "history.log")


def log_success(input_path: str, output_path: str, zone_count: int):
    _log(f"OK  | input: {os.path.basename(input_path):<40} | "
         f"output: {os.path.basename(output_path):<45} | zones: {zone_count}")


def log_error(input_path: str, error: str):
    brief = str(error)[:120]
    _log(f"ERR | input: {os.path.basename(input_path):<40} | error: {brief}")


def _log(message: str):
    os.makedirs(APP_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {message}\n")
