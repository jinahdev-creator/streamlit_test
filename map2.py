import streamlit as st
import requests
import pandas as pd
from pyproj import Transformer

# --- 페이지 설정 (가장 먼저 실행) ---
st.set_page_config(
    page_title="Tmap Agent 운영 위한 통합 POI 검색",
    page_icon="💡",
    layout="wide"
)

# --- 커스텀 CSS ---
st.markdown("""
<style>
    /* 전체 배경 */
    .main {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 30%);
    }

    /* Streamlit 기본 컨테이너 배경 제거 */
    .block-container {
        background: transparent !important;
    }

    .element-container {
        background: transparent !important;
    }

    div[data-testid="stVerticalBlock"] > div {
        background: transparent !important;
    }

    div[data-testid="column"] {
        background: transparent !important;
    }

    /* 메인 타이틀 */
    .main-title {
        font-size: 3rem;
        font-weight: 800;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
        text-align: center;
    }

    .subtitle {
        text-align: center;
        font-size: 1.2rem;
        color: #666;
        margin-bottom: 2rem;
    }

    /* 검색 박스 */
    .search-box {
        background: white;
        padding: 2.5rem;
        border-radius: 16px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        margin-bottom: 2rem;
    }

    /* 결과 카드 */
    .result-card {
        background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 50%, #e9ecef 100%);
        border-radius: 12px;
        padding: 1.5rem;
        box-shadow: 0 4px 15px rgba(0,0,0,0.08);
        margin-bottom: 1.5rem;
        border-left: 4px solid #667eea;
    }

    /* 헤더 스타일 */
    .section-header {
        font-size: 1.5rem;
        font-weight: 700;
        color: #2d3748;
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
        border-bottom: 3px solid #667eea;
    }

    /* 스탯 박스 */
    .stat-box {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1rem;
        border-radius: 10px;
        text-align: center;
        font-weight: 600;
        box-shadow: 0 4px 10px rgba(102, 126, 234, 0.3);
    }

    /* 옵션 패널 */
    .option-panel {
        background: #f8f9fa;
        padding: 1.5rem;
        border-radius: 10px;
        border: 1px solid #e0e0e0;
        margin-bottom: 1rem;
    }

    /* 지도 컨테이너 */
    .map-container {
        border-radius: 12px;
        overflow: hidden;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        margin-top: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# --- API 키 로딩 ---
try:
    TMAP_API_KEY = st.secrets["TMAP_API_KEY"]
    NAVER_CLIENT_ID = st.secrets["NAVER_CLIENT_ID"]
    NAVER_CLIENT_SECRET = st.secrets["NAVER_CLIENT_SECRET"]
    NCP_CLIENT_ID = st.secrets["NCP_CLIENT_ID"]
    NCP_CLIENT_SECRET = st.secrets["NCP_CLIENT_SECRET"]
except (KeyError, FileNotFoundError):
    st.error("⚠️ API 키를 찾을 수 없습니다. `.streamlit/secrets.toml` 파일을 확인해주세요.")
    st.stop()

# --- 헬퍼 함수: 좌표계 변환 (수정된 버전) ---
def convert_tm_to_wgs84(x, y):
    """
    네이버 지역 검색 API의 좌표를 위경도(WGS84)로 변환합니다.
    입력값이 TM좌표계가 아닌, 10^7이 곱해진 정수 형태이므로 직접 변환합니다.
    """
    try:
        # 1. 입력값이 유효한지 확인 (None 이거나 비어있는 경우)
        if x is None or y is None:
            return None, None

        # 2. 입력값을 float 형태로 변환. 실패 시 예외 처리
        x_val = float(x)
        y_val = float(y)

        # 3. 10,000,000 으로 나누어 실제 위경도 값으로 변환
        # 네이버 지역검색 API는 경도(lon)가 x, 위도(lat)가 y에 해당합니다.
        lon = x_val / 10000000.0
        lat = y_val / 10000000.0

        # 4. 변환된 좌표가 대한민국 범위 내에 있는지 최종 확인
        if not (33 < lat < 43 and 124 < lon < 132):
            st.write(f"DEBUG - 변환된 좌표({lat}, {lon})가 유효 범위를 벗어났습니다.")
            return None, None

        return lat, lon

    except (ValueError, TypeError) as e:
        # 숫자로 변환할 수 없는 값이 들어왔을 때 오류를 기록하고 None을 반환
        st.write(f"좌표 변환 중 예외 발생: 입력값({x}, {y}), 오류({e})")
        return None, None
    except Exception as e:
        # 기타 예상치 못한 오류 발생 시
        st.write(f"알 수 없는 좌표 변환 오류: {e}")
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
                places.append({
                    "이름": item.get("name", ""),
                    "주소": item.get("newAddressList", {}).get("newAddress", [{}])[0].get("fullAddressRoad", ""),
                    "위도": float(item.get("frontLat", 0)),
                    "경도": float(item.get("frontLon", 0))
                })
        return places
    except Exception as e:
        st.error(f"⚠️ 티맵 API 오류: {e}")
        return None

# 2. 네이버 지역 검색(상호명) 함수
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
                mapx = item.get("mapx")
                mapy = item.get("mapy")

                # (수정) 아래 두 줄의 디버그 메시지를 삭제했습니다.
                # st.write(f"DEBUG - {name}: mapx={mapx}, mapy={mapy}")
                lat, lon = convert_tm_to_wgs84(mapx, mapy) if mapx and mapy else (None, None)
                # st.write(f"  → 변환 후: lat={lat}, lon={lon}")

                if lat and lon:
                    places.append({
                        "이름": name,
                        "주소": item.get("roadAddress", ""),
                        "위도": lat,
                        "경도": lon
                    })
        return places
    except Exception as e:
        st.error(f"네이버 API 오류: {e}")
        return None


# 3. 네이버 지오코딩(주소) 함수
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
            places.append({
                "이름": addr.get("roadAddress", "주소 정보 없음"),
                "주소": addr.get("jibunAddress", ""),
                "위도": float(addr.get("y", 0)),
                "경도": float(addr.get("x", 0))
            })
        return places
    except Exception:
        return None

# 4. 네이버 스마트 검색 통합 함수
def smart_search_naver(keyword, display, sort):
    results = search_naver_local(keyword, display, sort)
    if results:
        return results, "지역 검색"

    st.info("ℹ️ 상호명 검색 결과가 없습니다. 주소 검색을 시도합니다...")
    results = search_naver_geocode(keyword)

    if results:
        return results, "주소 검색 (Geocoding)"
    else:
        return None, "검색 실패"

# --- Streamlit 앱 UI ---

# 헤더
st.markdown('<div class="main-title">💡 스마트 통합 장소 검색</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">티맵(POI)과 네이버(지역/주소) 검색 결과를 한눈에 비교하세요</div>', unsafe_allow_html=True)

# 검색 박스
# 검색 박스
st.markdown('<div class="search-box">', unsafe_allow_html=True)

# st.form을 사용하여 검색창과 버튼을 묶어줍니다.
with st.form(key="search_form"):
    col_search1, col_search2 = st.columns([4, 1])
    with col_search1:
        search_query = st.text_input(
            "🔍 검색어",
            value="",
            placeholder="상호명 또는 주소를 입력하세요 (예: SK T타워)",
            label_visibility="collapsed"
        )

    with col_search2:
        # 버튼을 st.form_submit_button으로 변경합니다.
        # use_container_width=True는 버튼을 컬럼 너비에 꽉 채워줍니다.
        submitted = st.form_submit_button("🚀 검색", type="primary", use_container_width=True)

st.markdown('</div>', unsafe_allow_html=True)

# 검색 옵션
with st.expander("⚙️ 네이버 지역 검색 옵션 설정"):
    st.markdown('<div class="option-panel">', unsafe_allow_html=True)

    col_opt1, col_opt2 = st.columns(2)
    with col_opt1:
        naver_display_count = st.slider("📊 결과 개수", 1, 5, 5)
    with col_opt2:
        sort_option_label = st.selectbox("🔄 정렬 방식", ("정확도순 (기본)", "리뷰순"))

    sort_param = "random" if sort_option_label == "정확도순 (기본)" else "comment"

    st.markdown('</div>', unsafe_allow_html=True)

st.markdown("---")

# 검색 실행
# if search_button: -> if submitted: 로 변경합니다.
if submitted:
    if not search_query:
        st.warning("⚠️ 검색어를 입력해주세요.")
    else:
        # (이하 검색 로직은 기존과 동일합니다)
        # 통계 정보
        stat_col1, stat_col2, stat_col3 = st.columns(3)

        col1, col2 = st.columns(2)

        # 티맵 검색 결과
        with col1:
            st.markdown('<div class="result-card">', unsafe_allow_html=True)
            st.markdown('<div class="section-header">📍 티맵 검색 결과</div>', unsafe_allow_html=True)

            with st.spinner("🔄 티맵 검색 중..."):
                tmap_results = search_tmap(search_query, 10)

                if tmap_results:
                    with stat_col1:
                        st.markdown(f'<div class="stat-box">티맵<br/>{len(tmap_results)}개</div>', unsafe_allow_html=True)

                    df_tmap = pd.DataFrame(tmap_results)

                    # (수정) 아래 디버그 메시지를 삭제했습니다.
                    # st.write("🔍 DEBUG - 티맵 원본 좌표:", df_tmap[['이름', '위도', '경도']].head())

                    # 좌표 정제: 한국 범위로 제한
                    df_tmap_clean = df_tmap.copy()
                    df_tmap_clean = df_tmap_clean[
                        (pd.notna(df_tmap_clean['위도'])) & 
                        (pd.notna(df_tmap_clean['경도'])) &
                        (df_tmap_clean['위도'] > 33) &
                        (df_tmap_clean['위도'] < 43) &
                        (df_tmap_clean['경도'] > 124) &
                        (df_tmap_clean['경도'] < 132)
                    ]

                    # (수정) 아래 디버그 메시지를 삭제했습니다.
                    # st.write(f"✅ 티맵 유효 좌표: {len(df_tmap_clean)}개 / {len(df_tmap)}개")

                    # 데이터 테이블
                    st.markdown("**📋 검색 결과 목록**")
                    st.dataframe(
                        df_tmap[['이름', '주소']],
                        hide_index=True
                    )

                    # 지도
                    st.markdown("**🗺️ 지도 위치**")
                    st.markdown('<div class="map-container">', unsafe_allow_html=True)
                    if len(df_tmap_clean) > 0:
                        try:
                            st.map(df_tmap_clean, latitude='위도', longitude='경도', size=20, color='#667eea')
                        except Exception as e:
                            st.error(f"지도 표시 오류: {e}")
                    else:
                        st.warning("⚠️ 유효한 좌표 정보가 없어 지도를 표시할 수 없습니다.")
                    st.markdown('</div>', unsafe_allow_html=True)
                else:
                    with stat_col1:
                        st.markdown('<div class="stat-box">티맵<br/>0개</div>', unsafe_allow_html=True)
                    st.info("ℹ️ 티맵 검색 결과가 없습니다.")

            st.markdown('</div>', unsafe_allow_html=True)

        # 네이버 검색 결과
        with col2:
            st.markdown('<div class="result-card">', unsafe_allow_html=True)
            st.markdown('<div class="section-header">✅ 네이버 스마트 검색 결과</div>', unsafe_allow_html=True)

            with st.spinner("🔄 네이버 검색 중..."):
                naver_results, search_type = smart_search_naver(search_query, naver_display_count, sort_param)

                if naver_results:
                    with stat_col2:
                        st.markdown(f'<div class="stat-box">네이버<br/>{len(naver_results)}개</div>', unsafe_allow_html=True)

                    st.success(f"✨ {search_type} 적용")
                    df_naver = pd.DataFrame(naver_results)

                    # (수정) 아래 세 줄의 디버그 메시지를 삭제했습니다.
                    # st.write("🔍 DEBUG - 네이버 원본 좌표:", df_naver[['이름', '위도', '경도']].head())

                    # 좌표 정제: 한국 범위로 제한
                    df_naver_clean = df_naver.copy()
                    df_naver_clean = df_naver_clean[
                        (pd.notna(df_naver_clean['위도'])) & 
                        (pd.notna(df_naver_clean['경도'])) &
                        (df_naver_clean['위도'] > 33) &
                        (df_naver_clean['위도'] < 43) &
                        (df_naver_clean['경도'] > 124) &
                        (df_naver_clean['경도'] < 132)
                    ]

                    # (수정) 아래 두 줄의 디버그 메시지를 삭제했습니다.
                    # st.write(f"✅ 네이버 유효 좌표: {len(df_naver_clean)}개 / {len(df_naver)}개")
                    # if len(df_naver_clean) > 0:
                    #     st.write("정제 후 좌표:", df_naver_clean[['이름', '위도', '경도']].head())

                    # 데이터 테이블
                    st.markdown("**📋 검색 결과 목록**")
                    st.dataframe(
                        df_naver[['이름', '주소']],
                        width="stretch",
                        hide_index=True
                    )

                    # 지도
                    st.markdown("**🗺️ 지도 위치**")
                    st.markdown('<div class="map-container">', unsafe_allow_html=True)
                    if len(df_naver_clean) > 0:
                        try:
                            st.map(df_naver_clean, latitude='위도', longitude='경도', size=20, color='#03c75a')
                        except Exception as e:
                            st.error(f"지도 표시 오류: {e}")
                    else:
                        st.warning("⚠️ 유효한 좌표 정보가 없어 지도를 표시할 수 없습니다.")
                    st.markdown('</div>', unsafe_allow_html=True)
                else:
                    with stat_col2:
                        st.markdown('<div class="stat-box">네이버<br/>0개</div>', unsafe_allow_html=True)
                    st.info("ℹ️ 네이버 검색 결과가 없습니다.")

            st.markdown('</div>', unsafe_allow_html=True)


        # 전체 통계
        with stat_col3:
            total_count = (len(tmap_results) if tmap_results else 0) + (len(naver_results) if naver_results else 0)
            st.markdown(f'<div class="stat-box">전체<br/>{total_count}개</div>', unsafe_allow_html=True)

# 푸터
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #666; padding: 2rem;'>"
    "💡 <b>Tmap Agent 운영 지원 도구</b> | Powered by Streamlit<br/>"
    "<small>티맵 POI 검색 · 네이버 지역/주소 검색 통합</small>"
    "</div>",
    unsafe_allow_html=True
)