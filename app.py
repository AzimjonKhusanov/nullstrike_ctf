import sqlite3, os
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from functools import wraps
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.urandom(24)
DB = 'ctf.db'

# ─── DB ───────────────────────────────────────────────────────────────────────

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db: db.close()

def init_db():
    db = sqlite3.connect(DB)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS competitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            flag TEXT NOT NULL,
            points INTEGER DEFAULT 100,
            category TEXT DEFAULT 'misc',
            hints TEXT DEFAULT '',
            type TEXT NOT NULL CHECK(type IN ('competition','practice')),
            competition_id INTEGER REFERENCES competitions(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            task_id INTEGER REFERENCES tasks(id),
            correct INTEGER DEFAULT 0,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, task_id)
        );
        CREATE TABLE IF NOT EXISTS participants (
            user_id INTEGER REFERENCES users(id),
            competition_id INTEGER REFERENCES competitions(id),
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_id, competition_id)
        );
    """)
    # default admin
    try:
        db.execute("INSERT INTO users(username,password,role) VALUES(?,?,?)",
                   ('admin','admin','admin'))
    except: pass
    db.commit()
    db.close()

# ─── AUTH HELPERS ─────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') != 'admin':
            flash('Admin access required.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

# ─── ROUTES: AUTH ─────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        u, p = request.form.get('username','').strip(), request.form.get('password','')
        if not u or not p:
            flash('Username and password required.', 'error')
        else:
            try:
                get_db().execute("INSERT INTO users(username,password) VALUES(?,?)", (u, p))
                get_db().commit()
                flash('Registered! Please login.', 'success')
                return redirect(url_for('login'))
            except:
                flash('Username already taken.', 'error')
    return render_template('auth.html', mode='register')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        u, p = request.form.get('username','').strip(), request.form.get('password','')
        row = get_db().execute("SELECT * FROM users WHERE username=? AND password=?", (u,p)).fetchone()
        if row:
            session['user_id'] = row['id']
            session['username'] = row['username']
            session['role'] = row['role']
            return redirect(url_for('dashboard'))
        flash('Invalid credentials.', 'error')
    return render_template('auth.html', mode='login')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ─── ROUTES: DASHBOARD ────────────────────────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    competitions = db.execute("SELECT * FROM competitions ORDER BY created_at DESC").fetchall()
    practice_count = db.execute("SELECT COUNT(*) FROM tasks WHERE type='practice'").fetchone()[0]
    solved = db.execute("SELECT COUNT(*) FROM submissions WHERE user_id=? AND correct=1",
                        (session['user_id'],)).fetchone()[0]
    return render_template('dashboard.html', competitions=competitions,
                           practice_count=practice_count, solved=solved)

# ─── ROUTES: COMPETITIONS ─────────────────────────────────────────────────────

@app.route('/competition/<int:cid>')
@login_required
def competition(cid):
    db = get_db()
    comp = db.execute("SELECT * FROM competitions WHERE id=?", (cid,)).fetchone()
    if not comp: flash('Not found.','error'); return redirect(url_for('dashboard'))
    
    joined = db.execute("SELECT 1 FROM participants WHERE user_id=? AND competition_id=?",
                        (session['user_id'], cid)).fetchone()
    tasks = []
    if comp['status'] == 'active' and joined:
        tasks = db.execute(
            """SELECT t.*, 
               CASE WHEN s.correct=1 THEN 1 ELSE 0 END as solved
               FROM tasks t
               LEFT JOIN submissions s ON s.task_id=t.id AND s.user_id=?
               WHERE t.type='competition' AND t.competition_id=?""",
            (session['user_id'], cid)).fetchall()
    
    scoreboard = db.execute(
        """SELECT u.username, SUM(t.points) as total
           FROM submissions s
           JOIN users u ON u.id=s.user_id
           JOIN tasks t ON t.id=s.task_id
           WHERE s.correct=1 AND t.competition_id=?
           GROUP BY u.id ORDER BY total DESC LIMIT 20""", (cid,)).fetchall()
    
    return render_template('competition.html', comp=comp, tasks=tasks,
                           joined=joined, scoreboard=scoreboard)

@app.route('/competition/<int:cid>/join', methods=['POST'])
@login_required
def join_competition(cid):
    db = get_db()
    comp = db.execute("SELECT * FROM competitions WHERE id=?", (cid,)).fetchone()
    if comp and comp['status'] == 'active':
        try:
            db.execute("INSERT INTO participants(user_id,competition_id) VALUES(?,?)",
                       (session['user_id'], cid))
            db.commit()
            flash('Joined competition!', 'success')
        except: flash('Already joined.', 'info')
    else:
        flash('Competition not active.', 'error')
    return redirect(url_for('competition', cid=cid))

# ─── ROUTES: TASKS ────────────────────────────────────────────────────────────

@app.route('/practice')
@login_required
def practice():
    db = get_db()
    tasks = db.execute(
        """SELECT t.*, 
           CASE WHEN s.correct=1 THEN 1 ELSE 0 END as solved
           FROM tasks t
           LEFT JOIN submissions s ON s.task_id=t.id AND s.user_id=?
           WHERE t.type='practice'""", (session['user_id'],)).fetchall()
    return render_template('practice.html', tasks=tasks)

@app.route('/task/<int:tid>', methods=['GET','POST'])
@login_required
def task(tid):
    db = get_db()
    t = db.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    if not t: flash('Not found.','error'); return redirect(url_for('dashboard'))
    
    # Access control
    if t['type'] == 'competition':
        comp = db.execute("SELECT * FROM competitions WHERE id=?", (t['competition_id'],)).fetchone()
        if not comp or comp['status'] != 'active':
            flash('Competition not active.', 'error'); return redirect(url_for('dashboard'))
        joined = db.execute("SELECT 1 FROM participants WHERE user_id=? AND competition_id=?",
                            (session['user_id'], t['competition_id'])).fetchone()
        if not joined and session.get('role') != 'admin':
            flash('Join the competition first.', 'error')
            return redirect(url_for('competition', cid=t['competition_id']))
    
    solved = db.execute("SELECT correct FROM submissions WHERE user_id=? AND task_id=?",
                        (session['user_id'], tid)).fetchone()
    
    if request.method == 'POST' and not (solved and solved['correct']):
        flag = request.form.get('flag','').strip()
        if flag == t['flag']:
            try:
                db.execute("INSERT INTO submissions(user_id,task_id,correct) VALUES(?,?,1)",
                           (session['user_id'], tid))
                db.commit()
                flash(f'Correct! +{t["points"]} points', 'success')
            except:
                db.execute("UPDATE submissions SET correct=1 WHERE user_id=? AND task_id=?",
                           (session['user_id'], tid))
                db.commit()
                flash(f'Correct! +{t["points"]} points', 'success')
            solved = {'correct': 1}
        else:
            db.execute("INSERT OR IGNORE INTO submissions(user_id,task_id,correct) VALUES(?,?,0)",
                       (session['user_id'], tid))
            db.commit()
            flash('Wrong flag. Try again!', 'error')
    
    hints = [h for h in t['hints'].split('|||') if h.strip()] if t['hints'] else []
    back = url_for('competition', cid=t['competition_id']) if t['type']=='competition' else url_for('practice')
    return render_template('task.html', task=t, solved=solved, hints=hints, back=back)

# ─── ROUTES: ADMIN ────────────────────────────────────────────────────────────

@app.route('/admin')
@login_required
@admin_required
def admin():
    db = get_db()
    competitions = db.execute("SELECT c.*, COUNT(DISTINCT p.user_id) as participants FROM competitions c LEFT JOIN participants p ON p.competition_id=c.id GROUP BY c.id ORDER BY c.created_at DESC").fetchall()
    comp_tasks = db.execute("SELECT t.*, c.name as comp_name FROM tasks t LEFT JOIN competitions c ON c.id=t.competition_id WHERE t.type='competition' ORDER BY t.created_at DESC").fetchall()
    prac_tasks = db.execute("SELECT * FROM tasks WHERE type='practice' ORDER BY created_at DESC").fetchall()
    users = db.execute("SELECT u.*, COUNT(s.id) as solves FROM users u LEFT JOIN submissions s ON s.user_id=u.id AND s.correct=1 GROUP BY u.id ORDER BY u.created_at DESC").fetchall()
    return render_template('admin.html', competitions=competitions,
                           comp_tasks=comp_tasks, prac_tasks=prac_tasks, users=users)

# Competition management
@app.route('/admin/competition/create', methods=['POST'])
@login_required
@admin_required
def create_competition():
    name = request.form.get('name','').strip()
    desc = request.form.get('description','').strip()
    if not name: flash('Name required.','error')
    else:
        get_db().execute("INSERT INTO competitions(name,description) VALUES(?,?)", (name, desc))
        get_db().commit()
        flash('Competition created.','success')
    return redirect(url_for('admin'))

@app.route('/admin/competition/<int:cid>/status', methods=['POST'])
@login_required
@admin_required
def set_competition_status(cid):
    status = request.form.get('status')
    if status in ('pending','active','ended'):
        get_db().execute("UPDATE competitions SET status=? WHERE id=?", (status, cid))
        get_db().commit()
        flash(f'Competition set to {status}.','success')
    return redirect(url_for('admin'))

@app.route('/admin/competition/<int:cid>/delete', methods=['POST'])
@login_required
@admin_required
def delete_competition(cid):
    get_db().execute("DELETE FROM competitions WHERE id=?", (cid,))
    get_db().commit()
    flash('Competition deleted.','success')
    return redirect(url_for('admin'))

# Task management
@app.route('/admin/task/create', methods=['POST'])
@login_required
@admin_required
def create_task():
    f = request.form
    task_type = f.get('type')
    if task_type not in ('competition','practice'):
        flash('Invalid task type.','error'); return redirect(url_for('admin'))
    
    comp_id = f.get('competition_id') if task_type == 'competition' else None
    if task_type == 'competition' and not comp_id:
        flash('Competition required for competition tasks.','error'); return redirect(url_for('admin'))
    
    hints = '|||'.join([h.strip() for h in f.get('hints','').split('\n') if h.strip()])
    try:
        pts = int(f.get('points', 100))
    except: pts = 100
    
    get_db().execute(
        "INSERT INTO tasks(title,description,flag,points,category,hints,type,competition_id) VALUES(?,?,?,?,?,?,?,?)",
        (f.get('title','').strip(), f.get('description','').strip(),
         f.get('flag','').strip(), pts, f.get('category','misc').strip(),
         hints, task_type, comp_id))
    get_db().commit()
    flash('Task created.','success')
    return redirect(url_for('admin'))

@app.route('/admin/task/<int:tid>/edit', methods=['GET','POST'])
@login_required
@admin_required
def edit_task(tid):
    db = get_db()
    t = db.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    if not t: flash('Not found.','error'); return redirect(url_for('admin'))
    
    if request.method == 'POST':
        f = request.form
        hints = '|||'.join([h.strip() for h in f.get('hints','').split('\n') if h.strip()])
        try: pts = int(f.get('points', t['points']))
        except: pts = t['points']
        db.execute(
            "UPDATE tasks SET title=?,description=?,flag=?,points=?,category=?,hints=? WHERE id=?",
            (f.get('title','').strip(), f.get('description','').strip(),
             f.get('flag','').strip(), pts, f.get('category','misc').strip(),
             hints, tid))
        db.commit()
        flash('Task updated.','success')
        return redirect(url_for('admin'))
    
    competitions = db.execute("SELECT * FROM competitions").fetchall()
    hints_str = '\n'.join([h for h in t['hints'].split('|||') if h]) if t['hints'] else ''
    return render_template('edit_task.html', task=t, competitions=competitions, hints_str=hints_str)

@app.route('/admin/task/<int:tid>/delete', methods=['POST'])
@login_required
@admin_required
def delete_task(tid):
    get_db().execute("DELETE FROM tasks WHERE id=?", (tid,))
    get_db().commit()
    flash('Task deleted.','success')
    return redirect(url_for('admin'))

@app.route('/scoreboard')
@login_required
def scoreboard():
    db = get_db()
    # Global: total points across all correct submissions
    global_board = db.execute("""
        SELECT u.username, SUM(t.points) as total, COUNT(s.id) as solves
        FROM submissions s
        JOIN users u ON u.id = s.user_id
        JOIN tasks t ON t.id = s.task_id
        WHERE s.correct = 1
        GROUP BY u.id
        ORDER BY total DESC, solves ASC
        LIMIT 50
    """).fetchall()

    # Per-competition boards
    competitions = db.execute("SELECT * FROM competitions WHERE status IN ('active','ended') ORDER BY created_at DESC").fetchall()
    comp_boards = {}
    for c in competitions:
        comp_boards[c['id']] = db.execute("""
            SELECT u.username, SUM(t.points) as total, COUNT(s.id) as solves
            FROM submissions s
            JOIN users u ON u.id = s.user_id
            JOIN tasks t ON t.id = s.task_id
            WHERE s.correct = 1 AND t.competition_id = ?
            GROUP BY u.id
            ORDER BY total DESC
            LIMIT 10
        """, (c['id'],)).fetchall()

    # Practice board
    practice_board = db.execute("""
        SELECT u.username, SUM(t.points) as total, COUNT(s.id) as solves
        FROM submissions s
        JOIN users u ON u.id = s.user_id
        JOIN tasks t ON t.id = s.task_id
        WHERE s.correct = 1 AND t.type = 'practice'
        GROUP BY u.id
        ORDER BY total DESC
        LIMIT 20
    """).fetchall()

    return render_template('scoreboard.html',
        global_board=global_board,
        competitions=competitions,
        comp_boards=comp_boards,
        practice_board=practice_board)

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
