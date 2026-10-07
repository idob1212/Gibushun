# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Hebrew-language military recruitment management system built with Flask. The system manages candidate evaluations across multiple stations, interviews, and group assignments for military recruitment processes.

## Development Commands

### Running the Application

**Development Server:**
```bash
export FLASK_APP=gibushun
export FLASK_ENV=development
flask run
```

**Alternative Development (using run.sh):**
```bash
./run.sh
```

**Production with Docker:**
```bash
docker build -t gibushun .
docker run -p 3000:3000 gibushun
```

**Production with Gunicorn:**
```bash
gunicorn -w 4 -b 0.0.0.0:3000 main:app
```

### Database Management

**Database Location:**
- Development: `data.db` (SQLite)
- Production: PostgreSQL via `DATABASE_URL` environment variable

**Database Initialization:**
The database is created automatically when the app starts. Tables are created using SQLAlchemy models.

## Application Architecture

### Core Application Structure

**Single-File Architecture:**
- `main.py` (~3k lines) - Contains all application logic, routes, and database models
- `forms.py` - All WTForms form definitions
- `templates/` - HTML templates (Hebrew UI); `header.html`/`footer.html` wrap every page
- `static/` - CSS, JavaScript, and images
- `static/js/offline.js` - IndexedDB outbox: queues writes offline/on timeout and replays them with their request id
- `static/js/app.js` - UI behaviour: scroll shell, tap/busy feedback, double-submit guard, quick-note sheet
- `static/sw.js` - Service worker (bump `VERSION` when cached assets change)
- `static/src/input.css` → `static/css/app.css` (Tailwind v4 + DaisyUI; run `npm run build` and commit the output)

**Mobile app shell (installed PWA):** the document never scrolls. `.app-shell` is
fixed to the viewport, only `<main id="app-main">` scrolls, and the bottom dock is a
flex row, not `position: fixed` (iOS left the dock stranded mid-screen otherwise).
Never toggle layout on input focus/blur — a tap on "save" blurs first and a layout
jump sends the tap elsewhere.

### Database Models

**User Model (`users` table):**
- Represents groups (military units)
- `id` field is the group number
- Special admin user has `id=0`
- Contains counters for different evaluation types

**Candidate Model (`candidates` table):**
- Primary key format: "group_id/candidate_number"
- Contains personal info, interview results, and final status
- Belongs to a specific group

**Review Model (`reviews` table):**
- Station-based evaluations
- Links candidates to their performance scores
- Supports both numerical grades and counter-based evaluations

**Note Model (`notes` table):**
- Behavioral observations and notes
- Categorized as positive, neutral, or negative

**PriorInterview Model (`prior_interviews` table):**
- Rows of the unit's interview form (Google Forms "תגובות" export), synced by the admin
- Matched to candidates by `name_key()` (no niqqud/quotes/dashes, final letters folded,
  word order ignored; a middle name added/left out is a "possible" match)
- Keeps name, time, interviewer, gibush, rating, impression only — no ID numbers,
  no medical / ת"ש answers

### Authentication System

**User Roles:**
- **Admin** (`id=0`): Full system access, can manage all groups and candidates
- **Group Users** (`id>0`): Can only access their assigned candidates
- **Staff stations** (`id<0`): doctor (`-1`) and HR officer (`-2`). Log in by role +
  password (set by the admin in `/admin-panel`), reach only `STAFF_ENDPOINTS`, and
  write notes of type `רפואה` / `כוח אדם` on any group's candidates (shown on the
  group's home page next to the candidate number)

**Security Notes:**
- Passwords are stored in plain text (security concern)
- No password hashing implementation
- Session management via Flask-Login

### Key Routes and Functionality

**Authentication:**
- `/login` - Group / admin / staff-station login
- `/register` - New group registration (admin only); creates placeholder candidates 1–N ("מגובש N")
- `/staff` - Doctor / HR station home

**Candidate Management:**
- `/add-candidate`, `/add-candidate-batch` - Add candidates (fills a placeholder's name if the number exists)
- `/group-manage` - Bulk naming, photos (`/candidate-photo/...`), retire, remove unused numbers
- `/candidate/<group>/<number>` - Candidate page: scores, notes, edit/delete saved grades

**Evaluation System:**
- `/circles` - Arrival order (circle mode); `/acts` - saved heats (move/delete)
- `/counter-review` - March counters; `/new-review`, `/new-group-review` - station grades
- `/notes/quick` - JSON endpoint behind the floating quick-note sheet
- `/interview/`, `/show-interview/` - Interviews (summary lists all by default)
- `/final-grade/`, `/final-summary/` - Final category and ranking inside each category

**Interview check:**
- `/interviews/sync` (admin, POST, .xlsx/.csv) - merge the interview form export; re-uploads update in place
- `/interviews/clear` (admin, POST) - delete the synced list
- Matches pop up on the admin home (every group) and the group home (own candidates),
  once per new match per phone (localStorage); rating and impression are admin-only

**Reporting:**
- `/download-sheet/` - Excel export functionality
- `/reviews-finder` - Search and filter evaluations

**Tests:** `tests/*.py` are plain scripts (`python tests/<file>.py` with the pinned deps).

### Evaluation Stations

**Physical Stations:**
- ספרינטים (Sprints)
- זחילות (Crawls)  
- אלונקה סוציומטרית (Sociometric Stretcher)
- מסע 1, מסע 2, מסע 3 (Marches 1, 2, 3)
- שקי חול (Sandbags)

**Cognitive Evaluations:**
- Station-based assessments with 1-4 grade scale
- Interview evaluations with detailed notes
- Behavioral observations and notes

### Data Export

**Excel Export Features:**
- Comprehensive candidate reports
- Performance analytics
- Group comparisons
- Multiple sheet formats using pandas and xlwt

## Development Guidelines

### Working with the Codebase

**Language Considerations:**
- UI text is in Hebrew
- Database content is in Hebrew
- Comments and variable names are in English
- Station names and evaluation criteria are in Hebrew

**Database Operations:**
- Use SQLAlchemy ORM for all database interactions
- Candidate IDs follow format: "group_id/candidate_number"
- Admin operations require `current_user.id == 0` check

**Form Handling:**
- All forms are defined in `forms.py`
- Use WTForms validation
- Hebrew labels and validation messages

### Technical Debt and Limitations

**Architecture Issues:**
- Single massive file (main.py) - consider refactoring into modules
- No proper error handling
- No logging system
- No unit tests
- No API documentation

**Security Concerns:**
- Plain text password storage
- No password hashing
- Limited input validation
- No CSRF protection beyond WTForms

**Performance Considerations:**
- SQLite for development may not handle concurrent users well
- No database connection pooling
- No caching layer
- Large single-file architecture impacts startup time

## Environment Configuration

**Required Environment Variables:**
- `DATABASE_URL` - PostgreSQL connection string for production
- `FLASK_APP` - Set to "gibushun" for development
- `FLASK_ENV` - Set to "development" for development mode

**Dependencies:**
- Python 3.9+
- Flask 1.1.2
- SQLAlchemy for ORM
- pandas for Excel exports; openpyxl (+ defusedxml) reads the interview-form upload
- Bootstrap for UI
- All dependencies listed in `requirements.txt`

## Deployment

**Docker Deployment:**
- Uses Python 3.9 slim base image
- Runs with Gunicorn (4 workers)
- Listens on port 3000
- Platform: linux/amd64

**Heroku Deployment:**
- Procfile configured for Heroku
- Uses PostgreSQL add-on
- Gunicorn WSGI server