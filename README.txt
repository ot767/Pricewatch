PRICEWATCH DEPLOYMENT

This project is ready for a Python web host such as Render.

Files:
app.py
requirements.txt
.python-version
public/index.html

Render settings:
Build Command:
pip install -r requirements.txt

Start Command:
gunicorn app:app

Environment variable:
REEF_API_KEY = your ReefAPI key

Do not put the API key inside index.html or app.py.

The live product search uses Takealot data through ReefAPI.
The watchlist currently uses a local JSON file, so for a serious public launch we should move watchlist data to a real database before driving significant traffic.
