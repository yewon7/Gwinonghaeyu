import glob
import math

import pandas as pd
import requests
from bs4 import BeautifulSoup
from pyproj import Transformer

from crop_codes import CROP_CODES, SUITABILITY


# =========================================================
# 1. 충청북도 지역 코드
# =========================================================

CHUNGBUK_SIGUN_CODES = {
    "청주시": "43110",
    "충주시": "43130",
    "제천시": "43150",
    "보은군": "43720",
    "옥천군": "43730",
    "영동군": "43740",
    "증평군": "43745",
    "진천군": "43750",
    "괴산군": "43760",
    "음성군": "43770",
    "단양군": "43800",
}

REGION_ALIASES = {
    "청주": "청주시",
    "충주": "충주시",
    "제천": "제천시",
    "보은": "보은군",
    "옥천": "옥천군",
    "영동": "영동군",
    "증평": "증평군",
    "진천": "진천군",
    "괴산": "괴산군",
    "음성": "음성군",
    "단양": "단양군",
}


def normalize_sigun(name):
    name = name.strip()
    return REGION_ALIASES.get(name, name)


def unique_keep_order(items):
    return list(dict.fromkeys(items))


# =========================================================
# 2. 농지은행 좌표 → 흙토람 좌표
# =========================================================

transformer = Transformer.from_crs(
    "EPSG:4326",
    "EPSG:5186",
    always_xy=True
)


# =========================================================
# 3. 예산 점수
# =========================================================

def calculate_budget_score(price, budget):

    ratio = price / budget

    if ratio <= 0.60:
        return 20

    elif ratio <= 0.80:
        return 17

    elif ratio <= 0.90:
        return 14

    return 10


def get_budget_rule(price, budget):

    ratio = price / budget

    if ratio <= 0.60:
        return "예산의 60% 이하"

    elif ratio <= 0.80:
        return "예산의 80% 이하"

    elif ratio <= 0.90:
        return "예산의 90% 이하"

    return "예산 이하"


# =========================================================
# 4. 면적 점수
# =========================================================

def calculate_area_scores(farmlands):

    if not farmlands:
        return

    sorted_farmlands = sorted(
        farmlands,
        key=lambda x: x["area"]
    )

    count = len(sorted_farmlands)

    for index, farmland in enumerate(
        sorted_farmlands
    ):

        percentile = (
            index + 1
        ) / count

        if percentile <= 0.25:

            farmland["area_score"] = 6

            farmland["area_rule"] = (
                "후보 농지 면적 하위 25%"
            )

        elif percentile <= 0.50:

            farmland["area_score"] = 9

            farmland["area_rule"] = (
                "후보 농지 면적 25~50%"
            )

        elif percentile <= 0.75:

            farmland["area_score"] = 12

            farmland["area_rule"] = (
                "후보 농지 면적 50~75%"
            )

        else:

            farmland["area_score"] = 15

            farmland["area_rule"] = (
                "후보 농지 면적 상위 25%"
            )


# =========================================================
# 5. 두 좌표 사이 거리 계산
# =========================================================

def haversine(
    lat1,
    lng1,
    lat2,
    lng2
):

    R = 6371.0

    lat1 = math.radians(
        lat1
    )

    lat2 = math.radians(
        lat2
    )

    dlat = (
        lat2
        - lat1
    )

    dlng = math.radians(
        lng2 - lng1
    )

    a = (
        math.sin(
            dlat / 2
        ) ** 2
        +
        math.cos(lat1)
        * math.cos(lat2)
        * math.sin(
            dlng / 2
        ) ** 2
    )

    c = (
        2
        * math.atan2(
            math.sqrt(a),
            math.sqrt(1 - a)
        )
    )

    return R * c


# =========================================================
# 6. 산지유통센터 점수
# =========================================================

def calculate_apc_score(
    distance
):

    if distance is None:

        return (
            0,
            "관련 시설 없음"
        )

    if distance <= 3:

        return (
            13,
            "3km 이하"
        )

    elif distance <= 5:

        return (
            11,
            "3km 초과 ~ 5km 이하"
        )

    elif distance <= 10:

        return (
            8,
            "5km 초과 ~ 10km 이하"
        )

    elif distance <= 20:

        return (
            5,
            "10km 초과 ~ 20km 이하"
        )

    return (
        2,
        "20km 초과"
    )


# =========================================================
# 7. 가공사업장 점수
# =========================================================

def calculate_processing_score(
    distance
):

    if distance is None:

        return (
            0,
            "관련 시설 없음"
        )

    if distance <= 5:

        return (
            12,
            "5km 이하"
        )

    elif distance <= 10:

        return (
            10,
            "5km 초과 ~ 10km 이하"
        )

    elif distance <= 15:

        return (
            7,
            "10km 초과 ~ 15km 이하"
        )

    elif distance <= 25:

        return (
            4,
            "15km 초과 ~ 25km 이하"
        )

    return (
        2,
        "25km 초과"
    )


# =========================================================
# 8. 시설 CSV 불러오기
# =========================================================

def load_facility_data():

    csv_files = glob.glob(
        "data/geocoded/*좌표추가.csv"
    )

    apc_df = None

    processing_df = None

    for file_path in csv_files:

        try:

            df = pd.read_csv(
                file_path,
                encoding="utf-8-sig"
            )

        except Exception:

            continue

        if "주요품목" in df.columns:

            apc_df = df

        elif "상품명" in df.columns:

            processing_df = df

    return (
        apc_df,
        processing_df
    )


# =========================================================
# 9. 선택 작물과 시설 품목 일치
# =========================================================

def get_matching_crops(
    text,
    selected_crops
):

    text = str(text)

    matched = []

    for crop in selected_crops:

        if crop in text:

            matched.append(
                crop
            )

    return matched


# =========================================================
# 10. 가장 적합한 시설 탐색
# =========================================================

def find_best_facility(
    df,
    farmland_lat,
    farmland_lng,
    selected_crops,
    name_column,
    item_column
):

    if df is None:

        return None

    candidates = []

    for _, row in df.iterrows():

        if (
            "위도" not in row.index
            or
            "경도" not in row.index
        ):

            continue

        if (
            pd.isna(
                row["위도"]
            )
            or
            pd.isna(
                row["경도"]
            )
        ):

            continue

        matched_crops = (
            get_matching_crops(
                row[item_column],
                selected_crops
            )
        )

        if not matched_crops:

            continue

        try:

            facility_lat = float(
                row["위도"]
            )

            facility_lng = float(
                row["경도"]
            )

        except (
            TypeError,
            ValueError
        ):

            continue

        distance = haversine(

            farmland_lat,
            farmland_lng,

            facility_lat,
            facility_lng
        )

        candidates.append(
            {
                "name":
                    str(
                        row[
                            name_column
                        ]
                    ),

                "items":
                    str(
                        row[
                            item_column
                        ]
                    ),

                "distance":
                    distance,

                "matched_crops":
                    matched_crops,

                "match_count":
                    len(
                        matched_crops
                    )
            }
        )

    if not candidates:

        return None

    max_match_count = max(

        candidate[
            "match_count"
        ]

        for candidate
        in candidates
    )

    best_candidates = [

        candidate

        for candidate
        in candidates

        if candidate[
            "match_count"
        ] == max_match_count
    ]

    return min(

        best_candidates,

        key=lambda x:
            x["distance"]
    )


# =========================================================
# 11. 입지 점수
# =========================================================

def calculate_location_score(
    farmland,
    selected_crops,
    apc_df,
    processing_df
):

    apc = (
        find_best_facility(

            apc_df,

            farmland["lat"],
            farmland["lng"],

            selected_crops,

            "사업자명",
            "주요품목"
        )
    )

    if apc is None:

        apc_score = 0

        apc_rule = (
            "관련 시설 없음"
        )

    else:

        (
            apc_score,
            apc_rule
        ) = calculate_apc_score(
            apc["distance"]
        )

    processing = (
        find_best_facility(

            processing_df,

            farmland["lat"],
            farmland["lng"],

            selected_crops,

            "사업장명",
            "상품명"
        )
    )

    if processing is None:

        processing_score = 0

        processing_rule = (
            "관련 시설 없음"
        )

    else:

        (
            processing_score,
            processing_rule
        ) = (
            calculate_processing_score(
                processing[
                    "distance"
                ]
            )
        )

    return {

        "apc":
            apc,

        "apc_score":
            apc_score,

        "apc_rule":
            apc_rule,

        "processing":
            processing,

        "processing_score":
            processing_score,

        "processing_rule":
            processing_rule,

        "location_score":
            (
                apc_score
                +
                processing_score
            )
    }


# =========================================================
# 12. 흙토람 작물 적성 조회
# =========================================================

def get_crop_suitability(
    lng,
    lat,
    selected_crops
):

    x, y = (
        transformer.transform(
            lng,
            lat
        )
    )

    url = (
        "https://gis.naas.go.kr/"
        "geoserver/soilmap/ows"
    )

    bbox = (
        f"{x-1},{y-1},"
        f"{x+1},{y+1},"
        f"EPSG:5186"
    )

    params = {

        "service":
            "WFS",

        "version":
            "1.0.0",

        "request":
            "GetFeature",

        "typeName":
            "soilmap:CROP_PG_1",

        "outputFormat":
            "application/json",

        "bbox":
            bbox
    }

    try:

        response = (
            requests.get(
                url,
                params=params,
                timeout=10
            )
        )

        response.raise_for_status()

        data = response.json()

    except Exception:

        return {

            "soil":
                None,

            "crops":
                {},

            "all_suitable":
                False,

            "has_complete_data":
                False,

            "soil_score":
                0
        }

    features = data.get(
        "features",
        []
    )

    if not features:

        return {

            "soil":
                None,

            "crops":
                {},

            "all_suitable":
                False,

            "has_complete_data":
                False,

            "soil_score":
                0
        }

    properties = (
        features[0]
        .get(
            "properties",
            {}
        )
    )

    crop_results = {}

    crop_scores = []

    all_suitable = True

    has_complete_data = True

    for crop in selected_crops:

        crop_code = (
            CROP_CODES[crop]
        )

        suitability_code = (
            properties.get(
                crop_code
            )
        )

        if suitability_code is None:

            suitability_info = {

                "name":
                    "데이터 없음",

                "score":
                    0,

                "suitable":
                    False
            }

            has_complete_data = False

        else:

            suitability_info = (
                SUITABILITY.get(
                    suitability_code,
                    {
                        "name":
                            "데이터 없음",

                        "score":
                            0,

                        "suitable":
                            False
                    }
                )
            )

            if (
                suitability_info[
                    "name"
                ]
                == "데이터 없음"
            ):

                has_complete_data = False

        crop_results[crop] = {

            "code":
                suitability_code,

            "grade":
                suitability_info[
                    "name"
                ],

            "score":
                suitability_info[
                    "score"
                ],

            "suitable":
                suitability_info[
                    "suitable"
                ]
        }

        crop_scores.append(
            suitability_info[
                "score"
            ]
        )

        if not (
            suitability_info[
                "suitable"
            ]
        ):

            all_suitable = False

    soil_score = (

        min(
            crop_scores
        )

        if crop_scores

        else 0
    )

    return {

        "soil":
            properties.get(
                "soil_ksign"
            ),

        "crops":
            crop_results,

        "all_suitable":
            all_suitable,

        "has_complete_data":
            has_complete_data,

        "soil_score":
            soil_score
    }


# =========================================================
# 13. 농지은행에서 특정 시·군 조회
# =========================================================

def fetch_farmlands_for_sigun(
    session,
    sigun_name,
    sigun_code,
    budget
):

    map_url = (
        "https://www.fbo.or.kr/"
        "gis/map.do?menuId=091020"
    )

    url = (
        "https://www.fbo.or.kr/"
        "gis/selectSellList.do"
    )

    data = [

        (
            "schLndcgrCList",
            "D03080200"
        ),

        (
            "schLndcgrCList",
            "D03080100"
        ),

        (
            "schLndcgrCList",
            "D03080300"
        ),

        (
            "schLndcgrCList",
            "NH"
        ),

        (
            "schLndcgrCList",
            "DRT"
        ),

        (
            "currentPageNo",
            "1"
        ),

        (
            "schBizTp",
            "S"
        ),

        (
            "flndStock",
            "N"
        ),

        (
            "facility",
            "N"
        ),

        (
            "flndRent",
            "N"
        ),

        (
            "schSidoCd",
            "43"
        ),

        (
            "schSigunCd",
            sigun_code
        ),

        (
            "schEupmyonCd",
            ""
        ),

        (
            "schAmtMin",
            ""
        ),

        (
            "schAmtMax",
            ""
        ),

        (
            "schAreaMin",
            ""
        ),

        (
            "schAreaMax",
            ""
        )
    ]

    headers = {

        "Referer":
            map_url,

        "User-Agent":
            "Mozilla/5.0"
    }

    try:

        response = (
            session.post(
                url,
                data=data,
                headers=headers,
                timeout=15
            )
        )

        response.raise_for_status()

    except Exception as e:

        print(
            f"⚠ {sigun_name} "
            f"농지은행 조회 실패:",
            e
        )

        return []

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    rows = soup.select(
        "tr[data-pnu]"
    )

    candidates = []

    for row in rows:

        address_cell = (
            row.select_one(
                "td.addr"
            )
        )

        if address_cell is None:

            continue

        address = (
            address_cell.get(
                "data-full-text",
                ""
            )
            .strip()
        )

        # 묶음 요약 행 제외
        if " 외 " in address:

            continue

        cells = (
            row.find_all(
                "td"
            )
        )

        if len(cells) < 2:

            continue

        area_text = (
            cells[-2]
            .get_text(
                " ",
                strip=True
            )
        )

        price_text = (
            cells[-1]
            .get_text(
                " ",
                strip=True
            )
        )

        try:

            price = int(

                price_text
                .replace(",", "")
                .replace("원", "")
                .strip()
            )

        except ValueError:

            continue

        try:

            area = int(

                area_text
                .replace(",", "")
                .replace("㎡", "")
                .strip()
            )

        except ValueError:

            continue

        if price > budget:

            continue

        try:

            lat = float(
                row.get(
                    "data-lat"
                )
            )

            lng = float(
                row.get(
                    "data-lng"
                )
            )

        except (
            TypeError,
            ValueError
        ):

            continue

        candidates.append(
            {

                "sigun":
                    sigun_name,

                "address":
                    address,

                "price":
                    price,

                "area":
                    area,

                "area_text":
                    area_text,

                "pnu":
                    row.get(
                        "data-pnu"
                    ),

                "lat":
                    lat,

                "lng":
                    lng,

                "reqid":
                    row.get(
                        "data-reqid"
                    )
            }
        )

    return candidates


# =========================================================
# 14. 농지 중복 제거
# =========================================================

def deduplicate_farmlands(
    farmlands
):

    unique = {}

    for farmland in farmlands:

        pnu = farmland.get(
            "pnu"
        )

        reqid = farmland.get(
            "reqid"
        )

        if pnu:

            key = (
                "pnu",
                pnu
            )

        elif reqid:

            key = (
                "reqid",
                reqid
            )

        else:

            key = (
                "address",
                farmland["address"],
                farmland["price"],
                farmland["area"]
            )

        if key not in unique:

            unique[key] = (
                farmland
            )

    return list(
        unique.values()
    )


# =========================================================
# 15. 시설 결과 출력
# =========================================================

def print_facility_result(
    title,
    facility,
    score,
    max_score,
    rule,
    selected_crops
):

    print(title)

    if facility is None:

        print(
            "  관련 시설 없음"
        )

        print(
            f"  점수: "
            f"{score}/{max_score}"
        )

        return

    matched_text = (
        ", ".join(
            facility[
                "matched_crops"
            ]
        )
    )

    print(
        "  시설명:",
        facility["name"]
    )

    print(
        "  거리:",
        f'{facility["distance"]:.2f} km'
    )

    print(
        "  선택작물 일치:",
        f'{facility["match_count"]}'
        f'/'
        f'{len(selected_crops)}'
        f" ({matched_text})"
    )

    print(
        "  취급정보:",
        facility["items"]
    )

    print(
        "  적용 기준:",
        rule
    )

    print(
        "  점수:",
        f"{score}/{max_score}"
    )


# =========================================================
# 16. 점수 출력
# =========================================================

def print_score_result(
    farmland,
    budget
):

    print()

    print(
        "[📊 100점 추천 점수]"
    )

    print(
        "🌱 토양적성:",
        f'{farmland["soil_score"]}/40'
    )

    print(
        "💰 예산적합도:",
        f'{farmland["budget_score"]}/20'
    )

    print(
        "   기준:",
        get_budget_rule(
            farmland["price"],
            budget
        )
    )

    print(
        "📐 면적:",
        f'{farmland["area_score"]}/15'
    )

    print(
        "   기준:",
        farmland["area_rule"]
    )

    print(
        "📍 입지조건:",
        f'{farmland["location_score"]}/25'
    )

    print(
        "   ├ 산지유통센터:",
        f'{farmland["apc_score"]}/13'
    )

    print(
        "   └ 가공사업장:",
        f'{farmland["processing_score"]}/12'
    )

    print(
        "--------------------------------"
    )

    print(
        "⭐ 종합점수:",
        f'{farmland["total_score"]}/100'
    )


# =========================================================
# 17. 메인 실행
# =========================================================

def main():

    print()

    print(
        "============================================"
    )

    print(
        "        🌱 맞춤 농지 추천 시스템"
    )

    print(
        "============================================"
    )

    print()

    apc_df, processing_df = (
        load_facility_data()
    )

    print(
        "📊 농지 추천점수 기준"
    )

    print(
        "🌱 작물·토양 적합성    40점"
    )

    print(
        "💰 예산 적합성         20점"
    )

    print(
        "📐 농지 면적           15점"
    )

    print(
        "📍 입지조건            25점"
    )

    print(
        "   ├ 산지유통센터      13점"
    )

    print(
        "   └ 농식품가공시설    12점"
    )

    print(
        "--------------------------------------------"
    )

    print(
        "⭐ 총점               100점"
    )

    print()

    print(
        "※ 정책지원은 점수에 "
        "포함하지 않고 별도로 매칭합니다."
    )

    print()


    # =====================================================
    # 지역 입력
    # =====================================================

    print(
        "[현재 지원 지역]"
    )

    print(
        ", ".join(
            CHUNGBUK_SIGUN_CODES.keys()
        )
    )

    print()

    sido_input = input(
        "희망 시도를 입력하세요 "
        "(예: 충청북도): "
    ).strip()

    if sido_input not in [
        "충청북도",
        "충북"
    ]:

        print()

        print(
            "현재 테스트 버전은 "
            "충청북도만 지원합니다."
        )

        return


    # =====================================================
    # ★ 여러 시·군 선택
    # =====================================================

    sigun_input = input(
        "희망 시·군을 입력하세요 "
        "(여러 개 선택 시 쉼표 사용, "
        "예: 영동군,괴산군 / 전체): "
    ).strip()


    if sigun_input in [
        "전체",
        "전체선택",
        "모두"
    ]:

        selected_siguns = list(
            CHUNGBUK_SIGUN_CODES.keys()
        )

    else:

        selected_siguns = [

            normalize_sigun(
                name
            )

            for name
            in sigun_input.split(",")

            if name.strip()
        ]


        # 같은 지역 중복 입력 제거
        selected_siguns = (
            unique_keep_order(
                selected_siguns
            )
        )


    if not selected_siguns:

        print(
            "시·군을 하나 이상 "
            "선택해주세요."
        )

        return


    invalid_siguns = [

        sigun

        for sigun
        in selected_siguns

        if sigun not in (
            CHUNGBUK_SIGUN_CODES
        )
    ]


    if invalid_siguns:

        print()

        print(
            "지원하지 않는 지역이 있습니다:",
            ", ".join(
                invalid_siguns
            )
        )

        return


    # =====================================================
    # 작물 입력
    # =====================================================

    crop_input = input(
        "희망 작물을 입력하세요 "
        "(예: 사과,복숭아,포도): "
    )


    selected_crops = [

        crop.strip()

        for crop
        in crop_input.split(",")

        if crop.strip()
    ]


    # 같은 작물 중복 입력 제거
    selected_crops = (
        unique_keep_order(
            selected_crops
        )
    )


    if not selected_crops:

        print(
            "작물을 하나 이상 "
            "입력해주세요."
        )

        return


    invalid_crops = [

        crop

        for crop
        in selected_crops

        if crop not in (
            CROP_CODES
        )
    ]


    if invalid_crops:

        print()

        print(
            "지원하지 않는 작물이 있습니다:",
            ", ".join(
                invalid_crops
            )
        )

        return


    # =====================================================
    # 예산 입력
    # =====================================================

    try:

        budget_manwon = int(

            input(
                "예산을 만원 단위로 "
                "입력하세요: "
            )
            .replace(",", "")
        )

    except ValueError:

        print(
            "예산은 숫자로 입력해주세요."
        )

        return


    budget = (
        budget_manwon
        * 10000
    )


    print()

    print(
        "============================================"
    )

    print(
        "🔎 검색 조건"
    )

    print(
        "============================================"
    )


    print(
        "지역:",
        "충청북도 "
        + ", ".join(
            selected_siguns
        )
    )


    print(
        "선택 작물:",
        ", ".join(
            selected_crops
        )
    )


    print(
        "예산:",
        f"{budget:,} 원"
    )

    print()


    # =====================================================
    # 농지은행 접속
    # =====================================================

    session = requests.Session()


    map_url = (
        "https://www.fbo.or.kr/"
        "gis/map.do?menuId=091020"
    )


    try:

        session.get(
            map_url,
            timeout=10
        )

    except Exception as e:

        print(
            "농지은행 접속 오류:",
            e
        )

        return


    # =====================================================
    # ★ 선택한 시·군 각각 조회
    # =====================================================

    all_budget_candidates = []


    print(
        "📡 선택 지역 매물 조회 중..."
    )


    for sigun_name in selected_siguns:

        sigun_code = (
            CHUNGBUK_SIGUN_CODES[
                sigun_name
            ]
        )


        region_candidates = (
            fetch_farmlands_for_sigun(

                session,

                sigun_name,

                sigun_code,

                budget
            )
        )


        print(
            f"- {sigun_name}: "
            f"예산 이내 "
            f"{len(region_candidates)}개"
        )


        all_budget_candidates.extend(
            region_candidates
        )


    # =====================================================
    # PNU 기준 중복 제거
    # =====================================================

    before_dedup = len(
        all_budget_candidates
    )


    budget_candidates = (
        deduplicate_farmlands(
            all_budget_candidates
        )
    )


    duplicate_count = (
        before_dedup
        -
        len(
            budget_candidates
        )
    )


    print()


    print(
        "예산을 통과한 농지:",
        f"{len(budget_candidates)}개"
    )


    if duplicate_count > 0:

        print(
            "중복 제거:",
            f"{duplicate_count}개"
        )


    if not budget_candidates:

        print()

        print(
            "현재 조건에 맞는 "
            "농지은행 매물이 없습니다."
        )

        return


    # =====================================================
    # 토양 데이터 검사
    # =====================================================

    valid_candidates = []

    excluded_candidates = []


    for farmland in budget_candidates:

        soil_result = (
            get_crop_suitability(

                farmland["lng"],

                farmland["lat"],

                selected_crops
            )
        )


        farmland["soil"] = (
            soil_result[
                "soil"
            ]
        )


        farmland[
            "crop_results"
        ] = (
            soil_result[
                "crops"
            ]
        )


        farmland[
            "soil_score"
        ] = (
            soil_result[
                "soil_score"
            ]
        )


        farmland[
            "all_suitable"
        ] = (
            soil_result[
                "all_suitable"
            ]
        )


        if not (
            soil_result[
                "has_complete_data"
            ]
        ):

            farmland[
                "exclusion_reason"
            ] = (
                "선택 작물의 "
                "흙토람 데이터 부족"
            )


            excluded_candidates.append(
                farmland
            )

            continue


        valid_candidates.append(
            farmland
        )


    # =====================================================
    # 여러 지역의 유효 후보 전체를 합쳐 면적 평가
    # =====================================================

    calculate_area_scores(
        valid_candidates
    )


    # =====================================================
    # 100점 계산
    # =====================================================

    strict_candidates = []

    alternative_candidates = []

    reference_candidates = []


    for farmland in valid_candidates:

        farmland[
            "budget_score"
        ] = (
            calculate_budget_score(

                farmland["price"],

                budget
            )
        )


        location_result = (
            calculate_location_score(

                farmland,

                selected_crops,

                apc_df,

                processing_df
            )
        )


        farmland["apc"] = (
            location_result[
                "apc"
            ]
        )


        farmland[
            "apc_score"
        ] = (
            location_result[
                "apc_score"
            ]
        )


        farmland[
            "apc_rule"
        ] = (
            location_result[
                "apc_rule"
            ]
        )


        farmland[
            "processing"
        ] = (
            location_result[
                "processing"
            ]
        )


        farmland[
            "processing_score"
        ] = (
            location_result[
                "processing_score"
            ]
        )


        farmland[
            "processing_rule"
        ] = (
            location_result[
                "processing_rule"
            ]
        )


        farmland[
            "location_score"
        ] = (
            location_result[
                "location_score"
            ]
        )


        suitable_count = 0


        for crop in selected_crops:

            crop_result = (
                farmland[
                    "crop_results"
                ][crop]
            )


            if crop_result[
                "suitable"
            ]:

                suitable_count += 1


        farmland[
            "suitable_count"
        ] = suitable_count


        farmland[
            "selected_crop_count"
        ] = len(
            selected_crops
        )


        farmland[
            "total_score"
        ] = (

            farmland[
                "soil_score"
            ]

            +

            farmland[
                "budget_score"
            ]

            +

            farmland[
                "area_score"
            ]

            +

            farmland[
                "location_score"
            ]
        )


        # 모든 작물 최적지/적지
        if farmland[
            "all_suitable"
        ]:

            farmland[
                "recommendation_type"
            ] = "엄격 추천"


            strict_candidates.append(
                farmland
            )


        # 일부 작물만 적합
        elif suitable_count > 0:

            farmland[
                "recommendation_type"
            ] = "대안 추천"


            alternative_candidates.append(
                farmland
            )


        # 모두 가능지 이하
        else:

            farmland[
                "recommendation_type"
            ] = "참고 후보"


            reference_candidates.append(
                farmland
            )


    # =====================================================
    # 정렬
    # =====================================================

    strict_candidates.sort(

        key=lambda x: (

            -x[
                "total_score"
            ],

            x[
                "price"
            ],

            -x[
                "area"
            ]
        )
    )


    alternative_candidates.sort(

        key=lambda x: (

            -x[
                "suitable_count"
            ],

            -x[
                "total_score"
            ],

            x[
                "price"
            ]
        )
    )


    reference_candidates.sort(

        key=lambda x: (

            -x[
                "soil_score"
            ],

            -x[
                "total_score"
            ],

            x[
                "price"
            ]
        )
    )


    # =====================================================
    # 결과 요약
    # =====================================================

    print()

    print(
        "#" * 65
    )

    print(
        "📋 분석 결과 요약"
    )

    print(
        "#" * 65
    )


    print(
        "선택 지역:",
        ", ".join(
            selected_siguns
        )
    )


    print(
        f"예산 통과: "
        f"{len(budget_candidates)}개"
    )


    print(
        f"분석 가능: "
        f"{len(valid_candidates)}개"
    )


    print(
        f"데이터 부족 제외: "
        f"{len(excluded_candidates)}개"
    )


    print(
        f"🌱 엄격 추천: "
        f"{len(strict_candidates)}개"
    )


    print(
        f"🔎 대안 추천: "
        f"{len(alternative_candidates)}개"
    )


    print(
        f"📎 참고 후보: "
        f"{len(reference_candidates)}개"
    )


    # =====================================================
    # 엄격 추천
    # =====================================================

    if strict_candidates:

        print()

        print(
            "#" * 65
        )

        print(
            "🌱 최종 추천 농지"
        )

        print(
            "#" * 65
        )


        for index, farmland in enumerate(

            strict_candidates,

            start=1
        ):

            print()

            print(
                "=" * 65
            )


            print(
                f"🌱 [추천 {index}]"
            )


            print(
                "지역:",
                farmland[
                    "sigun"
                ]
            )


            print(
                farmland[
                    "address"
                ]
            )


            print(
                "가격:",
                f'{farmland["price"]:,} 원'
            )


            print(
                "면적:",
                farmland[
                    "area_text"
                ]
            )


            print()

            print(
                "[🌾 작물별 적성]"
            )


            for crop in selected_crops:

                result = (
                    farmland[
                        "crop_results"
                    ][crop]
                )


                print(
                    f"- {crop}: "
                    f'{result["grade"]} ✅'
                )


            print()

            print(
                "[📍 입지 분석]"
            )


            print_facility_result(

                "📦 산지유통센터",

                farmland[
                    "apc"
                ],

                farmland[
                    "apc_score"
                ],

                13,

                farmland[
                    "apc_rule"
                ],

                selected_crops
            )


            print()


            print_facility_result(

                "🏭 농식품 가공사업장",

                farmland[
                    "processing"
                ],

                farmland[
                    "processing_score"
                ],

                12,

                farmland[
                    "processing_rule"
                ],

                selected_crops
            )


            print_score_result(

                farmland,

                budget
            )


    # =====================================================
    # 대안 추천
    # =====================================================

    elif alternative_candidates:

        print()

        print(
            "#" * 65
        )


        print(
            "🔎 엄격 조건을 만족하는 "
            "농지는 없습니다."
        )


        print(
            "대신 일부 작물에 적합한 "
            "농지를 추천합니다."
        )


        print(
            "#" * 65
        )


        for index, farmland in enumerate(

            alternative_candidates[
                :5
            ],

            start=1
        ):

            print()

            print(
                "=" * 65
            )


            print(
                f"🔎 [대안 추천 {index}]"
            )


            print(
                "지역:",
                farmland[
                    "sigun"
                ]
            )


            print(
                farmland[
                    "address"
                ]
            )


            print(
                "가격:",
                f'{farmland["price"]:,} 원'
            )


            print(
                "면적:",
                farmland[
                    "area_text"
                ]
            )


            print(
                "토양:",
                farmland[
                    "soil"
                ]
            )


            print()


            print(
                "적합 작물:",
                f'{farmland["suitable_count"]}'
                f'/'
                f'{farmland["selected_crop_count"]}'
            )


            print()

            print(
                "[🌾 작물별 적성]"
            )


            unsuitable_crops = []


            for crop in selected_crops:

                result = (
                    farmland[
                        "crop_results"
                    ][crop]
                )


                if result[
                    "suitable"
                ]:

                    mark = "✅"


                elif (
                    result[
                        "grade"
                    ]
                    == "가능지"
                ):

                    mark = "△"


                else:

                    mark = "❌"


                if not result[
                    "suitable"
                ]:

                    unsuitable_crops.append(
                        crop
                    )


                print(
                    f"- {crop}: "
                    f'{result["grade"]} '
                    f"{mark}"
                )


            print()

            print(
                "⚠ 대안 추천 사유"
            )


            print(
                "엄격조건 미충족 작물:",
                ", ".join(
                    unsuitable_crops
                )
            )


            print()

            print(
                "[📍 입지 분석]"
            )


            print_facility_result(

                "📦 산지유통센터",

                farmland[
                    "apc"
                ],

                farmland[
                    "apc_score"
                ],

                13,

                farmland[
                    "apc_rule"
                ],

                selected_crops
            )


            print()


            print_facility_result(

                "🏭 농식품 가공사업장",

                farmland[
                    "processing"
                ],

                farmland[
                    "processing_score"
                ],

                12,

                farmland[
                    "processing_rule"
                ],

                selected_crops
            )


            print_score_result(

                farmland,

                budget
            )


    # =====================================================
    # 참고 후보
    # =====================================================

    elif reference_candidates:

        print()

        print(
            "#" * 65
        )


        print(
            "📎 선택한 작물 중 "
            "최적지 또는 적지인 "
            "농지가 없습니다."
        )


        print(
            "가능지 이하의 농지를 "
            "참고 후보로 보여드립니다."
        )


        print(
            "#" * 65
        )


        for index, farmland in enumerate(

            reference_candidates[
                :5
            ],

            start=1
        ):

            print()

            print(
                "=" * 65
            )


            print(
                f"📎 [참고 후보 {index}]"
            )


            print(
                "지역:",
                farmland[
                    "sigun"
                ]
            )


            print(
                farmland[
                    "address"
                ]
            )


            print(
                "가격:",
                f'{farmland["price"]:,} 원'
            )


            print(
                "면적:",
                farmland[
                    "area_text"
                ]
            )


            print()

            print(
                "[🌾 작물별 적성]"
            )


            for crop in selected_crops:

                result = (
                    farmland[
                        "crop_results"
                    ][crop]
                )


                if (
                    result[
                        "grade"
                    ]
                    == "가능지"
                ):

                    mark = "△"


                else:

                    mark = "❌"


                print(
                    f"- {crop}: "
                    f'{result["grade"]} '
                    f"{mark}"
                )


            print()


            print(
                "⚠ 해당 농지는 "
                "엄격추천 또는 대안추천 "
                "조건을 충족하지 않습니다."
            )


            print_score_result(

                farmland,

                budget
            )


    else:

        print()

        print(
            "추천 가능한 농지가 없습니다."
        )


    # =====================================================
    # 데이터 부족 농지
    # =====================================================

    if excluded_candidates:

        print()

        print(
            "=" * 65
        )


        print(
            "⚠ 토양 데이터 부족으로 "
            "분석에서 제외된 농지"
        )


        print(
            "=" * 65
        )


        for farmland in (
            excluded_candidates
        ):

            print(
                "-",
                f"[{farmland['sigun']}]",
                farmland[
                    "address"
                ]
            )


        print()


        print(
            "해당 농지는 선택 작물의 "
            "흙토람 데이터가 충분하지 않아 "
            "추천점수를 계산하지 않았습니다."
        )


    print()

    print(
        "=" * 65
    )


    print(
        "🏦 정책·지원"
    )


    print(
        "=" * 65
    )


    print(
        "정책·지원은 농지 추천점수에 "
        "포함하지 않습니다."
    )


    print(
        "추후 사용자 조건에 따라 "
        "별도 매칭할 수 있습니다."
    )

if __name__ == "__main__":
    main()