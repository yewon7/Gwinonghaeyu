import glob
import math
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup
from pyproj import Transformer

from crop_codes import CROP_CODES, SUITABILITY

BASE = Path(__file__).resolve().parent
CHUNGBUK_SIGUN_CODES = {"청주시":"43110","충주시":"43130","제천시":"43150","보은군":"43720","옥천군":"43730","영동군":"43740","증평군":"43745","진천군":"43750","괴산군":"43760","음성군":"43770","단양군":"43800"}
transformer = Transformer.from_crs("EPSG:4326", "EPSG:5186", always_xy=True)


def budget_score(price, budget):
    ratio = price / budget
    return 20 if ratio <= .6 else 17 if ratio <= .8 else 14 if ratio <= .9 else 10


def budget_rule(price, budget):
    ratio = price / budget
    return "예산의 60% 이하" if ratio <= .6 else "예산의 80% 이하" if ratio <= .8 else "예산의 90% 이하" if ratio <= .9 else "예산 이하"


def area_scores(items):
    ordered = sorted(items, key=lambda x: x["area"])
    for i, item in enumerate(ordered):
        p = (i + 1) / len(ordered)
        item["area_score"], item["area_rule"] = ((6,"후보 농지 면적 하위 25%") if p <= .25 else (9,"후보 농지 면적 25~50%") if p <= .5 else (12,"후보 농지 면적 50~75%") if p <= .75 else (15,"후보 농지 면적 상위 25%"))


def haversine(a,b,c,d):
    a,c,dl = map(math.radians, (a,c,d-b)); da=c-a
    x=math.sin(da/2)**2+math.cos(a)*math.cos(c)*math.sin(dl/2)**2
    return 6371 * 2 * math.atan2(math.sqrt(x), math.sqrt(1-x))


def load_facilities():
    apc=processing=None
    for path in glob.glob(str(BASE / "data/geocoded/*좌표추가.csv")):
        try: df=pd.read_csv(path, encoding="utf-8-sig")
        except Exception: continue
        if "주요품목" in df: apc=df
        elif "상품명" in df: processing=df
    return apc, processing


def matches(text, crops):
    text=str(text)
    # 짧은 작물명이 다른 단어에 끼어드는 대표 오인식을 막는다.
    blocked={"배":["배추"],"밀":["메밀"],"콩":["땅콩"],"조":["복숭아병조림"]}
    return [c for c in crops if c in text and not any(word in text for word in blocked.get(c, []))]


def best_facility(df, lat, lng, crops, name_col, item_col):
    if df is None: return None
    found=[]
    for _, row in df.iterrows():
        if pd.isna(row.get("위도")) or pd.isna(row.get("경도")): continue
        hit=matches(row.get(item_col,""), crops)
        if not hit: continue
        try: distance=haversine(lat,lng,float(row["위도"]),float(row["경도"]))
        except (TypeError,ValueError): continue
        found.append({"name":str(row.get(name_col,"-")),"items":str(row.get(item_col,"")),"distance":round(distance,2),"matched_crops":hit,"match_count":len(hit)})
    return min(found, key=lambda x:(-x["match_count"],x["distance"])) if found else None


def facility_scores(farm,crops,apc_df,processing_df):
    apc=best_facility(apc_df,farm["lat"],farm["lng"],crops,"사업자명","주요품목")
    proc=best_facility(processing_df,farm["lat"],farm["lng"],crops,"사업장명","상품명")
    ad=apc["distance"] if apc else None; pdist=proc["distance"] if proc else None
    aps,ar=(0,"관련 시설 없음") if ad is None else (13,"3km 이하") if ad<=3 else (11,"3~5km") if ad<=5 else (8,"5~10km") if ad<=10 else (5,"10~20km") if ad<=20 else (2,"20km 초과")
    ps,pr=(0,"관련 시설 없음") if pdist is None else (12,"5km 이하") if pdist<=5 else (10,"5~10km") if pdist<=10 else (7,"10~15km") if pdist<=15 else (4,"15~25km") if pdist<=25 else (2,"25km 초과")
    return {"apc":apc,"apc_score":aps,"apc_rule":ar,"processing":proc,"processing_score":ps,"processing_rule":pr,"location_score":aps+ps}


def suitability(lng,lat,crops):
    x,y=transformer.transform(lng,lat); bbox=f"{x-1},{y-1},{x+1},{y+1},EPSG:5186"
    try:
        res=requests.get("https://gis.naas.go.kr/geoserver/soilmap/ows",params={"service":"WFS","version":"1.0.0","request":"GetFeature","typeName":"soilmap:CROP_PG_1","outputFormat":"application/json","bbox":bbox},timeout=10)
        props=res.json().get("features",[])[0].get("properties",{})
    except Exception: return {"complete":False,"soil":None,"crops":{},"score":0,"all":False}
    results={}; scores=[]; complete=True; all_ok=True
    for crop in crops:
        code=props.get(CROP_CODES[crop]); info=SUITABILITY.get(code,{"name":"데이터 없음","score":0,"suitable":False})
        if code is None or info["name"]=="데이터 없음": complete=False
        results[crop]={"grade":info["name"],"score":info["score"],"suitable":info["suitable"]}; scores.append(info["score"]); all_ok &= info["suitable"]
    return {"complete":complete,"soil":props.get("soil_ksign"),"crops":results,"score":min(scores) if scores else 0,"all":all_ok}


def fetch_farmlands(sigun,budget):
    session=requests.Session(); map_url="https://www.fbo.or.kr/gis/map.do?menuId=091020"; session.get(map_url,timeout=10)
    data=[("schLndcgrCList",x) for x in ("D03080200","D03080100","D03080300","NH","DRT")]+[("currentPageNo","1"),("schBizTp","S"),("flndStock","N"),("facility","N"),("flndRent","N"),("schSidoCd","43"),("schSigunCd",CHUNGBUK_SIGUN_CODES[sigun]),("schEupmyonCd",""),("schAmtMin",""),("schAmtMax",""),("schAreaMin",""),("schAreaMax","")]
    res=session.post("https://www.fbo.or.kr/gis/selectSellList.do",data=data,headers={"Referer":map_url,"User-Agent":"Mozilla/5.0"},timeout=15); res.raise_for_status()
    items=[]
    for row in BeautifulSoup(res.text,"html.parser").select("tr[data-pnu]"):
        cell=row.select_one("td.addr"); cells=row.find_all("td")
        if cell is None or len(cells)<2: continue
        address=cell.get("data-full-text","").strip()
        if " 외 " in address: continue
        try: area=int(cells[-2].get_text(strip=True).replace(",","").replace("㎡","")); price=int(cells[-1].get_text(strip=True).replace(",","").replace("원","")); lat=float(row.get("data-lat")); lng=float(row.get("data-lng"))
        except (TypeError,ValueError): continue
        if price<=budget: items.append({"address":address,"area":area,"area_text":f"{area:,}㎡","price":price,"lat":lat,"lng":lng,"pnu":row.get("data-pnu"),"reqid":row.get("data-reqid")})
    return items


def clean(item):
    return dict(item)


def deduplicate_farmlands(items):
    unique = {}
    for item in items:
        key = item.get("pnu") or (item["address"], item["price"], item["area"])
        unique[key] = item
    return list(unique.values())


def recommend(siguns,crops,budget_manwon):
    budget=budget_manwon*10000
    raw=[]
    for sigun in siguns:
        raw.extend(fetch_farmlands(sigun,budget))
    raw=deduplicate_farmlands(raw); valid=[]; excluded=[]
    for farm in raw:
        soil=suitability(farm["lng"],farm["lat"],crops); farm.update({"soil":soil["soil"],"crop_results":soil["crops"],"soil_score":soil["score"],"all_suitable":soil["all"]})
        (valid if soil["complete"] else excluded).append(farm)
    if valid: area_scores(valid)
    apc_df,proc_df=load_facilities(); groups={"strict":[],"alternative":[],"reference":[]}
    for farm in valid:
        farm.update(facility_scores(farm,crops,apc_df,proc_df)); farm["budget_score"]=budget_score(farm["price"],budget); farm["budget_rule"]=budget_rule(farm["price"],budget)
        farm["suitable_count"]=sum(v["suitable"] for v in farm["crop_results"].values()); farm["selected_crop_count"]=len(crops); farm["total_score"]=farm["soil_score"]+farm["budget_score"]+farm["area_score"]+farm["location_score"]
        key="strict" if farm["all_suitable"] else "alternative" if farm["suitable_count"] else "reference"; farm["recommendation_type"]={"strict":"엄격 추천","alternative":"대안 추천","reference":"참고 후보"}[key]; groups[key].append(clean(farm))
    for key in groups: groups[key].sort(key=lambda x:(-x["total_score"],x["price"],-x["area"]))
    return {"query":{"sido":"충청북도","sigun":siguns,"crops":crops,"budget_manwon":budget_manwon},"summary":{"budget_passed":len(raw),"analyzed":len(valid),"excluded":len(excluded),"strict":len(groups["strict"]),"alternative":len(groups["alternative"]),"reference":len(groups["reference"])},"results":groups}

