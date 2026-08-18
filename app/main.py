import os
import random
import string
import traceback
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, HttpUrl
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import engine, get_db, redis_client, Base
from models import URLMapping

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB tables on application startup
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(title="Containerized URL Shortener Platform", lifespan=lifespan)

class URLCreateRequest(BaseModel):
    url: HttpUrl

class URLResponse(BaseModel):
    short_code: str
    short_url: str
    original_url: str
    click_count: int

def generate_short_code(length: int = 6) -> str:
    chars = string.ascii_letters + string.digits
    return "".join(random.choice(chars) for _ in range(length))

@app.get("/", response_class=FileResponse)
def serve_ui():
    index_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Welcome to URL Shortener API. UI template missing."}

@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    try:
        redis_client.ping()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "healthy"}
    except Exception as e:
        print("HEALTH CHECK FAILED:", traceback.format_exc(), flush=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Health check failed: {str(e)}"
        )

@app.post("/shorten", response_model=URLResponse, status_code=status.HTTP_201_CREATED)
def shorten_url(payload: URLCreateRequest, db: Session = Depends(get_db)):
    original_url = str(payload.url)
    short_code = generate_short_code()

    while db.query(URLMapping).filter(URLMapping.short_code == short_code).first():
        short_code = generate_short_code()

    new_mapping = URLMapping(original_url=original_url, short_code=short_code)
    db.add(new_mapping)
    db.commit()
    db.refresh(new_mapping)

    redis_client.set(f"url:{short_code}", original_url)
    redis_client.set(f"clicks:{short_code}", 0)

    return {
        "short_code": short_code,
        "short_url": f"http://localhost/{short_code}",
        "original_url": original_url,
        "click_count": 0
    }

@app.get("/stats/{short_code}", response_model=URLResponse)
def get_stats(short_code: str, db: Session = Depends(get_db)):
    mapping = db.query(URLMapping).filter(URLMapping.short_code == short_code).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Short URL not found")

    cached_clicks = redis_client.get(f"clicks:{short_code}")
    click_count = int(cached_clicks) if cached_clicks else mapping.click_count

    return {
        "short_code": mapping.short_code,
        "short_url": f"http://localhost/{mapping.short_code}",
        "original_url": mapping.original_url,
        "click_count": click_count
    }

@app.get("/{short_code}")
def redirect_to_url(short_code: str, db: Session = Depends(get_db)):
    cached_url = redis_client.get(f"url:{short_code}")
    
    if cached_url:
        redis_client.incr(f"clicks:{short_code}")
        db.query(URLMapping).filter(URLMapping.short_code == short_code).update(
            {URLMapping.click_count: URLMapping.click_count + 1}
        )
        db.commit()
        return RedirectResponse(url=cached_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    mapping = db.query(URLMapping).filter(URLMapping.short_code == short_code).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Short URL not found")

    mapping.click_count += 1
    db.commit()

    redis_client.set(f"url:{short_code}", mapping.original_url)
    redis_client.set(f"clicks:{short_code}", mapping.click_count)

    return RedirectResponse(url=mapping.original_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)