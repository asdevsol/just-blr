import sqlite3

DATABASE = 'employees.db'

def init_db():
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS employee_salaries (
                emp_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                salary REAL NOT NULL
            )
        ''')
        conn.commit()
