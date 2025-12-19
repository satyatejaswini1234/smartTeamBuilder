import os
import sqlite3
from flask import Flask, request, jsonify, g, render_template, redirect, url_for, flash
import google.generativeai as genai
import pandas as pd
from werkzeug.utils import secure_filename
import random

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Replace with a real secret key

DATABASE = 'team_compatibility.db'
GEMINI_API_KEY ='yourSecretKey'
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

# Create UPLOAD_FOLDER if it doesn't exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

genai.configure(api_key=GEMINI_API_KEY)

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db
@app.route('/employee_work_data', methods=['GET'])
def get_employee_work_data():
    employees = query_db('SELECT name FROM employees')
    tasks = ['Development', 'Testing', 'Documentation', 'Meetings']
    
    data = []
    for employee in employees:
        employee_data = {
            'name': employee['name'],
            'Development': random.randint(10, 50),
            'Testing': random.randint(10, 50),
            'Documentation': random.randint(10, 50),
            'Meetings': random.randint(10, 50)
        }
        data.append(employee_data)
    
    return jsonify(data)
@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/create_project', methods=['POST'])
def create_project():
    data = request.json
    project_name = data['project_name']
    requirements = data['requirements']
    deadline = data['deadline']

    employees = query_db('SELECT * FROM employees')
    
    prompt = f"Project: {project_name}\nRequirements: {requirements}\nDeadline: {deadline}\n\n"
    prompt += "Employees:\n"
    available_employees = [emp for emp in employees if not emp['project_assigned']]
    for emp in available_employees:
        prompt += f"Name: {emp['name']}, Role: {emp['role']}, Skills: {emp['technical_skills']}, " \
               f"Experience: {emp['years_experience']} years, Personality: {emp['personality_type']}, " \
               f"Work Style: {emp['work_style']}, Communication: {emp['communication_style']}\n," \
               f"Previously Worked Projects: {emp['previous_worked_projects']}\n," \
               f"Previous project success percentage: {emp['previous_success_percentage']}\n"

    prompt += "\nBased on the project details and employee information, suggest the best team for this project. " \
          "Provide reasoning for your choices. Format your response as follows:\n" \
          "Team Suggestion:\n" \
          "1. [Employee Name] - [Role]\n" \
          "2. [Employee Name] - [Role]\n" \
          "...\n\n" \
          "Reasoning:\n" \
          "1. [Reason for first employee]\n" \
          "2. [Reason for second employee]\n" \
          "...\n\n" \
          "Team Dynamics:\n" \
          "[Brief explanation of how the team members' skills and personalities complement each other]"

    model = genai.GenerativeModel('gemini-pro')
    response = model.generate_content(prompt)

    ai_suggestion = response.text

    return jsonify({
        'project': project_name,
        'ai_suggestion': ai_suggestion
    })

@app.route('/teams', methods=['GET'])
def get_teams():
    teams = query_db('SELECT * FROM teams')
    return jsonify([dict(team) for team in teams])

@app.route('/employees', methods=['GET'])
def get_employees():
    search_query = request.args.get('search', '')
    limit = request.args.get('limit', 5, type=int)
    
    query = '''
    SELECT e.*,t.team_name FROM employees e 
    LEFT JOIN teams t ON e.team_id = t.team_id
    WHERE e.name  LIKE ? OR role LIKE ? 
    ORDER BY 
        CASE 
            WHEN e.name LIKE ? THEN 1 
            WHEN e.name LIKE ? THEN 2 
            ELSE 3 
        END 
    LIMIT ?
    '''
    search_param = f'%{search_query}%'
    exact_match = f'{search_query}%'
    employees = query_db(query, (search_param, search_param, exact_match, search_param, limit))
    
    employee_list = []
    for emp in employees:
        emp_dict = dict(emp)
        # Remove team_name from the main dictionary and add it as a separate key
        team_name = emp_dict.pop('team_name', None)
        emp_dict['team_name'] = team_name if team_name else 'Not Assigned'
        employee_list.append(emp_dict)
    
    return jsonify(employee_list)

@app.route('/employee_suggestions', methods=['GET'])
def get_employee_suggestions():
    search_query = request.args.get('search', '')
    limit = request.args.get('limit', 5, type=int)
    
    query = '''
    SELECT name FROM employees 
    WHERE name LIKE ? 
    ORDER BY 
        CASE 
            WHEN name LIKE ? THEN 1 
            ELSE 2 
        END 
    LIMIT ?
    '''
    search_param = f'%{search_query}%'
    exact_match = f'{search_query}%'
    suggestions = query_db(query, (search_param, exact_match, limit))
    
    return jsonify([suggestion['name'] for suggestion in suggestions])

@app.route('/add_team', methods=['GET', 'POST'])
def add_team():
    if request.method == 'POST':
        team_name = request.form['team_name']
        department = request.form['department']
        db = get_db()
        db.execute('INSERT INTO teams (team_name, department) VALUES (?, ?)',
                   [team_name, department])
        db.commit()
        return redirect(url_for('home'))
    
    return render_template('add_team.html')

def employee_exists(name):
    return query_db('SELECT 1 FROM employees WHERE name = ?', [name], one=True) is not None

@app.route('/add_employee', methods=['GET', 'POST'])
def add_employee():
    if request.method == 'POST':
        employee_id = request.form['employee_id']
        name = request.form['name']
        role = request.form['role']
        technical_skills = request.form['technical_skills']
        years_experience = request.form['years_experience']
        personality_type = request.form['personality_type']
        work_style = request.form['work_style']
        communication_style = request.form['communication_style']
        team_id = request.form['team_id']
        previous_success_percentage = request.form['previous_success_percentage']
        previous_worked_projects = request.form['previous_worked_projects']
        project_assigned = request.form['project_assigned']
        
        if employee_exists(name):
            flash(f'Warning: Employee "{name}" already exists in the database.', 'warning')
            return redirect(url_for('add_employee'))
        
        db = get_db()
        db.execute('INSERT INTO employees (employee_id,team_id,name, role, technical_skills, years_experience, personality_type, work_style, communication_style,previous_success_percentage,previous_worked_projects,project_assigned) VALUES (?,?,?,?,?,?, ?, ?, ?, ?, ?, ?)',
                   [employee_id,team_id,name, role, technical_skills, years_experience, personality_type, work_style, communication_style,previous_success_percentage,previous_worked_projects,project_assigned])
        db.commit()
        flash(f'Employee "{name}" added successfully.', 'success')
        return redirect(url_for('home'))
    return render_template('add_employee.html')
@app.route('/remove_employee/<employee_id>', methods=['POST'])
def remove_employee(employee_id):
    db = get_db()
    db.execute('DELETE FROM employees WHERE employee_id = ?', [employee_id])
    db.commit()
    flash(f'Employee with ID "{employee_id}" has been removed.', 'success')
    return redirect(url_for('home'))

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload_excel', methods=['POST'])
def upload_excel():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file and allowed_file(file.filename):
        try:
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            df = pd.read_excel(file_path)
            db = get_db()
            
            existing_employees = []
            new_employees = []
            
            for _, row in df.iterrows():
                if employee_exists(row['name']):
                    existing_employees.append(row['name'])
                else:
                    new_employees.append(tuple(row))
            
            if new_employees:
                db.executemany('INSERT INTO employees (employee_id,team_id,name, role, technical_skills, years_experience, personality_type, work_style, communication_style,previous_success_percentage,previous_worked_projects,project_assigned) VALUES (?,?,?,?,?,?, ?, ?, ?, ?, ?, ?)', new_employees)
                db.commit()
            
            os.remove(file_path)
            
            message = f'{len(new_employees)} new employees added successfully. '
            if existing_employees:
                message += f'{len(existing_employees)} employees already exist in the database: {", ".join(existing_employees)}'
            
            return jsonify({'message': message}), 200
        except Exception as e:
            return jsonify({'error': f'Error processing file: {str(e)}'}), 500
    else:
        return jsonify({'error': 'File type not allowed'}), 400

if __name__ == '__main__':
    app.run(debug=True)
