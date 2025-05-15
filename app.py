from flask import Flask, render_template, request, redirect, url_for, flash, session
import mysql.connector
import os
import secrets
from werkzeug.security import generate_password_hash, check_password_hash

# Create Flask app
app = Flask(__name__)

# Secret key setup
SECRET_KEY_FILE = 'secret_key.txt'

if os.path.exists(SECRET_KEY_FILE):
    with open(SECRET_KEY_FILE, 'r') as f:
        app.secret_key = f.read().strip()
else:
    generated_key = secrets.token_hex(32)
    with open(SECRET_KEY_FILE, 'w') as f:
        f.write(generated_key)
    app.secret_key = generated_key

# Optional: More secure cookie handling (especially for production)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = False  # Set True when deploying with HTTPS

# DB connection setup
from db_config import mydb

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        phone = request.form['phone']
        password = request.form['password']
        confirm = request.form['confirm']

        if password != confirm:
            print("Password mismatch")
            flash("Passwords do not match!")
            return redirect(url_for('signup'))

        try:
            hashed_pw = generate_password_hash(password)

            cursor = mydb.cursor()
            insert_query = """
                INSERT INTO users (name, email, password, phone_number, role, accommodation_status)
                VALUES (%s, %s, %s, %s, 'user', %s)
            """
            values = (username, email, hashed_pw, phone, False)
            cursor.execute(insert_query, values)
            mydb.commit()
            cursor.close()

            flash("Account created successfully! Please login.")
            return redirect(url_for('login'))

        except mysql.connector.Error as err:
            flash(f"Error: {err}")
            return redirect(url_for('signup'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        role = request.form['user_type']

        cursor = mydb.cursor(dictionary=True)

        try:
            user = None

            if role == 'admin':
                query = "SELECT * FROM users WHERE email=%s AND role='admin'"
                cursor.execute(query, (email,))
                user = cursor.fetchone()

            elif role == 'participant':
                query = "SELECT * FROM users WHERE email=%s AND role='user'"
                cursor.execute(query, (email,))
                user = cursor.fetchone()

            elif role == 'judge':
                query = "SELECT * FROM judges WHERE email=%s"
                cursor.execute(query, (email,))
                user = cursor.fetchone()
                if not user:
                    flash("Judge account not found.")
                    print("Judge not found")
                    return redirect(url_for('login'))

                if not user['password']== password:
                    flash("Incorrect password.")
                    return redirect(url_for('login'))

            else:
                flash("Invalid role selected!")
                return redirect(url_for('login'))

            if user:
                if role in ['admin', 'participant']:
                    if not check_password_hash(user['password'], password):
                        flash("Incorrect password.")
                        return redirect(url_for('login'))
                    if role == 'admin':
                        session['admin_id'] = user['user_id']
                    elif role == 'participant':
                        session['participant_id'] = user['user_id']

                elif role == 'judge':
                    session['judge_id'] = user['judge_id']  # assumes judge_id column exists

                session['email'] = user['email']
                session['role'] = role

                if role == 'admin':
                    return redirect(url_for('admin_dashboard'))
                elif role == 'participant':
                    return redirect(url_for('user_dashboard'))
                elif role == 'judge':
                    return redirect(url_for('judge_dashboard'))
            else:
                flash("Account not found.")
                return redirect(url_for('login'))
        except Exception as e:
            flash(f"Login error: {str(e)}")
            return redirect(url_for('login'))
        finally:
            cursor.close()

    return render_template('login.html')

@app.route('/admin/Dashboard')
def admin_dashboard():
    cursor = mydb.cursor(dictionary=True)

    # Total non-admin users
    cursor.execute("SELECT COUNT(*) AS total_users FROM users WHERE NOT role = 'admin'")
    total_users = cursor.fetchone()['total_users']

    # Total sponsors
    cursor.execute("SELECT COUNT(*) AS total_sponsors FROM sponsors")
    total_sponsors = cursor.fetchone()['total_sponsors']

    # Total events
    cursor.execute("SELECT COUNT(*) AS total_events FROM events")
    total_events = cursor.fetchone()['total_events']

    # Total payments
    cursor.execute("SELECT COALESCE(SUM(amount), 0) AS total_payments FROM payments")
    total_payments = cursor.fetchone()['total_payments']

    # Sponsor funds by category
    sponsor_funds = {}
    categories = ['Platinum', 'Gold', 'Silver', 'Bronze']
    for category in categories:
        cursor.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM sponsors WHERE sponsorship_category = %s",
            (category,)
        )
        sponsor_funds[category.lower()] = cursor.fetchone()['total']

    # Event Conflicts: overlapping events at the same venue
    cursor.execute("""
        SELECT e1.name AS event1, e2.name AS event2,
               v.name AS venue, e1.event_date, 
               e1.start_time AS start1, e1.end_time AS end1,
               e2.start_time AS start2, e2.end_time AS end2
        FROM events e1
        JOIN events e2 ON e1.venue_id = e2.venue_id
        JOIN venue v ON e1.venue_id = v.venue_id
        WHERE e1.event_id < e2.event_id
          AND e1.event_date = e2.event_date
          AND (
                (e1.start_time < e2.end_time AND e1.end_time > e2.start_time)
              )
    """)
    conflicts = cursor.fetchall()

    cursor.close()

    return render_template('admin/Dashboard.html',
                           total_users=total_users,
                           total_sponsors=total_sponsors,
                           total_events=total_events,
                           total_payments=total_payments,
                           platinum_funds=sponsor_funds['platinum'],
                           gold_funds=sponsor_funds['gold'],
                           silver_funds=sponsor_funds['silver'],
                           bronze_funds=sponsor_funds['bronze'],
                           conflicts=conflicts
                          )


@app.route('/user/dashboard')
def user_dashboard():
    return render_template('user/dashboard.html')

@app.route('/judge/dashboard')
def judge_dashboard():
    return render_template('judge/dashboard.html')


#####################################################################
#                                                                   #
#                             User routes                           #
#                                                                   #
#####################################################################

@app.route('/events')
def events():
    cursor = mydb.cursor(dictionary=True)
    query = '''
        SELECT 
            e.event_id, e.name AS event_name, e.rules, e.event_date, 
            e.start_time, e.end_time, e.max_participants, e.registration_fees,
            e.event_type,
            v.name AS venue_name,
            o.society, o.head, o.department
        FROM events e
        JOIN venue v ON e.venue_id = v.venue_id
        JOIN event_organizer o ON e.event_organizer_id = o.event_organizer_id
        WHERE e.event_type = 'computing'
        ORDER BY e.event_date ASC, e.start_time ASC;
    '''
    cursor.execute(query)
    events = cursor.fetchall()
    cursor.close()
    return render_template('user/events.html', events=events)



@app.route('/engineering_events')
def engineering_events():
    cursor = mydb.cursor(dictionary=True)
    query = '''
        SELECT 
            e.event_id, e.name AS event_name, e.rules, e.event_date, 
            e.start_time, e.end_time, e.max_participants, e.registration_fees,
            e.event_type,
            v.name AS venue_name,
            o.society, o.head, o.department
        FROM events e
        JOIN venue v ON e.venue_id = v.venue_id
        JOIN event_organizer o ON e.event_organizer_id = o.event_organizer_id
        WHERE e.event_type = 'engineering'
        ORDER BY e.event_date ASC, e.start_time ASC;
    '''
    cursor.execute(query)
    events = cursor.fetchall()
    cursor.close()
    return render_template("user/engineering_events.html", events=events)


@app.route('/social_events')
def social_events():
    cursor = mydb.cursor(dictionary=True)
    query = '''
        SELECT 
            e.event_id, e.name AS event_name, e.rules, e.event_date, 
            e.start_time, e.end_time, e.max_participants, e.registration_fees,
            e.event_type,
            v.name AS venue_name,
            o.society, o.head, o.department
        FROM events e
        JOIN venue v ON e.venue_id = v.venue_id
        JOIN event_organizer o ON e.event_organizer_id = o.event_organizer_id
        WHERE e.event_type = 'social'
        ORDER BY e.event_date ASC, e.start_time ASC;
    '''
    cursor.execute(query)
    events = cursor.fetchall()
    cursor.close()
    return render_template("user/social_events.html", events=events)


@app.route('/sports_events')
def sports_events():
    cursor = mydb.cursor(dictionary=True)
    query = '''
        SELECT 
            e.event_id, e.name AS event_name, e.rules, e.event_date, 
            e.start_time, e.end_time, e.max_participants, e.registration_fees,
            e.event_type,
            v.name AS venue_name,
            o.society, o.head, o.department
        FROM events e
        JOIN venue v ON e.venue_id = v.venue_id
        JOIN event_organizer o ON e.event_organizer_id = o.event_organizer_id
        WHERE e.event_type = 'sports'
        ORDER BY e.event_date ASC, e.start_time ASC;
    '''
    cursor.execute(query)
    events = cursor.fetchall()
    cursor.close()
    return render_template("user/sports_events.html", events=events)

@app.route('/register_event/<int:event_id>', methods=['GET', 'POST'])
def register_event(event_id):
    if session.get('role') == 'participant':
        user_id = session.get('participant_id')
    elif session.get('role') == 'admin':
        user_id = session.get('admin_id')
    elif session.get('role') == 'judge':
        user_id = session.get('judge_id')
    else:
        flash("Unauthorized access.")
        return redirect(url_for('login'))

    # Fetch event details
    cursor = mydb.cursor(dictionary=True)
    cursor.execute("SELECT e.event_id ,e.name , v.name as location , e.event_date, e.registration_fees FROM events e,venue v WHERE e.venue_id = v.venue_id AND event_id = %s", (event_id,))
    event = cursor.fetchone()

    if request.method == 'POST':
        action = request.form['action']

        if action == 'register':
            try:
                cursor.execute("""
                    INSERT INTO user_events (user_id, event_id)
                    VALUES (%s, %s)
                """, (user_id, event_id))

                room_no = request.form.get('room_no')
                total_payment = event['registration_fees']

                if room_no and room_no != "none":
                    # Get room rent from accommodation table
                    cursor.execute("SELECT rent FROM accommodation WHERE room_no = %s", (room_no,))
                    rent_row = cursor.fetchone()
                    if rent_row:
                        total_payment += rent_row['rent']

                    # Insert into accommodation_user
                    cursor.execute("""
                        INSERT INTO accommodation_user (room_no, user_id)
                        VALUES (%s, %s)
                    """, (room_no, user_id))

                # Insert payment with total amount
                cursor.execute("""
                    INSERT INTO payments (amount, user_id)
                    VALUES (%s, %s)
                """, (total_payment, user_id))

                mydb.commit()
                flash('Registration successful! Please confirm payment.', 'success')

            except mydb.IntegrityError:
                flash('You have already registered for this event.', 'warning')

        elif action == 'pay':
            # Update fee_submitted = TRUE (trigger will set payment_status = paid)
            cursor.execute("""
                UPDATE user_events
                SET fee_submitted = TRUE
                WHERE user_id = %s AND event_id = %s
            """, (user_id, event_id))
            mydb.commit()
            flash('Payment confirmed! Registration complete.', 'success')

        return redirect(url_for('register_event', event_id=event_id))
    
    cursor.execute('Select * from accommodation')
    accomodation = cursor.fetchall()
    cursor.close()

    return render_template('user/register_event.html', event=event , accomodation_packages = accomodation)

def get_sponsors_by_category(category):
    cursor = mydb.cursor(dictionary=True)
    query = "SELECT company_name FROM sponsors WHERE sponsorship_category = %s LIMIT 5"
    cursor.execute(query, (category,))
    sponsors = cursor.fetchall()
    cursor.close()
    return sponsors

@app.route('/user/sponsors')
def sponsors():
    categories = ['Platinum', 'Gold', 'Silver', 'Bronze']
    sponsor_data = {}

    for cat in categories:
        sponsor_data[cat.lower()] = get_sponsors_by_category(cat.capitalize())
    
    print(sponsor_data)
    return render_template('user/sponsors.html', sponsor_data=sponsor_data)

@app.route('/user/aboutus')
def aboutus():
    return render_template('user/aboutus.html')

@app.route('/user/become_sponsor', methods=['GET', 'POST'])
def become_sponsor():
    if request.method == 'POST':
        company_name = request.form['company_name']
        email = request.form['email']
        amount = request.form['amount']
        representative_name = request.form['sponsor_representative_name']

        try:
            cursor = mydb.cursor()
            insert_query = """
                INSERT INTO sponsorship_requests 
                (company_name, sponsorship_category, email, amount, sponsor_representative_name)
                VALUES (%s, Null, %s, %s, %s)
            """
            values = (company_name, email, amount, representative_name)
            cursor.execute(insert_query, values)
            mydb.commit()
            cursor.close()
            flash("Sponsorship request submitted successfully!", "success")
            return redirect(url_for('sponsors'))

        except mysql.connector.Error as err:
            print(err)
            flash(f"Database Error: {err}", "danger")
            return redirect(url_for('become_sponsor'))

    return render_template('user/become_sponsor.html')



#####################################################################
#                                                                   #
#                            Admin routes                           #
#                                                                   #
#####################################################################

@app.route('/admin/Accomodation' , methods=['GET', 'POST'])
def accomodation():
    cursor = mydb.cursor(dictionary=True)
    if request.method == "POST":
        rent = float(request.form['rent'])
        capacity = int(request.form['capacity'])

        try:
            query = "INSERT INTO accommodation (rent, capacity) values (%s, %s)"
            values = (rent, capacity)
            cursor.execute(query, values)
            mydb.commit()
            flash("Accomodation added successfully!")
            return redirect(url_for('accomodation'))
        except Exception as e:
            print(e)
            flash("An error occurred while adding the accomodation.")
            return redirect(url_for('accomodation'))
        
    cursor.execute("SELECT * FROM accommodation")
    accomodations = cursor.fetchall()
    cursor.close()
    return render_template('admin/Accomodation.html' , accomodations = accomodations)

@app.route('/admin/Accomodation/Delete/<int:id>', methods=['POST'])
def delete_accomodation(id):
    cursor = mydb.cursor()
    try:
        query = "DELETE FROM accommodation WHERE room_no = %s"
        cursor.execute(query, (id,))
        mydb.commit()
        flash("Accomodation deleted successfully!")
        return redirect(url_for('accomodation'))
    except Exception as e:
        print(e)
        flash("An error occurred while deleting the accomodation.")
        return redirect(url_for('accomodation'))


@app.route('/admin/Evaluations')
def evaluations():
    cursor = mydb.cursor(dictionary=True)

    # Get all events with their types (even if no evaluation exists)
    cursor.execute("""
        SELECT 
            e.event_id,
            e.name AS event_name,
            e.event_type
        FROM events e
        ORDER BY e.event_type, e.name
    """)
    all_events = cursor.fetchall()

    # Get aggregated evaluation data
    cursor.execute("""
        SELECT 
            e.event_id,
            COUNT(DISTINCT ue.user_id) AS total_participants,
            ROUND(AVG(ev.score), 2) AS average_score,
            MAX(ev.score) AS max_score
        FROM events e
        JOIN evaluation ev ON e.event_id = ev.event_id
        JOIN user_evaluation ue ON ue.evaluation_id = ev.evaluation_id
        GROUP BY e.event_id
    """)
    eval_summary = {row['event_id']: row for row in cursor.fetchall()}

    # Get winners
    cursor.execute("""
        SELECT 
            e.event_id,
            u.name AS winner_name,
            ev.score AS winner_score
        FROM evaluation ev
        JOIN events e ON e.event_id = ev.event_id
        JOIN user_evaluation ue ON ue.evaluation_id = ev.evaluation_id
        JOIN users u ON u.user_id = ue.user_id
        WHERE (e.event_id, ev.score) IN (
            SELECT e.event_id, MAX(ev.score)
            FROM evaluation ev
            JOIN events e ON e.event_id = ev.event_id
            GROUP BY e.event_id
        )
    """)
    winner_map = {row['event_id']: row for row in cursor.fetchall()}
    cursor.close()

    # Merge everything
    grouped_data = {}
    for event in all_events:
        eid = event['event_id']
        etype = event['event_type']

        data = {
            'event_name': event['event_name'],
            'total_participants': eval_summary.get(eid, {}).get('total_participants', '-'),
            'average_score': eval_summary.get(eid, {}).get('average_score', '-'),
            'winner_name': winner_map.get(eid, {}).get('winner_name', '-'),
            'winner_score': winner_map.get(eid, {}).get('winner_score', '-')
        }

        grouped_data.setdefault(etype, []).append(data)

    return render_template('admin/Evaluations.html', grouped_data=grouped_data)


@app.route('/admin/Events', methods=['GET', 'POST'])
def events_admin():
    cursor = mydb.cursor(dictionary=True)

    if request.method == 'POST':
        name = request.form['name']
        rules = request.form['rules']
        max_participants = int(request.form['max_participants'])
        registration_fees = float(request.form['registration_fees'])
        event_date = request.form['event_date']
        start_time = request.form['start_time']
        end_time = request.form['end_time']
        event_type = request.form['event_type'].strip().lower()
        venue_id = int(request.form['venue_id'])
        event_organizer_id = int(request.form['event_organizer_id'])
        judge_id = int(request.form['judge_id'])

        try:
            insert_query = """
                INSERT INTO events
                (name, rules, max_participants, registration_fees, event_date, start_time, end_time, event_type, venue_id, event_organizer_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            values = (
                name, rules, max_participants, registration_fees,
                event_date, start_time, end_time, event_type,
                venue_id, event_organizer_id
            )
            cursor.execute(insert_query, values)
            event_id = cursor.lastrowid

            mydb.commit()
            cursor.execute("INSERT IGNORE INTO can_evaluate (judge_id , event_id) values (%s , %s)" ,(judge_id ,event_id))
            
            flash("Event added successfully!", "success")
            return redirect(url_for('events_admin'))
        except mysql.connector.Error as err:
            print("Error:", err._full_msg)
            flash(f"Database error: {err}", "error")
            mydb.rollback()


    # Fetch all events
    cursor.execute("""
        SELECT 
            e.*, 
            o.society AS organizer_society, 
            v.name AS venue_name,
            j.name AS judge_name
        FROM events e
        JOIN event_organizer o ON e.event_organizer_id = o.event_organizer_id
        JOIN venue v ON e.venue_id = v.venue_id
        LEFT JOIN can_evaluate ce ON e.event_id = ce.event_id
        LEFT JOIN judges j ON ce.judge_id = j.judge_id
    """)
    events = cursor.fetchall()

    # Fetch organizers and venues for form dropdown
    cursor.execute("SELECT event_organizer_id, society FROM event_organizer")
    organizers = cursor.fetchall()

    cursor.execute("SELECT venue_id, name FROM venue")
    venues = cursor.fetchall()

    cursor.execute("SELECT judge_id,name FROM judges")
    judges = cursor.fetchall()

    cursor.close()
    return render_template('admin/Events.html', events=events, organizers=organizers, venues=venues,judges = judges)

@app.route('/admin/Events/delete/<int:event_id>', methods=['POST'])
def delete_event(event_id):
    try:
        cursor = mydb.cursor()
        cursor.execute("DELETE FROM events WHERE event_id = %s", (event_id,))
        mydb.commit()
        flash("Event deleted successfully.", "success")
    except Exception as e:
        flash(f"Failed to delete event: {e}", "danger")
    return redirect(url_for('events_admin'))

@app.route('/admin/Judges', methods=['GET', 'POST'])
def judges():
    cursor = mydb.cursor(dictionary=True)

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        try:
            query = "INSERT INTO judges (name, email, password) VALUES (%s, %s, %s)"
            cursor.execute(query, (name, email, password))
            mydb.commit()
            flash("Judge added successfully!", "success")
        except mysql.connector.Error as err:
            flash(f"Error: {err}", "error")
        finally:
            cursor.close()
            return redirect(url_for('judges'))

    # Fetch judges for GET
    cursor.execute("SELECT * FROM judges")
    judges_list = cursor.fetchall()
    cursor.close()
    return render_template('admin/Judges.html', judges=judges_list)

@app.route('/admin/Organizers', methods=['GET', 'POST'])
def organizers():
    cursor = mydb.cursor(dictionary=True)

    if request.method == 'POST':
        society = request.form['society']
        head = request.form['head']
        department = request.form['department']

        try:
            query = "INSERT INTO event_organizer (society,head,department) VALUES (%s, %s, %s)"
            cursor.execute(query, (society, head, department))
            mydb.commit()
            flash("Organizer added successfully!", "success")
        except mysql.connector.Error as err:
            flash(f"Database insertion error: {err}", "danger")
        return redirect(url_for('organizers'))

    # Fetch all organizers for display
    cursor.execute("SELECT * FROM event_organizer")
    organizers = cursor.fetchall()
    cursor.close()

    return render_template('admin/Organizers.html', organizers=organizers)

@app.route('/admin/organizers/delete/<int:organizer_id>', methods=['POST'])
def delete_organizer(organizer_id):
    cursor = mydb.cursor()
    cursor.execute("DELETE FROM event_organizer WHERE event_organizer_id = %s", (organizer_id,))
    mydb.commit()
    cursor.close()
    return redirect(url_for('organizers'))


@app.route('/admin/payments')
def payments():
    cursor = mydb.cursor(dictionary=True)
    cursor.execute("SELECT u.name, p.payment_status,p.amount FROM payments p JOIN users u ON p.user_id = u.user_id")
    payments_list = cursor.fetchall()

    total_amount = sum([p['amount'] for p in payments_list])

    cursor.close()
    return render_template('admin/payments.html', payments=payments_list, total_amount=total_amount)


@app.route('/admin/Sponsors', methods=['GET', 'POST'])
def sponsors_admin():
    cursor = mydb.cursor(dictionary=True)

    if request.method == "POST":
        request_id = request.form['request_id']
        action = request.form['action']

        status = 'accepted' if action == 'accept' else 'rejected'

        try:
            update_query = "UPDATE sponsorship_requests SET status = %s WHERE request_id = %s"
            cursor.execute(update_query, (status, request_id))
            mydb.commit()
            flash(f"Sponsorship request {status}.", "success")
        except mysql.connector.Error as err:
            flash(f"Error updating request: {err}", "danger")

    # Fetch all sponsorship requests
    cursor.execute("SELECT * FROM sponsorship_requests ORDER BY request_id DESC")
    requests = cursor.fetchall()
    cursor.close()
    return render_template('admin/Sponsors.html', requests=requests)


from mysql.connector import IntegrityError
@app.route('/accept_request/<int:request_id>', methods=['POST'])
def accept_request(request_id):
    cursor = mydb.cursor(dictionary=True)

    # Retrieve the sponsorship request
    cursor.execute("SELECT * FROM sponsorship_requests WHERE request_id = %s", (request_id,))
    request_data = cursor.fetchone()

    if not request_data:
        cursor.close()
        flash("Sponsorship request not found.", "error")
        return redirect(url_for('sponsors_admin'))

    email = request_data['email'].strip().lower()

    try:
        # Check if a sponsor with the same email already exists
        cursor.execute("SELECT sponsor_id FROM sponsors WHERE email = %s", (email,))
        existing_sponsor = cursor.fetchone()

        if not existing_sponsor:
            # Insert new sponsor
            insert_query = """
                INSERT INTO sponsors (company_name, sponsorship_category, email, amount, sponsor_representative_name)
                VALUES (%s, %s, %s, %s, %s)
            """
            values = (
                request_data['company_name'],
                request_data['sponsorship_category'],
                email,
                request_data['amount'],
                request_data['sponsor_representative_name']
            )
            cursor.execute(insert_query, values)

        # Update the request status to 'accepted'
        cursor.execute("UPDATE sponsorship_requests SET status = 'accepted' WHERE request_id = %s", (request_id,))
        mydb.commit()
        flash("Sponsorship request accepted successfully.", "success")

    except IntegrityError as e:
        mydb.rollback()
        flash(f"Database error: {e}", "error")
    finally:
        cursor.close()

    return redirect(url_for('sponsors_admin'))


@app.route('/reject_request/<int:request_id>', methods=['POST'])
def reject_request(request_id):
    cursor = mydb.cursor(dictionary=True)
    try:
        # Check if the request exists
        cursor.execute("SELECT * FROM sponsorship_requests WHERE request_id = %s", (request_id,))
        request_data = cursor.fetchone()

        if not request_data:
            flash("Sponsorship request not found.", "error")
            return redirect(url_for('view_requests'))

        # Option 1: Just update status to 'rejected'
        cursor.execute("""
            UPDATE sponsorship_requests SET status = 'rejected' WHERE request_id = %s
        """, (request_id,))

        # Option 2 (optional): Delete the request entirely
        # cursor.execute("DELETE FROM sponsorship_requests WHERE request_id = %s", (request_id,))

        mydb.commit()
        flash("Sponsorship request rejected.", "success")

    except Exception as e:
        mydb.rollback()
        flash(f"Error rejecting request: {e}", "error")

    finally:
        cursor.close()

    return redirect(url_for('sponsors_admin'))

@app.route('/admin/Users')
def Users():
    cursor = mydb.cursor(dictionary=True)
    cursor.execute("SELECT user_name, email, phone, accommodation_package, event_name FROM participant_accommodation_view")
    participants = cursor.fetchall()
    cursor.close()
    return render_template('admin/Users.html', participants=participants)


@app.route('/admin/Venues', methods=['GET', 'POST'])
def venues():
    cursor = mydb.cursor(dictionary=True)

    if request.method == 'POST':
        name = request.form['name']
        capacity = request.form['capacity']

        try:
            insert_query = "INSERT INTO venue (name, capacity) VALUES (%s, %s)"
            cursor.execute(insert_query, (name, capacity))
            mydb.commit()
            flash("Venue added successfully!", "success")
        except mysql.connector.Error as err:
            flash(f"Database error: {err}", "error")
        return redirect(url_for('venues'))

    # Fetch venues for display
    cursor.execute("SELECT * FROM venue")
    venues_data = cursor.fetchall()
    cursor.close()
    return render_template('admin/Venues.html', venues=venues_data)



#####################################################################
#                                                                   #
#                            Judge routes                           #
#                                                                   #
#####################################################################

@app.route('/judge/events')
def judge_events():
    # Fetch judge's events based on session user id
    judge_id = session['judge_id']  # Ensure session has user_id
    print("Judge ID:", judge_id)
    cursor = mydb.cursor(dictionary=True)
    cursor.execute("""
        SELECT e.event_id, e.name, e.event_type, v.name AS venue, e.event_date, e.start_time
        FROM events e
        JOIN venue v ON e.venue_id = v.venue_id
        JOIN can_evaluate je ON je.event_id = e.event_id
        WHERE je.judge_id = %s
    """, (judge_id,))
    events = cursor.fetchall()
    mydb.commit()
    print(events)
    return render_template('judge/events.html', events=events)

@app.route('/judge/evaluate/<int:event_id>', methods=['GET', 'POST'])
def judge_evaluate(event_id):
    judge_id = session.get('judge_id')
    cursor = mydb.cursor(dictionary=True)

    if request.method == 'POST':
        user_id = int(request.form['user_id'])
        score = int(request.form['score'])
        comment = request.form['comment']

        # Check if the current judge has already evaluated this user in this event
        cursor.execute("""
            SELECT e.evaluation_id
            FROM evaluation e
            JOIN user_evaluation ue ON e.evaluation_id = ue.evaluation_id
            JOIN make m ON m.evaluation_id = e.evaluation_id
            WHERE ue.user_id = %s AND e.event_id = %s AND m.judge_id = %s
        """, (user_id, event_id, judge_id))
        existing = cursor.fetchone()

        if existing:
            flash(f"Already evaluated User ID {user_id} for this event.", "warning")
        else:
            # Insert evaluation
            cursor.execute("""
                INSERT INTO evaluation (score, comments, event_id)
                VALUES (%s, %s, %s)
            """, (score, comment, event_id))
            evaluation_id = cursor.lastrowid

            # Map user to evaluation
            cursor.execute("""
                INSERT INTO user_evaluation (user_id, evaluation_id)
                VALUES (%s, %s)
            """, (user_id, evaluation_id))

            # Map judge to evaluation
            cursor.execute("""
                INSERT INTO make (judge_id, evaluation_id)
                VALUES (%s, %s)
            """, (judge_id, evaluation_id))

            mydb.commit()
            flash(f"Evaluation saved for User ID {user_id}.", "success")

        cursor.close()
        return redirect(url_for('judge_evaluate', event_id=event_id))

    else:
        # Get all participants for the event along with their evaluation status
        cursor.execute("""
            SELECT u.user_id, u.name,
            EXISTS (
                SELECT 1
                FROM evaluation e
                JOIN user_evaluation ue ON ue.evaluation_id = e.evaluation_id
                JOIN make m ON m.evaluation_id = e.evaluation_id
                WHERE ue.user_id = u.user_id AND e.event_id = %s AND m.judge_id = %s
            ) AS already_evaluated
            FROM users u
            JOIN user_events ue ON u.user_id = ue.user_id
            WHERE ue.event_id = %s
        """, (event_id, judge_id, event_id))
        
        participants = cursor.fetchall()

    # Fetch event name
        cursor.execute("SELECT name FROM events WHERE event_id = %s", (event_id,))
        event_name = cursor.fetchone()['name']
        cursor.close()
        return render_template('judge/evaluate.html', participants=participants, event_id=event_id, event_name = event_name)

@app.route('/judge/results')
def judge_results():
    judge_id = session.get('judge_id')  # assuming judge is logged in

    cursor = mydb.cursor(dictionary=True)

    # Fetch all events this judge can evaluate
    cursor.execute("""
        SELECT e.event_id, e.name AS event_name
        FROM can_evaluate ce
        JOIN events e ON e.event_id = ce.event_id
        WHERE ce.judge_id = %s
    """, (judge_id,))
    judge_events = cursor.fetchall()

    event_results = []

    for event in judge_events:
        event_id = event['event_id']
        event_name = event['event_name']

        # Total participants assigned for evaluation in this event (from participant_event or other logic)
        cursor.execute("""
            SELECT COUNT(DISTINCT ue.user_id) AS total_participants
            FROM user_events ue
            WHERE ue.event_id = %s
        """, (event_id,))
        total_result_row = cursor.fetchone()
        total_participants = total_result_row['total_participants'] or 0

        # Evaluations done by this judge for this event
        cursor.execute("""
            SELECT COUNT(*) AS evaluations_done,
                ROUND(AVG(e.score), 2) AS avg_score,
                MAX(e.score) AS max_score
            FROM evaluation e
            JOIN make m ON e.evaluation_id = m.evaluation_id
            WHERE m.judge_id = %s AND e.event_id = %s
        """, (judge_id, event_id))
        eval_stats = cursor.fetchone()

        evaluations_done = eval_stats['evaluations_done'] or 0
        avg_score = eval_stats['avg_score'] if eval_stats['avg_score'] is not None else "-"
        max_score = eval_stats['max_score'] if eval_stats['max_score'] is not None else "-"

        event_results.append({
            'event_name': event_name,
            'total_participants': total_participants,
            'evaluations_done': evaluations_done,
            'average_score': avg_score,
            'max_score': max_score,
            'completion': f"{evaluations_done} / {total_participants}"
        })

    cursor.close()
    return render_template('judge/results.html', event_results=event_results)



if __name__ == '__main__':
    app.run(debug=True)


