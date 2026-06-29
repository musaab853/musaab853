from flask_bcrypt import Bcrypt

bcrypt = Bcrypt()

# 1. Admin Password
admin_pass = bcrypt.generate_password_hash('admin123').decode('utf-8')

# 2. Technician Password
tech_pass = bcrypt.generate_password_hash('tech123').decode('utf-8')

print("\n--- RUN THIS SQL IN MYSQL TO CREATE USERS ---\n")

print(f"""
INSERT INTO Employee (name, email, role, phone, salary, work_schedule, password_hash)
VALUES ('System Admin', 'admin@solar.com', 'Admin', '111-111-1111', 80000, '9-5', '{admin_pass}');
""")

print(f"""
INSERT INTO Employee (name, email, role, phone, salary, work_schedule, password_hash)
VALUES ('John Technician', 'tech@solar.com', 'Technician', '222-222-2222', 45000, 'Shift A', '{tech_pass}');
""")