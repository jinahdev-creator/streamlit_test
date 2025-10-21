import streamlit as st
import requests
import pandas as pd
from pyproj import Proj, transform

# --- 페이지 설정 (가장 먼저 실행) ---
st.set_page_config(
    page_title="스마트 통합 검색",
    page_icon="💡",
    layout="wide"
)

# --- API 키 로딩 ---
try:
    TMAP_API_KEY = st.secrets["TMAP_API_KEY"]
    NAVER_CLIENT_ID = st.secrets["NAVER_CLIENT_ID"]
    NAVER_CLIENT_SECRET = st.secrets["NAVER_CLIENT_SECRET"]
    NCP_CLIENT_ID = st.secrets["NCP_CLIENT_ID"]
    NCP_CLIENT_SECRET = st.secrets["NCP_CLIENT_SECRET"]
except (KeyError, FileNotFoundError):
    st.error("오류: API 키를 모두 찾을 수 없습니다. .streamlit/secrets.toml 파일을 확인해주세요.")
    st.stop()

# --- 헬퍼 함수: 좌표계 변환 ---
def convert_tm_to_wgs84(x, y):
    """네이버 지역 검색 API의 TM 좌표를 위경도(WGS84)로 변환"""
    try:
        proj_tm = Proj('EPSG:2097')
        proj_wgs84 = Proj('EPSG:4326')
        x_val, y_val = int(x), int(y)
        lon, lat = transform(proj_tm, proj_wgs84, x_val, y_val)
        return lat, lon
    except Exception:
        return None, None

# --- API 호출 함수들 ---

# 1. 티맵 POI 검색 함수
def search_tmap(keyword, count=10):
    url = "https://apis.openapi.sk.com/tmap/pois"
    headers = {"appKey": TMAP_API_KEY, "Accept": "application/json"}
    params = {"version": "1", "searchKeyword": keyword, "count": count, "searchtypCd": "A", "resCoordType": "WGS84GEO"}
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        places = []
        if data.get("searchPoiInfo", {}).get("totalCount", "0") != "0":
            for item in data["searchPoiInfo"]["pois"]["poi"]:
                places.append({"이름": item.get("name", ""), "주소": item.get("newAddressList", {}).get("newAddress", [{}])[0].get("fullAddressRoad", ""), "위도": float(item.get("frontLat", 0)), "경도": float(item.get("frontLon", 0))})
        return places
    except Exception as e:
        st.error(f"티맵 API 오류: {e}")
        return None

# 2. 네이버 지역 검색(상호명) 함수
def search_naver_local(keyword, display, sort):
    url = "https://openapi.naver.com/v1/search/local.json"
    headers = {"X-Naver-Client-Id": NAVER_CLIENT_ID, "X-Naver-Client-Secret": NAVER_CLIENT_SECRET}
    params = {"query": keyword, "display": display, "sort": sort}
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        places = []
        if data.get("total", 0) > 0 and data.get("items"):
            for item in data["items"]:
                name = item.get("title", "").replace("<b>", "").replace("</b>", "")
                lat, lon = convert_tm_to_wgs84(item.get("mapx"), item.get("mapy"))
                if lat and lon:
                    places.append({"이름": name, "주소": item.get("roadAddress", ""), "위도": lat, "경도": lon})
        return places
    except Exception: return None

# 3. 네이버 지오코딩(주소) 함수 - 공식 문서의 정확한 URL 적용
def search_naver_geocode(query):
    url = "https://maps.apigw.ntruss.com/map-geocode/v2/geocode"
    headers = {"x-ncp-apigw-api-key-id": NCP_CLIENT_ID, "x-ncp-apigw-api-key": NCP_CLIENT_SECRET}
    params = {"query": query}
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        places = []
        if data.get("status") == "OK" and data.get("addresses"):
            addr = data["addresses"][0]
            places.append({"이름": addr.get("roadAddress", "주소 정보 없음"), "주소": addr.get("jibunAddress", ""), "위도": float(addr.get("y", 0)), "경도": float(addr.get("x", 0))})
        return places
    except Exception: return None

# 4. 네이버 스마트 검색 통합 함수
def smart_search_naver(keyword, display, sort):
    results = search_naver_local(keyword, display, sort)
    if results:
        return results, "지역 검색"

    st.info("ℹ️ 상호명 검색 결과가 없습니다. 주소 검색(Geocoding)을 시도합니다.")
    results = search_naver_geocode(keyword)

    if results:
        return results, "주소 검색 (Geocoding)"
    else:
        return None, "검색 실패"

# --- Streamlit 앱 UI ---
st.title("💡 스마트 통합 장소 검색")
st.markdown("티맵(POI)과 네이버(지역/주소) 검색 결과를 함께 조회합니다.")
st.markdown("---")

search_query = st.text_input("검색어 (상호명 또는 주소)", "SK T타워")

with st.expander("⚙️ 네이버 지역 검색 옵션 (상호명 검색 시 적용)"):
    naver_display_count = st.slider("결과 개수", 1, 5, 5)
    sort_option_label = st.selectbox("정렬 방식", ("정확도순 (기본)", "리뷰순"))
    sort_param = "random" if sort_option_label == "정확도순 (기본)" else "comment"

if st.button("🚀 검색 실행", use_container_width=True):
    if not search_query:
        st.warning("검색어를 입력해주세요.")
    else:
        col1, col2 = st.columns(2)

        with col1:
            st.header("📍 티맵 검색 결과")
            with st.spinner("티맵 검색 중..."):
                tmap_results = search_tmap(search_query, 10)
                if tmap_results:
                    df_tmap = pd.DataFrame(tmap_results)
                    st.dataframe(df_tmap[['이름', '주소']], use_container_width=True)
                    st.map(df_tmap, latitude='위도', longitude='경도')
                else:
                    st.info("티맵 검색 결과가 없습니다.")

        with col2:
            st.header("✅ 네이버 스마트 검색 결과")
            with st.spinner("네이버 검색 중..."):
                naver_results, search_type = smart_search_naver(search_query, naver_display_count, sort_param)

                if naver_results:
                    st.subheader(f"✨ {search_type} 결과")
                    df_naver = pd.DataFrame(naver_results)
                    st.dataframe(df_naver[['이름', '주소']], use_container_width=True)
                    st.map(df_naver, latitude='위도', longitude='경도')
                else:
                    st.info("네이버에서 검색 결과가 없습니다.")