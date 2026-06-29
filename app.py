from flask import Flask, render_template, request, redirect, url_for, session, flash
import pymysql
import pymysql.cursors
from flask_bcrypt import Bcrypt
from config import Config
from functools import wraps
from contextlib import contextmanager
import datetime
import random
import string
import os
import time
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config.from_object(Config)
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

LAST_INVOICE_CHECK = 0

@app.before_request
def auto_generate_rental_invoices():
    global LAST_INVOICE_CHECK
    now = time.time()
    # Run at most once per hour (3600 seconds)
    if now - LAST_INVOICE_CHECK > 3600:
        try:
            with get_db() as conn:
                cur = conn.cursor()
                today = datetime.date.today()
                current_month_str = today.strftime('%Y-%m')
                
                # Retrieve all active rentals where current date is between start_date and end_date (or end_date is NULL)
                cur.execute("""
                    SELECT rental_id, customer_id, monthly_rental_fee
                    FROM RentalAgreement
                    WHERE start_date <= %s 
                      AND (end_date IS NULL OR end_date >= %s)
                      AND monthly_rental_fee IS NOT NULL
                """, (today, today))
                active_rentals = cur.fetchall()
                
                for r in active_rentals:
                    ref_id = f"Rental {r['rental_id']} {current_month_str}"
                    # Ensure no duplicate invoice for the current month is created
                    cur.execute("SELECT payment_id FROM Payment WHERE reference_id = %s", (ref_id,))
                    if not cur.fetchone():
                        cur.execute("""
                            INSERT INTO Payment (customer_id, amount_paid, payment_date, payment_method, payment_type, payment_status, reference_id)
                            VALUES (%s, %s, NOW(), 'Cash', 'Rental', 'Pending', %s)
                        """, (r['customer_id'], r['monthly_rental_fee'], ref_id))
                conn.commit()
                cur.close()
        except:
            pass
        finally:
            LAST_INVOICE_CHECK = now

# --- CONNECTION POOL ---
_pool = None

def _get_pool():
    global _pool
    if _pool is None:
        try:
            from dbutils.pooled_db import PooledDB
        except ImportError:
            import importlib
            PooledDB = importlib.import_module('DBUtils.PooledDB').PooledDB

        connect_kwargs = {
            'host': app.config['MYSQL_HOST'],
            'user': app.config['MYSQL_USER'],
            'password': app.config['MYSQL_PASSWORD'],
            'database': app.config['MYSQL_DB'],
            'port': app.config.get('MYSQL_PORT', 3306),
            'cursorclass': pymysql.cursors.DictCursor,
            'autocommit': False,
        }

        # Enable SSL for cloud-hosted MySQL (non-localhost)
        if app.config['MYSQL_HOST'] != 'localhost' and app.config['MYSQL_HOST'] != '127.0.0.1':
            connect_kwargs['ssl'] = {'ssl': True}

        _pool = PooledDB(
            creator=pymysql,
            maxconnections=5,
            mincached=1,
            maxcached=3,
            blocking=True,
            **connect_kwargs
        )
    return _pool

@contextmanager
def get_db():
    """Context manager — always returns a connection and closes it on exit."""
    conn = _get_pool().connection()
    try:
        yield conn
    finally:
        conn.close()

bcrypt = Bcrypt(app)

# --- LOGIN DECORATORS ---
def customer_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'customer_id' not in session:
            return redirect(url_for('customer_login'))
        return f(*args, **kwargs)
    return decorated_function

def employee_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'employee_id' not in session:
            return redirect(url_for('employee_login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'employee_role' not in session or session['employee_role'] != 'Admin':
            flash('Admin access required', 'danger')
            return redirect(url_for('employee_login'))
        return f(*args, **kwargs)
    return decorated_function

def generate_invoice_number():
    return 'INV-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

# --- PUBLIC ROUTES ---
@app.route('/')
def index():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM SolarPanel LIMIT 3")
        panels = cur.fetchall()
        cur.close()
    return render_template('index.html', panels=panels)

@app.route('/panels')
def panels():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM SolarPanel WHERE status != 'Retired'")
        panels = cur.fetchall()
        cur.close()
    return render_template('panels.html', panels=panels)

# --- CUSTOMER AUTH ---
@app.route('/customer/register', methods=['GET', 'POST'])
def customer_register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        address = request.form['address']
        password = request.form['password']
        pw_hash = bcrypt.generate_password_hash(password).decode('utf-8')

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO Customer (name, email, phone, address, password_hash, service_start_date)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (name, email, phone, address, pw_hash, datetime.date.today()))
            conn.commit()
            cur.close()

        flash('Registration successful. Please log in.', 'success')
        return redirect(url_for('customer_login'))

    return render_template('customer_register.html')

@app.route('/customer/login', methods=['GET', 'POST'])
def customer_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM Customer WHERE email = %s", (email,))
            customer = cur.fetchone()
            cur.close()

        if customer and bcrypt.check_password_hash(customer['password_hash'], password):
            session['customer_id'] = customer['customer_id']
            session['customer_name'] = customer['name']
            return redirect(url_for('customer_dashboard'))
        else:
            flash('Invalid email or password', 'danger')

    return render_template('customer_login.html')

@app.route('/customer/logout')
def customer_logout():
    session.clear()
    return redirect(url_for('customer_login'))

# --- EMPLOYEE AUTH ---
@app.route('/employee/login', methods=['GET', 'POST'])
def employee_login():
    if request.method == 'POST':
        email = request.form['email'].strip()
        password = request.form['password']

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM Employee WHERE email = %s", (email,))
            employee = cur.fetchone()
            cur.close()

        if employee is None:
            flash('Invalid email or password', 'danger')
            return render_template('employee_login.html')

        if bcrypt.check_password_hash(employee['password_hash'], password):
            session['employee_id'] = employee['employee_id']
            session['employee_name'] = employee['name']
            session['employee_role'] = employee['role']
            return redirect(url_for('employee_dashboard'))
        else:
            flash('Invalid email or password', 'danger')

    return render_template('employee_login.html')

@app.route('/employee/logout')
def employee_logout():
    session.clear()
    return redirect(url_for('employee_login'))

# --- CUSTOMER DASHBOARD ---
@app.route('/customer/dashboard')
@customer_login_required
def customer_dashboard():
    cid = session['customer_id']
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT ra.*, sp.model_name, sp.capacity_kw FROM RentalAgreement ra JOIN SolarPanel sp ON ra.panel_id=sp.panel_id WHERE ra.customer_id=%s", (cid,))
        rentals = cur.fetchall()
        cur.execute("SELECT st.*, sp.model_name FROM SalesTransaction st JOIN SolarPanel sp ON st.panel_id=sp.panel_id WHERE st.customer_id=%s", (cid,))
        sales = cur.fetchall()
        cur.execute("SELECT ms.*, sp.model_name FROM MaintenanceService ms JOIN SolarPanel sp ON ms.panel_id=sp.panel_id WHERE ms.customer_id=%s", (cid,))
        maintenance = cur.fetchall()
        cur.execute("SELECT * FROM Payment WHERE customer_id=%s ORDER BY payment_date DESC", (cid,))
        payments = cur.fetchall()
        cur.close()
    return render_template('customer_dashboard.html', rentals=rentals, sales=sales, maintenance=maintenance, payments=payments)

@app.route('/customer/rent/<int:panel_id>', methods=['GET', 'POST'])
@customer_login_required
def customer_rent_panel(panel_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM SolarPanel WHERE panel_id=%s", (panel_id,))
        panel = cur.fetchone()

        if not panel:
            cur.close()
            flash('Panel not found.', 'danger')
            return redirect(url_for('panels'))

        if request.method == 'POST':
            customer_id = session['customer_id']
            cur.execute("""
                INSERT INTO RentalAgreement
                    (customer_id, panel_id, start_date, end_date,
                     monthly_rental_fee, payment_status)
                VALUES (%s, %s, NULL, NULL, NULL, 'Pending')
            """, (customer_id, panel_id))
            conn.commit()
            cur.close()
            flash('Rental request sent. Admin will set your plan and schedule installation.', 'success')
            return redirect(url_for('customer_dashboard'))

        cur.close()
    return render_template('customer_rent_form.html', panel=panel)

@app.route('/customer/buy/<int:panel_id>', methods=['GET', 'POST'])
@customer_login_required
def customer_buy_panel(panel_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM SolarPanel WHERE panel_id = %s", (panel_id,))
        panel = cur.fetchone()

        if not panel:
            cur.close()
            flash('Panel not found.', 'danger')
            return redirect(url_for('panels'))

        if request.method == 'POST':
            customer_id = session['customer_id']
            sale_date = datetime.date.today()
            total_price = panel['price']

            invoice_num = generate_invoice_number()
            cur.execute("""
                INSERT INTO SalesTransaction
                    (customer_id, panel_id, sale_date, total_price, payment_status, invoice_number)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (customer_id, panel_id, sale_date, total_price, 'Pending', invoice_num))
            sale_id = cur.lastrowid

            cur.execute("""
                INSERT INTO MaintenanceService
                    (panel_id, customer_id, service_date, service_type,
                     technician_id, cost_of_service, maintenance_status)
                VALUES (%s, %s, %s, %s, %s, %s, 'Scheduled')
            """, (panel_id, customer_id, sale_date, 'Installation', None, 0.00))

            conn.commit()
            cur.close()
            flash('Purchase request sent. Admin will assign installation and generate invoice.', 'success')
            return redirect(url_for('customer_dashboard'))

        cur.close()
    return render_template('customer_buy_form.html', panel=panel)

@app.route('/customer/pay/<int:payment_id>', methods=['GET', 'POST'])
@customer_login_required
def customer_pay(payment_id):
    cid = session['customer_id']

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM Payment
            WHERE payment_id = %s AND customer_id = %s
        """, (payment_id, cid))
        payment = cur.fetchone()

        if not payment:
            cur.close()
            flash('Payment not found.', 'danger')
            return redirect(url_for('customer_dashboard'))

        if payment['payment_status'] != 'Pending':
            cur.close()
            flash('This payment is not pending.', 'warning')
            return redirect(url_for('customer_dashboard'))

        if request.method == 'POST':
            payment_method = request.form['payment_method']

            cur.execute("""
                UPDATE Payment
                SET payment_status = 'Completed', payment_method = %s
                WHERE payment_id = %s
            """, (payment_method, payment_id))

            if payment['payment_type'] == 'Rental' and payment['reference_id']:
                parts = payment['reference_id'].split()
                if len(parts) >= 2:
                    try:
                        rental_id = int(parts[1])
                        cur.execute("""
                            UPDATE RentalAgreement
                            SET payment_status = 'Paid'
                            WHERE rental_id = %s
                        """, (rental_id,))
                    except ValueError:
                        pass

            if payment['payment_type'] == 'Maintenance' and payment['reference_id']:
                if payment['reference_id'].startswith('MS-'):
                    try:
                        maint_id = int(payment['reference_id'].split('-')[1])
                        cur.execute("""
                            UPDATE MaintenanceService
                            SET billing_status = 'Paid'
                            WHERE maintenance_id = %s
                        """, (maint_id,))
                    except ValueError:
                        pass

            conn.commit()
            cur.close()
            return render_template('payment_success.html')

        cur.close()
    return render_template('customer_pay.html', payment=payment)


# --- EMPLOYEE (ADMIN & TECHNICIAN) DASHBOARD ---
@app.route('/employee/dashboard')
@employee_login_required
def employee_dashboard():
    eid = session['employee_id']
    role = session['employee_role']

    with get_db() as conn:
        cur = conn.cursor()

        if role == 'Admin':
            cur.execute("SELECT SUM(amount_paid) as total FROM Payment WHERE payment_status='Completed'")
            res_rev = cur.fetchone()
            revenue = res_rev['total'] if res_rev and res_rev['total'] else 0

            cur.execute("SELECT COUNT(*) as count FROM SalesTransaction WHERE payment_status='Requested'")
            res_sales = cur.fetchone()
            pending_sales = res_sales['count'] if res_sales else 0

            cur.execute("SELECT COUNT(*) as count FROM MaintenanceService WHERE maintenance_status='Scheduled'")
            res_jobs = cur.fetchone()
            open_jobs = res_jobs['count'] if res_jobs else 0

            cur.execute("""
                SELECT ms.*, sp.model_name,
                       e.name AS tech_name,
                       c.name AS customer_name
                FROM MaintenanceService ms
                JOIN SolarPanel sp ON ms.panel_id = sp.panel_id
                LEFT JOIN Employee e ON ms.technician_id = e.employee_id
                LEFT JOIN Customer c ON ms.customer_id = c.customer_id
                ORDER BY ms.service_date DESC
                LIMIT 10
            """)
            jobs = cur.fetchall()

            cur.execute("""
                SELECT st.sale_id,
                       c.name AS customer_name,
                       sp.model_name,
                       st.sale_date,
                       st.total_price,
                       st.payment_status
                FROM SalesTransaction st
                JOIN Customer c ON st.customer_id = c.customer_id
                JOIN SolarPanel sp ON st.panel_id = sp.panel_id
                WHERE st.payment_status = 'Requested'
                ORDER BY st.sale_date DESC
                LIMIT 10
            """)
            sales_requests = cur.fetchall()

            cur.execute("""
                SELECT ra.rental_id,
                       c.name AS customer_name,
                       sp.model_name,
                       ra.start_date,
                       ra.monthly_rental_fee,
                       ra.payment_status
                FROM RentalAgreement ra
                JOIN Customer c ON ra.customer_id = c.customer_id
                JOIN SolarPanel sp ON ra.panel_id = sp.panel_id
                ORDER BY ra.start_date DESC
                LIMIT 10
            """)
            rental_requests = cur.fetchall()

            cur.execute("""
                SELECT ms.maintenance_id,
                       c.name AS customer_name,
                       sp.model_name,
                       ms.service_date,
                       ms.service_type,
                       ms.maintenance_status
                FROM MaintenanceService ms
                JOIN SolarPanel sp ON ms.panel_id = sp.panel_id
                LEFT JOIN Customer c ON ms.customer_id = c.customer_id
                WHERE ms.maintenance_status = 'Requested'
                ORDER BY ms.service_date DESC
                LIMIT 10
            """)
            service_requests = cur.fetchall()
            cur.close()

            return render_template(
                'employee_dashboard.html',
                role=role,
                jobs=jobs,
                sales_requests=sales_requests,
                rental_requests=rental_requests,
                service_requests=service_requests,
                revenue=revenue,
                pending_sales=pending_sales,
                open_jobs=open_jobs
            )

        # Technician view
        cur.execute("""
            SELECT ms.*, sp.model_name, c.name AS customer_name, c.address
            FROM MaintenanceService ms
            JOIN SolarPanel sp ON ms.panel_id = sp.panel_id
            LEFT JOIN Customer c ON ms.customer_id = c.customer_id
            WHERE ms.technician_id = %s
              AND ms.maintenance_status != 'Completed'
            ORDER BY ms.service_date ASC
        """, (eid,))
        jobs = cur.fetchall()
        cur.close()

    return render_template('employee_dashboard.html', role=role, jobs=jobs)


# --- TECHNICIAN ACTION: COMPLETE JOB ---
@app.route('/technician/complete_job/<int:maintenance_id>', methods=['GET', 'POST'])
@employee_login_required
def complete_job(maintenance_id):
    eid = session['employee_id']

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT ms.*, sp.model_name, c.name AS customer_name
            FROM MaintenanceService ms
            JOIN SolarPanel sp ON ms.panel_id = sp.panel_id
            LEFT JOIN Customer c ON ms.customer_id = c.customer_id
            WHERE ms.maintenance_id = %s AND ms.technician_id = %s
        """, (maintenance_id, eid))
        job = cur.fetchone()

        if not job:
            cur.close()
            flash('Job not found or not assigned to you.', 'danger')
            return redirect(url_for('employee_dashboard'))

        if request.method == 'POST':
            if 'photo' not in request.files:
                flash('No file part.', 'danger')
                return redirect(request.url)

            file = request.files['photo']
            if file.filename == '':
                flash('No image selected.', 'danger')
                return redirect(request.url)

            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename or '')
                unique_name = f"job_{maintenance_id}_{filename}"
                upload_folder = app.config['UPLOAD_FOLDER']
                full_path = os.path.join(upload_folder, unique_name)
                os.makedirs(upload_folder, exist_ok=True)
                file.save(full_path)
                db_path = os.path.join('uploads', unique_name).replace("\\", "/")

                cur.execute("""
                    UPDATE MaintenanceService
                    SET completion_image = %s, maintenance_status = 'Completed'
                    WHERE maintenance_id = %s
                """, (db_path, maintenance_id))

                cur.execute("""
                    SELECT customer_id, cost_of_service, billing_status
                    FROM MaintenanceService
                    WHERE maintenance_id = %s
                """, (maintenance_id,))
                job_data = cur.fetchone()

                if job_data and job_data['cost_of_service'] > 0 and job_data['billing_status'] == 'NotBilled':
                    reference_id = f"MS-{maintenance_id}"
                    cur.execute("""
                        INSERT INTO Payment (
                            customer_id, amount_paid, payment_date,
                            payment_method, payment_type, payment_status, reference_id
                        )
                        VALUES (%s, %s, NOW(), 'Cash', 'Maintenance', 'Pending', %s)
                    """, (job_data['customer_id'], job_data['cost_of_service'], reference_id))
                    cur.execute("""
                        UPDATE MaintenanceService
                        SET billing_status = 'Invoiced'
                        WHERE maintenance_id = %s
                    """, (maintenance_id,))
                    flash('Job completed, photo uploaded, and Customer Invoice generated automatically!', 'success')
                else:
                    flash('Job completed and photo uploaded.', 'success')

                conn.commit()
                cur.close()
                return redirect(url_for('employee_dashboard'))
            else:
                flash('Invalid file type. Please upload PNG, JPG, or GIF.', 'danger')
                return redirect(request.url)

        cur.close()
    return render_template('technician_complete_job.html', job=job)


# --- ADMIN ROUTES ---
@app.route('/admin/panels')
@admin_required
def admin_panels():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM SolarPanel")
        panels = cur.fetchall()
        cur.close()
    return render_template('admin_panels.html', panels=panels)

@app.route('/admin/panels/add', methods=['GET', 'POST'])
@admin_required
def admin_add_panel():
    if request.method == 'POST':
        model_name = request.form['model_name']
        p_type = request.form['type']
        capacity = request.form['capacity_kw']
        price = request.form['price']
        warranty = request.form['warranty_info']

        image_path = 'images/default_panel.jpg'
        if 'panel_image' in request.files:
            file = request.files['panel_image']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_name = f"panel_{int(datetime.datetime.now().timestamp())}_{filename}"
                upload_folder = app.config['UPLOAD_FOLDER']
                os.makedirs(upload_folder, exist_ok=True)
                file.save(os.path.join(upload_folder, unique_name))
                image_path = f"uploads/{unique_name}"

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO SolarPanel
                (model_name, type, capacity_kw, price, warranty_info, status, image_path)
                VALUES (%s, %s, %s, %s, %s, 'Available', %s)
            """, (model_name, p_type, capacity, price, warranty, image_path))
            conn.commit()
            panel_id = cur.lastrowid
            cur.execute("""
                INSERT INTO Inventory (panel_id, stock_quantity, cost_per_unit, reorder_level)
                VALUES (%s, 0, 0, 5)
            """, (panel_id,))
            conn.commit()
            cur.close()

        flash('New Panel Added Successfully!', 'success')
        return redirect(url_for('admin_panels'))

    return render_template('admin_add_panels.html')

@app.route('/admin/rentals')
@admin_required
def admin_rentals():
    current_month_str = datetime.date.today().strftime('%Y-%m')
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT ra.*, c.name as cname, sp.model_name,
                   (SELECT COUNT(*)
                    FROM Payment p
                    WHERE p.reference_id = CONCAT('Rental ', ra.rental_id, ' ', %s)
                   ) as billed_this_month
            FROM RentalAgreement ra
            JOIN Customer c ON ra.customer_id=c.customer_id
            JOIN SolarPanel sp ON ra.panel_id=sp.panel_id
        """, (current_month_str,))
        rentals = cur.fetchall()
        cur.close()
    return render_template('admin_rentals.html', rentals=rentals)

@app.route('/admin/rentals/configure/<int:rental_id>', methods=['GET', 'POST'])
@employee_login_required
@admin_required
def admin_configure_rental(rental_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT ra.*, c.name AS customer_name, sp.model_name, sp.capacity_kw
            FROM RentalAgreement ra
            JOIN Customer c ON ra.customer_id = c.customer_id
            JOIN SolarPanel sp ON ra.panel_id = sp.panel_id
            WHERE ra.rental_id = %s
        """, (rental_id,))
        rental = cur.fetchone()

        if not rental:
            cur.close()
            flash('Rental not found.', 'danger')
            return redirect(url_for('admin_rentals'))

        cur.execute("SELECT employee_id, name FROM Employee WHERE role = 'Technician'")
        technicians = cur.fetchall()

        if request.method == 'POST':
            start_date = request.form['start_date'] or None
            end_date = request.form['end_date'] or None
            monthly_fee = request.form['monthly_rental_fee'] or None
            technician_id = request.form.get('technician_id') or None

            cur.execute("""
                UPDATE RentalAgreement
                SET start_date = %s, end_date = %s, monthly_rental_fee = %s
                WHERE rental_id = %s
            """, (start_date, end_date, monthly_fee, rental_id))

            fee_value = float(monthly_fee) if monthly_fee else 0.00

            cur.execute("""
                SELECT maintenance_id FROM MaintenanceService
                WHERE rental_id = %s AND service_type = 'Installation'
                LIMIT 1
            """, (rental_id,))
            existing_job = cur.fetchone()

            if existing_job:
                cur.execute("""
                    UPDATE MaintenanceService
                    SET service_date = %s, technician_id = %s, cost_of_service = %s
                    WHERE maintenance_id = %s
                """, (start_date, technician_id, fee_value, existing_job['maintenance_id']))
            else:
                cur.execute("""
                    INSERT INTO MaintenanceService
                        (panel_id, customer_id, rental_id, service_date, service_type,
                         technician_id, cost_of_service, maintenance_status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'Scheduled')
                """, (rental['panel_id'], rental['customer_id'], rental_id,
                      start_date, 'Installation', technician_id, fee_value))

            conn.commit()
            cur.close()
            flash('Rental terms saved and installation job updated/created.', 'success')
            return redirect(url_for('admin_rentals'))

        cur.close()
    return render_template('admin_configure_rental.html', rental=rental, technicians=technicians)

@app.route('/customer/rental_pay/<int:rental_id>', methods=['GET', 'POST'])
@customer_login_required
def customer_rental_pay(rental_id):
    cid = session['customer_id']

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT ra.*, sp.model_name, sp.capacity_kw
            FROM RentalAgreement ra
            JOIN SolarPanel sp ON ra.panel_id = sp.panel_id
            WHERE ra.rental_id = %s AND ra.customer_id = %s
        """, (rental_id, cid))
        rental = cur.fetchone()

        if not rental:
            cur.close()
            flash('Rental not found.', 'danger')
            return redirect(url_for('customer_dashboard'))

        if request.method == 'POST':
            if rental['monthly_rental_fee'] is None:
                cur.close()
                flash('Monthly rental fee has not been set by admin yet.', 'danger')
                return redirect(url_for('customer_dashboard'))

            billing_month = request.form['billing_month']
            amount = rental['monthly_rental_fee']

            cur.execute("""
                INSERT INTO Payment (
                    customer_id, amount_paid, payment_date,
                    payment_method, payment_type, payment_status, reference_id
                )
                VALUES (%s, %s, NOW(), 'Cash', 'Rental', 'Pending', %s)
            """, (cid, amount, f"Rental {rental_id} {billing_month}"))
            payment_id = cur.lastrowid
            conn.commit()
            cur.close()
            return redirect(url_for('customer_pay', payment_id=payment_id))

        cur.close()
    return render_template('customer_rental_pay.html', rental=rental)

@app.route('/admin/rentals/invoice/<int:rental_id>', methods=['POST'])
@employee_login_required
@admin_required
def admin_generate_rental_invoice(rental_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT customer_id, monthly_rental_fee
            FROM RentalAgreement WHERE rental_id = %s
        """, (rental_id,))
        rental = cur.fetchone()

        if not rental or not rental['monthly_rental_fee']:
            cur.close()
            flash('Cannot generate invoice: missing monthly fee.', 'danger')
            return redirect(url_for('admin_rentals'))

        today = datetime.date.today()
        billing_month = today.strftime('%Y-%m')
        reference_id = f"Rental {rental_id} {billing_month}"

        cur.execute("""
            INSERT INTO Payment (
                customer_id, amount_paid, payment_date,
                payment_method, payment_type, payment_status, reference_id
            )
            VALUES (%s, %s, NOW(), 'Cash', 'Rental', 'Pending', %s)
        """, (rental['customer_id'], rental['monthly_rental_fee'], reference_id))
        conn.commit()
        cur.close()

    flash(f'Monthly rental invoice created for rental #{rental_id} ({billing_month}).', 'success')
    return redirect(url_for('admin_rentals'))

@app.route('/admin/rentals/add', methods=['GET', 'POST'])
@admin_required
def admin_add_rental():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT customer_id, name FROM Customer")
        customers = cur.fetchall()
        cur.execute("SELECT panel_id, model_name FROM SolarPanel")
        panels = cur.fetchall()

        if request.method == 'POST':
            cur.execute("""
                INSERT INTO RentalAgreement
                    (customer_id, panel_id, start_date, monthly_rental_fee, payment_status)
                VALUES (%s, %s, %s, %s, 'Pending')
            """, (request.form['customer_id'], request.form['panel_id'],
                  request.form['start_date'], request.form['monthly_rental_fee']))
            conn.commit()
            cur.close()
            return redirect(url_for('admin_rentals'))

        cur.close()
    return render_template('admin_add_rental.html', customers=customers, panels=panels)

@app.route('/admin/sales')
@employee_login_required
@admin_required
def admin_sales():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT st.*,
                   c.name AS cname,
                   sp.model_name,
                   ms.completion_image AS proof_image
            FROM SalesTransaction st
            JOIN Customer c ON st.customer_id = c.customer_id
            JOIN SolarPanel sp ON st.panel_id = sp.panel_id
            LEFT JOIN MaintenanceService ms ON ms.panel_id = st.panel_id AND ms.customer_id = st.customer_id
            ORDER BY st.sale_date DESC
        """)
        sales = cur.fetchall()
        cur.close()
    return render_template('admin_sales.html', sales=sales)

@app.route('/admin/sales/add', methods=['GET', 'POST'])
@employee_login_required
@admin_required
def admin_add_sale():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT customer_id, name FROM Customer")
        customers = cur.fetchall()
        cur.execute("SELECT panel_id, model_name FROM SolarPanel")
        panels = cur.fetchall()

        if request.method == 'POST':
            cur.execute("""
                INSERT INTO SalesTransaction
                    (customer_id, panel_id, sale_date, total_price, payment_status, invoice_number)
                VALUES (%s, %s, %s, %s, 'Pending', %s)
            """, (request.form['customer_id'], request.form['panel_id'],
                  request.form['sale_date'], request.form['total_price'],
                  generate_invoice_number()))
            conn.commit()
            cur.close()
            flash('Sale created with invoice.', 'success')
            return redirect(url_for('admin_sales'))

        cur.close()
    return render_template('admin_add_sale.html', customers=customers, panels=panels)

@app.route('/admin/sales/invoice/<int:sale_id>', methods=['POST'])
@employee_login_required
@admin_required
def admin_generate_invoice(sale_id):
    invoice_number = generate_invoice_number()
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE SalesTransaction
            SET invoice_number = %s, payment_status = 'Pending'
            WHERE sale_id = %s
        """, (invoice_number, sale_id))
        conn.commit()
        cur.close()
    flash(f'Invoice {invoice_number} generated for sale #{sale_id}.', 'success')
    return redirect(url_for('admin_sales'))

@app.route('/admin/sales/<int:sale_id>/assign_installation', methods=['GET', 'POST'])
@employee_login_required
@admin_required
def admin_assign_installation(sale_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT st.*, c.customer_id, c.name AS customer_name, sp.model_name
            FROM SalesTransaction st
            JOIN Customer c ON st.customer_id = c.customer_id
            JOIN SolarPanel sp ON st.panel_id = sp.panel_id
            WHERE st.sale_id = %s
        """, (sale_id,))
        sale = cur.fetchone()

        if not sale:
            cur.close()
            flash('Sale not found.', 'danger')
            return redirect(url_for('admin_sales'))

        cur.execute("SELECT employee_id, name FROM Employee WHERE role = 'Technician'")
        technicians = cur.fetchall()

        if request.method == 'POST':
            service_date = request.form['service_date']
            technician_id = request.form.get('technician_id') or None
            cost_of_service = request.form['cost_of_service']

            cur.execute("""
                INSERT INTO MaintenanceService
                    (panel_id, customer_id, service_date, service_type,
                     technician_id, cost_of_service, maintenance_status)
                VALUES (%s, %s, %s, %s, %s, %s, 'Scheduled')
            """, (sale['panel_id'], sale['customer_id'],
                  service_date, 'Installation', technician_id, cost_of_service))
            conn.commit()
            cur.close()
            flash(f'Installation job assigned for sale #{sale_id}.', 'success')
            return redirect(url_for('admin_maintenance'))

        cur.close()
    return render_template('admin_assign_installation.html', sale=sale, technicians=technicians)

@app.route('/admin/sales/mark_paid/<int:sale_id>', methods=['POST'])
@employee_login_required
@admin_required
def admin_mark_sale_paid(sale_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE SalesTransaction SET payment_status = 'Paid' WHERE sale_id = %s
        """, (sale_id,))
        conn.commit()
        cur.close()
    flash(f'Sale #{sale_id} marked as Paid.', 'success')
    return redirect(url_for('admin_sales'))

@app.route('/admin/maintenance')
@admin_required
def admin_maintenance():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT ms.*, sp.model_name, e.name as tech_name
            FROM MaintenanceService ms
            JOIN SolarPanel sp ON ms.panel_id=sp.panel_id
            LEFT JOIN Employee e ON ms.technician_id=e.employee_id
            ORDER BY ms.service_date DESC
        """)
        jobs = cur.fetchall()
        cur.close()
    return render_template('admin_maintenance.html', jobs=jobs)

@app.route('/admin/maintenance/invoice/<int:maintenance_id>', methods=['POST'])
@employee_login_required
@admin_required
def admin_generate_maintenance_invoice(maintenance_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT customer_id, cost_of_service, billing_status
            FROM MaintenanceService WHERE maintenance_id = %s
        """, (maintenance_id,))
        job = cur.fetchone()

        if not job or not job['customer_id']:
            cur.close()
            flash('Unable to create invoice: job or customer missing.', 'danger')
            return redirect(url_for('admin_maintenance'))

        if job['billing_status'] in ('Invoiced', 'Paid'):
            cur.close()
            flash('Invoice already generated for this job.', 'warning')
            return redirect(url_for('admin_maintenance'))

        invoice_number = generate_invoice_number()
        reference_id = f"MS-{maintenance_id}"

        cur.execute("""
            INSERT INTO Payment (
                customer_id, amount_paid, payment_date,
                payment_method, payment_type, payment_status, reference_id
            )
            VALUES (%s, %s, NOW(), 'Cash', 'Maintenance', 'Pending', %s)
        """, (job['customer_id'], job['cost_of_service'], reference_id))

        cur.execute("""
            UPDATE MaintenanceService SET billing_status = 'Invoiced'
            WHERE maintenance_id = %s
        """, (maintenance_id,))

        conn.commit()
        cur.close()

    flash(f'Invoice {invoice_number} generated for job #{maintenance_id}.', 'success')
    return redirect(url_for('admin_maintenance'))

@app.route('/admin/maintenance/assign/<int:maintenance_id>', methods=['GET', 'POST'])
@employee_login_required
@admin_required
def admin_assign_maintenance(maintenance_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT ms.*, sp.model_name, c.name AS customer_name
            FROM MaintenanceService ms
            JOIN SolarPanel sp ON ms.panel_id = sp.panel_id
            LEFT JOIN Customer c ON ms.customer_id = c.customer_id
            WHERE ms.maintenance_id = %s
        """, (maintenance_id,))
        job = cur.fetchone()

        if not job:
            cur.close()
            flash('Maintenance job not found.', 'danger')
            return redirect(url_for('admin_maintenance'))

        cur.execute("SELECT employee_id, name FROM Employee WHERE role = 'Technician'")
        technicians = cur.fetchall()

        if request.method == 'POST':
            service_date = request.form['service_date']
            technician_id = request.form.get('technician_id') or None
            cost_of_service = request.form['cost_of_service']

            cur.execute("""
                UPDATE MaintenanceService
                SET service_date = %s, technician_id = %s, cost_of_service = %s
                WHERE maintenance_id = %s
            """, (service_date, technician_id, cost_of_service, maintenance_id))
            conn.commit()
            cur.close()
            flash('Maintenance job updated and technician assigned.', 'success')
            return redirect(url_for('admin_maintenance'))

        cur.close()
    return render_template('admin_assign_maintenance.html', job=job, technicians=technicians)

@app.route('/admin/maintenance/add', methods=['GET', 'POST'])
@admin_required
def admin_add_maintenance():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT panel_id, model_name FROM SolarPanel")
        panels = cur.fetchall()
        cur.execute("SELECT customer_id, name FROM Customer")
        customers = cur.fetchall()
        cur.execute("SELECT employee_id, name FROM Employee WHERE role='Technician'")
        techs = cur.fetchall()

        if request.method == 'POST':
            cur.execute("""
                INSERT INTO MaintenanceService
                    (panel_id, customer_id, service_date, service_type,
                     technician_id, cost_of_service, maintenance_status)
                VALUES (%s, %s, %s, %s, %s, %s, 'Scheduled')
            """, (request.form['panel_id'], request.form['customer_id'] or None,
                  request.form['service_date'], request.form['service_type'],
                  request.form['technician_id'] or None, request.form['cost_of_service']))
            conn.commit()
            cur.close()
            return redirect(url_for('admin_maintenance'))

        cur.close()
    return render_template('admin_add_maintenance.html', panels=panels, customers=customers, techs=techs)

@app.route('/admin/inventory')
@employee_login_required
@admin_required
def admin_inventory():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                sp.panel_id,
                sp.model_name,
                COALESCE(i.stock_quantity, 0) AS stock_quantity,
                COALESCE(i.supplier_info, '-') AS supplier_info,
                COALESCE(i.cost_per_unit, 0) AS cost_per_unit,
                COALESCE(i.reorder_level, 0) AS reorder_level
            FROM SolarPanel sp
            LEFT JOIN Inventory i ON i.panel_id = sp.panel_id
            ORDER BY sp.model_name
        """)
        inv = cur.fetchall()
        cur.close()
    return render_template('admin_inventory.html', inv=inv)

@app.route('/admin/inventory/add', methods=['GET', 'POST'])
@employee_login_required
@admin_required
def admin_add_inventory():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT panel_id, model_name FROM SolarPanel ORDER BY model_name")
        panels = cur.fetchall()

        if request.method == 'POST':
            try:
                panel_id = int(request.form['panel_id'])
                stock_quantity = int(request.form['stock_quantity'])
                supplier_info = (request.form.get('supplier_info') or '').strip() or None
                cost_per_unit = float(request.form['cost_per_unit'])
                reorder_level_raw = request.form.get('reorder_level')
                reorder_level = int(reorder_level_raw) if reorder_level_raw not in (None, '', ' ') else None

                cur.execute("""
                    INSERT INTO Inventory (panel_id, stock_quantity, supplier_info, cost_per_unit, reorder_level)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        stock_quantity = VALUES(stock_quantity),
                        supplier_info  = VALUES(supplier_info),
                        cost_per_unit  = VALUES(cost_per_unit),
                        reorder_level  = VALUES(reorder_level)
                """, (panel_id, stock_quantity, supplier_info, cost_per_unit, reorder_level))
                conn.commit()
                cur.close()
                flash('Inventory saved (added/updated).', 'success')
                return redirect(url_for('admin_inventory'))

            except Exception as e:
                conn.rollback()
                cur.close()
                flash(f'Error saving inventory: {e}', 'danger')
                return render_template('admin_add_inventory.html', panels=panels)

        cur.close()
    return render_template('admin_add_inventory.html', panels=panels)

@app.route('/admin/inventory/edit/<int:panel_id>', methods=['GET', 'POST'])
@employee_login_required
@admin_required
def admin_edit_inventory(panel_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT sp.panel_id, sp.model_name,
                   COALESCE(i.stock_quantity, 0) AS stock_quantity,
                   COALESCE(i.supplier_info, '') AS supplier_info,
                   COALESCE(i.cost_per_unit, 0) AS cost_per_unit,
                   COALESCE(i.reorder_level, 5) AS reorder_level
            FROM SolarPanel sp
            LEFT JOIN Inventory i ON i.panel_id = sp.panel_id
            WHERE sp.panel_id = %s
        """, (panel_id,))
        item = cur.fetchone()

        if not item:
            cur.close()
            flash("Panel not found.", "danger")
            return redirect(url_for('admin_inventory'))

        if request.method == 'POST':
            try:
                stock_quantity = int(request.form['stock_quantity'])
                supplier_info = (request.form.get('supplier_info') or '').strip() or None
                cost_per_unit = float(request.form['cost_per_unit'])
                reorder_level_raw = request.form.get('reorder_level')
                reorder_level = int(reorder_level_raw) if reorder_level_raw not in (None, '', ' ') else None

                cur.execute("""
                    INSERT INTO Inventory (panel_id, stock_quantity, supplier_info, cost_per_unit, reorder_level)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        stock_quantity = VALUES(stock_quantity),
                        supplier_info  = VALUES(supplier_info),
                        cost_per_unit  = VALUES(cost_per_unit),
                        reorder_level  = VALUES(reorder_level)
                """, (panel_id, stock_quantity, supplier_info, cost_per_unit, reorder_level))
                conn.commit()
                cur.close()
                flash("Inventory updated.", "success")
                return redirect(url_for('admin_inventory'))
            except Exception as e:
                conn.rollback()
                cur.close()
                flash(f"Error updating inventory: {e}", "danger")
                return render_template('admin_edit_inventory.html', item=item)

        cur.close()
    return render_template('admin_edit_inventory.html', item=item)

@app.route('/admin/panels/edit/<int:panel_id>', methods=['GET', 'POST'])
@employee_login_required
@admin_required
def admin_edit_panel(panel_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM SolarPanel WHERE panel_id=%s", (panel_id,))
        panel = cur.fetchone()

        if not panel:
            cur.close()
            flash("Panel not found.", "danger")
            return redirect(url_for('admin_panels'))

        if request.method == 'POST':
            model_name = request.form['model_name']
            p_type = request.form['type']
            capacity_kw = request.form['capacity_kw']
            price = request.form['price']
            warranty_info = request.form.get('warranty_info')
            status = request.form.get('status', panel['status'])
            image_path = panel.get('image_path') or 'images/default_panel.jpg'

            if 'panel_image' in request.files:
                file = request.files['panel_image']
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    unique_name = f"panel_{panel_id}_{int(datetime.datetime.now().timestamp())}_{filename}"
                    upload_folder = app.config['UPLOAD_FOLDER']
                    os.makedirs(upload_folder, exist_ok=True)
                    file.save(os.path.join(upload_folder, unique_name))
                    image_path = f"uploads/{unique_name}"

            cur.execute("""
                UPDATE SolarPanel
                SET model_name=%s, type=%s, capacity_kw=%s, price=%s,
                    warranty_info=%s, status=%s, image_path=%s
                WHERE panel_id=%s
            """, (model_name, p_type, capacity_kw, price, warranty_info, status, image_path, panel_id))
            conn.commit()
            cur.close()
            flash("Panel updated.", "success")
            return redirect(url_for('admin_panels'))

        cur.close()
    return render_template('admin_edit_panel.html', panel=panel)

@app.route('/admin/panel/manage/<int:panel_id>', methods=['GET', 'POST'])
@employee_login_required
@admin_required
def admin_manage_panel(panel_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                sp.panel_id, sp.model_name, sp.type, sp.capacity_kw, sp.price,
                sp.warranty_info, sp.status, sp.image_path,
                COALESCE(i.stock_quantity, 0) AS stock_quantity,
                COALESCE(i.supplier_info, '') AS supplier_info,
                COALESCE(i.cost_per_unit, 0) AS cost_per_unit,
                COALESCE(i.reorder_level, 5) AS reorder_level
            FROM SolarPanel sp
            LEFT JOIN Inventory i ON i.panel_id = sp.panel_id
            WHERE sp.panel_id = %s
        """, (panel_id,))
        item = cur.fetchone()

        if not item:
            cur.close()
            flash("Panel not found.", "danger")
            return redirect(url_for('admin_inventory'))

        if request.method == 'POST':
            try:
                model_name = request.form['model_name'].strip()
                p_type = request.form.get('type', '').strip()
                capacity_kw = request.form.get('capacity_kw') or None
                price = request.form.get('price') or None
                warranty_info = request.form.get('warranty_info') or None
                status = request.form.get('status', item['status'])
                image_path = item['image_path'] or 'images/default_panel.jpg'

                if 'panel_image' in request.files:
                    file = request.files['panel_image']
                    if file and file.filename and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        unique_name = f"panel_{panel_id}_{int(datetime.datetime.now().timestamp())}_{filename}"
                        upload_folder = app.config['UPLOAD_FOLDER']
                        os.makedirs(upload_folder, exist_ok=True)
                        file.save(os.path.join(upload_folder, unique_name))
                        image_path = f"uploads/{unique_name}"

                cur.execute("""
                    UPDATE SolarPanel
                    SET model_name=%s, type=%s, capacity_kw=%s, price=%s,
                        warranty_info=%s, status=%s, image_path=%s
                    WHERE panel_id=%s
                """, (model_name, p_type, capacity_kw, price, warranty_info, status, image_path, panel_id))

                stock_quantity = int(request.form['stock_quantity'])
                supplier_info = (request.form.get('supplier_info') or '').strip() or None
                cost_per_unit = float(request.form['cost_per_unit'])
                reorder_level_raw = request.form.get('reorder_level')
                reorder_level = int(reorder_level_raw) if reorder_level_raw not in (None, '', ' ') else None

                cur.execute("""
                    INSERT INTO Inventory (panel_id, stock_quantity, supplier_info, cost_per_unit, reorder_level)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        stock_quantity = VALUES(stock_quantity),
                        supplier_info  = VALUES(supplier_info),
                        cost_per_unit  = VALUES(cost_per_unit),
                        reorder_level  = VALUES(reorder_level)
                """, (panel_id, stock_quantity, supplier_info, cost_per_unit, reorder_level))

                conn.commit()
                cur.close()
                flash("Panel + Inventory updated.", "success")
                return redirect(url_for('admin_inventory'))

            except Exception as e:
                conn.rollback()
                cur.close()
                flash(f"Error updating: {e}", "danger")
                return render_template('admin_manage_panel.html', item=item)

        cur.close()
    return render_template('admin_manage_panel.html', item=item)

@app.route('/admin/payments')
@admin_required
def admin_payments():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT p.*, c.name as cname FROM Payment p JOIN Customer c ON p.customer_id=c.customer_id")
        pay = cur.fetchall()
        cur.close()
    return render_template('admin_payments.html', pay=pay)

@app.route('/admin/payments/add', methods=['GET', 'POST'])
@admin_required
def admin_add_payment():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT customer_id, name FROM Customer")
        customers = cur.fetchall()

        if request.method == 'POST':
            cur.execute("""
                INSERT INTO Payment
                    (customer_id, amount_paid, payment_date, payment_method, payment_type, payment_status)
                VALUES (%s, %s, NOW(), %s, %s, %s)
            """, (request.form['customer_id'], request.form['amount_paid'],
                  request.form['payment_method'], request.form['payment_type'],
                  request.form['payment_status']))
            conn.commit()
            cur.close()
            return redirect(url_for('admin_payments'))

        cur.close()
    return render_template('admin_add_payment.html', customers=customers)

@app.route('/admin/customers', endpoint='admin_customers_page')
@admin_required
def admin_customers_page():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM Customer ORDER BY created_at DESC")
        customers = cur.fetchall()
        cur.close()
    return render_template('admin_customers.html', customers=customers)

@app.route('/admin/employees')
@employee_login_required
@admin_required
def admin_employees():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT employee_id, name, email, role, phone, salary, work_schedule
            FROM Employee
            WHERE role = 'Technician'
            ORDER BY name
        """)
        employees = cur.fetchall()
        cur.close()
    return render_template('admin_employees.html', employees=employees)

@app.route('/admin/employees/add', methods=['GET', 'POST'])
@employee_login_required
@admin_required
def admin_add_employee():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        salary = request.form['salary']
        work_schedule = request.form['work_schedule']
        password = request.form['password']
        pw_hash = bcrypt.generate_password_hash(password).decode('utf-8')

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO Employee (name, email, role, phone, salary, work_schedule, password_hash)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (name, email, 'Technician', phone, salary, work_schedule, pw_hash))
            conn.commit()
            cur.close()

        flash('Technician added successfully.', 'success')
        return redirect(url_for('admin_employees'))

    return render_template('admin_add_employee.html')

@app.route('/customer/service_request', methods=['GET', 'POST'])
@customer_login_required
def customer_service_request():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT panel_id, model_name FROM SolarPanel WHERE status != 'Retired'")
        panels = cur.fetchall()

        if request.method == 'POST':
            panel_id = request.form['panel_id']
            service_date = request.form['service_date']
            service_type = request.form['service_type']
            customer_id = session['customer_id']

            cur.execute("""
                INSERT INTO MaintenanceService
                    (panel_id, customer_id, service_date, service_type,
                     technician_id, cost_of_service, maintenance_status)
                VALUES (%s, %s, %s, %s, NULL, 0, 'Requested')
            """, (panel_id, customer_id, service_date, service_type))
            conn.commit()
            cur.close()
            flash('Service request sent to admin.', 'success')
            return redirect(url_for('customer_dashboard'))

        cur.close()
    return render_template('customer_service_request.html', panels=panels)

if __name__ == '__main__':
    app.run(debug=True)