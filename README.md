# Barangay Blotter Management System

A desktop program for recording barangay blotter cases, made with Python (Tkinter) and MySQL (XAMPP).

## Features

- Login and Create Account
- Blotter Entry with automatic blotter number (YYYY-NNNN)
- Search Records by name, blotter number or incident date
- Status Update (Pending, For Hearing, Settled, Referred to Police)
- Hearing Schedule with summon letter preview and PDF export

The program creates the database and tables by itself on first run. No manual SQL import is needed.

## Requirements

- Windows
- [Python 3.10 or newer](https://www.python.org/downloads/) (check "Add Python to PATH" during install)
- [XAMPP](https://www.apachefriends.org/) with MySQL

## Installation

1. Download this project: click the green **Code** button, then **Download ZIP**, then extract it.
   (Or `git clone` the repository.)

2. Open **XAMPP Control Panel** and click **Start** next to **MySQL**.

3. Open **Command Prompt** inside the project folder and install the packages:

   ```
   pip install -r requirements.txt
   ```

4. Run the program:

   ```
   python System.py
   ```

5. Log in with the default account:

   - Username: `admin`
   - Password: `admin123`

   Change this after the first login by creating your own account from the Login screen.

## Settings

If your MySQL uses a password or a different user, edit the top of `System.py`:

```python
DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = ""
DB_NAME = "barangay_blotter"
BARANGAY_NAME = "BARANGAY ____________"
```

Put your barangay name in `BARANGAY_NAME`. It appears on the summon letter.

## Troubleshooting

| Problem | What to do |
|---|---|
| "Database Error" on start | Make sure MySQL is started in XAMPP. Check `DB_USER` and `DB_PASSWORD`. |
| `No module named mysql` or `fpdf` | Run `pip install -r requirements.txt` again. |
| `python` is not recognized | Reinstall Python and check "Add Python to PATH". |
| PDF export fails | Run `pip install fpdf2`. |
| Program freezes on save | Stop and Start MySQL in XAMPP, then run the program again. |

## Project files

```
System.py                  main program (GUI, validation, database, migration)
requirements.txt           Python packages
sql/blotter_system.sql     database script (reference only; the program creates the tables)
diagrams/                  editable draw.io files (DFD, ERD, schema, flowcharts, UI mockup)
```

## Known limitations

- Passwords are stored as unsalted SHA-256 hashes.
- One complainant and one respondent per blotter.
- Blotter records cannot be edited or deleted, only the status can change.
- PDF export uses the Helvetica font, so some special characters may appear as `?`.
- No printing. Export the PDF and print it from a PDF reader.
- The program does not alter tables that already exist. If you used an older version, delete the `barangay_blotter` database in phpMyAdmin first.