import hashlib
import re
import tkinter as tk
from datetime import date, datetime, time, timedelta
from tkinter import filedialog, messagebox, ttk

import mysql.connector
from mysql.connector import Error


# ---------------------------------------------------------------
# Settings
# ---------------------------------------------------------------

DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = ""
DB_NAME = "barangay_blotter"

BARANGAY_NAME = "BARANGAY ____________"

DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin123"

CASE_TYPES = [
    "Neighbor Dispute (Away magkapitbahay)",
    "Noise (Ingay)",
    "Drunkenness (Lasing)",
    "Theft (Pagnanakaw)",
    "Debt (Utang)",
    "Others",
]
STATUSES = ["Pending", "For Hearing", "Settled", "Referred to Police"]
STATUS_FOR_HEARING = "For Hearing"
SEARCH_TYPES = ["Name", "Blotter Number", "Incident Date"]

MAX_LENGTH = {
    "username": 50,
    "name": 150,
    "address": 255,
    "contact": 20,
    "place": 255,
    "narrative": 2000,
    "venue": 150,
    "panel": 150,
}

HEADING_FONT = ("Arial", 16, "bold")


# ---------------------------------------------------------------
# Database migration (creates the database and tables automatically)
# ---------------------------------------------------------------

TABLE_OPTIONS = "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci"

MIGRATIONS = [
    f"""
    CREATE TABLE IF NOT EXISTS users (
        user_id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(50) NOT NULL UNIQUE,
        password_hash CHAR(64) NOT NULL,
        full_name VARCHAR(100) NOT NULL
    ) {TABLE_OPTIONS}
    """,
    f"""
    CREATE TABLE IF NOT EXISTS person (
        person_id INT AUTO_INCREMENT PRIMARY KEY,
        full_name VARCHAR(150) NOT NULL,
        address VARCHAR(255),
        contact_no VARCHAR(20),
        KEY idx_person_name (full_name)
    ) {TABLE_OPTIONS}
    """,
    f"""
    CREATE TABLE IF NOT EXISTS blotter (
        blotter_id INT AUTO_INCREMENT PRIMARY KEY,
        blotter_no VARCHAR(30) NOT NULL UNIQUE,
        case_type VARCHAR(50) NOT NULL,
        incident_date DATE NOT NULL,
        incident_place VARCHAR(255) NOT NULL,
        narrative TEXT,
        status VARCHAR(30) NOT NULL DEFAULT 'Pending',
        CONSTRAINT chk_blotter_status CHECK
            (status IN ('Pending', 'For Hearing', 'Settled', 'Referred to Police')),
        KEY idx_blotter_date (incident_date),
        KEY idx_blotter_status (status)
    ) {TABLE_OPTIONS}
    """,
    f"""
    CREATE TABLE IF NOT EXISTS involved (
        involved_id INT AUTO_INCREMENT PRIMARY KEY,
        blotter_id INT NOT NULL,
        person_id INT NOT NULL,
        role VARCHAR(20) NOT NULL,
        CONSTRAINT chk_involved_role CHECK (role IN ('Complainant', 'Respondent')),
        CONSTRAINT uq_involved UNIQUE (blotter_id, person_id, role),
        CONSTRAINT fk_involved_blotter FOREIGN KEY (blotter_id)
            REFERENCES blotter (blotter_id) ON DELETE CASCADE,
        CONSTRAINT fk_involved_person FOREIGN KEY (person_id)
            REFERENCES person (person_id) ON DELETE RESTRICT,
        KEY idx_involved_person (person_id)
    ) {TABLE_OPTIONS}
    """,
    f"""
    CREATE TABLE IF NOT EXISTS hearing (
        hearing_id INT AUTO_INCREMENT PRIMARY KEY,
        blotter_id INT NOT NULL,
        hearing_date DATE NOT NULL,
        hearing_time TIME NOT NULL,
        venue VARCHAR(150) NOT NULL,
        lupon_panel VARCHAR(150) NOT NULL,
        CONSTRAINT fk_hearing_blotter FOREIGN KEY (blotter_id)
            REFERENCES blotter (blotter_id) ON DELETE CASCADE,
        KEY idx_hearing_date (hearing_date)
    ) {TABLE_OPTIONS}
    """,
    """
    CREATE OR REPLACE VIEW v_summon_letter AS
    SELECT h.hearing_id, b.blotter_id, b.blotter_no, b.case_type,
           p.full_name, p.address, i.role,
           h.hearing_date, h.hearing_time, h.venue, h.lupon_panel
    FROM hearing h
    JOIN blotter b ON b.blotter_id = h.blotter_id
    JOIN involved i ON i.blotter_id = b.blotter_id
    JOIN person p ON p.person_id = i.person_id
    """,
]


def create_database():
    server = mysql.connector.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD
    )
    try:
        cursor = server.cursor()
        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"
        )
        cursor.close()
    finally:
        server.close()


def run_migrations():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        for statement in MIGRATIONS:
            cursor.execute(statement)
    finally:
        cursor.close()


def setup_database():
    create_database()
    connect_db()
    run_migrations()
    create_default_admin()


# ---------------------------------------------------------------
# Database access
# ---------------------------------------------------------------

connection = None


def connect_db():
    global connection
    connection = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        autocommit=True,
        connection_timeout=10,
    )
    cursor = connection.cursor()
    cursor.execute("SET SESSION innodb_lock_wait_timeout = 5")
    cursor.close()


def close_db():
    if connection is not None and connection.is_connected():
        connection.close()


def get_connection():
    if connection is None or not connection.is_connected():
        connect_db()
    return connection


def fetch_all(query, params=()):
    cursor = get_connection().cursor(dictionary=True, buffered=True)
    try:
        cursor.execute(query, params)
        return cursor.fetchall()
    finally:
        cursor.close()


def fetch_one(query, params=()):
    cursor = get_connection().cursor(dictionary=True, buffered=True)
    try:
        cursor.execute(query, params)
        return cursor.fetchone()
    finally:
        cursor.close()


def execute_query(query, params=()):
    cursor = get_connection().cursor()
    try:
        cursor.execute(query, params)
        return cursor.lastrowid
    finally:
        cursor.close()


def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def create_default_admin():
    row = fetch_one("SELECT COUNT(*) AS total FROM users")
    if row["total"] == 0:
        execute_query(
            "INSERT INTO users (username, password_hash, full_name) "
            "VALUES (%s, %s, %s)",
            (DEFAULT_USERNAME, hash_password(DEFAULT_PASSWORD), "Barangay Secretary"),
        )


def verify_login(username, password):
    return fetch_one(
        "SELECT user_id, full_name FROM users "
        "WHERE username = %s AND password_hash = %s",
        (username, hash_password(password)),
    )


def create_account(username, full_name, password):
    execute_query(
        "INSERT INTO users (username, password_hash, full_name) "
        "VALUES (%s, %s, %s)",
        (username, hash_password(password), full_name),
    )


def generate_blotter_no(cursor):
    year = date.today().year
    cursor.execute(
        "SELECT blotter_no FROM blotter WHERE blotter_no LIKE %s "
        "ORDER BY blotter_no DESC LIMIT 1",
        (f"{year}-%",),
    )
    row = cursor.fetchone()
    number = int(row[0].split("-")[1]) + 1 if row else 1
    if number > 9999:
        raise ValueError("The limit of 9999 blotters for this year was reached.")
    return f"{year}-{number:04d}"


def find_or_create_person(cursor, name, address, contact):
    cursor.execute(
        "SELECT person_id FROM person WHERE full_name = %s AND contact_no = %s",
        (name, contact),
    )
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute(
        "INSERT INTO person (full_name, address, contact_no) VALUES (%s, %s, %s)",
        (name, address, contact),
    )
    return cursor.lastrowid


def save_blotter(data):
    conn = get_connection()
    cursor = conn.cursor(buffered=True)
    try:
        cursor.execute("START TRANSACTION")
        blotter_no = generate_blotter_no(cursor)
        complainant_id = find_or_create_person(
            cursor, data["complainant_name"],
            data["complainant_address"], data["complainant_contact"])
        respondent_id = find_or_create_person(
            cursor, data["respondent_name"],
            data["respondent_address"], data["respondent_contact"])

        cursor.execute(
            "INSERT INTO blotter (blotter_no, case_type, incident_date, "
            "incident_place, narrative) VALUES (%s, %s, %s, %s, %s)",
            (blotter_no, data["case_type"], parse_date(data["incident_date"]),
             data["incident_place"], data["narrative"]),
        )
        blotter_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO involved (blotter_id, person_id, role) VALUES (%s, %s, %s)",
            (blotter_id, complainant_id, "Complainant"))
        cursor.execute(
            "INSERT INTO involved (blotter_id, person_id, role) VALUES (%s, %s, %s)",
            (blotter_id, respondent_id, "Respondent"))
        conn.commit()
        return blotter_no
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


SEARCH_CONDITIONS = {
    "Name": "p.full_name LIKE %s",
    "Blotter Number": "b.blotter_no LIKE %s",
    "Incident Date": "b.incident_date = %s",
}


def search_blotters(search_by, text):
    if search_by == "Incident Date":
        value = parse_date(text)
    else:
        value = f"%{text}%"
    query = (
        "SELECT DISTINCT b.blotter_id, b.blotter_no, b.case_type, "
        "b.incident_date, b.status "
        "FROM blotter b "
        "LEFT JOIN involved i ON i.blotter_id = b.blotter_id "
        "LEFT JOIN person p ON p.person_id = i.person_id "
        f"WHERE {SEARCH_CONDITIONS[search_by]} "
        "ORDER BY b.incident_date DESC, b.blotter_id DESC"
    )
    return fetch_all(query, (value,))


def get_blotter_details(blotter_id):
    blotter = fetch_one("SELECT * FROM blotter WHERE blotter_id = %s", (blotter_id,))
    people = fetch_all(
        "SELECT i.role, p.full_name, p.address, p.contact_no "
        "FROM involved i JOIN person p ON p.person_id = i.person_id "
        "WHERE i.blotter_id = %s ORDER BY i.role",
        (blotter_id,),
    )
    hearings = fetch_all(
        "SELECT hearing_date, hearing_time, venue, lupon_panel "
        "FROM hearing WHERE blotter_id = %s ORDER BY hearing_date, hearing_time",
        (blotter_id,),
    )
    return blotter, people, hearings


def get_blotter_numbers():
    rows = fetch_all("SELECT blotter_no FROM blotter ORDER BY blotter_id DESC")
    return [row["blotter_no"] for row in rows]


def get_blotter_by_no(blotter_no):
    return fetch_one(
        "SELECT blotter_id, blotter_no, case_type, status "
        "FROM blotter WHERE blotter_no = %s",
        (blotter_no,),
    )


def update_blotter_status(blotter_id, status):
    execute_query(
        "UPDATE blotter SET status = %s WHERE blotter_id = %s",
        (status, blotter_id),
    )


def save_hearing_record(blotter_id, data):
    return execute_query(
        "INSERT INTO hearing (blotter_id, hearing_date, hearing_time, venue, "
        "lupon_panel) VALUES (%s, %s, %s, %s, %s)",
        (blotter_id, parse_date(data["hearing_date"]),
         parse_time(data["hearing_time"]), data["venue"], data["lupon_panel"]),
    )


def get_summon_data(hearing_id):
    return fetch_all(
        "SELECT * FROM v_summon_letter WHERE hearing_id = %s ORDER BY role",
        (hearing_id,),
    )


# ---------------------------------------------------------------
# Helpers and validation
# ---------------------------------------------------------------

def parse_date(text):
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_time(text):
    try:
        return datetime.strptime(text.strip(), "%H:%M").time()
    except ValueError:
        return None


def format_date(value):
    return value.strftime("%B %d, %Y")


def format_time(value):
    if isinstance(value, timedelta):
        total = int(value.total_seconds())
        value = time(total // 3600, total % 3600 // 60)
    return value.strftime("%I:%M %p")


# Each check returns an error message, or None if the value is fine.

def check_required(fields):
    for label, value in fields.items():
        if not value.strip():
            return f"Incomplete Fields: {label} is required."
    return None


def check_max_length(fields):
    for label, value, limit in fields:
        if len(value) > limit:
            return f"{label} must be {limit} characters or less."
    return None


def check_contact(label, value):
    if not re.fullmatch(r"[0-9+\-\s]{7,20}", value):
        return f"{label} must be 7 to 20 characters (numbers, +, - and spaces only)."
    return None


def check_incident_date(text):
    incident_date = parse_date(text)
    if incident_date is None:
        return "Incident Date must be in YYYY-MM-DD format."
    if incident_date > date.today():
        return "Incident Date cannot be in the future."
    return None


def check_hearing_date(text):
    hearing_date = parse_date(text)
    if hearing_date is None:
        return "Hearing Date must be in YYYY-MM-DD format."
    if hearing_date < date.today():
        return "Hearing Date cannot be in the past."
    return None


def check_hearing_time(text):
    if parse_time(text) is None:
        return "Hearing Time must be in HH:MM format (24-hour, example 14:30)."
    return None


def check_different_people(data):
    same_name = data["complainant_name"].lower() == data["respondent_name"].lower()
    same_contact = data["complainant_contact"] == data["respondent_contact"]
    if same_name and same_contact:
        return "The complainant and the respondent cannot be the same person."
    return None


def validate_login(username, password):
    if not username or not password:
        return "Please enter your username and password."
    return None


def validate_new_account(username, full_name, password, confirm):
    if not username or not full_name or not password or not confirm:
        return "Please fill in all fields."
    if not re.fullmatch(r"[A-Za-z0-9_]{4,50}", username):
        return "Username must be 4 to 50 characters (letters, numbers and underscore only)."
    if len(full_name) > 100:
        return "Full name must be 100 characters or less."
    if len(password) < 6 or len(password) > 50:
        return "Password must be 6 to 50 characters."
    if password != confirm:
        return "Passwords do not match."
    return None


def validate_blotter(data):
    required = {
        "Complainant Name": data["complainant_name"],
        "Complainant Address": data["complainant_address"],
        "Complainant Contact No.": data["complainant_contact"],
        "Respondent Name": data["respondent_name"],
        "Respondent Address": data["respondent_address"],
        "Respondent Contact No.": data["respondent_contact"],
        "Case Type": data["case_type"],
        "Incident Date": data["incident_date"],
        "Incident Place": data["incident_place"],
    }
    lengths = [
        ("Complainant Name", data["complainant_name"], MAX_LENGTH["name"]),
        ("Complainant Address", data["complainant_address"], MAX_LENGTH["address"]),
        ("Respondent Name", data["respondent_name"], MAX_LENGTH["name"]),
        ("Respondent Address", data["respondent_address"], MAX_LENGTH["address"]),
        ("Incident Place", data["incident_place"], MAX_LENGTH["place"]),
        ("Narrative", data["narrative"], MAX_LENGTH["narrative"]),
    ]
    return (
        check_required(required)
        or check_max_length(lengths)
        or check_contact("Complainant Contact No.", data["complainant_contact"])
        or check_contact("Respondent Contact No.", data["respondent_contact"])
        or check_incident_date(data["incident_date"])
        or check_different_people(data)
    )


def validate_search(search_by, text):
    if not text:
        return "Please enter a search value."
    if len(text) > MAX_LENGTH["address"]:
        return "Search value is too long."
    if search_by == "Incident Date" and parse_date(text) is None:
        return "Incident Date must be in YYYY-MM-DD format."
    return None


def validate_hearing(data):
    required = {
        "Hearing Date": data["hearing_date"],
        "Hearing Time": data["hearing_time"],
        "Venue": data["venue"],
        "Assigned Lupon Panel": data["lupon_panel"],
    }
    lengths = [
        ("Venue", data["venue"], MAX_LENGTH["venue"]),
        ("Assigned Lupon Panel", data["lupon_panel"], MAX_LENGTH["panel"]),
    ]
    return (
        check_required(required)
        or check_max_length(lengths)
        or check_hearing_date(data["hearing_date"])
        or check_hearing_time(data["hearing_time"])
    )


# ---------------------------------------------------------------
# Text and PDF
# ---------------------------------------------------------------

def build_details_text(blotter, people, hearings):
    lines = [
        f"Blotter No.:   {blotter['blotter_no']}",
        f"Case Type:     {blotter['case_type']}",
        f"Incident Date: {format_date(blotter['incident_date'])}",
        f"Place:         {blotter['incident_place']}",
        f"Status:        {blotter['status']}",
        "",
    ]
    for person in people:
        lines.append(f"{person['role']}: {person['full_name']}")
        lines.append(f"    Address: {person['address']}")
        lines.append(f"    Contact: {person['contact_no']}")
    lines.append("")
    lines.append("Narrative:")
    lines.append(blotter["narrative"] or "(none)")
    if hearings:
        lines.append("")
        lines.append("Hearings:")
        for hearing in hearings:
            lines.append(
                f"    {format_date(hearing['hearing_date'])} "
                f"{format_time(hearing['hearing_time'])} - "
                f"{hearing['venue']} ({hearing['lupon_panel']})"
            )
    return "\n".join(lines)


def build_letter(rows):
    first = rows[0]
    complainant = next((r for r in rows if r["role"] == "Complainant"), None)
    respondent = next((r for r in rows if r["role"] == "Respondent"), None)

    lines = [
        BARANGAY_NAME,
        "SUMMON LETTER",
        "",
        f"Blotter No.: {first['blotter_no']}",
        f"Case Type: {first['case_type']}",
        "",
    ]
    if respondent:
        lines.append(f"To: {respondent['full_name']}")
        lines.append(f"    {respondent['address']}")
    if complainant:
        lines.append("")
        lines.append(f"Complainant: {complainant['full_name']}")
    lines += [
        "",
        "You are requested to appear for a hearing of the case stated above.",
        "",
        f"Date:  {format_date(first['hearing_date'])}",
        f"Time:  {format_time(first['hearing_time'])}",
        f"Venue: {first['venue']}",
        f"Lupon Panel: {first['lupon_panel']}",
        "",
        "",
        "______________________________",
        "Barangay Secretary",
    ]
    return "\n".join(lines)


def export_pdf(letter_text, file_path):
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    for line in letter_text.split("\n"):
        if line == "":
            pdf.ln(7)
        else:
            safe_line = line.encode("latin-1", "replace").decode("latin-1")
            pdf.multi_cell(0, 7, safe_line, new_x="LMARGIN", new_y="NEXT")
    pdf.output(file_path)


# ---------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------

def add_field(parent, row, label, variable, width=35):
    ttk.Label(parent, text=label).grid(row=row, column=0, sticky="e", padx=(0, 10), pady=4)
    entry = ttk.Entry(parent, textvariable=variable, width=width)
    entry.grid(row=row, column=1, sticky="w", pady=4)
    return entry


def load_blotter_numbers(combobox):
    try:
        combobox["values"] = get_blotter_numbers()
    except Error as err:
        messagebox.showerror("Database Error", f"Could not load blotter numbers.\n\n{err}")


def set_text(widget, text):
    widget.config(state="normal")
    widget.delete("1.0", "end")
    widget.insert("1.0", text)
    widget.config(state="disabled")


# ---------------------------------------------------------------
# Screens
# ---------------------------------------------------------------

class SummonPreview(tk.Toplevel):
    def __init__(self, parent, letter_text, default_name):
        super().__init__(parent)
        self.title("Summon Letter Preview")
        self.geometry("560x520")
        self.transient(parent.winfo_toplevel())
        self.letter_text = letter_text
        self.default_name = default_name

        frame = ttk.Frame(self, padding=15)
        frame.pack(fill="both", expand=True)

        self.text = tk.Text(frame, wrap="word", font=("Consolas", 11), height=22)
        self.text.pack(fill="both", expand=True)
        set_text(self.text, letter_text)

        buttons = ttk.Frame(frame)
        buttons.pack(pady=(10, 0))
        ttk.Button(buttons, text="Export as PDF", command=self.export).pack(side="left", padx=5)
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="left", padx=5)

        self.grab_set()

    def export(self):
        file_path = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialfile=self.default_name,
        )
        if not file_path:
            return
        try:
            export_pdf(self.letter_text, file_path)
        except ImportError:
            messagebox.showerror(
                "Export Failed",
                "The fpdf2 package is not installed.\nRun: pip install fpdf2",
                parent=self)
            return
        except Exception as err:
            messagebox.showerror("Export Failed", f"Could not export the PDF.\n\n{err}", parent=self)
            return
        messagebox.showinfo("PDF Exported", f"Saved to:\n{file_path}", parent=self)


class CreateAccountDialog(tk.Toplevel):
    def __init__(self, login_screen):
        super().__init__(login_screen)
        self.login_screen = login_screen
        self.title("Create Account")
        self.resizable(False, False)
        self.transient(login_screen.winfo_toplevel())

        frame = ttk.Frame(self, padding=20)
        frame.pack()

        ttk.Label(frame, text="Create Account", font=HEADING_FONT).grid(
            row=0, column=0, columnspan=2, pady=(0, 15))

        self.full_name = tk.StringVar()
        self.username = tk.StringVar()
        self.password = tk.StringVar()
        self.confirm = tk.StringVar()

        first_entry = add_field(frame, 1, "Full Name:", self.full_name, 30)
        add_field(frame, 2, "Username:", self.username, 30)
        add_field(frame, 3, "Password:", self.password, 30).config(show="*")
        add_field(frame, 4, "Confirm Password:", self.confirm, 30).config(show="*")
        first_entry.focus()

        buttons = ttk.Frame(frame)
        buttons.grid(row=5, column=0, columnspan=2, pady=(15, 0))
        ttk.Button(buttons, text="Create Account", command=self.save).pack(side="left", padx=5)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", padx=5)

        self.bind("<Return>", lambda event: self.save())
        self.bind("<Escape>", lambda event: self.destroy())
        self.grab_set()

    def save(self):
        username = self.username.get().strip()
        full_name = self.full_name.get().strip()
        password = self.password.get()
        confirm = self.confirm.get()

        error = validate_new_account(username, full_name, password, confirm)
        if error:
            messagebox.showwarning("Invalid Input", error, parent=self)
            return

        try:
            create_account(username, full_name, password)
        except Error as err:
            if err.errno == 1062:
                messagebox.showerror(
                    "Username Taken", "That username is already in use.", parent=self)
            else:
                messagebox.showerror(
                    "Database Error", f"Could not create the account.\n\n{err}", parent=self)
            return

        messagebox.showinfo(
            "Account Created", "Account created. You can now log in.", parent=self)
        self.login_screen.username.set(username)
        self.login_screen.password.set("")
        self.destroy()


class LoginScreen(ttk.Frame):
    TITLE = "Barangay Blotter Management System - Login"
    SIZE = (480, 400)

    def __init__(self, app):
        super().__init__(app, padding=30)
        self.app = app

        ttk.Label(self, text="Barangay Blotter\nManagement System",
                  font=HEADING_FONT, justify="center").pack(pady=(0, 5))
        ttk.Label(self, text="Please log in to continue").pack(pady=(0, 20))

        form = ttk.Frame(self)
        form.pack()
        self.username = tk.StringVar()
        self.password = tk.StringVar()
        username_entry = add_field(form, 0, "Username:", self.username, 25)
        password_entry = add_field(form, 1, "Password:", self.password, 25)
        password_entry.config(show="*")

        buttons = ttk.Frame(self)
        buttons.pack(pady=20)
        ttk.Button(buttons, text="Login", command=self.login).pack(side="left", padx=5)
        ttk.Button(buttons, text="Create Account",
                   command=self.open_create_account).pack(side="left", padx=5)

        username_entry.bind("<Return>", lambda event: self.login())
        password_entry.bind("<Return>", lambda event: self.login())
        username_entry.focus()

    def open_create_account(self):
        CreateAccountDialog(self)

    def login(self):
        username = self.username.get().strip()
        password = self.password.get()

        error = validate_login(username, password)
        if error:
            messagebox.showwarning("Invalid Input", error)
            return

        try:
            user = verify_login(username, password)
        except Error as err:
            messagebox.showerror("Database Error", f"Could not check the login.\n\n{err}")
            return

        if user is None:
            messagebox.showerror("Login Failed", "Invalid username or password.")
            self.password.set("")
            return

        self.app.user_name = user["full_name"]
        self.app.show_screen(MainMenu)


class MainMenu(ttk.Frame):
    TITLE = "Main Menu"
    SIZE = (440, 470)

    def __init__(self, app):
        super().__init__(app, padding=30)
        self.app = app

        ttk.Label(self, text="Main Menu", font=HEADING_FONT).pack(pady=(0, 5))
        ttk.Label(self, text=f"Logged in as: {app.user_name}").pack(pady=(0, 20))

        menu = [
            ("Blotter Entry", BlotterEntryScreen),
            ("Search Records", SearchScreen),
            ("Status Update", StatusUpdateScreen),
            ("Hearing Schedule", HearingScreen),
        ]
        for text, screen in menu:
            ttk.Button(self, text=text, width=30,
                       command=lambda s=screen: app.show_screen(s)).pack(pady=6, ipady=6)
        ttk.Button(self, text="Logout", width=30,
                   command=self.logout).pack(pady=6, ipady=6)

    def logout(self):
        if messagebox.askyesno("Logout", "Confirm logout?"):
            self.app.close_app()


class BlotterEntryScreen(ttk.Frame):
    TITLE = "Blotter Entry"
    SIZE = (740, 700)

    def __init__(self, app):
        super().__init__(app, padding=15)
        self.app = app

        ttk.Label(self, text="Blotter Entry", font=HEADING_FONT).pack(pady=(0, 10))

        self.complainant = self.make_person_box("Complainant")
        self.respondent = self.make_person_box("Respondent")

        box = ttk.LabelFrame(self, text="Incident Details", padding=10)
        box.pack(fill="x", pady=5)

        ttk.Label(box, text="Case Type:").grid(row=0, column=0, sticky="e", padx=(0, 10), pady=4)
        self.case_type = tk.StringVar()
        ttk.Combobox(box, textvariable=self.case_type, values=CASE_TYPES,
                     state="readonly", width=40).grid(row=0, column=1, sticky="w", pady=4)

        self.incident_date = tk.StringVar(value=date.today().isoformat())
        add_field(box, 1, "Incident Date:", self.incident_date, 20)
        ttk.Label(box, text="(YYYY-MM-DD)").grid(row=1, column=2, sticky="w", padx=5)

        self.incident_place = tk.StringVar()
        add_field(box, 2, "Incident Place:", self.incident_place, 50)

        ttk.Label(box, text="Narrative:").grid(row=3, column=0, sticky="ne", padx=(0, 10), pady=4)
        self.narrative = tk.Text(box, width=50, height=5, wrap="word")
        self.narrative.grid(row=3, column=1, sticky="w", pady=4)

        buttons = ttk.Frame(self)
        buttons.pack(pady=15)
        ttk.Button(buttons, text="Save", command=self.save).pack(side="left", padx=5)
        ttk.Button(buttons, text="Back",
                   command=lambda: app.show_screen(MainMenu)).pack(side="left", padx=5)

    def make_person_box(self, title):
        box = ttk.LabelFrame(self, text=title, padding=10)
        box.pack(fill="x", pady=5)
        name = tk.StringVar()
        address = tk.StringVar()
        contact = tk.StringVar()
        add_field(box, 0, "Full Name:", name, 50)
        add_field(box, 1, "Address:", address, 50)
        add_field(box, 2, "Contact No.:", contact, 25)
        return name, address, contact

    def save(self):
        data = {
            "complainant_name": self.complainant[0].get().strip(),
            "complainant_address": self.complainant[1].get().strip(),
            "complainant_contact": self.complainant[2].get().strip(),
            "respondent_name": self.respondent[0].get().strip(),
            "respondent_address": self.respondent[1].get().strip(),
            "respondent_contact": self.respondent[2].get().strip(),
            "case_type": self.case_type.get().strip(),
            "incident_date": self.incident_date.get().strip(),
            "incident_place": self.incident_place.get().strip(),
            "narrative": self.narrative.get("1.0", "end").strip(),
        }

        error = validate_blotter(data)
        if error:
            messagebox.showwarning("Invalid Input", error)
            return

        try:
            blotter_no = save_blotter(data)
        except (Error, ValueError) as err:
            messagebox.showerror("Save Failed", f"The blotter could not be saved.\n\n{err}")
            return

        messagebox.showinfo(
            "Blotter Successfully Filed",
            f"Blotter Successfully Filed.\n\nBlotter No.: {blotter_no}")
        self.app.show_screen(MainMenu)


class SearchScreen(ttk.Frame):
    TITLE = "Search Records"
    SIZE = (760, 660)

    def __init__(self, app):
        super().__init__(app, padding=15)
        self.app = app

        ttk.Label(self, text="Search Records", font=HEADING_FONT).pack(pady=(0, 10))

        top = ttk.Frame(self)
        top.pack(fill="x", pady=5)
        ttk.Label(top, text="Search By:").pack(side="left")
        self.search_by = tk.StringVar(value=SEARCH_TYPES[0])
        ttk.Combobox(top, textvariable=self.search_by, values=SEARCH_TYPES,
                     state="readonly", width=16).pack(side="left", padx=5)
        self.search_text = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.search_text, width=30)
        entry.pack(side="left", padx=5)
        entry.bind("<Return>", lambda event: self.search())
        entry.focus()
        ttk.Button(top, text="Search", command=self.search).pack(side="left", padx=5)
        ttk.Label(self, text="For Incident Date, use YYYY-MM-DD.").pack(anchor="w")

        table_frame = ttk.Frame(self)
        table_frame.pack(fill="x", pady=10)
        columns = ("blotter_no", "case_type", "incident_date", "status")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=8)
        headings = ["Blotter No.", "Case Type", "Incident Date", "Status"]
        widths = [110, 300, 120, 140]
        for column, heading, width in zip(columns, headings, widths):
            self.tree.heading(column, text=heading)
            self.tree.column(column, width=width)
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="x", expand=True)
        scrollbar.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.show_details)

        ttk.Label(self, text="Record Details:").pack(anchor="w")
        self.details = tk.Text(self, height=12, wrap="word",
                               font=("Consolas", 10), state="disabled")
        self.details.pack(fill="both", expand=True, pady=5)

        ttk.Button(self, text="Back",
                   command=lambda: app.show_screen(MainMenu)).pack(pady=(5, 0))

    def search(self):
        search_by = self.search_by.get()
        text = self.search_text.get().strip()

        self.tree.delete(*self.tree.get_children())
        set_text(self.details, "")

        error = validate_search(search_by, text)
        if error:
            messagebox.showwarning("Invalid Input", error)
            return

        try:
            rows = search_blotters(search_by, text)
        except Error as err:
            messagebox.showerror("Database Error", f"Could not search the records.\n\n{err}")
            return

        if not rows:
            messagebox.showinfo("No Record Found", "No Record Found.")
            return

        for row in rows:
            self.tree.insert("", "end", iid=str(row["blotter_id"]), values=(
                row["blotter_no"], row["case_type"],
                format_date(row["incident_date"]), row["status"]))

    def show_details(self, event):
        selected = self.tree.selection()
        if not selected:
            return
        try:
            blotter, people, hearings = get_blotter_details(int(selected[0]))
        except Error as err:
            messagebox.showerror("Database Error", f"Could not load the record.\n\n{err}")
            return
        set_text(self.details, build_details_text(blotter, people, hearings))


class StatusUpdateScreen(ttk.Frame):
    TITLE = "Status Update"
    SIZE = (540, 340)

    def __init__(self, app):
        super().__init__(app, padding=20)
        self.app = app
        self.record = None

        ttk.Label(self, text="Status Update", font=HEADING_FONT).pack(pady=(0, 15))

        form = ttk.Frame(self)
        form.pack()

        ttk.Label(form, text="Blotter No.:").grid(row=0, column=0, sticky="e", padx=(0, 10), pady=5)
        self.blotter_no = tk.StringVar()
        self.number_box = ttk.Combobox(form, textvariable=self.blotter_no, width=18)
        self.number_box.grid(row=0, column=1, sticky="w", pady=5)
        self.number_box.bind("<<ComboboxSelected>>", lambda event: self.reset_record())
        load_blotter_numbers(self.number_box)
        ttk.Button(form, text="Find Record", command=self.find_record).grid(
            row=0, column=2, padx=10)

        ttk.Label(form, text="Case Type:").grid(row=1, column=0, sticky="e", padx=(0, 10), pady=5)
        self.case_label = ttk.Label(form, text="-")
        self.case_label.grid(row=1, column=1, columnspan=2, sticky="w")

        ttk.Label(form, text="Current Status:").grid(row=2, column=0, sticky="e", padx=(0, 10), pady=5)
        self.status_label = ttk.Label(form, text="-")
        self.status_label.grid(row=2, column=1, columnspan=2, sticky="w")

        ttk.Label(form, text="New Status:").grid(row=3, column=0, sticky="e", padx=(0, 10), pady=5)
        self.new_status = tk.StringVar()
        self.status_box = ttk.Combobox(form, textvariable=self.new_status, values=STATUSES,
                                       state="disabled", width=22)
        self.status_box.grid(row=3, column=1, columnspan=2, sticky="w", pady=5)

        buttons = ttk.Frame(self)
        buttons.pack(pady=20)
        ttk.Button(buttons, text="Update Status", command=self.update_status).pack(side="left", padx=5)
        ttk.Button(buttons, text="Back",
                   command=lambda: app.show_screen(MainMenu)).pack(side="left", padx=5)

    def reset_record(self):
        self.record = None
        self.case_label.config(text="-")
        self.status_label.config(text="-")
        self.new_status.set("")
        self.status_box.config(state="disabled")

    def find_record(self):
        blotter_no = self.blotter_no.get().strip()
        self.reset_record()
        if not blotter_no:
            messagebox.showwarning("Invalid Input", "Incomplete Fields: Blotter No. is required.")
            return

        try:
            record = get_blotter_by_no(blotter_no)
        except Error as err:
            messagebox.showerror("Database Error", f"Could not find the record.\n\n{err}")
            return

        if record is None:
            messagebox.showinfo("Record Not Found", "Record Not Found.")
            return

        self.record = record
        self.case_label.config(text=record["case_type"])
        self.status_label.config(text=record["status"])
        self.new_status.set(record["status"])
        self.status_box.config(state="readonly")

    def update_status(self):
        if self.record is None or self.blotter_no.get().strip() != self.record["blotter_no"]:
            messagebox.showwarning("Find Record First", "Please find the record first.")
            return

        new_status = self.new_status.get()
        if not new_status:
            messagebox.showwarning("Invalid Input", "Incomplete Fields: New Status is required.")
            return
        if new_status == self.record["status"]:
            messagebox.showinfo("No Change", "The record already has that status.")
            return

        confirmed = messagebox.askyesno(
            "Confirm Update",
            f"Change the status of {self.record['blotter_no']}\n"
            f"from '{self.record['status']}' to '{new_status}'?")
        if not confirmed:
            messagebox.showinfo("Cancelling Update", "Cancelling Update.")
            self.app.show_screen(MainMenu)
            return

        try:
            update_blotter_status(self.record["blotter_id"], new_status)
        except Error as err:
            messagebox.showerror("Update Failed", f"Could not update the status.\n\n{err}")
            return

        messagebox.showinfo("Status Updated Successfully", "Status Updated Successfully.")
        self.app.show_screen(MainMenu)


class HearingScreen(ttk.Frame):
    TITLE = "Hearing Schedule"
    SIZE = (600, 420)

    def __init__(self, app):
        super().__init__(app, padding=20)
        self.app = app
        self.record = None

        ttk.Label(self, text="Hearing Schedule", font=HEADING_FONT).pack(pady=(0, 15))

        form = ttk.Frame(self)
        form.pack()

        ttk.Label(form, text="Blotter No.:").grid(row=0, column=0, sticky="e", padx=(0, 10), pady=5)
        self.blotter_no = tk.StringVar()
        self.number_box = ttk.Combobox(form, textvariable=self.blotter_no, width=18)
        self.number_box.grid(row=0, column=1, sticky="w", pady=5)
        self.number_box.bind("<<ComboboxSelected>>", lambda event: self.lock_inputs())
        load_blotter_numbers(self.number_box)
        ttk.Button(form, text="Check Record", command=self.check_record).grid(
            row=0, column=2, padx=10)

        self.info_label = ttk.Label(form, text="-")
        self.info_label.grid(row=1, column=0, columnspan=3, sticky="w", pady=5)

        self.hearing_date = tk.StringVar()
        self.hearing_time = tk.StringVar()
        self.venue = tk.StringVar()
        self.lupon_panel = tk.StringVar()
        self.inputs = [
            add_field(form, 2, "Hearing Date:", self.hearing_date, 20),
            add_field(form, 3, "Hearing Time:", self.hearing_time, 20),
            add_field(form, 4, "Venue:", self.venue, 40),
            add_field(form, 5, "Assigned Lupon Panel:", self.lupon_panel, 40),
        ]
        ttk.Label(form, text="(YYYY-MM-DD)").grid(row=2, column=2, sticky="w")
        ttk.Label(form, text="(HH:MM, 24-hour)").grid(row=3, column=2, sticky="w")
        self.lock_inputs()

        buttons = ttk.Frame(self)
        buttons.pack(pady=20)
        ttk.Button(buttons, text="Save Hearing", command=self.save_hearing).pack(side="left", padx=5)
        ttk.Button(buttons, text="Back",
                   command=lambda: app.show_screen(MainMenu)).pack(side="left", padx=5)

    def lock_inputs(self):
        self.record = None
        self.info_label.config(text="-")
        for entry in self.inputs:
            entry.config(state="disabled")

    def unlock_inputs(self):
        for entry in self.inputs:
            entry.config(state="normal")

    def check_record(self):
        blotter_no = self.blotter_no.get().strip()
        self.lock_inputs()
        if not blotter_no:
            messagebox.showwarning("Invalid Input", "Incomplete Fields: Blotter No. is required.")
            return

        try:
            record = get_blotter_by_no(blotter_no)
        except Error as err:
            messagebox.showerror("Database Error", f"Could not check the record.\n\n{err}")
            return

        if record is None:
            messagebox.showinfo("Record Not Found", "Record Not Found.")
            return

        self.info_label.config(
            text=f"{record['case_type']}  |  Status: {record['status']}")
        if record["status"] != STATUS_FOR_HEARING:
            messagebox.showwarning(
                "Not Eligible for Scheduling",
                "Not Eligible for Scheduling.\n\n"
                f"Only records with the status '{STATUS_FOR_HEARING}' can be scheduled.")
            return

        self.record = record
        self.unlock_inputs()

    def save_hearing(self):
        if self.record is None or self.blotter_no.get().strip() != self.record["blotter_no"]:
            messagebox.showwarning("Check Record First", "Please check the record first.")
            return

        data = {
            "hearing_date": self.hearing_date.get().strip(),
            "hearing_time": self.hearing_time.get().strip(),
            "venue": self.venue.get().strip(),
            "lupon_panel": self.lupon_panel.get().strip(),
        }
        error = validate_hearing(data)
        if error:
            messagebox.showwarning("Invalid Input", error)
            return

        hearing_id = self.save_with_retry(data)
        if hearing_id is None:
            self.app.show_screen(MainMenu)
            return

        try:
            rows = get_summon_data(hearing_id)
        except Error as err:
            messagebox.showerror(
                "Summon Letter Error",
                "The hearing was saved, but the summon letter could not be created.\n\n"
                f"{err}")
            self.app.show_screen(MainMenu)
            return

        preview = SummonPreview(self, build_letter(rows),
                                f"summon_{self.record['blotter_no']}.pdf")
        self.wait_window(preview)

        messagebox.showinfo("Hearing Scheduled Successfully",
                            "Hearing Scheduled Successfully.")
        self.app.show_screen(MainMenu)

    def save_with_retry(self, data):
        while True:
            try:
                return save_hearing_record(self.record["blotter_id"], data)
            except Error as err:
                retry = messagebox.askretrycancel(
                    "Save Failed", f"The hearing could not be saved.\n\n{err}")
                if not retry:
                    return None


# ---------------------------------------------------------------
# Main window
# ---------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.current = None
        self.user_name = ""
        self.protocol("WM_DELETE_WINDOW", self.close_app)

    def show_screen(self, screen_class):
        if self.current is not None:
            self.current.destroy()
        self.current = screen_class(self)
        self.current.pack(fill="both", expand=True)

        width, height = screen_class.SIZE
        x = (self.winfo_screenwidth() - width) // 2
        y = max((self.winfo_screenheight() - height) // 2 - 20, 0)
        self.title(screen_class.TITLE)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.resizable(False, False)

    def close_app(self):
        close_db()
        self.destroy()


def main():
    app = App()
    app.withdraw()
    try:
        setup_database()
    except Error as err:
        messagebox.showerror(
            "Database Error",
            "Could not set up the database.\n"
            "Make sure MySQL is running in XAMPP and the settings at the top "
            f"of the file are correct.\n\n{err}")
        app.destroy()
        return
    app.deiconify()
    app.show_screen(LoginScreen)
    app.mainloop()


if __name__ == "__main__":
    main()