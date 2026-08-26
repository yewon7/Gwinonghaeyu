# 귀농해유

충청북도 귀농 희망자를 위한 맞춤 농지 추천 웹서비스입니다. 기존 100점 추천 기준(토양 40, 예산 20, 면적 15, 입지 25)을 유지하며 농지은행·흙토람·충북 공공데이터를 사용합니다.

## 실행 방법

프로젝트 루트에 `.env` 파일을 만들고 카카오맵 JavaScript 키와 브이월드 API 키를 넣습니다.

```
KAKAO_MAP_KEY=발급받은_카카오맵_JavaScript_키
VWORLD_API_KEY=발급받은_브이월드_API_키
```

```bash
python3 -m pip install -r requirements.txt
python3 -m uvicorn app:app --reload
```

브라우저에서 `http://127.0.0.1:8000`을 엽니다.

실제 추천 검색에는 농지은행과 흙토람 접속을 위한 인터넷 연결이 필요합니다. 지도 위 필지 경계선은 `/api/parcel-boundary` 엔드포인트를 통해 브이월드 Data API(LP_PA_CBND_BUBUN)를 서버에서만 호출해 표시합니다.
