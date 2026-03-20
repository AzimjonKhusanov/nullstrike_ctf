# CTF.PWN — Minimal CTF Platform

## Setup & Run

```bash
pip install flask
python app.py
```

Open http://localhost:5000

## Default Credentials
- **Admin**: `admin` / `admin`
- Register new users at `/register`

## Structure
```
ctf/
├── app.py              # All backend logic (~300 lines)
├── requirements.txt
└── templates/
    ├── base.html       # Layout, nav, styles
    ├── auth.html       # Login / Register
    ├── dashboard.html  # Competition list
    ├── competition.html# Competition detail + scoreboard
    ├── practice.html   # Practice tasks
    ├── task.html       # Task detail + flag submit
    ├── admin.html      # Full admin panel
    └── edit_task.html  # Edit task form
```

## Features
- **Auth**: Register, login, sessions, admin/user roles
- **Competitions**: Create, start/stop/end, delete
- **Tasks (strictly separated)**:
  - Competition tasks — linked to a competition, visible only when active
  - Practice tasks — always available, never mixed with competition tasks
- **Solving**: Submit flags, instant feedback, duplicate prevention
- **Scoreboard**: Per-competition ranking by points
- **Admin**: Full CRUD on competitions and both task types, user list

## Database Schema (SQLite)
- `users` — id, username, password, role
- `competitions` — id, name, description, status (pending/active/ended)
- `tasks` — id, title, description, flag, points, category, hints, **type** (competition|practice), competition_id
- `submissions` — user_id, task_id, correct (unique constraint prevents re-solving)
- `participants` — user_id, competition_id (join table)
# nullstrike_ctf
