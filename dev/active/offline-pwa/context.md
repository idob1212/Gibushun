# Key Files & Architecture

## Core Files
- `main.py` - Monolithic Flask app (~2046 lines), all routes and models
- `templates/header.html` - Nav, CDN refs (Bootstrap 4.5 CSS/JS, jQuery, Google Fonts)
- `templates/footer.html` - Local vendor scripts (jQuery, Bootstrap bundle)
- `forms.py` - WTForms definitions

## Database Models (main.py)
- User (groups): id, password, name, sprint/crawl/alonka/mitam_num
- Candidate: id (format "group/num"), group_id, name, interview fields, status
- Review: id, author_id, station, subject_id, grade, note, counter_value
- Note: id, author_id, subject_id, type, text, location, date

## Key AJAX Endpoints
- GET /subjects/<group> - candidate list (JSON)
- GET /physicals/<group> - physical station list (JSON)
- GET /stations/<group> - all station list (JSON)
- GET /get-station-reviews/<station> - counter review data (JSON)
- POST /update-counter-reviews - save counter reviews (JSON)
- POST /circles/finished - save circle results (JSON)
- POST /circles/finished-act - save circle act results (JSON)
- POST /add-review-candidate - single AJAX review submission
- POST /add-all - group review form submission

## Vendor Directory Structure
- static/vendor/bootstrap/css/, js/
- static/vendor/jquery/ (jquery.min.js exists)
- static/vendor/fontawesome-free/css/

## CDN Dependencies to Remove
- Bootstrap CSS: //maxcdn.bootstrapcdn.com/bootstrap/4.5.0/css/bootstrap.min.css
- jQuery: https://code.jquery.com/jquery-3.5.1.min.js
- Bootstrap JS: //maxcdn.bootstrapcdn.com/bootstrap/4.5.0/js/bootstrap.min.js
- Google Fonts: Lora, Open Sans (will use system font fallback)
- NOTE: Many templates also load CDN Bootstrap/jQuery in their <header> section
