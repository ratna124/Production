"""
printer_utils.py
─────────────────
Utilities for sending labels to physical printers.

Supports:
  - CUPS (Linux/Mac) — most thermal printers via USB or network
  - ZPL (Zebra printers) — direct TCP/IP socket
  - Windows WinPrint — via win32print (Windows only)
  - Manual (save PNG and open system dialog)

Usage:
  from printer_utils import print_label, bulk_reprint
  print_label("HD01-20250412-A3B2")           # print single label
  bulk_reprint(date="2025-04-12", shift="Shift 1")  # reprint all from a shift
"""

import os
import sys
import socket
import sqlite3
import subprocess
import platform
import json
from pathlib import Path
from datetime import datetime

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DB_PATH    = os.path.join(BASE_DIR, "data", "production.db")
LABELS_DIR = os.path.join(BASE_DIR, "labels_output")

# ── CONFIGURATION ──────────────────────────────────────────────────────────────
# Set these to match your environment

PRINTER_TYPE = "cups"            # Options: "cups" | "zpl" | "windows" | "manual"
CUPS_PRINTER = "Thermal_Label"  # CUPS printer name (run: lpstat -p to list)
ZPL_HOST     = "192.168.1.100"  # Zebra printer IP address
ZPL_PORT     = 9100             # Zebra default raw print port

# ── CUPS PRINT (Linux/Mac) ──────────────────────────────────────────────────────
def print_cups(label_path: str, printer: str = CUPS_PRINTER) -> bool:
    """Send a PNG label to a CUPS printer (Linux/Mac)."""
    if not os.path.exists(label_path):
        print(f"  ✗ Label file not found: {label_path}")
        return False
    cmd = ["lp", "-d", printer, "-o", "fit-to-page", label_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"  ✓ Sent to CUPS printer '{printer}': {os.path.basename(label_path)}")
        return True
    else:
        print(f"  ✗ CUPS error: {result.stderr.strip()}")
        return False

# ── ZPL PRINT (Zebra printers via TCP/IP) ──────────────────────────────────────
def png_to_zpl(label_path: str) -> str:
    """
    Convert a PNG label to ZPL format for Zebra printers.
    Uses ^GF (Graphic Field) command.
    Requires: pip install pillow
    """
    from PIL import Image
    import math

    img = Image.open(label_path).convert("1")  # convert to 1-bit BW
    w, h = img.size
    bytes_per_row = math.ceil(w / 8)
    total_bytes   = bytes_per_row * h

    pixels = list(img.getdata())
    hex_data = ""
    for row in range(h):
        row_bytes = b""
        for col_byte in range(bytes_per_row):
            byte_val = 0
            for bit in range(8):
                px_idx = row * w + col_byte * 8 + bit
                if px_idx < len(pixels):
                    # In ZPL, 0 = black (print), 1 = white (no print)
                    if pixels[px_idx] == 0:
                        byte_val |= (0x80 >> bit)
            row_bytes += bytes([byte_val])
        hex_data += row_bytes.hex().upper()

    zpl = (
        "^XA\n"
        f"^FO0,0\n"
        f"^GFA,{total_bytes},{total_bytes},{bytes_per_row},{hex_data}\n"
        "^XZ\n"
    )
    return zpl

def print_zpl(label_path: str, host: str = ZPL_HOST, port: int = ZPL_PORT) -> bool:
    """Send a label to a Zebra printer via raw TCP socket."""
    try:
        zpl = png_to_zpl(label_path)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect((host, port))
            s.sendall(zpl.encode("utf-8"))
        print(f"  ✓ Sent to Zebra printer {host}:{port}: {os.path.basename(label_path)}")
        return True
    except Exception as e:
        print(f"  ✗ ZPL print error: {e}")
        return False

# ── WINDOWS PRINT ───────────────────────────────────────────────────────────────
def print_windows(label_path: str) -> bool:
    """Open Windows print dialog (ShellExecute)."""
    if platform.system() != "Windows":
        print("  ✗ Windows print only available on Windows")
        return False
    try:
        os.startfile(label_path, "print")
        print(f"  ✓ Sent to Windows print dialog: {os.path.basename(label_path)}")
        return True
    except Exception as e:
        print(f"  ✗ Windows print error: {e}")
        return False

# ── MANUAL / OPEN FILE ──────────────────────────────────────────────────────────
def print_manual(label_path: str) -> bool:
    """Open the label file with the system default viewer."""
    try:
        if platform.system() == "Windows":
            os.startfile(label_path)
        elif platform.system() == "Darwin":
            subprocess.run(["open", label_path])
        else:
            subprocess.run(["xdg-open", label_path])
        print(f"  ✓ Opened label file: {label_path}")
        return True
    except Exception as e:
        print(f"  ✗ Could not open file: {e}")
        return False

# ── UNIFIED PRINT FUNCTION ──────────────────────────────────────────────────────
def print_label(order_id: str, printer_type: str = PRINTER_TYPE) -> bool:
    """Print a label by order_id using the configured printer type."""
    label_path = os.path.join(LABELS_DIR, f"{order_id}.png")
    if not os.path.exists(label_path):
        print(f"  ✗ Label not found: {label_path}")
        return False

    if printer_type == "cups":
        return print_cups(label_path)
    elif printer_type == "zpl":
        return print_zpl(label_path)
    elif printer_type == "windows":
        return print_windows(label_path)
    else:
        return print_manual(label_path)

# ── BULK REPRINT ────────────────────────────────────────────────────────────────
def bulk_reprint(date: str = None, shift: str = None, divisi: str = None,
                 dry_run: bool = False) -> int:
    """
    Reprint labels from the database by filter.
    Args:
        date:    YYYY-MM-DD — filter by date (defaults to today)
        shift:   e.g. "Shift 1" — filter by shift
        divisi:  e.g. "HDPE Kantong" — filter by division
        dry_run: if True, only list what would be printed

    Returns:
        Number of labels printed (or would be printed in dry_run)
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    query = "SELECT order_id, tanggal, shift, divisi, produk FROM production_output WHERE 1=1"
    params = []
    if date:
        query += " AND tanggal = ?"; params.append(date)
    if shift:
        query += " AND shift LIKE ?"; params.append(f"%{shift}%")
    if divisi:
        query += " AND divisi = ?"; params.append(divisi)
    query += " ORDER BY created_at ASC"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    print(f"\n{'='*50}")
    print(f"  Bulk Reprint — {date or 'all dates'}")
    if shift:  print(f"  Shift:  {shift}")
    if divisi: print(f"  Divisi: {divisi}")
    print(f"  Found {len(rows)} orders to {'preview' if dry_run else 'print'}")
    print(f"{'='*50}\n")

    count = 0
    for r in rows:
        label_path = os.path.join(LABELS_DIR, f"{r['order_id']}.png")
        exists = os.path.exists(label_path)
        status = "✓" if exists else "✗ (file missing)"
        print(f"  {r['order_id']} | {r['shift'][:7]} | {r['produk'][:25]:<25} {status}")
        if not dry_run and exists:
            print_label(r["order_id"])
        count += 1

    print(f"\n  {'Would print' if dry_run else 'Printed'}: {count} label(s)\n")
    return count

# ── LIST CUPS PRINTERS ──────────────────────────────────────────────────────────
def list_printers():
    """List available CUPS printers on this machine."""
    result = subprocess.run(["lpstat", "-p"], capture_output=True, text=True)
    if result.returncode == 0:
        print("Available CUPS printers:\n" + result.stdout)
    else:
        print("Could not list printers (is CUPS installed?)")

# ── CLI ENTRY POINT ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Label Printer Utility")
    parser.add_argument("--print",    metavar="ORDER_ID", help="Print a single label by order ID")
    parser.add_argument("--reprint",  action="store_true", help="Bulk reprint mode")
    parser.add_argument("--date",     default=None, help="Date filter YYYY-MM-DD (default: today)")
    parser.add_argument("--shift",    default=None, help="Shift filter e.g. 'Shift 1'")
    parser.add_argument("--divisi",   default=None, help="Division filter")
    parser.add_argument("--dry-run",  action="store_true", help="Preview without printing")
    parser.add_argument("--list",     action="store_true", help="List available printers")
    args = parser.parse_args()

    if args.list:
        list_printers()
    elif args.print:
        print_label(args.print)
    elif args.reprint:
        bulk_reprint(date=args.date, shift=args.shift, divisi=args.divisi, dry_run=args.dry_run)
    else:
        parser.print_help()
