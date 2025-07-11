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
- `main.py` (28k+ lines) - Contains all application logic, routes, and database models
- `forms.py` - All WTForms form definitions
- `templates/` - HTML templates (Hebrew UI)
- `static/` - CSS, JavaScript, and images

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

### Authentication System

**User Roles:**
- **Admin** (`id=0`): Full system access, can manage all groups and candidates
- **Group Users** (`id>0`): Can only access their assigned candidates

**Security Notes:**
- Passwords are stored in plain text (security concern)
- No password hashing implementation
- Session management via Flask-Login

### Key Routes and Functionality

**Authentication:**
- `/login` - Group login
- `/register` - New group registration (admin only)

**Candidate Management:**
- `/add-candidate` - Add individual candidates
- `/add-candidate-batch` - Bulk candidate addition
- `/candidate/<id>` - View candidate details

**Evaluation System:**
- `/new-review` - Create station evaluations
- `/counter-review` - Physical activity evaluations
- `/interview` - Interview management
- `/physical-reviews/` - Physical performance reviews

**Reporting:**
- `/rankings` - Candidate rankings
- `/download-sheet/` - Excel export functionality
- `/reviews-finder` - Search and filter evaluations

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
- pandas for Excel exports
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