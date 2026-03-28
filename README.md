# SnipVault 🗄️
A Flask-based code snippet manager with bcrypt authentication and inverted index search.

## Live Demo
👉 [Your Render URL here after deployment]

## Features
- 🔐 Secure login with bcrypt password hashing
- 🔍 Inverted index search with stop-word filtering
- ⭐ Favorites system
- 🏷️ Language filter (Python, JS, HTML, CSS)
- ✏️ Add / Edit / Delete snippets
- ☁️ Deployed on Render.com with Aiven MySQL

## Tech Stack
- Backend: Python, Flask, Flask-Bcrypt
- Database: MySQL (Aiven cloud)
- Deployment: Render.com
- Search: Custom inverted index (no external search library)

## Local Setup
1. `pip install -r requirements.txt`
2. Copy `.env.example` → `.env` and fill credentials
3. Create MySQL tables (see schema in `.env.example`)
4. `python app.py`
