# ☀️ Solar Company Management System

A full-stack web application for managing a solar panel company's operations — including panel sales, rentals, maintenance scheduling, inventory tracking, employee management, and customer self-service.

Built with **Flask**, **MySQL**, and **Jinja2** templates.

---

## 📋 Table of Contents

- [Features](#-features)
- [Tech Stack](#-tech-stack)
- [Database Schema](#-database-schema)
- [Project Structure](#-project-structure)
- [Getting Started](#-getting-started)
- [Environment Variables](#-environment-variables)
- [User Roles](#-user-roles)
- [Screenshots](#-screenshots)
- [License](#-license)

---

## ✨ Features

### 🔑 Authentication & Authorization
- Separate login portals for **Customers** and **Employees**
- Password hashing with **bcrypt**
- Role-based access control (Admin, Technician, Customer)

### 👤 Customer Portal
- **Register & Login** — secure account creation
- **Browse Panels** — view available solar panels
- **Buy Panels** — purchase solar panels with auto-generated invoices
- **Rent Panels** — submit rental requests; admin configures terms
- **Request Maintenance** — schedule repair/cleaning/inspection services
- **Make Payments** — pay pending invoices (supports Credit Card, Bank Transfer, Cash, UPI)
- **Dashboard** — view all rentals, purchases, maintenance jobs, and payment history

### 🛠️ Admin Dashboard
- **Revenue Overview** — total completed payments at a glance
- **Manage Panels** — add, edit, and retire solar panels (with image uploads)
- **Sales Management** — view sales, generate invoices, assign installations, mark as paid
- **Rental Management** — configure rental terms (dates, monthly fees), generate monthly invoices
- **Maintenance & Jobs** — create maintenance jobs, assign technicians, generate service invoices
- **Inventory Control** — track stock quantities, supplier info, cost per unit, reorder levels
- **Employee Management** — add and manage technician accounts
- **Customer Directory** — view all registered customers
- **Payment Tracking** — view and add payment records

### 🔧 Technician Portal
- **Assigned Jobs** — view jobs assigned by admin
- **Complete Jobs** — upload proof-of-completion photos; auto-generates customer invoices

### ⚙️ Automated Features
- **Auto Rental Invoice Generation** — monthly invoices are auto-created for active rentals (runs hourly via `@app.before_request`)
- **Connection Pooling** — MySQL connection pool via `DBUtils` for performance

---

## 🛠️ Tech Stack

| Layer        | Technology                        |
|--------------|-----------------------------------|
| **Backend**  | Python 3, Flask                   |
| **Database** | MySQL (PyMySQL driver)            |
| **Auth**     | Flask-Bcrypt                      |
| **Pooling**  | DBUtils (PooledDB)                |
| **Frontend** | HTML5, CSS3, Jinja2 Templates     |
| **Uploads**  | Werkzeug (secure file uploads)    |

---

## 🗄️ Database Schema

The application uses **8 tables** in a MySQL database called `solar_company`:

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│    Customer       │     │   SolarPanel      │     │    Employee       │
├──────────────────┤     ├──────────────────┤     ├──────────────────┤
│ customer_id (PK) │     │ panel_id (PK)     │     │ employee_id (PK) │
│ name             │     │ model_name        │     │ name             │
│ email            │     │ type              │     │ email            │
│ phone            │     │ capacity_kw       │     │ role             │
│ address          │     │ price             │     │ phone            │
│ password_hash    │     │ warranty_info     │     │ salary           │
│ ...              │     │ status            │     │ password_hash    │
└──────────────────┘     └──────────────────┘     └──────────────────┘
        │                     │       │                    │
        ├─────────┬───────────┤       │                    │
        │         │           │       │                    │
        ▼         ▼           ▼       ▼                    ▼
┌───────────────┐ ┌─────────────────┐ ┌──────────────────────┐
│RentalAgreement│ │SalesTransaction │ │ MaintenanceService    │
├───────────────┤ ├─────────────────┤ ├──────────────────────┤
│ rental_id (PK)│ │ sale_id (PK)    │ │ maintenance_id (PK)  │
│ customer_id   │ │ customer_id     │ │ panel_id             │
│ panel_id      │ │ panel_id        │ │ customer_id          │
│ start_date    │ │ sale_date       │ │ service_date         │
│ end_date      │ │ total_price     │ │ service_type         │
│ monthly_fee   │ │ payment_status  │ │ technician_id        │
│ payment_status│ │ invoice_number  │ │ cost_of_service      │
└───────────────┘ └─────────────────┘ │ maintenance_status   │
                                      └──────────────────────┘
┌──────────────────┐     ┌──────────────────┐
│    Payment        │     │   Inventory       │
├──────────────────┤     ├──────────────────┤
│ payment_id (PK)  │     │ inventory_id (PK)│
│ customer_id      │     │ panel_id          │
│ amount_paid      │     │ stock_quantity    │
│ payment_date     │     │ supplier_info     │
│ payment_method   │     │ cost_per_unit     │
│ payment_type     │     │ reorder_level     │
│ payment_status   │     └──────────────────┘
│ reference_id     │
└──────────────────┘
```

> The full SQL schema is available in [`sql.schema`](sql.schema).

---

## 📁 Project Structure

```
Solar_Company/
├── app.py                  # Main Flask application (all routes)
├── config.py               # Configuration (DB credentials, secret key)
├── requirements.txt        # Python dependencies
├── sql.schema              # MySQL database schema
├── create_employees_db.py  # Script to seed employee data
├── create_users.py         # Script to seed customer data
├── .gitignore              # Git ignore rules
│
├── static/
│   ├── css/
│   │   └── style.css       # Application stylesheet
│   ├── images/             # Default panel images
│   └── uploads/            # User-uploaded images (job photos, panel images)
│
└── templates/
    ├── base.html                       # Base template (navbar, layout)
    ├── index.html                      # Landing page
    ├── panels.html                     # Public panel catalog
    │
    ├── customer_login.html             # Customer login
    ├── customer_register.html          # Customer registration
    ├── customer_dashboard.html         # Customer dashboard
    ├── customer_buy_form.html          # Purchase a panel
    ├── customer_rent_form.html         # Rent a panel
    ├── customer_rental_pay.html        # Pay rental invoice
    ├── customer_pay.html               # Generic payment page
    ├── customer_service_request.html   # Request maintenance
    ├── payment_success.html            # Payment confirmation
    │
    ├── employee_login.html             # Employee login
    ├── employee_dashboard.html         # Employee/Admin dashboard
    ├── technician_complete_job.html    # Technician job completion
    │
    ├── admin_panels.html               # Manage panels
    ├── admin_add_panels.html           # Add new panel
    ├── admin_edit_panel.html           # Edit panel details
    ├── admin_manage_panel.html         # Panel + inventory management
    ├── admin_sales.html                # View sales
    ├── admin_add_sale.html             # Create a sale
    ├── admin_assign_installation.html  # Assign installation job
    ├── admin_rentals.html              # View rentals
    ├── admin_add_rentals.html          # Create a rental
    ├── admin_configure_rental.html     # Configure rental terms
    ├── admin_maintenance.html          # View maintenance jobs
    ├── admin_add_maintenance.html      # Create maintenance job
    ├── admin_assign_maintenance.html   # Assign technician to job
    ├── admin_inventory.html            # View inventory
    ├── admin_add_inventory.html        # Add inventory record
    ├── admin_edit_inventory.html       # Edit inventory record
    ├── admin_payments.html             # View all payments
    ├── admin_add_payment.html          # Add payment record
    ├── admin_customers.html            # View all customers
    ├── admin_employees.html            # View technicians
    └── admin_add_employee.html         # Add technician
```

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.8+**
- **MySQL 5.7+** (or MariaDB)

### 1. Clone the Repository

```bash
git clone https://github.com/musaab853/musaab853.git
cd musaab853
```

### 2. Create a Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Set Up the Database

Log into MySQL and run the schema:

```bash
mysql -u root -p < sql.schema
```

This creates the `solar_company` database and all 8 tables.

### 5. Seed Initial Data (Optional)

```bash
python create_employees_db.py   # Creates admin & technician accounts
python create_users.py          # Creates sample customer accounts
```

### 6. Run the Application

```bash
python app.py
```

The app will start at **http://127.0.0.1:5000**

---

## 🔐 Environment Variables

Configure these environment variables (or they'll use defaults from `config.py`):

| Variable         | Default                      | Description              |
|------------------|------------------------------|--------------------------|
| `SECRET_KEY`     | `dev-key-change-in-production` | Flask session secret key |
| `MYSQL_HOST`     | `localhost`                  | MySQL server hostname    |
| `MYSQL_USER`     | `root`                       | MySQL username           |
| `MYSQL_PASSWORD` | *(set in config)*            | MySQL password           |
| `MYSQL_DB`       | `solar_company`              | MySQL database name      |

> 💡 **Tip:** Create a `.env` file in the project root to set these variables. The `.env` file is excluded from version control via `.gitignore`.

---

## 👥 User Roles

| Role           | Access                                                                 |
|----------------|------------------------------------------------------------------------|
| **Customer**   | Browse panels, buy/rent panels, request maintenance, make payments     |
| **Admin**      | Full system access — manage panels, sales, rentals, inventory, employees, payments |
| **Technician** | View assigned jobs, upload completion photos, auto-generate invoices   |

### Default Login Routes

| Portal      | URL                         |
|-------------|-----------------------------|
| Home Page   | `/`                         |
| Customer    | `/customer/login`           |
| Employee    | `/employee/login`           |

---

## 📸 Screenshots

*Coming soon — run the application and explore the dashboard!*

---

## 📄 License

This project is for educational / portfolio purposes.

---

> Built with ❤️ using Flask & MySQL
