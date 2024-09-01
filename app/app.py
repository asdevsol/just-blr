from flask import Flask, request, render_template, redirect, url_for
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import os
from weasyprint import HTML, CSS  # Import HTML from WeasyPrint

app = Flask(__name__)

# Database initialization
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

# Load and display uploaded file
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        file = request.files['file']
        if file and file.filename.endswith('.xlsx'):
            file_path = os.path.join('uploads', file.filename)
            file.save(file_path)
            return redirect(url_for('salary', file_path=file_path))
    return render_template('index.html')

# Display form for entering salaries
@app.route('/salary', methods=['GET', 'POST'])
def salary():
    file_path = request.args.get('file_path')
    employees = []
    existing_salaries = {}
    salary_data = {}
    debug_info = ""

    if file_path:
        df = pd.read_excel(file_path)

        # Ensure consistent data types and remove any extra spaces
        df['Emp Id'] = df['Emp Id'].astype(str).str.strip()
        employees = df[['Emp Id', 'Name']].drop_duplicates().to_dict(orient='records')

    # Handle the optional salary sheet upload
    salary_file = request.files.get('salary_file')
    if salary_file and salary_file.filename.endswith(('.xlsx', '.xls')):
        salary_df = pd.read_excel(salary_file)

        # Ensure consistent data types and remove any extra spaces
        salary_df['Code'] = salary_df['Code'].astype(str).str.strip()
        salary_data = salary_df.set_index('Code')['Salary'].to_dict()

    if request.method == 'POST':
        if 'match_all' in request.form:
            # Auto-match all salaries
            for emp in employees:
                emp_id = emp['Emp Id']
                if emp_id in salary_data:
                    existing_salaries[emp_id] = salary_data[emp_id]
                    debug_info += f"Matched salary for Emp ID {emp_id}: {salary_data[emp_id]}<br>"
        else:
            with sqlite3.connect(DATABASE) as conn:
                cursor = conn.cursor()
                for emp_id in request.form:
                    if emp_id == 'submit' or emp_id == 'match_all':
                        continue
                    salary = request.form[emp_id]
                    if salary:  # Only process non-empty salaries
                        try:
                            name = next(emp['Name'] for emp in employees if str(emp['Emp Id']) == emp_id)
                            cursor.execute('''
                                INSERT OR REPLACE INTO employee_salaries (emp_id, name, salary)
                                VALUES (?, ?, ?)
                            ''', (int(emp_id), name, float(salary)))
                            debug_info += f"Updated salary for Emp ID {emp_id}: {salary}<br>"
                        except StopIteration:
                            debug_info += f"Employee ID {emp_id} not found.<br>"
                conn.commit()
            return redirect(url_for('result', file_path=file_path))

    # Fetch existing salaries from the database
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT emp_id, salary FROM employee_salaries')
        rows = cursor.fetchall()
        db_salaries = {str(row[0]): row[1] for row in rows}  # Convert emp_id to string
        existing_salaries.update(db_salaries)

    # Render the salary form with existing salaries pre-filled
    return render_template('salary.html', employees=employees, existing_salaries=existing_salaries, debug_info=debug_info)


# Calculate deductions and display results
@app.route('/result', methods=['GET'])
def result():
    file_path = request.args.get('file_path')
    if not file_path:
        return redirect(url_for('index'))

    df = pd.read_excel(file_path)
    
    # Drop unwanted columns
    df = df.drop(columns=['Shift', 'From', 'To', 'Total Break Hours'], errors='ignore')

    # Fetch salary data from the database
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT emp_id, salary FROM employee_salaries')
        salary_data = cursor.fetchall()
        salary_dict = dict(salary_data)

    # Filter out rows where 'Emp Id' does not have corresponding salary data
    df = df[df['Emp Id'].isin(salary_dict.keys())]

    # Apply the penalty calculation
    df[['Late Deduction', 'Deduction Explanation']] = df.apply(
        lambda row: pd.Series(calculate_deduction(row, salary_dict)), axis=1
    )

    # Filter to include only rows with penalties
    df = df[(df['Late Deduction'] != 0) & (df['Late Deduction'] != "ABSENT")]

    # Save the filtered DataFrame to CSV
    output_file_path = 'static/attendance_with_deductions.csv'
    df.to_csv(output_file_path, index=False)
    
    # Render the PDF using WeasyPrint in landscape orientation
    rendered_html = render_template('pdf_template.html', table=df.to_html(classes='table table-bordered'))
    pdf_file_path = 'static/attendance_with_deductions.pdf'
    HTML(string=rendered_html).write_pdf(pdf_file_path, stylesheets=[CSS(string='@page { size: A4 landscape; margin: 20mm; }')])

    return render_template('result.html', file_path=output_file_path, pdf_path=pdf_file_path)


def calculate_deduction(row, salary_dict):
    emp_id = row['Emp Id']
    salary = salary_dict.get(emp_id, None)
    
    if salary is None:
        # If no salary data available, return default deduction
        return 50, "No salary data available, Rs. 50 flat deduction"
    
    hourly_rate = salary / (30 * 24)  # Assuming 30 days in a month

    first_punch = row.get('First Punch', '-')
    last_punch = row.get('Last Punch', '-')

    if (first_punch == '-' or pd.isna(first_punch)) and (last_punch == '-' or pd.isna(last_punch)):
        # Both punches missing: mark as absent
        return "ABSENT", "Absent. No punches recorded."

    if first_punch == '-' or pd.isna(first_punch):
        # Only first punch missing
        return 25, "No punch-in, Rs. 25 flat deduction"

    if last_punch == '-' or pd.isna(last_punch):
        # Only last punch missing
        return 25, "No punch-out, Rs. 25 flat deduction"
    
    # Determine first punch time
    first_punch_time = datetime.strptime(row['First Punch'], '%I:%M %p')
    
    # Determine the shift start time based on the punch time
    shift_start_time = determine_shift(first_punch_time)
    
    # Calculate delay
    delay = first_punch_time - shift_start_time

    # Calculate deduction based on delay
    if delay <= timedelta(minutes=15):
        return 0, "No deduction, within grace period"
    elif delay <= timedelta(minutes=45):
        return 50, "Late by up to 45 minutes, Rs. 50 flat deduction"
    else:
        # Deduction proportional to salary double for every hour late
        hours_late = (delay.total_seconds() / 3600) - 0.75  # Subtracting the first 45 minutes
        deduction_amount = hourly_rate * 2 * hours_late
        deduction_amount = max(50, round(deduction_amount, 2))  # Ensure minimum deduction of Rs. 50
        return deduction_amount, f"Late by {delay}, deduction: Rs. {deduction_amount:.2f} (2x salary for {hours_late:.2f} hours late)"

def determine_shift(punch_time):
    if punch_time.hour < 14:  # Punch time before 2 PM is considered for the 11 AM shift
        return shift_start_times["11:00 AM"]
    else:  # Punch time from 2 PM onward is considered for the 3 PM shift
        return shift_start_times["03:00 PM"]

# Define the shift start times
shift_start_times = {
    "11:00 AM": datetime.strptime("11:00 AM", "%I:%M %p"),
    "03:00 PM": datetime.strptime("03:00 PM", "%I:%M %p")
}

if __name__ == '__main__':
    if not os.path.exists('uploads'):
        os.makedirs('uploads')
    if not os.path.exists('static'):
        os.makedirs('static')
    init_db()
    #app.run(debug=False, host='0.0.0.0', port=3000)
