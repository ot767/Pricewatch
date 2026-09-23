import os
import json
from pathlib import Path
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, request, send_from_directory

BASE = Path(__file__).resolve().parent
DB = BASE / "pricewatch-data.json"
PUBLIC = BASE / "public"

app = Flask(__name__, static_folder=str(PUBLIC), static_url_path="")
REEF_KEY = os.environ.get("REEF_API_KEY", "").strip()
REEF_BASE = "https://api.reefapi.com"

def load_db():
    try:
        return json.loads(DB.read_text(encoding="utf-8"))
    except Exception:
        return {"watchlist": []}

def save_db(db):
    DB.write_text(json.dumps(db, indent=2), encoding="utf-8")

def reef(endpoint, payload):
    if not REEF_KEY:
        raise RuntimeError(
            "REEF_API_KEY is not configured. Add your ReefAPI key before using live prices."
        )
    r = requests.post(
        REEF_BASE + endpoint,
        headers={"x-api-key": REEF_KEY, "content-type": "application/json"},
        json=payload,
        timeout=30,
    )
    try:
        data = r.json()
    except Exception:
        data = {}
    if not r.ok or data.get("ok") is False:
        err = data.get("error")
        if isinstance(err, dict):
            err = err.get("message") or err.get("detail")
        raise RuntimeError(str(err or f"Live API error ({r.status_code})"))
    return data

@app.get("/api/health")
def health():
    return jsonify(ok=True, live=bool(REEF_KEY))

@app.get("/api/search")
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify(error="Enter a product to search."), 400
    try:
        j = reef("/takealot/v1/search", {
            "query": q,
            "country": "za",
            "sort": "price_asc"
        })
        results = []
        for x in (j.get("data", {}).get("results", []) or [])[:18]:
            results.append({
                "product_id": str(x.get("plid") or x.get("product_id") or ""),
                "title": x.get("title") or "Untitled product",
                "brand": x.get("brand"),
                "image": x.get("image"),
                "url": x.get("url"),
                "price": x.get("price"),
                "currency": x.get("currency") or "ZAR",
                "in_stock": x.get("in_stock"),
                "stock_status": x.get("stock_status"),
                "rating": x.get("rating"),
                "review_count": x.get("review_count"),
            })
        return jsonify(results=results, source="Takealot via ReefAPI", live=True)
    except Exception as e:
        return jsonify(error=str(e)), 502

@app.get("/api/watch")
def get_watchlist():
    return jsonify(watchlist=load_db()["watchlist"])

@app.post("/api/watch")
def add_watch():
    body = request.get_json(silent=True) or {}
    required = ["product_id", "title", "url", "target_price", "current_price"]
    if not all(body.get(k) is not None for k in required):
        return jsonify(error="Missing watch details."), 400

    db = load_db()
    pid = str(body["product_id"])
    snap = {
        "at": datetime.now(timezone.utc).isoformat(),
        "price": float(body["current_price"])
    }
    existing = next((x for x in db["watchlist"] if x["product_id"] == pid), None)

    if existing:
        existing["target_price"] = float(body["target_price"])
        existing["current_price"] = float(body["current_price"])
        existing["history"] = (existing.get("history", []) + [snap])[-90:]
    else:
        db["watchlist"].append({
            "product_id": pid,
            "title": body["title"],
            "url": body["url"],
            "image": body.get("image"),
            "target_price": float(body["target_price"]),
            "current_price": float(body["current_price"]),
            "history": [snap],
        })
    save_db(db)
    return jsonify(ok=True)

@app.delete("/api/watch/<path:product_id>")
def remove_watch(product_id):
    db = load_db()
    db["watchlist"] = [x for x in db["watchlist"] if x["product_id"] != str(product_id)]
    save_db(db)
    return jsonify(ok=True)

def refresh():
    db = load_db()
    for w in db["watchlist"]:
        try:
            j = reef("/takealot/v1/product/detail", {
                "product_id": w["product_id"],
                "country": "za"
            })
            d = j.get("data", {}) or {}
            price = d.get("price", d.get("price_min"))
            if price is not None:
                price = float(price)
                w["current_price"] = price
                w["history"] = (
                    w.get("history", []) +
                    [{"at": datetime.now(timezone.utc).isoformat(), "price": price}]
                )[-90:]
            if d.get("image"):
                w["image"] = d["image"]
            if d.get("url"):
                w["url"] = d["url"]
        except Exception as e:
            print("Refresh error:", w.get("product_id"), e)
    save_db(db)

@app.post("/api/refresh")
def manual_refresh():
    try:
        refresh()
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(error=str(e)), 502

@app.get("/")
def home():
    return send_from_directory(PUBLIC, "index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8787"))
    print(f"PriceWatch running at http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
