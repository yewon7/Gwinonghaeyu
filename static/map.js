const CHUNGBUK_SW = {lat: 36.02, lng: 127.25};
const CHUNGBUK_NE = {lat: 37.28, lng: 128.35};

const GRADE_META = {
    strict: {cls: 'grade-strict', label: '엄격 추천', color: '#2e7d46'},
    alternative: {cls: 'grade-alt', label: '대안 추천', color: '#e08a2e'},
    reference: {cls: 'grade-ref', label: '참고 후보', color: '#8f8b76'},
};

let map = null;
let mapMarkers = [];
let mapPolygons = [];
let markersByKey = {};
let activeInfo = null;
let kakaoReady = false;
let kakaoReadyQueue = [];

function onKakaoReady(fn) {
    if (kakaoReady) fn();
    else kakaoReadyQueue.push(fn);
}

if (window.kakao && window.kakao.maps) {
    kakao.maps.load(() => {
        kakaoReady = true;
        kakaoReadyQueue.forEach(fn => fn());
        kakaoReadyQueue = [];
    });
}

function chungbukBounds() {
    return new kakao.maps.LatLngBounds(
        new kakao.maps.LatLng(CHUNGBUK_SW.lat, CHUNGBUK_SW.lng),
        new kakao.maps.LatLng(CHUNGBUK_NE.lat, CHUNGBUK_NE.lng)
    );
}

function ensureMap() {
    onKakaoReady(() => {
        const container = document.getElementById('resultMap');
        if (!container) return;
        if (!map) {
            map = new kakao.maps.Map(container, {center: new kakao.maps.LatLng(36.63, 127.75), level: 9});
            map.setBounds(chungbukBounds());
            kakao.maps.event.addListener(map, 'click', () => closeInfoWindow());
        } else {
            map.relayout();
        }
    });
}

function clearMap() {
    mapMarkers.forEach(m => m.setMap(null));
    mapMarkers = [];
    mapPolygons.forEach(p => p.setMap(null));
    mapPolygons = [];
    markersByKey = {};
    closeInfoWindow();
}

function closeInfoWindow() {
    if (activeInfo) {
        activeInfo.setMap(null);
        activeInfo = null;
    }
}

function renderMapMarkers() {
    onKakaoReady(() => {
        if (!map || !data) return;
        clearMap();
        const bounds = new kakao.maps.LatLngBounds();
        let any = false;
        ['strict', 'alternative', 'reference'].forEach(group => {
            (data.results[group] || []).forEach((f, i) => {
                if (f.lat == null || f.lng == null) return;
                any = true;
                const pos = new kakao.maps.LatLng(f.lat, f.lng);
                bounds.extend(pos);
                addMarker(f, group, i, pos);
                if (f.pnu) loadParcelBoundary(f, group);
            });
        });
        if (any) map.setBounds(bounds);
        else map.setBounds(chungbukBounds());
    });
}

function addMarker(f, group, i, pos) {
    const meta = GRADE_META[group];
    const el = document.createElement('div');
    el.className = `map-marker ${meta.cls}`;
    el.textContent = `${i + 1}위`;
    el.title = `${meta.label} ${i + 1}위 · ${f.address}`;
    el.addEventListener('click', (e) => {
        e.stopPropagation();
        openInfoWindow(f, group, i, pos);
        selectTabAndScroll(group, i, keyOf(f));
    });
    const overlay = new kakao.maps.CustomOverlay({position: pos, content: el, yAnchor: 1, zIndex: 3});
    overlay.setMap(map);
    mapMarkers.push(overlay);
    markersByKey[keyOf(f)] = {pos, farm: f, group, i};
}

function focusMarker(key) {
    onKakaoReady(() => {
        const entry = markersByKey[key];
        if (!map || !entry) return;
        const container = document.getElementById('resultMap');
        if (container) container.scrollIntoView({behavior: 'smooth', block: 'center'});
        if (map.getLevel() > 4) map.setLevel(4);
        map.panTo(entry.pos);
        openInfoWindow(entry.farm, entry.group, entry.i, entry.pos);
    });
}

function openInfoWindow(f, group, i, pos) {
    closeInfoWindow();
    const meta = GRADE_META[group];
    const cropTags = Object.entries(f.crop_results || {}).map(([k, v]) => `<span>${k} · ${v.grade}</span>`).join('');
    const box = document.createElement('div');
    box.className = 'map-infowindow';
    box.innerHTML = `<button class="iw-close" type="button">×</button><b class="iw-rank">${meta.label} ${i + 1}위</b><h4>${f.address}</h4><p>${(f.price / 10000).toLocaleString()}만원 · 총점 ${f.total_score}/100</p><div class="iw-crops">${cropTags}</div>`;
    box.querySelector('.iw-close').onclick = (e) => {
        e.stopPropagation();
        closeInfoWindow();
    };
    activeInfo = new kakao.maps.CustomOverlay({position: pos, content: box, yAnchor: 1.35, zIndex: 5});
    activeInfo.setMap(map);
}

async function loadParcelBoundary(f, group) {
    try {
        const res = await fetch(`/api/parcel-boundary?pnu=${encodeURIComponent(f.pnu)}`);
        if (!res.ok) return;
        const body = await res.json();
        drawParcelPolygon(body.geometry, group);
    } catch (err) {
        /* 필지 경계를 못 불러와도 마커는 그대로 유지 */
    }
}

function drawParcelPolygon(geometry, group) {
    if (!geometry) return;
    const meta = GRADE_META[group];
    const rings = geometry.type === 'Polygon' ? [geometry.coordinates]
        : geometry.type === 'MultiPolygon' ? geometry.coordinates
        : [];
    rings.forEach(polygon => {
        const outer = polygon[0];
        if (!outer) return;
        const path = outer.map(([lng, lat]) => new kakao.maps.LatLng(lat, lng));
        const shape = new kakao.maps.Polygon({
            path,
            strokeWeight: 2,
            strokeColor: meta.color,
            strokeOpacity: 0.85,
            fillColor: meta.color,
            fillOpacity: 0.22,
        });
        shape.setMap(map);
        mapPolygons.push(shape);
    });
}

function selectTabAndScroll(group, i, key) {
    if (current !== group) {
        current = group;
        $$('.tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === group));
        renderCards();
    }
    requestAnimationFrame(() => {
        const target = [...$$('.card')].find(c => c.dataset.key === key);
        if (!target) return;
        $$('.card').forEach(c => c.classList.remove('card-highlight'));
        target.classList.add('card-highlight');
        target.scrollIntoView({behavior: 'smooth', block: 'center'});
        setTimeout(() => target.classList.remove('card-highlight'), 2400);
    });
}
