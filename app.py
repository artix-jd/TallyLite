import os
import re
import ast
import math
import sys
import csv
import json
import ctypes
import shutil
import sqlite3
import calendar
import webbrowser
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import customtkinter as ctk

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

if sys.platform == "win32":
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TallyLite.Desktop")
    except Exception:
        pass

ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")

# Resource files (icon/docs) are read from the app bundle or source folder.
if getattr(sys, "frozen", False):
    RESOURCE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
else:
    RESOURCE_DIR = os.path.dirname(os.path.abspath(__file__))

# User data belongs in a writable per-user location, never beside the EXE.
LOCAL_APP_DATA = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
DATA_DIR = os.path.join(LOCAL_APP_DATA, "TallyLite")
BOOKS_DIR = os.path.join(DATA_DIR, "books")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
EXPORT_DIR = os.path.join(DATA_DIR, "exports")
README_PATH = os.path.join(RESOURCE_DIR, "README.md")
CHANGELOG_PATH = os.path.join(RESOURCE_DIR, "CHANGELOG.md")
ICON_PATH = os.path.join(RESOURCE_DIR, "ac_logo.ico")
REGISTRY_JSON = os.path.join(BOOKS_DIR, "books_registry.json")

os.makedirs(BOOKS_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs(EXPORT_DIR, exist_ok=True)

CREATE_NEW_OPTION = "➕ Create New Ledger..."

LEDGER_GROUPS = [
    "Bank Account",
    "Cash in Hand",
    "Expense",
    "Income",
    "Party / Person (Customer / Vendor)",
    "Due / Pay Later (Payable)",
    "Money to Receive (Receivable)",
    "Fixed Asset / Property"
]

GROUP_DESCRIPTIONS = {
    "Bank Account": "Savings, Current, or UPI Bank Accounts (Shown on Balance Sheet under Assets).",
    "Cash in Hand": "Physical Cash wallet or home cash box (Shown on Balance Sheet under Assets).",
    "Expense": "Daily household or business expenses (Shown on Profit & Loss A/c).",
    "Income": "Salary, Business Sales, or revenue earned (Shown on Profit & Loss A/c).",
    "Party / Person (Customer / Vendor)": "Vendor or partner (e.g. Kapil, AK). Automatically tracks To Pay / To Receive.",
    "Due / Pay Later (Payable)": "Credit cards, unpaid bills, or loans to pay back.",
    "Money to Receive (Receivable)": "Advances or money others have to return to you.",
    "Fixed Asset / Property": "Long-term items bought — e.g. Laptop, Phone, Equipment."
}

ANALYTICS_PERIODS = [
    "FY 2026-27",
    "All Time",
    "Last 7 Days",
    "This Week",
    "This Month",
    "Last 3 Months",
    "Oct 2026",
    "Nov 2026",
    "Dec 2026",
    "Custom Date Range"
]



def safe_numeric_eval(expression: str) -> float:
    """Evaluate simple arithmetic only; never execute Python code from an input field."""
    node = ast.parse(str(expression).strip(), mode="eval")

    def visit(n):
        if isinstance(n, ast.Expression):
            return visit(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return float(n.value)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd, ast.USub)):
            value = visit(n.operand)
            return value if isinstance(n.op, ast.UAdd) else -value
        if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)):
            left, right = visit(n.left), visit(n.right)
            if isinstance(n.op, ast.Add): result = left + right
            elif isinstance(n.op, ast.Sub): result = left - right
            elif isinstance(n.op, ast.Mult): result = left * right
            elif isinstance(n.op, ast.Div): result = left / right
            elif isinstance(n.op, ast.FloorDiv): result = left // right
            elif isinstance(n.op, ast.Mod): result = left % right
            else:
                if abs(right) > 10 or abs(left) > 1e12:
                    raise ValueError("Exponent or value too large")
                result = left ** right
            if not math.isfinite(result) or abs(result) > 1e15:
                raise ValueError("Result out of range")
            return result
        raise ValueError("Only basic arithmetic is allowed")

    return float(visit(node))


def sanitize_narration(text: str) -> str:
    if not text:
        return ""
    cleaned = "".join(
        ch for ch in text
        if ch.isprintable() and not (0x1F000 <= ord(ch) <= 0x1FAFF) and not (0x2600 <= ord(ch) <= 0x27BF)
    )
    return " ".join(cleaned.strip().split())


def generate_ac_icon(ico_path: str):
    if not HAS_PIL or os.path.exists(ico_path):
        return
    try:
        img = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle((8, 8, 120, 120), radius=24, fill=(15, 23, 42, 255), outline=(37, 99, 235, 255), width=6)
        draw.rectangle((18, 86, 110, 96), fill=(16, 185, 129, 255))
        try:
            font = ImageFont.truetype("arialbd.ttf", 44)
        except Exception:
            font = ImageFont.load_default()
        draw.text((22, 26), "A/C", fill=(255, 255, 255, 255), font=font)
        img.save(ico_path, format="ICO", sizes=[(64, 64), (32, 32), (16, 16)])
    except Exception:
        pass


def resolve_period_dates(period_label: str, custom_from: str = "", custom_to: str = ""):
    today = datetime.now().date()
    if not period_label or period_label == "All Time":
        return None, None
    if period_label == "Last 7 Days":
        start = today - timedelta(days=6)
        return start.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
    if period_label == "This Week":
        start = today - timedelta(days=today.weekday())
        return start.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
    if period_label == "This Month":
        start = today.replace(day=1)
        last_day = calendar.monthrange(today.year, today.month)[1]
        end = today.replace(day=last_day)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    if period_label == "Last 3 Months":
        start = today - timedelta(days=90)
        return start.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
    if period_label in ("Oct 2026", "Nov 2026", "Dec 2026"):
        dt = datetime.strptime(period_label, "%b %Y")
        last_d = calendar.monthrange(dt.year, dt.month)[1]
        return f"{dt.year:04d}-{dt.month:02d}-01", f"{dt.year:04d}-{dt.month:02d}-{last_d:02d}"
    if period_label == "Custom Date Range":
        s = custom_from.strip() if custom_from.strip() else "2000-01-01"
        e = custom_to.strip() if custom_to.strip() else "2099-12-31"
        return s, e
    if period_label.startswith("FY "):
        try:
            start_yr = int(period_label.replace("FY", "").strip().split("-")[0])
            return f"{start_yr}-04-01", f"{start_yr + 1}-03-31"
        except Exception:
            return None, None
    return None, None


class BookDatabaseV652a:
    def __init__(self):
        self.conn = None
        self.cursor = None
        self.active_book_name = ""
        self.active_db_path = ""
        self.active_fy = "FY 2026-27"
        self._load_or_init_registry()

    def _safe_filename(self, book_name: str) -> str:
        slug = re.sub(r'[^a-zA-Z0-9_\-]', '_', book_name.strip())
        slug = re.sub(r'_+', '_', slug).strip('_')
        return f"{slug or 'Book'}.db"

    def _load_or_init_registry(self):
        if not os.path.exists(REGISTRY_JSON):
            self.registry = {"active_book": "", "books": []}
            self._save_registry()
        else:
            try:
                with open(REGISTRY_JSON, "r", encoding="utf-8") as f:
                    self.registry = json.load(f)
            except Exception:
                self.registry = {"active_book": "", "books": []}

        valid_books = []
        for b in self.registry.get("books", []):
            p = os.path.join(BOOKS_DIR, b["file"])
            if os.path.exists(p):
                valid_books.append(b)
        self.registry["books"] = valid_books

        if not self.registry["books"]:
            self.create_or_switch_company("My First Book", "FY 2026-27")
        else:
            act_name = self.registry.get("active_book", "")
            found = next((b for b in self.registry["books"] if b["name"].lower() == act_name.lower()), self.registry["books"][0])
            self.open_book_file(found["name"], found.get("fy", "FY 2026-27"))

    def _save_registry(self):
        with open(REGISTRY_JSON, "w", encoding="utf-8") as f:
            json.dump(self.registry, f, indent=2)

    def clean_name(self, name: str) -> str:
        if not name:
            return ""
        cleaned = " ".join(name.strip().split())
        words = []
        for w in cleaned.split(" "):
            if len(w) <= 3 and w.isupper():
                words.append(w)
            else:
                words.append(w.capitalize())
        return " ".join(words)

    def normalize_group(self, grp: str, name: str = "") -> str:
        if grp in LEDGER_GROUPS:
            return grp
        g_low = (grp or "").lower()
        if "bank" in g_low:
            return "Bank Account"
        if "cash" in g_low:
            return "Cash in Hand"
        if "asset" in g_low or "property" in g_low or "equip" in g_low:
            return "Fixed Asset / Property"
        if "party" in g_low or "person" in g_low or "vendor" in g_low:
            return "Party / Person (Customer / Vendor)"
        if "income" in g_low:
            return "Income"
        if "expense" in g_low:
            return "Expense"
        if "receive" in g_low or "debtor" in g_low:
            return "Money to Receive (Receivable)"
        if "due" in g_low or "pay" in g_low or "creditor" in g_low:
            return "Due / Pay Later (Payable)"
        return "Expense"

    def open_book_file(self, book_name: str, fy: str = "FY 2026-27"):
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass

        c_name = book_name.strip()
        existing = next((b for b in self.registry["books"] if b["name"].lower() == c_name.lower()), None)
        if existing:
            fname = existing["file"]
            existing["fy"] = fy
            c_name = existing["name"]
        else:
            fname = self._safe_filename(c_name)
            counter = 1
            while os.path.exists(os.path.join(BOOKS_DIR, fname)):
                fname = f"{self._safe_filename(c_name)[:-3]}_{counter}.db"
                counter += 1
            self.registry["books"].append({"name": c_name, "file": fname, "fy": fy})

        self.registry["active_book"] = c_name
        self._save_registry()

        self.active_book_name = c_name
        self.active_fy = fy
        self.active_db_path = os.path.join(BOOKS_DIR, fname)

        self.conn = sqlite3.connect(self.active_db_path)
        self.cursor = self.conn.cursor()
        self.cursor.execute("PRAGMA synchronous = NORMAL")
        self.cursor.execute("PRAGMA temp_store = MEMORY")
        self._init_single_book_schema()

    def _init_single_book_schema(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS ledgers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL COLLATE NOCASE,
                ledger_group TEXT NOT NULL,
                opening_balance REAL DEFAULT 0.0,
                show_on_top INTEGER DEFAULT 0,
                notes TEXT DEFAULT ''
            )
        """)
        self.cursor.execute("SELECT COUNT(*) FROM ledgers")
        if self.cursor.fetchone()[0] == 0:
            self.cursor.execute("""
                INSERT INTO ledgers (name, ledger_group, opening_balance, show_on_top)
                VALUES ('Cash', 'Cash in Hand', 0.0, 1)
            """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_date TEXT NOT NULL,
                tx_type TEXT NOT NULL,
                category TEXT NOT NULL,
                account TEXT NOT NULL,
                to_account TEXT DEFAULT '',
                description TEXT,
                amount REAL NOT NULL,
                dr_ledger TEXT DEFAULT '',
                cr_ledger TEXT DEFAULT '',
                voucher_group_id INTEGER DEFAULT 0
            )
        """)
        self.cursor.execute("PRAGMA table_info(transactions)")
        cols = [c[1] for c in self.cursor.fetchall()]
        if "voucher_group_id" not in cols:
            self.cursor.execute("ALTER TABLE transactions ADD COLUMN voucher_group_id INTEGER DEFAULT 0")

        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(tx_date)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_dr_ledger ON transactions(dr_ledger COLLATE NOCASE)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_cr_ledger ON transactions(cr_ledger COLLATE NOCASE)")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_vch_grp ON transactions(voucher_group_id)")
        self.conn.commit()

    def get_active_company(self):
        return {"id": 1, "name": self.active_book_name, "fy": self.active_fy, "db_path": self.active_db_path}

    def get_all_companies_with_counts(self):
        results = []
        for idx, b in enumerate(self.registry.get("books", []), start=1):
            p = os.path.join(BOOKS_DIR, b["file"])
            l_cnt, t_cnt = 0, 0
            if os.path.exists(p):
                try:
                    tmp_c = sqlite3.connect(p)
                    cur = tmp_c.cursor()
                    cur.execute("SELECT COUNT(*) FROM ledgers")
                    l_cnt = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(*) FROM transactions")
                    t_cnt = cur.fetchone()[0]
                    tmp_c.close()
                except Exception:
                    pass
            is_act = (b["name"].lower() == self.active_book_name.lower())
            results.append((idx, b["name"], b.get("fy", "FY 2026-27"), is_act, l_cnt, t_cnt, b["file"]))
        return results

    def create_or_switch_company(self, name: str, fy: str = "FY 2026-27"):
        self.open_book_file(name, fy)

    def delete_company_by_name(self, book_name: str):
        if len(self.registry["books"]) <= 1:
            return False, "Cannot delete the only Book. Create a new Book first, then delete this one."
        target = next((b for b in self.registry["books"] if b["name"].lower() == book_name.lower()), None)
        if not target:
            return False, "Book not found."

        db_file_path = os.path.join(BOOKS_DIR, target["file"])
        if self.active_book_name.lower() == book_name.lower() and self.conn:
            self.conn.close()
            self.conn = None

        if os.path.exists(db_file_path):
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.move(db_file_path, os.path.join(BACKUP_DIR, f"deleted_book_{target['file']}_{ts}.db"))

        self.registry["books"] = [b for b in self.registry["books"] if b["name"].lower() != book_name.lower()]
        self._save_registry()

        next_book = self.registry["books"][0]
        self.open_book_file(next_book["name"], next_book.get("fy", "FY 2026-27"))
        return True, f"Book '{book_name}' removed and archived to backups."

    def ledger_exists(self, name: str) -> bool:
        if not name or name == CREATE_NEW_OPTION:
            return False
        self.cursor.execute("SELECT 1 FROM ledgers WHERE name=? COLLATE NOCASE", (name.strip(),))
        return self.cursor.fetchone() is not None

    def get_canonical_name(self, name: str) -> str:
        self.cursor.execute("SELECT name FROM ledgers WHERE name=? COLLATE NOCASE", (name.strip(),))
        row = self.cursor.fetchone()
        return row[0] if row else self.clean_name(name)

    def save_ledger(self, name: str, group: str, opening_bal: float = 0.0, show_on_top: int = None, notes: str = ""):
        c_name = self.clean_name(name)
        c_grp = self.normalize_group(group, c_name)
        if show_on_top is None:
            show_on_top = 1 if c_grp in ("Bank Account", "Cash in Hand") else 0
        if c_grp not in ("Bank Account", "Cash in Hand"):
            show_on_top = 0

        self.cursor.execute("""
            INSERT INTO ledgers (name, ledger_group, opening_balance, show_on_top, notes)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                ledger_group=excluded.ledger_group,
                opening_balance=excluded.opening_balance,
                show_on_top=excluded.show_on_top,
                notes=excluded.notes
        """, (c_name, c_grp, opening_bal, show_on_top, notes))
        self.conn.commit()
        return c_name

    def delete_ledger(self, name: str):
        self.cursor.execute("""
            SELECT COUNT(*) FROM transactions
            WHERE category=? COLLATE NOCASE OR account=? COLLATE NOCASE OR to_account=? COLLATE NOCASE
        """, (name, name, name))
        cnt = self.cursor.fetchone()[0]
        if cnt > 0:
            return False, f"Cannot delete '{name}' because it has {cnt} transactions in this Book."
        self.cursor.execute("DELETE FROM ledgers WHERE name=? COLLATE NOCASE", (name,))
        self.conn.commit()
        return True, f"Ledger '{name}' deleted."

    def set_ledger_pin(self, name: str, pin: int):
        self.cursor.execute("UPDATE ledgers SET show_on_top=? WHERE name=? COLLATE NOCASE", (pin, name))
        self.conn.commit()

    def get_ledgers_by_groups(self, groups: list) -> list:
        placeholders = ",".join(["?"] * len(groups))
        self.cursor.execute(
            f"SELECT name FROM ledgers WHERE ledger_group IN ({placeholders}) ORDER BY name COLLATE NOCASE",
            list(groups)
        )
        return [r[0] for r in self.cursor.fetchall()]

    def get_all_ledgers_metadata(self):
        self.cursor.execute("""
            SELECT name, ledger_group, opening_balance, show_on_top, notes
            FROM ledgers ORDER BY ledger_group, name COLLATE NOCASE
        """)
        return self.cursor.fetchall()

    def _compute_dr_cr(self, tx_type: str, category: str, account: str, to_account: str):
        if tx_type == "Expense":
            return category, account
        elif tx_type == "Income":
            return account, category
        else:
            return to_account, account

    def _next_voucher_group_id(self) -> int:
        self.cursor.execute("SELECT COALESCE(MAX(voucher_group_id), 0) + 1 FROM transactions")
        return self.cursor.fetchone()[0]

    def add_transaction(self, tx_date, tx_type, category, account, to_account, description, amount, voucher_group_id=0):
        acc_c = self.get_canonical_name(account)
        to_c = self.get_canonical_name(to_account) if tx_type == "Transfer" else ""
        cat_c = "Contra Transfer" if tx_type == "Transfer" else self.get_canonical_name(category)
        dr, cr = self._compute_dr_cr(tx_type, cat_c, acc_c, to_c)
        clean_desc = sanitize_narration(description)

        self.cursor.execute("""
            INSERT INTO transactions
            (tx_date, tx_type, category, account, to_account, description, amount, dr_ledger, cr_ledger, voucher_group_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (tx_date, tx_type, cat_c, acc_c, to_c, clean_desc, amount, dr, cr, voucher_group_id))
        self.conn.commit()

    def save_compound_split_voucher(self, tx_date, tx_type, main_ledger, split_lines, split_target="category", existing_group_id=0):
        grp_id = existing_group_id if existing_group_id > 0 else self._next_voucher_group_id()
        if existing_group_id > 0:
            self.cursor.execute("DELETE FROM transactions WHERE voucher_group_id=?", (existing_group_id,))

        main_c = self.get_canonical_name(main_ledger)
        for line_ledger, amt, line_note in split_lines:
            line_c = self.get_canonical_name(line_ledger)
            clean_note = sanitize_narration(line_note)
            if split_target == "account":
                cat_c = main_c
                acc_c = line_c
            else:
                cat_c = line_c
                acc_c = main_c
            dr, cr = self._compute_dr_cr(tx_type, cat_c, acc_c, "")
            self.cursor.execute("""
                INSERT INTO transactions
                (tx_date, tx_type, category, account, to_account, description, amount, dr_ledger, cr_ledger, voucher_group_id)
                VALUES (?, ?, ?, ?, '', ?, ?, ?, ?, ?)
            """, (tx_date, tx_type, cat_c, acc_c, clean_note, amt, dr, cr, grp_id))
        self.conn.commit()
        return grp_id

    def get_split_group_rows(self, voucher_group_id: int):
        self.cursor.execute("""
            SELECT id, tx_date, tx_type, category, account, description, amount
            FROM transactions WHERE voucher_group_id=? ORDER BY id ASC
        """, (voucher_group_id,))
        return self.cursor.fetchall()

    def update_transaction(self, tx_id, tx_date, tx_type, category, account, to_account, description, amount):
        acc_c = self.get_canonical_name(account)
        to_c = self.get_canonical_name(to_account) if tx_type == "Transfer" else ""
        cat_c = "Contra Transfer" if tx_type == "Transfer" else self.get_canonical_name(category)
        dr, cr = self._compute_dr_cr(tx_type, cat_c, acc_c, to_c)
        clean_desc = sanitize_narration(description)

        self.cursor.execute("""
            UPDATE transactions SET
                tx_date=?, tx_type=?, category=?, account=?, to_account=?,
                description=?, amount=?, dr_ledger=?, cr_ledger=?, voucher_group_id=0
            WHERE id=?
        """, (tx_date, tx_type, cat_c, acc_c, to_c, clean_desc, amount, dr, cr, tx_id))
        self.conn.commit()

    def delete_transaction(self, tx_id: int):
        self.cursor.execute("DELETE FROM transactions WHERE id=?", (int(tx_id),))
        self.conn.commit()

    def delete_voucher_group(self, voucher_group_id: int):
        self.cursor.execute("DELETE FROM transactions WHERE voucher_group_id=?", (int(voucher_group_id),))
        self.conn.commit()

    def _build_date_filter_sql(self, period_label="FY 2026-27", custom_from="", custom_to=""):
        start_d, end_d = resolve_period_dates(period_label, custom_from, custom_to)
        if start_d and end_d:
            return " AND tx_date >= ? AND tx_date <= ?", [start_d, end_d]
        return "", []

    def get_transactions(self, search_query="", account_filter="All", category_filter="All", type_filter="All", period_label="FY 2026-27", custom_from="", custom_to=""):
        query = """
            SELECT id, tx_date, tx_type, category, account, to_account, description, amount, dr_ledger, cr_ledger, COALESCE(voucher_group_id, 0)
            FROM transactions WHERE 1=1
        """
        params = []
        d_sql, d_params = self._build_date_filter_sql(period_label, custom_from, custom_to)
        query += d_sql
        params.extend(d_params)

        if search_query:
            query += " AND (description LIKE ? OR category LIKE ? OR account LIKE ? OR to_account LIKE ? OR tx_date LIKE ?)"
            params.extend([f"%{search_query}%"] * 5)
        if account_filter != "All":
            query += " AND (account = ? COLLATE NOCASE OR to_account = ? COLLATE NOCASE)"
            params.extend([account_filter, account_filter])
        if category_filter != "All":
            query += " AND category = ? COLLATE NOCASE"
            params.append(category_filter)
        if type_filter != "All":
            query += " AND tx_type = ? COLLATE NOCASE"
            params.append(type_filter)

        query += " ORDER BY tx_date DESC, id DESC"
        self.cursor.execute(query, params)
        return self.cursor.fetchall()

    def _is_debit_normal_group(self, grp: str) -> bool:
        return grp in (
            "Bank Account",
            "Cash in Hand",
            "Expense",
            "Money to Receive (Receivable)",
            "Party / Person (Customer / Vendor)",
            "Fixed Asset / Property"
        )

    def _format_balance_tag(self, grp: str, running_bal: float, net_dr_minus_cr: float):
        if abs(running_bal) < 0.005:
            return "Settled", "₹0.00"
        if grp in ("Party / Person (Customer / Vendor)", "Money to Receive (Receivable)", "Due / Pay Later (Payable)"):
            tag = "To Receive" if net_dr_minus_cr > 0 else "To Pay"
            return tag, f"₹{abs(net_dr_minus_cr):,.2f} ({tag})"
        if grp in ("Bank Account", "Cash in Hand"):
            tag = "Available" if running_bal > 0 else "Overdrawn"
            return tag, f"₹{abs(running_bal):,.2f} ({tag})"
        if grp == "Fixed Asset / Property":
            tag = "Asset Value" if running_bal > 0 else "Credit Bal"
            return tag, f"₹{abs(running_bal):,.2f} ({tag})"
        if grp == "Expense":
            tag = "Spent" if running_bal > 0 else "Recovered"
            return tag, f"₹{abs(running_bal):,.2f} ({tag})"
        tag = "Received" if running_bal > 0 else "Paid Out"
        return tag, f"₹{abs(running_bal):,.2f} ({tag})"

    def get_all_ledgers_summary(self, period_label="FY 2026-27", custom_from="", custom_to="", group_filter="All", search_query=""):
        d_sql, d_params = self._build_date_filter_sql(period_label, custom_from, custom_to)

        self.cursor.execute("SELECT name, ledger_group, opening_balance, show_on_top FROM ledgers ORDER BY ledger_group, name COLLATE NOCASE")
        ledgers = self.cursor.fetchall()

        dr_map = {}
        self.cursor.execute(f"SELECT lower(dr_ledger), SUM(amount), COUNT(*) FROM transactions WHERE 1=1 {d_sql} GROUP BY lower(dr_ledger)", d_params)
        for l_key, s_amt, cnt in self.cursor.fetchall():
            if l_key:
                dr_map[l_key] = (s_amt or 0.0, cnt or 0)

        cr_map = {}
        self.cursor.execute(f"SELECT lower(cr_ledger), SUM(amount), COUNT(*) FROM transactions WHERE 1=1 {d_sql} GROUP BY lower(cr_ledger)", d_params)
        for l_key, s_amt, cnt in self.cursor.fetchall():
            if l_key:
                cr_map[l_key] = (s_amt or 0.0, cnt or 0)

        out = []
        for name, grp, op_bal, pin in ledgers:
            if group_filter != "All" and grp != group_filter:
                continue
            if search_query and search_query.lower() not in name.lower() and search_query.lower() not in grp.lower():
                continue

            k = name.lower()
            tot_dr, cnt_dr = dr_map.get(k, (0.0, 0))
            tot_cr, cnt_cr = cr_map.get(k, (0.0, 0))
            tx_count = cnt_dr + cnt_cr

            if self._is_debit_normal_group(grp):
                running_bal = op_bal + tot_dr - tot_cr
                net_dr_minus_cr = running_bal
            else:
                running_bal = op_bal + tot_cr - tot_dr
                net_dr_minus_cr = tot_dr - (op_bal + tot_cr)

            tag, fmt_bal = self._format_balance_tag(grp, running_bal, net_dr_minus_cr)
            out.append({
                "name": name,
                "group": grp,
                "tx_count": tx_count,
                "opening": op_bal,
                "total_dr": tot_dr,
                "total_cr": tot_cr,
                "raw_closing": running_bal,
                "net_dr_minus_cr": net_dr_minus_cr,
                "formatted_closing": fmt_bal,
                "dr_cr_tag": tag,
                "pinned": pin
            })
        return out

    def get_financial_statements(self, period_label="FY 2026-27", custom_from="", custom_to=""):
        summaries = self.get_all_ledgers_summary(period_label, custom_from, custom_to)
        trial_balance = []
        tb_total_dr = 0.0
        tb_total_cr = 0.0

        pnl_expenses = []
        pnl_incomes = []
        total_pnl_exp = 0.0
        total_pnl_inc = 0.0

        bs_assets = []
        bs_liabilities = []
        total_assets = 0.0
        total_liabilities = 0.0
        opening_capital_diff = 0.0

        for s in summaries:
            name = s["name"]
            grp = s["group"]
            net_dc = s["net_dr_minus_cr"]

            if self._is_debit_normal_group(grp):
                opening_capital_diff += s["opening"]
            else:
                opening_capital_diff -= s["opening"]

            if abs(net_dc) > 0.005 or s["tx_count"] > 0:
                dr_col = net_dc if net_dc > 0 else 0.0
                cr_col = abs(net_dc) if net_dc < 0 else 0.0
                tb_total_dr += dr_col
                tb_total_cr += cr_col
                trial_balance.append({
                    "name": name,
                    "group": grp,
                    "opening": s["opening"],
                    "period_dr": s["total_dr"],
                    "period_cr": s["total_cr"],
                    "closing_dr": dr_col,
                    "closing_cr": cr_col
                })

            if grp == "Expense" and abs(net_dc) > 0.005:
                amt = net_dc
                pnl_expenses.append((name, amt))
                total_pnl_exp += amt
            elif grp == "Income" and abs(net_dc) > 0.005:
                amt = -net_dc
                pnl_incomes.append((name, amt))
                total_pnl_inc += amt
            elif grp in ("Bank Account", "Cash in Hand", "Fixed Asset / Property", "Money to Receive (Receivable)", "Party / Person (Customer / Vendor)", "Due / Pay Later (Payable)"):
                if abs(net_dc) > 0.005:
                    if net_dc > 0:
                        bs_assets.append((name, grp, net_dc))
                        total_assets += net_dc
                    else:
                        bs_liabilities.append((name, grp, abs(net_dc)))
                        total_liabilities += abs(net_dc)

        net_profit = total_pnl_inc - total_pnl_exp
        capital_plus_surplus = opening_capital_diff + net_profit
        total_liabilities_and_equity = total_liabilities + capital_plus_surplus

        return {
            "trial_balance": trial_balance,
            "tb_total_dr": tb_total_dr,
            "tb_total_cr": tb_total_cr,
            "pnl_expenses": sorted(pnl_expenses, key=lambda x: x[1], reverse=True),
            "pnl_incomes": sorted(pnl_incomes, key=lambda x: x[1], reverse=True),
            "total_pnl_exp": total_pnl_exp,
            "total_pnl_inc": total_pnl_inc,
            "net_profit": net_profit,
            "bs_assets": bs_assets,
            "bs_liabilities": bs_liabilities,
            "opening_capital": opening_capital_diff,
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "total_liabilities_and_equity": total_liabilities_and_equity
        }

    def get_quick_ledger_balance_text(self, ledger_name: str, period_label="FY 2026-27", custom_from="", custom_to="") -> str:
        if not ledger_name or not self.ledger_exists(ledger_name):
            return ""
        self.cursor.execute("SELECT name, ledger_group, opening_balance FROM ledgers WHERE name=? COLLATE NOCASE", (ledger_name.strip(),))
        row = self.cursor.fetchone()
        if not row:
            return ""
        c_name, grp, op_bal = row
        d_sql, d_params = self._build_date_filter_sql(period_label, custom_from, custom_to)
        self.cursor.execute(f"SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE dr_ledger=? COLLATE NOCASE {d_sql}", [c_name] + d_params)
        tot_dr = self.cursor.fetchone()[0]
        self.cursor.execute(f"SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE cr_ledger=? COLLATE NOCASE {d_sql}", [c_name] + d_params)
        tot_cr = self.cursor.fetchone()[0]

        if self._is_debit_normal_group(grp):
            running_bal = op_bal + tot_dr - tot_cr
            net_dr_minus_cr = running_bal
        else:
            running_bal = op_bal + tot_cr - tot_dr
            net_dr_minus_cr = tot_dr - (op_bal + tot_cr)

        _, fmt_bal = self._format_balance_tag(grp, running_bal, net_dr_minus_cr)
        return f"Cur Bal ({c_name}): {fmt_bal}"

    def get_dashboard_data(self, period_label="FY 2026-27", custom_from="", custom_to=""):
        all_summaries = self.get_all_ledgers_summary(period_label, custom_from, custom_to)
        bank_map = {}
        total_liquid = 0.0
        receivables = []
        payables = []

        for s in all_summaries:
            grp = s["group"]
            if grp in ("Bank Account", "Cash in Hand"):
                op = s["opening"]
                inc = (op if op > 0 else 0.0) + s["total_dr"]
                out = (abs(op) if op < 0 else 0.0) + s["total_cr"]
                bal = inc - out
                bank_map[s["name"]] = {
                    "group": grp, "opening": op, "in": inc, "out": out, "bal": bal, "pinned": bool(s["pinned"])
                }
                total_liquid += bal
            elif grp in ("Party / Person (Customer / Vendor)", "Money to Receive (Receivable)", "Due / Pay Later (Payable)"):
                net_val = s["net_dr_minus_cr"]
                if net_val > 0.005:
                    receivables.append({**s, "net_amt": net_val})
                elif net_val < -0.005:
                    payables.append({**s, "net_amt": abs(net_val)})

        d_sql, d_params = self._build_date_filter_sql(period_label, custom_from, custom_to)
        self.cursor.execute(f"""
            SELECT
                COALESCE(SUM(CASE WHEN tx_type='Income' THEN amount ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN tx_type='Expense' THEN amount ELSE 0 END), 0)
            FROM transactions WHERE 1=1 {d_sql}
        """, d_params)
        total_in, total_out = self.cursor.fetchone()

        self.cursor.execute(f"""
            SELECT category, SUM(amount) as exp_sum
            FROM transactions
            WHERE tx_type='Expense' {d_sql}
            GROUP BY category COLLATE NOCASE
            ORDER BY exp_sum DESC
        """, d_params)
        top_expenses = self.cursor.fetchall()

        return {
            "total_in": total_in,
            "total_out": total_out,
            "net_flow": total_in - total_out,
            "total_liquid": total_liquid,
            "bank_cash": bank_map,
            "receivables": receivables,
            "payables": payables,
            "top_expenses": top_expenses,
            "all_summaries": all_summaries
        }

    def get_category_breakdown(self, period_label="FY 2026-27", custom_from="", custom_to=""):
        d_sql, d_params = self._build_date_filter_sql(period_label, custom_from, custom_to)
        query = f"""
            SELECT category,
                   SUM(CASE WHEN tx_type='Income' THEN amount ELSE 0 END) as inc,
                   SUM(CASE WHEN tx_type='Expense' THEN amount ELSE 0 END) as exp
            FROM transactions
            WHERE tx_type IN ('Income', 'Expense') {d_sql}
            GROUP BY category COLLATE NOCASE
            ORDER BY exp DESC, inc DESC
        """
        self.cursor.execute(query, d_params)
        return self.cursor.fetchall()

    def get_single_ledger_statement(self, ledger_name: str, period_label="FY 2026-27", custom_from="", custom_to="", search_filter=""):
        self.cursor.execute("""
            SELECT name, ledger_group, opening_balance, show_on_top, notes
            FROM ledgers WHERE name=? COLLATE NOCASE
        """, (ledger_name,))
        row = self.cursor.fetchone()
        if not row:
            return {
                "name": ledger_name, "group": "Expense", "opening": 0.0, "pinned": 0, "notes": "",
                "total_dr": 0.0, "total_cr": 0.0, "raw_closing": 0.0, "net_dr_minus_cr": 0.0,
                "formatted_closing": "₹0.00", "dr_cr_tag": "-", "rows": []
            }

        c_name, grp, op_bal, pin, notes = row
        d_sql, d_params = self._build_date_filter_sql(period_label, custom_from, custom_to)
        query = f"""
            SELECT id, tx_date, tx_type, category, account, to_account, description, amount, dr_ledger, cr_ledger, COALESCE(voucher_group_id, 0)
            FROM transactions
            WHERE (dr_ledger = ? COLLATE NOCASE OR cr_ledger = ? COLLATE NOCASE) {d_sql}
        """
        params = [c_name, c_name] + d_params
        if search_filter:
            query += " AND (description LIKE ? OR category LIKE ? OR account LIKE ?)"
            params.extend([f"%{search_filter}%"] * 3)
        query += " ORDER BY tx_date ASC, id ASC"

        self.cursor.execute(query, params)
        raw_rows = self.cursor.fetchall()

        is_debit_normal = self._is_debit_normal_group(grp)
        running_bal = op_bal
        total_dr = 0.0
        total_cr = 0.0
        stmt_rows = []

        for tx_id, dt, t_type, cat, acc, to_acc, desc, amt, dr, cr, v_grp in raw_rows:
            is_dr = (dr.lower() == c_name.lower())
            dr_amt = amt if is_dr else 0.0
            cr_amt = amt if not is_dr else 0.0
            total_dr += dr_amt
            total_cr += cr_amt

            particulars = cr if is_dr else dr
            if v_grp > 0:
                particulars = f"{particulars} [Split #{v_grp}]"

            if is_debit_normal:
                running_bal += (dr_amt - cr_amt)
            else:
                running_bal += (cr_amt - dr_amt)

            stmt_rows.append({
                "id": tx_id, "date": dt, "type": t_type, "particulars": particulars,
                "description": desc, "dr": dr_amt, "cr": cr_amt, "balance": running_bal
            })

        if is_debit_normal:
            net_dr_minus_cr = (op_bal + total_dr) - total_cr
        else:
            net_dr_minus_cr = total_dr - (op_bal + total_cr)

        tag, fmt_bal = self._format_balance_tag(grp, running_bal, net_dr_minus_cr)

        return {
            "name": c_name, "group": grp, "opening": op_bal, "pinned": pin, "notes": notes or "",
            "total_dr": total_dr, "total_cr": total_cr, "raw_closing": running_bal,
            "net_dr_minus_cr": net_dr_minus_cr, "formatted_closing": fmt_bal, "dr_cr_tag": tag,
            "rows": list(reversed(stmt_rows))
        }


class InlineAutoCompleteField(ctk.CTkFrame):
    def __init__(self, parent, root_app, values_provider, on_create_new_callback, on_valid_commit=None, on_change_callback=None, placeholder="", height=32, btn_width=32):
        super().__init__(parent, fg_color="transparent")
        self.root_app = root_app
        self.values_provider = values_provider
        self.on_create_new = on_create_new_callback
        self.on_valid_commit = on_valid_commit
        self.on_change_callback = on_change_callback
        self.current_matches = []
        self.is_open = False
        self.is_enabled = True

        self.grid_columnconfigure(0, weight=1)

        top_row = ctk.CTkFrame(self, fg_color="transparent")
        top_row.grid(row=0, column=0, sticky="ew")
        top_row.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(top_row, placeholder_text=placeholder, height=height)
        self.entry.grid(row=0, column=0, sticky="ew", padx=(0, 3))

        self.btn_drop = ctk.CTkButton(
            top_row, text="▼", width=btn_width, height=height, fg_color="#475569", hover_color="#334155",
            command=self.toggle_list
        )
        self.btn_drop.grid(row=0, column=1)

        self.list_container = tk.Frame(self, bg="#CBD5E1", bd=1, relief="solid")
        scrollbar = tk.Scrollbar(self.list_container, orient="vertical")
        self.listbox = tk.Listbox(
            self.list_container, font=("Segoe UI", 10), height=5,
            bg="#FFFFFF", fg="#0F172A", selectbackground="#2563EB", selectforeground="#FFFFFF",
            activestyle="none", highlightthickness=0, bd=0, exportselection=False,
            yscrollcommand=scrollbar.set
        )
        scrollbar.config(command=self.listbox.yview)
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.entry.bind("<KeyRelease>", self.on_key_release)
        self.entry.bind("<Down>", self.on_arrow_down)
        self.entry.bind("<Up>", self.on_arrow_up)
        self.entry.bind("<Return>", self.on_enter_pressed)
        self.entry.bind("<Tab>", self.on_tab_pressed)
        self.listbox.bind("<ButtonRelease-1>", self.on_listbox_click)
        self.listbox.bind("<Return>", self.on_enter_pressed)

        self.root_app.register_autocomplete_widget(self)

    def destroy(self):
        self.root_app.unregister_autocomplete_widget(self)
        super().destroy()

    def set_enabled(self, enabled: bool):
        self.is_enabled = enabled
        if not enabled:
            self.hide_list()
        self.entry.configure(state="normal" if enabled else "disabled")
        self.btn_drop.configure(state="normal" if enabled else "disabled")

    def get(self) -> str:
        return self.entry.get().strip()

    def set(self, val: str):
        was_disabled = not self.is_enabled
        if was_disabled:
            self.entry.configure(state="normal")
        self.entry.delete(0, tk.END)
        if val:
            self.entry.insert(0, val)
        if was_disabled:
            self.entry.configure(state="disabled")
        self.hide_list()
        if self.on_change_callback:
            self.on_change_callback(val)

    def clear_to_placeholder(self):
        was_disabled = not self.is_enabled
        if was_disabled:
            self.entry.configure(state="normal")
        self.entry.delete(0, tk.END)
        if was_disabled:
            self.entry.configure(state="disabled")
        self.hide_list()
        if self.on_change_callback:
            self.on_change_callback("")

    def toggle_list(self):
        if not self.is_enabled:
            return
        if self.is_open:
            self.hide_list()
        else:
            self.entry.focus_set()
            self.show_list(show_all=True)

    def on_key_release(self, event):
        if not self.is_enabled or self.root_app.has_open_modal():
            return
        if event.keysym in ("Up", "Down", "Return", "Tab", "Escape", "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R"):
            return
        self.show_list(show_all=False)
        if self.on_change_callback:
            self.on_change_callback(self.get())

    def show_list(self, show_all=False):
        if not self.is_enabled or self.root_app.has_open_modal():
            return
        self.root_app.close_all_inline_dropdowns(except_widget=self)
        typed = "" if show_all else self.get().lower()
        all_items = self.values_provider()

        if not typed:
            matches = [CREATE_NEW_OPTION] + all_items
        else:
            starts = [x for x in all_items if x.lower().startswith(typed)]
            contains = [x for x in all_items if typed in x.lower() and x not in starts]
            matches = [CREATE_NEW_OPTION] + starts + contains

        self.current_matches = matches
        self.listbox.delete(0, tk.END)
        for item in matches:
            self.listbox.insert(tk.END, item)
        self.listbox.itemconfig(0, {'fg': '#2563EB'})
        self.listbox.configure(height=min(6, max(2, len(matches))))

        if not self.is_open:
            self.list_container.grid(row=1, column=0, sticky="ew", pady=(2, 4))
            self.is_open = True

        if len(matches) > 1 and typed:
            self.listbox.selection_set(1)
            self.listbox.activate(1)
            self.listbox.see(1)
        else:
            self.listbox.selection_set(0)
            self.listbox.activate(0)

    def hide_list(self):
        if self.is_open:
            self.list_container.grid_forget()
            self.is_open = False

    def on_arrow_down(self, event):
        if not self.is_enabled:
            return
        if not self.is_open:
            self.show_list(show_all=True)
            return "break"
        cur = self.listbox.curselection()
        idx = cur[0] if cur else -1
        nxt = min(len(self.current_matches) - 1, idx + 1)
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(nxt)
        self.listbox.activate(nxt)
        self.listbox.see(nxt)
        return "break"

    def on_arrow_up(self, event):
        if not self.is_enabled or not self.is_open:
            return
        cur = self.listbox.curselection()
        idx = cur[0] if cur else 1
        prv = max(0, idx - 1)
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(prv)
        self.listbox.activate(prv)
        self.listbox.see(prv)
        return "break"

    def on_listbox_click(self, event):
        if not self.is_enabled:
            return
        sel = self.listbox.curselection()
        if sel:
            self.apply_choice(self.current_matches[sel[0]])

    def on_enter_pressed(self, event):
        if not self.is_enabled or self.root_app.has_open_modal():
            return "break"
        if self.is_open:
            sel = self.listbox.curselection()
            if sel:
                self.apply_choice(self.current_matches[sel[0]])
                return "break"
        self.apply_choice(self.get())
        return "break"

    def on_tab_pressed(self, event):
        if self.is_open:
            sel = self.listbox.curselection()
            if sel:
                chosen = self.current_matches[sel[0]]
                if chosen != CREATE_NEW_OPTION:
                    self.set(chosen)
        self.hide_list()

    def apply_choice(self, chosen: str):
        self.hide_list()
        if not self.is_enabled or self.root_app.has_open_modal():
            return
        if not chosen or chosen == CREATE_NEW_OPTION:
            typed_now = self.get()
            prefill = "" if typed_now == CREATE_NEW_OPTION else typed_now
            self.on_create_new(prefill)
            return

        if self.root_app.db.ledger_exists(chosen):
            canon = self.root_app.db.get_canonical_name(chosen)
            self.set(canon)
            if self.on_valid_commit:
                self.on_valid_commit()
        else:
            self.on_create_new(chosen)


class CalendarPopup(ctk.CTkToplevel):
    def __init__(self, parent, initial_date_str: str, on_select_callback):
        super().__init__(parent)
        self.parent_app = parent
        self.title("Select Date (ESC to Close)")
        self.geometry("310x325")
        self.resizable(False, False)
        self.on_select = on_select_callback
        self.bind("<Escape>", lambda e: self.close_modal())
        self.protocol("WM_DELETE_WINDOW", self.close_modal)
        self.lift()
        self.focus_force()

        try:
            dt = datetime.strptime(initial_date_str.strip(), "%Y-%m-%d")
            self.year, self.month = dt.year, dt.month
        except Exception:
            now = datetime.now()
            self.year, self.month = now.year, now.month

        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=8)
        ctk.CTkButton(hdr, text="◀", width=36, command=self.prev_month).pack(side="left")
        self.lbl_month = ctk.CTkLabel(hdr, text="", font=ctk.CTkFont(size=14, weight="bold"))
        self.lbl_month.pack(side="left", expand=True)
        ctk.CTkButton(hdr, text="▶", width=36, command=self.next_month).pack(side="right")

        self.grid_frame = ctk.CTkFrame(self, corner_radius=8)
        self.grid_frame.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        ctk.CTkButton(
            self, text="Today", height=30, fg_color="#059669",
            command=lambda: self.pick_date(datetime.now().year, datetime.now().month, datetime.now().day)
        ).pack(fill="x", padx=10, pady=(0, 10))

        self.render_calendar()

    def close_modal(self):
        self.parent_app.active_modal = None
        self.destroy()

    def prev_month(self):
        self.month = 12 if self.month == 1 else self.month - 1
        if self.month == 12:
            self.year -= 1
        self.render_calendar()

    def next_month(self):
        self.month = 1 if self.month == 12 else self.month + 1
        if self.month == 1:
            self.year += 1
        self.render_calendar()

    def render_calendar(self):
        for w in self.grid_frame.winfo_children():
            w.destroy()
        self.lbl_month.configure(text=f"{calendar.month_name[self.month]} {self.year}")
        days = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
        for idx, d in enumerate(days):
            self.grid_frame.grid_columnconfigure(idx, weight=1)
            ctk.CTkLabel(self.grid_frame, text=d, font=ctk.CTkFont(size=11, weight="bold")).grid(row=0, column=idx, pady=4)

        cal = calendar.monthcalendar(self.year, self.month)
        for r_idx, week in enumerate(cal, start=1):
            for c_idx, day in enumerate(week):
                if day == 0:
                    continue
                btn = ctk.CTkButton(
                    self.grid_frame, text=str(day), width=32, height=28,
                    fg_color="#2563EB" if (day == datetime.now().day and self.month == datetime.now().month) else "#3B82F6",
                    command=lambda d=day: self.pick_date(self.year, self.month, d)
                )
                btn.grid(row=r_idx, column=c_idx, padx=2, pady=2)

    def pick_date(self, y, m, d):
        self.on_select(f"{y:04d}-{m:02d}-{d:02d}")
        self.close_modal()


class CreateLedgerModal(ctk.CTkToplevel):
    def __init__(self, parent, db: BookDatabaseV652a, prefill_name="", default_group="Expense", on_success=None):
        super().__init__(parent)
        self.parent_app = parent
        self.db = db
        self.on_success = on_success
        self.title("Create / Edit Ledger Account (ESC to Close)")
        self.geometry("520x510")
        self.minsize(500, 490)
        self.resizable(False, False)
        self.bind("<Escape>", lambda e: self.close_modal())
        self.protocol("WM_DELETE_WINDOW", self.close_modal)
        self.lift()
        self.focus_force()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, padx=22, pady=(16, 6), sticky="ew")
        ctk.CTkLabel(hdr, text="Create / Edit Ledger Account", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(
            hdr, text=f"Saving inside Book: {self.db.active_book_name}",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#059669"
        ).pack(anchor="w", pady=(2, 0))

        form = ctk.CTkFrame(self, corner_radius=10)
        form.grid(row=1, column=0, padx=22, pady=6, sticky="nsew")

        ctk.CTkLabel(form, text="Ledger / Account Name:", font=ctk.CTkFont(size=13, weight="bold")).pack(
            anchor="w", padx=16, pady=(14, 4)
        )
        self.ent_name = ctk.CTkEntry(form, height=34, placeholder_text="e.g. Union Bank, Kapil, Laptop, Groceries")
        self.ent_name.pack(fill="x", padx=16, pady=(0, 12))
        if prefill_name and prefill_name != CREATE_NEW_OPTION:
            self.ent_name.insert(0, prefill_name)
        self.ent_name.bind("<Return>", lambda e: self.save())

        ctk.CTkLabel(form, text="Account Type / Category:", font=ctk.CTkFont(size=13, weight="bold")).pack(
            anchor="w", padx=16, pady=(2, 4)
        )
        mapped_def = self.db.normalize_group(default_group, prefill_name)
        self.cmb_group = ctk.CTkOptionMenu(form, height=34, values=LEDGER_GROUPS, command=self.on_group_change)
        self.cmb_group.set(mapped_def)
        self.cmb_group.pack(fill="x", padx=16, pady=(0, 6))

        self.lbl_group_help = ctk.CTkLabel(
            form, text="", font=ctk.CTkFont(size=11), text_color="#2563EB", wraplength=450, justify="left"
        )
        self.lbl_group_help.pack(anchor="w", padx=16, pady=(0, 10))

        ctk.CTkLabel(
            form, text="Opening Balance (₹):", font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", padx=16, pady=(2, 4))
        self.ent_op = ctk.CTkEntry(form, height=34, placeholder_text="0.00")
        self.ent_op.insert(0, "0.00")
        self.ent_op.pack(fill="x", padx=16, pady=(0, 12))
        self.ent_op.bind("<Return>", lambda e: self.save())
        self.parent_app.attach_numeric_validator(self.ent_op)

        self.var_pin = tk.IntVar(value=1 if mapped_def in ("Bank Account", "Cash in Hand") else 0)
        self.chk_pin = ctk.CTkCheckBox(
            form, text="Show this Bank / Cash account on the Top Balance Bar", variable=self.var_pin
        )
        self.chk_pin.pack(anchor="w", padx=16, pady=(4, 14))

        btn_bar = ctk.CTkFrame(self, fg_color="transparent")
        btn_bar.grid(row=2, column=0, padx=22, pady=(8, 18), sticky="ew")

        ctk.CTkButton(
            btn_bar, text="✔ Save Ledger (Enter)", height=38, fg_color="#059669", hover_color="#047857",
            font=ctk.CTkFont(size=13, weight="bold"), command=self.save
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            btn_bar, text="Cancel (ESC)", height=38, width=120, fg_color="#64748B", hover_color="#475569",
            font=ctk.CTkFont(size=13, weight="bold"), command=self.close_modal
        ).pack(side="right")

        self.on_group_change(self.cmb_group.get())
        self.after(80, lambda: self.ent_name.focus_set())

    def close_modal(self):
        self.parent_app.active_modal = None
        self.destroy()

    def on_group_change(self, grp):
        self.lbl_group_help.configure(text=GROUP_DESCRIPTIONS.get(grp, ""))
        if grp in ("Bank Account", "Cash in Hand"):
            self.chk_pin.configure(state="normal")
            self.var_pin.set(1)
        else:
            self.var_pin.set(0)
            self.chk_pin.configure(state="disabled")

    def save(self):
        name = self.ent_name.get().strip()
        if not name or name == CREATE_NEW_OPTION:
            messagebox.showwarning("Missing Name", "Please enter a valid Ledger Name.", parent=self)
            return
        try:
            op = safe_numeric_eval(self.ent_op.get().strip() or "0")
        except Exception:
            messagebox.showerror("Invalid Amount", "Opening Balance must be a valid number.", parent=self)
            return

        saved_name = self.db.save_ledger(name, self.cmb_group.get(), op, self.var_pin.get())
        cb = self.on_success
        self.close_modal()
        if cb:
            cb(saved_name)


class DocumentViewerModal(ctk.CTkToplevel):
    def __init__(self, parent, title: str, content: str):
        super().__init__(parent)
        self.parent_app = parent
        self.title(f"{title} (ESC to Close)")
        self.geometry("780x580")
        self.bind("<Escape>", lambda e: self.close_modal())
        self.protocol("WM_DELETE_WINDOW", self.close_modal)
        self.lift()
        self.focus_force()

        ctk.CTkLabel(self, text=title, font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", padx=18, pady=(14, 6))
        txt = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=13), wrap="word")
        txt.pack(fill="both", expand=True, padx=18, pady=6)
        txt.insert("1.0", content)
        txt.configure(state="disabled")

        ctk.CTkButton(self, text="Close (ESC)", height=34, fg_color="#334155", command=self.close_modal).pack(
            anchor="e", padx=18, pady=(4, 14)
        )

    def close_modal(self):
        self.parent_app.active_modal = None
        self.destroy()


# ==============================================================================
# MAIN V6.5.2a APPLICATION (PHASE 2 HOTFIX: LOCKED PREVIEW + UNLOCK TO EDIT + ZERO FOCUS STEALING + TALLY ESC)
# ==============================================================================
class OfflineAccountingProV652a(ctk.CTk):
    def __init__(self):
        super().__init__()
        generate_ac_icon(ICON_PATH)
        if os.path.exists(ICON_PATH):
            try:
                self.iconbitmap(ICON_PATH)
            except Exception:
                pass

        self.db = BookDatabaseV652a()
        self.selected_tx_id = None
        self.selected_voucher_group_id = 0
        self.voucher_locked_preview = False  # True when viewing an existing transaction before clicking Unlock
        self.is_split_mode = False
        self.split_target = "category"
        self.split_row_widgets = []
        self.autocomplete_widgets = []

        self.active_drill_ledger = None
        self.calc_visible = False
        self.book_is_open = False
        self.active_modal = None
        self.gateway_selected_idx = 0
        self.gateway_companies = []
        self.gateway_card_widgets = []
        self.current_tab_key = "home"

        comp = self.db.get_active_company()
        self.current_period = comp["fy"]
        self.title("TallyLite — Select or Create Book")
        self.geometry("1450x910")
        self.minsize(1220, 760)

        self.refresh_dropdown_cache()
        self.build_root_containers()
        self.bind_shortcuts()

        self.show_company_gateway_screen(force=True)

    def register_autocomplete_widget(self, w):
        if w not in self.autocomplete_widgets:
            self.autocomplete_widgets.append(w)

    def unregister_autocomplete_widget(self, w):
        if w in self.autocomplete_widgets:
            self.autocomplete_widgets.remove(w)

    def attach_numeric_validator(self, ctk_entry_widget):
        vcmd = (self.register(self._validate_math_numeric), "%P")
        try:
            ctk_entry_widget._entry.configure(validate="key", validatecommand=vcmd)
        except Exception:
            pass

    def _validate_math_numeric(self, proposed: str) -> bool:
        if proposed == "":
            return True
        return bool(re.match(r'^[0-9.+\-*/() ]*$', proposed))

    def has_open_modal(self) -> bool:
        if self.active_modal is not None:
            try:
                if self.active_modal.winfo_exists():
                    return True
            except Exception:
                pass
            self.active_modal = None
        return False

    def has_unsaved_voucher_draft(self) -> bool:
        if not self.book_is_open:
            return False
        # If just viewing a locked preview, it is NOT an unsaved draft!
        if self.voucher_locked_preview:
            return False
        if self.selected_tx_id is not None or self.selected_voucher_group_id > 0:
            return True
        if self.ent_amount.get().strip() or self.ent_desc.get().strip():
            return True
        if self.ac_category.get().strip() or self.ac_account.get().strip() or self.ac_to_account.get().strip():
            return True
        if self.is_split_mode:
            for r in self.split_row_widgets:
                if r["cat"].get().strip() or r["amt"].get().strip() or r["note"].get().strip():
                    return True
        return False

    def open_create_ledger_modal(self, prefill_name="", default_group="Expense", on_success=None):
        if not self.book_is_open:
            return None
        self.close_all_inline_dropdowns()
        if self.has_open_modal():
            try:
                self.active_modal.lift()
                self.active_modal.focus_force()
            except Exception:
                pass
            return None
        self.active_modal = CreateLedgerModal(
            self, self.db, prefill_name=prefill_name, default_group=default_group, on_success=on_success
        )
        return self.active_modal

    def open_calendar_modal(self):
        if not self.book_is_open or self.voucher_locked_preview:
            return
        self.close_all_inline_dropdowns()
        if self.has_open_modal():
            self.active_modal.lift()
            return
        self.active_modal = CalendarPopup(self, self.ent_date.get(), self.set_voucher_date)

    def refresh_dropdown_cache(self):
        self.payment_accounts = self.db.get_ledgers_by_groups([
            "Bank Account",
            "Cash in Hand",
            "Party / Person (Customer / Vendor)",
            "Due / Pay Later (Payable)"
        ])
        self.bank_cash_only = self.db.get_ledgers_by_groups([
            "Bank Account",
            "Cash in Hand",
            "Party / Person (Customer / Vendor)",
            "Due / Pay Later (Payable)"
        ])
        self.voucher_ledgers = self.db.get_ledgers_by_groups([
            "Expense",
            "Income",
            "Party / Person (Customer / Vendor)",
            "Fixed Asset / Property",
            "Money to Receive (Receivable)",
            "Due / Pay Later (Payable)"
        ])
        self.all_ledgers = self.db.get_ledgers_by_groups(LEDGER_GROUPS)

    def close_all_inline_dropdowns(self, except_widget=None):
        for w in list(self.autocomplete_widgets):
            if w is not except_widget:
                try:
                    w.hide_list()
                except Exception:
                    pass

    def _any_inline_dropdown_open(self) -> bool:
        for w in list(self.autocomplete_widgets):
            if getattr(w, "is_open", False):
                return True
        return False

    def _build_large_top_menubar(self):
        self.top_menubar = ctk.CTkFrame(self, height=40, corner_radius=0, fg_color=("#0F172A", "#020617"))
        self.top_menubar.grid(row=0, column=0, sticky="ew")

        menu_font = ctk.CTkFont(family="Segoe UI", size=14, weight="bold")
        popup_font = ("Segoe UI", 12)

        def show_popup_menu(btn_widget, menu_builder):
            m = tk.Menu(self, tearoff=0, font=popup_font, bg="#FFFFFF", fg="#0F172A", activebackground="#2563EB", activeforeground="#FFFFFF")
            menu_builder(m)
            x = btn_widget.winfo_rootx()
            y = btn_widget.winfo_rooty() + btn_widget.winfo_height()
            m.tk_popup(x, y)

        def build_file_menu(m):
            m.add_command(label="🏢 Switch / Create Book Screen (F3)", command=self.show_company_gateway_screen)
            m.add_separator()
            for _, cname, cfy, is_act, l_cnt, t_cnt, _ in self.db.get_all_companies_with_counts():
                prefix = "✔ " if (is_act and self.book_is_open) else "   "
                m.add_command(
                    label=f"{prefix}Open Book: {cname} ({l_cnt} Ledgers, {t_cnt} Entries)",
                    command=lambda n=cname, f=cfy: self.request_open_book_with_guard(n, f)
                )
            m.add_separator()
            m.add_command(label="📂 Open Books Database Folder", command=lambda: os.startfile(BOOKS_DIR))
            m.add_command(label="❌ Exit Application", command=self.quit)

        def build_ledgers_menu(m):
            state_flag = "normal" if self.book_is_open else "disabled"
            m.add_command(label="➕ Create New Ledger Account (Ctrl+L)", state=state_flag, command=lambda: self.open_create_ledger_modal(on_success=lambda _: self.refresh_all()))
            m.add_command(label="⚙️ Open Manage Ledgers (Alt+3)", state=state_flag, command=lambda: self.switch_main_tab("ledgers"))

        def build_vouchers_menu(m):
            state_flag = "normal" if self.book_is_open else "disabled"
            m.add_command(label="🎯 New Entry / Jump to Voucher Box (Alt+V)", state=state_flag, command=self.focus_voucher_entry)
            m.add_command(label="🔓 Unlock Selected Entry for Editing (Alt+E)", state=state_flag, command=self.unlock_voucher_for_editing)
            m.add_command(label="➕ Toggle Multi-Line Split Voucher Mode (Alt+S)", state=state_flag, command=self.toggle_split_voucher_mode)
            m.add_separator()
            m.add_command(label="💸 Expense Entry (F5)", state=state_flag, command=lambda: self.switch_voucher_mode("Expense"))
            m.add_command(label="💰 Income Entry (F6)", state=state_flag, command=lambda: self.switch_voucher_mode("Income"))
            m.add_command(label="🔄 Transfer (F4)", state=state_flag, command=lambda: self.switch_voucher_mode("Transfer"))

        def build_view_menu(m):
            state_flag = "normal" if self.book_is_open else "disabled"
            m.add_command(label="🏠 Home Dashboard (Alt+1)", state=state_flag, command=lambda: self.switch_main_tab("home"))
            m.add_command(label="📒 All Transactions / Daybook (Alt+2)", state=state_flag, command=lambda: self.switch_main_tab("daybook"))
            m.add_command(label="⚙️ Manage Ledgers (Alt+3)", state=state_flag, command=lambda: self.switch_main_tab("ledgers"))
            m.add_command(label="📈 Financial Reports: TB, P&L, B/S (Alt+4)", state=state_flag, command=lambda: self.switch_main_tab("reports"))

        def build_export_menu(m):
            state_flag = "normal" if self.book_is_open else "disabled"
            m.add_command(label="📊 Export All Transactions to CSV", state=state_flag, command=self.export_daybook_csv)
            m.add_command(label="🖨 Print / Save Financial Statements (PDF/HTML)", state=state_flag, command=self.export_financial_statements_html_pdf)
            m.add_command(label="🏛 Export Tally XML File (.xml)", state=state_flag, command=self.export_tally_xml)

        def build_help_menu(m):
            m.add_command(label="⌨️ Keyboard Shortcuts (F1)", command=self.show_shortcuts_help)
            m.add_command(label="🆕 Version Changelog (V6.5.2a)", command=self.show_changelog_modal)
            m.add_command(label="📖 README & Tech Stack", command=self.show_readme_modal)

        menus = [
            ("📁 File & Books", build_file_menu),
            ("📒 Ledgers", build_ledgers_menu),
            ("🧾 Vouchers", build_vouchers_menu),
            ("👁 View & Reports", build_view_menu),
            ("📤 Export & Print", build_export_menu),
            ("❓ Help", build_help_menu)
        ]

        for label, builder in menus:
            btn = ctk.CTkButton(
                self.top_menubar, text=label, font=menu_font, height=34, width=115,
                fg_color="transparent", hover_color="#1E293B", text_color="#F8FAFC", corner_radius=6
            )
            btn.configure(command=lambda b=btn, bld=builder: show_popup_menu(b, bld))
            btn.pack(side="left", padx=4, pady=3)

    def bind_shortcuts(self):
        self.bind("<F1>", lambda e: self.show_shortcuts_help())
        self.bind("<F2>", lambda e: self.focus_voucher_date())
        self.bind("<F3>", lambda e: self.show_company_gateway_screen())
        self.bind("<F4>", lambda e: self.switch_voucher_mode("Transfer"))
        self.bind("<F5>", lambda e: self.switch_voucher_mode("Expense"))
        self.bind("<F6>", lambda e: self.switch_voucher_mode("Income"))
        self.bind("<Alt-v>", lambda e: self.focus_voucher_entry())
        self.bind("<Alt-V>", lambda e: self.focus_voucher_entry())
        self.bind("<Alt-e>", lambda e: self.unlock_voucher_for_editing())
        self.bind("<Alt-E>", lambda e: self.unlock_voucher_for_editing())
        self.bind("<Alt-s>", lambda e: self.toggle_split_voucher_mode())
        self.bind("<Alt-S>", lambda e: self.toggle_split_voucher_mode())
        self.bind("<Control-n>", lambda e: self.toggle_calculator_bar())
        self.bind("<Control-N>", lambda e: self.toggle_calculator_bar())
        self.bind("<Control-l>", lambda e: self.open_create_ledger_modal(on_success=lambda _: self.refresh_all()))
        self.bind("<Control-L>", lambda e: self.open_create_ledger_modal(on_success=lambda _: self.refresh_all()))
        self.bind("<Alt-Key-1>", lambda e: self.switch_main_tab("home") if self.book_is_open else None)
        self.bind("<Alt-Key-2>", lambda e: self.switch_main_tab("daybook") if self.book_is_open else None)
        self.bind("<Alt-Key-3>", lambda e: self.switch_main_tab("ledgers") if self.book_is_open else None)
        self.bind("<Alt-Key-4>", lambda e: self.switch_main_tab("reports") if self.book_is_open else None)
        self.bind("<Delete>", self.on_global_delete_key)
        self.bind("<Escape>", self.on_global_escape)
        self.bind("<Up>", self.on_gateway_arrow_up)
        self.bind("<Down>", self.on_gateway_arrow_down)
        self.bind("<Return>", self.on_gateway_enter)

    def on_global_delete_key(self, event):
        if not self.book_is_open or self.has_open_modal():
            return
        focused = self.focus_get()
        if isinstance(focused, tk.Entry):
            return
        self.delete_entry()

    def build_root_containers(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_large_top_menubar()

        self.gateway_frame = ctk.CTkFrame(self, fg_color=("#E2E8F0", "#0F172A"))
        self.accounting_frame = ctk.CTkFrame(self, fg_color=("#E2E8F0", "#0F172A"))

        self.calc_bar = ctk.CTkFrame(self, height=48, corner_radius=0, fg_color="#1E293B")
        self._build_bottom_calculator_bar()

        self._build_accounting_workspace()

    def request_open_book_with_guard(self, book_name: str, fy_label: str):
        if self.book_is_open and self.has_unsaved_voucher_draft():
            if not messagebox.askyesno(
                "Unsaved Voucher Entry in Progress",
                "You have an unsaved transaction in the Voucher Entry box!\n\nDo you want to discard your unsaved entry and switch books?"
            ):
                return
        self.open_book_and_enter(book_name, fy_label)

    def show_company_gateway_screen(self, force=False):
        if not force and self.book_is_open and self.has_unsaved_voucher_draft():
            if not messagebox.askyesno(
                "Unsaved Voucher Entry in Progress",
                "You are currently typing or editing a voucher entry that hasn't been saved yet!\n\nDo you want to discard your unsaved changes and go to the Select Book screen?"
            ):
                return

        if self.has_open_modal():
            self.active_modal.close_modal()
        self.book_is_open = False
        self.close_all_inline_dropdowns()
        self.accounting_frame.grid_forget()
        self.gateway_frame.grid(row=1, column=0, sticky="nsew")

        for w in self.gateway_frame.winfo_children():
            w.destroy()

        self.gateway_frame.grid_columnconfigure(0, weight=1)
        self.gateway_frame.grid_rowconfigure(0, weight=1)

        card = ctk.CTkFrame(self.gateway_frame, width=980, height=590, corner_radius=14, fg_color=("#FFFFFF", "#1E293B"))
        card.grid(row=0, column=0, padx=24, pady=24)
        card.grid_propagate(False)
        card.grid_columnconfigure(0, weight=3)
        card.grid_columnconfigure(1, weight=2)
        card.grid_rowconfigure(1, weight=1)

        hdr = ctk.CTkFrame(card, corner_radius=10, fg_color="#0F172A")
        hdr.grid(row=0, column=0, columnspan=2, padx=18, pady=(18, 10), sticky="ew")
        ctk.CTkLabel(
            hdr, text="A/C LEDGER PRO V6.5.2a — SELECT OR CREATE ISOLATED BOOK",
            font=ctk.CTkFont(size=20, weight="bold"), text_color="#FFFFFF"
        ).pack(anchor="w", padx=18, pady=(12, 2))
        ctk.CTkLabel(
            hdr, text="Home Gateway Mode: All voucher & ledger shortcuts are locked until you open a Book below.",
            font=ctk.CTkFont(size=12), text_color="#38BDF8"
        ).pack(anchor="w", padx=18, pady=(0, 12))

        left_box = ctk.CTkFrame(card, corner_radius=10, fg_color=("#F1F5F9", "#0F172A"))
        left_box.grid(row=1, column=0, padx=(18, 8), pady=10, sticky="nsew")
        left_box.grid_columnconfigure(0, weight=1)
        left_box.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            left_box, text="📂 Your Books (Use Up/Down Arrow Keys + Enter or Click):", font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, padx=14, pady=(12, 6), sticky="w")

        books_scroll = ctk.CTkScrollableFrame(left_box, corner_radius=8, fg_color="transparent")
        books_scroll.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")
        books_scroll.grid_columnconfigure(0, weight=1)

        self.gateway_companies = self.db.get_all_companies_with_counts()
        self.gateway_card_widgets = []
        self.gateway_selected_idx = 0

        for idx, (cid, cname, cfy, is_act, l_cnt, t_cnt, db_file) in enumerate(self.gateway_companies):
            if is_act:
                self.gateway_selected_idx = idx

            row_f = ctk.CTkFrame(
                books_scroll, corner_radius=8, fg_color=("#FFFFFF", "#1E293B"),
                border_width=2, border_color="#CBD5E1", cursor="hand2"
            )
            row_f.grid(row=idx, column=0, padx=4, pady=5, sticky="ew")
            row_f.grid_columnconfigure(0, weight=1)

            text_wrap = ctk.CTkFrame(row_f, fg_color="transparent", cursor="hand2")
            text_wrap.grid(row=0, column=0, padx=12, pady=10, sticky="ew")

            title_lbl = ctk.CTkLabel(
                text_wrap, text=f"[{idx + 1}] 🏢 {cname}",
                anchor="w", justify="left", font=ctk.CTkFont(size=14, weight="bold"),
                text_color=("#0F172A", "#F8FAFC"), cursor="hand2"
            )
            title_lbl.pack(fill="x", anchor="w")

            sub_lbl = ctk.CTkLabel(
                text_wrap, text=f"     File: {db_file}   •   {l_cnt} Ledgers   •   {t_cnt} Entries",
                anchor="w", justify="left", font=ctk.CTkFont(size=11), text_color="gray", cursor="hand2"
            )
            sub_lbl.pack(fill="x", anchor="w", pady=(2, 0))

            btn_open = ctk.CTkButton(
                row_f, text="Open (Enter) →", width=125, height=34,
                fg_color="#059669", hover_color="#047857",
                font=ctk.CTkFont(size=12, weight="bold"),
                command=lambda n=cname, f=cfy: self.open_book_and_enter(n, f)
            )
            btn_open.grid(row=0, column=1, padx=(6, 6), pady=10)

            if len(self.gateway_companies) > 1:
                btn_del = ctk.CTkButton(
                    row_f, text="🗑", width=34, height=34,
                    fg_color="#DC2626", hover_color="#B91C1C",
                    command=lambda c_n=cname: self.confirm_delete_book_from_gateway(c_n)
                )
                btn_del.grid(row=0, column=2, padx=(0, 10), pady=10)

            for clickable in (row_f, text_wrap, title_lbl, sub_lbl):
                clickable.bind("<Button-1>", lambda e, n=cname, f=cfy: self.open_book_and_enter(n, f))

            self.gateway_card_widgets.append(row_f)

        self._update_gateway_highlight()

        right_box = ctk.CTkFrame(card, corner_radius=10, fg_color=("#F1F5F9", "#0F172A"))
        right_box.grid(row=1, column=1, padx=(8, 18), pady=10, sticky="nsew")

        ctk.CTkLabel(right_box, text="➕ Create a New Clean Book:", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=16, pady=(14, 6))
        ctk.CTkLabel(right_box, text="Creates a brand-new .db file starting ONLY with 'Cash' (0.00).", font=ctk.CTkFont(size=11), text_color="#059669", wraplength=320, justify="left").pack(anchor="w", padx=16, pady=(0, 8))

        self.ent_gateway_new_book = ctk.CTkEntry(right_box, height=34, placeholder_text="Type new Book name here...")
        self.ent_gateway_new_book.pack(fill="x", padx=16, pady=6)

        ctk.CTkLabel(right_box, text="Default Period:", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=16, pady=(6, 2))
        self.cmb_gateway_fy = ctk.CTkOptionMenu(right_box, values=["FY 2026-27", "FY 2025-26", "All Time"])
        self.cmb_gateway_fy.set("FY 2026-27")
        self.cmb_gateway_fy.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkButton(
            right_box, text="✨ Create & Open Clean Book", height=36, fg_color="#2563EB",
            font=ctk.CTkFont(size=13, weight="bold"), command=self.create_book_from_gateway
        ).pack(fill="x", padx=16, pady=6)

    def _update_gateway_highlight(self):
        for i, card_w in enumerate(self.gateway_card_widgets):
            if i == self.gateway_selected_idx:
                card_w.configure(border_color="#2563EB", border_width=3, fg_color=("#EFF6FF", "#1E293B"))
            else:
                card_w.configure(border_color="#CBD5E1", border_width=1, fg_color=("#FFFFFF", "#1E293B"))

    def on_gateway_arrow_up(self, event):
        if self.book_is_open or self.has_open_modal() or not self.gateway_companies:
            return
        self.gateway_selected_idx = max(0, self.gateway_selected_idx - 1)
        self._update_gateway_highlight()

    def on_gateway_arrow_down(self, event):
        if self.book_is_open or self.has_open_modal() or not self.gateway_companies:
            return
        self.gateway_selected_idx = min(len(self.gateway_companies) - 1, self.gateway_selected_idx + 1)
        self._update_gateway_highlight()

    def on_gateway_enter(self, event):
        if self.book_is_open or self.has_open_modal():
            return
        focused = self.focus_get()
        if hasattr(self, "ent_gateway_new_book") and focused == self.ent_gateway_new_book._entry:
            self.create_book_from_gateway()
            return
        if self.gateway_companies and 0 <= self.gateway_selected_idx < len(self.gateway_companies):
            _, cname, cfy, _, _, _, _ = self.gateway_companies[self.gateway_selected_idx]
            self.open_book_and_enter(cname, cfy)

    def create_book_from_gateway(self):
        b_name = self.ent_gateway_new_book.get().strip()
        if not b_name:
            messagebox.showwarning("Required", "Please enter a name for the new Book.")
            return
        self.open_book_and_enter(b_name, self.cmb_gateway_fy.get())

    def confirm_delete_book_from_gateway(self, comp_name: str):
        if messagebox.askyesno("Delete Book", f"Delete Book '{comp_name}'?\n(A safety copy will be placed in your backups folder.)"):
            ok, msg = self.db.delete_company_by_name(comp_name)
            if ok:
                self.show_company_gateway_screen(force=True)
            else:
                messagebox.showwarning("Cannot Delete", msg)

    def open_book_and_enter(self, book_name: str, fy_label: str):
        self.db.create_or_switch_company(book_name, fy_label)
        self.current_period = fy_label if fy_label in ANALYTICS_PERIODS else "FY 2026-27"
        self.cmb_period.set(self.current_period)
        self.on_period_filter_change(self.current_period)
        self.active_drill_ledger = None
        self.book_is_open = True

        self.gateway_frame.grid_forget()
        self.accounting_frame.grid(row=1, column=0, sticky="nsew")
        self.clear_form()
        self.refresh_all()

    def _build_bottom_calculator_bar(self):
        self.calc_bar.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.calc_bar, text="🧮 Calculator (Ctrl+N):", font=ctk.CTkFont(size=12, weight="bold"), text_color="#F8FAFC").grid(row=0, column=0, padx=(14, 8), pady=8)

        self.ent_calc = ctk.CTkEntry(self.calc_bar, placeholder_text="Type math and press Enter...", height=30)
        self.ent_calc.grid(row=0, column=1, padx=6, pady=8, sticky="ew")
        self.ent_calc.bind("<Return>", self.evaluate_calculator)
        self.attach_numeric_validator(self.ent_calc)

        self.lbl_calc_result = ctk.CTkLabel(self.calc_bar, text="= ₹0.00", font=ctk.CTkFont(size=14, weight="bold"), text_color="#10B981")
        self.lbl_calc_result.grid(row=0, column=2, padx=12, pady=8)

        self.last_calc_value = ""
        ctk.CTkButton(self.calc_bar, text="📋 Copy to Amount", height=28, fg_color="#2563EB", command=self.send_calc_to_voucher).grid(row=0, column=3, padx=6, pady=8)
        ctk.CTkButton(self.calc_bar, text="✖ Close", width=65, height=28, fg_color="#475569", command=self.toggle_calculator_bar).grid(row=0, column=4, padx=(4, 14), pady=8)

    def toggle_calculator_bar(self):
        if not self.book_is_open:
            return
        if self.calc_visible:
            self.calc_bar.grid_forget()
            self.calc_visible = False
        else:
            self.calc_bar.grid(row=2, column=0, sticky="ew")
            self.calc_visible = True
            self.ent_calc.focus_set()

    def evaluate_calculator(self, event=None):
        expr = self.ent_calc.get().strip()
        if not expr:
            return
        try:
            res = safe_numeric_eval(expr)
            self.last_calc_value = f"{res:.2f}"
            self.lbl_calc_result.configure(text=f"= ₹{res:,.2f}")
        except Exception:
            self.lbl_calc_result.configure(text="Invalid Math")

    def send_calc_to_voucher(self):
        if self.voucher_locked_preview:
            self.unlock_voucher_for_editing()
        self.evaluate_calculator()
        if self.last_calc_value:
            self.ent_amount.delete(0, tk.END)
            self.ent_amount.insert(0, self.last_calc_value)
            self.ent_amount.focus_set()

    def _build_accounting_workspace(self):
        self.accounting_frame.grid_columnconfigure(0, weight=1)
        self.accounting_frame.grid_rowconfigure(2, weight=1)

        self.top_container = ctk.CTkFrame(self.accounting_frame, corner_radius=10, fg_color=("#FFFFFF", "#1E293B"))
        self.top_container.grid(row=0, column=0, padx=12, pady=(8, 4), sticky="ew")
        self.top_container.grid_columnconfigure((0, 1, 2, 3), weight=1)

        comp_strip = ctk.CTkFrame(self.top_container, fg_color="transparent")
        comp_strip.grid(row=0, column=0, columnspan=4, padx=12, pady=(6, 2), sticky="ew")

        self.lbl_comp_badge = ctk.CTkLabel(comp_strip, text="🏢 My First Book", font=ctk.CTkFont(size=16, weight="bold"), text_color=("#0F172A", "#F8FAFC"))
        self.lbl_comp_badge.pack(side="left")

        ctk.CTkButton(comp_strip, text="Switch Book (F3)", width=130, height=28, fg_color="#2563EB", font=ctk.CTkFont(size=12, weight="bold"), command=self.show_company_gateway_screen).pack(side="left", padx=8)
        ctk.CTkButton(comp_strip, text="🧮 Calculator (Ctrl+N)", width=145, height=28, fg_color="#059669", font=ctk.CTkFont(size=12, weight="bold"), command=self.toggle_calculator_bar).pack(side="left", padx=4)

        self.cmb_period = ctk.CTkOptionMenu(comp_strip, values=ANALYTICS_PERIODS, width=155, height=28, font=ctk.CTkFont(size=12, weight="bold"), command=self.on_period_filter_change)
        self.cmb_period.set("FY 2026-27")
        self.cmb_period.pack(side="right", padx=6)
        ctk.CTkLabel(comp_strip, text="📊 Period:", font=ctk.CTkFont(size=12, weight="bold")).pack(side="right", padx=2)

        self.custom_date_frame = ctk.CTkFrame(comp_strip, fg_color="transparent")
        self.ent_custom_from = ctk.CTkEntry(self.custom_date_frame, placeholder_text="From YYYY-MM-DD", width=115, height=26)
        self.ent_custom_from.pack(side="left", padx=2)
        ctk.CTkLabel(self.custom_date_frame, text="to").pack(side="left", padx=2)
        self.ent_custom_to = ctk.CTkEntry(self.custom_date_frame, placeholder_text="To YYYY-MM-DD", width=115, height=26)
        self.ent_custom_to.pack(side="left", padx=2)
        ctk.CTkButton(self.custom_date_frame, text="Apply", width=55, height=26, fg_color="#059669", command=self.refresh_all).pack(side="left", padx=4)

        self.lbl_tot_in = self._create_kpi_card(self.top_container, 1, 0, "TOTAL MONEY IN", "#059669")
        self.lbl_tot_out = self._create_kpi_card(self.top_container, 1, 1, "TOTAL MONEY OUT", "#DC2626")
        self.lbl_net_flow = self._create_kpi_card(self.top_container, 1, 2, "NET SAVINGS FLOW", "#2563EB")
        self.lbl_liquid = self._create_kpi_card(self.top_container, 1, 3, "TOTAL LIQUID BALANCE", "#7C3AED")

        self.bank_bar = ctk.CTkFrame(self.accounting_frame, corner_radius=10, fg_color=("#F8FAFC", "#1E293B"))
        self.bank_bar.grid(row=1, column=0, padx=12, pady=3, sticky="ew")

        self.paned = tk.PanedWindow(self.accounting_frame, orient=tk.HORIZONTAL, sashwidth=7, sashrelief=tk.RAISED, bg="#CBD5E1", bd=0, opaqueresize=True)
        self.paned.grid(row=2, column=0, padx=12, pady=(3, 8), sticky="nsew")

        self.left_pane_holder = ctk.CTkFrame(self.paned, fg_color="transparent")
        self.right_pane_holder = ctk.CTkFrame(self.paned, fg_color="transparent")

        self._build_left_voucher_panel()
        self._build_right_structured_views()

        self.paned.add(self.left_pane_holder, minsize=345, width=435)
        self.paned.add(self.right_pane_holder, minsize=620)

    def on_period_filter_change(self, choice: str):
        self.current_period = choice
        if choice == "Custom Date Range":
            self.custom_date_frame.pack(side="right", padx=6)
        else:
            self.custom_date_frame.pack_forget()
            self.refresh_all()

    def _create_kpi_card(self, parent, row, col, title, color):
        card = ctk.CTkFrame(parent, corner_radius=8, fg_color=("#F1F5F9", "#0F172A"))
        card.grid(row=row, column=col, padx=6, pady=6, sticky="ew")
        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=11, weight="bold"), text_color="gray").pack(pady=(6, 0))
        val_lbl = ctk.CTkLabel(card, text="₹0.00", font=ctk.CTkFont(size=18, weight="bold"), text_color=color)
        val_lbl.pack(pady=(0, 6))
        return val_lbl

    def _build_left_voucher_panel(self):
        self.left_pane_holder.grid_rowconfigure(0, weight=1)
        self.left_pane_holder.grid_columnconfigure(0, weight=1)

        self.left_panel = ctk.CTkScrollableFrame(self.left_pane_holder, corner_radius=10, fg_color=("#FFFFFF", "#1E293B"))
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 3))

        hdr_row = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        hdr_row.pack(fill="x", pady=(2, 2))
        ctk.CTkLabel(hdr_row, text="Voucher Entry (Alt+V)", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")
        ctk.CTkButton(hdr_row, text="+ New Ledger", width=95, height=26, fg_color="#2563EB", command=lambda: self.open_create_ledger_modal(on_success=lambda _: self.refresh_all())).pack(side="right")

        self.lbl_vch_hint = ctk.CTkLabel(self.left_panel, text="New Entry Mode — Type or select ledgers below", font=ctk.CTkFont(size=11, weight="bold"), text_color="#059669")
        self.lbl_vch_hint.pack(anchor="w", pady=(0, 6))

        ctk.CTkLabel(self.left_panel, text="Date (YYYY-MM-DD) [F2]:", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w")
        date_row = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        date_row.pack(fill="x", pady=(0, 6))
        self.ent_date = ctk.CTkEntry(date_row, height=32)
        self.ent_date.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.ent_date.insert(0, datetime.now().strftime("%Y-%m-%d"))
        self.ent_date.bind("<Return>", lambda e: self.focus_voucher_entry())
        self.btn_cal = ctk.CTkButton(date_row, text="📅", width=36, height=32, fg_color="#334155", hover_color="#1E293B", command=self.open_calendar_modal)
        self.btn_cal.pack(side="right")

        ctk.CTkLabel(self.left_panel, text="Transaction Type (F5 / F6 / F4):", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w")
        self.cmb_type = ctk.CTkSegmentedButton(self.left_panel, values=["Expense", "Income", "Transfer"], height=32, command=self.on_type_change)
        self.cmb_type.set("Expense")
        self.cmb_type.pack(fill="x", pady=(0, 6))

        self.cat_container = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.cat_container.pack(fill="x", pady=(0, 4))

        cat_hdr_row = ctk.CTkFrame(self.cat_container, fg_color="transparent")
        cat_hdr_row.pack(fill="x", pady=(0, 2))
        self.lbl_category = ctk.CTkLabel(cat_hdr_row, text="Category / Asset / Party Ledger [Alt+V]:", font=ctk.CTkFont(size=12, weight="bold"))
        self.lbl_category.pack(side="left")

        self.btn_toggle_split = ctk.CTkButton(cat_hdr_row, text="➕ Split / Multi-Line (Alt+S)", width=155, height=24, fg_color="#7C3AED", hover_color="#6D28D9", font=ctk.CTkFont(size=11, weight="bold"), command=self.toggle_split_voucher_mode)
        self.btn_toggle_split.pack(side="right")

        self.ac_category = InlineAutoCompleteField(
            self.cat_container, root_app=self,
            values_provider=lambda: self.voucher_ledgers,
            on_create_new_callback=self.prompt_create_category_ledger,
            on_valid_commit=lambda: (self.split_row_widgets[0]["cat"].entry.focus_set() if (self.is_split_mode and self.split_target == "account" and self.split_row_widgets) else self.ac_account.entry.focus_set()),
            on_change_callback=self.update_live_voucher_balances,
            placeholder="Select or type Expense, Asset, or Party..."
        )
        self.ac_category.pack(fill="x")

        self.lbl_cat_cur_bal = ctk.CTkLabel(self.cat_container, text="Cur Bal: —", font=ctk.CTkFont(size=11, weight="bold"), text_color="#64748B")
        self.lbl_cat_cur_bal.pack(anchor="w", pady=(1, 2))

        self.split_container = ctk.CTkFrame(self.left_panel, corner_radius=8, fg_color=("#F8FAFC", "#0F172A"), border_width=1, border_color="#7C3AED")

        split_top = ctk.CTkFrame(self.split_container, fg_color="transparent")
        split_top.pack(fill="x", padx=8, pady=(6, 2))
        self.lbl_split_title = ctk.CTkLabel(split_top, text="🔀 Multi-Line Split Mode:", font=ctk.CTkFont(size=12, weight="bold"), text_color="#7C3AED")
        self.lbl_split_title.pack(side="left")
        self.btn_close_split = ctk.CTkButton(split_top, text="✖ Single Mode (Alt+S)", width=125, height=22, fg_color="#64748B", font=ctk.CTkFont(size=11), command=self.toggle_split_voucher_mode)
        self.btn_close_split.pack(side="right")

        self.seg_split_target = ctk.CTkSegmentedButton(
            self.split_container,
            values=["Split Categories (Dr)", "Split Payment Modes (Cr)"],
            height=26,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self.on_split_target_change
        )
        self.seg_split_target.set("Split Categories (Dr)")
        self.seg_split_target.pack(fill="x", padx=8, pady=(2, 4))

        ctk.CTkLabel(
            self.split_container,
            text="Tip: Enter adds line & auto-fills remainder | Shift+BackSpace or Ctrl+D deletes line",
            font=ctk.CTkFont(size=10), text_color="#2563EB"
        ).pack(anchor="w", padx=8, pady=(0, 2))

        col_hdr = ctk.CTkFrame(self.split_container, fg_color="transparent")
        col_hdr.pack(fill="x", padx=8, pady=(0, 2))
        self.lbl_split_col_ledger = ctk.CTkLabel(col_hdr, text="Ledger / Party", font=ctk.CTkFont(size=11, weight="bold"), width=150, anchor="w")
        self.lbl_split_col_ledger.pack(side="left")
        ctk.CTkLabel(col_hdr, text="Amount (₹)", font=ctk.CTkFont(size=11, weight="bold"), width=82, anchor="w").pack(side="left", padx=4)
        ctk.CTkLabel(col_hdr, text="Line Note", font=ctk.CTkFont(size=11, weight="bold"), anchor="w").pack(side="left", fill="x", expand=True)

        self.split_rows_holder = ctk.CTkFrame(self.split_container, fg_color="transparent")
        self.split_rows_holder.pack(fill="x", padx=6, pady=2)

        split_btm = ctk.CTkFrame(self.split_container, fg_color="transparent")
        split_btm.pack(fill="x", padx=8, pady=(4, 8))
        self.btn_add_split_line = ctk.CTkButton(split_btm, text="+ Add Split Line", width=115, height=26, fg_color="#2563EB", font=ctk.CTkFont(size=11, weight="bold"), command=self.add_split_row)
        self.btn_add_split_line.pack(side="left")
        self.lbl_split_total = ctk.CTkLabel(split_btm, text="Split Sum: ₹0.00", font=ctk.CTkFont(size=13, weight="bold"), text_color="#059669")
        self.lbl_split_total.pack(side="right")

        self.acc_container = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.acc_container.pack(fill="x", pady=(0, 4))

        self.lbl_account = ctk.CTkLabel(self.acc_container, text="Paid From / Credit Account:", font=ctk.CTkFont(size=12, weight="bold"))
        self.lbl_account.pack(anchor="w")

        self.ac_account = InlineAutoCompleteField(
            self.acc_container, root_app=self,
            values_provider=lambda: self.bank_cash_only if self.cmb_type.get() == "Transfer" else self.payment_accounts,
            on_create_new_callback=self.prompt_create_account_ledger,
            on_valid_commit=lambda: (self.ac_to_account.entry.focus_set() if self.cmb_type.get() == "Transfer" else self.ent_amount.focus_set()),
            on_change_callback=self.update_live_voucher_balances,
            placeholder="Select or type Bank, Cash, or Party..."
        )
        self.ac_account.pack(fill="x")

        self.lbl_acc_cur_bal = ctk.CTkLabel(self.acc_container, text="Cur Bal: —", font=ctk.CTkFont(size=11, weight="bold"), text_color="#2563EB")
        self.lbl_acc_cur_bal.pack(anchor="w", pady=(1, 2))

        self.to_acc_container = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.lbl_to_account = ctk.CTkLabel(self.to_acc_container, text="Transfer To:", font=ctk.CTkFont(size=12, weight="bold"))
        self.lbl_to_account.pack(anchor="w")
        self.ac_to_account = InlineAutoCompleteField(
            self.to_acc_container, root_app=self,
            values_provider=lambda: self.bank_cash_only,
            on_create_new_callback=self.prompt_create_to_account_ledger,
            on_valid_commit=lambda: self.ent_amount.focus_set(),
            on_change_callback=self.update_live_voucher_balances,
            placeholder="Select receiving Bank or Cash..."
        )
        self.ac_to_account.pack(fill="x")
        self.lbl_to_acc_cur_bal = ctk.CTkLabel(self.to_acc_container, text="Cur Bal: —", font=ctk.CTkFont(size=11, weight="bold"), text_color="#059669")
        self.lbl_to_acc_cur_bal.pack(anchor="w", pady=(1, 4))

        self.single_amt_desc_container = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.single_amt_desc_container.pack(fill="x")

        self.lbl_amount_title = ctk.CTkLabel(self.single_amt_desc_container, text="Amount (Numbers & Math Only: 250+120):", font=ctk.CTkFont(size=12, weight="bold"))
        self.lbl_amount_title.pack(anchor="w")

        amt_row = ctk.CTkFrame(self.single_amt_desc_container, fg_color="transparent")
        amt_row.pack(fill="x", pady=(0, 6))

        lbl_rupee = ctk.CTkLabel(
            amt_row, text=" ₹ ", width=34, height=32, corner_radius=6,
            fg_color="#E2E8F0", text_color="#0F172A", font=ctk.CTkFont(size=15, weight="bold")
        )
        lbl_rupee.pack(side="left", padx=(0, 4))

        self.ent_amount = ctk.CTkEntry(amt_row, height=32, placeholder_text="0.00")
        self.ent_amount.pack(side="left", fill="x", expand=True)
        self.ent_amount.bind("<Return>", lambda e: self.ent_desc.focus_set())
        self.ent_amount.bind("<KeyRelease>", lambda e: self.update_split_total_label() if self.is_split_mode else None)
        self.attach_numeric_validator(self.ent_amount)

        self.lbl_desc_title = ctk.CTkLabel(self.single_amt_desc_container, text="Description / Short Note:", font=ctk.CTkFont(size=12, weight="bold"))
        self.lbl_desc_title.pack(anchor="w")
        self.ent_desc = ctk.CTkEntry(self.single_amt_desc_container, height=32, placeholder_text="Enter narration...")
        self.ent_desc.pack(fill="x", pady=(0, 10))
        self.ent_desc.bind("<Return>", lambda e: self.save_or_unlock_action())

        btn_row = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        btn_row.pack(fill="x", pady=4)
        self.btn_save = ctk.CTkButton(btn_row, text="✔ Save Entry (Enter)", height=34, fg_color="#059669", hover_color="#047857", font=ctk.CTkFont(size=13, weight="bold"), command=self.save_or_unlock_action)
        self.btn_save.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.btn_clear = ctk.CTkButton(btn_row, text="+ New / Clear", width=85, height=34, fg_color="#64748B", command=self.clear_form)
        self.btn_clear.pack(side="left", padx=3)

        self.btn_delete = ctk.CTkButton(btn_row, text="Delete", width=60, height=34, fg_color="#DC2626", hover_color="#B91C1C", command=self.delete_entry)
        self.btn_delete.pack(side="left", padx=(3, 0))

        ctk.CTkLabel(self.left_panel, text="──────────────────────────────", text_color="gray").pack(pady=4)
        ctk.CTkLabel(self.left_panel, text="Category-Wise Summary", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(0, 4))

        cat_frame = ctk.CTkFrame(self.left_panel)
        cat_frame.pack(fill="both", expand=True, pady=2)

        self.cat_tree = ttk.Treeview(cat_frame, columns=("Ledger", "In", "Out"), show="headings", height=6)
        self.cat_tree.heading("Ledger", text="Category")
        self.cat_tree.heading("In", text="In (₹)")
        self.cat_tree.heading("Out", text="Out (₹)")
        self.cat_tree.column("Ledger", width=155, anchor="w")
        self.cat_tree.column("In", width=80, anchor="e")
        self.cat_tree.column("Out", width=80, anchor="e")
        self.cat_tree.pack(fill="both", expand=True)
        self.cat_tree.bind("<Double-1>", self.on_quick_cat_double_click)
        self.cat_tree.bind("<Return>", self.on_quick_cat_double_click)

    # ==========================================================================
    # LOCKED PREVIEW vs UNLOCKED EDIT MODE HELPERS
    # ==========================================================================
    def _set_voucher_fields_enabled(self, enabled: bool):
        st = "normal" if enabled else "disabled"
        self.ent_date.configure(state=st)
        self.btn_cal.configure(state=st)
        self.cmb_type.configure(state=st)
        self.btn_toggle_split.configure(state=st)
        self.btn_close_split.configure(state=st)
        self.seg_split_target.configure(state=st)
        self.btn_add_split_line.configure(state=st)

        self.ac_category.set_enabled(enabled)
        self.ac_account.set_enabled(enabled)
        self.ac_to_account.set_enabled(enabled)
        self.ent_amount.configure(state=st)
        self.ent_desc.configure(state=st)

        for r in self.split_row_widgets:
            r["cat"].set_enabled(enabled)
            r["amt"].configure(state=st)
            r["note"].configure(state=st)
            r["btn_rem"].configure(state=st)

    def save_or_unlock_action(self):
        if self.voucher_locked_preview:
            self.unlock_voucher_for_editing()
        else:
            self.save_entry()

    def unlock_voucher_for_editing(self):
        if not self.book_is_open or self.has_open_modal():
            return
        if self.selected_tx_id is None and self.selected_voucher_group_id == 0:
            self.focus_voucher_entry()
            return
        self.voucher_locked_preview = False
        self._set_voucher_fields_enabled(True)
        if self.selected_voucher_group_id > 0:
            self.lbl_vch_hint.configure(text=f"✏️ UNLOCKED EDITING: Split Voucher #{self.selected_voucher_group_id} (ESC to Lock/Cancel)", text_color="#D97706")
            self.btn_save.configure(text=f"✔ Save Changes to Split #{self.selected_voucher_group_id}", fg_color="#D97706", hover_color="#B45309")
        else:
            self.lbl_vch_hint.configure(text=f"✏️ UNLOCKED EDITING: Voucher ID #{self.selected_tx_id} (ESC to Lock/Cancel)", text_color="#D97706")
            self.btn_save.configure(text=f"✔ Save Changes to ID #{self.selected_tx_id}", fg_color="#D97706", hover_color="#B45309")
        self.focus_voucher_entry()

    def update_live_voucher_balances(self, _=None):
        if not self.book_is_open:
            return
        c_from = self.ent_custom_from.get().strip()
        c_to = self.ent_custom_to.get().strip()
        cat_txt = self.db.get_quick_ledger_balance_text(self.ac_category.get(), self.current_period, c_from, c_to)
        self.lbl_cat_cur_bal.configure(text=cat_txt if cat_txt else "Cur Bal: —")

        acc_txt = self.db.get_quick_ledger_balance_text(self.ac_account.get(), self.current_period, c_from, c_to)
        self.lbl_acc_cur_bal.configure(text=acc_txt if acc_txt else "Cur Bal: —")

        if self.cmb_type.get() == "Transfer":
            to_txt = self.db.get_quick_ledger_balance_text(self.ac_to_account.get(), self.current_period, c_from, c_to)
            self.lbl_to_acc_cur_bal.configure(text=to_txt if to_txt else "Cur Bal: —")

    def on_split_target_change(self, choice: str):
        self.close_all_inline_dropdowns()
        if "Cr" in choice or "Payment" in choice:
            self.split_target = "account"
            self.lbl_split_col_ledger.configure(text="Bank / Cash / Party (Cr)")
            self.acc_container.pack_forget()
            self.cat_container.pack(fill="x", pady=(0, 4), after=self.cmb_type)
            self.split_container.pack(fill="x", pady=(0, 8), after=self.cat_container)
        else:
            self.split_target = "category"
            self.lbl_split_col_ledger.configure(text="Category / Party (Dr)")
            self.cat_container.pack_forget()
            self.split_container.pack(fill="x", pady=(0, 8), after=self.cmb_type)
            self.acc_container.pack(fill="x", pady=(0, 4), after=self.split_container)
        self.update_split_total_label()

    def toggle_split_voucher_mode(self, steal_focus=True):
        if not self.book_is_open or self.has_open_modal():
            return
        if self.voucher_locked_preview and steal_focus:
            return
        if self.cmb_type.get() == "Transfer":
            if steal_focus:
                messagebox.showinfo("Split Mode", "Split mode is for Expense or Income vouchers.")
            return

        self.close_all_inline_dropdowns()
        if not self.is_split_mode:
            self.is_split_mode = True
            self.seg_split_target.set("Split Categories (Dr)" if self.split_target == "category" else "Split Payment Modes (Cr)")
            self.on_split_target_change(self.seg_split_target.get())
            self.lbl_amount_title.configure(text="Total Voucher Amount (₹) [Optional — Auto-fills Remainder]:", text_color="#7C3AED")
            if not self.split_row_widgets:
                self.add_split_row(focus_new=False)
                self.add_split_row(focus_new=False)
            self.update_split_total_label()
            if steal_focus and self.split_row_widgets and not self.voucher_locked_preview:
                self.after(40, lambda: self.split_row_widgets[0]["cat"].entry.focus_set())
        else:
            self.is_split_mode = False
            self.split_container.pack_forget()
            self.cat_container.pack(fill="x", pady=(0, 4), after=self.cmb_type)
            self.acc_container.pack(fill="x", pady=(0, 4), after=self.cat_container)
            self.lbl_amount_title.configure(text="Amount (Numbers & Math Only: 250+120):", text_color=("#0F172A", "#F8FAFC"))

    def add_split_row(self, prefill_cat="", prefill_amt="", prefill_note="", focus_new=False):
        row_f = ctk.CTkFrame(self.split_rows_holder, fg_color="transparent")
        row_f.pack(fill="x", pady=2)
        row_f.grid_columnconfigure(0, weight=5)
        row_f.grid_columnconfigure(1, weight=3)
        row_f.grid_columnconfigure(2, weight=5)

        row_item = {"frame": row_f, "cat": None, "amt": None, "note": None, "btn_rem": None}

        def provide_split_values():
            return self.payment_accounts if self.split_target == "account" else self.voucher_ledgers

        def prompt_new_split_ledger(prefill_txt):
            if self.split_target == "account":
                def_grp = "Bank Account"
            else:
                def_grp = "Income" if self.cmb_type.get() == "Income" else "Expense"
            self.open_create_ledger_modal(
                prefill_name=prefill_txt,
                default_group=def_grp,
                on_success=lambda saved_n: (self.refresh_all(), row_item["cat"].set(saved_n), row_item["amt"].focus_set())
            )

        ac_split_ledger = InlineAutoCompleteField(
            row_f,
            root_app=self,
            values_provider=provide_split_values,
            on_create_new_callback=prompt_new_split_ledger,
            on_valid_commit=lambda: self._on_split_ledger_committed(row_item),
            placeholder="Type ledger...",
            height=28,
            btn_width=24
        )
        ac_split_ledger.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        if prefill_cat:
            ac_split_ledger.set(prefill_cat)

        ent_amt = ctk.CTkEntry(row_f, width=78, height=28, placeholder_text="0.00")
        if prefill_amt != "":
            ent_amt.insert(0, str(prefill_amt))
        ent_amt.grid(row=0, column=1, sticky="ew", padx=2)
        self.attach_numeric_validator(ent_amt)
        ent_amt.bind("<KeyRelease>", lambda e: self.update_split_total_label())
        ent_amt.bind("<Return>", lambda e: row_item["note"].focus_set())

        ent_note = ctk.CTkEntry(row_f, height=28, placeholder_text="Line note...")
        if prefill_note:
            ent_note.insert(0, prefill_note)
        ent_note.grid(row=0, column=2, sticky="ew", padx=2)
        ent_note.bind("<Return>", lambda e: self._on_split_row_enter(row_item))

        btn_rem = ctk.CTkButton(row_f, text="✖", width=26, height=28, fg_color="#DC2626", hover_color="#B91C1C", command=lambda: self.remove_split_row(row_item))
        btn_rem.grid(row=0, column=3, padx=(2, 0))

        row_item["cat"] = ac_split_ledger
        row_item["amt"] = ent_amt
        row_item["note"] = ent_note
        row_item["btn_rem"] = btn_rem

        for w_entry in (ac_split_ledger.entry, ent_amt, ent_note):
            w_entry.bind("<Shift-BackSpace>", lambda e, ri=row_item: self._keyboard_delete_split_row(ri))
            w_entry.bind("<Control-d>", lambda e, ri=row_item: self._keyboard_delete_split_row(ri))
            w_entry.bind("<Control-D>", lambda e, ri=row_item: self._keyboard_delete_split_row(ri))

        ac_split_ledger.entry.bind("<BackSpace>", lambda e, ri=row_item: self._on_split_cat_backspace(e, ri), add="+")

        self.split_row_widgets.append(row_item)
        self.update_split_total_label()
        if focus_new and not self.voucher_locked_preview:
            self.after(30, lambda: ac_split_ledger.entry.focus_set())
        return row_item

    def _on_split_ledger_committed(self, row_item):
        if self.voucher_locked_preview:
            return
        if not row_item["amt"].get().strip():
            rem = self._compute_remaining_voucher_amount(exclude_row=row_item)
            if rem > 0.009:
                row_item["amt"].insert(0, f"{rem:.2f}")
                self.update_split_total_label()
        row_item["amt"].focus_set()
        row_item["amt"].select_range(0, tk.END)

    def _compute_remaining_voucher_amount(self, exclude_row=None) -> float:
        target_str = self.ent_amount.get().strip()
        if not target_str:
            return 0.0
        try:
            target_val = safe_numeric_eval(target_str)
        except Exception:
            return 0.0
        used = 0.0
        for r in self.split_row_widgets:
            if r is exclude_row:
                continue
            s = r["amt"].get().strip()
            if s:
                try:
                    used += safe_numeric_eval(s)
                except Exception:
                    pass
        return max(0.0, target_val - used)

    def _on_split_row_enter(self, row_item):
        if self.voucher_locked_preview:
            return "break"
        rem = self._compute_remaining_voucher_amount()
        idx = self.split_row_widgets.index(row_item) if row_item in self.split_row_widgets else -1
        if idx + 1 < len(self.split_row_widgets):
            nxt = self.split_row_widgets[idx + 1]
            if not nxt["amt"].get().strip() and rem > 0.009:
                nxt["amt"].insert(0, f"{rem:.2f}")
                self.update_split_total_label()
            nxt["cat"].entry.focus_set()
            return "break"

        target_str = self.ent_amount.get().strip()
        if target_str and rem <= 0.009:
            self.ent_desc.focus_set()
            return "break"

        prefill_rem = f"{rem:.2f}" if rem > 0.009 else ""
        self.add_split_row(prefill_amt=prefill_rem, focus_new=True)
        return "break"

    def _on_split_cat_backspace(self, event, row_item):
        if self.voucher_locked_preview:
            return
        if len(self.split_row_widgets) > 1:
            if not row_item["cat"].get() and not row_item["amt"].get().strip() and not row_item["note"].get().strip():
                self._keyboard_delete_split_row(row_item)
                return "break"

    def _keyboard_delete_split_row(self, row_item):
        if self.voucher_locked_preview:
            return "break"
        if len(self.split_row_widgets) <= 1:
            row_item["cat"].set("")
            row_item["amt"].delete(0, tk.END)
            row_item["note"].delete(0, tk.END)
            self.update_split_total_label()
            return "break"
        idx = self.split_row_widgets.index(row_item)
        self.remove_split_row(row_item)
        focus_idx = max(0, idx - 1)
        if self.split_row_widgets:
            self.split_row_widgets[focus_idx]["cat"].entry.focus_set()
        return "break"

    def remove_split_row(self, row_item):
        if self.voucher_locked_preview or len(self.split_row_widgets) <= 1:
            return
        row_item["frame"].destroy()
        if row_item in self.split_row_widgets:
            self.split_row_widgets.remove(row_item)
        self.update_split_total_label()

    def clear_split_rows(self):
        for r in list(self.split_row_widgets):
            r["frame"].destroy()
        self.split_row_widgets.clear()
        if self.is_split_mode:
            self.add_split_row(focus_new=False)
            self.add_split_row(focus_new=False)
        self.update_split_total_label()

    def update_split_total_label(self):
        total = 0.0
        for r in self.split_row_widgets:
            val_s = r["amt"].get().strip()
            if val_s:
                try:
                    total += safe_numeric_eval(val_s)
                except Exception:
                    pass
        rem = self._compute_remaining_voucher_amount()
        if rem > 0.009:
            self.lbl_split_total.configure(text=f"Split Sum: ₹{total:,.2f}  (Rem: ₹{rem:,.2f})", text_color="#D97706")
        else:
            self.lbl_split_total.configure(text=f"Split Sum: ₹{total:,.2f}", text_color="#059669")
        return total

    def focus_voucher_entry(self):
        if not self.book_is_open or self.has_open_modal():
            return
        # If currently viewing a locked preview, Alt+V starts a clean New Entry!
        if self.voucher_locked_preview:
            self.clear_form()
        if self.cmb_type.get() == "Transfer":
            self.ac_account.entry.focus_set()
        elif self.is_split_mode:
            if self.split_target == "account":
                self.ac_category.entry.focus_set()
            elif self.split_row_widgets:
                self.split_row_widgets[0]["cat"].entry.focus_set()
        else:
            self.ac_category.entry.focus_set()

    def focus_voucher_date(self):
        if not self.book_is_open or self.has_open_modal():
            return
        if self.voucher_locked_preview:
            self.clear_form()
        self.ent_date.focus_set()
        self.ent_date.select_range(0, tk.END)

    def prompt_create_category_ledger(self, prefill_text: str):
        default_grp = "Income" if self.cmb_type.get() == "Income" else "Expense"
        self.open_create_ledger_modal(prefill_name=prefill_text, default_group=default_grp, on_success=lambda new_name: (self.refresh_all(), self.ac_category.set(new_name), self.ac_account.entry.focus_set()))

    def prompt_create_account_ledger(self, prefill_text: str):
        self.open_create_ledger_modal(prefill_name=prefill_text, default_group="Bank Account", on_success=lambda new_name: (self.refresh_all(), self.ac_account.set(new_name), self.ent_amount.focus_set()))

    def prompt_create_to_account_ledger(self, prefill_text: str):
        self.open_create_ledger_modal(prefill_name=prefill_text, default_group="Cash in Hand", on_success=lambda new_name: (self.refresh_all(), self.ac_to_account.set(new_name), self.ent_amount.focus_set()))

    def set_voucher_date(self, date_str: str):
        self.ent_date.delete(0, tk.END)
        self.ent_date.insert(0, date_str)

    def on_type_change(self, choice):
        self.close_all_inline_dropdowns()
        if choice == "Transfer":
            if self.is_split_mode:
                self.toggle_split_voucher_mode(steal_focus=False)
            self.cat_container.pack_forget()
            self.acc_container.pack(fill="x", pady=(0, 4), after=self.cmb_type)
            self.lbl_account.configure(text="Transfer From:")
            self.to_acc_container.pack(fill="x", pady=(0, 6), after=self.acc_container)
        elif choice == "Income":
            self.to_acc_container.pack_forget()
            if not self.is_split_mode:
                self.cat_container.pack(fill="x", pady=(0, 4), after=self.cmb_type)
                self.acc_container.pack(fill="x", pady=(0, 4), after=self.cat_container)
            self.lbl_category.configure(text="Income Source / Party:")
            self.lbl_account.configure(text="Received Into:")
        else:
            self.to_acc_container.pack_forget()
            if not self.is_split_mode:
                self.cat_container.pack(fill="x", pady=(0, 4), after=self.cmb_type)
                self.acc_container.pack(fill="x", pady=(0, 4), after=self.cat_container)
            self.lbl_category.configure(text="Category / Asset / Party:")
            self.lbl_account.configure(text="Paid From / Credit Account:")
        self.update_live_voucher_balances()

    def _build_right_structured_views(self):
        self.right_pane_holder.grid_rowconfigure(1, weight=1)
        self.right_pane_holder.grid_columnconfigure(0, weight=1)

        self.nav_header = ctk.CTkFrame(self.right_pane_holder, height=48, corner_radius=10, fg_color=("#FFFFFF", "#1E293B"))
        self.nav_header.grid(row=0, column=0, padx=(3, 0), pady=(0, 6), sticky="ew")
        self.nav_header.grid_columnconfigure((0, 1, 2, 3), weight=1)

        nav_font = ctk.CTkFont(size=13, weight="bold")
        self.btn_nav_home = ctk.CTkButton(self.nav_header, text="🏠 Home Dashboard (Alt+1)", height=36, corner_radius=8, font=nav_font, command=lambda: self.switch_main_tab("home"))
        self.btn_nav_home.grid(row=0, column=0, padx=4, pady=6, sticky="ew")

        self.btn_nav_daybook = ctk.CTkButton(self.nav_header, text="📒 All Transactions (Alt+2)", height=36, corner_radius=8, font=nav_font, command=lambda: self.switch_main_tab("daybook"))
        self.btn_nav_daybook.grid(row=0, column=1, padx=4, pady=6, sticky="ew")

        self.btn_nav_ledgers = ctk.CTkButton(self.nav_header, text="⚙️ Manage Ledgers (Alt+3)", height=36, corner_radius=8, font=nav_font, command=lambda: self.switch_main_tab("ledgers"))
        self.btn_nav_ledgers.grid(row=0, column=2, padx=4, pady=6, sticky="ew")

        self.btn_nav_reports = ctk.CTkButton(self.nav_header, text="📈 Trial Bal / P&L / B/S (Alt+4)", height=36, corner_radius=8, font=nav_font, command=lambda: self.switch_main_tab("reports"))
        self.btn_nav_reports.grid(row=0, column=3, padx=4, pady=6, sticky="ew")

        self.right_body = ctk.CTkFrame(self.right_pane_holder, corner_radius=10, fg_color=("#FFFFFF", "#1E293B"))
        self.right_body.grid(row=1, column=0, padx=(3, 0), sticky="nsew")
        self.right_body.grid_rowconfigure(0, weight=1)
        self.right_body.grid_columnconfigure(0, weight=1)

        self.tab_home = ctk.CTkFrame(self.right_body, fg_color="transparent")
        self.tab_daybook = ctk.CTkFrame(self.right_body, fg_color="transparent")
        self.tab_ledgers = ctk.CTkFrame(self.right_body, fg_color="transparent")
        self.tab_reports = ctk.CTkFrame(self.right_body, fg_color="transparent")

        self._build_home_dashboard_ui()
        self._build_daybook_ui()
        self._build_ledgers_and_profile_ui()
        self._build_financial_reports_ui()

        self.switch_main_tab("home")

    def _focus_and_select_tree(self, tree_widget, sync_form=False):
        children = tree_widget.get_children()
        tree_widget.focus_set()
        if children:
            cur = tree_widget.selection()
            target = cur[0] if (cur and cur[0] in children) else children[0]
            tree_widget.selection_set(target)
            tree_widget.focus(target)
            tree_widget.see(target)
            if sync_form and tree_widget in (self.tree, self.prof_tree):
                vals = tree_widget.item(target).get("values", [])
                if vals:
                    self._load_from_tree_item_values(vals, lock_preview=True)

    def _move_tree_selection_from_search(self, tree_widget, delta: int, sync_form=False):
        children = list(tree_widget.get_children())
        if not children:
            return "break"
        cur = tree_widget.selection()
        if not cur or cur[0] not in children:
            idx = 0
        else:
            idx = max(0, min(len(children) - 1, children.index(cur[0]) + delta))
        target = children[idx]
        tree_widget.selection_set(target)
        tree_widget.focus(target)
        tree_widget.see(target)
        if sync_form and tree_widget in (self.tree, self.prof_tree):
            vals = tree_widget.item(target).get("values", [])
            if vals:
                self._load_from_tree_item_values(vals, lock_preview=True)
        return "break"

    def _load_from_tree_item_values(self, vals, lock_preview=True):
        if not vals:
            return
        raw_id = str(vals[0])
        if raw_id.startswith("S#"):
            grp_id = int(raw_id.replace("S#", ""))
            rows = self.db.get_split_group_rows(grp_id)
            if rows:
                self.load_tx_into_form(rows[0][0], lock_preview=lock_preview)
        else:
            try:
                self.load_tx_into_form(int(raw_id), lock_preview=lock_preview)
            except Exception:
                pass

    def switch_main_tab(self, tab_key: str):
        self.current_tab_key = tab_key
        for f in (self.tab_home, self.tab_daybook, self.tab_ledgers, self.tab_reports):
            f.grid_forget()

        active_col = "#2563EB"
        inactive_col = "#E2E8F0"
        active_txt = "#FFFFFF"
        inactive_txt = "#0F172A"

        for k, btn in [("home", self.btn_nav_home), ("daybook", self.btn_nav_daybook), ("ledgers", self.btn_nav_ledgers), ("reports", self.btn_nav_reports)]:
            btn.configure(fg_color=active_col if tab_key == k else inactive_col, text_color=active_txt if tab_key == k else inactive_txt)

        if tab_key == "home":
            self.tab_home.grid(row=0, column=0, sticky="nsew")
        elif tab_key == "daybook":
            self.tab_daybook.grid(row=0, column=0, sticky="nsew")
            self.after(40, lambda: self._focus_and_select_tree(self.tree, sync_form=False))
        elif tab_key == "ledgers":
            self.tab_ledgers.grid(row=0, column=0, sticky="nsew")
            if self.active_drill_ledger:
                self.after(40, lambda: self._focus_and_select_tree(self.prof_tree, sync_form=False))
            else:
                self.after(40, lambda: self._focus_and_select_tree(self.manage_tree, sync_form=False))
        else:
            self.tab_reports.grid(row=0, column=0, sticky="nsew")
            self.refresh_financial_reports_tab()
            self.after(40, lambda: self._focus_and_select_tree(self.fin_tree, sync_form=False))

    # ==========================================================================
    # HOME DASHBOARD: VERTICAL STACK ON LEFT (TOP OUTFLOWS + DUE/PAY LATER) & GATEWAY SPACE ON RIGHT
    # ==========================================================================
    def _build_home_dashboard_ui(self):
        self.tab_home.grid_columnconfigure(0, weight=5)
        self.tab_home.grid_columnconfigure(1, weight=5)
        self.tab_home.grid_rowconfigure(1, weight=1)
        self.tab_home.grid_rowconfigure(2, weight=1)

        action_bar = ctk.CTkFrame(self.tab_home, corner_radius=10, fg_color=("#F1F5F9", "#0F172A"))
        action_bar.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 6), sticky="ew")

        ctk.CTkLabel(action_bar, text="⚡ Quick Actions:", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left", padx=(12, 8), pady=8)
        ctk.CTkButton(action_bar, text="🏢 Switch Book (F3)", height=30, fg_color="#2563EB", command=self.show_company_gateway_screen).pack(side="left", padx=4, pady=8)
        ctk.CTkButton(action_bar, text="➕ Create Ledger (Ctrl+L)", height=30, fg_color="#059669", command=lambda: self.open_create_ledger_modal(on_success=lambda _: self.refresh_all())).pack(side="left", padx=4, pady=8)
        ctk.CTkButton(action_bar, text="📈 Financial Reports (Alt+4)", height=30, fg_color="#7C3AED", command=lambda: self.switch_main_tab("reports")).pack(side="left", padx=4, pady=8)
        ctk.CTkButton(action_bar, text="📌 Pin Top Banks", height=30, fg_color="#475569", command=self.open_pin_manager_dialog).pack(side="left", padx=4, pady=8)
        ctk.CTkButton(action_bar, text="💾 Backup Book", height=30, fg_color="#D97706", command=self.backup_database_now).pack(side="right", padx=12, pady=8)

        exp_outer = ctk.CTkFrame(self.tab_home, corner_radius=10, fg_color=("#F8FAFC", "#1E293B"), border_width=1, border_color="#CBD5E1")
        exp_outer.grid(row=1, column=0, padx=(10, 5), pady=(4, 5), sticky="nsew")
        exp_outer.grid_rowconfigure(1, weight=1)
        exp_outer.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(exp_outer, text="📉 Top Outflows Breakdown (Click Any Item to Open Ledger)", font=ctk.CTkFont(size=13, weight="bold"), anchor="w").grid(row=0, column=0, padx=12, pady=(8, 2), sticky="ew")
        self.home_exp_card = ctk.CTkScrollableFrame(exp_outer, corner_radius=8, fg_color="transparent")
        self.home_exp_card.grid(row=1, column=0, padx=6, pady=(0, 6), sticky="nsew")

        due_outer = ctk.CTkFrame(self.tab_home, corner_radius=10, fg_color=("#F8FAFC", "#1E293B"), border_width=1, border_color="#CBD5E1")
        due_outer.grid(row=2, column=0, padx=(10, 5), pady=(5, 10), sticky="nsew")
        due_outer.grid_rowconfigure(1, weight=1)
        due_outer.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(due_outer, text="🤝 Due / Pay Later & Party Balances (Receivables & Payables)", font=ctk.CTkFont(size=13, weight="bold"), anchor="w").grid(row=0, column=0, padx=12, pady=(8, 2), sticky="ew")
        self.home_lenden_card = ctk.CTkScrollableFrame(due_outer, corner_radius=8, fg_color="transparent")
        self.home_lenden_card.grid(row=1, column=0, padx=6, pady=(0, 6), sticky="nsew")

        self.gateway_right_panel = ctk.CTkFrame(self.tab_home, corner_radius=10, fg_color=("#F8FAFC", "#1E293B"), border_width=1, border_color="#CBD5E1")
        self.gateway_right_panel.grid(row=1, column=1, rowspan=2, padx=(5, 10), pady=(4, 10), sticky="nsew")
        self.gateway_right_panel.grid_columnconfigure(0, weight=1)
        self.gateway_right_panel.grid_rowconfigure(1, weight=1)

        gw_hdr = ctk.CTkFrame(self.gateway_right_panel, corner_radius=8, fg_color="#1E3A8A")
        gw_hdr.grid(row=0, column=0, padx=12, pady=(12, 6), sticky="ew")
        ctk.CTkLabel(gw_hdr, text="GATEWAY OF TALLY (COMMAND PANEL)", font=ctk.CTkFont(size=14, weight="bold"), text_color="#FFFFFF").pack(pady=8)

        gw_placeholder = ctk.CTkFrame(self.gateway_right_panel, fg_color="transparent")
        gw_placeholder.grid(row=1, column=0, padx=16, pady=16, sticky="nsew")
        ctk.CTkLabel(
            gw_placeholder,
            text="Reserved for Gateway of Tally Menu\n(Phase 3 Implementation)",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#64748B",
            justify="center"
        ).pack(expand=True)

    # ==========================================================================
    # TAB 2: ALL TRANSACTIONS / DAYBOOK (COLLAPSIBLE TREE-MAP + UNLOCK EDIT BUTTON)
    # ==========================================================================
    def _build_daybook_ui(self):
        self.tab_daybook.grid_rowconfigure(2, weight=1)
        self.tab_daybook.grid_columnconfigure(0, weight=1)

        f_bar = ctk.CTkFrame(self.tab_daybook, fg_color="transparent")
        f_bar.grid(row=0, column=0, padx=8, pady=(8, 4), sticky="ew")

        self.ent_search = ctk.CTkEntry(f_bar, placeholder_text="🔍 Search (Up/Down arrows jump to rows)...", width=200)
        self.ent_search.pack(side="left", padx=(0, 4))
        self.ent_search.bind("<KeyRelease>", self.on_daybook_search_key)
        self.ent_search.bind("<Down>", lambda e: self._move_tree_selection_from_search(self.tree, 1, sync_form=True))
        self.ent_search.bind("<Up>", lambda e: self._move_tree_selection_from_search(self.tree, -1, sync_form=True))
        self.ent_search.bind("<Return>", lambda e: self.on_daybook_double_click(None))

        ctk.CTkLabel(f_bar, text="Type:").pack(side="left", padx=(4, 2))
        self.flt_type = ctk.CTkOptionMenu(f_bar, values=["All", "Expense", "Income", "Transfer"], width=100, command=lambda _: self.refresh_daybook_table(focus_table=True))
        self.flt_type.set("All")
        self.flt_type.pack(side="left", padx=2)

        ctk.CTkLabel(f_bar, text="Account:").pack(side="left", padx=(4, 2))
        self.flt_account = ctk.CTkOptionMenu(f_bar, values=["All"] + self.payment_accounts, width=115, command=lambda _: self.refresh_daybook_table(focus_table=True))
        self.flt_account.set("All")
        self.flt_account.pack(side="left", padx=2)

        ctk.CTkLabel(f_bar, text="Ledger:").pack(side="left", padx=(4, 2))
        self.flt_cat = ctk.CTkOptionMenu(f_bar, values=["All"] + self.voucher_ledgers, width=120, command=lambda _: self.refresh_daybook_table(focus_table=True))
        self.flt_cat.set("All")
        self.flt_cat.pack(side="left", padx=2)

        ctk.CTkButton(f_bar, text="🗑 Delete", width=75, fg_color="#DC2626", hover_color="#B91C1C", command=self.delete_entry).pack(side="right", padx=2)
        ctk.CTkButton(f_bar, text="📊 CSV", width=65, fg_color="#059669", command=self.export_daybook_csv).pack(side="right", padx=2)
        ctk.CTkButton(f_bar, text="🔓 Edit (Alt+E)", width=105, fg_color="#2563EB", hover_color="#1D4ED8", command=self.unlock_voucher_for_editing).pack(side="right", padx=3)

        tot_strip = ctk.CTkFrame(self.tab_daybook, corner_radius=8, fg_color=("#F1F5F9", "#0F172A"))
        tot_strip.grid(row=1, column=0, padx=8, pady=(0, 6), sticky="ew")

        self.lbl_daybook_summary = ctk.CTkLabel(
            tot_strip,
            text="📋 Entries: 0   |   Total In: ₹0.00   |   Total Out: ₹0.00   |   Net: ₹0.00",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#0F172A"
        )
        self.lbl_daybook_summary.pack(side="left", padx=12, pady=5)

        self.lbl_daybook_closing = ctk.CTkLabel(tot_strip, text="", font=ctk.CTkFont(size=12, weight="bold"), text_color="#2563EB")
        self.lbl_daybook_closing.pack(side="right", padx=12, pady=5)

        t_frame = ctk.CTkFrame(self.tab_daybook)
        t_frame.grid(row=2, column=0, padx=8, pady=(0, 8), sticky="nsew")
        t_frame.grid_rowconfigure(0, weight=1)
        t_frame.grid_columnconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", rowheight=29, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

        cols = ("ID", "Date", "Type", "Category / Ledger", "Paid From / Mode", "Description", "Income (₹)", "Expense (₹)", "Double-Entry (Dr → Cr)")
        self.tree = ttk.Treeview(t_frame, columns=cols, show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="Tree")
        self.tree.column("#0", width=36, stretch=False, anchor="center")

        widths = [55, 90, 95, 135, 140, 220, 95, 95, 175]
        for col, w in zip(cols, widths):
            self.tree.heading(col, text=col)
            align = "e" if "₹" in col else ("center" if col in ("ID", "Date", "Type") else "w")
            self.tree.column(col, width=w, anchor=align)

        self.tree.tag_configure("split_parent", background="#EFF6FF", font=("Segoe UI", 10, "bold"))
        self.tree.tag_configure("split_child", background="#F8FAFC", foreground="#475569")

        vsb = ttk.Scrollbar(t_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        self.tree.bind("<<TreeviewSelect>>", self.on_daybook_row_select)
        self.tree.bind("<Double-1>", self.on_daybook_double_click)
        self.tree.bind("<Return>", self.on_daybook_double_click)
        self.tree.bind("<space>", self.on_daybook_space_toggle_tree)

    def on_daybook_space_toggle_tree(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        item_id = sel[0]
        if self.tree.get_children(item_id):
            is_open = bool(self.tree.item(item_id, "open"))
            self.tree.item(item_id, open=not is_open)
        return "break"

    def on_daybook_search_key(self, event):
        if event.keysym in ("Up", "Down", "Return", "Escape"):
            return
        self.refresh_daybook_table(focus_table=False)

    # ==========================================================================
    # TAB 3: MANAGE LEDGERS (ZERO-MOUSE KEYBOARD ARROWS + ENTER STATEMENT OPEN)
    # ==========================================================================
    def _build_ledgers_and_profile_ui(self):
        self.tab_ledgers.grid_rowconfigure(0, weight=1)
        self.tab_ledgers.grid_columnconfigure(0, weight=1)

        self.ledger_list_page = ctk.CTkFrame(self.tab_ledgers, fg_color="transparent")
        self.ledger_list_page.grid(row=0, column=0, sticky="nsew")
        self.ledger_list_page.grid_rowconfigure(1, weight=1)
        self.ledger_list_page.grid_columnconfigure(0, weight=1)

        top_bar = ctk.CTkFrame(self.ledger_list_page, corner_radius=8, fg_color=("#F1F5F9", "#0F172A"))
        top_bar.grid(row=0, column=0, padx=8, pady=8, sticky="ew")

        self.ent_ledger_search = ctk.CTkEntry(top_bar, placeholder_text="🔍 Search ledger (Up/Down arrows + Enter)...", width=265)
        self.ent_ledger_search.pack(side="left", padx=8, pady=8)
        self.ent_ledger_search.bind("<KeyRelease>", self.on_ledger_search_key)
        self.ent_ledger_search.bind("<Down>", lambda e: self._move_tree_selection_from_search(self.manage_tree, 1))
        self.ent_ledger_search.bind("<Up>", lambda e: self._move_tree_selection_from_search(self.manage_tree, -1))
        self.ent_ledger_search.bind("<Return>", self.on_ledger_search_enter)

        ctk.CTkLabel(top_bar, text="Filter Group:").pack(side="left", padx=(6, 2))
        self.flt_ledger_group = ctk.CTkOptionMenu(top_bar, values=["All"] + LEDGER_GROUPS, width=200, command=lambda _: self.refresh_manage_ledgers_table(focus_table=True))
        self.flt_ledger_group.set("All")
        self.flt_ledger_group.pack(side="left", padx=4)

        ctk.CTkButton(top_bar, text="➕ New Ledger", fg_color="#059669", command=lambda: self.open_create_ledger_modal(on_success=lambda _: self.refresh_all())).pack(side="right", padx=8, pady=8)
        ctk.CTkButton(top_bar, text="🗑 Delete", width=80, fg_color="#DC2626", command=self.delete_selected_ledger_from_master).pack(side="right", padx=4, pady=8)
        ctk.CTkButton(top_bar, text="✏️ Edit", fg_color="#D97706", command=self.edit_selected_ledger_from_master).pack(side="right", padx=4, pady=8)
        ctk.CTkButton(top_bar, text="📂 Open Statement (Enter)", fg_color="#2563EB", command=self.open_selected_ledger_profile).pack(side="right", padx=4, pady=8)

        l_table_frame = ctk.CTkFrame(self.ledger_list_page)
        l_table_frame.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")
        l_table_frame.grid_rowconfigure(0, weight=1)
        l_table_frame.grid_columnconfigure(0, weight=1)

        cols = ("Ledger Name", "Account Type", "Entries", "Closing Balance")
        self.manage_tree = ttk.Treeview(l_table_frame, columns=cols, show="headings", selectmode="browse")
        widths = [260, 240, 110, 240]
        for c, w in zip(cols, widths):
            self.manage_tree.heading(c, text=c)
            align = "e" if "Balance" in c else ("center" if c == "Entries" else "w")
            self.manage_tree.column(c, width=w, anchor=align)

        vsb = ttk.Scrollbar(l_table_frame, orient="vertical", command=self.manage_tree.yview)
        self.manage_tree.configure(yscrollcommand=vsb.set)
        self.manage_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        self.manage_tree.bind("<Double-1>", lambda e: self.open_selected_ledger_profile())
        self.manage_tree.bind("<Return>", lambda e: self.open_selected_ledger_profile())

        self.ledger_profile_page = ctk.CTkFrame(self.tab_ledgers, fg_color="transparent")
        self.ledger_profile_page.grid_rowconfigure(2, weight=1)
        self.ledger_profile_page.grid_columnconfigure(0, weight=1)

        prof_nav = ctk.CTkFrame(self.ledger_profile_page, fg_color="transparent")
        prof_nav.grid(row=0, column=0, padx=8, pady=(6, 4), sticky="ew")

        ctk.CTkButton(prof_nav, text="⬅ Back (ESC)", width=130, fg_color="#334155", command=self.close_ledger_profile).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(prof_nav, text="Switch Ledger:").pack(side="left", padx=4)
        self.cmb_prof_switch = ctk.CTkComboBox(prof_nav, values=self.all_ledgers, width=200, command=self.open_ledger_profile_by_name)
        self.cmb_prof_switch.pack(side="left", padx=4)

        ctk.CTkButton(prof_nav, text="🖨 Print / PDF", width=110, fg_color="#7C3AED", command=self.export_active_profile_html_pdf).pack(side="right", padx=4)
        ctk.CTkButton(prof_nav, text="📊 CSV", width=95, fg_color="#059669", command=self.export_active_profile_csv).pack(side="right", padx=4)
        ctk.CTkButton(prof_nav, text="✏️ Edit Ledger", width=105, fg_color="#D97706", command=self.edit_active_profile_ledger).pack(side="right", padx=4)

        self.prof_banner = ctk.CTkFrame(self.ledger_profile_page, corner_radius=10, fg_color=("#F1F5F9", "#0F172A"))
        self.prof_banner.grid(row=1, column=0, padx=8, pady=4, sticky="ew")
        self.prof_banner.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        self.lbl_prof_title = ctk.CTkLabel(self.prof_banner, text="Ledger Name", font=ctk.CTkFont(size=18, weight="bold"))
        self.lbl_prof_title.grid(row=0, column=0, padx=14, pady=(10, 2), sticky="w")
        self.lbl_prof_sub = ctk.CTkLabel(self.prof_banner, text="Group", font=ctk.CTkFont(size=12), text_color="#2563EB")
        self.lbl_prof_sub.grid(row=1, column=0, padx=14, pady=(0, 10), sticky="w")

        self.lbl_prof_op = self._create_mini_stat(self.prof_banner, 1, "OPENING", "#475569")
        self.lbl_prof_dr = self._create_mini_stat(self.prof_banner, 2, "MONEY IN (Dr)", "#059669")
        self.lbl_prof_cr = self._create_mini_stat(self.prof_banner, 3, "MONEY OUT (Cr)", "#DC2626")
        self.lbl_prof_bal = self._create_mini_stat(self.prof_banner, 4, "CLOSING BALANCE", "#7C3AED")

        prof_body = ctk.CTkFrame(self.ledger_profile_page)
        prof_body.grid(row=2, column=0, padx=8, pady=(4, 8), sticky="nsew")
        prof_body.grid_rowconfigure(1, weight=1)
        prof_body.grid_columnconfigure(0, weight=1)

        pf_bar = ctk.CTkFrame(prof_body, fg_color="transparent")
        pf_bar.grid(row=0, column=0, columnspan=2, padx=8, pady=6, sticky="ew")
        ctk.CTkLabel(pf_bar, text="Filter:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 6))
        self.ent_prof_search = ctk.CTkEntry(pf_bar, placeholder_text="Search description (Up/Down arrows work)...", width=230)
        self.ent_prof_search.pack(side="left", padx=4)
        self.ent_prof_search.bind("<KeyRelease>", self.on_prof_search_key)
        self.ent_prof_search.bind("<Down>", lambda e: self._move_tree_selection_from_search(self.prof_tree, 1, sync_form=True))
        self.ent_prof_search.bind("<Up>", lambda e: self._move_tree_selection_from_search(self.prof_tree, -1, sync_form=True))

        ctk.CTkLabel(pf_bar, text="Period:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(10, 4))
        self.cmb_prof_period = ctk.CTkOptionMenu(pf_bar, values=["Same as Top Filter"] + ANALYTICS_PERIODS, width=155, command=lambda _: self.refresh_active_profile_view())
        self.cmb_prof_period.set("Same as Top Filter")
        self.cmb_prof_period.pack(side="left", padx=4)

        ctk.CTkButton(pf_bar, text="🗑 Delete", width=85, fg_color="#DC2626", command=self.delete_entry_from_profile).pack(side="right", padx=3)
        ctk.CTkButton(pf_bar, text="🔓 Edit Entry (Alt+E)", width=130, fg_color="#2563EB", command=self.unlock_voucher_for_editing).pack(side="right", padx=3)

        cols = ("ID", "Date", "Type", "Opposite Account", "Description", "Money In / Dr (₹)", "Money Out / Cr (₹)", "Running Balance (₹)")
        self.prof_tree = ttk.Treeview(prof_body, columns=cols, show="headings", selectmode="browse")
        widths = [45, 95, 80, 180, 240, 110, 110, 135]
        for c, w in zip(cols, widths):
            self.prof_tree.heading(c, text=c)
            align = "e" if "₹" in c else ("center" if c in ("ID", "Date", "Type") else "w")
            self.prof_tree.column(c, width=w, anchor=align)

        vsb2 = ttk.Scrollbar(prof_body, orient="vertical", command=self.prof_tree.yview)
        self.prof_tree.configure(yscrollcommand=vsb2.set)
        self.prof_tree.grid(row=1, column=0, sticky="nsew", padx=(8, 0), pady=(0, 8))
        vsb2.grid(row=1, column=1, sticky="ns", padx=(0, 8), pady=(0, 8))
        self.prof_tree.bind("<<TreeviewSelect>>", self.on_profile_tx_select)

    def on_ledger_search_key(self, event):
        if event.keysym in ("Up", "Down", "Return", "Escape"):
            return
        self.refresh_manage_ledgers_table(focus_table=False)

    def on_prof_search_key(self, event):
        if event.keysym in ("Up", "Down", "Return", "Escape"):
            return
        self.refresh_active_profile_view(focus_table=False)

    def on_ledger_search_enter(self, event):
        children = self.manage_tree.get_children()
        if children:
            cur = self.manage_tree.selection()
            if not cur:
                self.manage_tree.selection_set(children[0])
            self.open_selected_ledger_profile()

    def _create_mini_stat(self, parent, col, title, color):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid(row=0, column=col, rowspan=2, padx=8, pady=8, sticky="ew")
        ctk.CTkLabel(f, text=title, font=ctk.CTkFont(size=10, weight="bold"), text_color="gray").pack()
        lbl = ctk.CTkLabel(f, text="₹0.00", font=ctk.CTkFont(size=15, weight="bold"), text_color=color)
        lbl.pack()
        return lbl

    # ==========================================================================
    # TAB 4: FINANCIAL REPORTS (TB, P&L, B/S WITH KEYBOARD ENTER & ARROWS)
    # ==========================================================================
    def _build_financial_reports_ui(self):
        self.tab_reports.grid_rowconfigure(1, weight=1)
        self.tab_reports.grid_columnconfigure(0, weight=1)

        top_bar = ctk.CTkFrame(self.tab_reports, corner_radius=8, fg_color=("#F1F5F9", "#0F172A"))
        top_bar.grid(row=0, column=0, padx=10, pady=(8, 4), sticky="ew")

        self.seg_fin_report = ctk.CTkSegmentedButton(
            top_bar, values=["⚖️ Trial Balance", "📊 Profit & Loss A/c", "🏛 Balance Sheet"],
            height=32, font=ctk.CTkFont(size=13, weight="bold"), command=lambda _: (self.refresh_financial_reports_tab(), self._focus_and_select_tree(self.fin_tree))
        )
        self.seg_fin_report.set("⚖️ Trial Balance")
        self.seg_fin_report.pack(side="left", padx=10, pady=8)

        self.lbl_fin_verify = ctk.CTkLabel(top_bar, text="✔ Double-Entry Verified", font=ctk.CTkFont(size=12, weight="bold"), text_color="#059669")
        self.lbl_fin_verify.pack(side="left", padx=14)

        ctk.CTkButton(top_bar, text="🖨 Print Reports PDF", height=30, fg_color="#7C3AED", command=self.export_financial_statements_html_pdf).pack(side="right", padx=10, pady=8)

        self.fin_body = ctk.CTkFrame(self.tab_reports)
        self.fin_body.grid(row=1, column=0, padx=10, pady=(2, 10), sticky="nsew")
        self.fin_body.grid_rowconfigure(0, weight=1)
        self.fin_body.grid_columnconfigure(0, weight=1)

        cols = ("Col1", "Col2", "Col3", "Col4", "Col5")
        self.fin_tree = ttk.Treeview(self.fin_body, columns=cols, show="headings", selectmode="browse")
        vsb = ttk.Scrollbar(self.fin_body, orient="vertical", command=self.fin_tree.yview)
        self.fin_tree.configure(yscrollcommand=vsb.set)
        self.fin_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        self.fin_tree.bind("<Double-1>", self.on_fin_tree_double_click)
        self.fin_tree.bind("<Return>", self.on_fin_tree_double_click)

    def on_fin_tree_double_click(self, event):
        sel = self.fin_tree.selection()
        if not sel:
            return
        vals = self.fin_tree.item(sel[0])["values"]
        if vals and vals[0] and not str(vals[0]).startswith("═") and "TOTAL" not in str(vals[0]):
            l_name = str(vals[0]).split(" (")[0].strip()
            if self.db.ledger_exists(l_name):
                self.open_ledger_profile_by_name(l_name)

    def refresh_financial_reports_tab(self):
        if not self.book_is_open:
            return
        c_from = self.ent_custom_from.get().strip()
        c_to = self.ent_custom_to.get().strip()
        fin = self.db.get_financial_statements(self.current_period, c_from, c_to)
        mode = self.seg_fin_report.get()

        for r in self.fin_tree.get_children():
            self.fin_tree.delete(r)

        if mode == "⚖️ Trial Balance":
            headers = [("Col1", "Ledger Account", 240, "w"), ("Col2", "Account Type", 210, "w"), ("Col3", "Opening (₹)", 120, "e"), ("Col4", "Closing Debit (₹)", 150, "e"), ("Col5", "Closing Credit (₹)", 150, "e")]
            for c_id, h_txt, w, al in headers:
                self.fin_tree.heading(c_id, text=h_txt)
                self.fin_tree.column(c_id, width=w, anchor=al)

            for r in fin["trial_balance"]:
                dr_s = f"₹{r['closing_dr']:,.2f}" if r["closing_dr"] > 0 else "-"
                cr_s = f"₹{r['closing_cr']:,.2f}" if r["closing_cr"] > 0 else "-"
                self.fin_tree.insert("", tk.END, values=(r["name"], r["group"], f"₹{r['opening']:,.2f}", dr_s, cr_s))

            self.fin_tree.insert("", tk.END, values=("════════════════════", "════════════════", "══════════", "══════════════", "══════════════"))
            self.fin_tree.insert("", tk.END, values=("TOTAL TRIAL BALANCE", "", "", f"₹{fin['tb_total_dr']:,.2f}", f"₹{fin['tb_total_cr']:,.2f}"))
            self.lbl_fin_verify.configure(text=f"✔ Trial Balance — Total Dr: ₹{fin['tb_total_dr']:,.2f}  |  Total Cr: ₹{fin['tb_total_cr']:,.2f}")

        elif mode == "📊 Profit & Loss A/c":
            headers = [("Col1", "Expenses (Dr)", 240, "w"), ("Col2", "Expense Amt (₹)", 140, "e"), ("Col3", "│", 30, "center"), ("Col4", "Incomes / Revenue (Cr)", 240, "w"), ("Col5", "Income Amt (₹)", 140, "e")]
            for c_id, h_txt, w, al in headers:
                self.fin_tree.heading(c_id, text=h_txt)
                self.fin_tree.column(c_id, width=w, anchor=al)

            exps = list(fin["pnl_expenses"])
            incs = list(fin["pnl_incomes"])
            net_p = fin["net_profit"]
            if net_p >= 0:
                exps.append(("🟢 NET PROFIT / SAVINGS", net_p))
            else:
                incs.append(("🔴 NET DEFICIT / LOSS", abs(net_p)))

            max_len = max(len(exps), len(incs), 1)
            for i in range(max_len):
                e_n, e_a = exps[i] if i < len(exps) else ("", None)
                i_n, i_a = incs[i] if i < len(incs) else ("", None)
                self.fin_tree.insert("", tk.END, values=(e_n, f"₹{e_a:,.2f}" if e_a is not None else "", "│", i_n, f"₹{i_a:,.2f}" if i_a is not None else ""))

            grand_tot = max(fin["total_pnl_inc"], fin["total_pnl_exp"])
            self.fin_tree.insert("", tk.END, values=("════════════════════", "════════════", "│", "════════════════════", "════════════"))
            self.fin_tree.insert("", tk.END, values=("TOTAL", f"₹{grand_tot:,.2f}", "│", "TOTAL", f"₹{grand_tot:,.2f}"))
            p_tag = f"Net Profit / Savings: ₹{net_p:,.2f}" if net_p >= 0 else f"Net Deficit: -₹{abs(net_p):,.2f}"
            self.lbl_fin_verify.configure(text=f"📊 {p_tag}")

        else:
            headers = [("Col1", "Liabilities & Surplus (Cr)", 250, "w"), ("Col2", "Amount (₹)", 140, "e"), ("Col3", "│", 30, "center"), ("Col4", "Assets & Properties (Dr)", 250, "w"), ("Col5", "Amount (₹)", 140, "e")]
            for c_id, h_txt, w, al in headers:
                self.fin_tree.heading(c_id, text=h_txt)
                self.fin_tree.column(c_id, width=w, anchor=al)

            liabs = [(f"{n} ({g})", a) for n, g, a in fin["bs_liabilities"]]
            if abs(fin["opening_capital"]) > 0.005:
                liabs.append(("Opening Capital Offset", fin["opening_capital"]))
            if fin["net_profit"] != 0:
                lbl_s = "Net Profit / Savings" if fin["net_profit"] >= 0 else "Less: Net Deficit"
                liabs.append((lbl_s, fin["net_profit"]))

            assets = [(f"{n} ({g})", a) for n, g, a in fin["bs_assets"]]
            max_len = max(len(liabs), len(assets), 1)
            for i in range(max_len):
                l_n, l_a = liabs[i] if i < len(liabs) else ("", None)
                a_n, a_a = assets[i] if i < len(assets) else ("", None)
                self.fin_tree.insert("", tk.END, values=(l_n, f"₹{l_a:,.2f}" if l_a is not None else "", "│", a_n, f"₹{a_a:,.2f}" if a_a is not None else ""))

            self.fin_tree.insert("", tk.END, values=("════════════════════", "════════════", "│", "════════════════════", "════════════"))
            self.fin_tree.insert("", tk.END, values=("TOTAL LIABILITIES & SURPLUS", f"₹{fin['total_liabilities_and_equity']:,.2f}", "│", "TOTAL ASSETS", f"₹{fin['total_assets']:,.2f}"))
            self.lbl_fin_verify.configure(text=f"🏛 Balance Sheet Matched — Total Assets: ₹{fin['total_assets']:,.2f} == Liabilities: ₹{fin['total_liabilities_and_equity']:,.2f}")

        children = self.fin_tree.get_children()
        if children:
            self.fin_tree.selection_set(children[0])
            self.fin_tree.focus(children[0])

    # ==========================================================================
    # TALLY-STYLE ESCAPE KEY HANDLING
    # ==========================================================================
    def on_global_escape(self, event=None):
        if self.has_open_modal():
            self.active_modal.close_modal()
            return
        if self._any_inline_dropdown_open():
            self.close_all_inline_dropdowns()
            return
        if self.calc_visible:
            self.toggle_calculator_bar()
            return

        # 1. If actively editing an existing unlocked voucher -> Tally Quit/Lock prompt
        if (self.selected_tx_id is not None or self.selected_voucher_group_id > 0) and not self.voucher_locked_preview:
            if messagebox.askyesno("Cancel Edit? (Tally ESC)", "Discard unsaved edits and lock this voucher back?"):
                if self.selected_tx_id is not None:
                    self.load_tx_into_form(self.selected_tx_id, lock_preview=True)
                self._return_focus_to_active_table()
            return

        # 2. If mid-way typing a brand-new voucher -> Tally Quit/Clear prompt
        if self.selected_tx_id is None and self.selected_voucher_group_id == 0 and self.has_unsaved_voucher_draft():
            if messagebox.askyesno("Quit Voucher Entry? (Tally ESC)", "Clear / Quit the current unsaved voucher entry?"):
                self.clear_form()
            return

        # 3. If viewing a single ledger statement -> Back to Manage Ledgers list
        if self.active_drill_ledger and self.current_tab_key == "ledgers":
            self.close_ledger_profile()
            return

        # 4. If viewing a locked preview -> Clear preview back to New Entry Mode & keep focus on table
        if self.voucher_locked_preview:
            self.clear_form()
            self._return_focus_to_active_table()

    def _return_focus_to_active_table(self):
        if self.current_tab_key == "daybook":
            self.tree.focus_set()
        elif self.current_tab_key == "ledgers":
            if self.active_drill_ledger:
                self.prof_tree.focus_set()
            else:
                self.manage_tree.focus_set()
        elif self.current_tab_key == "reports":
            self.fin_tree.focus_set()

    def switch_voucher_mode(self, mode: str):
        if not self.book_is_open or self.has_open_modal():
            return
        if self.voucher_locked_preview:
            self.clear_form()
        self.cmb_type.set(mode)
        self.on_type_change(mode)
        self.focus_voucher_entry()

    def save_entry(self):
        if not self.book_is_open or self.has_open_modal():
            return
        if self.voucher_locked_preview:
            self.unlock_voucher_for_editing()
            return

        self.close_all_inline_dropdowns()
        tx_date = self.ent_date.get().strip()
        tx_type = self.cmb_type.get()

        if self.is_split_mode and tx_type in ("Expense", "Income"):
            if self.split_target == "account":
                main_ledger = self.ac_category.get().strip()
                if not main_ledger or main_ledger == CREATE_NEW_OPTION or not self.db.ledger_exists(main_ledger):
                    prefill = "" if main_ledger == CREATE_NEW_OPTION else main_ledger
                    self.prompt_create_category_ledger(prefill)
                    return
            else:
                main_ledger = self.ac_account.get().strip()
                if not main_ledger or main_ledger == CREATE_NEW_OPTION or not self.db.ledger_exists(main_ledger):
                    prefill = "" if main_ledger == CREATE_NEW_OPTION else main_ledger
                    self.prompt_create_account_ledger(prefill)
                    return

            split_lines = []
            split_sum = 0.0
            general_note = sanitize_narration(self.ent_desc.get())

            for idx, r in enumerate(self.split_row_widgets, start=1):
                c_name = r["cat"].get().strip()
                a_str = r["amt"].get().strip()
                n_str = sanitize_narration(r["note"].get()) or general_note
                if not a_str and not n_str and not c_name:
                    continue
                if not c_name or c_name == CREATE_NEW_OPTION or not self.db.ledger_exists(c_name):
                    def_grp = "Bank Account" if self.split_target == "account" else ("Income" if tx_type == "Income" else "Expense")
                    prefill = "" if c_name == CREATE_NEW_OPTION else c_name
                    self.open_create_ledger_modal(prefill_name=prefill, default_group=def_grp, on_success=lambda saved_n, rw=r: (self.refresh_all(), rw["cat"].set(saved_n)))
                    return
                if c_name.lower() == main_ledger.lower():
                    messagebox.showwarning("Same Ledger Error", f"Split Line #{idx} cannot use the same ledger as the main account ({main_ledger}).")
                    return
                try:
                    val = safe_numeric_eval(a_str)
                    if val <= 0:
                        raise ValueError
                except Exception:
                    messagebox.showerror("Invalid Split Amount", f"Enter a valid positive amount on Split Line #{idx}.")
                    r["amt"].focus_set()
                    return
                split_lines.append((c_name, val, n_str))
                split_sum += val

            if not split_lines:
                messagebox.showwarning("Empty Split", "Please enter at least one valid split row with an amount.")
                return

            bank_amt_str = self.ent_amount.get().strip()
            if bank_amt_str:
                try:
                    expected_bank_total = safe_numeric_eval(bank_amt_str)
                except Exception:
                    messagebox.showerror("Invalid Total Amount", "The Total Voucher Amount box has an invalid number.")
                    self.ent_amount.focus_set()
                    return
                if abs(expected_bank_total - split_sum) > 0.01:
                    diff = expected_bank_total - split_sum
                    messagebox.showwarning("Split Amount Mismatch!", f"Split Sum is ₹{split_sum:,.2f}, but Total Voucher Amount is ₹{expected_bank_total:,.2f}!\nDifference: ₹{diff:,.2f}")
                    return

            self.db.save_compound_split_voucher(
                tx_date, tx_type, main_ledger, split_lines,
                split_target=self.split_target,
                existing_group_id=self.selected_voucher_group_id
            )
            self.clear_form()
            self.refresh_all()
            return

        account = self.ac_account.get()
        if not account or account == CREATE_NEW_OPTION or not self.db.ledger_exists(account):
            prefill = "" if account == CREATE_NEW_OPTION else account
            self.prompt_create_account_ledger(prefill)
            return

        category = "Contra Transfer" if tx_type == "Transfer" else self.ac_category.get()
        to_account = self.ac_to_account.get() if tx_type == "Transfer" else ""
        desc = sanitize_narration(self.ent_desc.get())
        amt_str = self.ent_amount.get().strip()

        if tx_type != "Transfer":
            if not category or category == CREATE_NEW_OPTION or not self.db.ledger_exists(category):
                prefill = "" if category == CREATE_NEW_OPTION else category
                self.prompt_create_category_ledger(prefill)
                return
            if category.lower() == account.lower():
                messagebox.showwarning("Same Ledger Error", "Category/Party Ledger and Paid-From Account cannot be the exact same ledger.")
                return

        if tx_type == "Transfer":
            if not to_account or to_account == CREATE_NEW_OPTION or not self.db.ledger_exists(to_account):
                prefill = "" if to_account == CREATE_NEW_OPTION else to_account
                self.prompt_create_to_account_ledger(prefill)
                return
            if account.lower() == to_account.lower():
                messagebox.showwarning("Invalid Transfer", "From Account and To Account cannot be the same.")
                return

        if not amt_str:
            self.ent_amount.focus_set()
            return

        try:
            amount = safe_numeric_eval(amt_str)
            if amount <= 0:
                raise ValueError
        except Exception:
            messagebox.showerror("Invalid Amount", "Enter a valid positive amount or math expression.")
            self.ent_amount.focus_set()
            return

        if self.selected_tx_id is None:
            self.db.add_transaction(tx_date, tx_type, category, account, to_account, desc, amount)
        else:
            self.db.update_transaction(self.selected_tx_id, tx_date, tx_type, category, account, to_account, desc, amount)

        self.clear_form()
        self.refresh_all()

    def load_tx_into_form(self, tx_id: int, lock_preview=True):
        self.db.cursor.execute("SELECT id, tx_date, tx_type, category, account, to_account, description, amount, COALESCE(voucher_group_id, 0) FROM transactions WHERE id=?", (int(tx_id),))
        row = self.db.cursor.fetchone()
        if not row:
            return

        # Temporarily enable widgets so we can populate their text cleanly
        self.voucher_locked_preview = False
        self._set_voucher_fields_enabled(True)

        v_grp_id = row[8]
        if v_grp_id > 0:
            grp_rows = self.db.get_split_group_rows(v_grp_id)
            if len(grp_rows) > 1:
                self.selected_tx_id = row[0]
                self.selected_voucher_group_id = v_grp_id
                self.ent_date.delete(0, tk.END)
                self.ent_date.insert(0, row[1])
                self.cmb_type.set(row[2])
                self.on_type_change(row[2])

                distinct_cats = {r[3].lower() for r in grp_rows}
                distinct_accs = {r[4].lower() for r in grp_rows}

                if not self.is_split_mode:
                    self.toggle_split_voucher_mode(steal_focus=False)

                if len(distinct_accs) > 1 and len(distinct_cats) == 1:
                    self.split_target = "account"
                    self.seg_split_target.set("Split Payment Modes (Cr)")
                    self.on_split_target_change("Split Payment Modes (Cr)")
                    self.ac_category.set(grp_rows[0][3])
                else:
                    self.split_target = "category"
                    self.seg_split_target.set("Split Categories (Dr)")
                    self.on_split_target_change("Split Categories (Dr)")
                    self.ac_account.set(grp_rows[0][4])

                for r in list(self.split_row_widgets):
                    r["frame"].destroy()
                self.split_row_widgets.clear()

                tot_s = 0.0
                for _, _, _, s_cat, s_acc, s_desc, s_amt in grp_rows:
                    tot_s += s_amt
                    line_led = s_acc if self.split_target == "account" else s_cat
                    self.add_split_row(prefill_cat=line_led, prefill_amt=f"{s_amt:.2f}", prefill_note=s_desc, focus_new=False)

                self.ent_amount.delete(0, tk.END)
                self.ent_amount.insert(0, f"{tot_s:.2f}")
                self.update_split_total_label()
                self.update_live_voucher_balances()

                if lock_preview:
                    self.voucher_locked_preview = True
                    self._set_voucher_fields_enabled(False)
                    self.lbl_vch_hint.configure(text=f"🔒 LOCKED PREVIEW: Split #{v_grp_id} — Click 'Unlock to Edit' (Alt+E)", text_color="#2563EB")
                    self.btn_save.configure(text=f"🔓 Unlock to Edit Split #{v_grp_id} (Alt+E)", fg_color="#2563EB", hover_color="#1D4ED8")
                else:
                    self.lbl_vch_hint.configure(text=f"✏️ UNLOCKED EDITING: Split Voucher #{v_grp_id}", text_color="#D97706")
                    self.btn_save.configure(text=f"✔ Save Changes to Split #{v_grp_id}", fg_color="#D97706", hover_color="#B45309")
                return

        if self.is_split_mode:
            self.toggle_split_voucher_mode(steal_focus=False)

        self.selected_tx_id = row[0]
        self.selected_voucher_group_id = 0

        self.ent_date.delete(0, tk.END)
        self.ent_date.insert(0, row[1])
        self.cmb_type.set(row[2])
        self.on_type_change(row[2])
        if row[2] != "Transfer":
            self.ac_category.set(row[3])
        self.ac_account.set(row[4])
        if row[2] == "Transfer":
            self.ac_to_account.set(row[5])
        self.ent_desc.delete(0, tk.END)
        self.ent_desc.insert(0, row[6])
        self.ent_amount.delete(0, tk.END)
        self.ent_amount.insert(0, f"{row[7]:.2f}")
        self.update_live_voucher_balances()

        if lock_preview:
            self.voucher_locked_preview = True
            self._set_voucher_fields_enabled(False)
            self.lbl_vch_hint.configure(text=f"🔒 LOCKED PREVIEW: ID #{row[0]} — Click 'Unlock to Edit' (Alt+E)", text_color="#2563EB")
            self.btn_save.configure(text=f"🔓 Unlock to Edit ID #{row[0]} (Alt+E)", fg_color="#2563EB", hover_color="#1D4ED8")
        else:
            self.lbl_vch_hint.configure(text=f"✏️ UNLOCKED EDITING: Voucher ID #{row[0]}", text_color="#D97706")
            self.btn_save.configure(text=f"✔ Save Changes to ID #{row[0]}", fg_color="#D97706", hover_color="#B45309")

    def on_daybook_row_select(self, event):
        sel = self.tree.selection()
        if sel:
            vals = self.tree.item(sel[0]).get("values", [])
            self._load_from_tree_item_values(vals, lock_preview=True)
            # Keep keyboard focus strictly inside the Daybook treeview if Daybook is active!
            if self.current_tab_key == "daybook" and self.focus_get() != self.ent_search._entry:
                self.tree.focus_set()

    def on_profile_tx_select(self, event):
        sel = self.prof_tree.selection()
        if sel:
            self.load_tx_into_form(self.prof_tree.item(sel[0])["values"][0], lock_preview=True)
            if self.current_tab_key == "ledgers" and self.focus_get() != self.ent_prof_search._entry:
                self.prof_tree.focus_set()

    def delete_entry(self):
        if not self.book_is_open or self.has_open_modal():
            return
        if self.selected_voucher_group_id > 0:
            if messagebox.askyesno("Delete Split Voucher", f"Delete entire Split Voucher #{self.selected_voucher_group_id}?"):
                self.db.delete_voucher_group(self.selected_voucher_group_id)
                self.clear_form()
                self.refresh_all()
                return

        tx_id = self.selected_tx_id
        if tx_id is None:
            for t_widget in (self.tree, self.prof_tree):
                sel = t_widget.selection()
                if sel:
                    raw_id = str(t_widget.item(sel[0])["values"][0])
                    if raw_id.startswith("S#"):
                        grp_id = int(raw_id.replace("S#", ""))
                        if messagebox.askyesno("Delete Split Voucher", f"Delete entire Split Voucher #{grp_id}?"):
                            self.db.delete_voucher_group(grp_id)
                            self.clear_form()
                            self.refresh_all()
                        return
                    tx_id = int(raw_id)
                    break
        if tx_id is None:
            messagebox.showinfo("Select Entry", "Click any transaction row first to delete it.")
            return
        if messagebox.askyesno("Confirm Delete", f"Permanently delete Transaction Line ID #{tx_id}?"):
            self.db.delete_transaction(int(tx_id))
            self.clear_form()
            self.refresh_all()

    def delete_entry_from_profile(self):
        sel = self.prof_tree.selection()
        if not sel:
            messagebox.showinfo("Select Entry", "Click a transaction row in this ledger first.")
            return
        tx_id = self.prof_tree.item(sel[0])["values"][0]
        if messagebox.askyesno("Confirm Delete", f"Delete Transaction ID #{tx_id}?"):
            self.db.delete_transaction(int(tx_id))
            self.clear_form()
            self.refresh_all()

    def clear_form(self):
        self.voucher_locked_preview = False
        self._set_voucher_fields_enabled(True)
        self.selected_tx_id = None
        self.selected_voucher_group_id = 0
        self.lbl_vch_hint.configure(text="New Entry Mode — Type or select ledgers below", text_color="#059669")
        self.btn_save.configure(text="✔ Save Entry (Enter)", fg_color="#059669", hover_color="#047857")
        self.ac_category.clear_to_placeholder()
        self.ac_account.clear_to_placeholder()
        self.ac_to_account.clear_to_placeholder()
        self.ent_amount.delete(0, tk.END)
        self.ent_desc.delete(0, tk.END)
        self.clear_split_rows()
        for t in (self.tree, self.prof_tree):
            if t.selection():
                t.selection_remove(t.selection())
        self.update_live_voucher_balances()

    def open_ledger_profile_by_name(self, ledger_name: str):
        if not ledger_name or ledger_name == CREATE_NEW_OPTION:
            return
        self.active_drill_ledger = ledger_name
        self.switch_main_tab("ledgers")
        self.ledger_list_page.grid_forget()
        self.ledger_profile_page.grid(row=0, column=0, sticky="nsew")
        self.cmb_prof_switch.configure(values=self.all_ledgers)
        self.cmb_prof_switch.set(ledger_name)
        self.refresh_active_profile_view(focus_table=True)

    def open_selected_ledger_profile(self):
        sel = self.manage_tree.selection()
        if not sel:
            children = self.manage_tree.get_children()
            if children:
                self.manage_tree.selection_set(children[0])
                sel = (children[0],)
            else:
                messagebox.showinfo("Select Ledger", "Click a ledger row first.")
                return
        l_name = self.manage_tree.item(sel[0])["values"][0]
        self.open_ledger_profile_by_name(l_name)

    def close_ledger_profile(self):
        self.active_drill_ledger = None
        self.ledger_profile_page.grid_forget()
        self.ledger_list_page.grid(row=0, column=0, sticky="nsew")
        self.refresh_manage_ledgers_table(focus_table=True)

    def _get_effective_profile_period(self):
        p_choice = self.cmb_prof_period.get()
        return self.current_period if p_choice == "Same as Top Filter" else p_choice

    def refresh_active_profile_view(self, focus_table=False):
        if not self.active_drill_ledger:
            return
        eff_period = self._get_effective_profile_period()
        c_from = self.ent_custom_from.get().strip()
        c_to = self.ent_custom_to.get().strip()
        s_flt = self.ent_prof_search.get().strip()
        st = self.db.get_single_ledger_statement(self.active_drill_ledger, eff_period, c_from, c_to, s_flt)

        self.lbl_prof_title.configure(text=f"📒 {st['name']}")
        self.lbl_prof_sub.configure(text=f"Type: {st['group']}   |   Period: {eff_period}   |   Entries: {len(st['rows'])}")
        self.lbl_prof_op.configure(text=f"₹{st['opening']:,.2f}")
        self.lbl_prof_dr.configure(text=f"₹{st['total_dr']:,.2f}")
        self.lbl_prof_cr.configure(text=f"₹{st['total_cr']:,.2f}")
        self.lbl_prof_bal.configure(text=st["formatted_closing"])

        for r in self.prof_tree.get_children():
            self.prof_tree.delete(r)
        for r in st["rows"]:
            dr_s = f"{r['dr']:,.2f}" if r["dr"] > 0 else "-"
            cr_s = f"{r['cr']:,.2f}" if r["cr"] > 0 else "-"
            self.prof_tree.insert("", tk.END, values=(r["id"], r["date"], r["type"], r["particulars"], r["description"], dr_s, cr_s, f"₹{r['balance']:,.2f}"))

        children = self.prof_tree.get_children()
        if children:
            self.prof_tree.selection_set(children[0])
            self.prof_tree.focus(children[0])
            if focus_table:
                self.prof_tree.focus_set()

    def edit_selected_ledger_from_master(self):
        sel = self.manage_tree.selection()
        if not sel:
            messagebox.showinfo("Select Ledger", "Click a ledger row first.")
            return
        l_name = self.manage_tree.item(sel[0])["values"][0]
        self._open_edit_modal_for_ledger(l_name)

    def edit_active_profile_ledger(self):
        if self.active_drill_ledger:
            self._open_edit_modal_for_ledger(self.active_drill_ledger)

    def _open_edit_modal_for_ledger(self, ledger_name: str):
        st = self.db.get_single_ledger_statement(ledger_name)
        modal = self.open_create_ledger_modal(prefill_name=st["name"], default_group=st["group"], on_success=lambda new_n: (setattr(self, "active_drill_ledger", new_n if self.active_drill_ledger else None), self.refresh_all()))
        if modal:
            modal.ent_op.delete(0, tk.END)
            modal.ent_op.insert(0, str(st["opening"]))
            modal.var_pin.set(st["pinned"])

    def delete_selected_ledger_from_master(self):
        sel = self.manage_tree.selection()
        if not sel:
            messagebox.showinfo("Select Ledger", "Select a ledger row to delete.")
            return
        l_name = self.manage_tree.item(sel[0])["values"][0]
        if messagebox.askyesno("Confirm Delete Ledger", f"Delete ledger '{l_name}' from this Book?"):
            ok, msg = self.db.delete_ledger(l_name)
            if ok:
                self.refresh_all()
                messagebox.showinfo("Deleted", msg)
            else:
                messagebox.showwarning("Cannot Delete", msg)

    def on_quick_cat_double_click(self, event):
        sel = self.cat_tree.selection()
        if sel:
            l_name = self.cat_tree.item(sel[0])["values"][0]
            self.open_ledger_profile_by_name(l_name)

    def on_daybook_double_click(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        item_id = sel[0]
        vals = self.tree.item(item_id)["values"]
        if str(vals[0]).startswith("S#"):
            is_open = bool(self.tree.item(item_id, "open"))
            self.tree.item(item_id, open=not is_open)
            return
        cat = str(vals[3]).replace("↳ ", "").strip()
        acc = str(vals[4]).split(" → ")[0].strip()
        target = cat if (cat and cat != "Contra Transfer" and not cat.startswith("Split (")) else acc
        if self.db.ledger_exists(target):
            self.open_ledger_profile_by_name(target)

    def refresh_all(self):
        self.refresh_dropdown_cache()
        comp = self.db.get_active_company()
        self.lbl_comp_badge.configure(text=f"🏢 {comp['name']}")
        self.title(f"TallyLite — [{comp['name']} | {self.current_period}]")

        self.flt_account.configure(values=["All"] + self.payment_accounts)
        self.flt_cat.configure(values=["All"] + self.voucher_ledgers)

        c_from = self.ent_custom_from.get().strip()
        c_to = self.ent_custom_to.get().strip()
        dash = self.db.get_dashboard_data(self.current_period, c_from, c_to)

        self.lbl_tot_in.configure(text=f"₹{dash['total_in']:,.2f}")
        self.lbl_tot_out.configure(text=f"₹{dash['total_out']:,.2f}")
        self.lbl_net_flow.configure(text=f"₹{dash['net_flow']:,.2f}")
        self.lbl_liquid.configure(text=f"₹{dash['total_liquid']:,.2f}")

        for w in self.bank_bar.winfo_children():
            w.destroy()

        pinned_banks = [(k, v) for k, v in dash["bank_cash"].items() if v["pinned"]]
        if not pinned_banks:
            pinned_banks = list(dash["bank_cash"].items())[:4]

        for idx, (b_name, b_data) in enumerate(pinned_banks):
            self.bank_bar.grid_columnconfigure(idx, weight=1)
            card = ctk.CTkFrame(self.bank_bar, corner_radius=8, fg_color=("#FFFFFF", "#0F172A"))
            card.grid(row=0, column=idx, padx=5, pady=5, sticky="ew")

            icon = "🏦" if b_data["group"] == "Bank Account" else "💵"
            l1 = ctk.CTkLabel(card, text=f"{icon} {b_name}", font=ctk.CTkFont(size=12, weight="bold"), cursor="hand2")
            l1.pack(pady=(5, 0))
            bal_color = "#059669" if b_data["bal"] >= 0 else "#DC2626"
            l2 = ctk.CTkLabel(card, text=f"₹{b_data['bal']:,.2f}", font=ctk.CTkFont(size=16, weight="bold"), text_color=bal_color, cursor="hand2")
            l2.pack(pady=1)
            l3 = ctk.CTkLabel(card, text=f"In: ₹{b_data['in']:,.0f}  |  Out: ₹{b_data['out']:,.0f}", font=ctk.CTkFont(size=10), text_color="gray", cursor="hand2")
            l3.pack(pady=(0, 5))

            for widget in (card, l1, l2, l3):
                widget.bind("<Button-1>", lambda e, n=b_name: self.open_ledger_profile_by_name(n))

        for r in self.cat_tree.get_children():
            self.cat_tree.delete(r)
        for cat, inc, exp in self.db.get_category_breakdown(self.current_period, c_from, c_to):
            self.cat_tree.insert("", tk.END, values=(cat, f"{inc:,.0f}" if inc else "-", f"{exp:,.0f}" if exp else "-"))

        self._refresh_home_dashboard_widgets(dash)
        self.refresh_daybook_table()
        self.refresh_manage_ledgers_table(precomputed_summaries=dash["all_summaries"])
        self.update_live_voucher_balances()
        if self.active_drill_ledger:
            self.refresh_active_profile_view()
        if self.current_tab_key == "reports":
            self.refresh_financial_reports_tab()

    def _refresh_home_dashboard_widgets(self, dash):
        for w in self.home_exp_card.winfo_children():
            w.destroy()

        top_exp = dash["top_expenses"]
        max_exp = top_exp[0][1] if top_exp else 1.0
        if not top_exp:
            ctk.CTkLabel(self.home_exp_card, text="No expenses recorded in this Period yet.", text_color="gray").pack(pady=24)
        else:
            for cat_name, amt in top_exp[:8]:
                row = ctk.CTkFrame(self.home_exp_card, fg_color=("#FFFFFF", "#1E293B"), corner_radius=6)
                row.pack(fill="x", padx=4, pady=3)
                lbl_top = ctk.CTkFrame(row, fg_color="transparent")
                lbl_top.pack(fill="x", padx=8, pady=(4, 0))
                l_cat = ctk.CTkLabel(lbl_top, text=f"📌 {cat_name}", font=ctk.CTkFont(size=12, weight="bold"), cursor="hand2")
                l_cat.pack(side="left")
                l_cat.bind("<Button-1>", lambda e, n=cat_name: self.open_ledger_profile_by_name(n))
                ctk.CTkLabel(lbl_top, text=f"₹{amt:,.2f}", font=ctk.CTkFont(size=12, weight="bold"), text_color="#DC2626").pack(side="right")

                prog = ctk.CTkProgressBar(row, height=7, progress_color="#EF4444")
                prog.pack(fill="x", padx=8, pady=(3, 6))
                prog.set(min(1.0, amt / max_exp))

        for w in self.home_lenden_card.winfo_children():
            w.destroy()

        recs = dash["receivables"]
        pays = dash["payables"]
        if not recs and not pays:
            ctk.CTkLabel(self.home_lenden_card, text="✔ No Pending Dues or Receivables.", text_color="gray", justify="center").pack(pady=20)
        else:
            if recs:
                ctk.CTkLabel(self.home_lenden_card, text="🟢 MONEY TO RECEIVE BACK (RECEIVABLES):", font=ctk.CTkFont(size=12, weight="bold"), text_color="#059669").pack(anchor="w", padx=6, pady=(4, 2))
                for r in recs:
                    f = ctk.CTkFrame(self.home_lenden_card, corner_radius=6, fg_color=("#FFFFFF", "#1E293B"))
                    f.pack(fill="x", padx=4, pady=3)
                    lbl = ctk.CTkLabel(f, text=f"👤 {r['name']}", font=ctk.CTkFont(weight="bold"), cursor="hand2")
                    lbl.pack(side="left", padx=8, pady=6)
                    lbl.bind("<Button-1>", lambda e, n=r["name"]: self.open_ledger_profile_by_name(n))
                    ctk.CTkLabel(f, text=f"To Receive: ₹{r['net_amt']:,.2f}", text_color="#059669", font=ctk.CTkFont(weight="bold")).pack(side="right", padx=8)

            if pays:
                ctk.CTkLabel(self.home_lenden_card, text="🔴 DUE / TO PAY BACK (PAYABLES):", font=ctk.CTkFont(size=12, weight="bold"), text_color="#DC2626").pack(anchor="w", padx=6, pady=(8, 2))
                for p in pays:
                    f = ctk.CTkFrame(self.home_lenden_card, corner_radius=6, fg_color=("#FFFFFF", "#1E293B"))
                    f.pack(fill="x", padx=4, pady=3)
                    lbl = ctk.CTkLabel(f, text=f"💳 {p['name']}", font=ctk.CTkFont(weight="bold"), cursor="hand2")
                    lbl.pack(side="left", padx=8, pady=6)
                    lbl.bind("<Button-1>", lambda e, n=p["name"]: self.open_ledger_profile_by_name(n))
                    ctk.CTkLabel(f, text=f"To Pay: ₹{p['net_amt']:,.2f}", text_color="#DC2626", font=ctk.CTkFont(weight="bold")).pack(side="right", padx=8)

    def refresh_daybook_table(self, focus_table=False):
        for r in self.tree.get_children():
            self.tree.delete(r)

        c_from = self.ent_custom_from.get().strip()
        c_to = self.ent_custom_to.get().strip()
        acc_f = self.flt_account.get()
        cat_f = self.flt_cat.get()
        type_f = self.flt_type.get()

        rows = self.db.get_transactions(
            search_query=self.ent_search.get().strip(),
            account_filter=acc_f,
            category_filter=cat_f,
            type_filter=type_f,
            period_label=self.current_period,
            custom_from=c_from,
            custom_to=c_to
        )

        flt_in = 0.0
        flt_out = 0.0
        flt_trf = 0.0

        grouped_map = {}
        for r in rows:
            v_grp = r[10]
            if v_grp > 0:
                grouped_map.setdefault(v_grp, []).append(r)

        emitted_groups = set()

        for tx_id, dt, t_type, cat, acc, to_acc, desc, amt, dr, cr, v_grp in rows:
            if t_type == "Income":
                flt_in += amt
            elif t_type == "Expense":
                flt_out += amt
            elif t_type == "Transfer":
                flt_trf += amt

            if v_grp > 0 and len(grouped_map.get(v_grp, [])) > 1:
                if v_grp in emitted_groups:
                    continue
                emitted_groups.add(v_grp)
                g_rows = grouped_map[v_grp]
                tot_grp_amt = sum(x[7] for x in g_rows)
                distinct_cats = list(dict.fromkeys(x[3] for x in g_rows))
                distinct_accs = list(dict.fromkeys(x[4] for x in g_rows))

                cat_summary = distinct_cats[0] if len(distinct_cats) == 1 else f"Split ({len(distinct_cats)} Ledgers: {', '.join(distinct_cats[:2])}...)"
                acc_summary = distinct_accs[0] if len(distinct_accs) == 1 else f"Split ({', '.join(distinct_accs)})"
                inc_str = f"{tot_grp_amt:,.2f}" if t_type == "Income" else ""
                exp_str = f"{tot_grp_amt:,.2f}" if t_type == "Expense" else ""

                parent_iid = self.tree.insert(
                    "", tk.END,
                    text="▼",
                    open=False,
                    tags=("split_parent",),
                    values=(
                        f"S#{v_grp}",
                        dt,
                        f"{t_type} [Split]",
                        cat_summary,
                        acc_summary,
                        f"🔀 {len(g_rows)} Split Lines (Click ▶ or press Space to expand)",
                        inc_str,
                        exp_str,
                        f"Compound Split #{v_grp}"
                    )
                )
                for c_id, c_dt, c_type, c_cat, c_acc, c_to, c_desc, c_amt, c_dr, c_cr, _ in reversed(g_rows):
                    c_inc = f"{c_amt:,.2f}" if c_type == "Income" else ""
                    c_exp = f"{c_amt:,.2f}" if c_type == "Expense" else ""
                    self.tree.insert(
                        parent_iid, tk.END,
                        text="↳",
                        tags=("split_child",),
                        values=(c_id, c_dt, c_type, f"↳ {c_cat}", c_acc, c_desc, c_inc, c_exp, f"Dr {c_dr} | Cr {c_cr}")
                    )
            else:
                t_disp = f"{t_type} [S#{v_grp}]" if v_grp > 0 else t_type
                mode_str = f"{acc} → {to_acc}" if t_type == "Transfer" else acc
                inc_str = f"{amt:,.2f}" if t_type in ("Income", "Transfer") else ""
                exp_str = f"{amt:,.2f}" if t_type in ("Expense", "Transfer") else ""
                d_entry = f"Dr {dr} | Cr {cr}"
                self.tree.insert("", tk.END, text="", values=(tx_id, dt, t_disp, cat, mode_str, desc, inc_str, exp_str, d_entry))

        cnt = len(rows)
        if type_f == "Expense":
            sum_txt = f"📋 Filtered Entries: {cnt}   |   Total Expense: ₹{flt_out:,.2f}"
        elif type_f == "Income":
            sum_txt = f"📋 Filtered Entries: {cnt}   |   Total Income: ₹{flt_in:,.2f}"
        elif type_f == "Transfer":
            sum_txt = f"📋 Filtered Entries: {cnt}   |   Total Transfers: ₹{flt_trf:,.2f}"
        else:
            net_v = flt_in - flt_out
            sum_txt = f"📋 Entries: {cnt}   |   Income: ₹{flt_in:,.2f}   |   Expense: ₹{flt_out:,.2f}   |   Net: ₹{net_v:,.2f}"
            if flt_trf > 0:
                sum_txt += f"   (Transfers: ₹{flt_trf:,.2f})"

        self.lbl_daybook_summary.configure(text=sum_txt)

        target_ledger = acc_f if acc_f != "All" else (cat_f if cat_f != "All" else "")
        if target_ledger:
            bal_txt = self.db.get_quick_ledger_balance_text(target_ledger, self.current_period, c_from, c_to)
            self.lbl_daybook_closing.configure(text=f"📌 {bal_txt}")
        else:
            self.lbl_daybook_closing.configure(text="")

        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])
            if focus_table:
                self.tree.focus_set()

    def refresh_manage_ledgers_table(self, precomputed_summaries=None, focus_table=False):
        for r in self.manage_tree.get_children():
            self.manage_tree.delete(r)

        c_from = self.ent_custom_from.get().strip()
        c_to = self.ent_custom_to.get().strip()
        g_flt = self.flt_ledger_group.get()
        s_q = self.ent_ledger_search.get().strip()

        items = precomputed_summaries if (precomputed_summaries is not None and g_flt == "All" and not s_q) else self.db.get_all_ledgers_summary(self.current_period, c_from, c_to, g_flt, s_q)
        for item in items:
            self.manage_tree.insert("", tk.END, values=(item["name"], item["group"], item["tx_count"], item["formatted_closing"]))

        children = self.manage_tree.get_children()
        if children:
            self.manage_tree.selection_set(children[0])
            self.manage_tree.focus(children[0])
            if focus_table:
                self.manage_tree.focus_set()

    def open_pin_manager_dialog(self):
        if not self.book_is_open:
            return
        if self.has_open_modal():
            self.active_modal.lift()
            return
        win = ctk.CTkToplevel(self)
        self.active_modal = win
        win.title("Pin / Unpin Bank & Cash Accounts (ESC to Close)")
        win.geometry("440x420")
        win.bind("<Escape>", lambda e: (setattr(self, "active_modal", None), win.destroy()))
        win.protocol("WM_DELETE_WINDOW", lambda: (setattr(self, "active_modal", None), win.destroy()))
        win.lift()
        win.focus_force()

        ctk.CTkLabel(win, text="Choose Top Bar Bank & Cash Cards", font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=18, pady=(14, 4))
        scroll = ctk.CTkScrollableFrame(win, corner_radius=8)
        scroll.pack(fill="both", expand=True, padx=18, pady=6)

        self.db.cursor.execute("SELECT name, ledger_group, show_on_top FROM ledgers WHERE ledger_group IN ('Bank Account', 'Cash in Hand') ORDER BY name COLLATE NOCASE")
        vars_map = {}
        for name, grp, pin in self.db.cursor.fetchall():
            v = tk.IntVar(value=pin)
            vars_map[name] = v
            ctk.CTkCheckBox(scroll, text=f"{name} ({grp})", variable=v).pack(anchor="w", padx=8, pady=5)

        def apply_pins():
            for n, v in vars_map.items():
                self.db.set_ledger_pin(n, v.get())
            self.active_modal = None
            self.refresh_all()
            win.destroy()

        ctk.CTkButton(win, text="✔ Save Top Bar Layout", height=36, fg_color="#059669", command=apply_pins).pack(fill="x", padx=18, pady=12)

    def show_readme_modal(self):
        if self.has_open_modal():
            self.active_modal.lift()
            return
        content = "README file not found."
        if os.path.exists(README_PATH):
            with open(README_PATH, "r", encoding="utf-8") as f:
                content = f.read()
        self.active_modal = DocumentViewerModal(self, "📖 README — Tech Stack & Architecture", content)

    def show_changelog_modal(self):
        if self.has_open_modal():
            self.active_modal.lift()
            return
        content = "CHANGELOG file not found."
        if os.path.exists(CHANGELOG_PATH):
            with open(CHANGELOG_PATH, "r", encoding="utf-8") as f:
                content = f.read()
        self.active_modal = DocumentViewerModal(self, "🆕 Version Changelog (V6.5.2a)", content)

    def export_daybook_csv(self):
        if not self.book_is_open:
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialdir=EXPORT_DIR, initialfile=f"Transactions_{datetime.now().strftime('%Y%m%d')}.csv", filetypes=[("Excel CSV", "*.csv")])
        if not path:
            return
        c_from = self.ent_custom_from.get().strip()
        c_to = self.ent_custom_to.get().strip()
        rows = self.db.get_transactions(period_label=self.current_period, custom_from=c_from, custom_to=c_to)
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["ID", "Date", "Type", "Category", "Payment_Mode", "Transfer_To", "Description", "Amount", "Dr", "Cr", "Group_ID"])
            w.writerows(rows)
        messagebox.showinfo("Export Complete", f"CSV saved to:\n{path}")

    def export_active_profile_csv(self):
        if not self.active_drill_ledger:
            return
        eff_period = self._get_effective_profile_period()
        c_from = self.ent_custom_from.get().strip()
        c_to = self.ent_custom_to.get().strip()
        st = self.db.get_single_ledger_statement(self.active_drill_ledger, eff_period, c_from, c_to)
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialdir=EXPORT_DIR, initialfile=f"Ledger_{st['name']}.csv", filetypes=[("Excel CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["Ledger Name", st["name"], "Type", st["group"], "Closing Balance", st["formatted_closing"]])
            w.writerow([])
            w.writerow(["ID", "Date", "Type", "Particulars", "Description", "Dr", "Cr", "Balance"])
            for r in reversed(st["rows"]):
                w.writerow([r["id"], r["date"], r["type"], r["particulars"], r["description"], r["dr"], r["cr"], r["balance"]])
        messagebox.showinfo("Exported", f"Ledger CSV saved to:\n{path}")

    def export_active_profile_html_pdf(self):
        if not self.active_drill_ledger:
            return
        eff_period = self._get_effective_profile_period()
        c_from = self.ent_custom_from.get().strip()
        c_to = self.ent_custom_to.get().strip()
        st = self.db.get_single_ledger_statement(self.active_drill_ledger, eff_period, c_from, c_to)
        comp = self.db.get_active_company()
        path = os.path.join(EXPORT_DIR, f"Statement_{st['name']}.html")

        rows_html = ""
        for r in reversed(st["rows"]):
            dr_s = f"₹{r['dr']:,.2f}" if r["dr"] > 0 else "-"
            cr_s = f"₹{r['cr']:,.2f}" if r["cr"] > 0 else "-"
            rows_html += f"<tr><td>{r['id']}</td><td>{r['date']}</td><td>{r['type']}</td><td><b>{r['particulars']}</b></td><td>{r['description']}</td><td style='text-align:right;color:#059669;'>{dr_s}</td><td style='text-align:right;color:#DC2626;'>{cr_s}</td><td style='text-align:right;font-weight:bold;'>₹{r['balance']:,.2f}</td></tr>"

        html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'><title>Statement - {st['name']}</title><style>body {{ font-family: Arial; margin: 30px; }} table {{ width:100%; border-collapse:collapse; margin-top:10px; }} th, td {{ border:1px solid #CBD5E1; padding:8px; text-align:left; }} th {{ background:#F1F5F9; }}</style></head><body><h2>{comp['name']} — {st['name']} ({st['group']})</h2><table><thead><tr><th>ID</th><th>Date</th><th>Type</th><th>Particulars</th><th>Description</th><th style='text-align:right;'>Dr</th><th style='text-align:right;'>Cr</th><th style='text-align:right;'>Balance</th></tr></thead><tbody>{rows_html}</tbody></table></body></html>"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        webbrowser.open(f"file:///{path.replace(os.sep, '/')}")

    def export_financial_statements_html_pdf(self):
        if not self.book_is_open:
            return
        comp = self.db.get_active_company()
        c_from = self.ent_custom_from.get().strip()
        c_to = self.ent_custom_to.get().strip()
        fin = self.db.get_financial_statements(self.current_period, c_from, c_to)
        path = os.path.join(EXPORT_DIR, f"Financial_Statements_{self.current_period.replace(' ', '_')}.html")

        tb_rows = ""
        for r in fin["trial_balance"]:
            dr_s = f"₹{r['closing_dr']:,.2f}" if r["closing_dr"] > 0 else "-"
            cr_s = f"₹{r['closing_cr']:,.2f}" if r["closing_cr"] > 0 else "-"
            tb_rows += f"<tr><td><b>{r['name']}</b></td><td>{r['group']}</td><td style='text-align:right;'>₹{r['opening']:,.2f}</td><td style='text-align:right;color:#059669;'>{dr_s}</td><td style='text-align:right;color:#DC2626;'>{cr_s}</td></tr>"

        html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'><title>Financial Reports - {comp['name']}</title><style>body {{ font-family: Arial; margin: 30px; }} table {{ width:100%; border-collapse:collapse; margin-top:8px; margin-bottom:24px; }} th, td {{ border:1px solid #CBD5E1; padding:8px; text-align:left; }} th {{ background:#F1F5F9; }}</style></head><body><h2>{comp['name']} — Financial Reports</h2><h3>Trial Balance</h3><table><thead><tr><th>Ledger</th><th>Type</th><th style='text-align:right;'>Opening</th><th style='text-align:right;'>Debit</th><th style='text-align:right;'>Credit</th></tr></thead><tbody>{tb_rows}<tr style='font-weight:bold;background:#F8FAFC;'><td colspan='3'>TOTAL</td><td style='text-align:right;'>₹{fin['tb_total_dr']:,.2f}</td><td style='text-align:right;'>₹{fin['tb_total_cr']:,.2f}</td></tr></tbody></table></body></html>"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        webbrowser.open(f"file:///{path.replace(os.sep, '/')}")

    def export_tally_xml(self):
        if not self.book_is_open:
            return
        path = filedialog.asksaveasfilename(defaultextension=".xml", initialdir=EXPORT_DIR, initialfile=f"Tally_Vouchers_{datetime.now().strftime('%Y%m%d')}.xml", filetypes=[("Tally XML", "*.xml")])
        if not path:
            return
        rows = self.db.get_transactions(period_label=self.current_period)
        xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<ENVELOPE>', '  <BODY>', '    <IMPORTDATA>', '      <REQUESTDATA>']
        for tx_id, dt, t_type, cat, acc, to_acc, desc, amt, dr, cr, v_grp in rows:
            v_type = "Payment" if t_type == "Expense" else ("Receipt" if t_type == "Income" else "Contra")
            dt_clean = dt.replace("-", "")
            xml_lines.extend([
                '        <TALLYMESSAGE xmlns:UDF="TallyUDF">',
                f'          <VOUCHER VCHTYPE="{v_type}" ACTION="Create">',
                f'            <DATE>{dt_clean}</DATE>',
                f'            <VOUCHERTYPENAME>{v_type}</VOUCHERTYPENAME>',
                f'            <NARRATION>{desc}</NARRATION>',
                '            <ALLLEDGERENTRIES.LIST>',
                f'              <LEDGERNAME>{dr}</LEDGERNAME>',
                '              <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>',
                f'              <AMOUNT>-{amt:.2f}</AMOUNT>',
                '            </ALLLEDGERENTRIES.LIST>',
                '            <ALLLEDGERENTRIES.LIST>',
                f'              <LEDGERNAME>{cr}</LEDGERNAME>',
                '              <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>',
                f'              <AMOUNT>{amt:.2f}</AMOUNT>',
                '            </ALLLEDGERENTRIES.LIST>',
                '          </VOUCHER>',
                '        </TALLYMESSAGE>'
            ])
        xml_lines.extend(['      </REQUESTDATA>', '    </IMPORTDATA>', '  </BODY>', '</ENVELOPE>'])
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(xml_lines))
        messagebox.showinfo("Tally XML Exported", f"Tally-compatible XML saved to:\n{path}")

    def backup_database_now(self):
        if not self.book_is_open:
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        comp = self.db.get_active_company()
        dest = os.path.join(BACKUP_DIR, f"book_{self.db._safe_filename(comp['name'])[:-3]}_{ts}.db")
        shutil.copy2(comp["db_path"], dest)
        messagebox.showinfo("Backup Saved", f"Book database backed up safely to:\n{dest}")

    def show_shortcuts_help(self):
        msg = (
            "KEYBOARD SHORTCUTS (V6.5.2a — Phase 2 Hotfix):\n"
            "• Alt + 1 / 2 / 3 / 4 : Switch Tabs (Auto-focuses tables for Up/Down arrows)\n"
            "• Alt + E : Unlock Selected Transaction for Editing (prevents accidental edits!)\n"
            "• Alt + V : Start New Voucher Entry / Jump to Voucher Box\n"
            "• ESC : Tally-style Cancel / Lock Edit / Quit Unsaved Entry\n"
            "• Alt + S : Toggle Multi-Line Split Mode (Supports Dr Split & Cr Split)\n"
            "• Shift + BackSpace or Ctrl + D : Delete current Split Line via keyboard\n"
            "• Spacebar (in Daybook) : Expand / Collapse Tree-Map Split Vouchers"
        )
        messagebox.showinfo("Keyboard Shortcuts (F1)", msg)


if __name__ == "__main__":
    app = OfflineAccountingProV652a()
    app.mainloop()