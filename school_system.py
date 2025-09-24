# school_system.py
"""
Trixie High School - Integrated Tkinter + Flask single-file system
Features:
 - CLI: --dev / --prod --port --host
 - Web: Flask app at / (login), role-based pages
 - Desktop: Tkinter admin UI
 - Users persisted to users.json, logs to logs/logs.json with term rotation/archives
 - Startup/shutdown logs & console summary
"""

import os, sys, json, random, string, hashlib, threading, csv, datetime, time, signal, atexit, argparse
from functools import wraps

# Flask imports
from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify, send_file

# Tkinter imports
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# ---------------- CONFIG ----------------
TOTAL_TEACHERS = 44
MAX_LESSONS_PER_WEEK = 28
USERS_FILE = "users.json"
LOG_DIR = "logs"
LOGS_FILE = os.path.join(LOG_DIR, "logs.json")
LOG_ARCHIVE_THRESHOLD = 2000  # fallback auto-archive size
SECRET_KEY = os.environ.get("SCHOOL_SECRET_KEY") or hashlib.sha256(str(random.random()).encode()).hexdigest()

FIRST_NAMES = ["John","Jane","Michael","Sarah","David","Emma","James","Olivia","Robert","Sophia",
               "William","Isabella","Joseph","Ava","Charles","Mia","Thomas","Charlotte","Christopher","Amelia",
               "Daniel","Harper","Matthew","Evelyn","Anthony","Abigail","Mark","Emily","Donald","Elizabeth",
               "Steven","Sofia","Paul","Avery","Andrew","Ella","Joshua","Scarlett","Kenneth","Victoria"]
LAST_NAMES = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Rodriguez","Martinez",
              "Hernandez","Lopez","Gonzalez","Wilson","Anderson","Thomas","Taylor","Moore","Jackson","Martin",
              "Lee","Perez","Thompson","White","Harris","Sanchez","Clark","Ramirez","Lewis","Robinson"]
SUBJECTS = [
    "Mathematics","English","Kiswahili","Biology","Chemistry","Physics",
    "History","Geography","Business Studies","Computer Science","CRE","Agriculture","Art"
]

PERIODS = [
    ("07:20-08:00","Lesson"),
    ("08:00-08:20","Short Break"),
    ("08:20-09:00","Lesson"),
    ("09:00-09:40","Lesson"),
    ("09:40-10:20","Lesson"),
    ("10:20-10:50","Lesson"),
    ("10:50-11:10","Tea Break"),
    ("11:10-11:50","Lesson"),
    ("11:50-12:30","Lesson"),
    ("12:30-13:00","Lesson"),
    ("13:00-13:30","Lunch Break"),
    ("13:30-14:10","Lesson"),
    ("14:10-14:50","Lesson"),
    ("14:50-15:30","Lesson"),
    ("15:30-16:00","Lesson"),
    ("16:00-17:00","Games"),
    ("17:00-18:00","Remedial (Tuition)"),
    ("18:00-19:00","Supper"),
    ("19:00-21:35","Prep (Self Reading)"),
]
DAYS = ["Monday","Tuesday","Wednesday","Thursday","Friday"]

# grading
GRADE_BOUNDARIES = [
    (80,100,"A",12),(75,79,"A-",11),(70,74,"B+",10),(65,69,"B",9),
    (60,64,"B-",8),(55,59,"C+",7),(50,54,"C",6),(45,49,"C-",5),
    (40,44,"D+",4),(35,39,"D-",3),(30,34,"D",2),(0,29,"E",1)
]
MEAN_GRADE_SCALE = [
    (79,100,"A"),(73,78,"A-"),(66,72,"B+"),(59,65,"B"),
    (53,58,"B-"),(46,52,"C+"),(40,45,"C"),(35,39,"D+"),
    (30,34,"D"),(0,29,"E")
]

# ---------------- Utilities ----------------
def now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log_term_year(dt=None):
    # returns tuple (year, term) where term 1/2/3 by month mapping
    if dt is None:
        dt = datetime.datetime.now()
    m = dt.month
    year = dt.year
    if 1 <= m <= 4:
        term = 1
    elif 5 <= m <= 8:
        term = 2
    else:
        term = 3
    return year, term

def ensure_log_dir():
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

def hash_password(password, salt=None):
    if salt is None:
        salt = ''.join(random.choices(string.ascii_letters+string.digits, k=12))
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${h}"

def verify_password(stored, password):
    try:
        salt, h = stored.split("$",1)
        return hashlib.sha256((salt + password).encode()).hexdigest() == h
    except Exception:
        return False

# ---------------- Logs management ----------------
def load_logs_file(path=LOGS_FILE):
    ensure_log_dir()
    if not os.path.exists(path):
        return []
    try:
        with open(path,"r",encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_logs_file(logs, path=LOGS_FILE):
    ensure_log_dir()
    with open(path,"w",encoding="utf-8") as f:
        json.dump(logs, f, indent=2)

def append_log(user, role, action):
    ensure_log_dir()
    logs = load_logs_file()
    logs.append({"time": now_str(), "user": user, "role": role, "action": action})
    # auto-archive if huge
    if len(logs) > LOG_ARCHIVE_THRESHOLD:
        rotate_logs(force=True)
        logs = []
    save_logs_file(logs)

def list_archives():
    ensure_log_dir()
    arr = []
    for fname in os.listdir(LOG_DIR):
        if fname.startswith("logs_") and fname.endswith(".json"):
            arr.append(fname)
    arr.sort(reverse=True)
    return arr

def rotate_logs(force=False):
    """
    Rotate logs if current term/year differs from last archive's term/year
    or when force=True.
    """
    ensure_log_dir()
    current_logs = load_logs_file()
    if not current_logs and not force:
        return
    year, term = log_term_year()
    # target name
    archive_name = f"logs_{year}_Term{term}.json"
    archive_path = os.path.join(LOG_DIR, archive_name)
    # If a same-term archive exists, append timestamp to avoid overwrite
    if os.path.exists(archive_path) and not force:
        # do not rotate
        return
    # move current logs to archive with timestamp to avoid overwriting same term archive
    ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    archive_path = os.path.join(LOG_DIR, f"logs_{year}_Term{term}_{ts}.json")
    try:
        with open(archive_path, "w", encoding="utf-8") as f:
            json.dump(current_logs, f, indent=2)
        # clear current logs
        save_logs_file([], LOGS_FILE)
    except Exception as e:
        print("Log rotation failed:", e)

def filter_logs(user=None, action=None, start=None, end=None, path=LOGS_FILE):
    logs = load_logs_file(path)
    def in_range(tstr):
        if not start and not end: return True
        try:
            dt = datetime.datetime.strptime(tstr, "%Y-%m-%d %H:%M:%S")
        except:
            return True
        if start and dt < start: return False
        if end and dt > end: return False
        return True
    out=[]
    for e in logs:
        if user and e.get("user") != user: continue
        if action and action.lower() not in e.get("action","").lower(): continue
        if not in_range(e.get("time","")): continue
        out.append(e)
    return out

# ---------------- Model classes ----------------
class Student:
    def __init__(self, name, form, stream, admission_no):
        self.name = name
        self.form = form
        self.stream = stream
        self.admission_no = admission_no
        self.results = {}  # term -> exam -> subj -> (mark, grade, pts)

class Teacher:
    def __init__(self, name, subject, teacher_id, class_assigned=None):
        self.name = name
        self.subject = subject
        self.teacher_id = teacher_id
        self.class_assigned = class_assigned
        self.schedule = set()
        self.max_lessons = MAX_LESSONS_PER_WEEK
    def lesson_count(self):
        return len(self.schedule)

class Staff:
    def __init__(self,name,role,department):
        self.name = name
        self.role = role
        self.department = department

# ---------------- School core ----------------
def generate_teacher_id(name, existing):
    first = name.strip().split()[0].upper()[:3].ljust(3,'X')
    while True:
        num = f"{random.randint(0,99):02d}"
        letters = ''.join(random.choices(string.ascii_uppercase, k=2))
        tid = f"{first}{num}{letters}"
        if tid not in existing:
            existing.add(tid)
            return tid

def grade_subject(mark):
    for low,high,g,pts in GRADE_BOUNDARIES:
        if low <= mark <= high:
            return g, pts
    return "E", 1

def map_mean_to_grade(value):
    for low,high,g in MEAN_GRADE_SCALE:
        if low <= value <= high:
            return g
    return "E"

class School:
    def __init__(self, name, principal, deputy):
        self.name = name
        self.principal = principal
        self.deputy = deputy
        self.students = []
        self.teachers = []
        self.staff = []
        self.timetable = {}  # class_name -> day -> slot -> value
        self.working_hours = "07:20hrs to 21:35hrs"

    def generate_students(self):
        forms = [4,3,2,1]  # start from form 4 for admission ascending
        streams = ["Rangers","Trailblazers","Horizon","Elites"]
        adm = 9990
        for form in forms:
            for stream in streams:
                for _ in range(30):
                    name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
                    self.students.append(Student(name, form, stream, adm))
                    adm += 1

    def generate_teachers(self, total=TOTAL_TEACHERS):
        existing = set()
        forms = [1,2,3,4]
        streams = ["Rangers","Trailblazers","Horizon","Elites"]
        # assign class teachers first (16)
        for f in forms:
            for st in streams:
                name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
                subject = random.choice(SUBJECTS)
                tid = generate_teacher_id(name, existing)
                self.teachers.append(Teacher(name, subject, tid, class_assigned=f"Form {f} {st}"))
        # additional subject teachers
        while len(self.teachers) < total:
            name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
            subject = random.choice(SUBJECTS)
            tid = generate_teacher_id(name, existing)
            self.teachers.append(Teacher(name, subject, tid))

    def generate_staff(self):
        roles=[("Cook",3,"Kitchen"),("Cateress",1,"Kitchen"),("Librarian",2,"Library"),("Security Officer",5,"Security")]
        for r,cnt,dept in roles:
            for _ in range(cnt):
                name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
                self.staff.append(Staff(name,r,dept))

    def generate_timetable(self):
        class_names = [f"Form {f} {st}" for f in [1,2,3,4] for st in ["Rangers","Trailblazers","Horizon","Elites"]]
        # initialize
        for cname in class_names:
            self.timetable[cname] = {}
            for day in DAYS:
                self.timetable[cname][day] = {}
                for slot,_ in PERIODS:
                    self.timetable[cname][day][slot] = None
        subj_map = {s:[t for t in self.teachers if t.subject==s] for s in SUBJECTS}
        all_teachers = self.teachers[:]
        def choose_teacher(subject, day, slot):
            cand = subj_map.get(subject, [])[:]
            random.shuffle(cand)
            for t in cand:
                if (day,slot) in t.schedule: continue
                if t.lesson_count() < t.max_lessons:
                    return t
            free = [t for t in all_teachers if (day,slot) not in t.schedule]
            if not free:
                return random.choice(all_teachers)
            free.sort(key=lambda x: x.lesson_count())
            return free[0]
        for cname in class_names:
            core = ["Mathematics","English","Kiswahili","Biology","Chemistry","Physics"]
            weighted = core*3 + [s for s in SUBJECTS if s not in core]
            for day in DAYS:
                for slot,typ in PERIODS:
                    if typ != "Lesson":
                        self.timetable[cname][day][slot] = typ
                        continue
                    subj = random.choice(weighted)
                    t = choose_teacher(subj, day, slot)
                    t.schedule.add((day,slot))
                    self.timetable[cname][day][slot] = f"{subj} ({t.teacher_id})"

    def generate_exam_results(self, low=40, high=95):
        for s in self.students:
            s.results = {}
            for term in range(1,4):
                s.results[term] = {}
                for exam in ["CAT 1","CAT 2"]:
                    s.results[term][exam] = {}
                    if s.form >= 3:
                        core = ["Mathematics","English","Kiswahili","Biology","Chemistry","Physics"]
                        electives = random.sample([x for x in SUBJECTS if x not in core],2)
                        taken = core + electives
                    else:
                        taken = SUBJECTS[:]
                    for subj in taken:
                        m = random.randint(low, high)
                        g, pts = grade_subject(m)
                        s.results[term][exam][subj] = (m, g, pts)

    def _best_exam_for_student(self, s):
        terms = sorted(list(s.results.keys()))
        if not terms: return None, None, None
        latest = terms[-1]
        ex = s.results.get(latest, {})
        if "CAT 2" in ex and ex["CAT 2"]: return ex["CAT 2"], latest, "CAT 2"
        if "CAT 1" in ex and ex["CAT 1"]: return ex["CAT 1"], latest, "CAT 1"
        for t in reversed(terms):
            for ename, emap in s.results[t].items():
                if emap:
                    return emap, t, ename
        return None, None, None

    def calculate_overall_grade(self, student):
        exam, term, ename = self._best_exam_for_student(student)
        if not exam: return 0.0, "N/A", 0
        marks=[]; pts=[]
        for subj, (m,g,p) in exam.items():
            marks.append(m); pts.append(p)
        sum_pts = sum(pts)
        if student.form in [1,2]:
            avg = sum(marks)/max(1,len(marks))
            return avg, map_mean_to_grade(avg), sum_pts
        else:
            return sum_pts, map_mean_to_grade(sum_pts), sum_pts

    def find_student_by_adm(self, adm):
        for s in self.students:
            if s.admission_no == adm:
                return s
        return None

    def find_students_by_name(self, q):
        q = q.strip().lower()
        return [s for s in self.students if q in s.name.lower()]

    def find_teacher_by_id(self, tid):
        for t in self.teachers:
            if t.teacher_id == tid:
                return t
        return None

# ---------------- Users management ----------------
def load_users():
    if not os.path.exists(USERS_FILE):
        users = {
            "admin": {"password": hash_password("admin123"), "role": "admin"},
            "deputy": {"password": hash_password("deputy123"), "role": "admin"},
            "teacher1": {"password": hash_password("teach123"), "role":"teacher"}
        }
        with open(USERS_FILE,"w",encoding="utf-8") as f:
            json.dump(users,f,indent=2)
        return users
    try:
        with open(USERS_FILE,"r",encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_users(users):
    with open(USERS_FILE,"w",encoding="utf-8") as f:
        json.dump(users,f,indent=2)

USERS = load_users()

# ---------------- Flask app ----------------
flask_app = Flask(__name__)
flask_app.secret_key = SECRET_KEY

def login_required(f):
    @wraps(f)
    def inner(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return inner

def role_required(roles):
    def deco(f):
        @wraps(f)
        def inner(*args, **kwargs):
            u = session.get("user")
            if not u or u.get("role") not in roles:
                return render_template_string(BASE_HTML, navbar=build_navbar(), content="<div class='alert alert-danger'>Permission denied.</div>")
            return f(*args, **kwargs)
        return inner
    return deco

def build_navbar():
    u = session.get("user")
    user_html = f"Logged in as {u['username']} ({u['role']})" if u else ""
    auth_btn = "<a class='btn btn-outline-light' href='/logout'>Logout</a>" if u else "<a class='btn btn-outline-light' href='/login'>Login</a>"
    return f"""
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary mb-4">
      <div class="container-fluid">
        <a class="navbar-brand" href="/">TRIXIE HIGH SCHOOL</a>
        <div class="collapse navbar-collapse" id="navbars">
          <ul class="navbar-nav me-auto mb-2 mb-lg-0">
            <li class="nav-item"><a class="nav-link" href="/overview">Overview</a></li>
            <li class="nav-item"><a class="nav-link" href="/students">Students</a></li>
            <li class="nav-item"><a class="nav-link" href="/teachers">Teachers</a></li>
            <li class="nav-item"><a class="nav-link" href="/staff">Staff</a></li>
            <li class="nav-item"><a class="nav-link" href="/timetable">Timetable</a></li>
            <li class="nav-item dropdown">
              <a class="nav-link dropdown-toggle" href="#" data-bs-toggle="dropdown">Results</a>
              <ul class="dropdown-menu">
                <li><a class="dropdown-item" href="/results/1">Form 1</a></li>
                <li><a class="dropdown-item" href="/results/2">Form 2</a></li>
                <li><a class="dropdown-item" href="/results/3">Form 3</a></li>
                <li><a class="dropdown-item" href="/results/4">Form 4</a></li>
              </ul>
            </li>
          </ul>
          <span class="navbar-text text-white me-3">{user_html}</span>
          <form class="d-flex me-2" action="/student/search" method="get">
            <input class="form-control me-2" name="name" placeholder="Search student name">
            <button class="btn btn-outline-light" type="submit">Search</button>
          </form>
          {auth_btn}
        </div>
      </div>
    </nav>
    """

BASE_HTML = """
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TRIXIE HIGH SCHOOL</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet"></head>
<body>{{ navbar|safe }}<div class="container mt-3">{{ content|safe }}</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script></body></html>
"""

LOGIN_FORM = """
<div class="row justify-content-center"><div class="col-md-5"><h3>Login</h3>
<form method="post">
 <div class="mb-3"><label>Username</label><input class="form-control" name="username" required></div>
 <div class="mb-3"><label>Password</label><input type="password" class="form-control" name="password" required></div>
 <button class="btn btn-primary w-100" type="submit">Login</button>
</form>
<p class="mt-2 small text-muted">Admin: admin/admin123 — Students: firstname/admissionno (e.g. John/9990)</p>
</div></div>
"""

# ---------------- Flask routes ----------------
@flask_app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        uname = request.form.get("username","").strip()
        pwd = request.form.get("password","")
        user = USERS.get(uname)
        if user and verify_password(user["password"], pwd):
            session["user"] = {"username": uname, "role": user.get("role","teacher")}
            # attach teacher_id if present in USERS
            if isinstance(user, dict) and user.get("teacher_id"):
                session["teacher_id"] = user.get("teacher_id")
            log_action = f"Logged in"
            append_log(uname, user.get("role","teacher"), log_action)
            return redirect(request.args.get("next") or url_for("home"))
        # student fallback
        candidates = [s for s in school.students if s.name.split()[0].lower() == uname.lower()]
        if candidates:
            for s in candidates:
                if str(s.admission_no) == pwd:
                    session["user"] = {"username": uname, "role": "student", "adm": s.admission_no}
                    append_log(uname, "student", f"Student logged in (adm:{s.admission_no})")
                    return redirect(url_for("my_results"))
        return render_template_string(BASE_HTML, navbar=build_navbar(), content="<div class='alert alert-danger'>Invalid credentials</div>" + LOGIN_FORM)
    return render_template_string(BASE_HTML, navbar=build_navbar(), content=LOGIN_FORM)

@flask_app.route("/logout")
@login_required
def logout():
    u = session.get("user",{}).get("username","")
    r = session.get("user",{}).get("role","")
    session.clear()
    append_log(u, r, "Logged out")
    return redirect(url_for("login"))

@flask_app.route("/")
@login_required
def home():
    s = school
    cont = f"<div class='text-center py-4'><h1>Welcome to {s.name}</h1><p class='lead'>Principal: {s.principal} | Deputy: {s.deputy}</p></div>"
    return render_template_string(BASE_HTML, navbar=build_navbar(), content=cont)

@flask_app.route("/overview")
@login_required
def overview():
    s = school
    cont = f"<div class='card'><div class='card-body'><h4>{s.name}</h4><p>Principal: {s.principal}<br>Deputy: {s.deputy}<br>Working hours: {s.working_hours}</p></div></div>"
    return render_template_string(BASE_HTML, navbar=build_navbar(), content=cont)

@flask_app.route("/students")
@login_required
def students_page():
    u = session.get("user",{})
    rows = ""
    if u.get("role") == "teacher":
        tid = session.get("teacher_id")
        classes = set()
        if tid:
            for cname, days in school.timetable.items():
                for d in DAYS:
                    for slot, val in days[d].items():
                        if val and f"({tid})" in val:
                            classes.add(cname)
        students = [s for s in school.students if f"Form {s.form} {s.stream}" in classes] if classes else []
    elif u.get("role") == "student":
        students = [school.find_student_by_adm(u.get("adm"))] if u.get("adm") else []
    else:
        students = school.students
    for st in students:
        if not st: continue
        rows += f"<tr><td>{st.admission_no}</td><td>{st.name}</td><td>{st.form}</td><td>{st.stream}</td><td><a href='{url_for('student_by_adm', adm=st.admission_no)}'>View</a></td></tr>"
    cont = f"<h3>Students</h3><div class='table-responsive'><table class='table table-striped'><thead><tr><th>Adm</th><th>Name</th><th>Form</th><th>Stream</th><th>Action</th></tr></thead><tbody>{rows}</tbody></table></div>"
    return render_template_string(BASE_HTML, navbar=build_navbar(), content=cont)

@flask_app.route("/student/<int:adm>")
@login_required
def student_by_adm(adm):
    s = school.find_student_by_adm(adm)
    if not s:
        return render_template_string(BASE_HTML, navbar=build_navbar(), content="<div class='alert alert-warning'>No student found</div>")
    user = session.get("user",{}); role = user.get("role")
    if role == "student" and user.get("adm") != adm:
        return render_template_string(BASE_HTML, navbar=build_navbar(), content="<div class='alert alert-danger'>Permission denied</div>")
    if role == "teacher":
        tid = session.get("teacher_id")
        if tid:
            teaches = False
            for cname, days in school.timetable.items():
                if cname == f"Form {s.form} {s.stream}":
                    for d in DAYS:
                        for slot, val in days[d].items():
                            if val and f"({tid})" in val:
                                teaches = True; break
                        if teaches: break
                if teaches: break
            if not teaches:
                return render_template_string(BASE_HTML, navbar=build_navbar(), content="<div class='alert alert-danger'>Permission denied</div>")
    exam, term, ename = school._best_exam_for_student(s)
    if not exam:
        return render_template_string(BASE_HTML, navbar=build_navbar(), content=f"<h3>{s.name} ({s.admission_no})</h3><p>No exam data</p>")
    rows = "".join(f"<tr><td>{sub}</td><td>{m}</td><td>{g}</td><td>{p}</td></tr>" for sub,(m,g,p) in exam.items())
    can_edit = role in ("admin","teacher")
    edit_btn = f"<p><a class='btn btn-sm btn-primary' href='{url_for('student_marks', adm=adm)}'>Edit Marks</a></p>" if can_edit else ""
    cont = f"<h3>{s.name} ({s.admission_no}) - Form {s.form} {s.stream}</h3><h5>Latest: Term {term} - {ename}</h5><div class='table-responsive'><table class='table table-sm'><thead><tr><th>Subject</th><th>Marks</th><th>Grade</th><th>Points</th></tr></thead><tbody>{rows}</tbody></table></div>{edit_btn}"
    return render_template_string(BASE_HTML, navbar=build_navbar(), content=cont)

@flask_app.route("/student/<int:adm>/marks", methods=["GET","POST"])
@login_required
def student_marks(adm):
    s = school.find_student_by_adm(adm)
    if not s:
        return render_template_string(BASE_HTML, navbar=build_navbar(), content="<div class='alert alert-warning'>No student</div>")
    role = session.get("user",{}).get("role")
    if role not in ("admin","teacher"):
        return render_template_string(BASE_HTML, navbar=build_navbar(), content="<div class='alert alert-danger'>Permission denied</div>")
    if request.method == "GET":
        term = int(request.args.get("term", max(s.results.keys()) if s.results else 1))
        exam = request.args.get("exam","CAT 2")
        if s.form >= 3:
            core = ["Mathematics","English","Kiswahili","Biology","Chemistry","Physics"]
            electives = random.sample([x for x in SUBJECTS if x not in core],2)
            subjects = core + electives
        else:
            subjects = SUBJECTS[:]
        rows_html = ""
        for subj in subjects:
            val = ""
            if term in s.results and exam in s.results[term] and subj in s.results[term][exam]:
                val = s.results[term][exam][subj][0]
            rows_html += f"<div class='mb-2'><label>{subj}: <input name='subj__{subj}' value='{val}' /></label></div>"
        cont = f"<h3>Edit Marks - {s.name} ({s.admission_no})</h3><form method='post'><div class='mb-2'>Term: <input name='term' value='{term}'/></div><div class='mb-2'>Exam: <input name='exam' value='{exam}'/></div>{rows_html}<button class='btn btn-primary' type='submit'>Save</button></form>"
        return render_template_string(BASE_HTML, navbar=build_navbar(), content=cont)
    form = request.form
    term = int(form.get("term",1)); exam = form.get("exam","CAT 2")
    if term not in s.results: s.results[term] = {"CAT 1":{}, "CAT 2":{}}
    if exam not in s.results[term]: s.results[term][exam] = {}
    for k,v in form.items():
        if k.startswith("subj__"):
            subj = k.split("__",1)[1]; txt = v.strip()
            if not txt: continue
            try: mark = int(txt)
            except: mark = 0
            g,pts = grade_subject(mark)
            s.results[term][exam][subj] = (mark,g,pts)
    append_log(session.get("user",{}).get("username","unknown"), session.get("user",{}).get("role",""), f"Edited marks for {s.admission_no}")
    return redirect(url_for("student_by_adm", adm=adm))

@flask_app.route("/teachers")
@login_required
def teachers_page():
    u = session.get("user",{})
    rows = ""
    if u.get("role") == "teacher" and session.get("teacher_id"):
        for t in school.teachers:
            if t.teacher_id == session.get("teacher_id"):
                rows += f"<tr><td>{t.teacher_id}</td><td>{t.name}</td><td>{t.subject}</td><td>{t.class_assigned or ''}</td><td>{t.lesson_count()}</td><td><a href='{url_for('teacher_detail', tid=t.teacher_id)}'>View</a></td></tr>"
    else:
        for t in school.teachers:
            rows += f"<tr><td>{t.teacher_id}</td><td>{t.name}</td><td>{t.subject}</td><td>{t.class_assigned or ''}</td><td>{t.lesson_count()}</td><td><a href='{url_for('teacher_detail', tid=t.teacher_id)}'>View</a></td></tr>"
    cont = f"<h3>Teachers</h3><div class='table-responsive'><table class='table table-hover table-sm'><thead><tr><th>ID</th><th>Name</th><th>Subject</th><th>Class</th><th>Lessons</th><th>Action</th></tr></thead><tbody>{rows}</tbody></table></div>"
    return render_template_string(BASE_HTML, navbar=build_navbar(), content=cont)

@flask_app.route("/teacher/<tid>")
@login_required
def teacher_detail(tid):
    t = school.find_teacher_by_id(tid)
    if not t:
        return render_template_string(BASE_HTML, navbar=build_navbar(), content="<div class='alert alert-warning'>No teacher</div>")
    u = session.get("user",{})
    if u.get("role") == "teacher" and session.get("teacher_id") != tid:
        return render_template_string(BASE_HTML, navbar=build_navbar(), content="<div class='alert alert-danger'>Permission denied</div>")
    sched = {d:{} for d in DAYS}
    for cname, days in school.timetable.items():
        for d in DAYS:
            for slot, val in days[d].items():
                if val and f"({tid})" in val:
                    subj = val.split(" (")[0]
                    sched[d][slot] = f"{cname} - {subj}"
    slots = [slot for slot,_ in PERIODS]
    header = "".join(f"<th>{s}</th>" for s in ["Day"]+slots)
    body = ""
    for d in DAYS:
        row = "".join(f"<td>{sched[d].get(slot,'')}</td>" for slot in slots)
        body += f"<tr><td><strong>{d}</strong></td>{row}</tr>"
    cont = f"<h3>{t.name} ({t.teacher_id})</h3><p>Subject: {t.subject} | Class assigned: {t.class_assigned or '—'}</p><div class='table-responsive'><table class='table table-sm'><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div>"
    return render_template_string(BASE_HTML, navbar=build_navbar(), content=cont)

@flask_app.route("/staff")
@login_required
def staff_page():
    rows = "".join(f"<tr><td>{st.name}</td><td>{st.role}</td><td>{st.department}</td></tr>" for st in school.staff)
    cont = f"<h3>Staff</h3><div class='table-responsive'><table class='table table-sm'><thead><tr><th>Name</th><th>Role</th><th>Dept</th></tr></thead><tbody>{rows}</tbody></table></div>"
    return render_template_string(BASE_HTML, navbar=build_navbar(), content=cont)

@flask_app.route("/timetable")
@login_required
def timetable_page():
    class_list = list(school.timetable.keys())
    sel = request.args.get("class", class_list[0] if class_list else "")
    slots = [slot for slot,_ in PERIODS]
    header = "".join(f"<th>{s}</th>" for s in ["Day"]+slots)
    body = ""
    if sel in school.timetable:
        for d in DAYS:
            row = "".join(f"<td>{school.timetable[sel][d].get(slot,'')}</td>" for slot in slots)
            body += f"<tr><td><strong>{d}</strong></td>{row}</tr>"
    options = "".join(f"<option value='{c}' {'selected' if c==sel else ''}>{c}</option>" for c in class_list)
    cont = f"<h3>Timetable - {sel}</h3><form method='get'><label>Select Class <select name='class' onchange='this.form.submit()'>{options}</select></label></form><div class='table-responsive'><table class='table table-sm'><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div>"
    return render_template_string(BASE_HTML, navbar=build_navbar(), content=cont)

@flask_app.route("/results/<int:form>")
@login_required
def results_page(form):
    rows=[]
    u = session.get("user",{})
    for s in school.students:
        if s.form != form: continue
        if u.get("role") == "teacher":
            tid = session.get("teacher_id")
            allowed = False
            if tid:
                for cname, days in school.timetable.items():
                    if cname == f"Form {s.form} {s.stream}":
                        for d in DAYS:
                            for slot, val in days[d].items():
                                if val and f"({tid})" in val:
                                    allowed = True; break
                            if allowed: break
                    if allowed: break
            if not allowed: continue
        score, grade, _ = school.calculate_overall_grade(s)
        rows.append((score, s.admission_no, s.name, grade))
    rows.sort(key=lambda x: x[0], reverse=True)
    body = "".join(f"<tr><td>{i+1}</td><td>{adm}</td><td>{name}</td><td>{score:.2f}</td><td>{gr}</td></tr>" for i,(score,adm,name,gr) in enumerate(rows))
    cont = f"<h3>Form {form} Rankings</h3><div class='table-responsive'><table class='table table-sm'><thead><tr><th>Rank</th><th>Adm</th><th>Name</th><th>Score</th><th>Grade</th></tr></thead><tbody>{body}</tbody></table></div>"
    return render_template_string(BASE_HTML, navbar=build_navbar(), content=cont)

@flask_app.route("/my-results")
@login_required
def my_results():
    u = session.get("user",{})
    if u.get("role") != "student":
        return redirect(url_for("home"))
    adm = u.get("adm")
    return redirect(url_for("student_by_adm", adm=adm))

@flask_app.route("/register", methods=["GET","POST"])
@login_required
@role_required(["admin"])
def register():
    if request.method == "GET":
        form = """
        <h3>Create User (admin only)</h3>
        <form method='post'>
         <div class='mb-2'>Username: <input name='username'/></div>
         <div class='mb-2'>Password: <input name='password'/></div>
         <div class='mb-2'>Role: <select name='role'><option value='teacher'>teacher</option><option value='staff'>staff</option><option value='admin'>admin</option></select></div>
         <button class='btn btn-primary' type='submit'>Create</button>
        </form>
        """
        return render_template_string(BASE_HTML, navbar=build_navbar(), content=form)
    uname = request.form.get("username","").strip()
    pwd = request.form.get("password","")
    role = request.form.get("role","teacher")
    if not uname or not pwd:
        return render_template_string(BASE_HTML, navbar=build_navbar(), content="<div class='alert alert-danger'>Missing fields</div>")
    if uname in USERS:
        return render_template_string(BASE_HTML, navbar=build_navbar(), content="<div class='alert alert-warning'>User exists</div>")
    USERS[uname] = {"password": hash_password(pwd), "role": role}
    save_users(USERS)
    append_log(session.get("user",{}).get("username","admin"), "admin", f"Created user {uname} role={role}")
    return render_template_string(BASE_HTML, navbar=build_navbar(), content=f"<div class='alert alert-success'>User {uname} created</div>")

@flask_app.route("/change-password", methods=["GET","POST"])
@login_required
def change_password():
    u = session.get("user",{})
    uname = u.get("username")
    role = u.get("role")
    if request.method == "GET":
        form = """
        <h3>Change Password</h3>
        <form method='post'>
         <div class='mb-2'>Current Password: <input name='current' type='password'/></div>
         <div class='mb-2'>New Password: <input name='new' type='password'/></div>
         <button class='btn btn-primary' type='submit'>Change</button>
        </form>
        """
        return render_template_string(BASE_HTML, navbar=build_navbar(), content=form)
    cur = request.form.get("current","")
    new = request.form.get("new","")
    if role == "student":
        adm = u.get("adm")
        if not (str(adm) == cur or (uname in USERS and verify_password(USERS[uname]["password"], cur))):
            return render_template_string(BASE_HTML, navbar=build_navbar(), content="<div class='alert alert-danger'>Current password incorrect</div>")
        USERS[uname] = {"password": hash_password(new), "role":"student"}
        save_users(USERS)
        append_log(uname, "student", "Changed password")
        return render_template_string(BASE_HTML, navbar=build_navbar(), content="<div class='alert alert-success'>Password changed</div>")
    else:
        if uname not in USERS or not verify_password(USERS[uname]["password"], cur):
            return render_template_string(BASE_HTML, navbar=build_navbar(), content="<div class='alert alert-danger'>Current password incorrect</div>")
        USERS[uname]["password"] = hash_password(new)
        save_users(USERS)
        append_log(uname, role, "Changed password")
        return render_template_string(BASE_HTML, navbar=build_navbar(), content="<div class='alert alert-success'>Password changed</div>")

@flask_app.route("/logs")
@login_required
@role_required(["admin"])
def logs_page():
    user = request.args.get("user","")
    action = request.args.get("action","")
    start_raw = request.args.get("start","")
    end_raw = request.args.get("end","")
    start = end = None
    fmt = "%Y-%m-%d"
    try:
        if start_raw: start = datetime.datetime.strptime(start_raw, fmt)
        if end_raw: end = datetime.datetime.strptime(end_raw, fmt) + datetime.timedelta(days=1)
    except:
        start = end = None
    logs = filter_logs(user=user if user else None, action=action if action else None, start=start, end=end)
    rows = "".join(f"<tr><td>{e['time']}</td><td>{e['user']}</td><td>{e['role']}</td><td>{e['action']}</td></tr>" for e in reversed(logs))
    users_dropdown = "".join(f"<option value='{u}' {'selected' if u==user else ''}>{u}</option>" for u in sorted(set([e.get("user") for e in load_logs_file()] + list(USERS.keys()))))
    content = f"""
      <h3>Activity Logs</h3>
      <form method="get" class="row g-2 mb-3">
        <div class="col-auto"><label>User</label><select name="user" class="form-select"><option value=''>All</option>{users_dropdown}</select></div>
        <div class="col-auto"><label>Action contains</label><input name="action" value="{action}" class="form-control"/></div>
        <div class="col-auto"><label>Start (YYYY-MM-DD)</label><input name="start" value="{start_raw}" class="form-control"/></div>
        <div class="col-auto"><label>End (YYYY-MM-DD)</label><input name="end" value="{end_raw}" class="form-control"/></div>
        <div class="col-auto align-self-end"><button class="btn btn-primary">Filter</button></div>
        <div class="col-auto align-self-end"><a class="btn btn-secondary" href="/logs/export?user={user}&action={action}&start={start_raw}&end={end_raw}">Export CSV</a></div>
      </form>
      <div class="table-responsive"><table class="table table-sm"><thead><tr><th>Time</th><th>User</th><th>Role</th><th>Action</th></tr></thead><tbody>{rows}</tbody></table></div>
    """
    return render_template_string(BASE_HTML, navbar=build_navbar(), content=content)

@flask_app.route("/logs/export")
@login_required
@role_required(["admin"])
def logs_export():
    user = request.args.get("user","")
    action = request.args.get("action","")
    start_raw = request.args.get("start",""); end_raw = request.args.get("end","")
    start = end = None
    fmt = "%Y-%m-%d"
    try:
        if start_raw: start = datetime.datetime.strptime(start_raw, fmt)
        if end_raw: end = datetime.datetime.strptime(end_raw, fmt) + datetime.timedelta(days=1)
    except:
        start = end = None
    logs = filter_logs(user=user if user else None, action=action if action else None, start=start, end=end)
    fname = f"logs_export_{int(time.time())}.csv"
    with open(fname,"w",newline="",encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["time","user","role","action"])
        for e in logs:
            w.writerow([e.get("time"), e.get("user"), e.get("role"), e.get("action")])
    return send_file(fname, as_attachment=True)

@flask_app.route("/logs-archive")
@login_required
@role_required(["admin"])
def logs_archive_page():
    # list archived log files
    archives = list_archives()
    sel = request.args.get("file", archives[0] if archives else "")
    rows = ""
    if sel:
        path = os.path.join(LOG_DIR, sel)
        logs = load_logs_file(path)
        rows = "".join(f"<tr><td>{e['time']}</td><td>{e['user']}</td><td>{e['role']}</td><td>{e['action']}</td></tr>" for e in reversed(logs))
    options = "".join(f"<option value='{a}' {'selected' if a==sel else ''}>{a}</option>" for a in archives)
    content = f"""
      <h3>Logs Archive</h3>
      <form method="get" class="mb-3">
        <label>Select Archive</label>
        <select name="file" onchange="this.form.submit()">{options}</select>
        &nbsp;<a class="btn btn-secondary" href="/logs-archive/export?file={sel}&fmt=csv">Export CSV</a>
        &nbsp;<a class="btn btn-secondary" href="/logs-archive/export?file={sel}&fmt=json">Export JSON</a>
      </form>
      <div class="table-responsive"><table class="table table-sm"><thead><tr><th>Time</th><th>User</th><th>Role</th><th>Action</th></tr></thead><tbody>{rows}</tbody></table></div>
    """
    return render_template_string(BASE_HTML, navbar=build_navbar(), content=content)

@flask_app.route("/logs-archive/export")
@login_required
@role_required(["admin"])
def logs_archive_export():
    sel = request.args.get("file","")
    fmt = request.args.get("fmt","csv")
    if not sel:
        return redirect(url_for("logs_archive_page"))
    path = os.path.join(LOG_DIR, sel)
    logs = load_logs_file(path)
    if fmt == "json":
        fname = f"archive_export_{int(time.time())}.json"
        with open(fname,"w",encoding="utf-8") as f:
            json.dump(logs,f,indent=2)
        return send_file(fname, as_attachment=True)
    else:
        fname = f"archive_export_{int(time.time())}.csv"
        with open(fname,"w",newline="",encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["time","user","role","action"])
            for e in logs:
                w.writerow([e.get("time"), e.get("user"), e.get("role"), e.get("action")])
        return send_file(fname, as_attachment=True)

# API endpoints
@flask_app.route("/api/students")
@login_required
def api_students():
    return jsonify([{"adm":s.admission_no,"name":s.name,"form":s.form,"stream":s.stream} for s in school.students])

@flask_app.route("/api/results/<int:form>")
@login_required
def api_results(form):
    out=[]
    for s in school.students:
        if s.form!=form: continue
        score,grade,_ = school.calculate_overall_grade(s)
        out.append({"adm":s.admission_no,"name":s.name,"score":score,"grade":grade})
    return jsonify(out)

# ---------------- Flask run helpers ----------------
def run_flask_dev(host, port):
    print(f"🛠️ Flask dev server running on {host}:{port}")
    flask_app.run(host=host, port=port, debug=False, use_reloader=False)

def run_with_waitress(host, port):
    try:
        from waitress import serve
        print(f"🚀 Waitress serving on {host}:{port}")
        serve(flask_app, listen=f"{host}:{port}")
    except Exception as e:
        print("⚠️ Waitress unavailable or failed:", e)
        print("Falling back to Flask dev server (not for production).")
        flask_app.run(host=host, port=port, debug=False, use_reloader=False)

# ---------------- Tkinter admin UI ----------------
class SchoolApp:
    def __init__(self, root, school_inst):
        self.root = root
        self.school = school_inst
        self.root.title(f"{self.school.name} Management System - Web login at /login")
        self.root.geometry("1350x780")
        self.root.configure(bg="#eef6ff")
        style = ttk.Style(); style.theme_use("clam")
        style.configure("TNotebook", background="#003366", foreground="white")
        style.configure("TFrame", background="#eef6ff")
        style.configure("TLabel", background="#eef6ff", font=("Arial",12))
        style.configure("TButton", font=("Arial",10))

        self.notebook = ttk.Notebook(self.root); self.notebook.pack(fill="both", expand=True, padx=8, pady=8)
        self.overview_tab = ttk.Frame(self.notebook); self.students_tab = ttk.Frame(self.notebook)
        self.teachers_tab = ttk.Frame(self.notebook); self.staff_tab = ttk.Frame(self.notebook)
        self.timetable_tab = ttk.Frame(self.notebook); self.results_tab = ttk.Frame(self.notebook)
        self.logs_tab = ttk.Frame(self.notebook); self.archive_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.overview_tab, text="Overview"); self.notebook.add(self.students_tab, text="Students")
        self.notebook.add(self.teachers_tab, text="Teachers"); self.notebook.add(self.staff_tab, text="Staff")
        self.notebook.add(self.timetable_tab, text="Timetable"); self.notebook.add(self.results_tab, text="Results")
        self.notebook.add(self.logs_tab, text="Logs"); self.notebook.add(self.archive_tab, text="Logs Archive")

        self._build_overview(); self._build_students(); self._build_teachers(); self._build_staff(); self._build_timetable(); self._build_results(); self._build_logs(); self._build_archive()

        exit_btn = ttk.Button(self.root, text="Exit System", command=self._on_exit); exit_btn.pack(side="bottom", pady=8)

    def _build_overview(self):
        f=ttk.Frame(self.overview_tab); f.pack(fill="both", expand=True, padx=20, pady=20)
        ttk.Label(f, text=f"School Name: {self.school.name}", font=("Arial",16,"bold")).pack(pady=6)
        ttk.Label(f, text=f"Principal: {self.school.principal}", font=("Arial",13)).pack(pady=3)
        ttk.Label(f, text=f"Deputy: {self.school.deputy}", font=("Arial",13)).pack(pady=3)
        ttk.Label(f, text=f"Working Hours: {self.school.working_hours}", font=("Arial",13)).pack(pady=3)
        ttk.Label(f, text=f"Total Students: {len(self.school.students)}", font=("Arial",13)).pack(pady=3)
        ttk.Label(f, text=f"Total Teachers: {len(self.school.teachers)}", font=("Arial",13)).pack(pady=3)
        ttk.Label(f, text=f"Total Staff: {len(self.school.staff)}", font=("Arial",13)).pack(pady=3)

    def _build_students(self):
        frame = ttk.Frame(self.students_tab); frame.pack(fill="both", expand=True, padx=12, pady=12)
        top = ttk.Frame(frame); top.pack(fill="x", pady=6)
        ttk.Label(top, text="Students List", font=("Arial",16,"bold")).pack(side="left")
        sf = ttk.Frame(top); sf.pack(side="right")
        ttk.Label(sf, text="Search (Adm or name):").pack(side="left")
        self.search_var = tk.StringVar(); self.search_entry = ttk.Entry(sf, textvariable=self.search_var, width=30); self.search_entry.pack(side="left", padx=4)
        ttk.Button(sf, text="Find", command=self._search_student).pack(side="left", padx=4)
        cols = ("Admission No","Name","Form","Stream")
        self.student_tree = ttk.Treeview(frame, columns=cols, show="headings", height=18)
        for c in cols:
            self.student_tree.heading(c, text=c); self.student_tree.column(c, anchor="center", width=300 if c=="Name" else 120)
        self.student_tree.pack(fill="both", expand=True, padx=8, pady=8)
        for s in self.school.students:
            self.student_tree.insert("", "end", values=(s.admission_no, s.name, s.form, s.stream))

    def _search_student(self):
        q = self.search_var.get().strip()
        if not q:
            messagebox.showinfo("Search","Type admission number or name"); return
        try:
            adm = int(q); s = self.school.find_student_by_adm(adm)
            if s: self._show_student_popup(s); return
        except: pass
        matches = self.school.find_students_by_name(q)
        if not matches: messagebox.showinfo("Search","No student found"); return
        if len(matches) == 1: self._show_student_popup(matches[0]); return
        sel = tk.Toplevel(self.root); sel.title("Select Student")
        tk.Label(sel, text=f"Multiple matches ({len(matches)}). Choose:").pack(padx=10,pady=6)
        lb = tk.Listbox(sel, width=80, height=10); lb.pack(padx=10,pady=6)
        for s in matches:
            lb.insert(tk.END, f"{s.admission_no} - {s.name} (Form {s.form} {s.stream})")
        def choose():
            idx = lb.curselection()
            if not idx: return
            s = matches[idx[0]]; sel.destroy(); self._show_student_popup(s)
        ttk.Button(sel, text="Select", command=choose).pack(pady=6)

    def _show_student_popup(self, s):
        top = tk.Toplevel(self.root); top.title(f"{s.name} - {s.admission_no}")
        txt = tk.Text(top, width=100, height=30, font=("Courier",10)); txt.pack(fill="both", expand=True)
        txt.insert("end", f"Report Card for {s.name} (Adm: {s.admission_no})\nForm {s.form} {s.stream}\n\n")
        if not s.results: txt.insert("end","No exam results\n")
        for term,exams in s.results.items():
            txt.insert("end", f"--- Term {term} ---\n")
            for ename,subs in exams.items():
                txt.insert("end", f"  {ename}:\n")
                total=0; cnt=0
                for subj,(m,g,pts) in subs.items():
                    total+=pts; cnt+=1
                    txt.insert("end", f"    {subj:<18} {m:>3}  {g:<2}  {pts}pts\n")
                if s.form in [1,2]:
                    mean = sum([m for m,_,_ in subs.values()])/max(1,len(subs)); mg = map_mean_to_grade(mean)
                    txt.insert("end", f"    Average marks: {mean:.2f} => {mg}\n\n")
                else:
                    txt.insert("end", f"    Total points: {total} => {map_mean_to_grade(total)}\n\n")
        ttk.Button(top, text="Enter / Edit Marks", command=lambda:self._enter_marks_gui(s)).pack(pady=6)

    def _enter_marks_gui(self, student):
        win = tk.Toplevel(self.root); win.title(f"Enter Marks - {student.name}")
        tk.Label(win, text=f"Entering marks for {student.name} ({student.admission_no})").pack(pady=6)
        term_var = tk.IntVar(value=1); exam_var = tk.StringVar(value="CAT 2")
        ctrl = ttk.Frame(win); ctrl.pack(pady=6)
        ttk.Label(ctrl, text="Term:").grid(row=0,column=0); ttk.Combobox(ctrl, textvariable=term_var, values=[1,2,3], width=5, state="readonly").grid(row=0,column=1)
        ttk.Label(ctrl, text="Exam:").grid(row=0,column=2); ttk.Combobox(ctrl, textvariable=exam_var, values=["CAT 1","CAT 2"], width=8, state="readonly").grid(row=0,column=3)
        if student.form >=3:
            core = ["Mathematics","English","Kiswahili","Biology","Chemistry","Physics"]
            electives = random.sample([x for x in SUBJECTS if x not in core], 2)
            subjects = core + electives
        else:
            subjects = SUBJECTS[:]
        entries = {}
        frm = ttk.Frame(win); frm.pack(pady=6)
        for i,subj in enumerate(subjects):
            ttk.Label(frm, text=subj).grid(row=i,column=0, sticky="w", padx=4, pady=2)
            v=tk.StringVar(); e=ttk.Entry(frm, textvariable=v, width=6); e.grid(row=i,column=1, padx=6, pady=2)
            entries[subj] = v
            existing = student.results.get(term_var.get(),{}).get(exam_var.get(),{}).get(subj)
            if existing: v.set(str(existing[0]))
        def save():
            term = term_var.get(); exam = exam_var.get()
            if term not in student.results: student.results[term] = {"CAT 1":{}, "CAT 2":{}}
            for subj,var in entries.items():
                txt = var.get().strip()
                if not txt: continue
                try: mark = int(txt)
                except: messagebox.showerror("Invalid", f"Invalid mark for {subj}"); return
                g,pts = grade_subject(mark)
                student.results[term][exam][subj] = (mark,g,pts)
            append_log("local_admin","admin",f"Updated marks for {student.admission_no} via Tk")
            messagebox.showinfo("Saved","Marks updated"); win.destroy()
        ttk.Button(win, text="Save Marks", command=save).pack(pady=8)

    def _build_teachers(self):
        frame = ttk.Frame(self.teachers_tab); frame.pack(fill="both", expand=True, padx=12, pady=12)
        ttk.Label(frame, text="Teachers List", font=("Arial",16,"bold")).pack(pady=6)
        cols = ("Teacher ID","Name","Subject","Class Assigned","Lessons")
        tree = ttk.Treeview(frame, columns=cols, show="headings", height=20)
        for c in cols:
            tree.heading(c, text=c); tree.column(c, anchor="center", width=260 if c=="Name" else 120)
        tree.pack(fill="both", expand=True, padx=8, pady=8)
        for t in self.school.teachers:
            tree.insert("", "end", values=(t.teacher_id,t.name,t.subject,t.class_assigned or "", t.lesson_count()))

    def _build_staff(self):
        frame = ttk.Frame(self.staff_tab); frame.pack(fill="both", expand=True, padx=12, pady=12)
        ttk.Label(frame, text="Staff List", font=("Arial",16,"bold")).pack(pady=6)
        cols = ("Name","Role","Department")
        tree = ttk.Treeview(frame, columns=cols, show="headings", height=20)
        for c in cols:
            tree.heading(c, text=c); tree.column(c, anchor="center", width=300 if c=="Name" else 200)
        tree.pack(fill="both", expand=True, padx=8, pady=8)
        for st in self.school.staff:
            tree.insert("", "end", values=(st.name, st.role, st.department))

    def _build_timetable(self):
        frame = ttk.Frame(self.timetable_tab); frame.pack(fill="both", expand=True, padx=12, pady=12)
        ttk.Label(frame, text="School Timetable", font=("Arial",14,"bold")).pack(pady=6)
        ctrl = ttk.Frame(frame); ctrl.pack(fill="x", pady=4)
        ttk.Label(ctrl, text="Choose Class:").pack(side="left", padx=6)
        class_names = list(self.school.timetable.keys())
        self.selected_class = tk.StringVar(value=class_names[0] if class_names else "")
        class_menu = ttk.Combobox(ctrl, textvariable=self.selected_class, values=class_names, width=30, state="readonly"); class_menu.pack(side="left", padx=6)
        ttk.Button(ctrl, text="Refresh", command=self._render_timetable_table).pack(side="left", padx=6)
        self._timetable_container = frame
        self._render_timetable_table()

    def _render_timetable_table(self):
        frame = self._timetable_container
        for child in frame.winfo_children()[2:]:
            child.destroy()
        cname = self.selected_class.get()
        if not cname: return
        time_slots = [slot for slot,_ in PERIODS]
        columns = ["Day"] + time_slots
        table_frame = ttk.Frame(frame); table_frame.pack(fill="both", expand=True, padx=8, pady=8)
        tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=12)
        for c in columns:
            tree.heading(c, text=c); tree.column(c, width=120 if c=="Day" else 220, anchor="center")
        tree.pack(fill="both", expand=True)
        for day in DAYS:
            periods = self.school.timetable[cname][day]
            row = [day] + [periods.get(ts,"") for ts in time_slots]
            tree.insert("", "end", values=row)

    def _build_results(self):
        frame = ttk.Frame(self.results_tab); frame.pack(fill="both", expand=True, padx=12, pady=12)
        ttk.Label(frame, text="Exam Results & Rankings", font=("Arial",16,"bold")).pack(pady=6)
        self.results_display = tk.Text(frame, width=140, height=30, font=("Courier",10)); self.results_display.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        scrollbar = ttk.Scrollbar(frame, command=self.results_display.yview); scrollbar.pack(side="right", fill="y"); self.results_display.config(yscrollcommand=scrollbar.set)
        btn_frame = ttk.Frame(frame); btn_frame.pack(fill="x", pady=6)
        ttk.Button(btn_frame, text="Show Rankings (per form)", command=self.show_rankings).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="Export Rankings CSV", command=self._export_rankings_csv).pack(side="left", padx=6)

    def show_rankings(self):
        self.results_display.delete("1.0","end")
        for form in [1,2,3,4]:
            self.results_display.insert("end", f"\n==== Rankings for Form {form} ====\n")
            rows=[]
            for s in self.school.students:
                if s.form!=form: continue
                score,grade,_ = self.school.calculate_overall_grade(s)
                rows.append((score, s.admission_no, s.name, grade))
            rows.sort(key=lambda x:x[0], reverse=True)
            self.results_display.insert("end", f"{'Rank':<5}{'AdmNo':<9}{'Name':<30}{'Score':<12}{'Grade':<6}\n")
            for i,(score,adm,name,grade) in enumerate(rows, start=1):
                self.results_display.insert("end", f"{i:<5}{adm:<9}{name:<30}{score:<12.2f}{grade:<6}\n")

    def _export_rankings_csv(self):
        fname = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV","*.csv")])
        if not fname: return
        with open(fname,"w",newline="",encoding="utf-8") as f:
            w = csv.writer(f)
            for form in [1,2,3,4]:
                w.writerow([f"Rankings for Form {form}"])
                w.writerow(["Rank","AdmNo","Name","Score","Grade"])
                rows=[]
                for s in self.school.students:
                    if s.form!=form: continue
                    score,grade,_ = self.school.calculate_overall_grade(s)
                    rows.append((score, s.admission_no, s.name, grade))
                rows.sort(key=lambda x:x[0], reverse=True)
                for i,(score,adm,name,grade) in enumerate(rows, start=1):
                    w.writerow([i,adm,name,f"{score:.2f}",grade])
        messagebox.showinfo("Exported", f"Rankings exported to {fname}")

    def _build_logs(self):
        frame = ttk.Frame(self.logs_tab); frame.pack(fill="both", expand=True, padx=12, pady=12)
        ttk.Label(frame, text="Activity Logs (admin view only in web)", font=("Arial",16,"bold")).pack(pady=6)
        self.logs_text = tk.Text(frame, width=140, height=30); self.logs_text.pack(fill="both", expand=True)
        ttk.Button(frame, text="Refresh Logs", command=self._refresh_logs).pack(pady=6)
        self._refresh_logs()

    def _refresh_logs(self):
        logs = load_logs_file()
        self.logs_text.delete("1.0","end")
        for e in reversed(logs):
            self.logs_text.insert("end", f"{e.get('time')} | {e.get('user')} ({e.get('role')}) -> {e.get('action')}\n")

    def _build_archive(self):
        frame = ttk.Frame(self.archive_tab); frame.pack(fill="both", expand=True, padx=12, pady=12)
        ttk.Label(frame, text="Logs Archive", font=("Arial",16,"bold")).pack(pady=6)
        ctrl = ttk.Frame(frame); ctrl.pack(fill="x", pady=6)
        ttk.Label(ctrl, text="Select Archive:").pack(side="left", padx=6)
        self.archive_var = tk.StringVar()
        archives = list_archives()
        self.archive_var.set(archives[0] if archives else "")
        self.archive_combo = ttk.Combobox(ctrl, textvariable=self.archive_var, values=archives, width=60, state="readonly")
        self.archive_combo.pack(side="left", padx=6)
        ttk.Button(ctrl, text="Load", command=self._load_selected_archive).pack(side="left", padx=6)
        ttk.Button(ctrl, text="Export CSV", command=self._export_selected_archive_csv).pack(side="left", padx=6)
        ttk.Button(ctrl, text="Export JSON", command=self._export_selected_archive_json).pack(side="left", padx=6)
        self.archive_text = tk.Text(frame, width=140, height=30); self.archive_text.pack(fill="both", expand=True, pady=8)
        self._load_selected_archive()

    def _load_selected_archive(self):
        sel = self.archive_var.get()
        if not sel:
            self.archive_text.delete("1.0","end"); self.archive_text.insert("end","No archives found"); return
        path = os.path.join(LOG_DIR, sel)
        logs = load_logs_file(path)
        self.archive_text.delete("1.0","end")
        for e in reversed(logs):
            self.archive_text.insert("end", f"{e.get('time')} | {e.get('user')} ({e.get('role')}) -> {e.get('action')}\n")

    def _export_selected_archive_csv(self):
        sel = self.archive_var.get()
        if not sel:
            messagebox.showinfo("Export","No archive selected"); return
        path = os.path.join(LOG_DIR, sel)
        logs = load_logs_file(path)
        fname = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV","*.csv")])
        if not fname: return
        with open(fname,"w",newline="",encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["time","user","role","action"])
            for e in logs:
                w.writerow([e.get("time"), e.get("user"), e.get("role"), e.get("action")])
        messagebox.showinfo("Exported", f"Exported to {fname}")

    def _export_selected_archive_json(self):
        sel = self.archive_var.get()
        if not sel:
            messagebox.showinfo("Export","No archive selected"); return
        path = os.path.join(LOG_DIR, sel)
        logs = load_logs_file(path)
        fname = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON","*.json")])
        if not fname: return
        with open(fname,"w",encoding="utf-8") as f:
            json.dump(logs,f,indent=2)
        messagebox.showinfo("Exported", f"Exported to {fname}")

    def _on_exit(self):
        # log shutdown
        append_log("SYSTEM","Server","Local admin closed Tkinter UI (shutdown)")
        self.root.quit()

# ---------------- Startup / Shutdown handling ----------------
def startup_self_check(mode_str, host, port):
    # counts
    users_count = len(USERS)
    logs_count = len(load_logs_file())
    archives = list_archives()
    print("✅ TRIXIE HIGH SCHOOL system started!")
    print(f"Students loaded: {len(school.students)}")
    print(f"Teachers loaded: {len(school.teachers)}")
    print(f"Staff loaded: {len(school.staff)}")
    print(f"Users loaded: {users_count}")
    print(f"Logs loaded: {logs_count} | Archives: {len(archives)}")
    print()
    print(f"Mode: {mode_str}")
    print(f"Running at: http://{host}:{port}")
    # append system startup log
    append_log("SYSTEM","Server",f"System started in {mode_str} on {host}:{port}")

def shutdown_handler(signum=None, frame=None):
    append_log("SYSTEM","Server","System stopped gracefully")
    print("🛑 TRIXIE HIGH SCHOOL system shutting down...")

# register atexit & signals
atexit.register(lambda: append_log("SYSTEM","Server","System exiting via atexit"))
for sig in (signal.SIGINT, signal.SIGTERM):
    try:
        signal.signal(sig, shutdown_handler)
    except Exception:
        pass

# ---------------- Main entry ----------------
def main(argv=None):
    parser = argparse.ArgumentParser(description="Run TRIXIE HIGH SCHOOL system")
    parser.add_argument("--prod", action="store_true", help="Run in production mode (Waitress)")
    parser.add_argument("--dev", action="store_true", help="Run in dev mode (Flask built-in)")
    parser.add_argument("--port", type=int, default=5000, help="Web server port")
    parser.add_argument("--host", default="127.0.0.1", help="Web server host")
    args = parser.parse_args(argv)

    global school, USERS
    # Initialize school and data
    school = School("TRIXIE HIGH SCHOOL", "TRIXIE MISHEEN", "Mannuel Misheen")
    school.generate_students()
    school.generate_teachers(total=TOTAL_TEACHERS)
    school.generate_staff()
    school.generate_timetable()
    school.generate_exam_results()

    # Ensure users file has admin
    if "admin" not in USERS:
        USERS["admin"] = {"password": hash_password("admin123"), "role":"admin"}
        save_users(USERS)

    # Rotate logs if term changed
    rotate_logs(force=False)

    host = args.host; port = args.port
    mode = "PRODUCTION" if args.prod else "DEVELOPMENT"

    # startup self-check & log
    startup_self_check(mode, host, port)

    # start flask in background thread so Tkinter runs on main thread
    if args.prod:
        flask_thread = threading.Thread(target=lambda: run_with_waitress(host, port), daemon=True)
        flask_thread.start()
    else:
        flask_thread = threading.Thread(target=lambda: run_flask_dev(host, port), daemon=True)
        flask_thread.start()

    # start tkinter UI
    root = tk.Tk()
    app_ui = SchoolApp(root, school)
    try:
        root.mainloop()
    finally:
        shutdown_handler()

if __name__ == "__main__":
    main()
