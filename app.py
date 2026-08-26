import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from crop_codes import CROP_CODES
from recommendation_engine import CHUNGBUK_SIGUN_CODES, recommend

load_dotenv()

KAKAO_MAP_KEY = os.getenv("KAKAO_MAP_KEY", "")
VWORLD_API_KEY = os.getenv("VWORLD_API_KEY", "")
VWORLD_DATA_URL = "https://api.vworld.kr/req/data"

BASE = Path(__file__).resolve().parent
app = FastAPI(title="귀농해유", version="1.0.0")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


class SearchRequest(BaseModel):
    sido: str = "충청북도"
    sigun: list[str] = Field(min_length=1)
    crops: list[str] = Field(min_length=1)
    budget_manwon: int = Field(gt=0)


@app.get("/")
def home():
    html = (BASE / "static" / "index.html").read_text(encoding="utf-8")
    html = html.replace("{{KAKAO_MAP_KEY}}", KAKAO_MAP_KEY)
    return HTMLResponse(html)


@app.get("/api/options")
def options():
    return {"sido": ["충청북도"], "sigun": list(CHUNGBUK_SIGUN_CODES), "crops": list(CROP_CODES)}


@app.get("/api/parcel-boundary")
def parcel_boundary(pnu: str):
    if not VWORLD_API_KEY:
        raise HTTPException(500, "브이월드 API 키가 설정되지 않았어유.")
    params = {
        "service": "data",
        "version": "2.0",
        "request": "GetFeature",
        "format": "json",
        "errorformat": "json",
        "key": VWORLD_API_KEY,
        "data": "LP_PA_CBND_BUBUN",
        "attrFilter": f"pnu:=:{pnu}",
        "geomFilter": "",
        "crs": "EPSG:4326",
        "size": "10",
    }
    try:
        res = requests.get(VWORLD_DATA_URL, params=params, timeout=8)
        res.raise_for_status()
        body = res.json()
    except Exception as exc:
        raise HTTPException(502, f"필지 경계를 불러오지 못했어유: {exc}") from exc

    result = body.get("response", {})
    status = result.get("status")
    if status != "OK":
        raise HTTPException(404, "필지 경계 정보를 찾을 수 없어유.")

    features = result.get("result", {}).get("featureCollection", {}).get("features", [])
    if not features:
        raise HTTPException(404, "필지 경계 정보를 찾을 수 없어유.")

    return {"pnu": pnu, "geometry": features[0].get("geometry")}


@app.post("/api/recommend")
def recommendations(body: SearchRequest):
    if body.sido not in ("충청북도", "충북"):
        raise HTTPException(400, "현재는 충청북도만 지원해유.")
    invalid_siguns = [sigun for sigun in body.sigun if sigun not in CHUNGBUK_SIGUN_CODES]
    if invalid_siguns:
        raise HTTPException(400, "지원하지 않는 시·군이에유.")
    invalid = [crop for crop in body.crops if crop not in CROP_CODES]
    if invalid:
        raise HTTPException(400, f"지원하지 않는 작물: {', '.join(invalid)}")
    try:
        return recommend(body.sigun, body.crops, body.budget_manwon)
    except Exception as exc:
        raise HTTPException(502, f"농지 데이터를 불러오지 못했어유: {exc}") from exc

