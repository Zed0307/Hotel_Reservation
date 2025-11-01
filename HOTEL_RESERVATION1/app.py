from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import MySQLdb
from werkzeug.security import generate_password_hash, check_password_hash
import os
from functools import wraps
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev_secret_key")

DB_HOST = "localhost"
DB_USER = "root"
DB_PASS = ""  
DB_NAME = "hotel_db"

def get_db():
    return MySQLdb.connect(host=DB_HOST, user=DB_USER, passwd=DB_PASS, db=DB_NAME, charset='utf8')

def init_db():
    db = get_db()
    cur = db.cursor()
    # Users table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(150) NOT NULL,
        email VARCHAR(150) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL,
        is_admin TINYINT(1) DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB;
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS rooms (
        id INT AUTO_INCREMENT PRIMARY KEY,
        number INT NOT NULL UNIQUE,
        status VARCHAR(20) DEFAULT 'vacant',
        booked_by INT NULL,
        check_in VARCHAR(100) NULL,
        check_out VARCHAR(100) NULL,
        FOREIGN KEY (booked_by) REFERENCES users(id) ON DELETE SET NULL
    ) ENGINE=InnoDB;
    """)
    db.commit()

    cur.execute("SELECT id FROM users WHERE email=%s", ("admin@example.com",))
    if not cur.fetchone():
        cur.execute("INSERT INTO users (name,email,password_hash,is_admin) VALUES (%s,%s,%s,%s)",
                    ("Admin", "admin@example.com", generate_password_hash("admin123"), 1))
        db.commit()

    cur.execute("SELECT number FROM rooms")
    existing = set(n for (n,) in cur.fetchall())
    for floor in range(1,6):
        for r in range(1,6):
            room_no = floor*100 + r
            if room_no not in existing:
                cur.execute("INSERT INTO rooms (number,status) VALUES (%s,'vacant')",(room_no,))
    db.commit()
    cur.close()
    db.close()

init_db()

def current_user():
    if 'user_id' in session:
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT id,name,email,is_admin FROM users WHERE id=%s",(session['user_id'],))
        row = cur.fetchone()
        cur.close()
        db.close()
        if row:
            return {"id":row[0], "name":row[1], "email":row[2], "is_admin":bool(row[3])}
    return None

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = current_user()
        if not user or not user['is_admin']:
            session.clear()
            flash("Admin only access","danger")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    user = current_user()
    if user:
        if user['is_admin']:
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('user_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT id,password_hash,is_admin FROM users WHERE email=%s",(email,))
        row = cur.fetchone()
        cur.close()
        db.close()
        if row and check_password_hash(row[1],password):
            session['user_id'] = row[0]
            flash("Welcome!", "success")
            return redirect(url_for('index'))
        flash("Invalid email or password","danger")
    return render_template('login.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='POST':
        name = request.form.get('name')
        email = request.form.get('email').strip().lower()
        password = request.form.get('password')
        db = get_db()
        cur = db.cursor()
        if email=="admin@example.com":
            flash("Cannot register as admin","danger")
            return redirect(url_for('register'))
        try:
            cur.execute("INSERT INTO users (name,email,password_hash) VALUES (%s,%s,%s)",
                        (name,email,generate_password_hash(password)))
            db.commit()
            cur.execute("SELECT id FROM users WHERE email=%s",(email,))
            session['user_id'] = cur.fetchone()[0]
            flash("Registration successful!","success")
            return redirect(url_for('user_dashboard'))
        except MySQLdb.IntegrityError:
            flash("Email already registered","danger")
        cur.close()
        db.close()
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.","info")
    return redirect(url_for('login'))

@app.route('/user')
def user_dashboard():
    user = current_user()
    if not user:
        return redirect(url_for('login'))
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id,number,status,booked_by,check_in,check_out FROM rooms ORDER BY number")
    rooms = cur.fetchall()
    cur.close()
    db.close()
    room_list=[]
    for r in rooms:
        room_list.append({
            "id": r[0],
            "number": r[1],
            "status": r[2],
            "booked_by": r[3],
            "check_in": r[4],
            "check_out": r[5]
        })
    return render_template('user_dashboard.html', user=user, rooms=room_list)

@app.route('/reserve_room', methods=['POST'])
def reserve_room():
    user = current_user()
    if not user:
        return jsonify({"status":"error","message":"Not logged in"})
    room_id = request.form.get('room_id')
    check_in = request.form.get('check_in')
    check_out = request.form.get('check_out')

    try:
        ci = datetime.strptime(check_in, "%Y-%m-%dT%H:%M")
        co = datetime.strptime(check_out, "%Y-%m-%dT%H:%M")
        if co <= ci:
            return jsonify({"status":"error","message":"Check-out must be after check-in"})
    except:
        return jsonify({"status":"error","message":"Invalid datetime format"})

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT status,check_in,check_out FROM rooms WHERE id=%s",(room_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        db.close()
        return jsonify({"status":"error","message":"Room not found"})
    elif row[0]=='booked':
        cur.close()
        db.close()
        return jsonify({"status":"error","message":"Room already booked"})
    else:
    
        cur.execute("SELECT check_in,check_out FROM rooms WHERE id=%s",(room_id,))
        existing = cur.fetchone()
        if existing[0] and existing[1]:
            e_ci = datetime.strptime(existing[0], "%Y-%m-%dT%H:%M")
            e_co = datetime.strptime(existing[1], "%Y-%m-%dT%H:%M")
            if (ci <= e_co and co >= e_ci):
                cur.close()
                db.close()
                return jsonify({"status":"error","message":"Cannot book overlapping reservation"})
        cur.execute("UPDATE rooms SET status='booked', booked_by=%s, check_in=%s, check_out=%s WHERE id=%s",
                    (user['id'], check_in, check_out, room_id))
        db.commit()
        cur.close()
        db.close()
        return jsonify({"status":"success","message":"Room booked successfully!"})

@app.route('/admin', methods=['GET','POST'])
@admin_required
def admin_dashboard():
    user = current_user()
    db = get_db()
    cur = db.cursor()

    if request.method=='POST':
        if 'add_user' in request.form:
            name = request.form.get('name')
            password = request.form.get('password')
            email = f"{name.lower()}@hotel.com"
            try:
                cur.execute("INSERT INTO users (name,email,password_hash) VALUES (%s,%s,%s)", 
                            (name,email,generate_password_hash(password)))
                db.commit()
                flash("User added!","success")
            except MySQLdb.IntegrityError:
                flash("User already exists","danger")
        uid = request.form.get('edit_user')
        if uid:
            name = request.form.get('name')
            password = request.form.get('password')
            if password:
                cur.execute("UPDATE users SET name=%s, password_hash=%s WHERE id=%s AND is_admin=0",
                            (name,generate_password_hash(password),uid))
            else:
                cur.execute("UPDATE users SET name=%s WHERE id=%s AND is_admin=0",(name,uid))
            db.commit()
            flash("User updated!","success")
        uid = request.form.get('delete_user')
        if uid:
            cur.execute("DELETE FROM users WHERE id=%s AND is_admin=0",(uid,))
            db.commit()
            flash("User deleted!","info")
        rid = request.form.get('update_room')
        if rid:
            booked_by = request.form.get('booked_by') or None
            check_in = request.form.get('check_in') or None
            check_out = request.form.get('check_out') or None
            status = 'booked' if booked_by else 'vacant'
            cur.execute("UPDATE rooms SET status=%s, booked_by=(SELECT id FROM users WHERE name=%s), check_in=%s, check_out=%s WHERE id=%s",
                        (status, booked_by, check_in, check_out, rid))
            db.commit()
            flash("Room updated!","success")
        rid = request.form.get('release_room')
        if rid:
            cur.execute("UPDATE rooms SET status='vacant', booked_by=NULL, check_in=NULL, check_out=NULL WHERE id=%s",(rid,))
            db.commit()
            flash("Room released!","info")

    cur.execute("""
        SELECT r.id,r.number,r.status,u.name,r.check_in,r.check_out 
        FROM rooms r LEFT JOIN users u ON r.booked_by=u.id 
        ORDER BY r.number
    """)
    rooms = cur.fetchall()
    cur.execute("SELECT id,name,email,is_admin FROM users ORDER BY created_at DESC")
    users = cur.fetchall()
    cur.close()
    db.close()
    return render_template('admin_dashboard.html', admin=user, rooms=rooms, users=users)

@app.route('/api/rooms')
@admin_required
def api_rooms():
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT r.id, r.number, r.status, u.name, r.check_in, r.check_out
        FROM rooms r LEFT JOIN users u ON r.booked_by=u.id
        ORDER BY r.number
    """)
    rooms = cur.fetchall()
    cur.close()
    db.close()
    room_list = []
    for r in rooms:
        room_list.append({
            "id": r[0],
            "number": r[1],
            "status": r[2],
            "booked_by": r[3],
            "check_in": r[4],
            "check_out": r[5]
        })
    return jsonify({"rooms": room_list})

if __name__=='__main__':
    app.run(debug=True)

