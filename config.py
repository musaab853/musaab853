import os

env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(32).hex()
    MYSQL_HOST = os.environ.get('MYSQL_HOST', '127.0.0.1')
    MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_DB = os.environ.get('MYSQL_DB', 'solar_company')
    MYSQL_PORT = int(os.environ.get('MYSQL_PORT', 3306))
    MYSQL_CURSORCLASS = 'DictCursor'