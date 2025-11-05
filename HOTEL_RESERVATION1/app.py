from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import MySQLdb
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev_secret_key")

def get_db():
    return MySQLdb.connect(
        host="localhost",
        user="root",
        passwd="",
        db="hotel_db",
        charset="utf8",
        autocommit=False
    )

def init_db():
    db = get_db()
    cur = db.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(150) NOT NULL,
        address VARCHAR(255),
        age INT,
        contact VARCHAR(20),
        email VARCHAR(150) UNIQUE,
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
        booked_by INT,
        check_in VARCHAR(100),
        check_out VARCHAR(100),
        room_type VARCHAR(50),
        floor INT,
        FOREIGN KEY (booked_by) REFERENCES users(id) ON DELETE SET NULL
    ) ENGINE=InnoDB;
    """)

    cur.execute("SELECT id FROM users WHERE email=%s", ("admin@example.com",))
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO users (name, address, age, contact, email, password_hash, is_admin)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, ("Admin", "Admin Address", 30, "09123456789",
              "admin@example.com", generate_password_hash("admin123"), 1))
        db.commit()

    cur.execute("SELECT COUNT(*) FROM rooms")
    if cur.fetchone()[0] == 0:
        rooms_dict = {
            "Executive": [101, 201, 301, 401],
            "Deluxe": [102, 202, 302, 402],
            "Standard": [103, 203, 303, 403],
            "Family": [104, 204, 304, 404]
        }
        for room_type, numbers in rooms_dict.items():
            for room_number in numbers:
                floor = room_number // 100
                cur.execute("""
                    INSERT INTO rooms (number, room_type, floor, status)
                    VALUES (%s, %s, %s, 'vacant')
                """, (room_number, room_type, floor))
        db.commit()

    cur.close()
    db.close()

@app.route("/")
def home():
    return redirect(url_for("login"))

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method=="POST":
        name = request.form["name"]
        address = request.form.get("address")
        age = request.form.get("age")
        contact = request.form.get("contact")
        email = request.form["email"]
        password = request.form["password"]

        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT * FROM users WHERE email=%s", (email,))
        if cur.fetchone():
            flash("Email already registered!", "danger")
            cur.close(); db.close()
            return redirect(url_for("register"))

        password_hash = generate_password_hash(password)
        cur.execute("""
            INSERT INTO users (name, address, age, contact, email, password_hash)
            VALUES (%s,%s,%s,%s,%s,%s)
        """,(name,address,age,contact,email,password_hash))
        db.commit()
        cur.close(); db.close()

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        email = request.form["email"]
        password = request.form["password"]

        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT id,name,password_hash,is_admin FROM users WHERE email=%s", (email,))
        user = cur.fetchone()
        cur.close(); db.close()

        if user and check_password_hash(user[2], password):
            session["user_id"]=user[0]
            session["user_name"]=user[1]
            session["is_admin"]=user[3]

            if user[3]==1:
                return redirect(url_for("admin_dashboard"))
            else:
                return redirect(url_for("user_dashboard"))
        else:
            flash("Invalid email or password!","danger")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))

@app.route("/user_dashboard")
def user_dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id, number, room_type, floor, status FROM rooms ORDER BY number")
    rooms = cur.fetchall()
    cur.close(); db.close()

    rooms_dict = {}
    for r in rooms:
        rooms_dict.setdefault(r[2], []).append(r)

    return render_template("user_dashboard.html", rooms_dict=rooms_dict, user=session.get("user_name"))

@app.route("/book_room", methods=["POST"])
def book_room():
    if "user_id" not in session:
        return jsonify({"status":"error","message":"You must log in first!"})

    room_number = request.form.get("room_number")
    check_in = request.form.get("check_in")
    check_out = request.form.get("check_out")

    if not all([room_number, check_in, check_out]):
        return jsonify({"status":"error","message":"All fields are required."})

    room_number = int(room_number)

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id,status FROM rooms WHERE number=%s LIMIT 1",(room_number,))
    room = cur.fetchone()
    if not room:
        cur.close(); db.close()
        return jsonify({"status":"error","message":"Room not found."})

    room_id, status = room
    if status!="vacant":
        cur.close(); db.close()
        return jsonify({"status":"error","message":"Room is already booked."})

    cur.execute("""
        UPDATE rooms 
        SET status='booked', booked_by=%s, check_in=%s, check_out=%s
        WHERE id=%s
    """,(session["user_id"], check_in, check_out, room_id))
    db.commit()
    cur.close(); db.close()

    return jsonify({"status":"success","message":f"Room {room_number} booked successfully."})

@app.route("/admin_dashboard", methods=["GET","POST"])
def admin_dashboard():
    if "user_id" not in session or session.get("is_admin") != 1:
        flash("Access denied!", "danger")
        return redirect(url_for("login"))

    db = get_db()
    cur = db.cursor()

    if request.method=="POST":
        form_data = request.form

        if "delete_booking" in form_data:
            room_id = form_data["delete_booking"]
            try:
                cur.execute("""
                    UPDATE rooms 
                    SET booked_by=NULL, check_in=NULL, check_out=NULL, status='vacant' 
                    WHERE id=%s
                """,(room_id,))
                db.commit()
                return jsonify({"status":"success","message":"Booking deleted successfully"})
            except Exception as e:
                db.rollback()
                return jsonify({"status":"error","message":str(e)})

        if "update_room" in form_data:
            room_id = form_data["update_room"]
            booked_by = form_data.get("booked_by") or None
            check_in = form_data.get("check_in") or None
            check_out = form_data.get("check_out") or None
            status = "vacant" if not booked_by else "booked"
            try:
                cur.execute("""
                    UPDATE rooms 
                    SET booked_by=%s, check_in=%s, check_out=%s, status=%s
                    WHERE id=%s
                """,(booked_by, check_in, check_out, status, room_id))
                db.commit()
                return jsonify({"status":"success","message":"Room updated successfully","new_status":status.capitalize()})
            except Exception as e:
                db.rollback()
                return jsonify({"status":"error","message":str(e)})

        if "add_user" in form_data:
            name = form_data.get("name")
            email = form_data.get("email")
            password = form_data.get("password")
            if name and email and password:
                try:
                    cur.execute("INSERT INTO users (name,email,password_hash) VALUES (%s,%s,%s)",
                                (name,email,generate_password_hash(password)))
                    db.commit()
                    return redirect(url_for("admin_dashboard"))
                except Exception as e:
                    db.rollback()
                    flash(str(e),"danger")

    cur.execute("""SELECT r.id,r.number,r.status,u.name,r.check_in,r.check_out 
        FROM rooms r LEFT JOIN users u ON r.booked_by=u.id ORDER BY r.number""")
    rooms = cur.fetchall()

    cur.execute("SELECT id,name,email,is_admin FROM users ORDER BY id")
    users = cur.fetchall()

    cur.close(); db.close()
    return render_template("admin_dashboard.html", rooms=rooms, users=users)

if __name__=="__main__":
    init_db()
    app.run(debug=True)
