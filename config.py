import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
    MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '19_gikkx')
    MYSQL_DB = os.environ.get('MYSQL_DB', 'solar_company')
    MYSQL_CURSORCLASS = 'DictCursor'