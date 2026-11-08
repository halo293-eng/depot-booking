from flask import Flask, render_template, request, redirect, url_for, send_file, session
import sqlite3
import openpyxl
import os
from datetime import datetime, timezone, timedelta

app = Flask(__name__, template_folder='.')
app.secret_key = 'depot_secret_key_12345'
DB_FILE = 'booking.db'

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "depot_password_123"

# Функция для вывода даты на завтра по Московскому времени (UTC+3)
def get_current_date_str():
    days = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье']
    MSK = timezone(timedelta(hours=3))
    tomorrow = datetime.now(MSK) + timedelta(days=1)
    day_name = days[tomorrow.weekday()]
    return f"{day_name}, {tomorrow.strftime('%d.%m.%Y')}"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS slots
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  time_start TEXT,
                  time_end TEXT,
                  is_booked INTEGER DEFAULT 0, 
                  fio TEXT DEFAULT '', 
                  purpose TEXT DEFAULT '')''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS settings
                 (key TEXT PRIMARY KEY, value TEXT)''')
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('is_approved', '0')")
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, time_start, time_end, is_booked FROM slots ORDER BY id")
    slots = c.fetchall()
    conn.close()
    
    date_str = get_current_date_str()
    return render_template('index.html', slots=slots, date_str=date_str)

@app.route('/book', methods=['POST'])
def book():
    slot_id = request.form.get('slot_id')
    fio = request.form.get('fio')
    purpose = request.form.get('purpose')
    
    if slot_id and fio:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT is_booked FROM slots WHERE id=?", (slot_id,))
        res = c.fetchone()
        if res and res[0] == 0:
            c.execute("UPDATE slots SET is_booked=1, fio=?, purpose=? WHERE id=?", (fio, purpose, slot_id))
            c.execute("UPDATE settings SET value='0' WHERE key='is_approved'")
            conn.commit()
        conn.close()
    return redirect(url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form.get('username') == ADMIN_USERNAME and request.form.get('password') == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('admin'))
        else:
            error = 'Неверный логин или пароль'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
        
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'upload':
            file = request.files.get('file')
            if file and file.filename != '':
                try:
                    wb = openpyxl.load_workbook(file)
                    sheet = wb.active
                    c.execute("DELETE FROM slots")
                    
                    for row in sheet.iter_rows(min_row=2, values_only=True):
                        if row[0] is not None and row[1] is not None:
                            t_start = str(row[0]).strip()
                            t_end = str(row[1]).strip()
                            status = str(row[2]).strip() if len(row) > 2 and row[2] else "Свободно"
                            is_booked = 1 if status.lower() == "занято" else 0
                            
                            c.execute("INSERT INTO slots (time_start, time_end, is_booked) VALUES (?, ?, ?)", 
                                      (t_start, t_end, is_booked))
                    
                    c.execute("UPDATE settings SET value='0' WHERE key='is_approved'")
                    conn.commit()
                except Exception as e:
