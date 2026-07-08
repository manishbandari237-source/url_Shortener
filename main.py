from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Integer
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import random
import string
import os
from fastapi.responses import RedirectResponse
from upstash_redis import Redis
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request

load_dotenv()
redis = Redis(url=os.getenv("UPSTASH_REDIS_REST_URL"), token=os.getenv("UPSTASH_REDIS_REST_TOKEN"))

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class URLMapping(Base):
    __tablename__ = "url_mappings"
    id = Column(Integer, primary_key=True, index=True)
    short_code = Column(String, unique=True, index=True)
    long_url = Column(String)

Base.metadata.create_all(bind=engine)

app = FastAPI()

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

class URLRequest(BaseModel):
    long_url: str

def generate_short_code():
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(6))

@app.get("/")
def read_root():
    return {"message": "URL Shortener is running"}

@app.post("/shorten")
@limiter.limit("5/minute")
def create_short_url(request: Request, url_request: URLRequest):
    db = SessionLocal()
    short_code = generate_short_code()
    new_entry = URLMapping(short_code=short_code, long_url=url_request.long_url)
    db.add(new_entry)
    db.commit()
    db.close()
    redis.set(short_code, url_request.long_url, ex=3600)
    return {"short_code": short_code, "short_url": f"http://localhost:8000/{short_code}"}

@app.get("/{short_code}")
def redirect_to_long_url(short_code: str):
    cached_url = redis.get(short_code)
    if cached_url:
        return RedirectResponse(url=cached_url)

    db = SessionLocal()
    result = db.query(URLMapping).filter(URLMapping.short_code == short_code).first()
    db.close()
    if not result:
        return {"error": "Short URL not found"}

    redis.set(short_code, result.long_url, ex=3600)
    return RedirectResponse(url=result.long_url)