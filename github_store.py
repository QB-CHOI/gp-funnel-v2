import base64
import inspect
import io
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pandas as pd
import requests
import streamlit as st

# 일시적 실패(연결 끊김·5xx·호출 한도) 재시도 사이 대기(초). 회귀 검사는
# 실패 응답을 일부러 만들어 내므로 여기를 0으로 낮춰 0.7초 안에 끝낸다.
_RETRY_WAIT = 1.5

# 매 요청마다 새 TLS 연결을 맺으면 왕복이 그만큼 늘어난다(실측 건당 425ms →
# 연결 재사용 310ms). 로더가 46종이라 이 차이가 첫 로딩에서 크게 벌어진다.
_SESSION = requests.Session()
_SESSION.mount("https://", requests.adapters.HTTPAdapter(
    pool_connections=8, pool_maxsize=16))

REPO           = "QB-CHOI/gp-funnel-v2"   # 코드 저장소 (public, 배포용)
# 민감 데이터(매출·전환·인원)는 코드와 분리해 별도 private 저장소에 저장.
# → 코드 저장소는 public 유지(Streamlit 배포 안정), 데이터는 외부 비공개.
DATA_REPO      = "QB-CHOI/gp-funnel-data"
MEMBERS_PATH   = "data/members.csv"
CAMPAIGNS_PATH = "data/campaigns.csv"

MEMBERS_COLS   = ['date', 'room_num', 'room_name', 'members', 'prev_members', 'change']
CAMPAIGNS_COLS = ['room_num', 'campaign_name', 'product', 'cohort',
                  'start_date', 'lecture_start_date', 'end_date',
                  'is_current', 'memo', 'target_count', 'status']
ROOMS_PATH          = "data/rooms.csv"
ROOMS_COLS          = ['room_num', 'room_name']
ARCHIVED_ROOMS_PATH = "data/rooms_archived.csv"
ARCHIVED_ROOMS_COLS = ['room_num', 'room_name', 'archived_date', 'actual_close_date', 'final_members', 'archive_reason']
CONVERSIONS_PATH = "data/conversions.csv"
CONVERSIONS_COLS = ['date', 'room_num', 'applicants', 'confirmed', 'revenue', 'memo']

# 기수별 유료 등록 (웨비나 → 유료 전환 퍼널용). 개인정보 없이 집계만 저장.
ENROLLMENTS_PATH = "data/enrollments.csv"
ENROLLMENTS_COLS = ['product', 'cohort', 'enrolled', 'revenue', 'memo']

ADSPEND_PATH = "data/adspend.csv"
ADSPEND_COLS = ['date', 'room_num', 'channel', 'spend', 'impressions', 'clicks', 'memo']

PRODUCT_OPTIONS = ['사주', '타로', '부동산', '빌딩', '기타']
CHANNEL_OPTIONS = ['카카오모먼트', '네이버GFA', '메타(인스타)', '유튜브', '기타']

CONTENT_PATH = "data/content_logs.csv"
CONTENT_COLS = ['date', 'channel', 'content_type', 'title', 'url', 'memo']
CONTENT_TYPE_OPTIONS = ['영상(유튜브/릴스)', '카드뉴스', '블로그', '라이브', '광고소재', '기타']

# 마케팅 채널 metrics (일자별 채널별 광고비·세션·구매·매출) — 외부 시트 이관
MARKETING_PATH = "data/marketing_metrics.csv"
MARKETING_COLS = ['date', 'channel', 'ad_spend', 'sessions', 'purchases', 'revenue']

# 월별 성과 (주문 명단 집계: 무료 신청·유료 구매·매출) — 전 기간
MONTHLY_PERF_PATH = "data/monthly_performance.csv"
MONTHLY_PERF_COLS = ['month', 'free_signups', 'paid_orders', 'revenue', 'conv_rate']

# 월별 광고비 입력 (전 기간 ROAS·CPA 산출용)
AD_MONTHLY_PATH = "data/ad_spend_monthly.csv"
AD_MONTHLY_COLS = ['month', 'channel', 'spend', 'memo']
AD_CHANNEL_OPTIONS = ['전체', '메타', '구글', '네이버', '카카오', '유튜브', '기타']

# 경쟁사 강의 가격/포지셔닝 (경쟁사 조사 시트 이관)
COMPETITOR_PATH = "data/competitor_courses.csv"
COMPETITOR_COLS = ['category', 'company', 'product', 'price_min', 'price_max', 'free']

# 강의 집계 보고서 이관 (아임웹 강의별 집계 · 세트합계 기준)
COHORT_REV_PATH = "data/cohort_revenue.csv"
COHORT_REV_COLS = ['product', 'cohort', 'students', 'revenue']
COURSE_SUM_PATH = "data/course_summary.csv"
# paid=유료 결제 건수(헤더), students=세트 수강생(멤버십 제외, 매출과 동일 기준)
COURSE_SUM_COLS = ['product', 'paid', 'free', 'revenue', 'students']

# 캠페인(라이브)별 광고비·매출 — 상품군별 광고 ROI 산출용 (통합시트 이관)
CAMPAIGN_AD_PATH = "data/campaign_adspend.csv"
CAMPAIGN_AD_COLS = ['live_date', 'product', 'cohort', 'ad_spend', 'live_revenue']

# 월별×강의별 집계 (주문 원본 기준) — 기간별 시계열 분석용
MONTHLY_COURSE_PATH = "data/monthly_by_course.csv"
MONTHLY_COURSE_COLS = ['month', 'product', 'paid_revenue', 'paid_orders', 'free_signups']

# 유료 단계 전환 (기초→심화→전문가→해석/창업) — 강의별 유료 퍼널 (사주/타로)
COHORT_STAGE_PATH = "data/cohort_stage.csv"
COHORT_STAGE_COLS = ['product', 'cohort', '기초', '심화', '전문가', '해석창업']
STAGE_ORDER = ['기초', '심화', '전문가', '해석창업']

# 고객 분석 (LTV·재구매·교차판매) — 주문 원본 집계, 개인정보 미보관
CUST_REPEAT_PATH = "data/cust_repeat_dist.csv"
CUST_LTV_PATH = "data/cust_ltv_dist.csv"
CUST_PRODUCT_PATH = "data/cust_product_repeat.csv"
CUST_CROSS_PATH = "data/cust_cross_sell.csv"
CUST_MONTHLY_PATH = "data/cust_monthly_new_repeat.csv"
CUST_TIMING_PATH = "data/cust_repeat_timing.csv"
CUST_RET_CURVE_PATH = "data/cust_retention_curve.csv"
CUST_RET_MATRIX_PATH = "data/cust_retention_matrix.csv"
CUST_P_TIMING_PATH = "data/cust_product_timing.csv"
CUST_P_RET_PATH = "data/cust_product_retention.csv"
CUST_P_NEXTBUY_PATH = "data/cust_product_nextbuy.csv"
CUST_XSELL_PATH = "data/cust_crosssell_path.csv"

# 지역별 모객 (돈사공 초급반 9~12기 배송지 기준)
REGION_PATH = "data/region_signups.csv"
REGION_COLS = ['region', 'signups', 'pct']
REGION_COHORT_PATH = "data/region_cohort.csv"
REGION_COHORT_COLS = ['cohort', 'start', 'end', 'days', 'total', 'capital', 'capital_pct']
REGION_CITY_PATH = "data/region_city.csv"
REGION_CITY_COLS = ['city', 'count']
REGION_COHORT_DETAIL_PATH = "data/region_cohort_detail.csv"
REGION_COHORT_TOPCITY_PATH = "data/region_cohort_topcity.csv"

# 무료특강 주제별 모객 (주문 원본 집계) — 모객 콘텐츠 효율
WEBINAR_TOPICS_PATH = "data/webinar_topics.csv"
WEBINAR_HOOK_AD_PATH = "data/webinar_hook_ad.csv"
OHAENG_PERIOD_PATH = "data/ohaeng_period.csv"
EXPERIMENTS_PATH = "data/experiments.csv"
MARKET_SIGNALS_PATH = "data/market_signals.csv"
WEBINAR_SCHEDULE_PATH = "data/webinar_schedule.csv"
WEBINAR_SCHEDULE_COLS = ['id', 'date', 'product', 'topic', 'target_signups',
                         'budget', 'status', 'memo']
REFRESH_STATUS_PATH = "data/refresh_status.csv"
EXPERIMENTS_COLS = ['id', 'created', 'start', 'end', 'product', 'hook', 'channel',
                    'hypothesis', 'budget', 'status',
                    'leads', 'conversions', 'revenue', 'learning']
WEBINAR_CONV_PATH = "data/webinar_conversion.csv"

# 데이터 소스 레지스트리 (신선도 추적)
DATA_SOURCES_PATH = "data/data_sources.csv"

# 단계-강의 타임라인 (기초/심화/전문가/창업 강의별 시작·종료) — 기수 병합 가시화
STAGE_TIMELINE_PATH = "data/stage_timeline.csv"
# 수도권 3개 시도 (광고 집중 판단용)
CAPITAL_REGIONS = ['서울', '경기', '인천']


def _token() -> str:
    token = st.secrets.get("github_token", "")
    if not token:
        st.error(
            "❌ **GitHub 토큰 미설정**\n\n"
            "Streamlit Cloud → 앱 우하단 ⋮ → Settings → Secrets 에서\n"
            "`github_token = \"ghp_...\"` 을 추가하세요.",
            icon="🔑",
        )
        st.stop()
    return token


def _headers() -> dict:
    return {"Authorization": f"token {_token()}", "Accept": "application/vnd.github.v3+json"}


# ── GitHub 파일 읽기/쓰기 ────────────────────────────────────────


class RemoteReadError(RuntimeError):
    """원격 CSV를 **읽지 못했다**. '파일이 비어 있다'와 절대 섞이면 안 된다.

    이 구분이 없어서 실제로 데이터가 날아갔다(2026-08-22 rooms.csv 별칭 8개,
    2026-08-29 campaigns.csv 종료 방 5행). 저장 경로가 전부 '읽고 → 합치고 →
    통째로 쓰기'라서, 읽기가 한 번 실패해 빈 표가 돌아오면 그 위에 새 데이터만
    얹혀 원본이 교체된다. 실패는 예외로 알려 쓰기까지 가지 못하게 한다.
    """


def _report(kind: str, msg: str, icon: str = "⚠️"):
    """화면과 로그 **양쪽에** 남긴다.

    launchd 자동 갱신에는 화면이 없다. st.error()는 그 경우 아무 데도 출력되지
    않아서, 위 두 사고가 로그에 흔적조차 남기지 않았다 — 3주 뒤 CSV 이력을
    뒤져서야 발견했다. stderr로도 내보내 자동 갱신 로그에 반드시 남게 한다.
    """
    print(f"[github_store] {msg}", file=sys.stderr, flush=True)
    try:
        getattr(st, kind)(msg, icon=icon)
    except Exception:                  # 화면 없는 실행(bare) — 로그만으로 충분
        pass


def _read_csv(path: str, columns: list) -> pd.DataFrame:
    """원격 CSV를 읽는다. 없으면 빈 표, **못 읽으면 RemoteReadError**.

    일시적 실패(연결 끊김·5xx·호출 한도)는 대부분 잠깐이라 3회까지 다시 시도한
    뒤에 포기한다. 404만 '아직 없는 파일'로 보고 빈 표를 돌려준다.
    """
    url = f"https://api.github.com/repos/{DATA_REPO}/contents/{path}"
    last = ""
    for attempt in range(3):
        if attempt:
            time.sleep(_RETRY_WAIT * attempt)
        try:
            res = _SESSION.get(url, headers=_headers(), timeout=20)
        except requests.exceptions.RequestException as e:
            last = f"연결 오류: {type(e).__name__}"
            continue

        if res.status_code == 404:     # 아직 만들어지지 않은 파일 — 정상
            return pd.DataFrame(columns=columns)

        if res.ok:
            try:
                content = base64.b64decode(res.json()["content"]).decode("utf-8")
            except Exception as e:
                last = f"응답 해석 실패: {type(e).__name__}"
                continue
            if not content.strip():
                return pd.DataFrame(columns=columns)
            try:
                return pd.read_csv(io.StringIO(content))
            except Exception as e:     # 내용이 깨졌다면 재시도해도 같다
                raise RemoteReadError(f"{path} 내용을 표로 읽지 못했습니다: {e}") from e

        if res.status_code == 401:
            raise RemoteReadError(
                f"GitHub 토큰 인증 실패 (401) — {path}. 토큰이 만료되었을 수 있습니다. "
                "Streamlit Cloud → Settings → Secrets 의 github_token 을 교체하세요.")

        last = f"HTTP {res.status_code}"
        if res.status_code not in (403, 429) and res.status_code < 500:
            break                      # 재시도해도 달라지지 않는 오류

    raise RemoteReadError(f"{path} 를 읽지 못했습니다 ({last}).")


def _write_csv(path: str, df: pd.DataFrame, message: str, _retries: int = 3,
               allow_shrink: bool = False):
    """CSV를 GitHub에 저장. SHA 충돌(409) 시 최대 3회 자동 재시도.

    **행이 줄어드는 저장은 기본적으로 거부한다.** 저장 경로 27곳이 모두 '읽고 →
    합치고 → 통째로 쓰기'라, 중간의 읽기가 어긋나면 남은 것만 남기고 원본을
    교체해 버린다(2026-08-29 campaigns.csv 16행 → 11행). 사람이 지운 것이라면
    호출하는 쪽이 allow_shrink=True로 **의도를 밝히게** 한다 — 그러면 사고는
    막히고 진짜 삭제는 그대로 된다.

    sha를 얻으려고 어차피 GET을 하므로 기존 행 수는 그 응답에서 함께 센다.
    왕복이 늘지 않는다.
    """
    import time as _time
    url       = f"https://api.github.com/repos/{DATA_REPO}/contents/{path}"
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    content   = base64.b64encode(csv_bytes).decode("utf-8")

    for attempt in range(_retries):
        # 매 시도마다 최신 SHA를 가져와야 409 충돌을 피할 수 있음
        res_get = _SESSION.get(url, headers=_headers(), timeout=20)
        sha = res_get.json().get("sha", "") if res_get.status_code == 200 else ""

        if sha and not allow_shrink:
            _guard_shrink(path, res_get, df)

        payload = {"message": message, "content": content}
        if sha:
            payload["sha"] = sha

        res = _SESSION.put(url, headers=_headers(), json=payload, timeout=30)
        if res.ok:
            return

        if res.status_code == 409 and attempt < _retries - 1:
            _time.sleep(_RETRY_WAIT * (attempt + 1))  # 점진적 대기 후 재시도
            continue

        try:
            err_msg = res.json().get("message", res.text[:200])
        except Exception:
            err_msg = res.text[:200]
        raise RuntimeError(f"GitHub 저장 실패 [{res.status_code}]: {err_msg}")


def _guard_shrink(path: str, res_get, df: pd.DataFrame):
    """저장하려는 표가 원격본보다 짧으면 막는다."""
    try:
        cur = base64.b64decode(res_get.json()["content"]).decode("utf-8")
        n_old = len(pd.read_csv(io.StringIO(cur))) if cur.strip() else 0
    except Exception:
        return                          # 셀 수 없으면 통과 — 저장을 막지는 않는다

    if len(df) >= n_old:
        return

    msg = (f"❌ 저장을 멈췄습니다 — {path} 가 {n_old}행에서 {len(df)}행으로 "
           f"줄어듭니다. 데이터를 읽어오지 못한 채 덮어쓰는 상황일 수 있어 "
           f"원본을 지키는 쪽을 택했습니다. 정말 지우는 작업이라면 삭제 기능을 "
           f"쓰세요.")
    _report("error", msg, icon="🛑")
    raise RuntimeError(msg)


# ── 인원 데이터 ───────────────────────────────────────────────────

@st.cache_data(ttl=120)
def load_all() -> pd.DataFrame:
    df = _read_csv(MEMBERS_PATH, MEMBERS_COLS)
    if df.empty:
        return df
    df["date"]     = pd.to_datetime(df["date"]).dt.date
    df["room_num"] = pd.to_numeric(df["room_num"], errors="coerce").astype("Int64")
    for col in ["members", "prev_members", "change"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def get_latest_per_room() -> dict:
    df = load_all()
    if df.empty:
        return {}
    return df.sort_values("date").groupby("room_num").last()["members"].to_dict()


def save_daily(date_str: str, room_data: list):
    df = load_all()
    df_prev = df[df["date"].astype(str) != date_str]
    prev = {}
    if not df_prev.empty:
        prev = df_prev.sort_values("date").groupby("room_num").last()["members"].to_dict()

    df = df[df["date"].astype(str) != date_str]

    new_rows = []
    for r in room_data:
        rn       = int(r["room_num"])
        members  = int(r["members"])
        prev_val = prev.get(rn)
        change   = int(members - prev_val) if prev_val is not None else None
        new_rows.append({
            "date": date_str, "room_num": rn,
            "room_name": r.get("room_name", f"채팅방 {rn}"),
            "members": members,
            "prev_members": int(prev_val) if prev_val is not None else None,
            "change": change,
        })

    combined = (pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
                .sort_values(['date', 'room_num'])
                .reset_index(drop=True))
    _write_csv(MEMBERS_PATH, combined, f"{date_str} 인원 업데이트")
    load_all.clear()


def delete_date(date_str: str):
    df = load_all()
    df = df[df["date"].astype(str) != date_str]
    _write_csv(MEMBERS_PATH, df, f"{date_str} 데이터 삭제", allow_shrink=True)
    load_all.clear()


# ── 캠페인 데이터 ─────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def load_campaigns() -> pd.DataFrame:
    df = _read_csv(CAMPAIGNS_PATH, CAMPAIGNS_COLS)
    if df.empty:
        return df
    df["room_num"]   = pd.to_numeric(df["room_num"], errors="coerce").astype("Int64")
    df["is_current"] = df["is_current"].astype(str).str.upper().isin(["TRUE", "1", "YES"])
    # status는 나중에 생긴 열이라 동기화 전 CSV에는 없다 — 없으면 빈 값으로 둔다.
    if "status" not in df.columns:
        df["status"] = ""
    df["status"] = df["status"].fillna("").astype(str).str.strip()
    return df


def get_current_campaigns() -> dict:
    df = load_campaigns()
    if df.empty:
        return {}
    return {
        int(row["room_num"]): row.to_dict()
        for _, row in df[df["is_current"]].iterrows()
    }


def save_campaign(room_num: int, campaign_name: str, product: str,
                  cohort: str, start_date: str, memo: str,
                  target_count: int = 0, lecture_start_date: str = ""):
    df = load_campaigns()
    if not df.empty:
        mask = (df["room_num"] == room_num) & (df["is_current"] == True)
        df.loc[mask, "is_current"] = False
        df.loc[mask, "end_date"]   = str(date.today())

    new_row = pd.DataFrame([{
        "room_num": room_num, "campaign_name": campaign_name,
        "product": product, "cohort": cohort,
        "start_date": start_date, "lecture_start_date": lecture_start_date,
        "end_date": "", "is_current": True,
        "memo": memo, "target_count": int(target_count),
        "status": "",          # 시트 동기화가 채운다(웨비나대기·웨비나종료·모집중)
    }])
    combined = pd.concat([df, new_row], ignore_index=True)
    _write_csv(CAMPAIGNS_PATH, combined, f"캠페인 등록: 채팅방 {room_num} — {campaign_name}")
    load_campaigns.clear()


def update_lecture_start_date(room_num: int, lecture_start_date: str):
    df = load_campaigns()
    if df.empty:
        return
    mask = (df["room_num"] == room_num) & (df["is_current"] == True)
    df.loc[mask, "lecture_start_date"] = lecture_start_date
    _write_csv(CAMPAIGNS_PATH, df, f"개강일 업데이트: 채팅방 {room_num} → {lecture_start_date}")
    load_campaigns.clear()


def end_campaign(room_num: int):
    df = load_campaigns()
    if df.empty:
        return
    mask = (df["room_num"] == room_num) & (df["is_current"] == True)
    df.loc[mask, "is_current"] = False
    df.loc[mask, "end_date"]   = str(date.today())
    _write_csv(CAMPAIGNS_PATH, df, f"캠페인 종료: 채팅방 {room_num}")
    load_campaigns.clear()


# ── 기수별 유료 등록 (전환 퍼널) ─────────────────────────────────

@st.cache_data(ttl=3600)
def load_enrollments() -> pd.DataFrame:
    """상품·기수별 유료 등록 집계 반환 (개인정보 없음)."""
    df = _read_csv(ENROLLMENTS_PATH, ENROLLMENTS_COLS)
    if df.empty:
        return df
    df['enrolled'] = pd.to_numeric(df['enrolled'], errors='coerce').fillna(0).astype(int)
    df['revenue']  = pd.to_numeric(df['revenue'], errors='coerce').fillna(0).astype(int)
    return df


def save_enrollment(product: str, cohort: str, enrolled: int,
                    revenue: int = 0, memo: str = ""):
    """상품·기수 키로 유료 등록 수·매출 저장(있으면 갱신)."""
    df = _read_csv(ENROLLMENTS_PATH, ENROLLMENTS_COLS)
    if not df.empty:
        mask = (df['product'].astype(str) == str(product)) & \
               (df['cohort'].astype(str) == str(cohort))
        df = df[~mask]
    new_row = pd.DataFrame([{
        'product': product, 'cohort': cohort,
        'enrolled': int(enrolled), 'revenue': int(revenue), 'memo': memo,
    }])
    combined = pd.concat([df, new_row], ignore_index=True)
    _write_csv(ENROLLMENTS_PATH, combined, f"유료 등록 저장: {product} {cohort} — {enrolled}명")
    load_enrollments.clear()


def delete_enrollment(product: str, cohort: str):
    df = _read_csv(ENROLLMENTS_PATH, ENROLLMENTS_COLS)
    if df.empty:
        return
    mask = (df['product'].astype(str) == str(product)) & \
           (df['cohort'].astype(str) == str(cohort))
    df = df[~mask]
    _write_csv(ENROLLMENTS_PATH, df, f"유료 등록 삭제: {product} {cohort}", allow_shrink=True)
    load_enrollments.clear()


# ── 채팅방 목록 ───────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def load_rooms() -> dict:
    df = _read_csv(ROOMS_PATH, ROOMS_COLS)
    if df.empty:
        return {}
    df['room_num'] = pd.to_numeric(df['room_num'], errors='coerce').astype('Int64')
    return {int(row['room_num']): row['room_name'] for _, row in df.iterrows()}


def save_room(room_num: int, room_name: str):
    df = _read_csv(ROOMS_PATH, ROOMS_COLS)
    if not df.empty:
        df['room_num'] = pd.to_numeric(df['room_num'], errors='coerce').astype('Int64')
        df = df[df['room_num'] != room_num]
    new_row = pd.DataFrame([{'room_num': room_num, 'room_name': room_name}])
    combined = pd.concat([df, new_row], ignore_index=True).sort_values('room_num')
    _write_csv(ROOMS_PATH, combined, f"채팅방 {room_num} 추가/수정")
    load_rooms.clear()


def save_rooms_batch(new_rooms: dict):
    """신규 채팅방 여러 개를 API 1회 호출로 일괄 등록.

    **이미 있는 방은 건드리지 않는다.** 여기 들어오는 이름은 '채팅방 37' 같은
    기본값인데, 목록에는 사람이 붙인 별칭('채팅방 37 (부동산2)')이 들어 있다.
    2026-08-22에 이 함수가 별칭 8개를 전부 기본값으로 되돌렸다 — 방 목록을
    읽어오지 못해 '전부 신규'로 보인 탓이었다. 신규 등록은 말 그대로 신규만.
    """
    df = _read_csv(ROOMS_PATH, ROOMS_COLS)
    if not df.empty:
        df['room_num'] = pd.to_numeric(df['room_num'], errors='coerce').astype('Int64')
        exist = set(df['room_num'].dropna().astype(int))
        new_rooms = {rn: nm for rn, nm in new_rooms.items() if int(rn) not in exist}
        if not new_rooms:
            return
    new_rows = pd.DataFrame([{'room_num': rn, 'room_name': name}
                              for rn, name in new_rooms.items()])
    combined = pd.concat([df, new_rows], ignore_index=True).sort_values('room_num')
    room_list = ", ".join(f"채팅방{rn}" for rn in sorted(new_rooms.keys()))
    _write_csv(ROOMS_PATH, combined, f"신규 채팅방 자동 등록: {room_list}")
    load_rooms.clear()


def delete_room(room_num: int):
    df = _read_csv(ROOMS_PATH, ROOMS_COLS)
    if df.empty:
        return
    df['room_num'] = pd.to_numeric(df['room_num'], errors='coerce').astype('Int64')
    df = df[df['room_num'] != room_num]
    _write_csv(ROOMS_PATH, df, f"채팅방 {room_num} 삭제", allow_shrink=True)
    load_rooms.clear()


@st.cache_data(ttl=3600)
def load_archived_rooms() -> pd.DataFrame:
    """운영 종료된 채팅방 목록 반환."""
    df = _read_csv(ARCHIVED_ROOMS_PATH, ARCHIVED_ROOMS_COLS)
    if df.empty:
        return df
    df['room_num']      = pd.to_numeric(df['room_num'], errors='coerce').astype('Int64')
    df['final_members'] = pd.to_numeric(df['final_members'], errors='coerce').fillna(0).astype(int)
    return df


def archive_room(room_num: int, room_name: str, final_members: int,
                 reason: str = "운영 종료", actual_close_date: str = ""):
    """채팅방을 운영 종료 처리: rooms.csv에서 제거 → rooms_archived.csv에 기록."""
    # 1) 보관 파일에 추가
    df_arch = _read_csv(ARCHIVED_ROOMS_PATH, ARCHIVED_ROOMS_COLS)
    if not df_arch.empty:
        df_arch['room_num'] = pd.to_numeric(df_arch['room_num'], errors='coerce').astype('Int64')
        df_arch = df_arch[df_arch['room_num'] != room_num]
    new_row = pd.DataFrame([{
        'room_num': room_num, 'room_name': room_name,
        'archived_date': str(date.today()),
        'actual_close_date': actual_close_date or "",
        'final_members': int(final_members),
        'archive_reason': reason,
    }])
    combined = pd.concat([df_arch, new_row], ignore_index=True).sort_values('room_num')
    _write_csv(ARCHIVED_ROOMS_PATH, combined, f"채팅방 {room_num} 운영 종료 보관")

    # 2) 활성 목록에서 제거
    df_rooms = _read_csv(ROOMS_PATH, ROOMS_COLS)
    if not df_rooms.empty:
        df_rooms['room_num'] = pd.to_numeric(df_rooms['room_num'], errors='coerce').astype('Int64')
        df_rooms = df_rooms[df_rooms['room_num'] != room_num]
        _write_csv(ROOMS_PATH, df_rooms, f"채팅방 {room_num} 활성 목록 제거", allow_shrink=True)

    load_rooms.clear()
    load_archived_rooms.clear()


def update_actual_close_date(room_num: int, actual_close_date: str):
    """운영 종료된 채팅방의 실제 종료일을 수정."""
    df = _read_csv(ARCHIVED_ROOMS_PATH, ARCHIVED_ROOMS_COLS)
    if df.empty:
        return
    df['room_num'] = pd.to_numeric(df['room_num'], errors='coerce').astype('Int64')
    df.loc[df['room_num'] == room_num, 'actual_close_date'] = actual_close_date
    _write_csv(ARCHIVED_ROOMS_PATH, df, f"채팅방 {room_num} 실제 종료일 수정 → {actual_close_date}")
    load_archived_rooms.clear()


def restore_room(room_num: int):
    """종료된 채팅방을 활성 목록으로 복원."""
    df_arch = _read_csv(ARCHIVED_ROOMS_PATH, ARCHIVED_ROOMS_COLS)
    if df_arch.empty:
        return
    df_arch['room_num'] = pd.to_numeric(df_arch['room_num'], errors='coerce').astype('Int64')
    row = df_arch[df_arch['room_num'] == room_num]
    if row.empty:
        return
    room_name = str(row.iloc[0]['room_name'])
    save_room(int(room_num), room_name)
    df_arch = df_arch[df_arch['room_num'] != room_num]
    _write_csv(ARCHIVED_ROOMS_PATH, df_arch, f"채팅방 {room_num} 복원", allow_shrink=True)
    load_rooms.clear()
    load_archived_rooms.clear()


def load_all_room_names() -> dict:
    """활성 + 종료 채팅방 이름 통합 반환 (이력 조회·차트 레이블용)."""
    names = load_rooms().copy()
    df_arch = load_archived_rooms()
    if not df_arch.empty:
        for _, r in df_arch.iterrows():
            rn = int(r['room_num'])
            if rn not in names:
                names[rn] = f"{r['room_name']} (종료)"
    return names


def get_history(room_num: int) -> pd.DataFrame:
    df = load_campaigns()
    if df.empty:
        return pd.DataFrame(columns=CAMPAIGNS_COLS)
    return (
        df[df["room_num"] == room_num]
        .sort_values("start_date", ascending=False)
        .reset_index(drop=True)
    )


# ── 전환 데이터 ───────────────────────────────────────────────────

@st.cache_data(ttl=600)
def load_conversions() -> pd.DataFrame:
    df = _read_csv(CONVERSIONS_PATH, CONVERSIONS_COLS)
    if df.empty:
        return df
    df['date']     = pd.to_datetime(df['date']).dt.date
    df['room_num'] = pd.to_numeric(df['room_num'], errors='coerce').astype('Int64')
    for col in ['applicants', 'confirmed', 'revenue']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    return df


def save_conversion(room_num: int, date_str: str, applicants: int,
                    confirmed: int, revenue: int, memo: str):
    df = load_conversions()
    if not df.empty:
        df = df[~((df['room_num'] == room_num) & (df['date'].astype(str) == date_str))]
    new_row = pd.DataFrame([{
        'date': date_str, 'room_num': room_num,
        'applicants': applicants, 'confirmed': confirmed,
        'revenue': revenue, 'memo': memo,
    }])
    combined = pd.concat([df, new_row], ignore_index=True).sort_values(['date', 'room_num'])
    _write_csv(CONVERSIONS_PATH, combined, f"전환 데이터 저장: 채팅방 {room_num} {date_str}")
    load_conversions.clear()


def delete_conversion_row(row_idx: int):
    """최신순 정렬 기준 인덱스로 전환 데이터 행 삭제."""
    df = load_conversions()
    sorted_df = df.sort_values('date', ascending=False).reset_index()
    if row_idx < 0 or row_idx >= len(sorted_df):
        return
    real_idx = int(sorted_df.iloc[row_idx]['index'])
    df = df.drop(index=real_idx).reset_index(drop=True)
    _write_csv(CONVERSIONS_PATH, df, f"전환 데이터 삭제 (row {row_idx})", allow_shrink=True)
    load_conversions.clear()
    get_latest_conversions.clear()


def get_latest_conversions() -> pd.DataFrame:
    """방별 가장 최근 전환 데이터 1행씩 반환."""
    df = load_conversions()
    if df.empty:
        return df
    return (
        df.sort_values('date')
          .groupby('room_num', as_index=False)
          .last()
    )


# ── 광고비 데이터 ─────────────────────────────────────────────────

@st.cache_data(ttl=600)
def load_adspend() -> pd.DataFrame:
    df = _read_csv(ADSPEND_PATH, ADSPEND_COLS)
    if df.empty:
        return df
    df['date']     = pd.to_datetime(df['date']).dt.date
    df['room_num'] = pd.to_numeric(df['room_num'], errors='coerce').astype('Int64')
    for col in ['spend', 'impressions', 'clicks']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    return df


def save_adspend(room_num: int, date_str: str, channel: str,
                 spend: int, impressions: int, clicks: int, memo: str):
    df = load_adspend()
    if not df.empty:
        df = df[~(
            (df['room_num'] == room_num) &
            (df['date'].astype(str) == date_str) &
            (df['channel'] == channel)
        )]
    new_row = pd.DataFrame([{
        'date': date_str, 'room_num': room_num, 'channel': channel,
        'spend': spend, 'impressions': impressions, 'clicks': clicks, 'memo': memo,
    }])
    combined = pd.concat([df, new_row], ignore_index=True).sort_values(['date', 'room_num'])
    _write_csv(ADSPEND_PATH, combined, f"광고비 저장: 채팅방 {room_num} {channel} {date_str}")
    load_adspend.clear()


def delete_adspend_row(row_idx: int):
    """최신순 정렬 기준 인덱스로 광고비 데이터 행 삭제."""
    df = load_adspend()
    sorted_df = df.sort_values('date', ascending=False).reset_index()
    if row_idx < 0 or row_idx >= len(sorted_df):
        return
    real_idx = int(sorted_df.iloc[row_idx]['index'])
    df = df.drop(index=real_idx).reset_index(drop=True)
    _write_csv(ADSPEND_PATH, df, f"광고비 데이터 삭제 (row {row_idx})", allow_shrink=True)
    load_adspend.clear()


# ── 콘텐츠 기록 ───────────────────────────────────────────────────

@st.cache_data(ttl=600)
def load_content() -> pd.DataFrame:
    df = _read_csv(CONTENT_PATH, CONTENT_COLS)
    if df.empty:
        return df
    df['date'] = pd.to_datetime(df['date']).dt.date
    return df


def save_content(date_str: str, channel: str, content_type: str,
                 title: str, url: str, memo: str):
    df = load_content()
    new_row = pd.DataFrame([{
        'date': date_str, 'channel': channel, 'content_type': content_type,
        'title': title, 'url': url, 'memo': memo,
    }])
    combined = pd.concat([df, new_row], ignore_index=True).sort_values('date').reset_index(drop=True)
    _write_csv(CONTENT_PATH, combined, f"콘텐츠 기록: {channel} {date_str}")
    load_content.clear()


def delete_content_row(row_idx: int):
    """정렬 기준 인덱스로 콘텐츠 행 삭제."""
    df = load_content()
    if df.empty or row_idx < 0 or row_idx >= len(df):
        return
    df = df.drop(index=row_idx).reset_index(drop=True)
    _write_csv(CONTENT_PATH, df, f"콘텐츠 기록 삭제 (row {row_idx})", allow_shrink=True)
    load_content.clear()


# ── 마케팅 채널 metrics ───────────────────────────────────────────

@st.cache_data(ttl=3600)
def load_marketing() -> pd.DataFrame:
    """일자별 채널별 광고비·세션·구매·매출 (외부 마케팅 시트 이관분)."""
    df = _read_csv(MARKETING_PATH, MARKETING_COLS)
    if df.empty:
        return df
    df['date'] = pd.to_datetime(df['date'], errors='coerce').dt.date
    for c in ['ad_spend', 'sessions', 'purchases', 'revenue']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)
    return df.dropna(subset=['date'])


@st.cache_data(ttl=3600)
def load_monthly_performance() -> pd.DataFrame:
    """월별 무료 신청·유료 구매·매출·전환율 (주문 명단 집계, 전 기간)."""
    df = _read_csv(MONTHLY_PERF_PATH, MONTHLY_PERF_COLS)
    if df.empty:
        return df
    for c in ['free_signups', 'paid_orders', 'revenue']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)
    df['conv_rate'] = pd.to_numeric(df['conv_rate'], errors='coerce').fillna(0.0)
    return df.sort_values('month').reset_index(drop=True)


@st.cache_data(ttl=600)
def load_ad_spend_monthly() -> pd.DataFrame:
    """월별 광고비 입력값."""
    df = _read_csv(AD_MONTHLY_PATH, AD_MONTHLY_COLS)
    if df.empty:
        return df
    df['spend'] = pd.to_numeric(df['spend'], errors='coerce').fillna(0).astype(int)
    return df


def save_ad_spend_monthly(month: str, channel: str, spend: int, memo: str = ""):
    """월별 광고비 저장(같은 월+채널이면 갱신)."""
    df = _read_csv(AD_MONTHLY_PATH, AD_MONTHLY_COLS)
    if not df.empty:
        mask = (df['month'].astype(str) == str(month)) & (df['channel'].astype(str) == str(channel))
        df = df[~mask]
    new_row = pd.DataFrame([{'month': month, 'channel': channel, 'spend': int(spend), 'memo': memo}])
    combined = pd.concat([df, new_row], ignore_index=True).sort_values(['month', 'channel'])
    _write_csv(AD_MONTHLY_PATH, combined, f"월별 광고비 저장: {month} {channel} {spend:,}원")
    load_ad_spend_monthly.clear()


# 월별 KPI 목표 (매출·모객) — 목표 대비 실적 추적
TARGETS_PATH = "data/targets.csv"
TARGETS_COLS = ['month', 'revenue_target', 'signup_target', 'memo']


@st.cache_data(ttl=300)
def load_targets() -> pd.DataFrame:
    """월별 KPI 목표(매출·무료 모객)."""
    df = _read_csv(TARGETS_PATH, TARGETS_COLS)
    if df.empty:
        return df
    for c in ['revenue_target', 'signup_target']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)
    return df


def save_target(month: str, revenue_target: int, signup_target: int, memo: str = ""):
    """월별 목표 저장(같은 월이면 갱신)."""
    df = _read_csv(TARGETS_PATH, TARGETS_COLS)
    if not df.empty:
        df = df[df['month'].astype(str) != str(month)]
    new_row = pd.DataFrame([{'month': month, 'revenue_target': int(revenue_target),
                             'signup_target': int(signup_target), 'memo': memo}])
    combined = pd.concat([df, new_row], ignore_index=True).sort_values('month')
    _write_csv(TARGETS_PATH, combined, f"월별 목표 저장: {month}")
    load_targets.clear()


@st.cache_data(ttl=3600)
def load_competitor_courses() -> pd.DataFrame:
    """경쟁사 강의 가격/포지셔닝 (황금후추 자사 대표가 포함)."""
    df = _read_csv(COMPETITOR_PATH, COMPETITOR_COLS)
    if df.empty:
        return df
    for c in ['price_min', 'price_max']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)
    df['free'] = pd.to_numeric(df['free'], errors='coerce').fillna(0).astype(int)
    return df


@st.cache_data(ttl=3600)
def load_cohort_revenue() -> pd.DataFrame:
    """강의별 기수별 매출/수강생 (세트합계·멤버십 제외)."""
    df = _read_csv(COHORT_REV_PATH, COHORT_REV_COLS)
    if df.empty:
        return df
    for c in ['students', 'revenue']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)
    return df


@st.cache_data(ttl=3600)
def load_course_summary() -> pd.DataFrame:
    """상품군 top-line (유료 건수·무료 신청·총매출·세트 수강생).

    - paid: 유료 결제 건수(리포트 헤더, 거래 기준)
    - students: 세트 수강생(기초+심화+패키지·멤버십 제외) = 매출과 동일 기준.
      객단가·전환율은 매출과 정합을 위해 students를 분모로 사용한다.
    """
    df = _read_csv(COURSE_SUM_PATH, COURSE_SUM_COLS)
    if df.empty:
        return df
    for c in ['paid', 'free', 'revenue', 'students']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)
    # students 누락(구버전 데이터) 시 paid로 대체
    if 'students' not in df.columns or (df['students'] == 0).all():
        df['students'] = df['paid']
    return df


@st.cache_data(ttl=3600)
def load_campaign_adspend() -> pd.DataFrame:
    """캠페인(라이브)별 광고비·매출 (상품군별 광고 ROI 산출용)."""
    df = _read_csv(CAMPAIGN_AD_PATH, CAMPAIGN_AD_COLS)
    if df.empty:
        return df
    for c in ['ad_spend', 'live_revenue']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)
    return df


@st.cache_data(ttl=3600)
def load_monthly_by_course() -> pd.DataFrame:
    """월별×강의별 집계 (주문 원본 기준: 매출·유료건·무료신청)."""
    df = _read_csv(MONTHLY_COURSE_PATH, MONTHLY_COURSE_COLS)
    if df.empty:
        return df
    for c in ['paid_revenue', 'paid_orders', 'free_signups']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)
    return df


@st.cache_data(ttl=3600)
def load_cohort_stage() -> pd.DataFrame:
    """유료 단계 전환 인원 (기초→심화→전문가→해석/창업, 사주·타로)."""
    df = _read_csv(COHORT_STAGE_PATH, COHORT_STAGE_COLS)
    if df.empty:
        return df
    for c in STAGE_ORDER:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)
    return df


@st.cache_data(ttl=3600)
def load_cust_repeat_dist() -> pd.DataFrame:
    """고객 재구매 횟수 분포 (1회/2회/3~4회/5회+)."""
    df = _read_csv(CUST_REPEAT_PATH, ['bucket', 'customers'])
    if not df.empty:
        df['customers'] = pd.to_numeric(df['customers'], errors='coerce').fillna(0).astype(int)
    return df


@st.cache_data(ttl=3600)
def load_cust_ltv_dist() -> pd.DataFrame:
    """고객 누적결제(LTV) 구간 분포."""
    df = _read_csv(CUST_LTV_PATH, ['bucket', 'customers'])
    if not df.empty:
        df['customers'] = pd.to_numeric(df['customers'], errors='coerce').fillna(0).astype(int)
    return df


@st.cache_data(ttl=3600)
def load_cust_product_repeat() -> pd.DataFrame:
    """상품군별 구매자·재구매율·평균 LTV."""
    df = _read_csv(CUST_PRODUCT_PATH, ['product', 'buyers', 'repeat_buyers', 'repeat_rate', 'avg_ltv'])
    if df.empty:
        return df
    for c in ['buyers', 'repeat_buyers', 'avg_ltv']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)
    df['repeat_rate'] = pd.to_numeric(df['repeat_rate'], errors='coerce').fillna(0.0)
    return df


@st.cache_data(ttl=3600)
def load_cust_cross_sell() -> pd.DataFrame:
    """교차판매 매트릭스 (from 구매자 중 to 구매 비율)."""
    df = _read_csv(CUST_CROSS_PATH, ['from', 'to', 'rate', 'count'])
    if df.empty:
        return df
    df['rate'] = pd.to_numeric(df['rate'], errors='coerce').fillna(0.0)
    df['count'] = pd.to_numeric(df['count'], errors='coerce').fillna(0).astype(int)
    return df


@st.cache_data(ttl=3600)
def load_cust_monthly_new_repeat() -> pd.DataFrame:
    """월별 신규/재구매 고객·매출."""
    df = _read_csv(CUST_MONTHLY_PATH, ['month', 'new_customers', 'repeat_orders', 'new_revenue', 'repeat_revenue'])
    if df.empty:
        return df
    for c in ['new_customers', 'repeat_orders', 'new_revenue', 'repeat_revenue']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)
    return df


@st.cache_data(ttl=3600)
def load_cust_repeat_timing() -> pd.DataFrame:
    """재구매 타이밍 (첫→2번째 구매 간격 분포)."""
    df = _read_csv(CUST_TIMING_PATH, ['bucket', 'customers'])
    if not df.empty:
        df['customers'] = pd.to_numeric(df['customers'], errors='coerce').fillna(0).astype(int)
    return df


@st.cache_data(ttl=3600)
def load_cust_retention_curve() -> pd.DataFrame:
    """평균 리텐션 커브 (첫 구매 후 k개월 재구매 비율)."""
    df = _read_csv(CUST_RET_CURVE_PATH, ['k', 'pct'])
    if df.empty:
        return df
    df['k'] = pd.to_numeric(df['k'], errors='coerce').fillna(0).astype(int)
    df['pct'] = pd.to_numeric(df['pct'], errors='coerce').fillna(0.0)
    return df


@st.cache_data(ttl=3600)
def load_cust_retention_matrix() -> pd.DataFrame:
    """코호트 리텐션 매트릭스 (acq월 × k개월 재구매 비율)."""
    df = _read_csv(CUST_RET_MATRIX_PATH, ['acq', 'k', 'pct', 'cohort_size'])
    if df.empty:
        return df
    for c in ['k', 'cohort_size']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)
    df['pct'] = pd.to_numeric(df['pct'], errors='coerce').fillna(0.0)
    return df


@st.cache_data(ttl=3600)
def load_cust_product_timing() -> pd.DataFrame:
    """상품군별 재구매 타이밍 분포."""
    df = _read_csv(CUST_P_TIMING_PATH, ['product', 'bucket', 'customers'])
    if not df.empty:
        df['customers'] = pd.to_numeric(df['customers'], errors='coerce').fillna(0).astype(int)
    return df


@st.cache_data(ttl=3600)
def load_cust_product_retention() -> pd.DataFrame:
    """상품군별 리텐션 커브 (홈고객 첫 구매 후 k개월 재구매율)."""
    df = _read_csv(CUST_P_RET_PATH, ['product', 'k', 'pct'])
    if df.empty:
        return df
    df['k'] = pd.to_numeric(df['k'], errors='coerce').fillna(0).astype(int)
    df['pct'] = pd.to_numeric(df['pct'], errors='coerce').fillna(0.0)
    return df


@st.cache_data(ttl=3600)
def load_cust_product_nextbuy() -> pd.DataFrame:
    """상품군별 다음 구매 (같은 상품 업셀 vs 다른 강의 교차판매)."""
    df = _read_csv(CUST_P_NEXTBUY_PATH, ['product', 'home_customers', 'repeat_rate', 'same_pct', 'diff_pct'])
    if df.empty:
        return df
    df['home_customers'] = pd.to_numeric(df['home_customers'], errors='coerce').fillna(0).astype(int)
    for c in ['repeat_rate', 'same_pct', 'diff_pct']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
    return df


@st.cache_data(ttl=3600)
def load_cust_crosssell_path() -> pd.DataFrame:
    """순차 교차판매 경로 (홈 강의 → 다른 강의 2번째 구매 분포)."""
    df = _read_csv(CUST_XSELL_PATH, ['home', 'dest', 'customers', 'pct'])
    if df.empty:
        return df
    df['customers'] = pd.to_numeric(df['customers'], errors='coerce').fillna(0).astype(int)
    df['pct'] = pd.to_numeric(df['pct'], errors='coerce').fillna(0.0)
    return df


@st.cache_data(ttl=3600)
def load_region_signups() -> pd.DataFrame:
    """지역별 신청 분포 (돈사공 초급반 9~12기 배송지)."""
    df = _read_csv(REGION_PATH, REGION_COLS)
    if df.empty:
        return df
    df['signups'] = pd.to_numeric(df['signups'], errors='coerce').fillna(0).astype(int)
    df['pct'] = pd.to_numeric(df['pct'], errors='coerce').fillna(0.0)
    return df


@st.cache_data(ttl=3600)
def load_region_cohort() -> pd.DataFrame:
    """기수별 수도권 비중·모집 기간."""
    df = _read_csv(REGION_COHORT_PATH, REGION_COHORT_COLS)
    if df.empty:
        return df
    for c in ['days', 'total', 'capital']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)
    df['capital_pct'] = pd.to_numeric(df['capital_pct'], errors='coerce').fillna(0.0)
    return df


@st.cache_data(ttl=3600)
def load_region_city() -> pd.DataFrame:
    """도시/구 단위 상위 신청 분포."""
    df = _read_csv(REGION_CITY_PATH, REGION_CITY_COLS)
    if df.empty:
        return df
    df['count'] = pd.to_numeric(df['count'], errors='coerce').fillna(0).astype(int)
    return df


@st.cache_data(ttl=3600)
def load_region_cohort_detail() -> pd.DataFrame:
    """기수별 지역 분포 상세 (cohort×region 신청 수·비율)."""
    df = _read_csv(REGION_COHORT_DETAIL_PATH, ['cohort', 'region', 'count', 'pct'])
    if df.empty:
        return df
    df['count'] = pd.to_numeric(df['count'], errors='coerce').fillna(0).astype(int)
    df['pct'] = pd.to_numeric(df['pct'], errors='coerce').fillna(0.0)
    return df


@st.cache_data(ttl=3600)
def load_region_cohort_topcity() -> pd.DataFrame:
    """기수별 주요 상위 도시/구."""
    df = _read_csv(REGION_COHORT_TOPCITY_PATH, ['cohort', 'city', 'count'])
    if df.empty:
        return df
    df['count'] = pd.to_numeric(df['count'], errors='coerce').fillna(0).astype(int)
    return df


@st.cache_data(ttl=3600)
def load_webinar_topics() -> pd.DataFrame:
    """무료특강 주제별 모객 수 (상품군·주제·모객)."""
    df = _read_csv(WEBINAR_TOPICS_PATH, ['product', 'topic', 'signups'])
    if df.empty:
        return df
    df['signups'] = pd.to_numeric(df['signups'], errors='coerce').fillna(0).astype(int)
    return df


@st.cache_data(ttl=3600)
def load_webinar_hook_ad() -> pd.DataFrame:
    """무료특강 후킹 소재별 메타 광고 성과 (마케팅시트 이관, 스냅샷).

    period·product·hook·creatives·spend·impressions·clicks·leads.
    leads = 메타 전환(0원강의 신청). 파생: ctr·cvr·cpl.
    """
    df = _read_csv(WEBINAR_HOOK_AD_PATH,
                   ['period', 'product', 'hook', 'format', 'creatives',
                    'spend', 'impressions', 'clicks', 'leads'])
    if df.empty:
        return df
    if 'format' not in df.columns:       # 구버전 파일 호환
        df['format'] = '기타'
    for c in ['creatives', 'spend', 'impressions', 'clicks', 'leads']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)
    df['ctr'] = (df['clicks'] / df['impressions'] * 100).where(df['impressions'] > 0, 0.0)
    df['cvr'] = (df['leads'] / df['clicks'] * 100).where(df['clicks'] > 0, 0.0)
    df['cpl'] = (df['spend'] / df['leads']).where(df['leads'] > 0, 0.0)
    return df


@st.cache_data(ttl=600)
def load_refresh_status() -> pd.DataFrame:
    """자동 갱신 실행 상태 — 맥의 launchd 작업이 남긴 기록.

    로그는 그 맥에만 있어 자동 갱신이 멈춰도 알아채기 어렵다.
    실행 결과를 사이트에서 보이게 해 중단을 즉시 알 수 있게 한다.
    """
    return _read_csv(REFRESH_STATUS_PATH,
                     ['last_run', 'market_signals', 'order_aggregates',
                      'rooms', 'changed', 'alerts'])


@st.cache_data(ttl=1800)
def load_market_signals() -> pd.DataFrame:
    """시장 신호 — 키워드 분석툴(별도 앱)에서 이관한 소재 기획용 데이터.

    signal: own_top(자사 고성과 콘텐츠 제목) · market_top(시장 상위 영상 제목)
            · age(키워드별 최고 반응 연령대)
    키워드툴은 로컬 전용이라 직접 호출이 불가능해, 캐시를 CSV로 옮겨 쓴다.
    scripts/sync_market_signals.py 로 갱신.
    """
    df = _read_csv(MARKET_SIGNALS_PATH,
                   ['product', 'signal', 'rank_by', 'text',
                    'metric1', 'metric2', 'collected'])
    if df.empty:
        return df
    df['metric1'] = pd.to_numeric(df['metric1'], errors='coerce').fillna(0).astype(int)
    return df


@st.cache_data(ttl=300)
def load_webinar_schedule() -> pd.DataFrame:
    """무료특강(웨비나) 진행 일정 — 모객 계획의 기준선.

    이 일정이 있어야 '언제 무엇을 준비해야 하는지'와 '그 시기가 그 강의에
    유리한지'를 미리 판단할 수 있다.
    """
    df = _read_csv(WEBINAR_SCHEDULE_PATH, WEBINAR_SCHEDULE_COLS)
    if df.empty:
        return df
    for c in ['target_signups', 'budget']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    return df.dropna(subset=['date']).sort_values('date').reset_index(drop=True)


def save_webinar(row: dict):
    """웨비나 일정 저장/수정 (id 같으면 갱신)."""
    df = _read_csv(WEBINAR_SCHEDULE_PATH, WEBINAR_SCHEDULE_COLS)
    if not df.empty and 'id' in df.columns:
        df = df[df['id'].astype(str) != str(row['id'])]
    new = pd.DataFrame([{c: row.get(c, '') for c in WEBINAR_SCHEDULE_COLS}])
    _write_csv(WEBINAR_SCHEDULE_PATH, pd.concat([df, new], ignore_index=True),
               f"웨비나 일정 저장: {row.get('date')} {row.get('product')}")
    load_webinar_schedule.clear()


def delete_webinar(wid: str):
    df = _read_csv(WEBINAR_SCHEDULE_PATH, WEBINAR_SCHEDULE_COLS)
    if df.empty:
        return
    _write_csv(WEBINAR_SCHEDULE_PATH,
               df[df['id'].astype(str) != str(wid)], f"웨비나 일정 삭제: {wid}",
               allow_shrink=True)
    load_webinar_schedule.clear()


@st.cache_data(ttl=300)
def load_experiments() -> pd.DataFrame:
    """마케팅 실험 일지 — 무엇을 왜 했고 결과가 어땠는지 기록.

    기록하지 않은 실험은 학습으로 남지 않는다. 실행(가설·예산)과
    결과(모객·전환·매출)를 한 행에 모아 회고와 대표 보고에 쓴다.
    """
    df = _read_csv(EXPERIMENTS_PATH, EXPERIMENTS_COLS)
    if df.empty:
        return df
    for c in ['budget', 'leads', 'conversions', 'revenue']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)
    df['cpl'] = (df['budget'] / df['leads']).where(df['leads'] > 0, 0.0)
    df['cvr'] = (df['conversions'] / df['leads'] * 100).where(df['leads'] > 0, 0.0)
    df['roas'] = (df['revenue'] / df['budget']).where(df['budget'] > 0, 0.0)
    return df.sort_values('start', ascending=False).reset_index(drop=True)


def save_experiment(row: dict):
    """실험 저장/수정 (id가 같으면 갱신)."""
    df = _read_csv(EXPERIMENTS_PATH, EXPERIMENTS_COLS)
    if not df.empty and 'id' in df.columns:
        df = df[df['id'].astype(str) != str(row['id'])]
    new = pd.DataFrame([{c: row.get(c, '') for c in EXPERIMENTS_COLS}])
    combined = pd.concat([df, new], ignore_index=True)
    _write_csv(EXPERIMENTS_PATH, combined, f"실험 일지 저장: {row.get('id')}")
    load_experiments.clear()


def delete_experiment(exp_id: str):
    """실험 삭제."""
    df = _read_csv(EXPERIMENTS_PATH, EXPERIMENTS_COLS)
    if df.empty:
        return
    df = df[df['id'].astype(str) != str(exp_id)]
    _write_csv(EXPERIMENTS_PATH, df, f"실험 일지 삭제: {exp_id}", allow_shrink=True)
    load_experiments.clear()


@st.cache_data(ttl=3600)
def load_ohaeng_period() -> pd.DataFrame:
    """오행(五行) 시기별 모객·전환 — 절기 기준 명리월 집계.

    양력 달이 아니라 **절입일 기준 명리월**로 주문을 다시 묶은 것.
    월주의 천간·지지가 각각 어느 오행인지(stem_element/branch_element)로
    시기를 나눠 모객·전환을 비교할 수 있다.
    """
    df = _read_csv(OHAENG_PERIOD_PATH,
                   ['product', 'saju_year', 'saju_month', 'year_pillar', 'month_pillar',
                    'stem', 'branch', 'stem_element', 'branch_element',
                    'free_signups', 'paid_orders', 'revenue'])
    if df.empty:
        return df
    if 'product' not in df.columns:      # 구버전 파일 호환
        df['product'] = '전체'
    for c in ['saju_year', 'saju_month', 'free_signups', 'paid_orders', 'revenue']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)
    df['conv_rate'] = (df['paid_orders'] / df['free_signups'] * 100).where(
        df['free_signups'] > 0, 0.0)
    return df.sort_values(['saju_year', 'saju_month']).reset_index(drop=True)


@st.cache_data(ttl=3600)
def load_stage_timeline() -> pd.DataFrame:
    """단계-강의 타임라인 (product·stage·cohort·start·end·orders)."""
    df = _read_csv(STAGE_TIMELINE_PATH, ['product', 'stage', 'cohort', 'start', 'end', 'orders'])
    if df.empty:
        return df
    df['orders'] = pd.to_numeric(df['orders'], errors='coerce').fillna(0).astype(int)
    return df


@st.cache_data(ttl=600)
def load_data_sources() -> pd.DataFrame:
    """데이터 소스 레지스트리 (데이터·출처·기준시점·갱신 방법)."""
    return _read_csv(DATA_SOURCES_PATH,
                     ['category', 'dataset', 'source', 'as_of', 'cadence', 'refresh'])


@st.cache_data(ttl=600)
def order_asof():
    """주문 원본이 담고 있는 마지막 날짜 (없으면 None).

    이 날짜가 '어느 달까지 완결됐나'의 기준이다. 오늘 날짜로 판정하면 안 된다 —
    주문 명단은 사람이 쇼핑몰에서 내려받아 전달하는 스냅샷이라 며칠~몇 주 뒤처지고,
    그동안 마지막 달은 '일부만 담긴 달'이 된다. 실제로 2026-07은 7/19까지만 담겨
    매출이 6,744만원(6월 9.4억)으로 찍혔는데, 이걸 완결된 달로 보고 런레이트를
    계산해 전망이 10% 낮게 나오고 있었다.
    """
    ds = load_data_sources()
    if ds.empty:
        return None
    _r = ds[ds['source'].astype(str).str.contains('강의별_리스트', na=False)]
    if _r.empty:
        return None
    try:
        return pd.to_datetime(_r['as_of'].iloc[0]).date()
    except (ValueError, TypeError):
        return None


def update_order_asof(asof) -> bool:
    """주문 원본 기준일을 데이터 레지스트리에 반영.

    order_asof()가 읽는 값이라, 여기가 갱신되지 않으면 새 명단을 올려도
    사이트는 계속 옛 스냅샷 기준으로 부분월을 판정한다.
    """
    ds = load_data_sources()
    if ds.empty:
        return False
    _m = ds['source'].astype(str).str.contains('강의별_리스트', na=False)
    if not _m.any():
        return False
    ds.loc[_m, 'as_of'] = str(asof)
    _write_csv(DATA_SOURCES_PATH, ds, f"data: 주문 원본 기준일 {asof}")
    return True


def save_order_aggregates(out: dict, asof, on_step=None):
    """주문 집계 CSV 일괄 저장. (성공수, 전체수, 실패목록) 반환.

    on_step(i, name)으로 진행 상황을 알린다 — 16종을 순차 저장하느라
    시간이 걸려서, 화면이 멈춘 것처럼 보이면 사용자가 새로고침해 버린다.
    """
    fails = []
    for i, (name, df) in enumerate(out.items(), 1):
        if on_step:
            on_step(i, name)
        try:
            _write_csv(f"data/{name}", df, f"data: 주문 집계 갱신 ({asof}) — {name}",
                       allow_shrink=True)
        except Exception as e:                     # 한 건 실패가 나머지를 막지 않게
            fails.append(f"{name}: {type(e).__name__}")
    if not fails:
        update_order_asof(asof)
    return len(out) - len(fails), len(out), fails


def complete_months(df: pd.DataFrame, col: str = 'month') -> pd.DataFrame:
    """분석용으로 쓸 수 있는 '완결된 달'만. (부분월·미래월 제외)

    추이·평균·전망처럼 달끼리 비교하는 계산은 반드시 이걸 거쳐야 한다.
    화면에 '보여주는' 것까지 지우지는 않는다 — 부분월도 사실이고, 숨기면
    데이터가 사라진 것처럼 보인다. 대신 부분월임을 라벨로 밝힌다.
    """
    if df.empty or col not in df.columns:
        return df
    _cut = date.today().strftime('%Y-%m')          # 당월은 언제나 진행 중
    _asof = order_asof()
    if _asof:
        _cut = min(_cut, _asof.strftime('%Y-%m'))  # 주문 스냅샷이 끊긴 달도 부분월
    return df[df[col].astype(str) < _cut]


@st.cache_data(ttl=3600)
def load_webinar_conversion() -> pd.DataFrame:
    """후킹별 전환 (고유 모객·전환자·전환율·자사 전환·self 비중)."""
    df = _read_csv(WEBINAR_CONV_PATH, ['product', 'topic', 'unique_signups', 'converters',
                                       'conv_rate', 'self_converters', 'self_rate', 'self_share'])
    if df.empty:
        return df
    for c in ['unique_signups', 'converters', 'self_converters']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)
    for c in ['conv_rate', 'self_rate', 'self_share']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
    # 구버전 데이터(자사 컬럼 없음) 대비
    if 'self_share' not in df.columns:
        df['self_share'] = 0.0
    return df


# ── 날짜별 메모 ───────────────────────────────────────────────────

DATE_NOTES_PATH = "data/date_notes.csv"
DATE_NOTES_COLS = ['date', 'memo']


@st.cache_data(ttl=300)  # 당일 메모 수정 가능성 고려
def load_date_notes() -> pd.DataFrame:
    df = _read_csv(DATE_NOTES_PATH, DATE_NOTES_COLS)
    if df.empty:
        return df
    df['date'] = pd.to_datetime(df['date']).dt.date
    return df


def send_slack_alert(webhook_url: str, message: str) -> bool:
    """Slack Incoming Webhook 알림 전송. 성공 여부를 돌려준다.

    예전에는 실패를 통째로 삼켰다. 그런데 이 알림은 '아무도 안 보고 있을 때'를
    위한 장치라, 조용히 실패하면 장치가 없는 것과 똑같아진다(웹훅 주소가
    만료돼도 아무도 모른다). 부르는 쪽이 실패를 표시할 수 있게 돌려준다.
    """
    if not webhook_url:
        return False
    try:
        res = requests.post(webhook_url, json={"text": message}, timeout=5)
        return res.ok
    except Exception:
        return False


def save_date_note(date_str: str, memo: str):
    """날짜별 메모 저장(upsert). 빈 문자열이면 해당 날짜 메모 삭제."""
    df = load_date_notes()
    if not df.empty:
        df = df[df['date'].astype(str) != date_str]
    if memo.strip():
        new_row = pd.DataFrame([{'date': date_str, 'memo': memo.strip()}])
        combined = pd.concat([df, new_row], ignore_index=True).sort_values('date').reset_index(drop=True)
    else:
        combined = df
    _write_csv(DATE_NOTES_PATH, combined, f"날짜 메모: {date_str}")
    load_date_notes.clear()


# ── 첫 로딩 예열 ────────────────────────────────────────────────

def warm_cache(max_workers: int = 8) -> int:
    """모든 load_* 로더를 **동시에** 한 번씩 불러 캐시를 채운다.

    첫 로딩 19초의 정체는 탭을 그리는 비용이 아니었다 — 재렌더는 1.4초인데
    첫 화면만 19초였다. 원격 CSV 46종을 **하나씩 순서대로** 받아오느라 왕복
    지연이 그대로 쌓인 것이다(건당 365ms × 46 ≈ 17초). 서로 의존하지 않는
    파일들이라 순서대로 받을 이유가 없다 — 동시에 받으면 2초면 끝난다.

    캐시 의미는 건드리지 않는다. 로더마다 붙은 @st.cache_data와 TTL을 그대로
    쓰고, 여기서는 그 함수들을 미리 한 번 호출할 뿐이다. 이미 캐시가 차 있으면
    전부 즉시 반환이라 비용이 사실상 없다.

    예열이 실패해도 화면은 평소대로 그려져야 한다 — 각 호출의 예외는 삼키고,
    실제 값은 렌더 시점에 로더가 다시(이번엔 정상 경로로) 가져간다.
    """
    fns = []
    for name, fn in list(globals().items()):
        if not name.startswith("load_") or not callable(fn):
            continue
        try:                       # 인자가 필요한 로더는 예열 대상이 아니다
            sig = inspect.signature(fn)
            if any(p.default is inspect.Parameter.empty
                   and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
                   for p in sig.parameters.values()):
                continue
        except (TypeError, ValueError):
            continue
        fns.append(fn)

    def _call(f):
        try:
            f()
        except Exception:          # 예열 실패가 화면을 막지 않는다
            pass

    if fns:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            list(ex.map(_call, fns))
    return len(fns)
