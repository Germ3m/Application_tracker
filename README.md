# Job_tracker
A full-stack job application tracker for South African software engineering internships and graduate programmes — with live job search, auto-refresh, and application status management.


# JobTracker

A personal job application tracker built for South African software engineering 
internships and graduate programmes.

## Features
- Track job applications with statuses: Applied, OA, Interview, Offer, Rejected, Withdrawn
- Live job search aggregated from Adzuna, LinkedIn, and RemoteOK
- Auto-refreshes job listings every 30 minutes in the background
- Filter jobs by province and type (Internship / Graduate)
- Stream search results in real-time as each source responds
- Clean single-page UI with no frontend framework

## Tech Stack
- **Backend:** FastAPI + SQLite
- **Frontend:** Vanilla HTML/CSS/JS
- **Job Sources:** Adzuna API, LinkedIn (scraping), RemoteOK API

## Setup
1. Clone the repo
2. Install dependencies: `pip install -r requirements.txt`
3. Add your Adzuna credentials to a `.env` file:
ADZUNA_APP_ID=your_app_id
ADZUNA_APP_KEY=your_app_key
4. Run: `python main.py`
5. Open `http://127.0.0.1:8000`

