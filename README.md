# Roblox profile lookup

## Run locally
    python server.py
Open http://localhost:8000

## Deploy on Render
1. Push this folder to a GitHub repo.
2. Render dashboard > New > Web Service > pick the repo.
3. Runtime: Python 3
   Build Command: pip install -r requirements.txt
   Start Command: python server.py
4. Instance type: Free > Create Web Service.
(Or use New > Blueprint, which reads render.yaml.)
