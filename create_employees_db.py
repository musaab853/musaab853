from app import app, get_db, bcrypt

def create_employee(name, email, role, phone, salary, work_schedule, plain_password):
    with app.app_context():
        with get_db() as conn:
            cur = conn.cursor()
            pw_hash = bcrypt.generate_password_hash(plain_password).decode('utf-8')
            cur.execute("""
                INSERT INTO Employee (name, email, role, phone, salary, work_schedule, password_hash)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (name, email, role, phone, salary, work_schedule, pw_hash))
            conn.commit()
            cur.close()

if __name__ == '__main__':
    create_employee('System Admin', 'admin@solar.com', 'Admin',
                    '111-111-1111', 80000, '9-5', 'admin123')
    create_employee('John Technician', 'tech@solar.com', 'Technician',
                    '222-222-2222', 45000, 'Shift A', 'tech123')
    print("Employees created.")