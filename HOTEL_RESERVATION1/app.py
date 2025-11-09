from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import MySQLdb
import hashlib
import MySQLdb.cursors
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev_secret_key")

def get_db(database="hotel_db"):
    db = MySQLdb.connect(
        host="127.0.0.1",
        port=3306,
        user="root",
        passwd="",
        charset="utf8",
        autocommit=True
    )

    cur = db.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS {database} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
    cur.close()
    db.close()

    db = MySQLdb.connect(
        host="127.0.0.1",
        port=3306,
        user="root",
        passwd="",
        db=database,
        charset="utf8",
        autocommit=False
    )
    return db

def log_manager_action(manager_id, action_type, booking_id=None, user_id=None, description=None):
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO manager_actions (manager_id, action_type, booking_id, user_id, description)
            VALUES (%s, %s, %s, %s, %s)
        """, (manager_id, action_type, booking_id, user_id, description))
        db.commit()
    except Exception as e:
        db.rollback()
        print("Error logging manager action:", e)
    finally:
        cur.close()
        db.close()

def init_db():
    db = get_db()
    cur = db.cursor()

    # Users table
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

    # Rooms table
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
        payment_status ENUM('Pending','Paid') DEFAULT 'Pending',
        FOREIGN KEY (booked_by) REFERENCES users(id) ON DELETE SET NULL
    ) ENGINE=InnoDB;
    """)

    # Manager actions table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS manager_actions (
        id INT AUTO_INCREMENT PRIMARY KEY,
        manager_id INT NOT NULL,
        action_type VARCHAR(50) NOT NULL,
        booking_id INT DEFAULT NULL,
        user_id INT DEFAULT NULL,
        description TEXT,
        action_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (manager_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (booking_id) REFERENCES rooms(id) ON DELETE SET NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
    ) ENGINE=InnoDB;
    """)

    # Default admin
    cur.execute("SELECT id FROM users WHERE email=%s", ("admin@example.com",))
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO users (name, address, age, contact, email, password_hash, is_admin)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, ("Admin", "Admin Address", 30, "09123456789",
              "admin@example.com", generate_password_hash("admin123"), 1))
        db.commit()

    # Default manager
    cur.execute("SELECT id FROM users WHERE email=%s", ("manager@example.com",))
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO users (name, address, age, contact, email, password_hash, is_admin)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, ("Manager", "Manager Address", 28, "09123456788",
              "manager@example.com", generate_password_hash("manager123"), 2))
        db.commit()

    # Populate rooms if empty
    cur.execute("SELECT COUNT(*) FROM rooms")
    if cur.fetchone()[0] == 0:
        rooms_dict = {
            "Executive": [101,201,301,401],
            "Deluxe": [102, 202, 302, 402],
            "Standard": [103, 203, 303, 403],
            "Family": [104, 204, 304, 404]
        }
        for room_type, numbers in rooms_dict.items():
            for room_number in numbers:
                floor = room_number // 100
                cur.execute("""
                    INSERT INTO rooms (number, room_type, floor, status, payment_status)
                    VALUES (%s, %s, %s, 'vacant', 'Pending')
                """, (room_number, room_type, floor))
        db.commit()

    cur.close()
    db.close()

@app.route("/")
def home():
    return redirect(url_for("login"))

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
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
        """, (name, address, age, contact, email, password_hash))
        db.commit()
        cur.close(); db.close()

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email").lower()
        password = request.form.get("password")

        db = get_db()
        cur = db.cursor(MySQLdb.cursors.DictCursor)
        cur.execute("SELECT id, name, password_hash, is_admin FROM users WHERE LOWER(email)=%s", (email,))
        user = cur.fetchone()
        cur.close()
        db.close()

        if user:
            # Try check with werkzeug hash first (normal users)
            if check_password_hash(user['password_hash'], password):
                valid_password = True
            else:
                # Fallback to MD5 check (admin/manager)
                password_md5 = hashlib.md5(password.encode()).hexdigest()
                valid_password = user['password_hash'] == password_md5

            if valid_password:
                # Set session
                session["user_id"] = user['id']
                session["user_name"] = user['name']
                session["is_admin"] = user['is_admin']

                # Redirect based on role
                if user['is_admin'] == 1:
                    return redirect(url_for("admin_dashboard"))
                elif user['is_admin'] == 2:
                    return redirect(url_for("manager_dashboard"))
                else:
                    return redirect(url_for("user_dashboard"))
            else:
                flash("Invalid email or password!", "danger")
        else:
            flash("Invalid email or password!", "danger")

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
    cur = db.cursor(MySQLdb.cursors.DictCursor)

    cur.execute("SELECT id, number, room_type, floor, status, check_in, check_out, payment_status FROM rooms ORDER BY number")
    rooms = cur.fetchall()

    cur.execute("SELECT number, room_type, check_in, check_out, payment_status FROM rooms WHERE booked_by=%s ORDER BY number LIMIT 1", (session["user_id"],))
    user_booking = cur.fetchone()

    cur.close(); db.close()

    room_numbers = {}
    for r in rooms:
        room_numbers.setdefault(r["room_type"], []).append(r["number"])

    return render_template(
        "user_dashboard.html",
        room_numbers=room_numbers,
        user=session.get("user_name"),
        user_booking=user_booking
    )

@app.route("/book_room", methods=["POST"])
def book_room():
    if "user_id" not in session:
        return jsonify({"status":"error","message":"You must log in first!"})

    room_number = request.form.get("room_number")
    check_in = request.form.get("check_in")
    check_out = request.form.get("check_out")
    room_type = request.form.get("room_type")

    if not all([room_number, check_in, check_out, room_type]):
        return jsonify({"status":"error","message":"All fields are required."})

    room_number = int(room_number)

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id,status FROM rooms WHERE number=%s LIMIT 1", (room_number,))
    room = cur.fetchone()
    if not room:
        cur.close(); db.close()
        return jsonify({"status":"error","message":"Room not found."})

    room_id, status = room
    if status != "vacant":
        cur.close(); db.close()
        return jsonify({"status":"error","message":"Room is already booked."})

    cur.execute("""
        UPDATE rooms 
        SET status='booked', booked_by=%s, check_in=%s, check_out=%s, payment_status='Pending'
        WHERE id=%s
    """, (session["user_id"], check_in, check_out, room_id))
    db.commit()
    cur.close(); db.close()

    return jsonify({"status":"success","message":f"Room {room_number} booked successfully."})

@app.route("/edit_booking", methods=["POST"])
def edit_booking():
    if "user_id" not in session:
        return jsonify({"status": "error", "message": "Login required."})

    user_id = session["user_id"]
    new_room_type = request.form.get("room_type")
    new_room_number = request.form.get("room_number")
    new_check_in = request.form.get("new_check_in")
    new_check_out = request.form.get("new_check_out")

    if not all([new_room_type, new_room_number, new_check_in, new_check_out]):
        return jsonify({"status": "error", "message": "All fields are required."})

    try:
        new_room_number = int(new_room_number)
    except ValueError:
        return jsonify({"status": "error", "message": "Invalid room number."})

    db = get_db()
    cur = db.cursor(MySQLdb.cursors.DictCursor)

    try:
        cur.execute("""
            SELECT * FROM rooms
            WHERE number=%s AND booked_by IS NOT NULL AND booked_by != %s
        """, (new_room_number, user_id))
        conflict = cur.fetchone()
        if conflict:
            return jsonify({"status": "error", "message": "This room is already booked by another user."})

        cur.execute("""
            UPDATE rooms
            SET status='vacant', booked_by=NULL, check_in=NULL, check_out=NULL
            WHERE booked_by=%s
        """, (user_id,))

        cur.execute("""
            UPDATE rooms
            SET room_type=%s, status='booked', booked_by=%s, check_in=%s, check_out=%s
            WHERE number=%s
        """, (new_room_type, user_id, new_check_in, new_check_out, new_room_number))

        db.commit()
        return jsonify({"status": "success", "message": "Booking updated successfully!"})

    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "message": str(e)})
    finally:
        cur.close(); db.close()

@app.route("/admin_dashboard")
def admin_dashboard():
    if "user_id" not in session or session.get("is_admin") != 1:
        flash("Access denied!", "danger")
        return redirect(url_for("login"))

    db = get_db()
    cur = db.cursor(MySQLdb.cursors.DictCursor)

    cur.execute("""
        SELECT r.id, r.number, r.status, u.name AS user_name, r.check_in, r.check_out, r.payment_status
        FROM rooms r LEFT JOIN users u ON r.booked_by=u.id
        ORDER BY r.number
    """)
    rooms = cur.fetchall()

    cur.execute("""
        SELECT id, name, email, IF(is_admin=1,'Admin',IF(is_admin=2,'Manager','User')) AS role
        FROM users
        ORDER BY id
    """)
    users = cur.fetchall()

    cur.close()
    db.close()

    return render_template("admin_dashboard.html", rooms=rooms, users=users)

@app.route("/admin_update_payment", methods=["POST"])
def admin_update_payment():
    if "user_id" not in session or session.get("is_admin") != 1:
        return jsonify({"status": "error", "message": "Access denied."})

    room_id = request.form.get("room_id")
    new_status = request.form.get("payment_status")  # 'Paid' or 'Pending'

    if not all([room_id, new_status]):
        return jsonify({"status": "error", "message": "All fields are required."})

    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("UPDATE rooms SET payment_status=%s WHERE id=%s", (new_status, room_id))
        db.commit()
        return jsonify({"status": "success", "message": f"Payment status updated to {new_status}!"})
    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "message": str(e)})
    finally:
        cur.close(); db.close()

@app.route("/manager_dashboard")
def manager_dashboard():
    if "user_id" not in session or session.get("is_admin") != 2:
        flash("Access denied!", "danger")
        return redirect(url_for("login"))

    db = get_db()
    cur = db.cursor(MySQLdb.cursors.DictCursor)

    cur.execute("""
        SELECT r.id AS room_id, r.number AS room_number, r.room_type, r.check_in, r.check_out,
               r.status, u.name AS user_name
        FROM rooms r
        LEFT JOIN users u ON r.booked_by = u.id
        ORDER BY r.number
    """)
    bookings = cur.fetchall()

    cur.execute("SELECT id, number, room_type, floor, status, check_in, check_out FROM rooms ORDER BY number")
    rooms = cur.fetchall()

    cur.execute("""
        SELECT id, name AS full_name, email, IF(is_admin=1,'Admin',IF(is_admin=2,'Manager','User')) AS role
        FROM users
        ORDER BY id
    """)
    users = cur.fetchall()

    cur.execute("""
        SELECT ma.id, ma.action_type, ma.booking_id, ma.user_id, ma.description, ma.action_time,
               u.name AS manager_name
        FROM manager_actions ma
        JOIN users u ON ma.manager_id = u.id
        ORDER BY ma.action_time DESC
    """)
    manager_actions = cur.fetchall()

    cur.close(); db.close()

    return render_template("manager_dashboard.html",
                           bookings=bookings,
                           rooms=rooms,
                           users=users,
                           manager_actions=manager_actions)

@app.route("/manager_edit_booking", methods=["POST"])
def manager_edit_booking():
    if "user_id" not in session:
        return jsonify({"status": "error", "message": "Login required."})

    booking_id = request.form.get("booking_id")
    new_check_in = request.form.get("new_check_in")
    new_check_out = request.form.get("new_check_out")

    if not all([booking_id, new_check_in, new_check_out]):
        return jsonify({"status":"error","message":"All fields are required."})

    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            UPDATE rooms
            SET check_in=%s, check_out=%s
            WHERE id=%s
        """, (new_check_in, new_check_out, booking_id))
        db.commit()

        log_manager_action(
            manager_id=session["user_id"],
            action_type="edit_booking",
            booking_id=booking_id,
            description=f"Changed check-in to {new_check_in}, check-out to {new_check_out}"
        )

        return jsonify({"status":"success","message":"Booking updated successfully!"})
    except Exception as e:
        db.rollback()
        return jsonify({"status":"error","message":str(e)})
    finally:
        cur.close(); db.close()

@app.route("/manager_cancel_booking", methods=["POST"])
def manager_cancel_booking():
    if "user_id" not in session:
        return jsonify({"status": "error", "message": "Login required."})

    booking_id = request.form.get("booking_id")
    if not booking_id:
        return jsonify({"status":"error","message":"Booking ID required."})

    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            UPDATE rooms
            SET booked_by=NULL, check_in=NULL, check_out=NULL, status='vacant', payment_status='Pending'
            WHERE id=%s
        """, (booking_id,))
        db.commit()

        log_manager_action(
            manager_id=session["user_id"],
            action_type="cancel_booking",
            booking_id=booking_id,
            description="Canceled booking"
        )

        return jsonify({"status":"success","message":"Booking canceled successfully!"})
    except Exception as e:
        db.rollback()
        return jsonify({"status":"error","message":str(e)})
    finally:
        cur.close(); db.close()

@app.route("/manager_edit_user", methods=["POST"])
def manager_edit_user():
    if "user_id" not in session or session.get("is_admin") != 2:
        return jsonify({"status":"error","message":"Access denied."})

    user_id = request.form.get("user_id")
    name = request.form.get("name")
    email = request.form.get("email")
    contact = request.form.get("contact")
    age = request.form.get("age")

    if not all([user_id, name, email]):
        return jsonify({"status":"error","message":"User ID, name, and email are required."})

    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            UPDATE users
            SET name=%s, email=%s, contact=%s, age=%s
            WHERE id=%s
        """, (name, email, contact, age, user_id))
        db.commit()

        log_manager_action(
            manager_id=session["user_id"],
            action_type="edit_user",
            user_id=user_id,
            description=f"Updated user {name} ({email})"
        )
        return jsonify({"status":"success","message":"User updated successfully!"})
    except Exception as e:
        db.rollback()
        return jsonify({"status":"error","message":str(e)})
    finally:
        cur.close(); db.close()

@app.route("/manager_approve_payment", methods=["POST"])
def manager_approve_payment():
    if "user_id" not in session or session.get("is_admin") != 2:
        return jsonify({"status":"error","message":"Access denied."})

    room_id = request.form.get("room_id")
    if not room_id:
        return jsonify({"status":"error","message":"Room ID required."})

    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("UPDATE rooms SET payment_status='Paid' WHERE id=%s", (room_id,))
        db.commit()

        log_manager_action(
            manager_id=session["user_id"],
            action_type="approve_payment",
            booking_id=room_id,
            description="Approved payment"
        )

        return jsonify({"status":"success","message":"Payment approved successfully!"})
    except Exception as e:
        db.rollback()
        return jsonify({"status":"error","message":str(e)})
    finally:
        cur.close(); db.close()

@app.route("/user_pay_booking", methods=["POST"])
def user_pay_booking():
    if "user_id" not in session:
        return jsonify({"status":"error","message":"Login required."})

    room_number = request.form.get("room_number")
    if not room_number:
        return jsonify({"status":"error","message":"Room number required."})

    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("SELECT id, booked_by FROM rooms WHERE number=%s", (room_number,))
        room = cur.fetchone()
        if not room or room[1] != session["user_id"]:
            return jsonify({"status":"error","message":"You cannot pay for this room."})

        cur.execute("UPDATE rooms SET payment_status='Paid' WHERE number=%s", (room_number,))
        db.commit()
        return jsonify({"status":"success","message":"Payment successful!"})
    except Exception as e:
        db.rollback()
        return jsonify({"status":"error","message":str(e)})
    finally:
        cur.close(); db.close()


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
