from flask import Flask, render_template, request, redirect, url_for, send_file, session
import sqlite3
import openpyxl
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'depot_secret_key_12345'
DB_FILE = 'booking.db'

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "111"

# Функция для вывода даты на русском (например: "понедельник, 02.11.2026")
def get_current_date_str():
    days = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье']
    months = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
    now = datetime.now()
    day_name = days[now.weekday()]
    return f"{day_name}, {now.strftime('%d.%m.%Y')}"

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
                    print(f"Ошибка чтения Excel: {e}")
                    
        elif action == 'approve':
            c.execute("UPDATE settings SET value='1' WHERE key='is_approved'")
            conn.commit()
            
        elif action == 'cancel_slot':
            slot_id = request.form.get('slot_id')
            if slot_id:
                c.execute("UPDATE slots SET is_booked=0, fio='', purpose='' WHERE id=?", (slot_id,))
                c.execute("UPDATE settings SET value='0' WHERE key='is_approved'")
                conn.commit()
                
        return redirect(url_for('admin'))
            
    c.execute("SELECT id, time_start, time_end, fio, purpose FROM slots WHERE is_booked=1 ORDER BY id")
    booked = c.fetchall()
    
    c.execute("SELECT value FROM settings WHERE key='is_approved'")
    is_approved = c.fetchone()[0] == '1'
    
    conn.close()
    date_str = get_current_date_str()
    return render_template('admin.html', booked=booked, is_approved=is_approved, date_str=date_str)

@app.route('/export')
def export():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
        
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute("SELECT value FROM settings WHERE key='is_approved'")
    is_approved = c.fetchone()[0] == '1'
    
    if not is_approved:
        conn.close()
        return "Ошибка: График не утвержден! Сначала нажмите кнопку «Утвердить график».", 403
        
    c.execute("SELECT time_start || ' - ' || time_end as 'Время', fio as 'ФИО', purpose as 'Цель' FROM slots WHERE is_booked=1 ORDER BY id")
    rows = c.fetchall()
    conn.close()
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Записи"
    ws.append(['Время', 'ФИО', 'Цель'])
    for r in rows:
        ws.append(list(r))
        
    filename = f"raspisanie_{datetime.now().strftime('%d_%m_%Y')}.xlsx"
    wb.save(filename)
    return send_file(filename, as_attachment=True)

import os

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)