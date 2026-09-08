import streamlit as st
import ganji
import pandas as pd
import re
import shutil
from datetime import date, timedelta

from github_store import (
    load_all, save_daily, delete_date,
    load_campaigns, get_current_campaigns,
    save_campaign, end_campaign, get_history, update_lecture_start_date,
    load_rooms, save_room, save_rooms_batch, delete_room,
    load_archived_rooms, archive_room, restore_room, load_all_room_names,
    update_actual_close_date,
    load_conversions, save_conversion, get_latest_conversions, delete_conversion_row,
    load_enrollments, save_enrollment, delete_enrollment,
    load_marketing, load_monthly_performance,
    load_ad_spend_monthly, save_ad_spend_monthly, AD_CHANNEL_OPTIONS,
    load_targets, save_target,
    load_competitor_courses,
    load_cohort_revenue, load_course_summary, load_campaign_adspend,
    load_monthly_by_course, load_cohort_stage, STAGE_ORDER,
    load_cust_repeat_dist, load_cust_ltv_dist, load_cust_product_repeat,
    load_cust_cross_sell, load_cust_monthly_new_repeat,
    load_cust_repeat_timing, load_cust_retention_curve, load_cust_retention_matrix,
    load_cust_product_timing, load_cust_product_retention, load_cust_product_nextbuy,
    load_cust_crosssell_path,
    load_region_signups, load_region_cohort, load_region_city, CAPITAL_REGIONS,
    load_region_cohort_detail, load_region_cohort_topcity,
    load_webinar_topics, load_webinar_conversion, load_webinar_hook_ad,
    load_ohaeng_period,
    load_experiments, save_experiment, delete_experiment, load_market_signals,
    load_webinar_schedule, save_webinar, delete_webinar,
    load_refresh_status,
    load_data_sources, load_stage_timeline, order_asof, complete_months,
    warm_cache,
    save_order_aggregates,
    load_adspend, save_adspend, delete_adspend_row,
    load_content, save_content, delete_content_row,
    load_date_notes, save_date_note,
    send_slack_alert,
    PRODUCT_OPTIONS, CHANNEL_OPTIONS, CONTENT_TYPE_OPTIONS,
)
from alerts import (
    generate_alerts as _generate_alerts,
    lecture_date_split as _lecture_date_split,
    name_list as _name_list,
    slack_message,
)
from charts import (
    trend_line_chart, change_bar_chart, total_trend_bar,
    product_bar_chart, weekly_comparison_chart, cohort_trend_chart,
    funnel_chart, conversion_rate_chart, cohort_conversion_chart,
    churn_rate_chart, roi_chart,
    ranking_chart, weekly_aggregate_chart, monthly_aggregate_chart,
    cpm_chart, content_impact_table, trend_forecast_chart,
    room_snapshot_chart, period_total_trend, calendar_heatmap_chart,
    recruitment_curve_chart, retention_after_opening_chart, cohort_efficiency_df,
    cohort_funnel_data, conversion_funnel_chart, cohort_conversion_bar_chart,
    marketing_channel_summary, marketing_channel_chart, marketing_trend_chart,
    marketing_channel_conv_chart, monthly_perf_chart, competitor_price_chart,
    cohort_revenue_chart, product_revenue_mix_chart, monthly_roas_chart,
    monthly_lead_cpa_chart,
    region_distribution_chart, region_capital_trend_chart, region_city_chart,
    region_bubble_map,
    product_ad_roi_chart, cohort_ad_roi_chart,
    overall_conversion_funnel, product_conversion_rate_chart,
    monthly_course_heatmap, monthly_course_stack,
    stage_funnel_chart, cohort_stage_matrix_chart, webinar_topic_chart, webinar_hook_ad_chart,
    webinar_quadrant_chart, webinar_selfconv_chart,
    stage_timeline_chart, ad_efficiency_diagnosis,
    ohaeng_chart, ohaeng_timeline_chart, room_funnel_chart,
    cust_repeat_donut, cust_ltv_bar, cust_product_repeat_chart,
    cross_sell_heatmap, monthly_new_repeat_chart,
    runrate_forecast_chart,
    repeat_timing_chart, retention_curve_chart, retention_heatmap,
    target_vs_actual_chart,
    product_retention_curve_chart, nextbuy_chart, crosssell_path_heatmap,
    relabel_month_axis,
)

# ── 그래프 월 축을 한글+간지(사주 구조)로 자동 변환 ──────────────
# 모든 plotly 차트의 x축이 양력 월(YYYY-MM)이면 '2026년 6월 / 丙午 甲午'로
# 눈금을 바꾼다. 중앙 1곳에서 st.plotly_chart를 감싸 전 그래프에 일괄 적용
# (달력 월이 아닌 축은 무해한 no-op). 명리학적 해석을 위해 천간지지 병기.
# ⚠️ Streamlit은 상호작용마다 스크립트를 새 네임스페이스로 재실행한다. 가드가
# 없으면 재실행마다 래퍼가 한 겹씩 중첩돼 결국 RecursionError로 사이트가 죽는다.
if not getattr(st.plotly_chart, '_ganji_patched', False):
    _orig_plotly_chart = st.plotly_chart

    def _plotly_chart_ganji(fig, *args, **kwargs):
        try:
            if hasattr(fig, 'data'):
                relabel_month_axis(fig)
        except Exception:
            pass
        return _orig_plotly_chart(fig, *args, **kwargs)

    _plotly_chart_ganji._ganji_patched = True
    st.plotly_chart = _plotly_chart_ganji

st.set_page_config(
    page_title="황금후추 강의 분석",
    page_icon="📊",
    layout="wide",
)

# ── 모바일 반응형 CSS ─────────────────────────────────────────────
st.markdown("""
<style>
/* 모바일(768px 이하): 3컬럼 → 1컬럼 스택 */
@media (max-width: 768px) {
    div[data-testid="column"] { min-width: 100% !important; }
    div[data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; }
    /* 버튼 전체 너비 */
    div[data-testid="stButton"] button { width: 100% !important; }
    /* 숫자 입력 폰트 확대 */
    input[type="number"] { font-size: 16px !important; }
}
/* 검토 테이블 텍스트 줄 바꿈 방지 */
div[data-testid="stDataFrame"] td { white-space: nowrap; }

/* ── 리포트형 카드 (지역 분석 등 도식화) ── */
.gp-kpi-row{display:flex;gap:12px;flex-wrap:wrap;margin:6px 0 4px}
.gp-kpi{flex:1;min-width:150px;background:rgba(128,128,128,.08);
  border:1px solid rgba(128,128,128,.18);border-radius:14px;padding:14px 16px;position:relative;overflow:hidden}
.gp-kpi::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:#B0812A}
.gp-kpi .k{font-size:12px;opacity:.68;margin:0 0 4px;font-weight:600}
.gp-kpi .v{font-size:26px;font-weight:800;line-height:1.05;letter-spacing:-.02em}
.gp-kpi .v small{font-size:14px;font-weight:700;opacity:.7}
.gp-kpi .s{font-size:11.5px;opacity:.6;margin-top:3px}
.gp-card{background:rgba(128,128,128,.08);border:1px solid rgba(128,128,128,.18);
  border-radius:14px;padding:14px 16px;height:100%}
.gp-card .ch{display:flex;align-items:baseline;justify-content:space-between;gap:8px;
  border-bottom:1px solid rgba(128,128,128,.2);padding-bottom:7px;margin-bottom:9px}
.gp-card .ch b{font-size:15px;font-weight:800}
.gp-card .ch .tot{font-size:12.5px;opacity:.65;font-weight:700}
.gp-rank{display:flex;align-items:center;gap:8px;font-size:12.5px;padding:2.5px 0}
.gp-rank .rn{width:15px;opacity:.5;font-weight:700;flex:none;text-align:right}
.gp-rank .rr{width:42px;flex:none;font-weight:600}
.gp-rank .rbar{flex:1;height:9px;background:rgba(128,128,128,.14);border-radius:5px;overflow:hidden}
.gp-rank .rbar > i{display:block;height:100%;background:#5B8FF9;border-radius:5px}
.gp-rank .rv{width:58px;flex:none;text-align:right;opacity:.8;font-variant-numeric:tabular-nums}
.gp-city{font-size:12px;opacity:.85;margin-top:9px;padding-top:8px;border-top:1px dashed rgba(128,128,128,.25)}
.gp-city b{color:#B0812A}
.gp-brief{display:flex;gap:11px;padding:11px 2px;border-top:1px solid rgba(128,128,128,.15);align-items:flex-start}
.gp-brief:first-of-type{border-top:none}
.gp-brief .bi{font-size:18px;flex:none;line-height:1.35}
.gp-brief .bt{font-size:14px;line-height:1.6}
.gp-brief .bt .tt{font-weight:800}
.gp-brief b{font-weight:800}
.gp-dtbl th{padding:7px 8px;border-bottom:2px solid rgba(128,128,128,.3)}
.gp-dtbl td{padding:7px 8px;border-bottom:1px solid rgba(128,128,128,.15);vertical-align:top}
</style>
""", unsafe_allow_html=True)


def _dataset_asof(keyword: str):
    """데이터 레지스트리에서 특정 데이터의 기준 시점 문자열. 없으면 None.

    오래된 스냅샷을 현재 값으로 읽으면 판단이 틀어진다(주문 부분월 건과 같은
    계열). 화면에 기준 시점을 함께 적기 위한 조회용.
    """
    _ds = load_data_sources()
    if _ds.empty:
        return None
    _m = _ds[_ds['dataset'].astype(str).str.contains(keyword, na=False)]
    return str(_m['as_of'].iloc[0]) if not _m.empty else None


def _asof_tag(keyword: str, unit: str = "개월") -> str:
    """'(2025-12 기준 · 약 8개월 전)' 같은 꼬리표. 없으면 빈 문자열.

    v4.74가 지역 분포 **탭에만** 기준 시점을 붙였는데, 같은 데이터로 광고
    예산 배정을 지시하는 곳이 세 군데 더 있었다(종합 보고 KPI·전략 브리핑·
    소재 브리프). 거기서는 8개월 전 스냅샷이 '지금의 지역 분포'로 읽혔다.
    판정을 한 곳에 두어 다시 어긋나지 않게 한다.
    """
    _a = _dataset_asof(keyword)
    if not _a:
        return ""
    try:
        _mo = (date.today().year - int(_a[:4])) * 12 + (date.today().month - int(_a[5:7]))
    except (ValueError, IndexError):
        _mo = None
    return f"({_a} 기준" + (f" · 약 {_mo}{unit} 전)" if _mo and _mo >= 3 else ")")


@st.cache_data(ttl=1800, show_spinner=False, max_entries=1)
def _parse_order_upload(_bytes: bytes):
    """업로드한 주문 엑셀 → (요약, 집계 16종). 원본 주문 데이터는 반환하지 않는다.

    개인정보(이름·번호)가 담긴 원본은 이 함수 안에서만 존재하고, 밖으로는
    집계 숫자와 요약만 나간다. 캐시도 1건만 유지한다(max_entries=1).
    12만 행 파싱에 약 7초 — 위젯이 바뀔 때마다 다시 읽지 않도록 캐시한다.
    """
    import io as _io
    from scripts.refresh_order_aggregates import load_orders, build_all
    o = load_orders(_io.BytesIO(_bytes))
    summary = {
        'rows': len(o),
        'paid': int((o['pay'] > 0).sum()),
        'custs': int(o['cust'].nunique()),
        'revenue': int(o.loc[o['pay'] > 0, 'pay'].sum()),
        'first': o['d'].min(),
        'last': o['d'].max(),
    }
    return summary, build_all(o)


def _adspend_prorated(d1, d2):
    """[d1,d2] 기간과 겹치는 **전사 월별 광고비**를 일할 배분해 합산.

    반환: (금액, 입력이 있는 월, 입력이 없는 월).
    방별 광고비 수기 입력은 계속 비어 있는데 전사 월별 광고비는 실제로 쌓여
    있어서, '광고비 없음'이라고만 적히면 광고를 안 쓴 것처럼 읽힌다.
    출처가 다르므로 화면에서 라벨을 구분해 쓴다(리포트 수치에는 섞지 않는다).
    """
    adm = load_ad_spend_monthly()
    t1, t2 = pd.Timestamp(d1), pd.Timestamp(d2)
    want = [str(p) for p in pd.period_range(t1.to_period('M'), t2.to_period('M'), freq='M')]
    if adm.empty:
        return 0, [], want
    per_month = adm.groupby(adm['month'].astype(str))['spend'].sum()
    total, have = 0.0, []
    for m in want:
        if m not in per_month.index:
            continue
        m_start = pd.Timestamp(m + '-01')
        m_end   = m_start + pd.offsets.MonthEnd(0)
        days = (min(m_end, t2) - max(m_start, t1)).days + 1
        if days <= 0:
            continue
        total += float(per_month[m]) * days / m_end.day
        have.append(m)
    return int(round(total)), have, [m for m in want if m not in have]


def _kpi_band(items):
    """리포트형 KPI 밴드 렌더. items: [(label, value_html, sub), ...].
    value_html는 <small> 등 HTML 허용. 카드 CSS(.gp-kpi)는 전역 정의."""
    st.markdown('<div class="gp-kpi-row">' + ''.join(
        f'<div class="gp-kpi"><p class="k">{k}</p><div class="v">{v}</div>'
        f'<p class="s">{s}</p></div>' for k, v, s in items) + '</div>',
        unsafe_allow_html=True)


# ── 사이드바 — 캐시 새로고침 ─────────────────────────────────────

APP_VERSION = "v4.87"  # 배포 반영 확인용 — 화면 버전이 다르면 아직 리부팅 전

with st.sidebar:
    st.markdown("### 📊 황금후추 강의 분석")
    # 오늘이 속한 '명리 월'(절기 기준). 8/3은 입추(8/7) 전이라 아직 7월(乙未月).
    _ty, _tm = ganji.saju_month_of(date.today()) or (date.today().year, date.today().month)
    st.markdown(
        f'<div style="font-size:12px;opacity:.7">{APP_VERSION} · '
        f'{ganji.ym_korean(_ty, _tm)}</div>'
        f'<div style="font-size:15px;letter-spacing:1px">'
        f'{ganji.colorize(ganji.year_ganji(_ty, _tm))} '
        f'{ganji.colorize(ganji.month_ganji(_ty, _tm))}</div>',
        unsafe_allow_html=True)
    st.divider()

    # 오늘 입력 상태
    _df_check = load_all()
    _today_str = str(date.today())
    if _df_check.empty or _today_str not in _df_check['date'].astype(str).values:
        st.error(f"⚠️ 오늘({_today_str}) 데이터 미입력", icon="🚨")
    else:
        _n_today = len(_df_check[_df_check['date'].astype(str) == _today_str])
        st.success(f"✅ 오늘 {_n_today}개 방 입력 완료")

    # 최근 7일 완성도 및 누락 날짜 경고
    if not _df_check.empty:
        _recent_7 = [str(date.today() - timedelta(days=i)) for i in range(7)]
        _entered_7 = set(_df_check['date'].astype(str).unique())
        _missing_7 = [d for d in _recent_7 if d not in _entered_7]
        _comp_7 = round((7 - len(_missing_7)) / 7 * 100)
        st.caption(f"최근 7일 입력률 **{_comp_7}%**")
        if _missing_7:
            st.warning("누락: " + ", ".join(sorted(_missing_7, reverse=True)[:3]) +
                       (f" 외 {len(_missing_7)-3}일" if len(_missing_7) > 3 else "") +
                       "\n\n→ 🗂️ 데이터 관리 탭에서 소급 입력할 수 있습니다",
                       icon="📅")
        # 연속 입력일 — 습관이 유지되는지 한눈에
        _streak = 0
        _d = date.today()
        if _today_str not in _entered_7:      # 오늘 아직이면 어제부터 센다
            _d -= timedelta(days=1)
        while str(_d) in _df_check['date'].astype(str).values:
            _streak += 1
            _d -= timedelta(days=1)
        if _streak >= 3:
            st.caption(f"🔥 연속 입력 **{_streak}일**")

    # 진행 중인데 개강일이 비어 있는 강의 — 개강 효과 분석에서 통째로 빠진다
    _miss_ld, _wait_ld = _lecture_date_split(load_campaigns())
    if not _miss_ld.empty:
        st.warning(
            f"📅 개강일 미입력 **{len(_miss_ld)}건**\n\n"
            + _name_list(_miss_ld)
            + "\n\n→ ⚙️ 채팅방 설정에서 입력하면 개강 효과 분석에 반영됩니다",
            icon="⚠️")
    if not _wait_ld.empty:
        # 며칠째 대기인지가 빠지면 '정상'과 '넉 달째 방치'가 같아 보인다.
        _wd_days = pd.to_datetime(_wait_ld['start_date'], errors='coerce')
        _wd_max = (pd.Timestamp(date.today()) - _wd_days).dt.days.max()
        st.caption(f"🕗 개강 대기 **{len(_wait_ld)}개 방** — {_name_list(_wait_ld)} "
                   + (f"· 최장 {int(_wd_max)}일째 " if pd.notna(_wd_max) else "")
                   + "(웨비나 후 개강일이 자동으로 채워집니다)")

    st.divider()
    if st.button("🔄 데이터 새로고침", width='stretch',
                 help="GitHub에서 최신 데이터를 강제로 다시 불러옵니다 (3분 캐시 초기화)"):
        load_all.clear()
        load_campaigns.clear()
        load_rooms.clear()
        load_conversions.clear()
        load_adspend.clear()
        load_content.clear()
        load_date_notes.clear()
        st.toast("✅ 데이터를 새로고침했습니다", icon="🔄")
        st.rerun()
    st.caption(f"마지막 갱신: {pd.Timestamp.now().strftime('%H:%M:%S')}")

# ── 세션 상태 초기화 ──────────────────────────────────────────────

if 'ocr_results' not in st.session_state:
    st.session_state.ocr_results = {}
if 'ocr_done' not in st.session_state:
    st.session_state.ocr_done = False
if 'uploaded_file_names' not in st.session_state:
    st.session_state.uploaded_file_names = []
if 'pending_delete_date' not in st.session_state:
    st.session_state.pending_delete_date = None
if '_pending_new_rooms' not in st.session_state:
    st.session_state._pending_new_rooms = {}
if '_editing_room' not in st.session_state:
    st.session_state._editing_room = None
if '_ocr_error' not in st.session_state:
    st.session_state._ocr_error = None
if '_ocr_model' not in st.session_state:
    st.session_state._ocr_model = ''
if '_pending_archive' not in st.session_state:
    st.session_state['_pending_archive'] = None



# ── OCR 검토 테이블 ───────────────────────────────────────────────

def _show_ocr_review(ocr_results: dict, rooms: dict, prev: dict):
    """OCR 인식 결과를 전체 채팅방 기준으로 보여주는 검토 테이블.
    인식되지 않은 방도 '미인식' 상태로 표시한다."""
    rows = []
    has_warning = False
    recognized = 0

    for rn in sorted(rooms.keys()):
        name = rooms.get(rn, f"채팅방 {rn}")
        ocr_val = ocr_results.get(rn)
        prev_val = prev.get(rn)

        if ocr_val is None:
            rows.append({
                "채팅방": name,
                "인식값": None,
                "전일": int(prev_val) if prev_val is not None else None,
                "증감": None,
                "상태": "❌ 미인식",
            })
            continue

        recognized += 1
        if prev_val is not None:
            diff = ocr_val - int(prev_val)
            pct  = abs(diff / prev_val * 100) if prev_val else 0
            # 방 규모에 비례한 임계값 (작은 방엔 느슨, 큰 방엔 엄격)
            if prev_val >= 500:
                warn_pct, alert_pct = 15, 30
            elif prev_val >= 100:
                warn_pct, alert_pct = 20, 40
            else:
                warn_pct, alert_pct = 25, 50
            if pct > alert_pct or abs(diff) > 1000:
                status = "🚨 확인 필요"
                has_warning = True
            elif pct > warn_pct or abs(diff) > 500:
                status = "⚠️ 변동 큼"
                has_warning = True
            else:
                status = "✅ 정상"
        else:
            diff = None
            status = "➕ 신규"

        rows.append({
            "채팅방": name,
            "인식값": ocr_val,
            "전일": int(prev_val) if prev_val is not None else None,
            "증감": diff,
            "상태": status,
        })

    if not rows:
        return

    total = len(rooms)
    unrecognized = total - recognized

    st.subheader(f"인식 결과 검토 ({recognized} / {total}개 인식)")

    if unrecognized > 0:
        miss_names = [rooms.get(rn, f"채팅방 {rn}") for rn in sorted(rooms.keys()) if rn not in ocr_results]
        st.error(f"❌ {unrecognized}개 미인식 — 2단계에서 직접 입력하세요: " + "  |  ".join(miss_names))
    if has_warning:
        st.warning("⚠️ 이상값 감지 — 아래 표를 확인하고 2단계에서 수정하세요.")
    if recognized == total and not has_warning:
        st.success("모든 채팅방 인식 완료. 값이 맞으면 3단계에서 저장하세요.")

    df_review = pd.DataFrame(rows)

    def _row_color(row):
        s = row.get("상태", "")
        if s == "❌ 미인식":
            return ["background-color: #ffebee"] * len(row)
        if s == "🚨 확인 필요":
            return ["background-color: #fff3e0"] * len(row)
        if s == "⚠️ 변동 큼":
            return ["background-color: #fffde7"] * len(row)
        return [""] * len(row)

    st.dataframe(
        df_review.style.apply(_row_color, axis=1),
        hide_index=True,
        column_config={
            "인식값": st.column_config.NumberColumn(format="%d명"),
            "전일": st.column_config.NumberColumn(format="%d명"),
            "증감": st.column_config.NumberColumn(format="%+d명"),
        },
    )

    # 하단 요약: OCR 인식 / 전일 데이터 / 미입력
    n_ocr   = sum(1 for r in rows if r["상태"] not in ("❌ 미인식",) and r["인식값"] is not None)
    n_miss  = sum(1 for r in rows if r["상태"] == "❌ 미인식")
    n_warn  = sum(1 for r in rows if r["상태"] in ("🚨 확인 필요", "⚠️ 변동 큼"))
    sc1, sc2, sc3 = st.columns(3)
    sc1.metric("📷 OCR 인식", f"{n_ocr}개")
    sc2.metric("❌ 미인식", f"{n_miss}개", delta=f"-{n_miss}" if n_miss else None,
               delta_color="inverse")
    sc3.metric("⚠️ 이상값", f"{n_warn}개", delta=f"{n_warn}건 확인 필요" if n_warn else "이상 없음",
               delta_color="inverse" if n_warn else "off")
    if n_warn > 0:
        st.caption("💡 이상값이 광고·이벤트 등 특수 상황이면 3단계 저장 후 메모를 남기세요. 메모는 추이 그래프에 오버레이로 표시됩니다.")


# ── 로그인 인증 ──────────────────────────────────────────────────

def _run_auth() -> bool:
    """Secrets에 app_password 가 있으면 비밀번호 게이트를 실행.
    없으면 즉시 True(통과) 반환 — 로컬 개발 시 자동 우회."""
    pw_secret = st.secrets.get("app_password", "")
    if not pw_secret:
        return True

    if st.session_state.get("_authenticated"):
        return True

    st.title("📊 황금후추 강의 분석")
    st.subheader("🔒 로그인")
    with st.form("login_form"):
        entered = st.text_input("비밀번호", type="password", placeholder="비밀번호를 입력하세요")
        if st.form_submit_button("로그인", type="primary", width='stretch'):
            if entered == pw_secret:
                st.session_state["_authenticated"] = True
                st.rerun()
            else:
                st.error("비밀번호가 올바르지 않습니다.")
    return False


# ── 메인 ─────────────────────────────────────────────────────────

def _safe_tab(fn, label):
    """탭 하나가 터져도 나머지 탭은 살린다.

    Streamlit은 스크립트를 위에서 아래로 한 번에 실행하므로, 탭 하나에서 예외가
    나면 **그 아래 탭은 아예 그려지지 않는다**(3탭 중 2번을 터뜨리면 3번이 빈
    화면인 것을 실제로 확인했다). 종합 보고가 첫 탭이라 거기서 한 번 터지면
    사이트 전체가 빈 화면이 된다 — 데이터가 갱신 중이거나 형태가 바뀌면 충분히
    생길 수 있는 일이고, 그때 다른 탭까지 못 보는 건 과한 대가다.

    st.exception()으로 남기는 이유 — verify_app.py가 `at.exception`으로 배포 전
    검증을 한다. 조용히 삼키면 터진 코드가 검증을 통과해 버린다. 화면에서는 그
    탭만 실패로 보이고 검증에서는 여전히 잡히도록, 둘 다 만족시킨다.
    """
    try:
        fn()
    except Exception as e:            # 어떤 예외든 사이트 전체를 죽이면 안 된다
        st.error(f"⚠️ **{label}** 탭을 그리는 중 오류가 났습니다. "
                 "다른 탭은 정상이니 그쪽을 먼저 보세요.\n\n"
                 "데이터가 갱신되는 중이면 잠시 뒤 새로고침으로 풀립니다. "
                 "계속되면 아래 내용을 그대로 전달해 주세요.")
        st.exception(e)


# 탭 순서 = 화면 순서. 라벨과 함수를 한 줄에 두어 어긋나지 않게 한다.
TABS = [
    ("🧭 종합 보고", "tab_overview"),
    ("📸 오늘 입력", "tab_input"),
    ("📊 현황", "tab_dashboard"),
    ("📋 전환 분석", "tab_conversion"),
    ("📈 추이 그래프", "tab_trend"),
    ("🎓 강의 분석", "tab_lecture_analysis"),
    ("🔎 강의별 상세", "tab_course_detail"),
    ("📅 기간별 분석", "tab_period"),
    ("👥 고객 분석", "tab_customer"),
    ("📢 마케팅 분석", "tab_marketing"),
    ("📍 지역 분석", "tab_region"),
    ("🗓️ 웨비나 일정", "tab_webinar"),
    ("🧪 실험 일지", "tab_experiments"),
    ("📑 경영진 보고", "tab_report"),
    ("⚙️ 채팅방 설정", "tab_campaign"),
    ("🗂️ 데이터 관리", "tab_data"),
]


def main():
    if not _run_auth():
        return

    st.title("📊 황금후추 강의 분석")

    # 탭을 그리기 전에 필요한 CSV를 동시에 받아 둔다. 순서대로 받으면 왕복
    # 지연이 그대로 쌓여 첫 화면이 19초 걸렸다(재렌더는 1.4초였다).
    # 캐시가 이미 차 있으면 전부 즉시 반환이라 비용이 없다.
    warm_cache()

    _tabs = st.tabs([_label for _label, _ in TABS])
    for _slot, (_label, _fname) in zip(_tabs, TABS):
        with _slot:
            _safe_tab(globals()[_fname], _label)


# ── 탭: 고객 분석 (LTV·재구매·교차판매) ───────────────────────────

def tab_customer():
    st.header("👥 고객 분석")
    st.caption("주문 원본에서 **고객 단위**로 집계한 재구매·생애가치(LTV)·교차판매 분석입니다. "
               "개인정보는 저장하지 않고 집계 수치만 사용합니다.")

    rep = load_cust_repeat_dist()
    ltv = load_cust_ltv_dist()
    pr = load_cust_product_repeat()
    xs = load_cust_cross_sell()
    mnr = load_cust_monthly_new_repeat()
    if rep.empty and pr.empty:
        st.info("고객 집계 데이터가 없습니다.")
        return

    # ── 핵심 지표 ───────────────────────────────────────
    _tot_cust = int(rep['customers'].sum()) if not rep.empty else 0
    _repeat = int(rep[rep['bucket'] != '1회']['customers'].sum()) if not rep.empty else 0
    _repeat_rate = _repeat / _tot_cust * 100 if _tot_cust else 0
    _new_rev = int(mnr['new_revenue'].sum()) if not mnr.empty else 0
    _rep_rev = int(mnr['repeat_revenue'].sum()) if not mnr.empty else 0
    _rep_rev_share = _rep_rev / (_new_rev + _rep_rev) * 100 if (_new_rev + _rep_rev) else 0
    _hi_ltv = "—"
    if not pr.empty:
        _hi = pr.loc[pr['avg_ltv'].idxmax()]
        _hi_ltv = f"{_hi['product']} {_hi['avg_ltv']/1e4:,.0f}<small>만</small>"
    _ckpis = [
        ("👥 총 고객", f"{_tot_cust:,}<small>명</small>", "유료 구매 고객"),
        ("🔁 재구매율", f"{_repeat_rate:.1f}<small>%</small>", "2회 이상 결제"),
        ("💵 재구매 매출 비중", f"{_rep_rev_share:.0f}<small>%</small>",
         f"재구매 {_rep_rev/1e8:.1f}억 / 신규 {_new_rev/1e8:.1f}억"),
        ("💎 최고 LTV 상품", _hi_ltv, "상품군 평균 LTV"),
    ]
    _kpi_band(_ckpis)
    st.write("")

    if _rep_rev_share >= 40:
        st.success(f"💡 **재구매 매출이 전체의 {_rep_rev_share:.0f}%** — 신규 유치만큼 "
                   "**기존 고객 재구매·상위 과정 업셀**이 매출의 핵심 축입니다. "
                   "CRM·재구매 유도에 투자할 근거가 명확합니다.")

    # ── 재구매 분포 + LTV 분포 ──────────────────────────
    st.divider()
    d1, d2 = st.columns(2)
    with d1:
        _f = cust_repeat_donut(rep)
        if _f:
            st.plotly_chart(_f, key="cust_repeat")
    with d2:
        _f = cust_ltv_bar(ltv)
        if _f:
            st.plotly_chart(_f, key="cust_ltv")

    # ── 상품군별 재구매율·LTV ───────────────────────────
    st.divider()
    st.subheader("상품군별 재구매율 · 평균 LTV")
    _f = cust_product_repeat_chart(pr)
    if _f:
        st.plotly_chart(_f, key="cust_prod")
    if not pr.empty:
        _hr = pr.loc[pr['repeat_rate'].idxmax()]
        _lr = pr.loc[pr['repeat_rate'].idxmin()]
        st.info(f"💡 **{_hr['product']}**가 재구매율 **{_hr['repeat_rate']:.1f}%**로 최고 "
                "(무료→유료 전환도 높은 상품 → 충성 고객층 형성). "
                f"**{_lr['product']}**는 **{_lr['repeat_rate']:.1f}%**로 낮아 "
                "(단일 고가 상품 특성) 후속 상품 라인업이 재구매 여지를 좌우합니다.")

    # ── 교차판매 매트릭스 ───────────────────────────────
    if not xs.empty:
        st.divider()
        st.subheader("교차판매 (강의 간 이동)")
        _f = cross_sell_heatmap(xs)
        if _f:
            st.plotly_chart(_f, key="cust_cross")
        _top = xs.sort_values('rate', ascending=False).iloc[0]
        st.info(f"💡 **{_top['from']} 구매자의 {_top['rate']:.0f}%가 {_top['to']}도 구매** — "
                f"가장 강한 교차판매 경로입니다. {_top['from']} 고객에게 {_top['to']}를 "
                "우선 추천하는 CRM이 효과적입니다.")

    # ── 월별 신규 vs 재구매 매출 ────────────────────────
    if not mnr.empty:
        st.divider()
        st.subheader("월별 신규 vs 재구매 매출")
        _f = monthly_new_repeat_chart(mnr)
        if _f:
            st.plotly_chart(_f, key="cust_monthly")
        st.caption("파랑=신규 고객 첫 결제, 골드=기존 고객 재구매. 재구매 비중이 높아지는 달일수록 "
                   "고객 자산이 축적되고 있다는 신호입니다.")

    # ── 리텐션 (재구매 타이밍·잔존) ──────────────────────
    timing = load_cust_repeat_timing()
    curve = load_cust_retention_curve()
    matrix = load_cust_retention_matrix()
    if not timing.empty or not curve.empty:
        st.divider()
        st.subheader("🔁 재구매 타이밍 · 리텐션")
        st.caption("첫 구매 고객이 **언제** 다시 구매하는지 — CRM·리마케팅 시점 설계의 근거입니다.")
        rt1, rt2 = st.columns(2)
        with rt1:
            _f = repeat_timing_chart(timing)
            if _f:
                st.plotly_chart(_f, key="cust_timing")
        with rt2:
            _f = retention_curve_chart(curve)
            if _f:
                st.plotly_chart(_f, key="cust_ret_curve")
        # 타이밍 인사이트
        if not timing.empty:
            _tt = int(timing['customers'].sum())
            _within3 = int(timing[timing['bucket'].isin(['1개월', '2~3개월'])]['customers'].sum())
            if _tt:
                st.info(f"💡 재구매 고객의 **{_within3/_tt*100:.0f}%가 첫 구매 후 3개월 이내**에 다시 "
                        "구매합니다. → **첫 구매 후 1~3개월**에 상위 과정 안내·리마케팅을 집중하는 것이 "
                        "가장 효율적입니다. 이 시기를 놓치면 재구매 확률이 급감합니다.")
        # 코호트 히트맵
        if not matrix.empty:
            _f = retention_heatmap(matrix)
            if _f:
                st.plotly_chart(_f, key="cust_ret_heat")
            st.caption("가입월(세로)별로 첫 구매 후 경과월(가로)에 재구매한 비율. "
                       "진한 칸이 많은 가입월 = 충성도 높은 코호트.")

    # ── 상품군별 리텐션 (강의별 재구매 패턴 차이) ────────
    p_time = load_cust_product_timing()
    p_ret = load_cust_product_retention()
    p_nb = load_cust_product_nextbuy()
    if not p_ret.empty or not p_nb.empty:
        st.divider()
        st.subheader("📚 강의별 재구매 패턴")
        st.caption("상품군마다 재구매율·타이밍·재구매 방향이 다릅니다. 강의별로 CRM 전략을 다르게 짜야 합니다.")

        pc1, pc2 = st.columns(2)
        with pc1:
            _f = product_retention_curve_chart(p_ret)
            if _f:
                st.plotly_chart(_f, key="cust_p_curve")
        with pc2:
            _f = nextbuy_chart(p_nb)
            if _f:
                st.plotly_chart(_f, key="cust_p_nextbuy")

        # 강의 선택 → 타이밍 상세
        if not p_time.empty:
            _pp = [p for p in ['사주', '타로', '부동산', '빌딩']
                   if p in p_time['product'].unique()]
            _psel = st.selectbox("강의 선택 (재구매 타이밍 상세)", options=_pp, key="cust_p_sel")
            _pt = p_time[p_time['product'] == _psel][['bucket', 'customers']]
            _f = repeat_timing_chart(_pt)
            if _f:
                st.plotly_chart(_f, key="cust_p_timing")

        # 업셀 vs 교차판매 전략 인사이트
        if not p_nb.empty:
            _up = p_nb[p_nb['same_pct'] >= 50].sort_values('same_pct', ascending=False)
            _cr = p_nb[p_nb['diff_pct'] >= 60].sort_values('diff_pct', ascending=False)
            _msg = "💡 **강의별 CRM 전략** — "
            if not _up.empty:
                _msg += (f"**{' · '.join(_up['product'])}**는 재구매가 주로 **같은 강의 상위과정**입니다"
                         f"(예 {_up.iloc[0]['product']} 업셀 {_up.iloc[0]['same_pct']:.0f}%) → "
                         "기초→심화→전문가 **단계 업셀 안내**가 효과적. ")
            if not _cr.empty:
                _msg += (f"반면 **{' · '.join(_cr['product'])}**는 재구매의 **{_cr.iloc[0]['diff_pct']:.0f}%가 "
                         "다른 강의**로 이동 → 첫 구매자에게 **연관 강의 교차 추천**이 핵심입니다.")
            st.info(_msg)

        # ── 교차판매 경로 (무엇을 추천할지) ──────────────
        xpath = load_cust_crosssell_path()
        if not xpath.empty:
            st.markdown("**🔀 교차판매 경로 — 다음에 무엇을 추천할까**")
            st.caption("첫 구매 강의(세로)의 고객이 교차판매로 **어느 강의(가로)를 사는지** 비중입니다. "
                       "각 강의 첫 구매자에게 **가장 많이 이어지는 강의를 추천**하면 성공률이 높습니다.")
            xc1, xc2 = st.columns([1.15, 1])
            with xc1:
                _f = crosssell_path_heatmap(xpath)
                if _f:
                    st.plotly_chart(_f, key="cust_xpath")
            with xc2:
                # 강의별 1순위 추천 표
                _recs = []
                for _hp in ['사주', '타로', '부동산', '빌딩']:
                    _sub = xpath[xpath['home'] == _hp].sort_values('pct', ascending=False)
                    if not _sub.empty and _sub.iloc[0]['pct'] > 0:
                        _top = _sub.iloc[0]
                        _recs.append({'첫 구매': _hp, '추천 강의': _top['dest'],
                                      '교차 전환': f"{_top['pct']:.0f}%"})
                if _recs:
                    st.markdown("**강의별 1순위 추천**")
                    st.dataframe(pd.DataFrame(_recs), hide_index=True, width='stretch')
            # 허브 상품 인사이트 — 여러 강의의 '1순위 목적지'가 되는 강의
            _top_dest = {}
            for _hp in ['사주', '타로', '부동산', '빌딩']:
                _sub = xpath[xpath['home'] == _hp].sort_values('pct', ascending=False)
                if not _sub.empty and _sub.iloc[0]['pct'] > 0:
                    _top_dest[_hp] = _sub.iloc[0]['dest']
            if _top_dest:
                from collections import Counter
                _cnt = Counter(_top_dest.values())
                _hub, _hub_n = _cnt.most_common(1)[0]
                _sources = [h for h, d in _top_dest.items() if d == _hub]
                if _hub_n >= 2:
                    st.info(f"💡 **{_hub}가 교차판매 허브** — **{' · '.join(_sources)}** "
                            f"({_hub_n}개 강의) 첫 구매자가 다음으로 가장 많이 사는 강의가 모두 "
                            f"**{_hub}**입니다. 타 강의 첫 구매자 CRM에서 **{_hub}를 최우선 추천**하세요. "
                            f"반대로 {_hub} 첫 구매자는 여러 강의로 분산되므로 관심사 기반 추천이 필요합니다.")


# ── 탭: 기간별 분석 ───────────────────────────────────────────────

def tab_period():
    st.header("📅 기간별 분석")
    mbc = load_monthly_by_course()
    ad_m = load_ad_spend_monthly()
    if mbc.empty:
        st.info("월별×강의별 집계 데이터가 없습니다.")
        return
    st.caption("주문 원본(개인정보 제외) 기준 월별×강의별 매출·유료건·무료신청. "
               "각 강의가 **언제** 성과를 냈는지(개강 효과)를 시점축으로 봅니다.")

    _months = sorted(mbc['month'].unique())

    # ── 🔮 월별 사주 구조 (간지) × 매출 ──────────────────
    st.subheader("🔮 월별 사주 구조 (干支) · 매출")
    st.caption("각 달의 **년주·월주**를 매출과 나란히 봅니다. 월주는 절기(입춘·경칩·망종…) 기준이며, "
               "천간지지로 월별 성과의 명리학적 패턴(오행·십신 흐름)을 함께 해석할 수 있습니다.")
    st.markdown(ganji.element_legend_html(), unsafe_allow_html=True)
    st.caption("⚠️ **월주는 달력 1일이 아니라 절기에 바뀝니다.** 예를 들어 丙申月은 "
               "8월 1일이 아니라 **8월 7일 22시 입추**부터입니다. 아래 '절입' 열이 "
               "각 월주가 실제로 시작되는 시점이며, 오행 집계도 이 기준으로 계산됩니다.")
    _mrev = mbc.groupby('month', as_index=False)['paid_revenue'].sum().sort_values('month')
    _gj = _mrev.tail(18).iloc[::-1]
    _mx_rev = float(_mrev['paid_revenue'].max()) or 1
    _rows = ""
    for _, r in _gj.iterrows():
        _y, _m = ganji._parse_ym(r['month'])
        _bar = int(r['paid_revenue'] / _mx_rev * 100)
        _rows += (
            f'<tr><td style="white-space:nowrap">{ganji.ym_korean(_y, _m)}</td>'
            f'<td style="font-size:16px;letter-spacing:1px">'
            f'{ganji.colorize(ganji.year_ganji(_y, _m))}</td>'
            f'<td style="font-size:16px;letter-spacing:1px">'
            f'{ganji.colorize(ganji.month_ganji(_y, _m))}</td>'
            f'<td style="opacity:.7;white-space:nowrap">{ganji.saju_kor(_y, _m)}</td>'
            f'<td style="opacity:.6;white-space:nowrap;font-size:12px">'
            f'{ganji.jeolgi_label(_y, _m)}</td>'
            f'<td style="text-align:right;white-space:nowrap">'
            f'{r["paid_revenue"]/1e8:,.2f}억</td>'
            f'<td style="width:38%"><div style="background:rgba(127,127,127,.18);'
            f'border-radius:3px;height:9px"><div style="width:{_bar}%;height:9px;'
            f'background:#C8901A;border-radius:3px"></div></div></td></tr>')
    st.markdown(
        '<table class="gp-dtbl" style="width:100%;border-collapse:collapse;font-size:13px">'
        '<thead><tr style="text-align:left"><th>연월</th><th>년주</th><th>월주</th>'
        '<th>독음</th><th>절입(월주 시작)</th>'
        '<th style="text-align:right">매출</th><th></th></tr></thead>'
        f'<tbody>{_rows}</tbody></table>', unsafe_allow_html=True)
    # 최고 매출 달의 간지
    _top = _mrev.loc[_mrev['paid_revenue'].idxmax()]
    _ty, _tm = ganji._parse_ym(_top['month'])
    st.info(f"💡 최고 매출 달은 **{ganji.ym_label(_top['month'], with_ganji=False)} "
            f"({ganji.saju_han(_ty, _tm)} · {ganji.saju_kor(_ty, _tm)})**로 "
            f"**{_top['paid_revenue']/1e8:.2f}억**입니다. "
            "아래 모든 월별 그래프의 가로축에도 연월과 간지가 함께 표시됩니다.")
    # ── 🌳 오행별 시기 분석 ──────────────────────────────
    _oh = load_ohaeng_period()
    if not _oh.empty:
        st.divider()
        st.subheader("🌳 오행(五行) 시기별 모객 · 전환")
        st.caption("월주의 **천간·지지가 속한 오행**으로 시기를 나눠 모객과 전환을 비교합니다. "
                   "(목=갑·을/인·묘, 화=병·정/사·오, 토=무·기/진·술·축·미, "
                   "금=경·신/신·유, 수=임·계/해·자) "
                   "**절기 기준 명리월**로 주문을 다시 묶었습니다 — 양력 1일이 아니라 "
                   "입춘·경칩 등 절입일에 달이 바뀝니다.")
        st.markdown(ganji.element_legend_html(), unsafe_allow_html=True)

        # 강의별 오행 분석 — 상품군 선택
        _oprods = ['전체'] + [p for p in ['사주', '타로', '부동산', '빌딩']
                              if p in set(_oh['product'])]
        _osel = st.radio("강의 선택", _oprods, horizontal=True, key="oh_prod")
        _oh_all = _oh
        _oh = _oh[_oh['product'] == _osel]
        if _oh.empty:
            _oh = _oh_all[_oh_all['product'] == '전체']
            _osel = '전체'
        st.caption(f"**{_osel}** 기준 — 강의마다 잘 모이는 시기와 잘 팔리는 시기가 다릅니다.")

        _ok1, _ok2 = st.columns(2)
        with _ok1:
            _f1 = ohaeng_chart(_oh, 'stem')
            if _f1:
                st.plotly_chart(_f1, key="oh_stem")
        with _ok2:
            _f2 = ohaeng_chart(_oh, 'branch')
            if _f2:
                st.plotly_chart(_f2, key="oh_branch")

        _ft = ohaeng_timeline_chart(_oh)
        if _ft:
            st.plotly_chart(_ft, key="oh_timeline")

        # 오행별 요약표 + 해석
        _rows = ""
        _tot_m = len(_oh)
        for _kind, _col in [("천간", "stem_element"), ("지지", "branch_element")]:
            _g = _oh.groupby(_col).agg(n=('saju_month', 'size'),
                                       free=('free_signups', 'sum'),
                                       paid=('paid_orders', 'sum'),
                                       rev=('revenue', 'sum'))
            for _el in ['목', '화', '토', '금', '수']:
                if _el not in _g.index:
                    continue
                _r = _g.loc[_el]
                _af = _r['free'] / _r['n']
                _cv = _r['paid'] / _r['free'] * 100 if _r['free'] else 0
                _rows += (
                    f'<tr><td>{_kind}</td>'
                    f'<td><span style="color:{ganji.ELEMENT_COLORS[_el]};font-weight:700">'
                    f'{ganji.ELEMENT_HANJA[_el]} {_el}</span></td>'
                    f'<td style="text-align:right">{int(_r["n"])}</td>'
                    f'<td style="text-align:right">{int(_r["free"]):,}</td>'
                    f'<td style="text-align:right">{_af:,.0f}</td>'
                    f'<td style="text-align:right">{int(_r["paid"]):,}</td>'
                    f'<td style="text-align:right">{_cv:.2f}%</td>'
                    f'<td style="text-align:right">{_r["rev"]/1e8:.2f}억</td></tr>')
        st.markdown(
            '<table class="gp-dtbl" style="width:100%;border-collapse:collapse;font-size:13px">'
            '<thead><tr style="text-align:left"><th>구분</th><th>오행</th>'
            '<th style="text-align:right">개월</th><th style="text-align:right">모객</th>'
            '<th style="text-align:right">월평균</th><th style="text-align:right">유료</th>'
            '<th style="text-align:right">전환율</th><th style="text-align:right">매출</th>'
            '</tr></thead>'
            f'<tbody>{_rows}</tbody></table>', unsafe_allow_html=True)

        # 자동 해석 (월평균 기준 — 오행별 개월 수가 다르므로)
        _sg = _oh.groupby('stem_element').agg(n=('saju_month', 'size'),
                                              free=('free_signups', 'sum'),
                                              paid=('paid_orders', 'sum'))
        _sg['avg'] = _sg['free'] / _sg['n']
        _sg['cv'] = (_sg['paid'] / _sg['free'] * 100).where(_sg['free'] > 0, 0)
        _bg = _oh.groupby('branch_element').agg(n=('saju_month', 'size'),
                                                free=('free_signups', 'sum'),
                                                paid=('paid_orders', 'sum'))
        _bg['avg'] = _bg['free'] / _bg['n']
        _bg['cv'] = (_bg['paid'] / _bg['free'] * 100).where(_bg['free'] > 0, 0)
        _s_top, _b_top = _sg['avg'].idxmax(), _bg['avg'].idxmax()
        _s_cv, _b_cv = _sg['cv'].idxmax(), _bg['cv'].idxmax()
        st.info(
            f"💡 **오행별 패턴** — 모객이 가장 많았던 시기는 천간 **{_s_top}"
            f"({ganji.ELEMENT_HANJA[_s_top]})월 평균 {_sg.loc[_s_top,'avg']:,.0f}명**, "
            f"지지 **{_b_top}({ganji.ELEMENT_HANJA[_b_top]})월 평균 "
            f"{_bg.loc[_b_top,'avg']:,.0f}명**입니다. "
            f"전환율이 가장 높았던 시기는 천간 **{_s_cv}({_sg.loc[_s_cv,'cv']:.2f}%)**, "
            f"지지 **{_b_cv}({_bg.loc[_b_cv,'cv']:.2f}%)** — "
            "**많이 모으는 시기와 잘 파는 시기가 다를 수 있으니** 모객은 전자에, "
            "전환 캠페인·마감은 후자에 무게를 두는 식으로 활용할 수 있습니다.")
        st.caption(f"⚠️ 해석 주의 — 전체 {_tot_m}개 명리월(오행당 2~8개월)로 표본이 작고, "
                   "강의 개강 일정·광고비 집행이 시기와 겹쳐 **오행 자체의 효과와 "
                   "사업 일정 효과가 섞여 있습니다.** 인과가 아닌 **패턴 참고용**으로 보시고, "
                   "데이터가 쌓이면 매월 자동으로 정밀해집니다. "
                   "집계 기준: 4개 상품군(전자책·달력 등 기타 제외).")

    st.divider()

    # ── 히트맵 ───────────────────────────────────────────
    st.subheader("월별 × 강의별 매출 히트맵")
    fig_h = monthly_course_heatmap(mbc)
    if fig_h:
        st.plotly_chart(fig_h, key="prd_heat")
    st.caption("색이 진한 칸 = 그 달 그 강의 매출이 큼. 강의별 개강월에 매출이 집중되는 패턴을 확인하세요.")

    # ── 월별 매출 구성 + 광고비 ──────────────────────────
    st.divider()
    st.subheader("월별 매출 구성 · 광고비 추이")
    fig_s = monthly_course_stack(mbc, ad_m if not ad_m.empty else None)
    if fig_s:
        st.plotly_chart(fig_s, key="prd_stack")

    # ── 특정 월 드릴다운 ─────────────────────────────────
    st.divider()
    st.subheader("월 선택 상세")
    _msel = st.selectbox("월 선택", options=_months[::-1], key="prd_month",
                         format_func=lambda m: ganji.ym_label(m))
    _cur = mbc[mbc['month'] == _msel]
    _prev_month = _months[_months.index(_msel) - 1] if _months.index(_msel) > 0 else None
    _prev = mbc[mbc['month'] == _prev_month] if _prev_month else pd.DataFrame()

    _tot_rev = int(_cur['paid_revenue'].sum())
    _tot_ord = int(_cur['paid_orders'].sum())
    _tot_free = int(_cur['free_signups'].sum())
    _prev_rev = int(_prev['paid_revenue'].sum()) if not _prev.empty else 0
    mm1, mm2, mm3, mm4 = st.columns(4)
    mm1.metric(f"{ganji.ym_label(_msel, with_ganji=False)} 매출", f"{_tot_rev/1e8:,.2f}억",
               delta=(f"{(_tot_rev-_prev_rev)/1e8:+.2f}억 vs {ganji.ym_label(_prev_month, with_ganji=False)}"
                      if _prev_month else None))
    st.caption(f"🔮 사주 구조: **{ganji.saju_han(*ganji._parse_ym(_msel))}** "
               f"({ganji.saju_kor(*ganji._parse_ym(_msel))}) — 월주는 절기(입춘·망종 등) 기준")
    mm2.metric("유료 주문", f"{_tot_ord:,}건")
    mm3.metric("무료 신청", f"{_tot_free:,}명")
    mm4.metric("월 객단가", f"{_tot_rev/_tot_ord/1e4:,.0f}만" if _tot_ord else "—")

    # 그 달의 상품군 구성표
    _cd = _cur.sort_values('paid_revenue', ascending=False)
    # 0으로 나누기를 막을 때 pd.NA를 쓰면 정수 열이 object dtype으로 바뀌고,
    # 그 상태의 fillna는 pandas가 곧 동작을 바꾸겠다고 예고한 자리다(FutureWarning).
    # NaN을 쓰면 float dtype 그대로라 결과는 같고 경고도 없다 — 코드 전체 동일 적용.
    _cd_disp = pd.DataFrame({
        '상품군': _cd['product'],
        '매출': _cd['paid_revenue'].apply(lambda x: f"{x/1e8:,.2f}억" if x >= 1e7 else f"{x/1e4:,.0f}만"),
        '유료주문': _cd['paid_orders'].apply(lambda x: f"{x:,}건"),
        '무료신청': _cd['free_signups'].apply(lambda x: f"{x:,}명"),
        '객단가': (_cd['paid_revenue'] / _cd['paid_orders'].replace(0, float('nan'))).fillna(0).apply(
            lambda x: f"{x/1e4:,.0f}만"),
    })
    st.dataframe(_cd_disp, hide_index=True, width='stretch')
    if _tot_rev:
        _top = _cd.iloc[0]
        st.info(f"💡 **{ganji.ym_label(_msel, with_ganji=False)}**는 **{_top['product']}**가 매출 {_top['paid_revenue']/1e8:.2f}억으로 주도"
                f"({_top['paid_revenue']/_tot_rev*100:.0f}%). 개강·프로모션 시점과 대조해 보세요.")

    # ── 다음 기간 전망 (런레이트) ────────────────────────
    perf = load_monthly_performance()
    if not perf.empty and len(perf) >= 4:
        st.divider()
        st.subheader("📈 다음 기간 전망 (런레이트)")
        st.caption("강의 사업은 **개강 시점에 매출이 몰려** 월별 편차가 큽니다. 특정 월을 콕 집어 "
                   "예측하기보다 **최근 3개월 평균(런레이트)** 과 **최근 변동폭**으로 전망합니다. "
                   "당월과 **주문 명단이 중간에 끊긴 달(부분월)** 은 계산에서 제외합니다.")
        _p = perf.sort_values('month')
        # 런레이트(부분월·당월 제외 최근 3개월 평균).
        # 주문 명단이 달 중간에 끊기면 그 달은 실적이 아니라 '덜 담긴 달'이다.
        _complete = complete_months(_p)
        # 차트도 같은 기준으로 그린다 — KPI와 차트가 다른 달을 쓰면 숫자가 어긋난다.
        _pm = _complete['month'].tolist()
        _free = _complete['free_signups'].tolist()
        _rev = _complete['revenue'].tolist()
        _part = _p[~_p['month'].isin(_pm)]
        if not _part.empty:
            _pr = _part.iloc[-1]
            _ao = order_asof()
            st.caption(f"↳ 제외된 달: **{ganji.ym_label(_pr['month'], with_ganji=False)}** "
                       f"(매출 {_pr['revenue']/1e8:.2f}억·유료 {int(_pr['paid_orders'])}건) — "
                       + (f"주문 명단이 **{_ao}까지**만 담겨 있어 덜 채워진 값입니다. "
                          if _ao else "아직 집계 중인 달입니다. ")
                       + "실적 하락으로 읽으면 안 됩니다.")
        _rr_free = _complete['free_signups'].tail(3).mean() if len(_complete) >= 3 else 0
        _rr_rev = _complete['revenue'].tail(3).mean() if len(_complete) >= 3 else 0
        _kpi_band([
            ("🆓 무료 모객 런레이트", f"{_rr_free:,.0f}<small>명/월</small>", "최근 3개월 평균"),
            ("💰 매출 런레이트", f"{_rr_rev/1e8:,.2f}<small>억/월</small>", "완결된 3개월"),
            ("📅 연 환산 페이스", f"{_rr_rev*12/1e8:,.0f}<small>억/년</small>", "개강 일정에 따라 변동"),
        ])
        st.write("")

        fc1, fc2 = st.columns(2)
        with fc1:
            # exclude_last=False: 이미 완결된 달만 넘겼으므로 또 자르면 안 된다
            _ff = runrate_forecast_chart(_pm, _free, '무료 모객', unit='명',
                                         color='#7C9CBF', periods=2,
                                         exclude_last=False)
            if _ff:
                st.plotly_chart(_ff, key="prd_fc_free")
        with fc2:
            _fr = runrate_forecast_chart(_pm, _rev, '매출', color='#26A69A',
                                         periods=2, as_eok=True,
                                         exclude_last=False)
            if _fr:
                st.plotly_chart(_fr, key="prd_fc_rev")
        st.warning("⚠️ 전망은 **최근 추세 기준 참고치**입니다. 개강·프로모션이 있는 달은 크게 상회하고, "
                   "없는 달은 하회합니다. 확정 예측이 아니라 예산·목표 설정의 기준선으로 활용하세요.")

        # ── 🔍 전망 정확도 (지난 예측이 맞았나) ───────────
        # 전망만 보여주고 사후 검증을 안 하면 그 예측을 믿을지 알 수 없다.
        # 과거 각 시점에서 '직전 3개월 평균'으로 다음 달을 예측했다고 보고,
        # 실제와 대조해 평균 오차를 낸다(런레이트 로직과 동일한 방식).
        if len(_complete) >= 5:
            _bt = _complete.reset_index(drop=True)
            _rows_bt = []
            for i in range(3, len(_bt)):
                _pred_f = _bt['free_signups'].iloc[i - 3:i].mean()
                _pred_r = _bt['revenue'].iloc[i - 3:i].mean()
                _act_f = _bt['free_signups'].iloc[i]
                _act_r = _bt['revenue'].iloc[i]
                if _pred_f > 0 and _pred_r > 0:
                    _rows_bt.append({
                        'month': _bt['month'].iloc[i],
                        'pred_free': _pred_f, 'act_free': _act_f,
                        'err_free': (_act_f - _pred_f) / _pred_f * 100,
                        'pred_rev': _pred_r, 'act_rev': _act_r,
                        'err_rev': (_act_r - _pred_r) / _pred_r * 100,
                    })
            if len(_rows_bt) >= 3:
                _bd = pd.DataFrame(_rows_bt)
                # 사업 초기(매출 수만원대)는 분모가 작아 오차율이 폭발한다
                # (실제로 평균 ±1110%가 나왔다). 규모가 잡힌 구간만 평가하고,
                # 이상치에 휘둘리지 않도록 **중앙값**을 대표값으로 쓴다.
                _bd_all = _bd
                _bd = _bd[_bd['pred_rev'] >= 1e8]
                if len(_bd) < 3:
                    _bd = _bd_all
                _mae_f = _bd['err_free'].abs().median()
                _mae_r = _bd['err_rev'].abs().median()
                _bias_r = _bd['err_rev'].median()
                st.divider()
                st.subheader("🔍 전망 정확도 — 지난 예측은 맞았나")
                st.caption("과거 각 시점에서 위와 **똑같은 방식(직전 3개월 평균)**으로 "
                           "다음 달을 예측했다면 얼마나 맞았을지 대조했습니다. "
                           "이 오차를 알면 위 전망을 어느 정도 믿을지 판단할 수 있습니다.")
                _kpi_band([
                    ("🎯 검증 개월", f"{len(_bd)}<small>개월</small>", "초기 램프업 제외"),
                    ("🆓 모객 오차(중앙값)", f"±{_mae_f:.0f}<small>%</small>",
                     "낮을수록 예측 신뢰"),
                    ("💰 매출 오차(중앙값)", f"±{_mae_r:.0f}<small>%</small>",
                     "낮을수록 예측 신뢰"),
                    ("📐 매출 편향", f"{_bias_r:+.0f}<small>%</small>",
                     "＋면 과소예측 경향"),
                ])
                _bt_rows = "".join(
                    f'<tr><td>{ganji.ym_label(r["month"], with_ganji=False)}</td>'
                    f'<td style="text-align:right">{r["pred_rev"]/1e8:.2f}억</td>'
                    f'<td style="text-align:right">{r["act_rev"]/1e8:.2f}억</td>'
                    f'<td style="text-align:right;color:'
                    f'{"#2E9E5B" if abs(r["err_rev"])<=20 else "#E0483E"}">'
                    f'{r["err_rev"]:+.0f}%</td>'
                    f'<td style="text-align:right">{r["pred_free"]:,.0f}</td>'
                    f'<td style="text-align:right">{r["act_free"]:,.0f}</td>'
                    f'<td style="text-align:right;color:'
                    f'{"#2E9E5B" if abs(r["err_free"])<=20 else "#E0483E"}">'
                    f'{r["err_free"]:+.0f}%</td></tr>'
                    for _, r in _bd.tail(8).iloc[::-1].iterrows())
                st.markdown(
                    '<table class="gp-dtbl" style="width:100%;border-collapse:collapse;'
                    'font-size:13px"><thead><tr style="text-align:left"><th>월</th>'
                    '<th style="text-align:right">매출 예측</th>'
                    '<th style="text-align:right">실제</th>'
                    '<th style="text-align:right">오차</th>'
                    '<th style="text-align:right">모객 예측</th>'
                    '<th style="text-align:right">실제</th>'
                    '<th style="text-align:right">오차</th></tr></thead>'
                    f'<tbody>{_bt_rows}</tbody></table>', unsafe_allow_html=True)
                if _mae_r >= 40 or _mae_f >= 40:
                    _worse = "매출" if _mae_r >= _mae_f else "모객"
                    st.warning(
                        f"⚠️ **전망 오차가 큽니다 — 매출 ±{_mae_r:.0f}% · 모객 "
                        f"±{_mae_f:.0f}%(중앙값)**. 강의 사업은 개강 시점에 모객·매출이 "
                        "몰려 월 편차가 크기 때문입니다. **위 전망은 '대략의 방향'으로만 "
                        "보시고**, 실제 계획은 **개강 일정과 함께** 세우세요. "
                        f"특히 {_worse} 전망을 근거로 단정하지 마세요.")
                else:
                    st.success(
                        f"✅ 매출 전망 오차(중앙값) **±{_mae_r:.0f}%**, 모객 "
                        f"**±{_mae_f:.0f}%** — 계획 수립에 쓸 만한 수준입니다.")
                st.caption("※ 오차 = (실제−예측)÷예측. 초록은 ±20% 이내. 사업 초기(월 매출 "
                           "1억 미만)는 분모가 작아 오차율이 왜곡되므로 제외했고, "
                           "이상치 영향을 줄이려 평균이 아닌 **중앙값**을 씁니다. "
                           "개강이 없는 달은 구조적으로 매출이 낮아 오차가 큽니다.")

        # ── 🎯 목표 관리 & 달성 추적 ─────────────────────
        st.divider()
        st.subheader("🎯 목표 관리 & 달성 추적")
        st.caption("월별 매출·모객 목표를 설정하면 실적 대비 **달성률**을 자동 추적합니다. "
                   "목표는 위 런레이트를 기준선으로 참고해 설정하세요.")
        tgt = load_targets()
        # 실적 결합 (monthly_performance)
        _perf_idx = _p.set_index('month')
        _this_month = date.today().strftime('%Y-%m')

        # ── 전략 결론 기반 목표 자동 설정 ────────────────
        # 목표 관리 기능이 다 만들어져 있는데 목표가 0건이면 달성 추적·
        # 목표 지연 알림이 전부 잠들어 있게 된다. 전략 결론이 이미 계산한
        # 개선폭을 근거로 3개월치를 한 번에 세워 기능을 살린다.
        if tgt.empty and _rr_free and _rr_rev:
            _cs_t = load_course_summary()
            _cur_cv = _aov_t = 0.0
            if not _cs_t.empty and _cs_t['free'].sum() and _cs_t['students'].sum():
                _cur_cv = _cs_t['students'].sum() / _cs_t['free'].sum() * 100
                _aov_t = _cs_t['revenue'].sum() / _cs_t['students'].sum()
            _goal_cv = _cur_cv + 1.0                     # 전략 결론의 +1%p 목표
            _goal_free = int(round(_rr_free / 100) * 100)
            _goal_rev = _goal_free * (_goal_cv / 100) * _aov_t if _aov_t else _rr_rev
            _next3 = _future_months(_pm, 3)
            with st.container(border=True):
                st.markdown("**📌 아직 목표가 없습니다 — 전략 결론 기준으로 세워보세요**")
                st.caption(
                    f"모객은 최근 3개월 런레이트(**{_rr_free:,.0f}명/월**)를, "
                    f"매출은 **모객 × 목표 전환율 × 객단가**로 계산합니다. "
                    f"전환율 목표는 현재 **{_cur_cv:.2f}% → {_goal_cv:.2f}%**"
                    f"(전략 결론의 +1%p), 객단가 **{_aov_t/1e4:,.0f}만원** 기준입니다. "
                    "→ 근거가 분명해 대표님께 설명하기 쉽습니다.")
                st.markdown(
                    f"<div style='font-size:13px'>대상: <b>"
                    + " · ".join(ganji.ym_label(m, with_ganji=False) for m in _next3)
                    + f"</b><br>월 목표: 모객 <b>{_goal_free:,}명</b> · "
                      f"매출 <b>{_goal_rev/1e8:.2f}억</b></div>",
                    unsafe_allow_html=True)
                if st.button("이 목표로 3개월 자동 설정", type="primary", key="tgt_auto"):
                    for _m in _next3:
                        save_target(_m, int(_goal_rev), int(_goal_free),
                                    memo=f"전략 결론 기반 자동 설정(전환율 {_goal_cv:.2f}% 목표)")
                    st.success(f"{len(_next3)}개월 목표를 설정했습니다. "
                               "이제 달성률 추적과 목표 지연 알림이 작동합니다.")
                    st.rerun()

        # 목표 설정 폼 (런레이트 제안값 프리필)
        with st.expander("✏️ 월별 목표 설정 / 수정", expanded=tgt.empty):
            _sugg_rev = int(round(_rr_rev / 1e8, 1) * 10) / 10 if _rr_rev else 5.0
            _sugg_free = int(round(_rr_free / 100) * 100) if _rr_free else 3000
            with st.form("target_form"):
                tc1, tc2, tc3 = st.columns(3)
                with tc1:
                    _fm = st.selectbox("월", options=_pm[::-1] + _future_months(_pm, 3),
                                       key="tgt_month")
                with tc2:
                    _rev_t = st.number_input("매출 목표(억원)", min_value=0.0, step=0.5,
                                             value=float(_sugg_rev),
                                             help=f"런레이트 참고: {_rr_rev/1e8:.1f}억/월")
                with tc3:
                    _free_t = st.number_input("무료 모객 목표(명)", min_value=0, step=500,
                                              value=int(_sugg_free),
                                              help=f"런레이트 참고: {_rr_free:,.0f}명/월")
                if st.form_submit_button("목표 저장", type="primary", width='stretch'):
                    save_target(_fm, int(_rev_t * 1e8), int(_free_t))
                    st.success(f"{ganji.ym_label(_fm, with_ganji=False)} 목표 저장: 매출 {_rev_t}억 · 모객 {int(_free_t):,}명")
                    st.rerun()

        if not tgt.empty:
            # 이번 달(또는 최근 목표월) 달성 현황 카드
            _rev_rows, _free_rows = [], []
            for _, tr in tgt.iterrows():
                _mn = str(tr['month'])
                _act_rev = int(_perf_idx.loc[_mn, 'revenue']) if _mn in _perf_idx.index else 0
                _act_free = int(_perf_idx.loc[_mn, 'free_signups']) if _mn in _perf_idx.index else 0
                _rev_rows.append({'month': _mn, 'actual': _act_rev, 'target': int(tr['revenue_target'])})
                _free_rows.append({'month': _mn, 'actual': _act_free, 'target': int(tr['signup_target'])})
            _rev_df = pd.DataFrame(_rev_rows)
            _free_df = pd.DataFrame(_free_rows)

            # 이번 달 진행률 (있으면)
            _tm = tgt[tgt['month'].astype(str) == _this_month]
            if not _tm.empty:
                _t = _tm.iloc[0]
                _ar = int(_perf_idx.loc[_this_month, 'revenue']) if _this_month in _perf_idx.index else 0
                _af = int(_perf_idx.loc[_this_month, 'free_signups']) if _this_month in _perf_idx.index else 0
                st.markdown(f"**📌 이번 달({ganji.ym_label(_this_month, with_ganji=False)}) 진행** — 집계 진행 중")
                pc1, pc2 = st.columns(2)
                with pc1:
                    _rr = _ar / int(_t['revenue_target']) if int(_t['revenue_target']) else 0
                    st.metric("매출", f"{_ar/1e8:.2f}억 / {int(_t['revenue_target'])/1e8:.1f}억",
                              delta=f"달성률 {_rr*100:.0f}%", delta_color="off")
                    st.progress(min(_rr, 1.0))
                with pc2:
                    _fr2 = _af / int(_t['signup_target']) if int(_t['signup_target']) else 0
                    st.metric("무료 모객", f"{_af:,} / {int(_t['signup_target']):,}명",
                              delta=f"달성률 {_fr2*100:.0f}%", delta_color="off")
                    st.progress(min(_fr2, 1.0))

            # 목표 대비 실적 차트 (완료 월)
            gg1, gg2 = st.columns(2)
            with gg1:
                _f = target_vs_actual_chart(_rev_df, '매출', as_eok=True)
                if _f:
                    st.plotly_chart(_f, key="tgt_rev")
            with gg2:
                _f = target_vs_actual_chart(_free_df, '무료 모객')
                if _f:
                    st.plotly_chart(_f, key="tgt_free")
            # 달성 요약
            _done = _rev_df[(_rev_df['month'] < _this_month) & (_rev_df['target'] > 0)]
            if not _done.empty:
                _hit = int((_done['actual'] >= _done['target']).sum())
                st.info(f"💡 목표 설정된 완료 월 **{len(_done)}개월 중 {_hit}개월 달성**. "
                        "미달 월은 개강 일정·광고 집행과 대조해 원인을 진단하세요.")
        else:
            st.info("아직 설정된 목표가 없습니다. 위 폼에서 월별 목표를 입력하면 달성 추적이 시작됩니다.")


def _future_months(months, n):
    """마지막 월 이후 n개월 라벨 생성 (목표 선입력용)."""
    if not months:
        return []
    last = max(months)
    y, mo = int(last[:4]), int(last[5:7])
    out = []
    for _ in range(n):
        mo += 1
        if mo > 12:
            mo = 1
            y += 1
        out.append(f"{y:04d}-{mo:02d}")
    return out


# ── 탭: 강의별 상세 (드릴다운) ────────────────────────────────────

def tab_course_detail():
    st.header("🔎 강의별 상세")
    st.caption("상품군을 선택하면 그 강의의 **모객·매출·유료 단계 전환·광고 효율·지역**을 "
               "한 화면에 모아 정밀 진단합니다.")

    cohort_rev = load_cohort_revenue()
    camp = load_campaign_adspend()
    stage = load_cohort_stage()
    mbc = load_monthly_by_course()
    cs = load_course_summary()
    if cohort_rev.empty and cs.empty:
        st.info("강의 데이터가 없습니다.")
        return

    _prods = [p for p in ['사주', '타로', '부동산', '빌딩']
              if p in cohort_rev['product'].unique()] or ['사주', '타로', '부동산', '빌딩']
    prod = st.selectbox("강의(상품군) 선택 — 바꾸면 아래 매출·단계·광고효율·월별매출이 모두 해당 강의로 갱신됩니다",
                        options=_prods, key="drill_prod")

    # ── 상단 요약 KPI ────────────────────────────────────
    _cr = cohort_rev[cohort_rev['product'] == prod]
    _csum = cs[cs['product'] == prod]
    if not _csum.empty:
        _r = _csum.iloc[0]
        _st_n = int(_r['students'])
        _cv = _st_n / int(_r['free']) * 100 if int(_r['free']) else 0
        _aov = f"{int(_r['revenue'])/_st_n/1e4:,.0f}<small>만</small>" if _st_n else "—"
        _kpi_band([
            (f"💰 {prod} 누적 매출", f"{int(_r['revenue'])/1e8:,.1f}<small>억</small>", "세트합계 매출"),
            ("🎓 수강생", f"{_st_n:,}<small>명</small>", "세트 수강생"),
            ("🔄 무료→유료 전환", f"{_cv:.1f}<small>%</small>", "수강생 ÷ 무료"),
            ("💎 객단가", _aov, "매출 ÷ 수강생"),
        ])
        st.write("")

    # ── 기수별 매출 추이 ─────────────────────────────────
    st.divider()
    st.subheader("기수별 매출 · 수강생")
    fig_c = cohort_revenue_chart(cohort_rev, prod)
    if fig_c:
        st.plotly_chart(fig_c, key="drill_cohort")

    # ── 유료 단계 전환 (사주/타로/부동산) ─────────────────
    _st = stage[stage['product'] == prod] if not stage.empty else pd.DataFrame()
    _stl = load_stage_timeline()
    _stl_p = _stl[_stl['product'] == prod] if not _stl.empty else pd.DataFrame()
    if not _st.empty:
        st.divider()
        st.subheader("유료 단계 전환 (기초 → 심화 → 전문가 → 창업)")
        st.caption("무료→유료 이후 **상위 과정으로의 단계 전환**. 어느 단계에서 이탈하는지 봅니다. "
                   "퍼널의 마지막 단계는 **창업·해석 합산**(주문 데이터에서 두 과정이 한 항목으로 "
                   "집계됨)이며, 아래 **타임라인에서는 창업·해석이 분리**돼 실제 개강 시점을 보여줍니다.")

        # 단계-강의 타임라인 (기수 병합·이월 가시화) — 요청 1
        if not _stl_p.empty and _stl_p['stage'].nunique() >= 2:
            _ft = stage_timeline_chart(_stl_p, prod)
            if _ft:
                st.markdown("**🗓️ 단계-강의 타임라인 — 기수는 번호대로 1:1 진행되지 않습니다**")
                st.plotly_chart(_ft, key="drill_stage_timeline")
                # 병합/이월 자동 감지: 심화 기수 수 > 기초 기수 수 등, 시점 역전
                _merge_note = []
                _b = _stl_p[_stl_p['stage'] == '기초'].copy()
                _s = _stl_p[_stl_p['stage'] == '심화'].copy()
                if not _b.empty and not _s.empty:
                    _b['n'] = _b['cohort'].str.extract(r'(\d+)').astype(float)
                    _s['n'] = _s['cohort'].str.extract(r'(\d+)').astype(float)
                    # 같은 기수번호인데 심화 시작이 기초 종료보다 한참 뒤 = 이월
                    _mg = _b.merge(_s, on='n', suffixes=('_b', '_s'))
                    _mg['gap'] = (pd.to_datetime(_mg['start_s']) - pd.to_datetime(_mg['end_b'])).dt.days
                    _lag = _mg[_mg['gap'] >= 30]
                    if not _lag.empty:
                        _ex = _lag.sort_values('gap', ascending=False).iloc[0]
                        _merge_note.append(
                            f"예: **기초 {int(_ex['n'])}기** 종료 후 **{int(_ex['gap'])}일** 뒤에 "
                            f"심화 {int(_ex['n'])}기 개강 — 별개 시점에 운영")
                st.caption("막대=각 단계 강의의 실제 개강~마감 기간. 같은 기수 번호라도 **기초와 심화가 "
                           "다른 시점에 열렸고**, 전환 시점에 기수가 병합·이월된 경우가 있어 단순 "
                           "'기초N→심화N' 진행이 아닙니다." +
                           (" " + _merge_note[0] + "." if _merge_note else ""))
                st.write("")

        sc1, sc2 = st.columns([1, 1.3])
        with sc1:
            _cohs = _st.assign(n=_st['cohort'].str.extract(r'(\d+)').astype(float)) \
                       .sort_values('n')['cohort'].tolist()[::-1]
            # 최신 기수는 아직 상위 단계가 열리지 않아 퍼널이 비는 경우가 많다.
            # → 단계가 2개 이상 채워진 가장 최근 기수를 기본 선택.
            _have = [s for s in STAGE_ORDER if s in _st.columns]
            _ok = [c for c in _cohs
                   if (_st.loc[_st['cohort'] == c, _have].fillna(0) > 0).sum(axis=1).max() >= 2]
            _idx = _cohs.index(_ok[0]) if _ok else 0
            _csel = st.selectbox("기수 선택", options=_cohs, index=_idx, key="drill_stage_coh")
            _sf = stage_funnel_chart(stage, prod, _csel, STAGE_ORDER)
            if _sf:
                st.plotly_chart(_sf, key="drill_stage_funnel")
            else:
                _filled = (_st.loc[_st['cohort'] == _csel, _have].fillna(0) > 0).sum(axis=1).max()
                st.info(f"**{_csel}**는 아직 채워진 단계가 {int(_filled)}개뿐이라 퍼널을 그릴 수 "
                        f"없습니다(진행 중인 최신 기수는 상위 단계가 미개설). "
                        + (f"→ 위 선택에서 **{_ok[0]}** 등 완료된 기수를 보세요." if _ok else ""))
        with sc2:
            _mx = cohort_stage_matrix_chart(stage, prod, STAGE_ORDER)
            if _mx:
                st.plotly_chart(_mx, key="drill_stage_matrix")
        st.caption("⚠️ 위 퍼널·매트릭스의 기수 라벨은 리포트 기준으로 정렬된 값입니다. 심화 인원이 "
                   "기초보다 많은 기수(>100% 전환)는 **여러 기초 기수가 한 심화로 병합**된 경우입니다 "
                   "— 정확한 개강 구분은 위 타임라인을 참고하세요.")
        # 단계 전환 인사이트 (평균 이탈)
        _rows = _st.copy()
        _b2s = _rows[(_rows['기초'] > 0) & (_rows['심화'] > 0)]
        _s2p = _rows[(_rows['심화'] > 0) & (_rows['전문가'] > 0)]
        _parts = []
        if not _b2s.empty:
            _parts.append(f"기초→심화 평균 **{(_b2s['심화']/_b2s['기초']).mean()*100:.0f}%**")
        if not _s2p.empty:
            _parts.append(f"심화→전문가 평균 **{(_s2p['전문가']/_s2p['심화']).mean()*100:.0f}%**")
        if _parts:
            st.info("💡 " + " · ".join(_parts) +
                    ". 심화→전문가 전환이 급락하는 구간이 업셀 개선 포인트입니다.")
    elif prod == '빌딩':
        st.divider()
        st.caption("ℹ️ 빌딩은 단일 트랙이라 단계 전환(기초→심화→전문가)이 제공되지 않습니다.")

    # ── 광고 효율 추이 + 변동 원인 (기수/시점) ───────────
    _ca = camp[camp['product'] == prod] if not camp.empty else pd.DataFrame()
    if not _ca.empty:
        st.divider()
        st.subheader(f"광고 효율 (기수별) — {prod}")
        fig_ad = cohort_ad_roi_chart(camp, prod)
        if fig_ad:
            st.plotly_chart(fig_ad, key="drill_ad")

        # 광고 효율 변동 원인 분석 — 요청 3
        _diag = ad_efficiency_diagnosis(camp, prod)
        if _diag:
            _dd = _diag['d']
            _corr = _diag['corr']
            _best, _worst, _tsp = _diag['best'], _diag['worst'], _diag['top_spend']
            _first, _last = _diag['first'], _diag['last']
            st.markdown("**🔍 왜 이렇게 나왔나 — 광고 효율 변동 원인**")
            _msg = (f"**{prod}** 광고 ROAS는 **{_best['cohort']} {_best['roas']:.0f}배**(최고)에서 "
                    f"**{_worst['cohort']} {_worst['roas']:.1f}배**(최저)까지 움직였습니다. ")
            if not pd.isna(_corr) and _corr <= -0.4:
                _msg += (f"광고비와 ROAS의 상관계수가 **{_corr:+.2f}**(강한 음의 관계) — "
                         f"**광고비를 키울수록 효율이 떨어지는 수확체감**이 뚜렷합니다. "
                         f"광고비 최다 투입 **{_tsp['cohort']}({_tsp['ad']/1e8:.2f}억)**의 ROAS가 "
                         f"**{_tsp['rev']/_tsp['ad']:.1f}배**로 낮은 게 대표적입니다. ")
                # 회복 구간 감지
                if _last['roas'] > _worst['roas'] * 1.5 and _last['ad'] < _tsp['ad']:
                    _msg += (f"최근 **{_last['cohort']}**은 광고비를 **{_last['ad']/1e8:.2f}억**으로 "
                             f"줄이자 ROAS가 **{_last['roas']:.1f}배**로 회복됐습니다. → **적정 예산 구간**을 "
                             "찾아 과다 집행을 피하는 것이 핵심입니다.")
                else:
                    _msg += "→ 무리한 예산 확대보다 **효율이 유지되는 적정 규모**로 운영하세요."
            elif not pd.isna(_corr) and _corr >= 0.4:
                _msg += (f"광고비와 ROAS가 함께 움직이며(상관 {_corr:+.2f}), 초기 {_first['cohort']}가 "
                         f"가장 효율적이었고 시간이 지나며 완만히 하락하는 **시장 성숙/피로** 양상입니다. "
                         "새 후킹·타깃으로 초기 효율을 재현할 여지를 검토하세요.")
            else:
                _msg += (f"초기 **{_first['cohort']}({_first['roas']:.0f}배)**가 소규모·고효율이었고, "
                         "규모 확대 시 효율이 낮아지는 일반적 패턴입니다.")
            st.info("💡 " + _msg)
            st.caption("※ 여기 ROAS는 라이브 첫전환 매출÷광고비(기수별). 상관계수는 광고비와 ROAS의 "
                       "선형 관계(−1~+1), 음수일수록 '광고비↑→효율↓' 경향.")

    # ── 월별 매출 시계열 (해당 강의) ─────────────────────
    _mb = mbc[mbc['product'] == prod] if not mbc.empty else pd.DataFrame()
    if not _mb.empty:
        st.divider()
        st.subheader(f"월별 매출 추이 — {prod}")
        _mb2 = _mb.sort_values('month')
        import plotly.graph_objects as _go
        _pcolor = {'사주': '#7C4DBC', '타로': '#9C6ADE',
                   '부동산': '#2E8B7A', '빌딩': '#1E6FD9'}.get(prod, '#5B8FF9')
        _figm = _go.Figure(_go.Bar(
            x=_mb2['month'], y=_mb2['paid_revenue'],
            marker_color=_pcolor,
            hovertemplate='%{x}<br>%{y:,.0f}원<extra></extra>'))
        _figm.update_layout(title=f'{prod} 월별 매출 (주문 기준)', height=320,
                            margin=dict(t=50, b=50, l=20, r=20),
                            xaxis=dict(tickangle=-45), yaxis=dict(title='매출(원)'))
        st.plotly_chart(_figm, key="drill_monthly")


# ── 탭: 종합 보고 (전략 대시보드) ─────────────────────────────────

def _product_master_table():
    """상품군 통합 요약: 매출·유료·무료·전환율·객단가 + 광고비·광고ROAS."""
    cs = load_course_summary()
    camp = load_campaign_adspend()
    if cs.empty:
        return pd.DataFrame()
    m = cs.copy()
    # 전환율·객단가는 매출과 동일 기준인 '세트 수강생(students)'을 분모로 사용(기준 정합)
    m['전환율'] = (m['students'] / m['free'].replace(0, float('nan')) * 100).round(1).fillna(0)
    m['객단가'] = (m['revenue'] / m['students'].replace(0, float('nan'))).fillna(0).astype(int)
    if not camp.empty:
        ad = camp.groupby('product').agg(ad=('ad_spend', 'sum'),
                                         lrev=('live_revenue', 'sum')).reset_index()
        ad['광고ROAS'] = (ad['lrev'] / ad['ad'].replace(0, float('nan'))).round(1).fillna(0)
        m = m.merge(ad[['product', 'ad', '광고ROAS']], on='product', how='left')
    else:
        m['ad'] = 0
        m['광고ROAS'] = 0
    m['ad'] = m['ad'].fillna(0)
    m['광고ROAS'] = m['광고ROAS'].fillna(0)
    return m.sort_values('revenue', ascending=False)


def tab_overview():
    st.header("🧭 종합 보고 — 전략 대시보드")
    # 절기 기준 명리 월 (달력 월과 매월 초 며칠 어긋난다)
    _ty, _tm = ganji.saju_month_of(date.today()) or (date.today().year, date.today().month)
    st.caption("모객 · 매출 · 전환 · 광고 ROI · 지역을 한 화면에 종합한 경영 전략 요약입니다. "
               "모든 수치는 강의 집계·광고비·지역 실데이터에서 자동 계산됩니다.")
    st.markdown(
        '<div class="gp-card" style="padding:10px 14px;margin:2px 0 10px">'
        f'<span style="font-size:13px;opacity:.75">🔮 지금은 '
        f'{ganji.ym_korean(_ty, _tm)} (명리 기준) · '
        f'{ganji.jeolgi_label(_ty, _tm)}부터</span><br>'
        f'<span style="font-size:20px;letter-spacing:2px">'
        f'{ganji.colorize(ganji.year_ganji(_ty, _tm))}<span style="opacity:.45;'
        f'font-size:13px">年</span> '
        f'{ganji.colorize(ganji.month_ganji(_ty, _tm))}<span style="opacity:.45;'
        f'font-size:13px">月</span></span>'
        f'<span style="opacity:.6;font-size:12px"> · {ganji.saju_kor(_ty, _tm)}</span><br>'
        '<span style="font-size:11px;opacity:.6">월주는 달력 1일이 아니라 <b>절기</b>에 '
        '바뀝니다 · 모든 시간축 그래프와 집계가 절기 기준입니다 · '
        '월별 간지 전체는 📅 기간별 분석 탭 상단</span></div>',
        unsafe_allow_html=True)
    st.markdown(ganji.element_legend_html(), unsafe_allow_html=True)

    # ── 🚨 이상 탐지 알림 (능동 경고) ───────────────────
    _alerts = _generate_alerts()
    _crit = [a for a in _alerts if a['sev'] == 'critical']
    _warn = [a for a in _alerts if a['sev'] == 'warning']
    _info = [a for a in _alerts if a['sev'] == 'info']
    with st.container(border=True):
        if _crit or _warn:
            st.markdown(f"#### 🚨 알림 — 위험 {len(_crit)} · 주의 {len(_warn)}")
        else:
            st.markdown("#### 🚨 알림")
        if not _alerts:
            st.success("🟢 특이 알림 없음 — 주요 지표(총원·매출·광고·목표)가 정상 범위입니다.")
        else:
            for a in _crit:
                st.error(f"🔴 **{a['title']}** — {a['msg']}")
            for a in _warn:
                st.warning(f"🟡 **{a['title']}** — {a['msg']}")
            for a in _info:
                st.info(f"🔵 **{a['title']}** — {a['msg']}")

            # ── 슬랙 전송 (설정 시) ──────────────────────
            _slack = ""
            try:
                _slack = st.secrets.get("slack_webhook_url", "")
            except Exception:
                _slack = ""
            if _slack:
                if st.button("🔔 이 알림 슬랙으로 전송", key="alert_slack",
                             help="현재 알림을 팀 슬랙 채널로 보냅니다"):
                    if send_slack_alert(_slack, slack_message(_alerts)):
                        st.success("슬랙으로 전송했습니다.")
                    else:
                        st.error("슬랙 전송에 실패했습니다 — 웹훅 주소를 확인하세요.")
                st.caption("🔔 🔴 위험 알림은 자동 갱신(하루 3회)이 하루 한 번 "
                           "슬랙으로 자동 발송합니다 — 사이트를 열지 않아도 전달됩니다.")
            else:
                st.caption("🔔 지금은 🔴 위험 알림이 **갱신용 맥의 알림 센터로** 갑니다 "
                           "(하루 3회 자동). 팀 슬랙으로 받으려면 `slack_webhook_url`을 "
                           "두 곳에 넣으세요 — **Streamlit Cloud → Settings → Secrets**"
                           "(이 화면의 전송 버튼용)와 **갱신용 맥의 "
                           "`.streamlit/secrets.toml`**(자동 발송용).")

    cs = load_course_summary()
    if cs.empty:
        st.info("강의 집계 데이터가 아직 없습니다. 데이터가 이관되면 종합 보고가 표시됩니다.")
        return

    camp = load_campaign_adspend()
    region = load_region_signups()
    rc = load_region_cohort()
    perf = load_monthly_performance()
    ad_m = load_ad_spend_monthly()

    # ── 핵심 지표 ───────────────────────────────────────
    tot_rev = int(cs['revenue'].sum())
    tot_free = int(cs['free'].sum())
    tot_students = int(cs['students'].sum())   # 세트 수강생(매출과 동일 기준)
    conv = tot_students / tot_free * 100 if tot_free else 0

    roas_txt, _roas_help = "—", "월별 광고비 입력 시 표시"
    if not perf.empty and not ad_m.empty:
        _am = set(ad_m['month'].astype(str))
        _sp = int(ad_m['spend'].sum())
        _rv = int(perf[perf['month'].astype(str).isin(_am)]['revenue'].sum())
        if _sp:
            roas_txt = f"{_rv/_sp:.1f}배"
            _roas_help = f"매출 {_rv/1e8:.1f}억 ÷ 광고비 {_sp/1e8:.1f}억 (집행 기간)"

    cap_pct = 0.0
    if not region.empty:
        _t = int(region['signups'].sum())
        _c = int(region[region['region'].isin(CAPITAL_REGIONS)]['signups'].sum())
        cap_pct = _c / _t * 100 if _t else 0

    # 광고 최고효율 상품
    _best_ad = None
    if not camp.empty:
        _g = camp.groupby('product').agg(ad=('ad_spend', 'sum'),
                                         rev=('live_revenue', 'sum')).reset_index()
        _g = _g[_g['ad'] > 0]
        if not _g.empty:
            _g['roas'] = _g['rev'] / _g['ad']
            _best_ad = _g.loc[_g['roas'].idxmax()]

    _top_rev = cs.sort_values('revenue', ascending=False).iloc[0]
    _roas_v = roas_txt.replace('배', '<small>배</small>') if roas_txt != '—' else '—'
    _ad_eff = (f"{_best_ad['product']} {_best_ad['roas']:.1f}<small>배</small>"
               if _best_ad is not None else "—")
    _kpis = [
        ("💰 누적 매출", f"{tot_rev/1e8:,.1f}<small>억원</small>", "강의 집계 세트합계"),
        ("🆓 무료 모객", f"{tot_free:,}<small>명</small>", "무료 신청(중복 포함)"),
        ("🎓 유료 수강생", f"{tot_students:,}<small>명</small>", f"결제 {int(cs['paid'].sum()):,}건"),
        ("🔄 무료→유료 전환", f"{conv:.1f}<small>%</small>", "수강생 ÷ 무료"),
        ("📈 누적 ROAS", _roas_v, "매출 ÷ 광고비"),
        ("📍 수도권 집중도", (f"{cap_pct:.0f}<small>%</small>" if cap_pct else "—"),
         ("배송지 기준 " + _asof_tag('지역 분포')).strip()),
        ("🏆 광고 최고효율", _ad_eff, "라이브 첫전환 기준"),
        ("👑 매출 1위 상품", f"{_top_rev['product']} {_top_rev['revenue']/1e8:.1f}<small>억</small>", "상품군 매출"),
    ]
    st.markdown("#### 핵심 지표")
    _kpi_band(_kpis)

    st.divider()

    # ── 전략 브리핑 (카드형) ────────────────────────────
    _brief = _strategy_briefing()
    if _brief:
        with st.container(border=True):
            st.markdown("#### 🎯 전략 브리핑 — 지금 해야 할 것")
            def _mdb(s):
                _p = s.split('**')
                return ''.join(x if i % 2 == 0 else f'<b>{x}</b>' for i, x in enumerate(_p))
            st.markdown(''.join(
                f'<div class="gp-brief"><span class="bi">{_ic}</span>'
                f'<span class="bt"><span class="tt">{_t}</span> — {_mdb(_b)}</span></div>'
                for _ic, _t, _b in _brief), unsafe_allow_html=True)

    # ── 🏁 최종 전략 결론 (근거 → 방향 → 목표) ──────────────
    _con = _strategy_conclusion()
    if _con.get('strategies') or _con.get('portfolio'):
        st.divider()
        st.markdown("### 🏁 최종 전략 결론 — 무엇을, 왜, 얼마나")
        st.caption("모든 분석(광고 ROI·전환·단계·후킹·시기·고객)을 하나로 엮은 결론입니다. "
                   "수치는 실데이터에서 자동 계산되며, 데이터가 갱신되면 결론도 함께 갱신됩니다.")

        def _b2h(s):
            _p = str(s).split('**')
            return ''.join(x if i % 2 == 0 else f'<b>{x}</b>' for i, x in enumerate(_p))

        # 1) 포트폴리오 역할
        if _con['portfolio']:
            st.markdown("#### 1. 상품 포트폴리오 — 각 강의의 역할")
            _pr = ""
            for p in _con['portfolio']:
                _ro = f"{p['roas']:.1f}배" if p['roas'] else "—"
                _sh = f"{p['adshare']:.0f}%" if p['adshare'] else "—"
                _pr += (f'<tr><td><b>{p["product"]}</b></td>'
                        f'<td style="white-space:nowrap">{p["role"]}</td>'
                        f'<td style="text-align:right">{p["rev"]/1e8:.1f}억</td>'
                        f'<td style="text-align:right">{p["cv"]:.1f}%</td>'
                        f'<td style="text-align:right">{p["aov"]/1e4:,.0f}만</td>'
                        f'<td style="text-align:right">{_ro}</td>'
                        f'<td style="text-align:right">{_sh}</td>'
                        f'<td style="opacity:.8">{p["action"]}</td></tr>')
            st.markdown(
                '<table class="gp-dtbl" style="width:100%;border-collapse:collapse;font-size:13px">'
                '<thead><tr style="text-align:left"><th>강의</th><th>역할</th>'
                '<th style="text-align:right">누적매출</th><th style="text-align:right">전환율</th>'
                '<th style="text-align:right">객단가</th><th style="text-align:right">광고ROAS</th>'
                '<th style="text-align:right">광고비중</th><th>해야 할 일</th></tr></thead>'
                f'<tbody>{_pr}</tbody></table>', unsafe_allow_html=True)
            st.caption("역할은 전환율·객단가의 중앙값 기준으로 자동 분류됩니다. "
                       "**광고 ROAS가 높은데 광고비중이 낮은 강의가 최우선 확대 대상**입니다.")

        # 2) 전략 방향
        if _con['strategies']:
            st.markdown("#### 2. 전략 방향 — 근거 · 실행 · 기대효과")
            for s in _con['strategies']:
                with st.container(border=True):
                    st.markdown(f"**전략 {s['no']}. {s['title']}**")
                    st.markdown(
                        f'<div style="font-size:13px;line-height:1.65">'
                        f'<div style="margin-bottom:6px"><span style="opacity:.6">📌 근거</span><br>'
                        f'{_b2h(s["why"])}</div>'
                        f'<div style="margin-bottom:6px"><span style="opacity:.6">🛠 실행</span><br>'
                        f'{_b2h(s["how"])}</div>'
                        f'<div style="color:#C8901A"><span style="opacity:.7">📈 기대효과</span><br>'
                        f'{_b2h(s["effect"])}</div></div>', unsafe_allow_html=True)

        # 3) 정량 목표
        if _con['targets']:
            st.markdown("#### 3. 정량 목표 — 무엇을 얼마나")
            _tr = "".join(
                f'<tr><td><b>{t["kpi"]}</b></td>'
                f'<td style="text-align:right">{t["now"]}</td>'
                f'<td style="text-align:center;opacity:.5">→</td>'
                f'<td style="text-align:right;color:#C8901A;font-weight:700">{t["goal"]}</td>'
                f'<td style="opacity:.8;font-size:12px">{_b2h(t["basis"])}</td></tr>'
                for t in _con['targets'])
            st.markdown(
                '<table class="gp-dtbl" style="width:100%;border-collapse:collapse;font-size:13px">'
                '<thead><tr style="text-align:left"><th>지표</th>'
                '<th style="text-align:right">현재</th><th></th>'
                '<th style="text-align:right">목표</th><th>근거</th></tr></thead>'
                f'<tbody>{_tr}</tbody></table>', unsafe_allow_html=True)
            st.caption("목표는 현재 실적에서 **달성 가능한 개선폭**으로 산출했습니다. "
                       "📅 기간별 분석 탭의 '목표 관리'에서 월별 목표로 등록해 추적할 수 있습니다.")

        # 4) 강의별 모객 전략 플레이북
        _pb = _course_playbook()
        if _pb:
            st.markdown("#### 4. 강의별 모객 전략 — 어떤 후킹으로 · 언제 · 얼마에")
            st.caption("강의마다 잘 먹히는 후킹·잘 모이는 시기·광고 효율·이탈 지점이 다릅니다. "
                       "각 강의를 **개별 전략으로** 운영하기 위한 실행안입니다.")
            _tabs = st.tabs([f"{b['product']}" for b in _pb])
            for _tb, b in zip(_tabs, _pb):
                with _tb:
                    p = b['product']
                    _ro = f"{b['roas']:.1f}배" if b['roas'] else "—"
                    _kpi_band([
                        ("💰 누적 매출", f"{b['rev']/1e8:,.1f}<small>억</small>",
                         f"수강생 {b['students']:,}명"),
                        ("🎣 무료 모객", f"{b['free']:,}<small>명</small>",
                         f"전환율 {b['cv']:.1f}%"),
                        ("💎 객단가", f"{b['aov']/1e4:,.0f}<small>만원</small>", "수강생 1인당"),
                        ("📈 광고 ROAS", _ro,
                         f"광고비중 {b['adshare']:.0f}%" if b['adshare'] else "광고 데이터 없음"),
                    ])

                    _lines = []
                    # 후킹 전략
                    if b['hooks']:
                        _best = b['hooks'][0]
                        _vol = max(b['hooks'], key=lambda h: h['signups'])
                        if _vol['topic'] != _best['topic']:
                            _lines.append(
                                ("🎣 후킹 전략",
                                 f"모객은 **{_vol['topic']}**({_vol['signups']:,}명 모객, "
                                 f"전환 {_vol['conv']:.1f}%)로 규모를 만들고, 전환은 "
                                 f"**{_best['topic']}**(전환 {_best['conv']:.1f}%)를 "
                                 f"마감·리마케팅에 배치하세요. "
                                 f"두 후킹의 전환율 차이가 **{_best['conv']/max(_vol['conv'],0.1):.1f}배**입니다."))
                        else:
                            _lines.append(
                                ("🎣 후킹 전략",
                                 f"**{_best['topic']}**가 모객·전환 모두 1위"
                                 f"({_best['signups']:,}명·{_best['conv']:.1f}%)입니다. "
                                 "이 문구를 광고·랜딩 기본형으로 고정하고 변주만 테스트하세요."))
                        if _best.get('self_share'):
                            _sh = _best['self_share']
                            _lines.append(
                                ("🚪 후킹 성격",
                                 f"이 강의 특강 전환의 **{_sh:.0f}%가 같은 강의 구매**입니다. "
                                 + ("특강↔상품이 직결되는 **자기완결형**이라 특강 모객을 "
                                    "늘리면 매출이 바로 따라옵니다."
                                    if _sh >= 60 else
                                    "전환의 절반 이상이 **다른 강의로 흘러가는 관문형**이라, "
                                    "자사 전환율만으로 평가하면 저평가됩니다 — 유입 후 "
                                    "교차판매 동선을 반드시 연결하세요.")))
                    # 시기 전략
                    if b['season']:
                        s = b['season']
                        if s['vol'] != s['cv']:
                            _lines.append(
                                ("🌳 시기 전략(오행)",
                                 f"**{s['vol']}({ganji.ELEMENT_HANJA.get(s['vol'],'')})월에 "
                                 f"가장 많이 모이고**(월평균 {s['vol_n']:,.0f}명), "
                                 f"**{s['cv']}({ganji.ELEMENT_HANJA.get(s['cv'],'')})월에 "
                                 f"가장 잘 팔립니다**(전환 {s['cv_v']:.1f}%). "
                                 f"→ {s['vol']}월엔 광고비를 실어 리드를 쌓고, "
                                 f"{s['cv']}월에 개강·마감을 배치하세요."))
                        else:
                            _lines.append(
                                ("🌳 시기 전략(오행)",
                                 f"**{s['vol']}({ganji.ELEMENT_HANJA.get(s['vol'],'')})월**이 "
                                 f"모객·전환 모두 강합니다(월평균 {s['vol_n']:,.0f}명·"
                                 f"전환 {s['cv_v']:.1f}%). 이 시기에 개강을 집중하세요."))
                    # 광고 전략
                    if b['roas'] and b['adshare'] is not None:
                        if b['roas'] >= 10:
                            _ad = (f"ROAS **{b['roas']:.1f}배**인데 광고비 비중이 "
                                   f"**{b['adshare']:.0f}%**뿐입니다 — **확대 최우선**. "
                                   "소액씩 늘리며 효율 유지 구간을 찾으세요.")
                        elif b['roas'] >= 5:
                            _ad = (f"ROAS **{b['roas']:.1f}배**로 건전합니다"
                                   f"(비중 {b['adshare']:.0f}%). 현 수준 유지하며 "
                                   "소재·후킹 개선으로 효율을 올리세요.")
                        else:
                            _ad = (f"ROAS **{b['roas']:.1f}배**로 낮습니다"
                                   f"(비중 {b['adshare']:.0f}%). 광고비를 늘리기 전에 "
                                   "**전환 구조부터 손봐야** 합니다.")
                        _lines.append(("💰 광고 전략", _ad))
                    # 전환 병목
                    if b['bottleneck']:
                        bo = b['bottleneck']
                        if bo['rate'] <= 0.5:
                            # 전환 0% = 이탈이 아니라 상위 과정 자체가 아직 없는 경우
                            _lines.append(
                                ("🔧 상위 과정 부재",
                                 f"**{bo['to']}** 과정 수강이 사실상 없습니다"
                                 f"({bo['from']} {bo['base']:,.0f}명 → {bo['to']} "
                                 f"{bo['base']-bo['lost']:,.0f}명). 이탈이라기보다 "
                                 f"**상위 과정이 아직 개설·판매되지 않은 상태**로 보입니다. "
                                 f"→ {bo['from']} 수료생 **{bo['base']:,.0f}명**은 이미 확보된 "
                                 "수요이므로, 상위 과정을 열면 **모객 비용 없이** 매출을 "
                                 "만들 수 있는 가장 값싼 기회입니다."))
                        else:
                            _lines.append(
                                ("🔧 전환 병목",
                                 f"**{bo['from']}→{bo['to']}** 전환이 **{bo['rate']:.1f}%**로, "
                                 f"이 구간에서 **{bo['lost']:,.0f}명**이 이탈합니다. "
                                 "모객을 늘리기 전에 이 구간을 막는 게 비용 대비 효과가 큽니다."))
                    # 교차판매
                    if b['nextbuy']:
                        nbk = b['nextbuy']
                        _txt = (f"이 강의 첫 구매자는 다음에 **{nbk['to']}**를 가장 많이 삽니다"
                                f"({nbk['n']:,}명, {nbk['pct']:.0f}%).")
                        if b.get('repeat'):
                            _txt += (f" 재구매율 **{b['repeat']['rate']:.0f}%**, 그중 "
                                     f"**{b['repeat']['diff']:.0f}%가 다른 강의**로 이동합니다.")
                        _txt += f" → {p} 수강생에게 **{nbk['to']}** 오퍼를 자동 연결하세요."
                        _lines.append(("🔁 교차판매", _txt))

                    _html = "".join(
                        f'<div style="margin-bottom:9px"><span style="opacity:.6;'
                        f'font-size:12px">{t}</span><br>'
                        f'<span style="font-size:13px;line-height:1.6">{_b2h(v)}</span></div>'
                        for t, v in _lines)
                    st.markdown(f'<div style="margin-top:6px">{_html}</div>',
                                unsafe_allow_html=True)

        if _con['caveats']:
            st.caption("⚠️ " + "  ·  ".join(_con['caveats']))

    st.divider()

    # ── 도식 4종 (2×2) ──────────────────────────────────
    st.markdown("#### 종합 도식")
    o1, o2 = st.columns(2)
    with o1:
        _fig = product_revenue_mix_chart(cs)
        if _fig:
            st.plotly_chart(_fig, key="ov_mix")
    with o2:
        if not camp.empty:
            _fig = product_ad_roi_chart(camp)
            if _fig:
                st.plotly_chart(_fig, key="ov_adroi")
    o3, o4 = st.columns(2)
    with o3:
        _fig = product_conversion_rate_chart(cs)
        if _fig:
            st.plotly_chart(_fig, key="ov_conv")
    with o4:
        if not region.empty:
            _fig = region_distribution_chart(region, capital=tuple(CAPITAL_REGIONS))
            if _fig:
                st.plotly_chart(_fig, key="ov_region")

    # 기간 하이라이트 — 월별×강의별 매출 히트맵 (최근 12개월)
    _mbc = load_monthly_by_course()
    if not _mbc.empty:
        _fh = monthly_course_heatmap(_mbc, months=12)
        if _fh:
            st.plotly_chart(_fh, key="ov_heat")
            st.caption("최근 12개월 강의별 매출 집중 시점. 상세는 **📅 기간별 분석**·**🔎 강의별 상세** 탭 참고.")

    # ── 상품군 통합 요약표 ──────────────────────────────
    st.divider()
    st.markdown("#### 상품군 통합 요약표")
    m = _product_master_table()
    if not m.empty:
        disp = pd.DataFrame({
            '상품군': m['product'],
            '누적매출': m['revenue'].apply(lambda x: f"{x/1e8:,.2f}억"),
            '수강생': m['students'].apply(lambda x: f"{x:,}명"),
            '무료모객': m['free'].apply(lambda x: f"{x:,}"),
            '전환율': m['전환율'].apply(lambda x: f"{x}%"),
            '객단가': m['객단가'].apply(lambda x: f"{x/1e4:,.0f}만"),
            '광고비': m['ad'].apply(lambda x: f"{x/1e8:,.2f}억" if x else "—"),
            '광고ROAS': m['광고ROAS'].apply(lambda x: f"{x:.1f}배" if x else "—"),
        })
        st.dataframe(disp, hide_index=True, width='stretch')
        st.caption("수강생·전환율·객단가는 **세트 수강생**(멤버십 제외, 매출과 동일 기준). "
                   "전환율=수강생÷무료신청, 객단가=매출÷수강생. "
                   "광고비·광고ROAS=통합시트 캠페인별 귀속이며, **광고ROAS의 매출은 라이브 첫전환 기준**"
                   "이라 누적매출을 광고비로 나눈 값과 다릅니다.")

    # ── 전략 결론 ───────────────────────────────────────
    st.divider()
    st.markdown("#### 📌 전략 결론")
    _pts = []
    if _best_ad is not None and not m.empty:
        _low = m.sort_values('광고ROAS')
        _low = _low[_low['광고ROAS'] > 0]
        _worst_ad = _low.iloc[0] if not _low.empty else None
        _pts.append(f"**광고 예산**: 광고 효율 1위 **{_best_ad['product']}({_best_ad['roas']:.1f}배)** 확대, "
                    + (f"효율이 낮은 **{_worst_ad['product']}({_worst_ad['광고ROAS']:.1f}배)**는 소재·타깃 개선 후 재배분."
                       if _worst_ad is not None else ""))
    _cvbest = cs.copy()
    _cvbest['cv'] = _cvbest['students'] / _cvbest['free'].replace(0, float('nan'))
    _cvbest = _cvbest.dropna(subset=['cv'])
    if not _cvbest.empty:
        _cb = _cvbest.loc[_cvbest['cv'].idxmax()]
        _pts.append(f"**모객 확대**: 전환율 최고 **{_cb['product']}({_cb['cv']*100:.1f}%)**는 무료 모객을 늘릴수록 "
                    "유료 성과 직결 — 무료 특강 물량 확대 1순위.")
    if cap_pct:
        _pts.append(f"**지역 타깃**: 수도권 집중도 **{cap_pct:.0f}%** — 광고 예산을 서울·경기·인천에 우선 배정, "
                    "부산·경남 영남권을 보조 타깃으로. "
                    f"※ 배송지 리포트 {_asof_tag('지역 분포')} — 이후 기수는 미반영.")
    _hi_aov = m.sort_values('객단가', ascending=False).iloc[0] if not m.empty else None
    if _hi_aov is not None:
        _pts.append(f"**고가 라인**: 객단가 최고 **{_hi_aov['product']}({_hi_aov['객단가']/1e4:,.0f}만원)**는 "
                    "패키지·업셀 강화로 매출 레버리지가 큼.")
    for _p in _pts:
        st.markdown(f"- {_p}")


# ── 탭 1: 오늘 입력 ───────────────────────────────────────────────

def tab_input():
    ROOMS = load_rooms()
    ROOM_NUMBERS = sorted(ROOMS.keys())
    if not ROOMS:
        st.warning("채팅방이 등록되어 있지 않습니다. ⚙️ 채팅방 설정 탭에서 먼저 채팅방을 추가해주세요.")
        return
    st.header("오늘의 인원 입력")

    input_date = st.date_input("📅 날짜", value=date.today())

    # 전일 인원 사전 로드 (OCR 검토 테이블과 입력 폼에서 공용)
    df_all = load_all()
    prev = {}
    if not df_all.empty:
        today_str = str(input_date)
        df_prev = df_all[df_all['date'].astype(str) != today_str]
        if not df_prev.empty:
            prev = df_prev.sort_values('date').groupby('room_num').last()['members'].to_dict()

    # ── OCR 업로드 (선택) ──────────────────────────────────────
    st.subheader("1단계 — 스크린샷 업로드 (선택)")
    st.caption("📌 스크린샷 없이 아래 2단계에서 직접 입력해도 됩니다. 어제 값이 기본으로 채워져 있으니 바뀐 숫자만 수정하세요.")

    # 인식 엔진은 두 갈래다.
    #   tesseract — apt 설치가 필요한데, 스트림릿 서버 이미지에 수명이 끝난
    #               데비안 11 저장소가 섞여 apt 갱신 자체가 실패한다(2026-09-08).
    #               packages.txt가 있으면 배포가 통째로 중단돼 떼어 둔 상태다.
    #   gemini    — 순수 HTTP라 남의 서버 이미지 사정과 무관하다. 그래서 주 경로.
    # 있는 쪽을 쓰고, 둘 다 없으면 업로더를 감춘다 — 올려 봐야 '인식 0건'만
    # 돌아오면 사람이 이유를 알 수 없다.
    _ocr_engine = ('tesseract' if shutil.which('tesseract')
                   else ('gemini' if st.secrets.get('gemini_api_key', '') else None))

    if _ocr_engine:
        uploaded_files = st.file_uploader(
            "이미지 파일 선택 (PNG / JPG) — 여러 장 동시 선택 가능",
            type=['png', 'jpg', 'jpeg'],
            accept_multiple_files=True,
            key='screenshot_upload',
        )
        if _ocr_engine == 'gemini':
            st.caption("🤖 제미나이 비전으로 인식합니다 — 배지 번호와 인원 수를 "
                       "구분해 읽으므로 예전 방식보다 정확합니다.")
    else:
        uploaded_files = []
        st.warning(
            "🔧 **스크린샷 자동 인식이 꺼져 있습니다.** 스트림릿 서버 이미지의 낡은 "
            "데비안 저장소 때문에 OCR 설치 단계에서 배포가 실패해, 사이트를 살리려고 "
            "OCR 패키지를 떼어 놓았습니다(2026-09-08).\n\n"
            "**되살리는 법** — [Google AI Studio](https://aistudio.google.com/apikey)에서 "
            "무료 API 키를 받아, 앱 설정(**Manage app → Settings → Secrets**)에 "
            "`gemini_api_key = \"받은키\"` 한 줄을 넣으면 제미나이 비전이 대신 인식합니다.\n\n"
            "그때까지는 **아래 2단계에서 숫자를 직접 입력**하시면 저장·집계는 평소와 같습니다."
        )

    # 파일 목록이 바뀌면 OCR 상태 초기화
    current_names = [f.name for f in uploaded_files] if uploaded_files else []
    if current_names != st.session_state.uploaded_file_names:
        st.session_state.ocr_done = False
        st.session_state.ocr_results = {}
        st.session_state.uploaded_file_names = current_names

    if uploaded_files:
        from PIL import Image
        from ocr_parser import extract_from_image, get_badge_rooms

        images = []
        for f in uploaded_files:
            f.seek(0)
            images.append((f.name, Image.open(f).copy()))

        img_cols = st.columns(min(len(images), 3))
        for i, (name, img) in enumerate(images):
            with img_cols[i % 3]:
                st.image(img, caption=name, width='stretch')

        if not st.session_state.ocr_done:
            with st.spinner(f"{len(images)}장 인식 중..."):
                # ── 등록된 방 인원 인식 (ROOMS 필터 적용, 오인식 방지) ────
                merged = {}
                ocr_error = None
                try:
                    if _ocr_engine == 'gemini':
                        import gemini_vision
                        from concurrent.futures import ThreadPoolExecutor
                        _gkey = st.secrets.get('gemini_api_key', '')

                        # 한 장에 9~26초가 걸린다(실측). 줄 세우면 넉 장에 100초다.
                        # 서로 의존하지 않는 호출이라 동시에 보낸다 — 원격 CSV를
                        # 동시에 받게 한 v4.82와 같은 이유다.
                        # 한 장이 실패해도 나머지는 살린다. 스크린샷 넉 장 중
                        # 하나가 흐렸다고 전부 버리면 사람이 다시 다 올려야 한다.
                        def _one(item):
                            try:
                                return gemini_vision.extract_members(
                                    item[1], _gkey, ROOMS), None
                            except Exception as e:
                                return [], f"{item[0]}: {e}"

                        with ThreadPoolExecutor(max_workers=min(4, len(images))) as _ex:
                            _outs = list(_ex.map(_one, images))
                        for _rows, _ in _outs:          # 화면에 보인 순서대로 합친다
                            for r in _rows:
                                if r['room_num'] not in merged:
                                    merged[r['room_num']] = r['members']
                        _errs = [e for _, e in _outs if e]
                        if _errs:
                            ocr_error = "\n".join(_errs)
                        st.session_state._ocr_model = gemini_vision.LAST_MODEL
                    else:
                        for _, img in images:
                            for r in extract_from_image(img, ROOMS):
                                if r['room_num'] not in merged:
                                    merged[r['room_num']] = r['members']
                except Exception as e:
                    ocr_error = str(e)

                # ── 신규 방 후보 탐지: 배지 영역만 사용 (텍스트 오인식 차단) ──
                # 신규 방 후보는 **타당한 번호만** 받는다. OCR이 배지를 잘못
                # 읽으면(37→237 같은 자릿수 붙음) 그대로 등록 후보가 되고,
                # 등록해 버리면 인원 기록까지 남아 유령 방이 생긴다.
                # 실제로 237번방 4건이 이렇게 들어와 있었다(2026-08-13 정리).
                # 방 번호는 순차 증가하므로 '현재 최대 + 10'을 상한으로 둔다.
                _rn_max = (max(ROOMS) if ROOMS else 43) + 10
                # 배지 탐지는 tesseract 전용 경로다(픽셀 좌표 기반).
                # 제미나이일 때는 돌릴 것이 없어 건너뛴다.
                badge_new, badge_junk = {}, set()
                try:
                    for _, img in (images if _ocr_engine == 'tesseract' else []):
                        for rn, cnt_val in get_badge_rooms(img).items():
                            if rn in ROOMS or rn in badge_new:
                                continue
                            if not (1 <= rn <= _rn_max):
                                badge_junk.add(rn)
                                continue
                            badge_new[rn] = cnt_val
                except Exception:
                    pass
                if badge_junk:
                    st.caption(f"🔍 인식 오류로 보이는 방 번호 무시: "
                               f"{', '.join(str(x) for x in sorted(badge_junk))}")

                st.session_state.ocr_results = merged
                st.session_state.ocr_done = True
                st.session_state._ocr_error = ocr_error
                if badge_new:
                    st.session_state._pending_new_rooms = badge_new

                for rn in ROOMS:
                    if rn in merged:
                        st.session_state[f"inp_{rn}"] = merged[rn]
                    elif prev.get(rn) is not None:
                        st.session_state[f"inp_{rn}"] = int(prev[rn])
                    else:
                        st.session_state[f"inp_{rn}"] = 0

        else:
            cnt      = len(st.session_state.ocr_results)
            total_rn = len(ROOMS)
            if cnt == total_rn:
                st.success(f"✅ {cnt}/{total_rn}개 채팅방 전체 인식 완료")
            elif cnt > 0:
                st.warning(f"⚠️ {cnt}/{total_rn}개 인식 — 미인식 방은 전일 데이터로 채워집니다. 확인 후 수정하세요.")
            else:
                st.error("❌ 채팅방을 하나도 인식하지 못했습니다. 이미지 품질을 확인하거나 직접 입력하세요.")
            if st.session_state.get('_ocr_model'):
                st.caption(f"🤖 {st.session_state._ocr_model}로 인식했습니다.")
            if st.session_state.get('_ocr_error'):
                # 일부만 실패했어도 성공한 결과는 위에 이미 반영돼 있다.
                with st.expander("🔧 인식 실패 상세 (모델·설정·응답 그대로)"):
                    st.code(st.session_state._ocr_error)
            if st.button("🔄 다시 인식"):
                st.session_state.ocr_done = False
                st.session_state._pending_new_rooms = {}
                st.rerun()

        # ── 신규 채팅방 등록 확인 UI ──────────────────────────────────
        if st.session_state.get('_pending_new_rooms'):
            pending = st.session_state._pending_new_rooms
            with st.container(border=True):
                st.markdown(f"#### 🆕 새 채팅방 {len(pending)}개 감지")
                st.caption(
                    "이미지 배지에서 발견된 방입니다. **등록할 방만 체크하세요.** "
                    "OCR 오인식으로 잘못 감지된 방은 체크 해제 후 무시하세요."
                )
                selected_new = {}
                new_room_name_inputs = {}
                for rn in sorted(pending.keys()):
                    col_chk, col_cnt, col_nm = st.columns([1, 1, 3])
                    with col_chk:
                        checked = st.checkbox(f"채팅방 {rn}", key=f"chk_new_{rn}",
                                              value=True)
                        if checked:
                            selected_new[rn] = True
                    with col_cnt:
                        st.caption(f"인식 인원: {pending[rn]:,}명")
                    with col_nm:
                        new_room_name_inputs[rn] = st.text_input(
                            "방 이름",
                            value=f"채팅방 {rn}",
                            key=f"new_nm_{rn}",
                            label_visibility="collapsed",
                        )

                col_reg, col_skip = st.columns(2)
                with col_reg:
                    if st.button("✅ 선택한 방 등록", type="primary",
                                 width='stretch', key="btn_reg_new"):
                        rooms_to_add = {
                            rn: (new_room_name_inputs[rn].strip() or f"채팅방 {rn}")
                            for rn in selected_new
                        }
                        if rooms_to_add:
                            save_rooms_batch(rooms_to_add)
                            load_rooms.clear()
                            # 인식된 인원 수도 OCR 결과에 반영
                            for rn in rooms_to_add:
                                if rn in pending:
                                    st.session_state.ocr_results[rn] = pending[rn]
                                    st.session_state[f"inp_{rn}"] = pending[rn]
                        st.session_state._pending_new_rooms = {}
                        st.rerun()
                with col_skip:
                    if st.button("❌ 무시 (등록 안 함)",
                                 width='stretch', key="btn_skip_new"):
                        st.session_state._pending_new_rooms = {}
                        st.rerun()

        # ── 인식 결과 검토 테이블 ─────────────────────────────────
        if st.session_state.ocr_done:
            _show_ocr_review(st.session_state.ocr_results, ROOMS, prev)

    # ── 채팅방 빠른 관리 (잘못 등록된 방 삭제) ────────────────────
    with st.expander("🗂️ 채팅방 빠른 관리 — 잘못 등록된 방 삭제", expanded=False):
        st.caption("OCR 오인식으로 잘못 등록된 방을 여기서 바로 삭제할 수 있습니다. 이름·번호 수정은 ⚙️ 채팅방 설정 탭을 이용하세요.")
        del_cols = st.columns(3)
        for idx, rn in enumerate(ROOM_NUMBERS):
            with del_cols[idx % 3]:
                if st.button(f"🗑️ {rn} — {ROOMS[rn]}", key=f"quick_del_{rn}",
                             width='stretch'):
                    delete_room(rn)
                    load_rooms.clear()
                    st.toast(f"채팅방 {rn} 삭제 완료", icon="🗑️")
                    st.rerun()

    # ── 빠른 숫자 입력 ─────────────────────────────────────────
    with st.expander("⚡ 빠른 입력 — 숫자 목록 붙여넣기", expanded=False):
        st.caption(
            f"스크린샷 순서대로 인원 수를 입력하면 채팅방 {min(ROOM_NUMBERS)}~{max(ROOM_NUMBERS)} 순서로 자동 할당됩니다.\n"
            "공백 또는 쉼표로 구분하세요. (예: 1234 567 2100 890)"
        )
        import re as _re
        quick_text = st.text_input("인원 수 목록", placeholder="1234 567 2100 890 ...", key="quick_nums")
        if st.button("⚡ 자동 입력", key="quick_apply"):
            nums = [int(n) for n in _re.findall(r'\d+', quick_text) if 1 <= int(n) <= 99999]
            if nums:
                room_keys = sorted(ROOMS.keys())
                for i, n in enumerate(nums[:len(room_keys)]):
                    st.session_state[f"inp_{room_keys[i]}"] = n
                st.success(f"✅ {min(len(nums), len(room_keys))}개 방에 인원 입력 완료")
                st.rerun()
            else:
                st.warning("숫자를 입력해주세요.")

    # ── 인원 확인 및 수정 ──────────────────────────────────────
    st.subheader("2단계 — 인원 입력")

    _ocr_ran = st.session_state.get('ocr_done', False) and bool(st.session_state.ocr_results)
    if _ocr_ran:
        st.caption("OCR 결과를 확인하고 잘못된 숫자를 수정하세요.")
    else:
        _filled = sum(1 for rn in ROOM_NUMBERS if prev.get(rn))
        if _filled:
            st.caption(f"✅ 어제 값 {_filled}개 자동 로드됨 — 바뀐 숫자만 수정 후 저장하세요.")
        else:
            st.caption("각 채팅방의 오늘 인원을 입력하세요.")

    edited = {}
    cols = st.columns(3)

    for idx, room_num in enumerate(ROOM_NUMBERS):
        col = cols[idx % 3]
        with col:
            ocr_val  = st.session_state.ocr_results.get(room_num)
            prev_val = prev.get(room_num)

            # OCR 값 우선, 없으면 어제 값, 없으면 0
            if ocr_val is not None:
                default = int(ocr_val)
            elif prev_val is not None:
                default = int(prev_val)
            else:
                default = 0

            # help 텍스트: 값 출처 명시
            if ocr_val is not None:
                if prev_val is not None:
                    diff = int(ocr_val) - int(prev_val)
                    sign = "+" if diff >= 0 else ""
                    help_msg = f"📷 OCR 인식 | 전일: {int(prev_val):,}명 ({sign}{diff:,})"
                else:
                    help_msg = "📷 OCR 인식 | 전일 데이터 없음"
            elif prev_val is not None:
                help_msg = f"📅 전일 데이터 자동 입력 (OCR 미인식) | {int(prev_val):,}명"
            else:
                help_msg = "⚠️ 데이터 없음 — 직접 입력하세요"

            val = st.number_input(
                ROOMS[room_num],
                min_value=0,
                value=int(st.session_state.get(f"inp_{room_num}", default)),
                step=1,
                help=help_msg,
                key=f"inp_{room_num}",
            )
            edited[room_num] = val

    # ── 저장 ──────────────────────────────────────────────────
    st.subheader("3단계 — 저장")
    # 해당 날짜 데이터가 이미 존재하면 덮어쓰기 안내
    if not df_all.empty:
        _existing = df_all[df_all['date'].astype(str) == str(input_date)]
        if not _existing.empty:
            st.info(
                f"ℹ️ {input_date} 데이터가 이미 {len(_existing)}개 채팅방 저장되어 있습니다. "
                "저장하면 기존 데이터를 덮어씁니다."
            )

    # 날짜 메모 — 기존 메모 pre-fill
    _notes_all = load_date_notes()
    _existing_note = ""
    if not _notes_all.empty:
        _nr = _notes_all[_notes_all['date'].astype(str) == str(input_date)]
        if not _nr.empty:
            _existing_note = _nr['memo'].values[0]
    date_memo = st.text_input(
        "📝 오늘 메모 (선택)",
        value=_existing_note,
        placeholder="특이사항 기록 — 예: 광고 집행 시작, 이벤트 진행, 대규모 이탈 발생",
        key="date_memo_input",
    )

    col_save, col_reset = st.columns([3, 1])

    with col_save:
        if st.button("💾 저장하기", type="primary", width='stretch'):
            room_data = [
                {'room_num': rn, 'room_name': ROOMS[rn], 'members': v}
                for rn, v in edited.items()
                if v > 0
            ]
            missing_rooms = [ROOMS[rn] for rn, v in edited.items() if v == 0]
            if room_data:
                try:
                    with st.spinner("GitHub에 저장 중..."):
                        save_daily(str(input_date), room_data)
                        if date_memo.strip() or _existing_note:
                            save_date_note(str(input_date), date_memo.strip())
                    st.success(f"✅ {input_date} 데이터 저장 완료 — {len(room_data)}개 채팅방")
                    if missing_rooms:
                        st.warning(
                            f"⚠️ {len(missing_rooms)}개 채팅방이 입력되지 않았습니다:\n" +
                            "  |  ".join(missing_rooms)
                        )
                    st.session_state.ocr_done = False
                    st.session_state.ocr_results = {}
                    st.balloons()
                    # ── Slack 급감 알림 ──────────────────────────────
                    _slack_url = st.secrets.get("slack_webhook_url", "")
                    if _slack_url and prev:
                        _alerts = []
                        for _rn, _v in edited.items():
                            if _v > 0 and prev.get(_rn) is not None:
                                _pv = int(prev[_rn])
                                _diff = _v - _pv
                                _pct = abs(_diff / _pv * 100) if _pv > 0 else 0
                                if _diff < 0 and (_pct >= 10 or abs(_diff) >= 50):
                                    _alerts.append(
                                        f"• {ROOMS.get(_rn, f'채팅방{_rn}')}: "
                                        f"{_pv:,}명 → {_v:,}명 "
                                        f"({_diff:,}명, {round(_pct, 1)}% 감소)"
                                    )
                        if _alerts:
                            send_slack_alert(
                                _slack_url,
                                f"🚨 *인원 급감 알림* ({input_date})\n" + "\n".join(_alerts),
                            )
                except RuntimeError as e:
                    st.error(
                        f"❌ 저장 실패: {e}\n\n"
                        "잠시 후 다시 시도하거나, 사이드바 '🔄 데이터 새로고침' 후 재시도하세요."
                    )
            else:
                st.warning("입력된 인원이 없습니다. 숫자를 확인해주세요.")

    with col_reset:
        if st.button("초기화", width='stretch'):
            st.session_state.ocr_done = False
            st.session_state.ocr_results = {}
            st.rerun()


# ── 탭 2: 현황 대시보드 ───────────────────────────────────────────

def tab_dashboard():
    ROOMS = load_rooms()
    st.header("현황 대시보드")
    df = load_all()

    if df.empty:
        st.info("데이터가 없습니다. '오늘 입력' 탭에서 먼저 데이터를 입력해주세요.")
        return

    latest_date = df['date'].max()
    _today_str = str(date.today())

    # ── 오늘 미입력 강조 배너 ─────────────────────────────────
    if str(latest_date) < _today_str:
        st.error(
            f"📢 **오늘({_today_str}) 인원을 아직 입력하지 않았습니다!** "
            f"← '📸 오늘 입력' 탭으로 이동하여 데이터를 입력해주세요. "
            f"(최근 기록: {latest_date})"
        )

    st.caption(f"기준: {latest_date}")

    df_today = df[df['date'] == latest_date].copy()
    campaigns = get_current_campaigns()

    # ── 입력 완성도 경고 (일부 채팅방 누락) ──────────────────
    total_rooms = len(ROOMS)
    entered_rooms = len(df_today)
    if entered_rooms < total_rooms:
        missing_names = [ROOMS[rn] for rn in sorted(ROOMS.keys())
                         if rn not in df_today['room_num'].values]
        st.warning(
            f"⚠️ {latest_date} — {total_rooms - entered_rooms}개 채팅방 미입력: " +
            "  |  ".join(missing_names)
        )

    # ── 요약 지표 ──────────────────────────────────────────────
    total = int(df_today['members'].sum())
    df_changed = df_today.dropna(subset=['change'])
    net = int(df_changed['change'].sum()) if not df_changed.empty else 0
    up = int((df_changed['change'] > 0).sum()) if not df_changed.empty else 0
    down = int((df_changed['change'] < 0).sum()) if not df_changed.empty else 0

    # 입력 완수율: 첫 기록일 ~ 오늘 사이 데이터가 있는 날 비율
    first_date = df['date'].min()
    days_since = (date.today() - first_date).days + 1
    days_entered = df['date'].nunique()
    comp_rate = round(days_entered / days_since * 100, 1)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("전체 총원", f"{total:,}명")
    c2.metric("전일 대비 순증감", f"{net:+,}명")
    c3.metric("인원 증가 채팅방", f"{up}개")
    c4.metric("인원 감소 채팅방", f"{down}개")
    c5.metric("입력 완수율", f"{comp_rate}%", f"{days_entered}/{days_since}일")

    # 날짜 메모 표시
    _dash_notes = load_date_notes()
    if not _dash_notes.empty:
        _dn = _dash_notes[_dash_notes['date'].astype(str) == str(latest_date)]
        if not _dn.empty:
            st.info(f"📝 **{latest_date} 메모:** {_dn['memo'].values[0]}")

    # ── 데이터 신뢰도: 누락 날짜 감지 ──────────────────────────
    if days_since > 1:
        from datetime import timedelta as _td
        all_dates_in_range = set(
            str(first_date + _td(days=i)) for i in range(days_since)
        )
        entered_dates = set(df['date'].astype(str).unique())
        missing_dates = sorted(all_dates_in_range - entered_dates, reverse=True)
        if missing_dates:
            with st.expander(f"📅 누락 날짜 {len(missing_dates)}일 감지 — 클릭하여 확인", expanded=False):
                st.caption("아래 날짜는 데이터가 입력되지 않았습니다. 데이터 관리 탭에서 소급 입력할 수 있습니다.")
                # 최근 10개만 표시
                shown = missing_dates[:10]
                st.markdown("  ".join(f"`{d}`" for d in shown) +
                            (f"  _(외 {len(missing_dates)-10}일)_" if len(missing_dates) > 10 else ""))

    # ── 입력 현황 달력 ────────────────────────────────────────
    with st.expander("📅 입력 현황 달력 (최근 16주)", expanded=False):
        _fig_cal = calendar_heatmap_chart(df)
        if _fig_cal:
            st.plotly_chart(_fig_cal)
            _total_days = (date.today() - df['date'].min()).days + 1
            _entered_days = df['date'].nunique()
            st.caption(f"초록: 입력 완료 · 빨강: 데이터 없음 · 총 {_total_days}일 중 {_entered_days}일 입력 ({round(_entered_days/_total_days*100,1)}%)")

    # ── 증감 차트 + 상품별 분석 ───────────────────────────────
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        fig_bar = change_bar_chart(df_today, rooms=ROOMS)
        if fig_bar:
            st.plotly_chart(fig_bar)
    with col_c2:
        fig_prod = product_bar_chart(df, campaigns)
        if fig_prod:
            st.plotly_chart(fig_prod)
        elif not campaigns:
            st.info("⚙️ 채팅방 설정 탭에서 상품 정보를 등록하면 상품별 분석이 표시돼요.")

    # ── 목표 달성률 ────────────────────────────────────────────
    target_rows = [
        (rn, info)
        for rn, info in campaigns.items()
        if int(info.get('target_count', 0) or 0) > 0
    ]
    if target_rows:
        st.subheader("목표 달성 현황")
        goal_cols = st.columns(min(len(target_rows), 4))
        for i, (rn, info) in enumerate(sorted(target_rows)):
            target = int(info.get('target_count', 0))
            current_row = df_today[df_today['room_num'] == rn]
            current = int(current_row['members'].values[0]) if not current_row.empty else 0
            pct = round(current / target * 100, 1) if target else 0
            with goal_cols[i % 4]:
                st.metric(
                    label=f"{ROOMS.get(rn, f'채팅방 {rn}')}",
                    value=f"{current:,}명",
                    delta=f"목표 {pct}% ({target:,}명)",
                )

    # ── 주간 성과 랭킹 ────────────────────────────────────────────
    st.subheader("주간 성과 랭킹")
    fig_rank_top, fig_rank_bot = ranking_chart(df, rooms=ROOMS)
    if fig_rank_top or fig_rank_bot:
        rank_c1, rank_c2 = st.columns(2)
        with rank_c1:
            if fig_rank_top:
                st.plotly_chart(fig_rank_top)
            else:
                st.info("증가한 채팅방이 없습니다.")
        with rank_c2:
            if fig_rank_bot:
                st.plotly_chart(fig_rank_bot)
            else:
                st.success("감소한 채팅방이 없습니다.")
    else:
        st.info("주간 랭킹은 5일 이상 간격의 데이터가 있으면 자동으로 표시됩니다.")

    # ── 채팅방별 상세 표 ───────────────────────────────────────
    st.subheader("채팅방별 상세")

    display = df_today[['room_num', 'room_name', 'members', 'prev_members', 'change']].copy()
    display.columns = ['방 번호', '채팅방', '총원', '전일', '증감']
    display['진행 중인 강의'] = display['방 번호'].apply(
        lambda n: campaigns.get(int(n), {}).get('campaign_name', '-')
    )
    display['상품'] = display['방 번호'].apply(
        lambda n: campaigns.get(int(n), {}).get('product', '-')
    )
    display = display.sort_values('방 번호').reset_index(drop=True)

    def _style_change(series):
        return [
            'color: #2E7D32; font-weight: bold' if (not pd.isna(v) and v > 0)
            else 'color: #C62828; font-weight: bold' if (not pd.isna(v) and v < 0)
            else ''
            for v in series
        ]

    st.dataframe(
        display.style.apply(_style_change, subset=['증감']),
        hide_index=True,
        column_config={
            '총원': st.column_config.NumberColumn(format="%d명"),
            '전일': st.column_config.NumberColumn(format="%d명"),
            '증감': st.column_config.NumberColumn(format="%+d명"),
        },
    )

    # ── 텍스트 요약 ────────────────────────────────────────────
    st.subheader("요약")

    if not df_changed.empty:
        top_up = df_changed.sort_values('change', ascending=False).head(3)
        top_down = df_changed.sort_values('change').head(3)

        col_l, col_r = st.columns(2)
        with col_l:
            st.markdown("**인원 증가 TOP 3**")
            for _, row in top_up.iterrows():
                if row['change'] > 0:
                    camp = campaigns.get(int(row['room_num']), {}).get('campaign_name', '')
                    camp_str = f" · {camp}" if camp else ""
                    st.markdown(f"- {row['room_name']}{camp_str}: **+{int(row['change'])}명** (총 {int(row['members']):,}명)")
        with col_r:
            st.markdown("**인원 감소 TOP 3**")
            for _, row in top_down.iterrows():
                if row['change'] < 0:
                    camp = campaigns.get(int(row['room_num']), {}).get('campaign_name', '')
                    camp_str = f" · {camp}" if camp else ""
                    st.markdown(f"- {row['room_name']}{camp_str}: **{int(row['change'])}명** (총 {int(row['members']):,}명)")

    # ── 이탈률 경고 + 차트 ────────────────────────────────────
    # session_state에서 현재 임계값 읽기 (슬라이더 렌더 전에 계산에 사용)
    churn_threshold = st.session_state.get("churn_threshold", 5)
    churn_warnings: list = []

    if len(df) >= 2:
        dates_sorted = sorted(df['date'].unique())
        if len(dates_sorted) >= 2:
            # 경고 먼저 계산 (현재 threshold 기준)
            prev_date = dates_sorted[-2]
            df_prev_day = df[df['date'] == prev_date]
            for rn in df_today['room_num'].dropna().unique():
                cur_row  = df_today[df_today['room_num'] == rn]
                prev_row = df_prev_day[df_prev_day['room_num'] == rn]
                if cur_row.empty or prev_row.empty:
                    continue
                cur_m  = int(cur_row['members'].values[0])
                prev_m = int(prev_row['members'].values[0])
                if prev_m > 0 and prev_m > cur_m:
                    churn = round((prev_m - cur_m) / prev_m * 100, 1)
                    if churn >= churn_threshold:
                        churn_warnings.append(
                            f"{ROOMS.get(int(rn), f'채팅방 {rn}')} ({churn}%↓)"
                        )

            # 슬라이더 렌더 (다음 rerun부터 새 threshold 반영)
            churn_threshold = st.slider(
                "이탈률 경고 기준 (%)", min_value=1, max_value=20,
                value=churn_threshold, step=1, key="churn_threshold",
                help="전일 대비 인원 감소율이 이 값 이상이면 경고를 표시합니다."
            )
            if churn_warnings:
                st.error(
                    f"🚨 **이탈률 경고 (≥{churn_threshold}%):** " + "  |  ".join(churn_warnings) +
                    "\n\n전일 대비 인원이 기준치 이상 감소한 채팅방입니다. 콘텐츠 또는 광고 전략을 점검하세요."
                )

            # 3일 연속 이탈 경고
            if len(dates_sorted) >= 3:
                recent_3 = dates_sorted[-3:]
                declining = []
                for rn in ROOMS:
                    vals = []
                    for d in recent_3:
                        r = df[(df['date'] == d) & (df['room_num'] == rn)]
                        if not r.empty:
                            vals.append(int(r['members'].values[0]))
                    if len(vals) == 3 and vals[0] > vals[1] > vals[2]:
                        drop = vals[0] - vals[2]
                        pct = round(drop / vals[0] * 100, 1) if vals[0] > 0 else 0
                        declining.append(f"{ROOMS.get(rn, f'채팅방 {rn}')} (3일간 -{drop}명, -{pct}%)")
                if declining:
                    st.warning(
                        "📉 **3일 연속 이탈 감지:** " + "  |  ".join(declining) +
                        "\n\n최근 3일 연속으로 인원이 감소하고 있습니다. 원인을 점검하세요."
                    )

        fig_churn = churn_rate_chart(df, ROOMS, threshold=churn_threshold)
        if fig_churn:
            with st.expander("📉 이탈률 추이 차트", expanded=False):
                st.plotly_chart(fig_churn)

    # ── 채팅방별 주간 성장률 ──────────────────────────────────
    _df_dt = df.copy()
    _df_dt['date'] = pd.to_datetime(_df_dt['date'])
    _latest_dt = pd.to_datetime(latest_date)
    _week_cands = [d for d in _df_dt['date'].unique()
                   if pd.Timedelta('5 days') <= (_latest_dt - d) <= pd.Timedelta('9 days')]
    if _week_cands:
        _week_ago = max(_week_cands)
        _df_week = _df_dt[_df_dt['date'] == _week_ago]
        _growth = []
        for rn in ROOMS:
            _t = df_today[df_today['room_num'] == rn]
            _w = _df_week[_df_week['room_num'] == rn]
            if _t.empty or _w.empty:
                continue
            _cur = int(_t['members'].values[0])
            _prv = int(_w['members'].values[0])
            _rate = round((_cur - _prv) / _prv * 100, 1) if _prv > 0 else 0
            _growth.append({'name': ROOMS[rn], 'cur': _cur, 'rate': _rate})

        if _growth:
            with st.expander("📈 채팅방별 주간 성장률", expanded=False):
                st.caption(f"기준: {_week_ago.date()} → {latest_date}")
                _gcols = st.columns(min(4, len(_growth)))
                for i, g in enumerate(sorted(_growth, key=lambda x: x['rate'], reverse=True)):
                    _delta = f"+{g['rate']}%" if g['rate'] >= 0 else f"{g['rate']}%"
                    _gcols[i % 4].metric(g['name'], f"{g['cur']:,}명", _delta)

    # ── 현재 진행 중인 강의 목록 ───────────────────────────────
    if campaigns:
        st.subheader("현재 진행 중인 강의")
        camp_rows = []
        today = date.today()
        for room_num, info in sorted(campaigns.items()):
            start_str = info.get('start_date', '')
            try:
                start_dt = pd.to_datetime(start_str).date()
                day_n = (today - start_dt).days
                day_label = f"D+{day_n}"
            except Exception:
                day_label = '-'
            camp_rows.append({
                '방 번호': room_num,
                '채팅방': ROOMS.get(room_num, f'채팅방 {room_num}'),
                '강의명': info.get('campaign_name', '-'),
                '상품': info.get('product', '-'),
                '기수': info.get('cohort', '-'),
                '시작일': info.get('start_date', '-'),
                'D+N': day_label,
                '메모': info.get('memo', '-'),
            })
        st.dataframe(pd.DataFrame(camp_rows), hide_index=True)

    # ── 주간 요약 리포트 ──────────────────────────────────────
    with st.expander("📋 주간 요약 리포트", expanded=False):
        st.caption("클릭 후 Ctrl+A → Ctrl+C 로 전체 복사하여 공유하세요.")

        df_dt = df.copy()
        df_dt['date'] = pd.to_datetime(df_dt['date'])
        latest_dt = pd.to_datetime(latest_date)
        latest_total = int(df_today['members'].sum())

        # 5~9일 전 범위에서 가장 가까운 날짜 탐색
        week_cands = [d for d in df_dt['date'].unique()
                      if pd.Timedelta('5 days') <= (latest_dt - d) <= pd.Timedelta('9 days')]

        lines = []
        if week_cands:
            wa_dt   = max(week_cands)
            wa_str  = str(wa_dt.date())
            wa_total = int(df_dt[df_dt['date'] == wa_dt]['members'].sum())
            diff     = latest_total - wa_total
            diff_s   = f"+{diff:,}" if diff >= 0 else f"{diff:,}"
            lines.append(f"📊 주간 요약  {wa_str} → {latest_date}")
            lines.append(f"전체 총원: {latest_total:,}명  ({diff_s}명 전주 대비)")
        else:
            lines.append(f"📊 현황 요약  {latest_date}")
            lines.append(f"전체 총원: {latest_total:,}명")

        lines.append("")

        df_chg = df_today.dropna(subset=['change'])
        top_up = df_chg[df_chg['change'] > 0].sort_values('change', ascending=False).head(3)
        top_dn = df_chg[df_chg['change'] < 0].sort_values('change').head(3)

        if not top_up.empty:
            lines.append("▲ 인원 증가 TOP 3")
            for _, r in top_up.iterrows():
                nm = ROOMS.get(int(r['room_num']), f"채팅방 {r['room_num']}")
                lines.append(f"  {nm}  +{int(r['change']):,}명 → {int(r['members']):,}명")
            lines.append("")

        if not top_dn.empty:
            lines.append("▼ 인원 감소 TOP 3")
            for _, r in top_dn.iterrows():
                nm = ROOMS.get(int(r['room_num']), f"채팅방 {r['room_num']}")
                lines.append(f"  {nm}  {int(r['change']):,}명 → {int(r['members']):,}명")
            lines.append("")

        if churn_warnings:
            lines.append(f"⚠️ 이탈률 경고 (기준 ≥{churn_threshold}%)")
            for w in churn_warnings:
                lines.append(f"  {w}")
        else:
            lines.append(f"✅ 이탈률 경고 없음 (기준 ≥{churn_threshold}%)")

        if campaigns:
            lines.append("")
            lines.append("📚 진행 중인 강의")
            for rn, info in sorted(campaigns.items()):
                nm    = ROOMS.get(rn, f"채팅방 {rn}")
                cname = info.get('campaign_name', '-')
                mem_row = df_today[df_today['room_num'] == rn]
                mem = f"{int(mem_row['members'].values[0]):,}명" if not mem_row.empty else "-"
                lines.append(f"  {nm} ({cname}): {mem}")

        st.text_area(
            "요약 텍스트",
            value="\n".join(lines),
            height=300,
            key="weekly_summary_ta",
        )


# ── 탭 3: 전환 분석 ──────────────────────────────────────────────

def tab_conversion():
    ROOMS = load_rooms()
    st.header("전환 분석")
    st.caption("무료 특강 모객 → 유료 수강 전환을 강의 집계 실데이터로 분석하고, "
               "일별 신청·수강확정도 함께 기록합니다.")

    # ══ 실데이터 전환 (강의 집계: 무료 모객 → 유료 수강) ═══════════
    _csum = load_course_summary()
    if not _csum.empty:
        st.subheader("🔻 무료 특강 → 유료 수강 전환 (전체 실적)")
        st.caption("아임웹 강의 집계 기준. 무료 특강으로 모은 인원이 실제 유료 수강으로 "
                   "이어진 비율입니다. (세트합계·멤버십 제외)")
        _tf = int(_csum['free'].sum())
        _ts = int(_csum['students'].sum())   # 세트 수강생(매출 기준과 정합)
        _tr = int(_csum['revenue'].sum())
        _cv = (_ts / _tf * 100) if _tf else 0
        _kpi_band([
            ("🆓 무료 특강 모객", f"{_tf:,}<small>명</small>", "무료 신청(중복 포함)"),
            ("🎓 유료 수강생", f"{_ts:,}<small>명</small>", f"결제 {int(_csum['paid'].sum()):,}건"),
            ("🔄 종합 전환율", f"{_cv:.1f}<small>%</small>", "수강생 ÷ 무료"),
            ("💰 누적 매출", f"{_tr/1e8:,.1f}<small>억원</small>", "세트합계"),
        ])
        st.write("")

        cvc1, cvc2 = st.columns([1, 1.25])
        with cvc1:
            _ff = overall_conversion_funnel(_tf, _ts)
            if _ff:
                st.plotly_chart(_ff, key="conv_overall_funnel")
        with cvc2:
            _fp = product_conversion_rate_chart(_csum)
            if _fp:
                st.plotly_chart(_fp, key="conv_prod_rate")
        # 최고 전환 상품 인사이트
        _cc = _csum.copy()
        _cc['cv'] = _cc['students'] / _cc['free'].replace(0, float('nan'))
        _cc = _cc.dropna(subset=['cv'])
        if not _cc.empty:
            _bp = _cc.loc[_cc['cv'].idxmax()]
            st.info(f"💡 **{_bp['product']}**의 무료→유료 전환율이 **{_bp['cv']*100:.1f}%**로 가장 높습니다 — "
                    "무료 모객을 늘릴수록 유료 성과가 가장 잘 따라오는 상품군입니다.")
        st.divider()
        st.subheader("📋 일별 신청·수강 확정 기록")
        st.caption("아래는 채팅방별로 **일 단위 신청자·수강확정**을 수기 입력해 추적하는 영역입니다. "
                   "입력한 방만 그래프에 나타납니다.")

    campaigns = get_current_campaigns()
    if not campaigns:
        st.info("⚙️ 채팅방 설정 탭에서 진행 중인 강의를 먼저 등록해주세요.")
        return

    df_members = load_all()
    df_conv    = load_conversions()

    # ── 요약 지표 ──────────────────────────────────────────────
    latest_conv = get_latest_conversions()
    if not latest_conv.empty:
        total_applicants = int(latest_conv['applicants'].sum())
        total_confirmed  = int(latest_conv['confirmed'].sum())
        total_revenue    = int(latest_conv['revenue'].sum())
        conv_rate = round(total_confirmed / total_applicants * 100, 1) if total_applicants > 0 else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("총 신청자", f"{total_applicants:,}명")
        c2.metric("총 수강 확정", f"{total_confirmed:,}명")
        c3.metric("수강 전환율", f"{conv_rate}%")
        c4.metric("총 매출", f"{total_revenue:,}원")

        st.divider()

    # ── 퍼널 차트 ──────────────────────────────────────────────
    fig_funnel = funnel_chart(df_members, df_conv, campaigns, rooms=ROOMS)
    if fig_funnel:
        st.plotly_chart(fig_funnel)

    # ── 전환율 차트 ────────────────────────────────────────────
    fig_conv = conversion_rate_chart(df_conv, campaigns, rooms=ROOMS)
    if fig_conv:
        st.plotly_chart(fig_conv)

    # ── 기수별 전환율 비교 ─────────────────────────────────────
    fig_cohort_conv = cohort_conversion_chart(df_conv, campaigns, rooms=ROOMS)
    if fig_cohort_conv:
        st.plotly_chart(fig_cohort_conv)
    elif not df_conv.empty:
        st.info("전환 데이터를 입력하면 강의별 신청·수강확정·전환율 비교 차트가 표시됩니다.")

    # ── 전환 데이터 입력 ───────────────────────────────────────
    st.subheader("전환 데이터 입력")
    st.caption("강의별 신청자·수강 확정·매출을 기록합니다. 같은 방+날짜로 다시 저장하면 덮어씁니다.")

    with st.form("conversion_form"):
        col1, col2 = st.columns(2)
        with col1:
            conv_room = st.selectbox(
                "채팅방 (강의)",
                options=sorted(campaigns.keys()),
                format_func=lambda x: f"{ROOMS.get(x, f'채팅방 {x}')} — {campaigns[x].get('campaign_name', '')}",
            )
            conv_date = st.date_input("기준 날짜", value=date.today())
            applicants = st.number_input("신청자 수", min_value=0, step=1, value=0)
        with col2:
            confirmed = st.number_input("수강 확정자 수", min_value=0, step=1, value=0)
            revenue   = st.number_input("매출 (원)", min_value=0, step=10000, value=0,
                                        help="수강료 합계. 0이면 미입력.")
            conv_memo = st.text_input("메모", placeholder="특이사항 등")

        if st.form_submit_button("💾 저장", type="primary", width='stretch'):
            save_conversion(
                room_num=conv_room,
                date_str=str(conv_date),
                applicants=int(applicants),
                confirmed=int(confirmed),
                revenue=int(revenue),
                memo=conv_memo.strip(),
            )
            st.success(f"✅ {ROOMS.get(conv_room, f'채팅방 {conv_room}')} 전환 데이터 저장 완료")
            st.rerun()

    # ── 전환 이력 테이블 ───────────────────────────────────────
    if not df_conv.empty:
        st.subheader("전환 이력")
        disp = df_conv.copy()
        disp['채팅방'] = disp['room_num'].apply(lambda x: ROOMS.get(int(x), f"채팅방 {x}"))
        disp['강의명'] = disp['room_num'].apply(lambda x: campaigns.get(int(x), {}).get('campaign_name', '-'))
        disp['신청전환율'] = disp.apply(
            lambda r: f"{round(r['confirmed']/r['applicants']*100,1)}%"
            if r['applicants'] > 0 else '-', axis=1
        )
        disp = disp[['date', '채팅방', '강의명', 'applicants', 'confirmed', '신청전환율', 'revenue', 'memo']]
        disp.columns = ['날짜', '채팅방', '강의명', '신청자', '수강확정', '전환율', '매출(원)', '메모']
        disp = disp.sort_values('날짜', ascending=False).reset_index(drop=True)
        st.dataframe(disp, hide_index=True)
        conv_del_idx = st.number_input(
            "삭제할 행 번호 (0부터, 최신순 기준)",
            min_value=0, max_value=max(0, len(df_conv) - 1),
            step=1, key="conv_del_idx",
        )
        if st.button("🗑️ 전환 데이터 삭제", key="conv_del_btn", type="secondary"):
            delete_conversion_row(int(conv_del_idx))
            st.success("삭제 완료")
            st.rerun()

    st.divider()

    # ── 광고비 ROI 분석 ────────────────────────────────────────
    st.subheader("광고비 ROI 분석")

    # 방별 광고비 수기 입력은 계속 비어 있는데, 통합시트에서 받은 **기수별 광고비**는
    # 실제로 쌓여 있다. 입력만 기다리며 빈 화면을 두는 대신 지금 운영 중인 방이
    # 속한 기수의 실적을 먼저 보여준다. 한 기수에 방이 여러 개인 경우가 있어
    # (타로 4기 = 23·36번방) 기수 단위로 묶어 중복 합산을 막는다.
    _ca = load_campaign_adspend()
    if not _ca.empty and campaigns:
        _cur_keys = {}
        for _rn, _info in campaigns.items():
            _k = (str(_info.get('product', '')), str(_info.get('cohort', '')))
            _cur_keys.setdefault(_k, []).append(_rn)
        _g = _ca.groupby(['product', 'cohort']).agg(
            ad=('ad_spend', 'sum'), rev=('live_revenue', 'sum'),
            live=('live_date', 'max')).reset_index()
        _rows, _pending = [], []
        for (_p, _c), _rns in sorted(_cur_keys.items()):
            _room_lbl = ' · '.join(ROOMS.get(r, f"{r}번") for r in sorted(_rns))
            _m = _g[(_g['product'] == _p) & (_g['cohort'] == _c)]
            if _m.empty or int(_m['ad'].iloc[0]) == 0:
                _pending.append(f"{_p} {_c}({_room_lbl})")
                continue
            _ad, _rev = int(_m['ad'].iloc[0]), int(_m['rev'].iloc[0])
            _rows.append({
                '강의': f"{_p} {_c}", '채팅방': _room_lbl,
                '웨비나': str(pd.Timestamp(_m['live'].iloc[0]).date()),
                '광고비': f"{_ad/1e4:,.0f}만원", '라이브 매출': f"{_rev/1e8:.2f}억",
                'ROAS': f"{_rev/_ad:.1f}배" if _ad else '—',
            })
        if _rows:
            _asof_ca = _dataset_asof('캠페인별 광고비')
            st.markdown("**📊 진행 중인 방의 기수 광고 성과 (실데이터)**")
            st.caption(f"통합시트의 **기수별 광고비·라이브 매출** 기준"
                       + (f" (자료 기준 {_asof_ca})" if _asof_ca else "")
                       + ". 같은 기수를 쓰는 방은 한 줄로 묶어 중복 합산을 막았습니다.")
            st.dataframe(pd.DataFrame(_rows), hide_index=True, width='stretch')
        if _pending:
            st.caption("🕗 아직 웨비나 전이라 광고 실적이 없는 방: " + " · ".join(_pending))
        st.divider()

    st.caption("아래는 채팅방별 **일 단위 광고비**를 수기 입력해 CPM을 보는 보조 영역입니다. "
               "입력한 방만 그래프에 나타납니다.")

    df_adspend = load_adspend()

    # ROI 요약 지표
    if not df_adspend.empty and not df_conv.empty:
        total_spend = int(df_adspend['spend'].sum())
        latest_rev  = get_latest_conversions()
        total_rev   = int(latest_rev['revenue'].sum()) if not latest_rev.empty else 0
        total_conf  = int(latest_rev['confirmed'].sum()) if not latest_rev.empty else 0
        roas = round(total_rev / total_spend, 2) if total_spend > 0 else 0
        cpa  = round(total_spend / total_conf) if total_conf > 0 else 0

        r1, r2, r3 = st.columns(3)
        r1.metric("총 광고비", f"{total_spend:,}원")
        r2.metric("ROAS", f"{roas}x", help="매출 ÷ 광고비")
        r3.metric("CPA", f"{cpa:,}원", help="광고비 ÷ 수강 확정자")

    # ROI 차트
    fig_roi = roi_chart(df_adspend, df_conv, campaigns, ROOMS)
    if fig_roi:
        st.plotly_chart(fig_roi)

    # ── CPM 분석 ──────────────────────────────────────────────────
    if not df_adspend.empty and not df_members.empty:
        st.subheader("CPM 분석 (광고비 ÷ 인원증가)")
        st.caption("채팅방별 광고비 대비 인원 증가 효율을 비교합니다. 낮을수록 효율적입니다.")
        fig_cpm = cpm_chart(df_members, df_adspend, ROOMS)
        if fig_cpm:
            st.plotly_chart(fig_cpm)

    # 광고비 입력 폼
    with st.expander("📝 광고비 입력", expanded=df_adspend.empty):
        with st.form("adspend_form"):
            col1, col2 = st.columns(2)
            with col1:
                ad_room = st.selectbox(
                    "채팅방 (강의)",
                    options=sorted(campaigns.keys()),
                    format_func=lambda x: f"{ROOMS.get(x, f'채팅방 {x}')} — {campaigns[x].get('campaign_name', '')}",
                    key="ad_room",
                )
                ad_date    = st.date_input("집행 날짜", value=date.today(), key="ad_date")
                ad_channel = st.selectbox("광고 채널", options=CHANNEL_OPTIONS, key="ad_channel")
            with col2:
                ad_spend = st.number_input("광고비 (원)", min_value=0, step=10000, value=0, key="ad_spend")
                ad_imps  = st.number_input("노출수", min_value=0, step=100, value=0, key="ad_imps")
                ad_clicks = st.number_input("클릭수", min_value=0, step=10, value=0, key="ad_clicks")
                ad_memo  = st.text_input("메모", placeholder="캠페인명 등", key="ad_memo")

            if st.form_submit_button("💾 광고비 저장", type="primary", width='stretch'):
                save_adspend(
                    room_num=ad_room, date_str=str(ad_date),
                    channel=ad_channel, spend=int(ad_spend),
                    impressions=int(ad_imps), clicks=int(ad_clicks),
                    memo=ad_memo.strip(),
                )
                st.success(f"✅ 광고비 저장 완료: {ad_channel} {int(ad_spend):,}원")
                st.rerun()

    # 광고비 이력 테이블
    if not df_adspend.empty:
        with st.expander("광고비 이력", expanded=False):
            ad_disp = df_adspend.copy()
            ad_disp['채팅방'] = ad_disp['room_num'].apply(lambda x: ROOMS.get(int(x), f"채팅방 {x}"))
            ad_disp['강의명'] = ad_disp['room_num'].apply(
                lambda x: campaigns.get(int(x), {}).get('campaign_name', '-')
            )
            ad_disp = ad_disp[['date', '채팅방', '강의명', 'channel', 'spend', 'impressions', 'clicks', 'memo']]
            ad_disp.columns = ['날짜', '채팅방', '강의명', '채널', '광고비(원)', '노출수', '클릭수', '메모']
            ad_disp = ad_disp.sort_values('날짜', ascending=False).reset_index(drop=True)
            st.dataframe(ad_disp, hide_index=True)
            ad_del_idx = st.number_input(
                "삭제할 행 번호 (0부터, 최신순 기준)",
                min_value=0, max_value=max(0, len(df_adspend) - 1),
                step=1, key="ad_del_idx",
            )
            if st.button("🗑️ 광고비 데이터 삭제", key="ad_del_btn", type="secondary"):
                delete_adspend_row(int(ad_del_idx))
                st.success("삭제 완료")
                st.rerun()

    # ── 콘텐츠 기록 ────────────────────────────────────────────────
    st.divider()
    st.subheader("콘텐츠 기록")
    st.caption("발행한 콘텐츠(영상·카드뉴스·블로그 등)를 날짜별로 기록합니다. 추이 그래프에 발행일이 오버레이로 표시됩니다.")

    df_content = load_content()

    with st.expander("📝 콘텐츠 입력", expanded=df_content.empty):
        with st.form("content_form"):
            col1, col2 = st.columns(2)
            with col1:
                c_date    = st.date_input("발행 날짜", value=date.today(), key="c_date")
                c_channel = st.selectbox("채널", options=CHANNEL_OPTIONS, key="c_channel")
                c_type    = st.selectbox("콘텐츠 유형", options=CONTENT_TYPE_OPTIONS, key="c_type")
            with col2:
                c_title = st.text_input("제목", placeholder="영상·게시물 제목", key="c_title")
                c_url   = st.text_input("URL", placeholder="https://...", key="c_url")
                c_memo  = st.text_input("메모", placeholder="특이사항", key="c_memo")

            if st.form_submit_button("💾 콘텐츠 저장", type="primary", width='stretch'):
                if not c_title.strip():
                    st.error("제목을 입력해주세요.")
                else:
                    save_content(
                        date_str=str(c_date), channel=c_channel,
                        content_type=c_type, title=c_title.strip(),
                        url=c_url.strip(), memo=c_memo.strip(),
                    )
                    st.success(f"✅ 콘텐츠 기록 저장 완료 — {c_channel} '{c_title.strip()}'")
                    st.rerun()

    if not df_content.empty:
        with st.expander("📋 콘텐츠 이력", expanded=False):
            c_disp = df_content.sort_values('date', ascending=False).reset_index()
            c_disp.columns = ['원본idx', '날짜', '채널', '유형', '제목', 'URL', '메모']
            st.dataframe(
                c_disp[['날짜', '채널', '유형', '제목', 'URL', '메모']],
                hide_index=True,
            )
            st.caption(f"총 {len(df_content)}건 기록됨")

            # 개별 삭제
            del_idx = st.number_input(
                "삭제할 행 번호 (0부터 시작, 최신순 정렬 기준)",
                min_value=0, max_value=max(0, len(df_content) - 1),
                step=1, key="content_del_idx",
            )
            if st.button("🗑️ 해당 행 삭제", key="content_del_btn", type="secondary"):
                # 최신순 정렬 후 del_idx번째 행의 원래 인덱스 추출
                sorted_df = df_content.sort_values('date', ascending=False).reset_index()
                real_idx = int(sorted_df.iloc[del_idx]['index'])
                delete_content_row(real_idx)
                st.success("삭제 완료")
                st.rerun()

    # ── 콘텐츠 효과 분석 ──────────────────────────────────────────
    if not df_content.empty and not df_members.empty:
        st.divider()
        st.subheader("📊 콘텐츠 효과 분석")
        st.caption("콘텐츠 발행일 기준 전후 3일 평균 인원을 비교합니다. (데이터가 없는 날짜는 제외)")

        df_m = df_members.copy()
        df_m['date'] = pd.to_datetime(df_m['date'])

        effect_rows = []
        for _, crow in df_content.sort_values('date', ascending=False).iterrows():
            pub_dt = pd.to_datetime(crow['date'])
            before_mask = (df_m['date'] >= pub_dt - pd.Timedelta(days=3)) & (df_m['date'] < pub_dt)
            after_mask  = (df_m['date'] > pub_dt) & (df_m['date'] <= pub_dt + pd.Timedelta(days=3))

            before_total = df_m[before_mask].groupby('date')['members'].sum()
            after_total  = df_m[after_mask].groupby('date')['members'].sum()

            if before_total.empty or after_total.empty:
                continue

            avg_before = round(before_total.mean())
            avg_after  = round(after_total.mean())
            diff       = avg_after - avg_before
            pct        = round(diff / avg_before * 100, 1) if avg_before > 0 else 0

            effect_rows.append({
                '날짜':       str(crow['date']),
                '채널':       crow.get('channel', '-'),
                '유형':       crow.get('content_type', '-'),
                '제목':       crow.get('title', '-'),
                '발행전 평균': f"{int(avg_before):,}명",
                '발행후 평균': f"{int(avg_after):,}명",
                '변화량':     f"+{int(diff):,}" if diff >= 0 else f"{int(diff):,}",
                '변화율':     f"+{pct}%" if pct >= 0 else f"{pct}%",
            })

        if effect_rows:
            st.dataframe(pd.DataFrame(effect_rows), hide_index=True)
        else:
            st.info("발행일 전후 3일 내 인원 데이터가 충분하지 않아 분석할 수 없습니다.")

    # ── 콘텐츠 상관 분석표 ────────────────────────────────────────
    if not df_content.empty and not df_members.empty:
        st.divider()
        st.subheader("📈 콘텐츠 발행 후 인원 변화 (+1일/+3일/+7일)")
        st.caption("콘텐츠 발행일 기준으로 전체 채팅방 합산 인원 변화량을 보여줍니다.")
        df_impact = content_impact_table(df_members, df_content)
        if df_impact is not None and not df_impact.empty:
            st.dataframe(df_impact, hide_index=True)
        else:
            st.info("발행일 기준 +1/+3/+7일 인원 데이터가 충분하지 않습니다.")


# ── 탭 3: 추이 그래프 ─────────────────────────────────────────────

def tab_trend():
    ROOMS = load_rooms()
    st.header("인원 추이 그래프")
    df = load_all()

    if df.empty:
        st.info("데이터가 없습니다.")
        return

    all_rooms = sorted(df['room_num'].unique().tolist())
    min_date = df['date'].min()
    max_date = df['date'].max()

    # ── 필터 바 ────────────────────────────────────────────────
    col_f1, col_f2, col_f3 = st.columns([2, 1, 1])
    with col_f1:
        selected = st.multiselect(
            "채팅방 선택 (비워두면 전체)",
            options=all_rooms,
            format_func=lambda x: ROOMS.get(x, f"채팅방 {x}"),
        )
    with col_f2:
        date_from = st.date_input("시작일", value=min_date, min_value=min_date, max_value=max_date)
    with col_f3:
        date_to = st.date_input("종료일", value=max_date, min_value=min_date, max_value=max_date)

    # 필터 적용
    df_filtered = df[(df['date'] >= date_from) & (df['date'] <= date_to)]
    filter_rooms = selected if selected else all_rooms
    df_filtered = df_filtered[df_filtered['room_num'].isin(filter_rooms)]

    # 선택 방의 목표 인원 조회
    campaigns = get_current_campaigns()
    targets = {
        rn: int(info.get('target_count', 0) or 0)
        for rn, info in campaigns.items()
        if rn in filter_rooms
    }

    # 광고·콘텐츠 오버레이 날짜 준비 (선택된 날짜 범위 내)
    df_adspend_trend = load_adspend()
    df_content_trend = load_content()
    ad_dates: list = []
    content_dates: list = []
    if not df_adspend_trend.empty:
        ad_dates = [
            d for d in df_adspend_trend['date'].unique()
            if date_from <= d <= date_to
        ]
    if not df_content_trend.empty:
        content_dates = [
            d for d in df_content_trend['date'].unique()
            if date_from <= d <= date_to
        ]

    # 라인 차트 (목표 인원 점선 + 광고·콘텐츠 발행일 오버레이)
    fig_line = trend_line_chart(df_filtered, filter_rooms, targets=targets,
                                rooms=ROOMS, ad_dates=ad_dates,
                                content_dates=content_dates)
    if fig_line:
        st.plotly_chart(fig_line)
        # 발행 기록은 있는데 이 구간에 하나도 없으면, 마커가 안 보이는 이유를
        # 밝힌다(기록이 없어서인지, 기간이 안 겹쳐서인지 구분이 안 됨).
        if not df_content_trend.empty and not content_dates:
            _cmax = max(df_content_trend['date'])
            st.caption(f"콘텐츠 발행 기록 {len(df_content_trend)}건이 있지만 마지막 발행이 "
                       f"**{_cmax}**라 이 기간과 겹치지 않습니다 — 그래서 발행일 표시가 "
                       "없습니다. 마스터 시트의 '오카방 업로드 계획'을 다시 채우면 "
                       "자동으로 반영돼, 발행이 인원 변화로 이어졌는지 볼 수 있습니다.")

    # 전체 합계 막대 차트
    fig_total = total_trend_bar(df_filtered)
    if fig_total:
        st.plotly_chart(fig_total)

    # ── 주간 비교 차트 ──────────────────────────────────────────
    fig_week = weekly_comparison_chart(df_filtered, rooms=ROOMS)
    if fig_week:
        st.plotly_chart(fig_week)
    else:
        st.info("주간 비교는 5일 이상 간격의 데이터가 있으면 자동으로 표시됩니다.")

    # ── D+N 모객 곡선 ───────────────────────────────────────────
    st.subheader("강의별 모객 곡선 비교 (D+N일 기준)")
    cohort_mode = st.radio("표시 방식", ["절대값", "순증감"], horizontal=True, key="cohort_mode")
    fig_cohort = cohort_trend_chart(df, campaigns, rooms=ROOMS, mode=cohort_mode)
    if fig_cohort:
        st.plotly_chart(fig_cohort)
    else:
        st.info("⚙️ 채팅방 설정 탭에서 강의를 등록하면 모객 곡선이 표시됩니다.")

    # ── 주간 집계 ────────────────────────────────────────────────
    st.subheader("주간 평균 인원 추이")
    fig_weekly = weekly_aggregate_chart(df_filtered, rooms=ROOMS)
    if fig_weekly:
        st.plotly_chart(fig_weekly)
    else:
        st.info("주간 집계는 7일 이상의 데이터가 있으면 자동으로 표시됩니다.")

    # ── 월간 집계 ────────────────────────────────────────────────
    st.subheader("월간 순증감 현황")
    fig_monthly = monthly_aggregate_chart(df_filtered, rooms=ROOMS)
    if fig_monthly:
        st.plotly_chart(fig_monthly)
    else:
        st.info("월간 집계는 30일 이상의 데이터가 있으면 자동으로 표시됩니다.")

    # ── 인원 예측 ────────────────────────────────────────────────
    st.subheader("인원 추이 예측 (7일)")
    forecast_rooms = st.multiselect(
        "예측할 채팅방 선택 (비워두면 전체)",
        options=filter_rooms,
        format_func=lambda x: ROOMS.get(x, f"채팅방 {x}"),
        key="forecast_rooms",
    )
    forecast_targets = forecast_rooms if forecast_rooms else filter_rooms
    fig_forecast = trend_forecast_chart(df, forecast_targets, rooms=ROOMS, forecast_days=7)
    if fig_forecast:
        st.plotly_chart(fig_forecast)
    else:
        st.info("예측 차트는 채팅방별 21일 이상의 데이터가 있으면 자동으로 표시됩니다.")

    # ── 날짜 메모 ───────────────────────────────────────────────
    _trend_notes = load_date_notes()
    if not _trend_notes.empty:
        _tn_filtered = _trend_notes[
            (_trend_notes['date'] >= date_from) &
            (_trend_notes['date'] <= date_to)
        ].sort_values('date', ascending=False)
        if not _tn_filtered.empty:
            with st.expander(f"📝 날짜 메모 ({len(_tn_filtered)}건, 선택 기간 내)", expanded=False):
                _tn_disp = _tn_filtered.copy()
                _tn_disp['date'] = _tn_disp['date'].astype(str)
                _tn_disp.columns = ['날짜', '메모']
                st.dataframe(_tn_disp, hide_index=True)


# ── 탭: 강의 분석 ────────────────────────────────────────────────

def tab_lecture_analysis():
    ROOMS    = load_all_room_names()   # 활성 + 종료 방 통합 이름
    df_all   = load_all()
    df_camps = load_campaigns()
    df_arch  = load_archived_rooms()

    st.header("🎓 강의 분석")
    st.caption("기수별 모객 효율·개강 후 잔류율·채팅방 운영 이력을 한눈에 비교합니다.")

    # ── 💰 채팅방 모객 → 수강생·매출 (방이 돈이 되는가) ────────
    _rf = _room_funnel()
    if not _rf.empty:
        st.subheader("💰 채팅방 모객 → 수강생 · 매출")
        st.caption("모은 인원이 **실제 수강생과 매출로 얼마나 이어졌는지**를 봅니다. "
                   "방 인원과 매출 데이터를 기수 단위로 이어 붙였습니다. "
                   "'방을 키우는 것'이 정답인지 숫자로 판단할 수 있습니다.")
        _tot_peak = int(_rf['peak'].sum())
        _tot_stu = int(_rf['students'].sum())
        _tot_rev = float(_rf['revenue'].sum())
        _best = _rf.iloc[0]
        _kpi_band([
            ("👥 방 모객 합계", f"{_tot_peak:,}<small>명</small>",
             f"{len(_rf)}개 기수 · 방 {int(_rf['rooms'].sum())}개"),
            ("🎓 수강생", f"{_tot_stu:,}<small>명</small>",
             f"방 대비 {_tot_stu/_tot_peak*100:.1f}%"),
            ("💰 방 1명당 매출", f"{_tot_rev/_tot_peak:,.0f}<small>원</small>", "전체 평균"),
            ("🏆 최고 효율", f"{_best['label']}",
             f"{_best['rev_per_member']:,.0f}원/명"),
        ])
        _fig_rf = room_funnel_chart(_rf)
        if _fig_rf:
            st.plotly_chart(_fig_rf, key="lec_room_funnel")

        _rows_rf = "".join(
            f'<tr><td><b>{r["label"]}</b></td>'
            f'<td style="text-align:right">{int(r["rooms"])}</td>'
            f'<td style="text-align:right">{int(r["peak"]):,}</td>'
            f'<td style="text-align:right">{int(r["students"]):,}</td>'
            f'<td style="text-align:right">{r["room_to_student"]:.2f}%</td>'
            f'<td style="text-align:right">{r["revenue"]/1e8:.2f}억</td>'
            f'<td style="text-align:right;font-weight:700">'
            f'{r["rev_per_member"]:,.0f}원</td></tr>'
            for _, r in _rf.iterrows())
        st.markdown(
            '<table class="gp-dtbl" style="width:100%;border-collapse:collapse;'
            'font-size:13px"><thead><tr style="text-align:left"><th>기수</th>'
            '<th style="text-align:right">방</th>'
            '<th style="text-align:right">방 인원</th>'
            '<th style="text-align:right">수강생</th>'
            '<th style="text-align:right">전환율</th>'
            '<th style="text-align:right">매출</th>'
            '<th style="text-align:right">방1명당</th></tr></thead>'
            f'<tbody>{_rows_rf}</tbody></table>', unsafe_allow_html=True)

        # 핵심 진단: 방 크기가 효율과 관계있는가
        _corr_rf = _rf['peak'].corr(_rf['rev_per_member']) if len(_rf) >= 3 else None
        _worst = _rf.iloc[-1]
        _msg_rf = (f"💡 **방 1명당 매출이 기수마다 크게 다릅니다** — 최고 "
                   f"**{_best['label']} {_best['rev_per_member']:,.0f}원** vs 최저 "
                   f"**{_worst['label']} {_worst['rev_per_member']:,.0f}원**"
                   f"({_best['rev_per_member']/max(_worst['rev_per_member'],1):.1f}배 차이). ")
        if _corr_rf is not None and abs(_corr_rf) < 0.35:
            _msg_rf += (f"방 크기와 1명당 매출의 상관은 **{_corr_rf:+.2f}로 거의 무관**합니다 — "
                        "**인원을 늘리는 것 자체는 매출로 이어지지 않습니다.** "
                        "같은 규모를 모아도 기수·상품에 따라 결과가 갈리므로, "
                        "'몇 명 모았나'보다 **'어떤 사람을 모았나'와 개강 후 전환 설계**가 "
                        "성패를 가릅니다.")
        elif _corr_rf is not None and _corr_rf <= -0.35:
            _msg_rf += (f"방 크기와 1명당 매출의 상관이 **{_corr_rf:+.2f}(음)** — "
                        "**크게 모을수록 1명당 가치는 오히려 떨어집니다.** "
                        "무리한 규모 확대보다 타깃 정밀도를 높이세요.")
        else:
            _msg_rf += "방 크기가 클수록 1명당 매출도 높은 경향이라, 규모 확대가 유효합니다."
        st.info(_msg_rf)
        st.caption("※ 기수 번호로 연결했으며, 한 기수의 단계별 매출(기초·심화·전문가 등)은 "
                   "합산했습니다. 같은 기수를 여러 방으로 나눈 경우도 합산합니다. "
                   "강의 집계가 이관된 기수만 표시됩니다.")
        st.divider()

    if df_all.empty or df_camps.empty:
        st.info("데이터가 없습니다. 강의 정보를 등록하고 인원 데이터를 입력해주세요.")
        return

    # ── 상품 필터 ─────────────────────────────────────────────
    products = sorted(df_camps['product'].dropna().unique().tolist())
    sel_product = st.selectbox(
        "상품 선택 (전체 비교 또는 특정 상품)",
        options=["전체"] + products,
        key="lecture_product_filter",
    )
    product_arg = None if sel_product == "전체" else sel_product

    # 활성 + 종료 캠페인 모두 포함
    df_camps_all = df_camps.copy()

    # ── 0. 모객 → 유료 전환 퍼널 ──────────────────────────────
    st.divider()
    st.subheader("🔻 모객 → 유료 전환 퍼널")
    st.caption("무료 웨비나 방 인원이 실제 유료 등록으로 이어진 비율입니다. "
               "웨비나 최고인원은 자동 계산되고, 유료 등록·매출은 아래에서 입력합니다.")

    df_enroll = load_enrollments()
    funnel_df = cohort_funnel_data(df_all, df_camps_all, df_enroll, rooms=ROOMS)
    if product_arg and not funnel_df.empty:
        funnel_df = funnel_df[funnel_df['product'] == product_arg]

    _has_conv = (not funnel_df.empty) and funnel_df['conversion'].notna().any()
    if _has_conv:
        # KPI 요약: 등록 데이터가 있는 기수 기준
        _fd = funnel_df[funnel_df['conversion'].notna()]
        _tot_peak = int(_fd['webinar_peak'].sum())
        _tot_enr  = int(_fd['enrolled'].sum())
        _tot_rev  = int(_fd['revenue'].sum())
        _avg_conv = round(_tot_enr / _tot_peak * 100, 2) if _tot_peak > 0 else 0
        fk1, fk2, fk3, fk4 = st.columns(4)
        fk1.metric("웨비나 최고인원 합", f"{_tot_peak:,}명")
        fk2.metric("유료 등록 합", f"{_tot_enr:,}명")
        fk3.metric("평균 전환율", f"{_avg_conv:.2f}%")
        fk4.metric("등록 매출 합", f"{_tot_rev:,}원" if _tot_rev > 0 else "—")

        # 기수별 전환율 막대 비교
        fig_conv_bar = cohort_conversion_bar_chart(funnel_df, product_arg)
        if fig_conv_bar:
            st.plotly_chart(fig_conv_bar)

        # 개별 기수 퍼널 (등록 데이터 있는 기수만 선택지 제공)
        _opts = [f"{r['product']} {r['cohort']}" for _, r in _fd.iterrows()]
        _sel = st.selectbox("기수별 상세 퍼널", options=_opts, key="funnel_cohort_sel")
        if _sel:
            _row = _fd[(_fd['product'] + ' ' + _fd['cohort']) == _sel].iloc[0]
            fig_funnel = conversion_funnel_chart(
                _row['product'], _row['cohort'],
                int(_row['webinar_peak']), int(_row['enrolled']), int(_row['revenue']),
            )
            if fig_funnel:
                st.plotly_chart(fig_funnel)
    else:
        st.info("아직 유료 등록 데이터가 없습니다. 아래에서 기수별 등록 인원을 입력하면 "
                "웨비나 최고인원과 자동 결합해 전환 퍼널이 표시됩니다.")

    # 유료 등록 입력/수정 (개인정보 없이 집계만)
    with st.expander("✏️ 유료 등록·매출 입력 / 수정", expanded=not _has_conv):
        st.caption("수강생 명단의 **집계 숫자만** 입력하세요 (이름·연락처 등 개인정보 입력 금지).")
        # 기수 목록: 캠페인 기준
        _camp_keys = (df_camps_all[['product', 'cohort']]
                      .drop_duplicates().sort_values(['product', 'cohort']))
        _key_opts = [f"{r['product']} {r['cohort']}" for _, r in _camp_keys.iterrows()]
        with st.form("enroll_form"):
            ec1, ec2, ec3 = st.columns([2, 1, 1])
            with ec1:
                _sel_key = st.selectbox("상품·기수", options=_key_opts, key="enroll_key")
            # 기존 값 자동 로드
            _cur_enr, _cur_rev = 0, 0
            if _sel_key and not df_enroll.empty:
                _p, _c = _sel_key.rsplit(' ', 1)
                _m = df_enroll[(df_enroll['product'] == _p) & (df_enroll['cohort'] == _c)]
                if not _m.empty:
                    _cur_enr = int(_m.iloc[0]['enrolled']); _cur_rev = int(_m.iloc[0]['revenue'])
            with ec2:
                _enr = st.number_input("유료 등록 인원", min_value=0, step=1, value=_cur_enr)
            with ec3:
                _rev = st.number_input("등록 매출(원)", min_value=0, step=100000, value=_cur_rev)
            if st.form_submit_button("저장", type="primary", width='stretch'):
                _p, _c = _sel_key.rsplit(' ', 1)
                save_enrollment(_p, _c, int(_enr), int(_rev))
                st.success(f"{_sel_key} — 등록 {_enr}명 저장 완료")
                st.rerun()

    # ── 1. 기수별 모객 곡선 ───────────────────────────────────
    st.divider()
    st.subheader("📈 기수별 모객 곡선 비교")
    st.caption("모객 시작일(D+0) 기준 각 기수의 인원 증가 궤적입니다. "
               "💡 위에서 **상품을 선택하면** 같은 상품의 기수끼리 선명하게 비교됩니다.")

    # '전체'는 곡선이 겹쳐 스파게티가 되므로 진행 중인 기수만 표시
    if product_arg is None:
        _recruit_camps = df_camps_all[df_camps_all['is_current'] == True]
        st.caption("현재 **진행 중인 기수**만 표시 중입니다. 종료 기수까지 보려면 상품을 선택하세요.")
    else:
        _recruit_camps = df_camps_all

    fig_recruit = recruitment_curve_chart(df_all, _recruit_camps, product_arg, rooms=ROOMS)
    if fig_recruit:
        st.plotly_chart(fig_recruit)
    else:
        st.info("강의 정보가 등록된 채팅방의 인원 데이터가 필요합니다.")

    # ── 2. 개강 후 잔류율 ─────────────────────────────────────
    st.divider()
    st.subheader("📉 개강 후 잔류율")
    st.caption("개강일 인원 = 100% 기준, 이후 날짜별 남아 있는 비율입니다.")

    has_lecture_date = df_camps_all['lecture_start_date'].astype(str).str.strip().ne('').any()
    if has_lecture_date:
        fig_ret = retention_after_opening_chart(df_all, df_camps_all, product_arg)
        if fig_ret:
            st.plotly_chart(fig_ret)
        else:
            st.info("개강일이 설정된 강의의 데이터가 필요합니다.")
    else:
        st.info("⚙️ 채팅방 설정 탭에서 각 강의의 **개강일**을 입력하면 잔류율 분석이 활성화됩니다.")

    # ── 3. 기수 효율 요약 표 ──────────────────────────────────
    st.divider()
    st.subheader("📊 기수별 모객 효율 요약")
    st.caption("회의 자료로 활용하세요. 표를 클릭하면 정렬 가능합니다.")

    eff_df = cohort_efficiency_df(df_all, df_camps_all, rooms=ROOMS)
    if product_arg and not eff_df.empty:
        eff_df = eff_df[eff_df['상품'] == product_arg]

    if not eff_df.empty:
        # 컬럼 색상 스타일링
        def _style_status(series):
            return ['color:#2E7D32;font-weight:bold' if v == '진행 중'
                    else 'color:#9E9E9E' for v in series]

        styled = eff_df.style.apply(_style_status, subset=['상태'])
        st.dataframe(styled, hide_index=True)

        # CSV 다운로드
        csv_bytes = eff_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            "📥 효율 요약 CSV 다운로드",
            data=csv_bytes,
            file_name=f"강의_모객_효율_{date.today()}.csv",
            mime='text/csv',
        )
    else:
        st.info("표시할 데이터가 없습니다.")

    # ── 4. 종료된 채팅방 이력 ─────────────────────────────────
    st.divider()
    st.subheader("🗂️ 운영 종료된 채팅방 이력")

    if df_arch.empty:
        st.info("운영 종료 처리된 채팅방이 없습니다.")
    else:
        # members 전체를 room_num으로 사전 그룹화 (O(N×M) → O(1) 조회)
        _members_by_room = {
            rn_: grp for rn_, grp in df_all.groupby('room_num')
        } if not df_all.empty else {}

        for _, ar in df_arch.sort_values('archived_date', ascending=False).iterrows():
            rn        = int(ar['room_num'])
            rname     = ar['room_name']
            arch_dt   = ar['archived_date']
            _raw_actual = ar.get('actual_close_date', '')
            actual_dt = '' if pd.isna(_raw_actual) else str(_raw_actual).strip()
            final_m   = int(ar['final_members'])
            reason    = ar['archive_reason']

            # 해당 방의 전체 인원 이력
            rdf = _members_by_room.get(rn, pd.DataFrame()).sort_values('date') if rn in _members_by_room else pd.DataFrame()
            first_m = int(rdf.iloc[0]['members']) if not rdf.empty else 0
            peak_m  = int(rdf['members'].max())   if not rdf.empty else 0
            days    = int((rdf['date'].max() - rdf['date'].min()).days) + 1 if len(rdf) > 1 else 1
            net     = final_m - first_m
            net_s   = f"+{net:,}" if net >= 0 else f"{net:,}"

            # 캠페인 이력
            camp_hist = df_camps[df_camps['room_num'] == rn]

            close_label = actual_dt if actual_dt else arch_dt
            exp_title = f"**{rname}** (채팅방 {rn}) — 종료일: {close_label}"
            exp_title += " ✅" if not camp_hist.empty else " ⚠️ 강의 미등록"

            with st.expander(exp_title, expanded=camp_hist.empty):
                mc1, mc2, mc3, mc4 = st.columns(4)
                mc1.metric("최종 인원", f"{final_m:,}명")
                mc2.metric("최고 인원", f"{peak_m:,}명")
                mc3.metric("전체 순증감", f"{net_s}명")
                mc4.metric("운영 기간", f"{days}일")

                # ── 실제 종료일 수정 (container로 대체 — 중첩 expander 금지) ──
                st.divider()
                with st.container(border=True):
                    st.markdown("**📅 실제 종료일 수정**")
                    try:
                        _init_date = date.fromisoformat(actual_dt) if actual_dt else date.fromisoformat(arch_dt)
                    except ValueError:
                        _init_date = date.today()
                    new_close = st.date_input(
                        "실제 종료일",
                        value=_init_date,
                        key=f"close_dt_{rn}",
                        help="채팅방을 실제로 나간 날짜를 입력하세요.",
                    )
                    if st.button("💾 저장", key=f"save_close_{rn}", type="primary"):
                        update_actual_close_date(rn, str(new_close))
                        st.success(f"실제 종료일 저장 완료: {new_close}")
                        st.rerun()

                # ── 강의 이력 / 누락 경고 ─────────────────────────
                st.divider()
                if not camp_hist.empty:
                    st.markdown("**강의 이력**")
                    disp = camp_hist[['campaign_name', 'product', 'cohort',
                                      'start_date', 'lecture_start_date', 'end_date', 'memo']].copy()
                    disp.columns = ['강의명', '상품', '기수', '모객 시작', '개강일', '종료일', '메모']
                    st.dataframe(disp, hide_index=True)
                else:
                    st.warning("강의(캠페인) 이력이 없습니다. 등록하면 강의 분석 탭 모객 곡선에 포함됩니다.")
                    with st.container(border=True):
                        st.markdown("**➕ 강의 빠른 등록**")
                        with st.form(key=f"quick_camp_{rn}"):
                            qc1, qc2 = st.columns(2)
                            q_name   = qc1.text_input("강의명", placeholder="예) 황금사주 무료특강")
                            q_prod   = qc2.selectbox("상품", PRODUCT_OPTIONS, key=f"qprod_{rn}")
                            qc3, qc4 = st.columns(2)
                            q_cohort = qc3.text_input("기수", placeholder="예) 11기")
                            q_target = qc4.number_input("목표 인원", min_value=0, step=50, value=0)
                            qc5, qc6 = st.columns(2)
                            q_start  = qc5.date_input("모객 시작일", key=f"qstart_{rn}")
                            q_lstart = qc6.date_input("개강일 (선택)", value=None, key=f"qlstart_{rn}")
                            if st.form_submit_button("강의 등록", type="primary", width='stretch'):
                                if q_name.strip():
                                    save_campaign(
                                        room_num=rn,
                                        campaign_name=q_name.strip(),
                                        product=q_prod,
                                        cohort=q_cohort.strip(),
                                        start_date=str(q_start),
                                        memo="",
                                        target_count=int(q_target),
                                        lecture_start_date=str(q_lstart) if q_lstart else "",
                                    )
                                    # 종료된 방이므로 is_current=False로 즉시 변경
                                    end_campaign(rn)
                                    st.success("강의 등록 완료!")
                                    st.rerun()
                                else:
                                    st.error("강의명을 입력해주세요.")

                st.caption(f"종료 사유: {reason} | 처리일: {arch_dt}")

                # ── 복원 버튼 ──────────────────────────────────────
                if st.button("↩️ 활성 채팅방으로 복원", key=f"restore_{rn}"):
                    restore_room(rn)
                    st.success(f"채팅방 {rn} — '{rname}' 복원 완료")
                    st.rerun()


# ── 탭: 마케팅 분석 ──────────────────────────────────────────────

def _ad_budget_diagnosis(camp) -> list:
    """상품군별 광고 예산 진단: 비중·ROAS·수확체감(광고비↔ROAS 상관)·권고."""
    import math
    if camp is None or camp.empty:
        return []
    tot = int(camp['ad_spend'].sum())
    out = []
    for p in ['사주', '타로', '부동산', '빌딩']:
        d = camp[camp['product'] == p].groupby('cohort', as_index=False).agg(
            ad=('ad_spend', 'sum'), rev=('live_revenue', 'sum'))
        d = d[d['ad'] > 0]
        if d.empty:
            continue
        ad = int(d['ad'].sum())
        roas = d['rev'].sum() / ad if ad else 0
        d = d.assign(roas=d['rev'] / d['ad'])
        corr = float(d['ad'].corr(d['roas'])) if len(d) >= 3 else float('nan')
        share = ad / tot * 100 if tot else 0
        sat = (not math.isnan(corr)) and corr <= -0.5   # 수확체감
        if roas >= 12 and share < 15:
            rec, why = '확대', '최고 효율·최소 비중'
        elif sat and share >= 20:
            rec, why = '축소·재점검', '비중 높은데 수확체감'
        elif sat:
            rec, why = '적정 유지', '수확체감 확인'
        elif roas >= 7:
            rec, why = '유지·소폭 확대', '효율 양호'
        else:
            rec, why = '적정 유지', '효율 보통'
        out.append({'product': p, 'ad': ad, 'share': share, 'roas': roas,
                    'corr': corr, 'saturated': sat, 'rec': rec, 'why': why})
    return out


def _webinar_calendar_html(year: int, month: int, events: pd.DataFrame) -> str:
    """월별 캘린더 HTML — 절기 전환일과 웨비나 일정을 함께 보여준다.

    달력 월 안에서 월주가 바뀌는 날(절입)을 표시해, 명리 기준 시기와
    실제 일정을 한 화면에서 대조할 수 있게 한다.
    """
    import calendar as _cal
    _cal.setfirstweekday(_cal.SUNDAY)
    weeks = _cal.monthcalendar(year, month)
    jd, jh = ganji.jeolgi(year, month)
    prev_mg = ganji.month_ganji(*ganji.saju_month_of(date(year, month, 1)))
    cur_mg = ganji.month_ganji(year, month)

    ev = {}
    if not events.empty:
        for _, e in events.iterrows():
            d = e['date']
            if d.year == year and d.month == month:
                ev.setdefault(d.day, []).append(e)

    head = "".join(
        f'<th style="padding:4px;font-size:11px;opacity:.6;'
        f'color:{"#E0483E" if i == 0 else ("#3B82F6" if i == 6 else "inherit")}">'
        f'{d}</th>'
        for i, d in enumerate(['일', '월', '화', '수', '목', '금', '토']))
    body = ""
    _today = date.today()
    for wk in weeks:
        body += "<tr>"
        for i, day in enumerate(wk):
            if day == 0:
                body += '<td style="border:1px solid rgba(127,127,127,.15)"></td>'
                continue
            _is_today = (year, month, day) == (_today.year, _today.month, _today.day)
            _bg = "rgba(200,144,26,.13)" if _is_today else "transparent"
            _dcol = "#E0483E" if i == 0 else ("#3B82F6" if i == 6 else "inherit")
            cell = (f'<div style="font-size:12px;font-weight:600;color:{_dcol}">'
                    f'{day}</div>')
            if day == jd:      # 절입일 — 월주가 바뀌는 날
                cell += (f'<div style="font-size:10px;line-height:1.3;margin-top:1px">'
                         f'<span style="opacity:.65">{ganji.jeolgi_name(month)} {jh}시</span><br>'
                         f'{ganji.colorize(prev_mg)}<span style="opacity:.4">→</span>'
                         f'{ganji.colorize(cur_mg)}</div>')
            for e in ev.get(day, []):
                _c = _PRODUCT_COLOR_APP.get(e['product'], '#90A4AE')
                _done = str(e.get('status', '')) == '완료'
                cell += (f'<div style="margin-top:3px;padding:2px 4px;border-radius:3px;'
                         f'background:{_c};color:#fff;font-size:10px;line-height:1.25;'
                         f'opacity:{"0.5" if _done else "1"}">'
                         f'<b>{e["product"]}</b><br>{str(e["topic"])[:14]}</div>')
            body += (f'<td style="border:1px solid rgba(127,127,127,.15);'
                     f'vertical-align:top;padding:3px;height:74px;background:{_bg}">'
                     f'{cell}</td>')
        body += "</tr>"
    return (f'<table style="width:100%;border-collapse:collapse;table-layout:fixed">'
            f'<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>')


_PRODUCT_COLOR_APP = {'사주': '#C8901A', '타로': '#8A5CF6',
                      '부동산': '#2E9E5B', '빌딩': '#3B82F6'}


def _webinar_baseline(product, camp_ad, base):
    """과거 실적에서 이 강의의 '통상 규모'를 뽑아 예산·모객을 역산 제안.

    예산 권한이 없는 실무자가 숫자를 지어내지 않고, **근거를 들고 요청**할 수
    있게 하려는 것. 중앙값을 쓰는 이유는 한두 번의 큰 집행에 끌려가지 않기 위함.
    """
    if camp_ad is None or camp_ad.empty:
        return None
    c = camp_ad[camp_ad['product'] == product].copy()
    c = c[pd.to_numeric(c['ad_spend'], errors='coerce').fillna(0) > 0]
    if c.empty:
        return None
    _ad = float(pd.to_numeric(c['ad_spend'], errors='coerce').median())
    _rev = float(pd.to_numeric(c['live_revenue'], errors='coerce').median())
    out = {'n': len(c), 'ad': _ad, 'rev': _rev,
           'roas': (_rev / _ad) if _ad else 0}
    if base and base[1]:
        out['leads'] = _ad / base[1]          # 평균 CPL로 기대 리드 역산
        out['cpl'] = base[1]
    return out


def _webinar_advice(ev, pb_map, oh, base, camp_ad=None, others=None) -> list:
    """예정된 웨비나 1건에 대한 모객 방안 추천 (근거 있는 항목만).

    others: 다른 예정 회차들(같은 주에 몰린 회차를 감지해 역할을 나누기 위함).
    """
    out = []
    prod = ev['product']
    d = ev['date'].date() if hasattr(ev['date'], 'date') else ev['date']
    b = pb_map.get(prod)

    # ① 후킹 — 이 강의에서 검증된 문구
    if b and b.get('hooks'):
        _vol = max(b['hooks'], key=lambda h: h['signups'])
        _cv = b['hooks'][0]
        out.append(("🎣 후킹",
                    f"모객은 **{_vol['topic']}**({_vol['signups']:,}명 실적), "
                    f"마감은 **{_cv['topic']}**(전환 {_cv['conv']:.1f}%)로 이원화"))
        # 이미 정해진 주제가 검증된 후킹과 다르면, 주제를 바꾸라는 게 아니라
        # 광고 카피에서 그 각도를 빌려 쓰라고 알려준다.
        _tp = str(ev.get('topic', '')).strip()
        if _tp and _tp not in (_vol['topic'], _cv['topic']):
            out.append(("🔗 주제 연결",
                        f"등록 주제 **{_tp}**는 실적 데이터에 없는 새 각도입니다. "
                        f"주제는 그대로 두되 광고 카피에는 검증된 **{_vol['topic']}** "
                        f"각도(돈·투자 언어)를 섞어 클릭을 확보하고, 랜딩·마감 단계에서 "
                        f"**{_cv['topic']}**의 표현으로 넘기세요. 새 후킹은 실적이 없으니 "
                        "기존 후킹 소재와 **함께 돌려** 비교하는 편이 안전합니다."))

    # ①-2 같은 주 연속 회차 — 같은 소재를 두 번 돌리면 서로 잠식한다
    if others is not None and len(others):
        _near = []
        for _, _o in others.iterrows():
            _od = _o['date'].date() if hasattr(_o['date'], 'date') else _o['date']
            if _od != d and _o['product'] == prod and abs((_od - d).days) <= 3:
                _near.append(_od)
        if _near:
            _wd = ['월', '화', '수', '목', '금', '토', '일']
            out.append(("👥 같은 주 회차",
                        f"{prod} 특강이 **{', '.join(f'{x.month}/{x.day}({_wd[x.weekday()]})' for x in sorted(_near))}"
                        f"** 에도 있습니다. 같은 소재를 그대로 두 번 돌리면 같은 사람에게 "
                        "중복 노출돼 예산만 나눠 씁니다. **회차별로 소재·타깃을 갈라** "
                        "(예: 1회차=검증 후킹·광범위 타깃, 2회차=새 각도·리타깃) "
                        "어느 쪽이 이기는지 이번에 확인해 두세요."))

    # ② 시기 — 그 날짜가 속한 명리월이 이 강의에 유리한가
    sm = ganji.saju_month_of(d)
    if sm and not oh.empty:
        _mg = ganji.month_ganji(*sm)
        _el = ganji.element_of(_mg[1])          # 월지 오행
        o = oh[oh['product'] == prod]
        if len(o) >= 6 and _el:
            gb = o.groupby('branch_element').agg(
                n=('saju_month', 'size'), f=('free_signups', 'sum'),
                pd_=('paid_orders', 'sum'))
            gb = gb[gb['n'] >= 2]
            if not gb.empty and _el in gb.index and gb['f'].sum():
                gb['avg'] = gb['f'] / gb['n']
                gb['cv'] = (gb['pd_'] / gb['f'] * 100).where(gb['f'] > 0, 0)
                _rank_v = int((gb['avg'] > gb.loc[_el, 'avg']).sum()) + 1
                _rank_c = int((gb['cv'] > gb.loc[_el, 'cv']).sum()) + 1
                _n = len(gb)
                _t = (f"이 날은 **{ganji.ym_korean(*sm)} {_mg}月**(월지 {_el}"
                      f"{ganji.ELEMENT_HANJA.get(_el, '')}). "
                      f"{prod} 기준 이 오행 시기는 **모객 {_rank_v}/{_n}위 · "
                      f"전환 {_rank_c}/{_n}위**")
                if _rank_v <= 2 and _rank_c > 2:
                    _t += " — **모객엔 좋고 전환은 약한 시기**라 리드 확보에 무게를 두고, 마감은 다음 시기로 이어가세요."
                elif _rank_c <= 2 and _rank_v > 2:
                    _t += " — **전환이 강한 시기**라 마감·업셀을 이때 배치하세요."
                elif _rank_v <= 2 and _rank_c <= 2:
                    _t += " — 모객·전환 모두 강한 **황금 구간**입니다."
                else:
                    _t += " — 특별히 유리한 시기는 아니니 소재·타깃으로 승부하세요."
                out.append(("🌳 시기", _t))

    # ③ 예산·목표 — 정해져 있으면 진단, 비어 있으면 **데이터가 제안**
    _tg = int(ev['target_signups']) or 0
    _bd = int(ev['budget']) or 0
    _bl = _webinar_baseline(prod, camp_ad, base)
    if base and _tg and _bd:
        _need = _bd / _tg
        _v = ("🟢 여유 있는 목표" if _need >= base[1]
              else ("🟡 기준선보다 빡빡" if _need >= base[0] else "🔴 과도하게 공격적"))
        out.append(("💰 예산·목표 점검",
                    f"목표 {_tg:,}명 / 예산 {_bd/1e4:,.0f}만원 → "
                    f"필요 CPL **{_need:,.0f}원** ({_v}). "
                    f"기준선 최저 {base[0]:,.0f}·평균 {base[1]:,.0f}원"))
    elif _bl:
        # 예산 권한이 없는 경우 — 요청할 근거를 만들어 준다
        _t = (f"과거 **{prod} 웨비나 {_bl['n']}회**의 통상 규모는 광고비 "
              f"**{_bl['ad']/1e4:,.0f}만원**(중앙값)이고, 그때 매출은 "
              f"**{_bl['rev']/1e8:.2f}억**(ROAS {_bl['roas']:.1f}배)이었습니다. ")
        if _bl.get('leads'):
            _t += (f"평균 리드 단가 {_bl['cpl']:,.0f}원 기준으로 이 예산이면 "
                   f"**약 {_bl['leads']:,.0f}명** 모객이 기대됩니다.")
        out.append(("💰 통상 규모 (요청 근거)", _t))
    elif _tg and base:
        out.append(("💰 필요 예산 추정",
                    f"목표 {_tg:,}명이면 평균 CPL {base[1]:,.0f}원 기준 "
                    f"**약 {_tg*base[1]/1e4:,.0f}만원**이 필요합니다"))

    # ④ 준비 일정 (D-day)
    #
    # 예전엔 지난 단계를 그냥 지웠다. 그러면 D-5처럼 급한 시점에 남는 게
    # "D-3 소재 교체 → D-1 리마인드"뿐이라, 가장 도움이 필요할 때 조언이
    # 가장 빈약해졌다. 지난 단계는 지우지 말고 '안 했으면 지금 당장'으로
    # 바꿔 보여주고, 남은 날에 맞춰 할 일을 압축해 준다.
    _dd = (d - date.today()).days
    if _dd >= 0:
        _plan = [(14, "소재 3안 제작(동영상 우선)"),
                 (7, "광고 시작·초기 CPL 확인"),
                 (3, "저효율 소재 교체·예산 재배분"),
                 (1, "리마인드 발송(문자·채팅방)")]
        _todo, _late = [], []
        for _k, _label in _plan:
            (_todo if _dd >= _k else _late).append(f"D-{_k} {_label}")
        _t = f"**D-{_dd}**"
        if _late:
            _t += ("\n· ⚠️ **이미 지난 단계** — 아직 안 했다면 오늘 한 번에 몰아서: "
                   + " · ".join(_late))
        if _todo:
            _t += "\n· 남은 일정: " + " → ".join(_todo)
        if _dd <= 7:
            _t += ("\n· 지금 구간에서 가장 중요한 건 **새로 만드는 것이 아니라 "
                   "돌고 있는 소재의 CPL 점검**입니다. "
                   + (f"기준선 {base[1]:,.0f}원을 넘는 소재는 즉시 끄고 "
                      f"남은 예산을 이긴 소재로 옮기세요." if base else
                      "리드 단가가 나쁜 소재를 끄고 남은 예산을 이긴 소재로 옮기세요."))
        if _dd <= 2:
            _t += ("\n· 마지막 이틀은 **신청자 참석 전환**이 관건입니다 — "
                   "채팅방·문자 리마인드와 시작 30분 전 알림을 잊지 마세요.")
        out.append(("🗓 준비", _t))
    return out


def _room_funnel() -> pd.DataFrame:
    """채팅방 모객 → 수강생·매출 연결 (기수 단위).

    이 앱의 출발점인 '채팅방 인원'과 매출 데이터가 그동안 따로 놀았다.
    campaigns(방→상품·기수)로 이어 붙여 **방 1명이 얼마의 매출이 됐는지**를 본다.

    주의: 기수명 형식이 서로 다르다(campaigns '11기' vs cohort_revenue
    '11기(기+심)'). 기수 '번호'로 맞추고, 한 기수의 단계별 매출은 합산한다.
    같은 기수를 여러 방으로 나눠 모은 경우(예: 돈사공 11기 3개 방)도 합산.
    """
    mem = load_all()
    camp = load_campaigns()
    crev = load_cohort_revenue()
    if mem.empty or camp.empty or crev.empty:
        return pd.DataFrame()

    def _num(s):
        m = re.search(r'(\d+)', str(s))
        return m.group(1) if m else None

    cr = crev.copy()
    cr['n'] = cr['cohort'].map(_num)
    cr = cr.dropna(subset=['n'])
    agg = cr.groupby(['product', 'n'], as_index=False).agg(
        students=('students', 'sum'), revenue=('revenue', 'sum'))

    cp = camp.copy()
    cp['n'] = cp['cohort'].map(_num)
    peak = mem.groupby('room_num')['members'].max().reset_index(name='peak')
    cp = cp.merge(peak, on='room_num', how='left')
    rooms = cp.dropna(subset=['n']).groupby(['product', 'n'], as_index=False).agg(
        peak=('peak', 'sum'), rooms=('room_num', 'count'))

    j = rooms.merge(agg, on=['product', 'n'], how='inner')
    j = j[(j['peak'] > 0) & (j['students'] > 0)]
    if j.empty:
        return j
    j['rev_per_member'] = j['revenue'] / j['peak']
    j['room_to_student'] = j['students'] / j['peak'] * 100
    j['label'] = j['product'] + ' ' + j['n'] + '기'
    return j.sort_values('rev_per_member', ascending=False).reset_index(drop=True)


def _cpl_baseline():
    """검증된 후킹 소재의 리드 단가(CPL) 기준선 — 실험 결과 판정용.

    (최저, 평균, 최고) 원. 데이터가 없으면 None.
    """
    w = load_webinar_hook_ad()
    if w.empty:
        return None
    p = w[w['leads'] > 0]
    if p.empty:
        return None
    avg = p['spend'].sum() / p['leads'].sum()
    return float(p['cpl'].min()), float(avg), float(p['cpl'].max())


def tab_webinar():
    st.header("🗓️ 웨비나 일정 & 모객 계획")
    st.caption("무료특강(웨비나) 일정을 달력에 올리면, 각 회차에 맞는 **후킹·시기·예산·"
               "준비 일정**을 데이터에서 추천합니다. 절기 전환일도 함께 표시돼 "
               "명리 기준 시기와 실제 일정을 대조할 수 있습니다.")

    ws = load_webinar_schedule()
    pb = _course_playbook()
    pb_map = {b['product']: b for b in pb}
    oh = load_ohaeng_period()
    base = _cpl_baseline()
    camp_ad = load_campaign_adspend()

    # ── 월 선택 + 캘린더 ─────────────────────────────────
    _t = date.today()
    c1, c2, _ = st.columns([1, 1, 2])
    with c1:
        _yy = st.number_input("연도", min_value=2024, max_value=2030,
                              value=_t.year, step=1, key="wb_year")
    with c2:
        _mm = st.number_input("월", min_value=1, max_value=12,
                              value=_t.month, step=1, key="wb_month")
    _yy, _mm = int(_yy), int(_mm)
    st.markdown(f"#### {ganji.ym_korean(_yy, _mm)} · "
                f"{ganji.month_ganji(_yy, _mm)}月 "
                f"<span style='font-size:12px;opacity:.6'>"
                f"({ganji.jeolgi_label(_yy, _mm)}부터)</span>",
                unsafe_allow_html=True)
    st.markdown(_webinar_calendar_html(_yy, _mm, ws), unsafe_allow_html=True)
    st.caption("색 블록 = 예정된 웨비나(흐린 것은 완료) · "
               "절입일 칸에는 월주가 바뀌는 시각이 표시됩니다.")

    # ── 예정 웨비나별 추천 ───────────────────────────────
    st.divider()
    _up = ws[ws['date'].dt.date >= _t] if not ws.empty else pd.DataFrame()

    # 시트에서 '대기중'으로 받아온 모집방 중 일정이 안 잡힌 것 — 원본 시트에는
    # 웨비나 날짜 칸이 아예 없어서(개설일·강의 시작일뿐) 자동으로 채울 수 없다.
    # 그런데 일정을 등록하지 않으면 아래 회차별 모객 방안이 통째로 안 나온다.
    _, _wait_rooms = _lecture_date_split(load_campaigns())
    _up_prod = set(_up['product'].astype(str)) if not _up.empty else set()
    _need_wb = (_wait_rooms[~_wait_rooms['product'].astype(str).isin(_up_prod)]
                if not _wait_rooms.empty else pd.DataFrame())
    if not _need_wb.empty:
        _nl = []
        for _, _r in _need_wb.iterrows():
            _sd = pd.to_datetime(_r['start_date'], errors='coerce')
            _nl.append(f"**{_r['campaign_name']}**"
                       + (f"(개설 후 {(_t - _sd.date()).days}일)"
                          if pd.notna(_sd) else ""))
        st.info(f"🗓️ 모집 중인데 웨비나 일정이 등록되지 않은 방 **{len(_need_wb)}개** — "
                + " · ".join(_nl)
                + "\n\n원본 시트에 웨비나 날짜 칸이 없어 자동으로 채우지 못합니다. "
                  "아래 **➕ 웨비나 일정 추가**에 날짜만 넣으면 이 회차의 후킹·예산·"
                  "준비 일정 추천이 바로 나옵니다.")

    if _up.empty:
        st.info("예정된 웨비나가 없습니다. 아래에서 일정을 추가하면 "
                "회차별 모객 방안을 추천해 드립니다.")
    else:
        st.subheader(f"📌 다가오는 웨비나 {len(_up)}건 — 회차별 모객 방안")
        for _, e in _up.head(6).iterrows():
            _d = e['date'].date()
            _dd = (_d - _t).days
            with st.expander(
                    f"{'🔴' if _dd <= 7 else '🟡' if _dd <= 14 else '⚪'} "
                    f"{_d} ({['월','화','수','목','금','토','일'][_d.weekday()]}) · "
                    f"{e['product']} · {e['topic']}  —  D-{_dd}",
                    expanded=(_dd <= 14)):
                for _t2, _v in _webinar_advice(e, pb_map, oh, base, camp_ad,
                                               others=_up):
                    st.markdown(
                        f'<div style="margin-bottom:7px">'
                        f'<span style="opacity:.6;font-size:12px">{_t2}</span><br>'
                        f'<span style="font-size:13px;line-height:1.6">'
                        f'{_md_bold(_v)}</span></div>', unsafe_allow_html=True)
                if str(e.get('memo', '')).strip() and str(e['memo']) != 'nan':
                    st.caption(f"메모: {e['memo']}")

                # 예산·목표가 미정이면 '요청서'를 만들어 준다.
                # 실무자는 숫자를 정하는 사람이 아니라, 근거를 들고 요청하는 사람.
                if not int(e['budget']) or not int(e['target_signups']):
                    _bl2 = _webinar_baseline(e['product'], camp_ad, base)
                    if _bl2:
                        _hk = ""
                        _b2 = pb_map.get(e['product'])
                        if _b2 and _b2.get('hooks'):
                            _hv = max(_b2['hooks'], key=lambda h: h['signups'])
                            _hk = (f"\n- 후킹은 과거 최다 모객 '{_hv['topic']}'"
                                   f"({_hv['signups']:,}명) 계열로 준비하겠습니다.")
                        _req = (
                            f"[{_d} {e['product']} 무료특강 — 광고 예산 요청]\n\n"
                            f"- 과거 {e['product']} 웨비나 {_bl2['n']}회의 통상 광고비는 "
                            f"{_bl2['ad']/1e4:,.0f}만원(중앙값)이었고, "
                            f"그때 매출은 {_bl2['rev']/1e8:.2f}억"
                            f"(ROAS {_bl2['roas']:.1f}배)였습니다.\n"
                            + (f"- 이 예산이면 리드 단가 {_bl2['cpl']:,.0f}원 기준 "
                               f"약 {_bl2['leads']:,.0f}명 모객이 기대됩니다.\n"
                               if _bl2.get('leads') else "")
                            + f"- 요청: 광고비 {_bl2['ad']/1e4:,.0f}만원"
                            + (f" / 목표 모객 {_bl2['leads']:,.0f}명"
                               if _bl2.get('leads') else "")
                            + _hk
                            + "\n- 집행 후 리드 단가와 전환을 기록해 다음 회차에 "
                              "반영하겠습니다.")
                        with st.expander("📋 예산 요청 문구 (복사해서 보고)"):
                            st.code(_req, language=None)
                            st.caption("숫자를 지어내지 말고 **과거 실적을 근거로 요청**하는 "
                                       "형식입니다. 정해지면 위 폼에서 값을 채워 넣으면 "
                                       "목표 대비 점검으로 바뀝니다.")

                if st.button("삭제", key=f"wb_del_{e['id']}"):
                    delete_webinar(e['id'])
                    st.rerun()

    # ── 지난 회차 정리 ───────────────────────────────────
    # 날짜가 지나면 '예정'인 채로 목록에서 그냥 사라진다. 실제로 8/20·8/21 사주
    # 특강이 '예정'으로 남아 있는데 화면에는 "예정된 웨비나가 없습니다"만 떴다.
    # 끝난 회차를 닫아 둬야 달력·목록이 사실과 맞는다.
    _past_wb = (ws[(ws['date'].dt.date < _t)
                   & (ws['status'].astype(str) != '완료')]
                if not ws.empty else pd.DataFrame())
    if not _past_wb.empty:
        st.divider()
        st.warning(f"🔚 날짜가 지났는데 '예정'으로 남아 있는 회차 **{len(_past_wb)}건**"
                   " — 완료로 닫으면 달력에 흐리게 표시되고 목록이 사실과 맞습니다.")
        for _, _pe in _past_wb.sort_values('date').iterrows():
            _pc1, _pc2 = st.columns([5, 1])
            _pc1.markdown(f"**{_pe['date'].date()}** · {_pe['product']} · {_pe['topic']}")
            if _pc2.button("완료 처리", key=f"wb_done_{_pe['id']}", width='stretch'):
                save_webinar({**_pe.to_dict(),
                              'date': str(_pe['date'].date()), 'status': '완료'})
                st.rerun()

    # ── 일정 등록 ────────────────────────────────────────
    st.divider()
    with st.expander("➕ 웨비나 일정 추가",
                     expanded=bool(ws.empty or not _need_wb.empty)):
        # 과거 이력으로 기본값 제안
        _hint = ""
        if not camp_ad.empty:
            _ca = camp_ad.copy()
            _ca['live_date'] = pd.to_datetime(_ca['live_date'], errors='coerce')
            _ca = _ca.dropna(subset=['live_date'])
            if not _ca.empty:
                _wd = _ca['live_date'].dt.dayofweek.mode()
                _wdn = ['월', '화', '수', '목', '금', '토', '일'][int(_wd.iloc[0])] \
                    if not _wd.empty else '수'
                _hint = (f"과거 {len(_ca)}회 진행 · 가장 많이 연 요일 **{_wdn}요일** · "
                         f"평균 광고비 {_ca['ad_spend'].mean()/1e4:,.0f}만원")
        if _hint:
            st.caption(_hint)
        with st.form("wb_new"):
            w1, w2 = st.columns(2)
            with w1:
                # 일정이 빠진 대기방이 있으면 그 강의를 미리 골라 둔다 —
                # 무엇을 등록해야 하는지 위에서 이미 알려 준 상태다.
                _wp_opts = ['사주', '타로', '부동산', '빌딩']
                _wp_idx = 0
                if not _need_wb.empty:
                    _p0 = str(_need_wb.iloc[0]['product'])
                    if _p0 in _wp_opts:
                        _wp_idx = _wp_opts.index(_p0)
                _wp = st.selectbox("강의", _wp_opts, index=_wp_idx)
                _wd2 = st.date_input("웨비나 날짜", value=_t + timedelta(days=14))
                _wst = st.selectbox("상태", ['예정', '완료'])
            with w2:
                _wt = st.text_input("주제·후킹", placeholder="예) 재물운 투자법")
                _wtg = st.number_input(
                    "목표 모객(명) — 모르면 0", min_value=0, step=100, value=0,
                    help="기획팀·대표님이 정하는 값입니다. 비워두면(0) 과거 실적으로 "
                         "통상 규모를 제안해 드립니다.")
                _wb = st.number_input(
                    "광고 예산(원) — 모르면 0", min_value=0, step=1000000, value=0,
                    help="정해지지 않았으면 0으로 두세요. 요청에 쓸 근거를 만들어 드립니다.")
            # 선택 강의의 검증된 후킹 힌트
            _hb = pb_map.get(_wp)
            if _hb and _hb.get('hooks'):
                _hv = max(_hb['hooks'], key=lambda h: h['signups'])
                st.caption(f"💡 {_wp} 검증된 후킹 — 모객 1위 **{_hv['topic']}**"
                           f"({_hv['signups']:,}명) · 전환 1위 "
                           f"**{_hb['hooks'][0]['topic']}**"
                           f"({_hb['hooks'][0]['conv']:.1f}%)")
            _wm = st.text_input("메모", placeholder="선택")
            if st.form_submit_button("일정 추가", type="primary"):
                if not _wt.strip():
                    st.error("주제·후킹을 입력해주세요.")
                else:
                    save_webinar({
                        'id': f"{_wd2}-{_wp}-{str(abs(hash(_wt)))[:4]}",
                        'date': str(_wd2), 'product': _wp, 'topic': _wt.strip(),
                        'target_signups': int(_wtg), 'budget': int(_wb),
                        'status': _wst, 'memo': _wm.strip()})
                    st.success(f"{_wd2} {_wp} 웨비나를 추가했습니다.")
                    st.rerun()


def tab_experiments():
    st.header("🧪 실험 일지")
    st.caption("실행한 마케팅을 **가설 → 결과 → 배운 점**으로 남깁니다. "
               "기록하지 않은 실험은 학습으로 남지 않습니다. "
               "쌓인 기록은 그대로 대표님 보고 근거가 됩니다.")

    exps = load_experiments()
    base = _cpl_baseline()

    # ── 요약 KPI ────────────────────────────────────────
    if not exps.empty:
        _done = exps[exps['status'] == '완료']
        _run = exps[exps['status'] == '진행중']
        _tot_b = int(exps['budget'].sum())
        _tot_l = int(exps['leads'].sum())
        _avg_cpl = _tot_b / _tot_l if _tot_l else 0
        _kpi_band([
            ("🧪 누적 실험", f"{len(exps)}<small>건</small>",
             f"진행중 {len(_run)} · 완료 {len(_done)}"),
            ("💸 집행 예산", f"{_tot_b/1e4:,.0f}<small>만원</small>", "실험 합계"),
            ("🎣 확보 리드", f"{_tot_l:,}<small>건</small>",
             f"평균 CPL {_avg_cpl:,.0f}원" if _tot_l else "—"),
            ("📚 배운 점", f"{int((exps['learning'].astype(str).str.len() > 1).sum())}"
                          f"<small>건</small>", "회고 기록"),
        ])

    if base:
        st.info(f"📏 **판정 기준선** — 지금까지 검증된 후킹 소재의 리드 단가는 "
                f"**{base[0]:,.0f}원(최저) ~ {base[2]:,.0f}원(최고)**, 평균 "
                f"**{base[1]:,.0f}원**입니다. 실험 CPL이 이 범위보다 **낮으면 성공**, "
                f"높으면 소재·타깃을 바꿔야 한다는 신호입니다.")

    (tab_brief, tab_new, tab_run, tab_log,
     tab_month, tab_guide) = st.tabs(
        ["🎨 소재 브리프", "➕ 새 실험 등록", "📝 결과 입력", "📚 실험 기록",
         "📄 월간 리포트", "📚 성장 가이드"])

    # ── 📄 월간 성과 리포트 (대표 보고용) ────────────────
    with tab_month:
        st.markdown("**대표님께 낼 이번 달 리포트를 한 장으로 자동 생성합니다.** "
                    "지표 변화 · 실행한 실험 · 배운 점 · 다음 달 계획이 들어갑니다.")
        perf = load_monthly_performance()
        ad_m = load_ad_spend_monthly()
        if perf.empty:
            st.info("월별 성과 데이터가 없어 리포트를 만들 수 없습니다.")
        else:
            _ms = sorted(perf['month'].astype(str).unique())[::-1]
            # 부분월(주문 명단이 중간에 끊긴 달)이 기본 선택되면 덜 채워진 매출이
            # 그대로 대표 보고서에 올라간다 — 완결된 달을 기본값으로 둔다.
            _done = set(complete_months(perf)['month'].astype(str))
            _dflt = next((i for i, m in enumerate(_ms) if m in _done), 0)
            _msel2 = st.selectbox(
                "보고할 달", _ms, index=_dflt, key="rep_month",
                format_func=lambda m: ganji.ym_label(m, with_ganji=False)
                + ("" if m in _done else "  ⚠️ 부분 집계"))
            if _msel2 not in _done:
                _ao2 = order_asof()
                st.warning(f"⚠️ **{ganji.ym_label(_msel2, with_ganji=False)}은 아직 덜 채워진 달**입니다"
                           + (f" — 주문 명단이 {_ao2}까지만 담겨 있습니다. " if _ao2 else ". ")
                           + "이대로 보고하면 실적이 실제보다 낮게 나갑니다. "
                           "최신 주문 명단을 받아 갱신한 뒤 보고하세요.")
            _cur = perf[perf['month'].astype(str) == _msel2]
            _i = _ms.index(_msel2)
            _prev_m = _ms[_i + 1] if _i + 1 < len(_ms) else None
            _prv = perf[perf['month'].astype(str) == _prev_m] if _prev_m else pd.DataFrame()

            def _d(cur, prev, unit="", pct=False):
                if not prev:
                    return "—"
                _c = (cur - prev) / prev * 100
                _s = "▲" if cur > prev else ("▼" if cur < prev else "—")
                return f"{_s} {abs(_c):.0f}%"

            _c_free = int(_cur['free_signups'].sum()) if not _cur.empty else 0
            _c_paid = int(_cur['paid_orders'].sum()) if not _cur.empty else 0
            _c_rev = int(_cur['revenue'].sum()) if not _cur.empty else 0
            _p_free = int(_prv['free_signups'].sum()) if not _prv.empty else 0
            _p_paid = int(_prv['paid_orders'].sum()) if not _prv.empty else 0
            _p_rev = int(_prv['revenue'].sum()) if not _prv.empty else 0
            _c_ad = int(ad_m[ad_m['month'].astype(str) == _msel2]['spend'].sum()) \
                if not ad_m.empty else 0
            _p_ad = int(ad_m[ad_m['month'].astype(str) == str(_prev_m)]['spend'].sum()) \
                if (not ad_m.empty and _prev_m) else 0
            _c_cv = _c_paid / _c_free * 100 if _c_free else 0
            _p_cv = _p_paid / _p_free * 100 if _p_free else 0

            _kpis = [
                ("무료 모객", f"{_c_free:,}명", f"{_p_free:,}명" if _prev_m else "—",
                 _d(_c_free, _p_free)),
                ("유료 전환", f"{_c_paid:,}건", f"{_p_paid:,}건" if _prev_m else "—",
                 _d(_c_paid, _p_paid)),
                ("전환율", f"{_c_cv:.2f}%", f"{_p_cv:.2f}%" if _prev_m else "—",
                 _d(_c_cv, _p_cv)),
                ("매출", f"{_c_rev/1e8:.2f}억", f"{_p_rev/1e8:.2f}억" if _prev_m else "—",
                 _d(_c_rev, _p_rev)),
            ]
            if _c_ad:
                _kpis.append(("광고비", f"{_c_ad/1e4:,.0f}만원",
                              f"{_p_ad/1e4:,.0f}만원" if _p_ad else "—",
                              _d(_c_ad, _p_ad)))
                _kpis.append(("ROAS", f"{_c_rev/_c_ad:.1f}배",
                              f"{_p_rev/_p_ad:.1f}배" if _p_ad else "—",
                              _d(_c_rev/_c_ad, _p_rev/_p_ad if _p_ad else 0)))

            # 이번 달 실험
            _exp_m, _learn = [], []
            if not exps.empty:
                _in = exps[exps['start'].astype(str).str[:7] == _msel2]
                for _, e in _in.iterrows():
                    _v = "—"
                    if int(e['leads']) > 0 and base:
                        _cplv = e['cpl']
                        _v = ("🟢 성공" if _cplv <= base[1]
                              else ("🟡 보통" if _cplv <= base[2] else "🔴 중단"))
                    _exp_m.append({'product': e['product'], 'hook': e['hook'],
                                   'budget': int(e['budget']), 'leads': int(e['leads']),
                                   'cpl': e['cpl'], 'conv': int(e['conversions']),
                                   'verdict': _v})
                    if str(e['learning'] or '').strip():
                        _learn.append(f"[{e['product']}] {e['learning']}")

            # 다음 달 계획 = 전략 결론에서
            _con2 = _strategy_conclusion()
            _next = [(s['title'],
                      re.sub(r'\*\*', '', s['why'])[:160],
                      re.sub(r'\*\*', '', s['how'])[:160])
                     for s in _con2.get('strategies', [])[:3]]

            # 미리보기
            st.divider()
            st.markdown(f"#### 미리보기 — {ganji.ym_label(_msel2, with_ganji=False)}")
            _kr = "".join(
                f'<tr><td><b>{k}</b></td><td style="text-align:right">{c}</td>'
                f'<td style="text-align:right;opacity:.6">{p}</td>'
                f'<td style="text-align:right">{d}</td></tr>'
                for k, c, p, d in _kpis)
            st.markdown(
                '<table class="gp-dtbl" style="width:100%;border-collapse:collapse;'
                'font-size:13px"><thead><tr style="text-align:left"><th>지표</th>'
                '<th style="text-align:right">이번 달</th>'
                '<th style="text-align:right">전월</th>'
                '<th style="text-align:right">증감</th></tr></thead>'
                f'<tbody>{_kr}</tbody></table>', unsafe_allow_html=True)
            if _exp_m:
                st.markdown(f"**실험 {len(_exp_m)}건** · 배운 점 {len(_learn)}건")
            else:
                st.caption("이 달에 기록된 실험이 없습니다 — 실험을 등록하면 "
                           "리포트에 자동으로 들어갑니다.")

            try:
                from pdf_report import generate_monthly_report
                _pdf = generate_monthly_report(
                    ganji.ym_label(_msel2, with_ganji=False), _kpis, _exp_m, _learn,
                    _next,
                    notes=["수치는 주문 원본 집계 기준입니다.",
                           "다음 달 계획은 사이트의 전략 결론에서 자동 생성됩니다."])
                st.download_button(
                    "📄 월간 리포트 PDF 다운로드", _pdf,
                    file_name=f"마케팅리포트_{_msel2}.pdf", mime="application/pdf",
                    type="primary")
            except Exception as _e:
                st.error(f"PDF 생성 실패: {_e}")

    # ── 📚 마케터 성장 가이드 ────────────────────────────
    with tab_guide:
        st.markdown("**이 사이트로 어떻게 일하고 성장하는가.** 지표를 읽고 → 행동으로 "
                    "옮기고 → 결과를 회고하는 순서를 정리했습니다.")

        with st.expander("🗓 주간 루틴 — 이 순서대로만 하시면 됩니다", expanded=True):
            _routine = [
                ("월 · 방향 잡기 (15분)", "🧭 종합 보고 → 최종 전략 결론",
                 "이번 주에 건드릴 **강의 1개만** 고릅니다. 여러 개를 동시에 바꾸면 "
                 "무엇이 효과였는지 알 수 없습니다."),
                ("화 · 소재 기획 (30분)", "🧪 실험 일지 → 🎨 소재 브리프",
                 "고른 강의의 브리프를 뽑아 후킹 3안을 정합니다. "
                 "**검증된 문구의 변주**로 시작하는 게 가장 안전합니다."),
                ("수 · 실험 등록 후 집행", "🧪 실험 일지 → ➕ 새 실험 등록",
                 "**가설을 먼저 적고** 광고를 겁니다. 가설이 없으면 결과가 나와도 "
                 "배울 게 없습니다."),
                ("금 · 중간 점검 (20분)", "🧪 실험 일지 → 📝 결과 입력",
                 "리드 수를 넣으면 CPL이 자동 판정됩니다. 🔴가 뜨면 **주말 넘기지 말고 중단**."),
                ("월말 · 회고와 보고", "🧪 실험 일지 → 📚 실험 기록 / 📑 경영진 보고",
                 "배운 점을 적고, 보고용 요약을 복사해 대표님께 공유합니다."),
            ]
            for _t, _where, _what in _routine:
                st.markdown(
                    f'<div style="margin-bottom:9px">'
                    f'<b>{_t}</b> <span style="opacity:.55;font-size:12px">— {_where}</span><br>'
                    f'<span style="font-size:13px;opacity:.85">{_md_bold(_what)}</span></div>',
                    unsafe_allow_html=True)

        with st.expander("📖 용어 — 이 사이트에 나오는 숫자 읽는 법"):
            _terms = [
                ("CPL (리드 단가)", "무료 신청 1건을 얻는 데 쓴 광고비. **낮을수록 좋음**.",
                 f"우리 기준선 {base[1]:,.0f}원" if base else "광고비 ÷ 무료 신청 수"),
                ("CVR (전환율)", "무료 신청자 중 **유료 결제까지 간 비율**. 후킹의 '질'.",
                 "전환 ÷ 리드 × 100"),
                ("ROAS", "광고비 1원이 만든 매출. **2배 이상이면 통상 안전**.",
                 "매출 ÷ 광고비"),
                ("객단가 (AOV)", "수강생 1명이 낸 평균 금액. 높을수록 프리미엄 라인.",
                 "매출 ÷ 수강생"),
                ("수확체감", "광고비를 늘릴수록 **효율이 떨어지는 현상**. "
                             "'많이 쓸수록 좋다'가 틀린 이유.",
                 "광고비↑ → ROAS↓ 관계"),
                ("볼륨 자석 / 알짜", "많이 모으지만 전환이 낮은 후킹 vs "
                                     "적게 모아도 잘 파는 후킹. **역할이 다름**.",
                 "모객량 × 전환율로 판단"),
                ("자기완결형 / 관문형", "특강이 그 강의 판매로 직결되는 유형 vs "
                                        "다른 강의로 고객을 넘겨주는 유형.",
                 "self 비율 60% 이상이면 자기완결형"),
            ]
            _tr = "".join(
                f'<tr><td style="white-space:nowrap"><b>{a}</b></td>'
                f'<td>{_md_bold(b2)}</td>'
                f'<td style="opacity:.6;font-size:12px;white-space:nowrap">{c2}</td></tr>'
                for a, b2, c2 in _terms)
            st.markdown(
                '<table class="gp-dtbl" style="width:100%;border-collapse:collapse;'
                'font-size:13px"><thead><tr style="text-align:left"><th>용어</th>'
                '<th>뜻</th><th>계산</th></tr></thead>'
                f'<tbody>{_tr}</tbody></table>', unsafe_allow_html=True)

        with st.expander("🧭 숫자가 이러면 이렇게 — 판단 기준표"):
            _rules = [
                ("CPL이 기준선보다 낮다", "🟢", "예산 확대. 단, 한 번에 2배 이상 올리지 말 것"),
                ("CPL은 낮은데 전환이 안 난다", "🟡",
                 "리드는 싸게 왔지만 관심도가 낮은 타깃. 후킹은 유지하고 **타깃을 좁히세요**"),
                ("CPL이 높은데 전환은 좋다", "🟡",
                 "비싸도 좋은 고객. 객단가가 높은 강의라면 **유지**할 만합니다"),
                ("CPL도 전환도 나쁘다", "🔴", "즉시 중단. 후킹부터 다시"),
                ("모객은 느는데 매출이 안 는다", "🟡",
                 "**수확체감** 또는 뒤 단계 이탈. 강의별 상세에서 단계 전환을 확인하세요"),
                ("ROAS가 갑자기 떨어졌다", "🟡",
                 "광고비를 급히 늘렸는지 확인. 개강 시점과 어긋나면 자연스러운 변동일 수 있음"),
            ]
            _rr = "".join(
                f'<tr><td style="white-space:nowrap">{ic}</td><td><b>{a}</b></td>'
                f'<td>{_md_bold(c3)}</td></tr>' for a, ic, c3 in _rules)
            st.markdown(
                '<table class="gp-dtbl" style="width:100%;border-collapse:collapse;'
                'font-size:13px"><thead><tr style="text-align:left"><th></th>'
                '<th>상황</th><th>해야 할 일</th></tr></thead>'
                f'<tbody>{_rr}</tbody></table>', unsafe_allow_html=True)

        with st.expander("⚠️ 초보가 자주 하는 실수"):
            for _m in [
                "**한 번에 여러 개를 바꾼다** — 후킹·타깃·예산을 동시에 바꾸면 "
                "무엇이 효과였는지 영원히 알 수 없습니다. 하나씩.",
                "**결과가 나쁘면 기록하지 않는다** — 실패한 실험이 가장 값진 자산입니다. "
                "'이건 안 된다'를 아는 게 곧 실력입니다.",
                "**하루 이틀 보고 판단한다** — 최소 1~2주는 돌려야 의미 있는 숫자가 나옵니다.",
                "**모객 수만 본다** — 많이 모아도 전환이 없으면 비용만 씁니다. "
                "항상 CPL과 전환율을 **함께** 보세요.",
                "**대표님께 숫자만 보고한다** — '무엇을 했고 → 결과가 어땠고 → "
                "무엇을 배웠는지'를 함께 말해야 신뢰가 쌓입니다.",
            ]:
                st.markdown(f'<div style="font-size:13px;margin-bottom:7px">· '
                            f'{_md_bold(_m)}</div>', unsafe_allow_html=True)

        with st.expander("🚀 지금 가장 추천하는 첫 실험"):
            _pb2 = _course_playbook()
            _cand = [x for x in _pb2 if x['roas'] and x['adshare'] is not None]
            if _cand:
                _t = max(_cand, key=lambda x: x['roas'] / max(x['adshare'], 1))
                _msg2 = (f"**{_t['product']} 광고 확대 실험**\n\n"
                         f"· **근거**: 광고 ROAS **{_t['roas']:.1f}배**로 높은데 "
                         f"광고비 비중은 **{_t['adshare']:.0f}%**뿐입니다\n")
                if base:
                    _msg2 += (f"· **가설**: 예산을 늘려도 CPL이 기준선"
                              f"(**{base[1]:,.0f}원**) 아래로 유지될 것이다\n"
                              f"· **성공 기준**: CPL {base[1]:,.0f}원 이하 유지 · "
                              f"{base[2]:,.0f}원 초과 시 중단\n")
                _msg2 += "· **규모**: 100만~300만원 / 2~4주로 작게 시작"
                st.markdown(_msg2)
                st.caption("이 실험이 첫 시작으로 좋은 이유 — 이미 효율이 검증된 곳에 "
                           "예산을 더 쓰는 것이라 **실패 확률이 가장 낮고**, 성공하면 "
                           "숫자로 명확히 보여줄 수 있습니다.")

    # ── 🎨 소재 브리프 생성기 ────────────────────────────
    with tab_brief:
        st.markdown("**만들 소재의 기획서를 데이터에서 자동으로 뽑습니다.** "
                    "검증된 후킹·형식·시기·타깃·목표 CPL을 조합해, 무엇을 만들지 "
                    "막막하지 않게 해줍니다.")
        pb0 = _course_playbook()
        if not pb0:
            st.info("강의 집계 데이터가 없어 브리프를 만들 수 없습니다.")
        else:
            _bp = st.selectbox("어떤 강의의 소재를 만드나요?",
                               [b['product'] for b in pb0], key="brief_prod")
            b = next(x for x in pb0 if x['product'] == _bp)
            wha = load_webinar_hook_ad()
            region = load_region_signups()

            _sig = load_market_signals()
            _sp = _sig[_sig['product'] == _bp] if not _sig.empty else pd.DataFrame()

            _parts = []
            # 0) 지금 시장에서 먹히는 각도 (키워드 분석툴 이관)
            if not _sp.empty:
                _own = _sp[_sp['signal'] == 'own_top'].sort_values('metric1', ascending=False)
                _mkt = _sp[_sp['signal'] == 'market_top'].sort_values('metric1', ascending=False)
                _txt0 = ""
                if not _own.empty:
                    _txt0 += "· **우리 채널에서 가장 잘 먹힌 제목** (이 각도를 변주하세요)\n"
                    for _, r in _own.head(3).iterrows():
                        _m2 = f" · {r['metric2']}" if r['metric2'] else ""
                        _txt0 += f"   - {r['text']}  ({int(r['metric1']):,}회{_m2})\n"
                if not _mkt.empty:
                    _txt0 += "· **지금 시장 상위 영상** (경쟁이 쓰는 각도)\n"
                    for _, r in _mkt.head(3).iterrows():
                        _txt0 += f"   - {r['text']}  ({int(r['metric1']):,}회 · {r['metric2']})\n"
                if _txt0:
                    _cd = _sp['collected'].iloc[0] if 'collected' in _sp.columns else ''
                    _parts.append((f"⓪ 지금 먹히는 각도 (키워드 분석툴 · {_cd} 수집)",
                                   _txt0.rstrip()))

            # 1) 후킹 각도
            if b['hooks']:
                _vol = max(b['hooks'], key=lambda h: h['signups'])
                _cv = b['hooks'][0]
                _parts.append(("① 후킹 각도 (검증된 문구 기반)",
                               f"· 모객용 주력: **{_vol['topic']}** "
                               f"— 실적 {_vol['signups']:,}명 모객 / 전환 {_vol['conv']:.1f}%\n"
                               f"· 전환용 보조: **{_cv['topic']}** "
                               f"— 전환 {_cv['conv']:.1f}%로 최고\n"
                               f"· 제작 방향: 새 문구를 처음부터 만들기보다 "
                               f"**위 문구의 변주**(같은 약속, 다른 표현·사례)로 3안을 만들어 "
                               f"동시 테스트하세요."))
            # 2) 형식
            if not wha.empty and 'format' in wha.columns:
                _f = wha[wha['leads'] > 0].groupby('format').agg(
                    s=('spend', 'sum'), l=('leads', 'sum'))
                if len(_f) >= 2:
                    _f['cpl'] = _f['s'] / _f['l']
                    _bf = _f['cpl'].idxmin()
                    _parts.append(("② 소재 형식",
                                   f"· **{_bf} 우선** — 리드 단가 {_f.loc[_bf,'cpl']:,.0f}원으로 "
                                   f"가장 저렴 (타 형식 대비 "
                                   f"{(_f['cpl'].max()/_f['cpl'].min()-1)*100:.0f}% 우위)\n"
                                   f"· 편수: 같은 후킹으로 **3~5개** 만들어 함께 돌린 뒤 "
                                   f"이긴 소재에 예산을 몰아주세요."))
            # 3) 타깃
            _tg = []
            if not region.empty:
                _tot = int(region['signups'].sum())
                _cap = int(region[region['region'].isin(CAPITAL_REGIONS)]['signups'].sum())
                if _tot:
                    _tg.append(f"지역: **수도권 {_cap/_tot*100:.0f}%** 집중 "
                               f"(서울·경기·인천 우선, 예산 여유 시 광역시 확장) "
                               f"— 배송지 {_asof_tag('지역 분포')}")
            if b['hooks'] and b['hooks'][0].get('self_share'):
                _sh = b['hooks'][0]['self_share']
                _tg.append("성격: **자기완결형** — 특강→해당 강의 구매로 바로 이어짐"
                           if _sh >= 60 else
                           "성격: **관문형** — 특강 참여자 상당수가 다른 강의로 이동하므로 "
                           "랜딩에 다른 강의 동선도 함께 노출")
            if not _sp.empty:
                _age = _sp[_sp['signal'] == 'age'].sort_values('metric1', ascending=False)
                if not _age.empty:
                    _al = " · ".join(f"{r['text']}→{r['metric2']}"
                                     for _, r in _age.head(4).iterrows())
                    # 네이버 데이터랩은 연령대마다 따로 정규화되므로 연령 간 크기 비교가
                    # 불가능하다. '주 검색층'이 아니라 '최근 관심이 빠르게 느는 층'이다.
                    _tg.append(f"관심 급증 연령: **{_al}** — 최근 4주 검색이 이 연령대에서 "
                               "가장 빠르게 늘었습니다(**주 검색층이 아니라 증가 신호**). "
                               "새로 열리는 수요라 선점 여지가 있으니, 이 연령의 사례·말투로 "
                               "**시험 소재 1편**을 얹어 보세요")
            if _tg:
                _parts.append(("③ 타깃·노출", "\n".join("· " + t for t in _tg)))
            # 4) 시기
            if b['season']:
                s = b['season']
                _parts.append(("④ 집행 시기",
                               f"· 모객 강한 시기: **{s['vol']}"
                               f"({ganji.ELEMENT_HANJA.get(s['vol'],'')})월** "
                               f"(월평균 {s['vol_n']:,.0f}명) → 이때 광고비 집중\n"
                               f"· 전환 강한 시기: **{s['cv']}"
                               f"({ganji.ELEMENT_HANJA.get(s['cv'],'')})월** "
                               f"(전환 {s['cv_v']:.1f}%) → 이때 개강·마감 배치"))
            # 5) 예산·목표
            if base:
                _parts.append(("⑤ 예산·성공 기준",
                               f"· 테스트 예산: **100만~300만원 / 2~4주** "
                               f"(작게 시작해 이긴 소재만 확대)\n"
                               f"· 목표 CPL: **{base[1]:,.0f}원 이하** "
                               f"(최고 성과 {base[0]:,.0f}원)\n"
                               f"· 중단 기준: CPL **{base[2]:,.0f}원 초과** 시 즉시 중단·재검토"))
            # 6) 주의
            _cau = ["과장·단정 표현(수익 보장 등)은 쓰지 않습니다 — 광고 심의·신뢰 문제",
                    "한 번에 하나만 바꿔서 테스트하세요(후킹·형식·타깃 동시 변경 시 원인 불명)"]
            if b['bottleneck'] and b['bottleneck']['rate'] > 0.5:
                _cau.append(f"이 강의는 {b['bottleneck']['from']}→{b['bottleneck']['to']} "
                            f"전환이 {b['bottleneck']['rate']:.0f}%로 낮습니다 — "
                            "모객을 늘려도 뒤에서 새므로 후속 안내도 함께 준비하세요")
            _parts.append(("⑥ 주의", "\n".join("· " + c for c in _cau)))

            for _t, _v in _parts:
                st.markdown(f"**{_t}**")
                st.markdown(
                    f'<div style="font-size:13px;line-height:1.75;white-space:pre-wrap;'
                    f'opacity:.9;margin-bottom:10px">{_md_bold(_v)}</div>',
                    unsafe_allow_html=True)

            _copy = f"[{_bp} 소재 브리프]\n" + "\n\n".join(
                f"{t}\n{v}".replace('**', '') for t, v in _parts)
            with st.expander("📋 텍스트로 복사하기 (디자이너·외주 전달용)"):
                st.code(_copy, language=None)

        # ── 🧭 확장 주제 — 강의 밖에서 찾는 새 각도 ──────────
        # 키워드툴에 직접 추가한 주제(건강운·재테크 등). 어느 상품군에 붙일지가
        # 명확하지 않아(건강운=사주+타로, 재테크=부동산+빌딩+사주 재물운) 위
        # 브리프에는 섞지 않고 따로 보여준다 — 잘못 귀속시키면 그 강의의 신호가
        # 다른 의도로 모은 데이터에 오염된다.
        _sx = load_market_signals()
        if not _sx.empty:
            _sx = _sx[_sx['signal'].astype(str).str.startswith('ext_')]
        if not _sx.empty:
            st.divider()
            st.markdown("#### 🧭 확장 주제 — 강의 밖에서 찾는 새 각도")
            st.caption("키워드 분석툴에 직접 추가한 탐색 주제입니다. 특정 강의에 속하지 "
                       "않아 위 브리프와 분리했습니다. 기존 후킹이 식었을 때 새 각도를 "
                       "찾거나, 신규 강의 주제를 가늠할 때 보세요. "
                       "주제 추가·삭제는 키워드 분석툴에서 하면 다음 갱신에 반영됩니다.")
            for _tp in _sx['product'].unique():
                _g = _sx[_sx['product'] == _tp]
                _gm = _g[_g['signal'] == 'ext_market_top'].sort_values(
                    'metric1', ascending=False)
                _ga = _g[_g['signal'] == 'ext_age'].sort_values(
                    'metric1', ascending=False)
                with st.expander(f"**{_tp}** — 시장 상위 영상 {len(_gm)}건"
                                 + (f" · 관심 급증 연령 {len(_ga)}건" if len(_ga) else "")):
                    if not _gm.empty:
                        _t = "".join(
                            f"- {r['text']}  ({int(r['metric1']):,}회 · {r['metric2']})\n"
                            for _, r in _gm.head(6).iterrows())
                        st.markdown("**지금 이 주제에서 잘 되는 영상**\n\n" + _t)
                    if not _ga.empty:
                        st.markdown("**관심이 빠르게 느는 연령** (주 검색층이 아니라 증가 신호)\n\n"
                                    + "".join(f"- {r['text']} → {r['metric2']}\n"
                                              for _, r in _ga.head(4).iterrows()))
                    st.caption("이 제목들이 우리 강의 후킹으로 바꿔 쓸 만한지 보세요 — "
                               "그대로 베끼지 말고 같은 약속·다른 표현으로 변주합니다.")

    tab_new_placeholder = None

    # ── 새 실험 등록 ────────────────────────────────────
    with tab_new:
        st.markdown("**실행 전에 가설부터 적습니다.** 왜 될 거라고 보는지 먼저 쓰면, "
                    "결과가 나왔을 때 무엇을 배웠는지가 분명해집니다.")
        pb = _course_playbook()
        _prods = [b['product'] for b in pb] or ['사주', '타로', '부동산', '빌딩']
        with st.form("exp_new"):
            c1, c2 = st.columns(2)
            with c1:
                e_prod = st.selectbox("강의", _prods)
                e_hook = st.text_input("후킹·소재",
                                       placeholder="예) 재물운 투자법 — 영상 A안")
                e_ch = st.selectbox("채널", ["메타", "인스타", "유튜브", "카카오",
                                             "틱톡", "문자", "오가닉", "기타"])
            with c2:
                e_start = st.date_input("시작일", value=date.today())
                e_end = st.date_input("종료(예정)일", value=date.today() + timedelta(days=14))
                e_budget = st.number_input("예산(원)", min_value=0, step=100000, value=1000000)
            # 선택한 강의의 검증된 후킹을 힌트로
            _hint = next((b for b in pb if b['product'] == e_prod), None)
            if _hint and _hint.get('hooks'):
                _h = _hint['hooks'][0]
                _v = max(_hint['hooks'], key=lambda x: x['signups'])
                st.caption(f"💡 {e_prod} 참고 — 모객 1위 **{_v['topic']}**"
                           f"({_v['signups']:,}명·전환 {_v['conv']:.1f}%) · "
                           f"전환 1위 **{_h['topic']}**({_h['conv']:.1f}%)")
            e_hyp = st.text_area(
                "가설 — 왜 될 거라고 보는가",
                placeholder="예) 타로는 ROAS 17.4배인데 광고비 비중이 5%뿐이다. "
                            "예산을 2배로 늘려도 CPL이 기준선(14,000원) 아래로 유지될 것이다.",
                height=90)
            if st.form_submit_button("실험 등록", type="primary"):
                if not e_hook.strip() or not e_hyp.strip():
                    st.error("후킹·소재와 가설은 반드시 적어주세요. 가설 없는 실험은 "
                             "결과가 나와도 배울 게 없습니다.")
                else:
                    _eid = f"{e_start}-{e_prod}-{str(abs(hash(e_hook)))[:4]}"
                    save_experiment({
                        'id': _eid, 'created': str(date.today()),
                        'start': str(e_start), 'end': str(e_end),
                        'product': e_prod, 'hook': e_hook.strip(), 'channel': e_ch,
                        'hypothesis': e_hyp.strip(), 'budget': int(e_budget),
                        'status': '진행중', 'leads': 0, 'conversions': 0,
                        'revenue': 0, 'learning': ''})
                    st.success(f"등록 완료 — {e_prod} · {e_hook}")
                    st.rerun()

    # ── 결과 입력 ───────────────────────────────────────
    with tab_run:
        _open = exps[exps['status'] == '진행중'] if not exps.empty else pd.DataFrame()
        if _open.empty:
            st.info("진행 중인 실험이 없습니다. '➕ 새 실험 등록'에서 시작하세요.")
        else:
            _pick = st.selectbox(
                "실험 선택", _open['id'].tolist(),
                format_func=lambda i: (
                    f"{_open.loc[_open['id'] == i, 'product'].iloc[0]} · "
                    f"{_open.loc[_open['id'] == i, 'hook'].iloc[0]} "
                    f"({_open.loc[_open['id'] == i, 'start'].iloc[0]})"))
            _row = _open[_open['id'] == _pick].iloc[0]
            st.caption(f"📌 가설 — {_row['hypothesis']}")
            with st.form("exp_result"):
                r1, r2, r3 = st.columns(3)
                with r1:
                    r_leads = st.number_input("확보 리드(무료 신청)", min_value=0, step=1,
                                              value=int(_row['leads']))
                with r2:
                    r_conv = st.number_input("유료 전환(건)", min_value=0, step=1,
                                             value=int(_row['conversions']))
                with r3:
                    r_rev = st.number_input("매출(원)", min_value=0, step=100000,
                                            value=int(_row['revenue']))
                r_learn = st.text_area(
                    "배운 점 — 가설이 맞았나? 다음엔 무엇을 바꿀 것인가",
                    value=str(_row['learning'] or ''), height=90,
                    placeholder="예) CPL은 기준선 아래였지만 전환이 낮았다. "
                                "리드는 싸게 왔으나 관심도가 낮은 타깃 — 다음엔 관심사 좁히기")
                r_done = st.checkbox("이 실험 완료 처리")
                if st.form_submit_button("결과 저장", type="primary"):
                    save_experiment({
                        'id': _row['id'], 'created': _row['created'],
                        'start': _row['start'], 'end': _row['end'],
                        'product': _row['product'], 'hook': _row['hook'],
                        'channel': _row['channel'], 'hypothesis': _row['hypothesis'],
                        'budget': int(_row['budget']),
                        'status': '완료' if r_done else '진행중',
                        'leads': int(r_leads), 'conversions': int(r_conv),
                        'revenue': int(r_rev), 'learning': r_learn.strip()})
                    st.success("저장했습니다.")
                    st.rerun()

            # 즉시 판정
            if int(_row['leads']) > 0 and base:
                _cpl = int(_row['budget']) / int(_row['leads'])
                if _cpl <= base[0]:
                    st.success(f"🟢 CPL **{_cpl:,.0f}원** — 기존 최저({base[0]:,.0f}원)보다도 "
                               "저렴합니다. **확대 검토** 대상입니다.")
                elif _cpl <= base[1]:
                    st.success(f"🟢 CPL **{_cpl:,.0f}원** — 평균({base[1]:,.0f}원)보다 "
                               "좋습니다. 유지·소폭 확대하세요.")
                elif _cpl <= base[2]:
                    st.warning(f"🟡 CPL **{_cpl:,.0f}원** — 평균({base[1]:,.0f}원)보다 "
                               "비쌉니다. 소재를 바꿔 다시 시도해 보세요.")
                else:
                    st.error(f"🔴 CPL **{_cpl:,.0f}원** — 기존 최고({base[2]:,.0f}원)보다 "
                             "비쌉니다. **중단하고 후킹부터 재검토**하세요.")

    # ── 실험 기록 ───────────────────────────────────────
    with tab_log:
        if exps.empty:
            st.info("아직 기록된 실험이 없습니다.")
        else:
            for _, e in exps.iterrows():
                _ic = "✅" if e['status'] == '완료' else "🔄"
                with st.expander(
                        f"{_ic} {e['product']} · {e['hook']} "
                        f"({e['start']} ~ {e['end']}) · 예산 {int(e['budget'])/1e4:,.0f}만원"):
                    st.markdown(f"**가설** — {e['hypothesis']}")
                    if int(e['leads']) > 0:
                        m1, m2, m3, m4 = st.columns(4)
                        m1.metric("리드", f"{int(e['leads']):,}건")
                        m2.metric("CPL", f"{e['cpl']:,.0f}원")
                        m3.metric("전환", f"{int(e['conversions']):,}건",
                                  f"{e['cvr']:.1f}%")
                        m4.metric("ROAS", f"{e['roas']:.1f}배" if e['roas'] else "—")
                    else:
                        st.caption("결과 미입력 — '📝 결과 입력'에서 채워주세요.")
                    if str(e['learning'] or '').strip():
                        st.success(f"📚 **배운 점** — {e['learning']}")
                    if st.button("삭제", key=f"exp_del_{e['id']}"):
                        delete_experiment(e['id'])
                        st.rerun()

            _learned = exps[exps['learning'].astype(str).str.len() > 1]
            if not _learned.empty:
                st.divider()
                st.markdown("#### 📋 대표님 보고용 요약")
                _txt = "\n".join(
                    f"{i+1}. [{e['product']}] {e['hook']} — 예산 "
                    f"{int(e['budget'])/1e4:,.0f}만원 · 리드 {int(e['leads']):,}건"
                    f"(CPL {e['cpl']:,.0f}원) · 전환 {int(e['conversions']):,}건"
                    f"\n   배운 점: {e['learning']}"
                    for i, (_, e) in enumerate(_learned.iterrows()))
                st.code(_txt, language=None)
                st.caption("복사해서 보고에 그대로 쓰실 수 있습니다. "
                           "**무엇을 했고 → 결과가 어땠고 → 무엇을 배웠는지**의 형식이 "
                           "초보 마케터의 신뢰를 만듭니다.")


def _course_playbook() -> list:
    """강의별 모객 전략 플레이북 — 각 강의를 '어떤 후킹으로·언제·얼마에' 모을지.

    상품군마다 후킹 효율·시기(오행)·광고 효율·전환 병목이 다르므로,
    전 상품 공통 전략이 아니라 **강의별 실행안**을 데이터에서 생성한다.
    """
    cs = load_course_summary()
    camp = load_campaign_adspend()
    wcv = load_webinar_conversion()
    oh = load_ohaeng_period()
    stage = load_cohort_stage()
    nb = load_cust_product_nextbuy()
    xs = load_cust_crosssell_path()
    if cs.empty:
        return []

    roas, adspend, adshare = {}, {}, {}
    if not camp.empty and {'product', 'ad_spend', 'live_revenue'} <= set(camp.columns):
        k = camp.groupby('product').agg(ad=('ad_spend', 'sum'), rev=('live_revenue', 'sum'))
        _t = k['ad'].sum()
        for p, r in k.iterrows():
            if r['ad'] > 0:
                roas[p] = r['rev'] / r['ad']
                adspend[p] = float(r['ad'])
                adshare[p] = r['ad'] / _t * 100

    _stage_cols = [s for s in STAGE_ORDER if not stage.empty and s in stage.columns]
    books = []
    for _, r in cs.sort_values('revenue', ascending=False).iterrows():
        p = r['product']
        cv = (r['students'] / r['free'] * 100) if r['free'] else 0
        aov = (r['revenue'] / r['students']) if r['students'] else 0
        b = {'product': p, 'rev': float(r['revenue']), 'free': int(r['free']),
             'students': int(r['students']), 'cv': cv, 'aov': aov,
             'roas': roas.get(p), 'adshare': adshare.get(p), 'adspend': adspend.get(p)}

        # ① 후킹 — 이 강의에서 검증된 문구
        b['hooks'] = []
        if not wcv.empty:
            w = wcv[wcv['product'] == p]
            if not w.empty:
                b['hooks'] = [{
                    'topic': h['topic'], 'signups': int(h['unique_signups']),
                    'conv': float(h['conv_rate']),
                    'self_share': float(h.get('self_share', 0) or 0),
                } for _, h in w.sort_values('conv_rate', ascending=False).iterrows()]

        # ② 시기 — 이 강의가 잘 모이는/잘 팔리는 오행월
        b['season'] = None
        if not oh.empty:
            o = oh[oh['product'] == p]
            if len(o) >= 6:
                gb = o.groupby('branch_element').agg(
                    n=('saju_month', 'size'), f=('free_signups', 'sum'),
                    pd_=('paid_orders', 'sum'))
                gb = gb[gb['n'] >= 2]
                if not gb.empty and gb['f'].sum() > 0:
                    gb['avg'] = gb['f'] / gb['n']
                    gb['cv'] = (gb['pd_'] / gb['f'] * 100).where(gb['f'] > 0, 0)
                    b['season'] = {'vol': gb['avg'].idxmax(), 'vol_n': float(gb['avg'].max()),
                                   'cv': gb['cv'].idxmax(), 'cv_v': float(gb['cv'].max()),
                                   'months': int(gb['n'].sum())}

        # ③ 전환 병목 — 이 강의의 단계 이탈
        b['bottleneck'] = None
        if not stage.empty and _stage_cols:
            g = stage[stage['product'] == p]
            if not g.empty:
                t = g[_stage_cols].fillna(0).sum()
                worst = None
                for i in range(len(_stage_cols) - 1):
                    a_, b_ = t[_stage_cols[i]], t[_stage_cols[i + 1]]
                    if a_ >= 50:
                        rate = b_ / a_ * 100 if a_ else 0
                        if worst is None or (a_ - b_) > worst['lost']:
                            worst = {'from': _stage_cols[i], 'to': _stage_cols[i + 1],
                                     'rate': rate, 'lost': float(a_ - b_), 'base': float(a_)}
                b['bottleneck'] = worst

        # ④ 교차판매 — 이 강의 첫 구매자가 다음에 가는 강의 + 재구매 성향
        b['nextbuy'] = None
        if not xs.empty and {'home', 'dest', 'customers', 'pct'} <= set(xs.columns):
            x2 = xs[xs['home'] == p].sort_values('customers', ascending=False)
            if not x2.empty:
                b['nextbuy'] = {'to': x2.iloc[0]['dest'],
                                'n': int(x2.iloc[0]['customers']),
                                'pct': float(x2.iloc[0]['pct'])}
        b['repeat'] = None
        if not nb.empty and {'product', 'repeat_rate', 'diff_pct'} <= set(nb.columns):
            n2 = nb[nb['product'] == p]
            if not n2.empty:
                b['repeat'] = {'rate': float(n2.iloc[0]['repeat_rate']),
                               'diff': float(n2.iloc[0]['diff_pct'])}
        books.append(b)
    return books


def _md_bold(s) -> str:
    """마크다운 **굵게**를 <b>로 변환 (st.markdown HTML 렌더용)."""
    _p = str(s).split('**')
    return ''.join(x if i % 2 == 0 else f'<b>{x}</b>' for i, x in enumerate(_p))


def _strategy_conclusion() -> dict:
    """모든 분석을 종합한 **최종 전략 결론** — 근거 → 방향 → 목표.

    전략 브리핑(단발 액션)과 달리, 상품 포트폴리오 역할·예산 재배분·단계
    병목·시기 전략을 하나의 결론으로 엮고 **정량 목표까지 계산**한다.
    모든 수치는 실데이터에서 산출되므로 데이터가 갱신되면 결론도 갱신된다.
    """
    cs = load_course_summary()
    camp = load_campaign_adspend()
    stage = load_cohort_stage()
    wcv = load_webinar_conversion()
    oh = load_ohaeng_period()
    out = {'portfolio': [], 'strategies': [], 'targets': [], 'caveats': []}
    if cs.empty:
        return out

    # ── 상품 포트폴리오: 전환율·객단가·광고 ROAS로 역할 규정 ──────
    c = cs.copy()
    c['cv'] = (c['students'] / c['free'].replace(0, float('nan')) * 100)
    c['aov'] = (c['revenue'] / c['students'].replace(0, float('nan')))
    roas, adshare, adspend = {}, {}, {}
    if not camp.empty and {'product', 'ad_spend', 'live_revenue'} <= set(camp.columns):
        k = camp.groupby('product').agg(ad=('ad_spend', 'sum'), rev=('live_revenue', 'sum'))
        _tot_ad = k['ad'].sum()
        for p, r in k.iterrows():
            if r['ad'] > 0:
                roas[p] = r['rev'] / r['ad']
                adshare[p] = r['ad'] / _tot_ad * 100
                adspend[p] = r['ad']

    _med_cv = c['cv'].median()
    _med_aov = c['aov'].median()
    for _, r in c.sort_values('revenue', ascending=False).iterrows():
        p = r['product']
        _ro = roas.get(p)
        hi_cv, hi_aov = r['cv'] >= _med_cv, r['aov'] >= _med_aov
        if hi_cv and hi_aov:
            role, act = "⭐ 성장 엔진", "예산·인력 최우선 배분"
        elif hi_cv:
            role, act = "🚀 효율 확장", "광고비 확대로 규모를 키울 구간"
        elif hi_aov:
            role, act = "💎 프리미엄", "고단가 유지·업셀 설계"
        else:
            role, act = "🔧 재점검", "전환 구조 개선 후 재투자"
        out['portfolio'].append({
            'product': p, 'role': role, 'action': act,
            'rev': float(r['revenue']), 'free': int(r['free']),
            'students': int(r['students']), 'cv': float(r['cv']),
            'aov': float(r['aov']), 'roas': _ro,
            'adshare': adshare.get(p),
        })

    # ── 전략 1: 광고 예산 재배분 (ROAS 격차의 기회비용 정량화) ────
    if len(roas) >= 2:
        _hi = max(roas, key=roas.get)
        _lo = min(roas, key=roas.get)
        _hi_sh, _lo_sh = adshare.get(_hi, 0), adshare.get(_lo, 0)
        _shift = adspend.get(_lo, 0) * 0.15          # 저효율에서 15%만 이동(보수적)
        _decay = 0.5                                  # 확대 시 효율 절반으로 가정(수확체감)
        _gain = _shift * (roas[_hi] * _decay - roas[_lo])
        if _gain > 0:
            out['strategies'].append({
                'no': 1, 'title': f"광고 예산을 {_hi}로 재배분",
                'why': (f"광고 ROAS가 **{_hi} {roas[_hi]:.1f}배 vs {_lo} {roas[_lo]:.1f}배**로 "
                        f"**{roas[_hi]/roas[_lo]:.1f}배** 차이인데, 예산은 반대로 "
                        f"{_lo}에 **{_lo_sh:.0f}%**, {_hi}에 **{_hi_sh:.0f}%**만 쓰고 있습니다."),
                'how': (f"{_lo} 광고비의 **15%({_shift/1e4:,.0f}만원)** 만 {_hi}로 이동. "
                        f"소액부터 2~4주 단위로 옮기며 ROAS를 확인하고, 효율이 유지되면 단계적 확대."),
                'effect': (f"{_hi} 확대 시 효율이 **절반으로 떨어진다고 보수적으로 가정해도** "
                           f"추가 매출 **약 {_gain/1e8:.2f}억** (같은 예산, 배분만 변경)."),
            })

    # ── 전략 2: 단계 전환 병목 (가장 크게 새는 구간) ─────────────
    if not stage.empty:
        _cols = [s for s in STAGE_ORDER if s in stage.columns]
        _bott = None
        for p, g in stage.groupby('product'):
            t = g[_cols].fillna(0).sum()
            for i in range(len(_cols) - 1):
                a, b = t[_cols[i]], t[_cols[i + 1]]
                if a >= 100 and b >= 0:
                    rate = b / a * 100 if a else 0
                    lost = a - b
                    if _bott is None or lost > _bott['lost']:
                        _bott = {'p': p, 'f': _cols[i], 't': _cols[i + 1],
                                 'rate': rate, 'lost': lost, 'a': a, 'b': b}
        if _bott:
            _aov = float(c.loc[c['product'] == _bott['p'], 'aov'].iloc[0]) \
                if (c['product'] == _bott['p']).any() else 0
            _uplift = _bott['a'] * 0.10          # 전환율 +10%p 개선 시
            out['strategies'].append({
                'no': 2, 'title': f"{_bott['p']} {_bott['f']}→{_bott['t']} 이탈 막기",
                'why': (f"**{_bott['p']}**의 **{_bott['f']}→{_bott['t']}** 전환이 "
                        f"**{_bott['rate']:.1f}%**로, 이 구간에서만 **{int(_bott['lost']):,}명**이 "
                        f"이탈합니다({int(_bott['a']):,}명 중 {int(_bott['b']):,}명만 진급). "
                        "이미 유료로 돈을 낸 고객이라 **신규 모객보다 훨씬 싸게 잡을 수 있는 매출**입니다."),
                'how': (f"{_bott['f']} 수료 시점에 {_bott['t']} 안내를 자동화(수료 직후 3일 내 "
                        "혜택 마감형 오퍼), 수료생 후기·성과 사례 배포, 중도 이탈자 리마케팅. "
                        "기수 병합·이월로 다음 기수까지 텀이 길어지는 구간은 대기 기간 콘텐츠로 연결."),
                'effect': (f"전환율 **+10%p**만 올려도 추가 수강생 **약 {_uplift:,.0f}명** · "
                           f"객단가 {_aov/1e4:,.0f}만원 기준 **약 {_uplift*_aov/1e8:.2f}억**."),
            })

    # ── 전략 3: 후킹 — 볼륨자석 vs 알짜의 역할 분리 ──────────────
    if not wcv.empty and {'unique_signups', 'conv_rate'} <= set(wcv.columns):
        w = wcv.copy()
        _vol = w.loc[w['unique_signups'].idxmax()]
        _qual = w.loc[w['conv_rate'].idxmax()]
        if _vol['topic'] != _qual['topic']:
            out['strategies'].append({
                'no': 3, 'title': "모객용 후킹과 전환용 후킹을 나눠 쓰기",
                'why': (f"가장 많이 모으는 **{_vol['product']} {_vol['topic']}**은 "
                        f"{int(_vol['unique_signups']):,}명을 모으지만 전환율은 "
                        f"**{_vol['conv_rate']:.1f}%**입니다. 반대로 **{_qual['product']} "
                        f"{_qual['topic']}**은 {int(_qual['unique_signups']):,}명으로 적게 모아도 "
                        f"전환율 **{_qual['conv_rate']:.1f}%**로 "
                        f"**{_qual['conv_rate']/max(_vol['conv_rate'],0.1):.1f}배**입니다."),
                'how': ("① 대형 후킹은 **리드 확보용**으로 계속 쓰되, 유입 후 곧바로 팔지 말고 "
                        "고관여 콘텐츠로 데우는 CRM을 붙입니다. ② 고전환 후킹은 **마감·재구매 "
                        "캠페인**에 집중 배치합니다. ③ 같은 상품이라도 후킹 문구에 따라 전환이 "
                        "크게 갈리므로, 검증된 문구를 광고·랜딩에 우선 적용합니다."),
                'effect': (f"대형 후킹 전환율이 **{_vol['conv_rate']:.1f}% → "
                           f"{_vol['conv_rate']+2:.1f}%** (+2%p)만 돼도 추가 전환 "
                           f"**약 {_vol['unique_signups']*0.02:,.0f}명**."),
            })

    # ── 전략 4: 시기 전략 (오행 — 모객기 vs 전환기) ──────────────
    if not oh.empty and len(oh) >= 8:
        b = oh.groupby('branch_element').agg(n=('saju_month', 'size'),
                                             free=('free_signups', 'sum'),
                                             paid=('paid_orders', 'sum'))
        b['avg'] = b['free'] / b['n']
        b['cv'] = (b['paid'] / b['free'] * 100).where(b['free'] > 0, 0)
        _mo, _cvb = b['avg'].idxmax(), b['cv'].idxmax()
        if _mo != _cvb:
            out['strategies'].append({
                'no': 4, 'title': "모객기와 전환기를 시기로 나누기",
                'why': (f"명리월 기준으로 모객이 가장 많은 시기는 **{_mo}"
                        f"({ganji.ELEMENT_HANJA.get(_mo,'')})월(월평균 {b.loc[_mo,'avg']:,.0f}명)**, "
                        f"전환율이 가장 높은 시기는 **{_cvb}({ganji.ELEMENT_HANJA.get(_cvb,'')})월"
                        f"({b.loc[_cvb,'cv']:.2f}%)**로 서로 다릅니다."),
                'how': (f"{_mo}월에는 **광고비를 실어 리드를 최대한 확보**하고, "
                        f"{_cvb}월에는 **개강·마감·업셀 캠페인**을 배치해 쌓인 리드를 전환시킵니다. "
                        "개강 일정을 잡을 때 이 리듬을 참고하세요."),
                'effect': "같은 예산으로 리드는 싸게, 전환은 비싸게 파는 구조를 만듭니다.",
            })

    # ── 정량 목표 ────────────────────────────────────────────
    _tot_rev = float(c['revenue'].sum())
    _tot_free = int(c['free'].sum())
    _tot_std = int(c['students'].sum())
    _cur_cv = _tot_std / _tot_free * 100 if _tot_free else 0
    out['targets'].append({
        'kpi': "전사 무료→유료 전환율", 'now': f"{_cur_cv:.2f}%",
        'goal': f"{_cur_cv+1:.2f}%",
        'basis': (f"현재 {_tot_free:,}명 모객 → {_tot_std:,}명 수강. "
                  f"+1%p면 같은 모객으로 수강생 **약 {_tot_free*0.01:,.0f}명** 추가")})
    if roas:
        _hi = max(roas, key=roas.get)
        out['targets'].append({
            'kpi': f"{_hi} 광고비 비중", 'now': f"{adshare.get(_hi,0):.0f}%",
            'goal': f"{min(adshare.get(_hi,0)*2, 30):.0f}%",
            'basis': f"ROAS {roas[_hi]:.1f}배로 최고인데 예산 비중이 가장 낮음 — 단계적 2배"})
    if not c.empty:
        _best_aov = c.loc[c['aov'].idxmax()]
        out['targets'].append({
            'kpi': "객단가(전 상품 평균)", 'now': f"{_tot_rev/_tot_std/1e4:,.0f}만원",
            'goal': f"{_tot_rev/_tot_std/1e4*1.1:,.0f}만원",
            'basis': (f"최고 객단가 {_best_aov['product']} {_best_aov['aov']/1e4:,.0f}만원의 "
                      "패키지 구성을 타 상품에 이식 — +10%")})

    out['caveats'] = [
        "수치는 누적 실적 기반 추정입니다. 예산 이동은 **소액·단기간으로 시험한 뒤** 확대하세요.",
        "광고 확대 시 **수확체감**(광고비↑ → ROAS↓)이 관측되므로 위 기대효과는 효율 하락을 "
        "반영해 보수적으로 계산했습니다.",
        "시기(오행) 전략은 표본이 22개 명리월로 작고 개강 일정과 겹쳐 있어 **참고용**입니다.",
    ]
    return out


def _strategy_briefing() -> list:
    """모든 분석 데이터를 종합해 우선순위 전략 액션을 생성(데이터 기반·자동 갱신)."""
    cs = load_course_summary()
    camp = load_campaign_adspend()
    region = load_region_signups()
    perf = load_monthly_performance()
    ad_m = load_ad_spend_monthly()
    items = []  # (아이콘, 제목, 본문)

    # 1) 전체 광고 효율 (누적 ROAS)
    if not perf.empty and not ad_m.empty:
        _am = set(ad_m['month'].astype(str))
        _rev = int(perf[perf['month'].astype(str).isin(_am)]['revenue'].sum())
        _sp = int(ad_m['spend'].sum())
        if _sp > 0:
            items.append(("📈", "전체 광고 효율",
                          f"광고비 집행 기간 누적 **ROAS {_rev/_sp:.1f}배** "
                          f"(매출 {_rev/1e8:.1f}억 ÷ 광고비 {_sp/1e8:.1f}억). "
                          "업계 목표(2배)를 크게 상회 — 광고 확대 자체는 안전한 구간입니다."))

    # 2) 상품군 광고 예산 재배분 (수확체감 반영)
    _bd = _ad_budget_diagnosis(camp)
    if _bd:
        _exp = [b for b in _bd if b['rec'] in ('확대', '유지·소폭 확대')]
        _cut = [b for b in _bd if b['rec'] == '축소·재점검']
        _best = max(_bd, key=lambda x: x['roas'])
        _msg = (f"**{_best['product']}** 광고 ROAS **{_best['roas']:.1f}배**로 최고"
                f"(비중 {_best['share']:.0f}%) → **확대 1순위**. ")
        if _cut:
            _cn = " · ".join(b['product'] for b in _cut)
            _msg += (f"반면 **{_cn}**은 광고비를 늘려도 효율이 떨어지는 **수확체감** 구간이라 "
                     "무리한 확대보다 **적정 규모로 축소·재점검**이 맞습니다. ")
        _msg += "‘많이 쓸수록 좋다’가 아니라 상품별 적정 예산을 찾는 게 핵심입니다."
        items.append(("💰", "광고 예산 재배분", _msg))

    # 3) 전환 강점 상품 + 고객단가 (매출 기준과 정합: students 사용)
    if not cs.empty:
        cc = cs.copy()
        cc['cv'] = cc['students'] / cc['free'].replace(0, float('nan'))
        cc = cc.dropna(subset=['cv'])
        if not cc.empty:
            _bv = cc.loc[cc['cv'].idxmax()]
            items.append(("🎯", "전환 강점 상품",
                          f"**{_bv['product']}** 무료→유료 전환 **{_bv['cv']*100:.1f}%**로 최고 → "
                          "무료 모객을 늘릴수록 유료 성과가 가장 잘 따라오는 상품입니다."))
        c2 = cs.copy()
        c2['aov'] = c2['revenue'] / c2['students'].replace(0, float('nan'))
        c2 = c2.dropna(subset=['aov'])
        if not c2.empty:
            _hp = c2.loc[c2['aov'].idxmax()]
            items.append(("💎", "고객단가 상품",
                          f"**{_hp['product']}** 객단가 **{_hp['aov']/1e4:,.0f}만원**로 최고 → "
                          "고가 패키지·업셀 여력이 큰 프리미엄 라인입니다."))

    # 4) 지역 광고 집중
    if not region.empty:
        _tot = int(region['signups'].sum())
        _cap = int(region[region['region'].isin(CAPITAL_REGIONS)]['signups'].sum())
        _loc = region[~region['region'].isin(CAPITAL_REGIONS)].sort_values('signups', ascending=False)
        _tl = _loc.iloc[0]['region'] if not _loc.empty else '—'
        if _tot:
            items.append(("📍", "지역 광고 집중",
                          f"수도권 집중도 **{_cap/_tot*100:.0f}%**(서울·경기·인천). 광고 예산을 "
                          f"수도권에 우선 배정하고, 비수도권은 **{_tl}** 등 영남권을 보조 타깃으로 운영하세요. "
                          f"※ 배송지 리포트 {_asof_tag('지역 분포')}."))

    # 5) 재구매·LTV (고객 자산)
    _mnr = load_cust_monthly_new_repeat()
    _pr = load_cust_product_repeat()
    if not _mnr.empty:
        _nr = int(_mnr['new_revenue'].sum())
        _rr = int(_mnr['repeat_revenue'].sum())
        _share = _rr / (_nr + _rr) * 100 if (_nr + _rr) else 0
        _extra = ""
        if not _pr.empty:
            _hr = _pr.loc[_pr['repeat_rate'].idxmax()]
            _extra = f" 재구매율은 **{_hr['product']}({_hr['repeat_rate']:.0f}%)**가 최고."
        if _share >= 35:
            items.append(("🔁", "재구매·LTV 강화",
                          f"재구매 매출이 전체의 **{_share:.0f}%** — 신규 유치만큼 **기존 고객 업셀·"
                          f"CRM**이 매출 핵심입니다.{_extra} 상위 과정 라인업과 재구매 유도에 투자하세요."))
    return items


def tab_marketing():
    st.header("📢 마케팅 분석")

    # ══ 종합 전략 브리핑 (모든 분석 종합·데이터 자동 반영) ═══════════
    _brief = _strategy_briefing()
    if _brief:
        with st.container(border=True):
            st.markdown("### 🧭 종합 전략 브리핑")
            st.caption("광고 ROI·전환·객단가·지역 분석을 종합한 **데이터 기반 액션 요약**. "
                       "데이터가 갱신되면 문구도 자동으로 바뀝니다.")
            for _icon, _title, _body in _brief:
                st.markdown(f"- **{_icon} {_title}** — {_body}")
        st.divider()

    # ══ 전 기간 성과 추이 (주문 명단 집계) ══════════════════════
    perf = load_monthly_performance()
    ad_m = load_ad_spend_monthly()
    if not perf.empty:
        st.subheader("📈 전 기간 성과 추이")
        st.caption(f"주문 데이터 기반 월별 성과 ({ganji.ym_label(perf['month'].min(), with_ganji=False)} ~ "
                   f"{ganji.ym_label(perf['month'].max(), with_ganji=False)}, "
                   f"{len(perf)}개월). 개인정보 없는 집계.")
        _done_ov = set(complete_months(perf)['month'].astype(str))
        _part_ov = [m for m in perf['month'].astype(str) if m not in _done_ov]
        if _part_ov:
            _ao_ov = order_asof()
            st.caption(f"⚠️ 마지막 막대 **{ganji.ym_label(_part_ov[-1], with_ganji=False)}**은 "
                       + (f"주문 명단이 **{_ao_ov}까지**만 담긴 부분 집계입니다 — "
                          if _ao_ov else "아직 집계 중입니다 — ")
                       + "낮아 보이는 건 실적 하락이 아니라 **덜 담긴 데이터**입니다.")
        _tot_rev = int(perf['revenue'].sum())
        _tot_free = int(perf['free_signups'].sum())
        _tot_paid = int(perf['paid_orders'].sum())
        _tot_spend_m = int(ad_m['spend'].sum()) if not ad_m.empty else 0
        # ROAS는 광고비가 집행된 달의 매출로만 계산(기간 정합)
        if not ad_m.empty:
            _ad_months = set(ad_m['month'].astype(str))
            _rev_ad = int(perf[perf['month'].astype(str).isin(_ad_months)]['revenue'].sum())
        else:
            _rev_ad = 0
        if _tot_spend_m > 0:
            _m4 = ("📈 누적 ROAS", f"{_rev_ad/_tot_spend_m:,.1f}<small>배</small>",
                   f"매출 {_rev_ad/1e8:,.1f}억 ÷ 광고비 {_tot_spend_m/1e8:,.1f}억")
        else:
            _m4 = ("🔄 평균 전환율",
                   (f"{_tot_paid/_tot_free*100:.2f}<small>%</small>" if _tot_free else "—"),
                   "유료 ÷ 무료")
        _kpi_band([
            ("💰 누적 매출", f"{_tot_rev/1e8:,.1f}<small>억원</small>", "주문 기준"),
            ("🆓 누적 무료 신청", f"{_tot_free:,}", "무료 신청 건"),
            ("🎓 누적 유료 구매", f"{_tot_paid:,}<small>건</small>", "유료 결제"),
            _m4,
        ])
        st.write("")

        _camps_ov = load_campaigns()
        fig_m = monthly_perf_chart(perf, ad_m if not ad_m.empty else None,
                                   campaigns_df=_camps_ov if not _camps_ov.empty else None)
        if fig_m:
            st.plotly_chart(fig_m, key="mkt_monthly")
            st.caption("🎓 세로 점선 = 강의 모객 시작월 (개강 캠페인이 매출·유입에 미친 영향 확인용)")

        # 월별 광고비 입력
        # 선택지를 주문 집계(perf)의 월로만 만들면, 주문 명단이 밀린 동안에는
        # '이번 달'이 목록에 아예 없어 지금 집행 중인 광고비를 넣을 방법이 사라진다.
        # 광고비는 주문과 무관하게 매달 나가므로 최근 12개월을 항상 함께 제공한다.
        _this_m_str = date.today().strftime('%Y-%m')
        _missing_this = _this_m_str not in set(ad_m['month'].astype(str)) if not ad_m.empty else True
        with st.expander("✏️ 월별 광고비 입력 — ROAS·CPA 산출용",
                         expanded=(ad_m.empty or _missing_this)):
            st.caption("광고 플랫폼(메타·구글 등)의 **월별 지출 총액**만 넣으면 전 기간 ROAS가 계산됩니다. "
                       "채널을 나눠 넣어도 됩니다.")
            if _missing_this and not ad_m.empty:
                st.warning(f"⚠️ {ganji.ym_label(_this_m_str, with_ganji=False)} 광고비가 아직 없습니다 — "
                           "이번 달 ROAS·CPL 판정과 예산 조언이 지난달 기준으로 남습니다.")
            _recent12 = [str(p) for p in pd.period_range(
                end=pd.Timestamp(date.today()).to_period('M'), periods=12, freq='M')]
            _months = sorted(set(perf['month'].astype(str)) | set(_recent12))
            with st.form("ad_spend_form"):
                ac1, ac2, ac3 = st.columns([1.4, 1, 1.2])
                with ac1:
                    _am = st.selectbox("월", options=_months[::-1], key="ad_month")
                with ac2:
                    _ac = st.selectbox("채널", options=AD_CHANNEL_OPTIONS, key="ad_ch")
                with ac3:
                    _asp = st.number_input("광고비(원)", min_value=0, step=100000, value=0)
                if st.form_submit_button("저장", type="primary", width='stretch'):
                    save_ad_spend_monthly(_am, _ac, int(_asp))
                    st.success(f"{ganji.ym_label(_am, with_ganji=False)} {_ac} 광고비 {_asp:,}원 저장 완료")
                    st.rerun()
            if not ad_m.empty:
                _disp = ad_m.copy()
                _disp['spend'] = _disp['spend'].apply(lambda x: f"{x:,}원")
                _disp['month'] = _disp['month'].apply(lambda m: ganji.ym_label(m))
                st.dataframe(_disp[['month', 'channel', 'spend']].rename(
                    columns={'month': '월(사주 구조)', 'channel': '채널', 'spend': '광고비'}),
                    hide_index=True)

        # ── 월별 광고비 vs 매출 ROAS ──────────────────────────
        if not ad_m.empty:
            fig_roas = monthly_roas_chart(perf, ad_m)
            if fig_roas:
                st.markdown("**📊 월별 광고비 대비 매출(ROAS)**")
                st.plotly_chart(fig_roas, key="mkt_roas")
                st.caption("광고비가 입력된 달만 표시. ROAS = 해당 월 매출 ÷ 광고비. "
                           "※ 광고비는 다음 달 매출에 반영되는 **시차**가 있어 월 단위 ROAS는 편차가 큽니다 "
                           "— 아래 리드 획득 단가를 함께 보세요.")

            # ── 월별 리드 획득 단가 + 수확체감 진단 ──────────
            fig_cpa = monthly_lead_cpa_chart(ad_m, perf)
            if fig_cpa:
                st.markdown("**🎣 월별 리드 획득 단가(CPA) — 광고는 '모객 엔진'**")
                st.plotly_chart(fig_cpa, key="mkt_lead_cpa")
                # 진단: 광고비↔모객(+), 광고비↔ROAS(-)
                _sp = ad_m.groupby('month', as_index=False)['spend'].sum()
                _mm = _sp.merge(perf[['month', 'free_signups', 'revenue']], on='month', how='inner')
                _mm = _mm[_mm['spend'] >= 5e6].copy()
                if len(_mm) >= 4:
                    _mm['cpa'] = _mm['spend'] / _mm['free_signups'].replace(0, float('nan'))
                    _mm['roas'] = _mm['revenue'] / _mm['spend']
                    _corr_lead = _mm['spend'].corr(_mm['free_signups'])
                    _corr_roas = _mm['spend'].corr(_mm['roas'])
                    _best_cpa = _mm.loc[_mm['cpa'].idxmin()]
                    _worst_cpa = _mm.loc[_mm['cpa'].idxmax()]
                    st.info(
                        f"💡 **광고비의 1차 성과는 '무료 모객'입니다** — 광고비↔모객 상관 "
                        f"**{_corr_lead:+.2f}**(강한 양). 리드 획득 단가는 **{ganji.ym_label(_best_cpa['month'], with_ganji=False)} "
                        f"{_best_cpa['cpa']:,.0f}원**(최저)에서 **{ganji.ym_label(_worst_cpa['month'], with_ganji=False)} "
                        f"{_worst_cpa['cpa']:,.0f}원**(최고) 사이입니다. "
                        f"다만 광고비↔ROAS 상관은 **{_corr_roas:+.2f}**(음) — "
                        "**광고를 키우면 리드는 싸게 대량으로 오지만, 그 리드의 매출 전환 효율은 "
                        "떨어집니다**(대량 유입=볼륨 자석 후킹의 낮은 전환과 일치). → 무작정 광고비를 "
                        "늘리기보다 **리드 CPA가 낮게 유지되는 적정 규모**에서 운영하고, 유입 리드의 "
                        "전환을 CRM으로 끌어올리는 게 핵심입니다.")
                    st.caption("리드 CPA = 월 광고비 ÷ 월 무료 모객. 광고비 500만원 미만인 초기 달은 "
                               "매출이 오가닉/이전 캠페인이라 제외했습니다.")
        st.divider()

    # ══ 무료특강 주제별 모객 효율 (콘텐츠 후킹) ════════════════════
    wt = load_webinar_topics()
    if not wt.empty:
        st.subheader("🎣 무료특강 주제별 모객 효율")
        st.caption("어떤 무료특강 주제(후킹)가 사람을 가장 많이 모으는지 — 모객 콘텐츠 전략의 핵심입니다. "
                   "주문 원본의 무료 신청을 주제별로 집계(전자책·이벤트 제외, 개인정보 미보관).")
        _wt = wt.copy()
        _tot_w = int(_wt['signups'].sum())
        # 상품군별 1위 후킹
        _best_by_p = (_wt.sort_values('signups', ascending=False)
                      .drop_duplicates('product'))
        st.markdown('<div class="gp-kpi-row">' + ''.join(
            f'<div class="gp-kpi"><p class="k">🏆 {p} 대표 후킹</p>'
            f'<div class="v" style="font-size:18px">{t}</div>'
            f'<p class="s">{int(s):,}명 모객</p></div>'
            for p, t, s in zip(_best_by_p['product'], _best_by_p['topic'], _best_by_p['signups'])
            if p in ['사주', '타로', '부동산', '빌딩']) + '</div>', unsafe_allow_html=True)
        st.write("")

        wc1, wc2 = st.columns([1.25, 1])
        with wc1:
            _fw = webinar_topic_chart(_wt)
            if _fw:
                st.plotly_chart(_fw, key="mkt_webinar")
        with wc2:
            st.markdown("**상품군별 후킹 효율 (모객 비중)**")
            for _p in ['사주', '타로', '부동산', '빌딩']:
                _ps = _wt[_wt['product'] == _p].sort_values('signups', ascending=False)
                if _ps.empty:
                    continue
                _pt = int(_ps['signups'].sum())
                _top = _ps.iloc[0]
                st.markdown(f"- **{_p}** (총 {_pt:,}명) — 1위 **{_top['topic']}** "
                            f"({_top['signups']/_pt*100:.0f}%)")

        # 후킹 프레이밍 인사이트 (같은 상품 내 1위 vs 2위 격차)
        _ins = []
        for _p in ['사주', '타로', '부동산', '빌딩']:
            _ps = _wt[_wt['product'] == _p].sort_values('signups', ascending=False)
            if len(_ps) >= 2 and _ps.iloc[1]['signups'] > 0:
                _r = _ps.iloc[0]['signups'] / _ps.iloc[1]['signups']
                if _r >= 2:
                    _ins.append(f"**{_p}**: ‘{_ps.iloc[0]['topic']}’이 ‘{_ps.iloc[1]['topic']}’보다 "
                                f"**{_r:.1f}배** 모객")
        if _ins:
            st.info("💡 **후킹 프레이밍이 모객을 좌우** — " + " · ".join(_ins) +
                    ". 성과가 검증된 후킹을 광고·랜딩 카피에 우선 활용하고, 신규 주제는 이 승자들과 "
                    "A/B로 비교하세요.")

        # ── 후킹 품질: 모객량 × 전환율 ────────────────────
        wcv = load_webinar_conversion()
        if not wcv.empty:
            st.markdown("**🎯 후킹 품질 — 많이 모으는 후킹 ≠ 잘 파는 후킹**")
            st.caption("가로=고유 모객 수, 세로=유료 전환율, 버블 크기=실제 전환 고객 수. "
                       "무료 신청 고객이 이후 유료 구매까지 이어졌는지로 후킹의 '질'을 봅니다.")
            st.plotly_chart(webinar_quadrant_chart(wcv), key="mkt_webinar_quad")
            _w = wcv.copy()
            _best_conv = _w.loc[_w['conv_rate'].idxmax()]
            _best_vol = _w.loc[_w['unique_signups'].idxmax()]
            _best_abs = _w.loc[_w['converters'].idxmax()]
            # 볼륨자석(모객 상위인데 전환율 하위) 탐지
            _mv = _w['unique_signups'].median()
            _mc = _w['conv_rate'].median()
            _vanity = _w[(_w['unique_signups'] >= _mv) & (_w['conv_rate'] < _mc)].sort_values(
                'unique_signups', ascending=False)
            _gem = _w[(_w['unique_signups'] < _mv) & (_w['conv_rate'] >= _mc)].sort_values(
                'conv_rate', ascending=False)
            msg = (f"💡 **후킹 품질 진단** — 전환율 최고는 **{_best_conv['product']} "
                   f"{_best_conv['topic']}({_best_conv['conv_rate']:.0f}%)**, "
                   f"실제 유료 고객을 가장 많이 만든 후킹은 **{_best_abs['product']} "
                   f"{_best_abs['topic']}({int(_best_abs['converters']):,}명)**입니다. ")
            if not _vanity.empty:
                _v = _vanity.iloc[0]
                msg += (f"**{_v['product']} {_v['topic']}**은 모객은 최대급이나 전환율 "
                        f"**{_v['conv_rate']:.0f}%**로 낮은 **볼륨 자석형** — 리드는 많지만 질이 낮으니 "
                        "후속 CRM 강화가 필요합니다. ")
            if not _gem.empty:
                _g2 = _gem.iloc[0]
                msg += (f"반대로 **{_g2['product']} {_g2['topic']}**은 모객은 적어도 전환율 "
                        f"**{_g2['conv_rate']:.0f}%**로 높은 **알짜형** — 타깃이 명확하니 "
                        "유사 고관여 세그먼트로 확대할 가치가 있습니다.")
            st.info(msg)

            # ── 자기완결 vs 관문(다른 강의 유입) ──────────
            if 'self_share' in wcv.columns:
                st.markdown("**🚪 후킹 유형 — 자기완결(자사) vs 관문(다른 강의 유입)**")
                st.caption("특강 참석자의 전환이 **같은 강의 구매**인지(자기완결), "
                           "**다른 강의로 유입**인지(관문)로 나눕니다. 관문형은 자사 전환이 낮아도 "
                           "생태계(특히 사주 허브)로 고객을 유입시키는 기여가 있습니다.")
                st.plotly_chart(webinar_selfconv_chart(wcv), key="mkt_webinar_self")
                _wself = wcv.copy()
                _selfish = _wself[_wself['self_share'] >= 60].sort_values('self_share', ascending=False)
                _gate = _wself[_wself['self_share'] < 45].sort_values('unique_signups', ascending=False)
                _gmsg = "💡 **후킹 역할 구분** — "
                if not _selfish.empty:
                    _gmsg += (f"**{' · '.join(_selfish['product'].unique())}** 계열 후킹은 "
                              f"전환의 60%+가 자기 강의(자기완결형, 예 {_selfish.iloc[0]['topic']} "
                              f"self {_selfish.iloc[0]['self_share']:.0f}%) — 특강↔상품이 직결. ")
                if not _gate.empty:
                    _gt = _gate.iloc[0]
                    _gmsg += (f"반면 **{_gt['product']} {_gt['topic']}** 등은 전환의 절반 이상이 "
                              "**다른 강의로 유입되는 관문형** — 자사 전환율만으로 평가하면 저평가됩니다. "
                              "모객 규모가 크므로 **생태계 유입 창구**로 계속 활용하되, 유입 후 "
                              "교차판매(사주 허브) CRM을 연결하세요.")
                st.info(_gmsg)

        # ── 후킹 소재별 광고 효율 (메타, 스냅샷) ──────────
        wha = load_webinar_hook_ad()
        if not wha.empty:
            _pd = wha['product'].iloc[0]
            _per = wha['period'].iloc[0]
            _per_lbl = ganji.ym_label(_per)  # '2025년 11월 · 乙巳年 丁亥月'
            st.markdown(f"**💸 후킹 소재별 광고 효율 — {_pd} 무료특강 ({_per_lbl}, 메타)**")
            st.caption("어떤 후킹 주제에 메타 광고비를 얼마 써서 무료 신청(리드)을 얼마에 얻는지 — "
                       "'모객' 뒤의 실제 **광고 투자 효율**입니다. 막대=광고비, 색=리드 단가(CPL, 초록=저렴).")
            _tot_sp = int(wha['spend'].sum()); _tot_ld = int(wha['leads'].sum())
            _avg_cpl = _tot_sp / _tot_ld if _tot_ld else 0
            _paid = wha[wha['leads'] > 0]
            _best = _paid.loc[_paid['cpl'].idxmin()]
            _worst = _paid.loc[_paid['cpl'].idxmax()]
            _topspend = wha.loc[wha['spend'].idxmax()]
            _kpi_band([
                ("💸 광고비 합계", f"{_tot_sp/1e4:,.0f}<small>만원</small>",
                 f"소재 {int(wha['creatives'].sum())}개"),
                ("🎣 리드 합계", f"{_tot_ld:,}<small>건</small>", "무료 신청 전환"),
                ("📉 평균 리드 단가", f"{_avg_cpl:,.0f}<small>원</small>", "광고비÷리드"),
                ("🏆 최저 CPL 후킹", f"{_best['hook']}",
                 f"{_best['cpl']:,.0f}원 · 리드 {int(_best['leads']):,}"),
            ])
            _fig = webinar_hook_ad_chart(wha)
            if _fig is not None:
                st.plotly_chart(_fig, key="mkt_hook_ad")
            # 표
            _t = wha.sort_values('spend', ascending=False)[
                ['hook', 'creatives', 'spend', 'leads', 'ctr', 'cvr', 'cpl']].copy()
            _t.columns = ['후킹', '소재수', '광고비', '리드', 'CTR%', 'CVR%', 'CPL(원)']
            st.dataframe(
                _t.style.format({'광고비': '{:,.0f}', '리드': '{:,.0f}',
                                 'CTR%': '{:.1f}', 'CVR%': '{:.1f}', 'CPL(원)': '{:,.0f}'}),
                hide_index=True, width='stretch')
            # 인사이트: 볼륨자석(고클릭·저전환) vs 알짜(저CPL)
            _hi_ctr = wha.loc[wha['ctr'].idxmax()]
            _hi_cvr = _paid.loc[_paid['cvr'].idxmax()]
            _ratio = _worst['cpl'] / _best['cpl'] if _best['cpl'] else 0
            _msg = (f"💡 **후킹 광고 효율 진단** — 광고비의 최대 몫은 **{_topspend['hook']}**"
                    f"({_topspend['spend']/_tot_sp*100:.0f}%)에 투입됐고, 리드를 가장 싸게 얻은 후킹은 "
                    f"**{_best['hook']}({_best['cpl']:,.0f}원)**, 가장 비싼 후킹은 "
                    f"**{_worst['hook']}({_worst['cpl']:,.0f}원, {_ratio:.1f}배)**입니다. ")
            if _hi_ctr['hook'] != _hi_cvr['hook']:
                _msg += (f"**{_hi_ctr['hook']}**은 클릭률(CTR {_hi_ctr['ctr']:.1f}%)이 가장 높아 "
                         "시선을 끌지만, 실제 신청 전환은 "
                         f"**{_hi_cvr['hook']}**(CVR {_hi_cvr['cvr']:.1f}%)이 가장 높습니다 — "
                         "**'잘 눌리는 후킹'과 '잘 신청되는 후킹'이 다릅니다.** ")
            _msg += (f"CPL이 낮은 **{_best['hook']}·{_paid.sort_values('cpl').iloc[1]['hook']}** "
                     f"계열로 예산을 더 싣고, 고비용 **{_worst['hook']}**은 소재를 교체하거나 축소하세요. "
                     "※ 이 값은 마케팅시트 스냅샷 기준(단일 기간)이므로 추세는 자료가 누적되면 갱신됩니다.")
            st.info(_msg)

            # 소재 형식(동영상 vs 이미지) 효율 — 무엇을 만들지의 근거
            if 'format' in wha.columns and wha['format'].nunique() > 1:
                _fm = wha.groupby('format').agg(
                    n=('creatives', 'sum'), spend=('spend', 'sum'),
                    leads=('leads', 'sum'), imp=('impressions', 'sum'),
                    clk=('clicks', 'sum'))
                _fm = _fm[_fm['leads'] > 0]
                if len(_fm) >= 2:
                    _fm['cpl'] = _fm['spend'] / _fm['leads']
                    _fm['ctr'] = _fm['clk'] / _fm['imp'] * 100
                    _bf = _fm['cpl'].idxmin()
                    _wf = _fm['cpl'].idxmax()
                    _gap = (_fm.loc[_wf, 'cpl'] / _fm.loc[_bf, 'cpl'] - 1) * 100
                    st.markdown("**🎬 소재 형식별 효율 — 무엇을 만들어야 하나**")
                    _fr = "".join(
                        f'<tr><td><b>{i}</b></td>'
                        f'<td style="text-align:right">{int(r["n"])}개</td>'
                        f'<td style="text-align:right">{r["spend"]/1e4:,.0f}만원</td>'
                        f'<td style="text-align:right">{int(r["leads"]):,}건</td>'
                        f'<td style="text-align:right">{r["cpl"]:,.0f}원</td>'
                        f'<td style="text-align:right">{r["ctr"]:.1f}%</td></tr>'
                        for i, r in _fm.sort_values('cpl').iterrows())
                    st.markdown(
                        '<table class="gp-dtbl" style="width:100%;border-collapse:collapse;'
                        'font-size:13px"><thead><tr style="text-align:left"><th>형식</th>'
                        '<th style="text-align:right">소재수</th>'
                        '<th style="text-align:right">광고비</th>'
                        '<th style="text-align:right">리드</th>'
                        '<th style="text-align:right">CPL</th>'
                        '<th style="text-align:right">CTR</th></tr></thead>'
                        f'<tbody>{_fr}</tbody></table>', unsafe_allow_html=True)
                    st.success(f"🎬 **{_bf}이 {_wf}보다 리드를 {_gap:.0f}% 싸게** 데려옵니다"
                               f"({_fm.loc[_bf,'cpl']:,.0f}원 vs {_fm.loc[_wf,'cpl']:,.0f}원). "
                               f"→ 신규 소재는 **{_bf} 우선**으로 제작하세요.")
        st.divider()

    # ══ 강의 ROI 분석 (강의 집계 보고서 기반) ════════════════════
    course_sum = load_course_summary()
    cohort_rev = load_cohort_revenue()
    if not course_sum.empty:
        st.subheader("🎓 강의 ROI 분석")
        st.caption("아임웹 강의별 집계(세트합계·멤버십 제외) 기준. 무료 특강 모객 → 유료 전환 성과를 "
                   "상품군·기수별로 비교합니다.")

        _tot_paid_rev = int(course_sum['revenue'].sum())
        _tot_students = int(course_sum['students'].sum())
        _tot_free_cnt = int(course_sum['free'].sum())
        _ad_all = int(ad_m['spend'].sum()) if not ad_m.empty else 0
        _free2paid = (_tot_students / _tot_free_cnt * 100) if _tot_free_cnt else 0
        _kpi_band([
            ("💰 강의 누적 매출", f"{_tot_paid_rev/1e8:,.1f}<small>억원</small>", "4개 상품군 세트합계"),
            ("🎓 누적 유료 수강생", f"{_tot_students:,}<small>명</small>",
             f"결제 {int(course_sum['paid'].sum()):,}건"),
            ("🆓 누적 무료 모객", f"{_tot_free_cnt:,}<small>명</small>", "무료 신청(중복 포함)"),
            ("🔄 무료→유료 전환율", f"{_free2paid:.1f}<small>%</small>", "수강생 ÷ 무료"),
        ])
        st.write("")

        cm1, cm2 = st.columns([1, 1.2])
        with cm1:
            fig_mix = product_revenue_mix_chart(course_sum)
            if fig_mix:
                st.plotly_chart(fig_mix, key="roi_mix")
        with cm2:
            # 상품군별 요약표 — 세트 수강생 기준(매출과 정합), 0 나눔 가드
            cs = course_sum.copy().sort_values('revenue', ascending=False)
            cs['전환율'] = (cs['students'] / cs['free'].replace(0, float('nan')) * 100).round(1).fillna(0)
            cs['객단가'] = (cs['revenue'] / cs['students'].replace(0, float('nan'))).round(0).fillna(0).astype(int)
            cs_disp = pd.DataFrame({
                '상품군': cs['product'],
                '누적매출': cs['revenue'].apply(lambda x: f"{x/1e8:,.2f}억"),
                '수강생': cs['students'].apply(lambda x: f"{x:,}명"),
                '무료모객': cs['free'].apply(lambda x: f"{x:,}명"),
                '전환율': cs['전환율'].apply(lambda x: f"{x}%"),
                '객단가': cs['객단가'].apply(lambda x: f"{x/1e4:,.0f}만원"),
            })
            st.dataframe(cs_disp, hide_index=True)
            st.caption("전환율=세트 수강생÷무료신청, 객단가=누적매출÷세트 수강생 "
                       "(매출과 동일 기준인 세트 수강생으로 계산해 정합을 맞춤. 무료신청은 중복 포함).")

        # ── 상품군별 광고 ROI (캠페인별 광고비 귀속) ──────────
        camp_ad = load_campaign_adspend()
        g = pd.DataFrame()
        if not camp_ad.empty:
            g = camp_ad.groupby('product').agg(
                ad=('ad_spend', 'sum'), rev=('live_revenue', 'sum')).reset_index()
            g = g[g['ad'] > 0].copy()
        if not g.empty:
            st.markdown("**💰 상품군별 광고 효율 (광고비 대비 ROAS)**")
            st.caption("통합시트 라이브(캠페인)별 광고비를 상품군에 귀속한 결과. "
                       "여기 '광고 매출'은 해당 캠페인 라이브가 직접 만든 매출(첫 전환 기준)이라 "
                       "위 누적매출(패키지·재구매 포함)보다 작습니다. 광고 효율만 비교하는 값입니다.")
            fig_ad = product_ad_roi_chart(camp_ad)
            if fig_ad:
                st.plotly_chart(fig_ad, key="roi_prod_ad")

            g['roas'] = g['rev'] / g['ad']
            g = g.sort_values('roas', ascending=False)
            _best_p = g.iloc[0]
            _worst_p = g.iloc[-1]
            _tot_camp_ad = int(g['ad'].sum())
            ga1, ga2, ga3 = st.columns(3)
            ga1.metric("광고 최고효율", f"{_best_p['product']} {_best_p['roas']:.1f}배",
                       help="광고비 대비 라이브 직접 매출")
            ga2.metric("광고 최저효율", f"{_worst_p['product']} {_worst_p['roas']:.1f}배")
            ga3.metric("캠페인 광고비 총계", f"{_tot_camp_ad/1e8:,.2f}억원",
                       help=f"라이브별 광고비 합 (월별 집행 총액 {int(ad_m['spend'].sum())/1e8:.2f}억과 "
                            "집계 방식 차이로 소폭 다름)" if not ad_m.empty else "라이브별 광고비 합")

            g_disp = pd.DataFrame({
                '상품군': g['product'],
                '광고비': g['ad'].apply(lambda x: f"{x/1e8:,.2f}억"),
                '광고매출': g['rev'].apply(lambda x: f"{x/1e8:,.2f}억"),
                '광고 ROAS': g['roas'].apply(lambda x: f"{x:.1f}배"),
                '광고비 비중': (g['ad'] / g['ad'].sum() * 100).apply(lambda x: f"{x:.0f}%"),
            })
            st.dataframe(g_disp, hide_index=True)
            _ad_sum = int(g['ad'].sum())
            _top_spend = g.loc[g['ad'].idxmax()]           # 광고비 최다 집중 상품군
            _top_share = _top_spend['ad'] / _ad_sum * 100 if _ad_sum else 0
            _eff_names = " · ".join(g.sort_values('roas', ascending=False).head(2)['product'].tolist())
            st.info(f"💡 **광고 전략** — **{_best_p['product']}**가 광고비 대비 매출 **{_best_p['roas']:.1f}배**로 "
                    f"가장 효율적이라 광고 확대 여지가 큽니다. 반면 **{_worst_p['product']}**는 "
                    f"**{_worst_p['roas']:.1f}배**로, 광고비 비중이 높다면 소재·타깃 개선 또는 예산 재배분이 "
                    f"필요합니다. 현재 광고비의 **{_top_share:.0f}%**가 **{_top_spend['product']}**에 집중되어 있어, "
                    f"효율 높은 **{_eff_names}**로의 분산도 검토할 만합니다.")

            # ── 광고 예산 최적화 진단 (수확체감 반영) ──────────
            _bd = _ad_budget_diagnosis(camp_ad)
            if _bd:
                st.markdown("**⚖️ 광고 예산 최적화 진단 — 많이 쓴다고 좋은 게 아님**")
                st.caption("광고비를 키울수록 효율이 떨어지는 **수확체감**(광고비↔ROAS 상관)을 반영해 "
                           "상품군별로 확대·유지·축소를 권고합니다. 상관이 −0.5 이하면 수확체감 구간입니다.")
                _rec_color = {'확대': '#2E7D5B', '유지·소폭 확대': '#2E7D5B',
                              '적정 유지': '#B77A1B', '축소·재점검': '#BC4A38'}
                _bh = ""
                for _b in sorted(_bd, key=lambda x: -x['share']):
                    _c = _rec_color.get(_b['rec'], '#8A93A3')
                    _corr_txt = (f"{_b['corr']:+.2f}" if not (_b['corr'] != _b['corr']) else "—")
                    _sat_txt = "🔻 수확체감" if _b['saturated'] else "—"
                    _bh += (f'<tr><td><b>{_b["product"]}</b></td>'
                            f'<td style="text-align:right">{_b["ad"]/1e8:,.2f}억 <span style="opacity:.55">({_b["share"]:.0f}%)</span></td>'
                            f'<td style="text-align:right">{_b["roas"]:.1f}배</td>'
                            f'<td style="text-align:center">{_corr_txt}<div style="font-size:11px;opacity:.6">{_sat_txt}</div></td>'
                            f'<td style="color:{_c};font-weight:800;white-space:nowrap">{_b["rec"]}</td>'
                            f'<td style="font-size:12px;opacity:.7">{_b["why"]}</td></tr>')
                st.markdown(
                    '<table class="gp-dtbl" style="width:100%;border-collapse:collapse;font-size:13px">'
                    '<thead><tr style="text-align:left"><th>상품군</th><th style="text-align:right">광고비(비중)</th>'
                    '<th style="text-align:right">ROAS</th><th style="text-align:center">수확체감</th>'
                    '<th>권고</th><th>근거</th></tr></thead>'
                    f'<tbody>{_bh}</tbody></table>', unsafe_allow_html=True)
                _cut = [b for b in _bd if b['rec'] == '축소·재점검']
                _exp = [b for b in _bd if b['rec'] in ('확대', '유지·소폭 확대')]
                if _cut and _exp:
                    _cut_names = " · ".join(b['product'] for b in _cut)
                    _exp_top = max(_exp, key=lambda x: x['roas'])
                    st.info(f"💡 **예산 재배분 방향** — **{_cut_names}**는 광고비를 늘려도 효율이 "
                            f"떨어지는(수확체감) 구간이므로 **적정 규모로 축소**하고, 여유분을 **효율 최고 "
                            f"{_exp_top['product']}(ROAS {_exp_top['roas']:.1f}배·비중 {_exp_top['share']:.0f}%)**로 "
                            "옮기면 같은 예산으로 총 매출을 키울 수 있습니다. 단, 축소 상품도 최소 규모는 "
                            "유지해 모객 파이프라인이 끊기지 않게 하세요.")
                st.write("")

            # ── 기수별 광고 효율 진단 (저효율 상품 심층 분석) ──
            st.markdown("**🔬 기수별 광고 효율 진단**")
            st.caption("상품군을 골라 기수별 광고비 대비 매출(ROAS)을 진단합니다. "
                       "광고비를 많이 쓰고도 효율이 낮은 기수를 찾아 소재·타깃을 재점검하세요.")
            _diag_prods = [p for p in ['사주', '부동산', '빌딩', '타로']
                           if not camp_ad[camp_ad['product'] == p].empty]
            # 저효율(광고비 대비 ROAS 낮은) 상품을 기본 선택
            _default_idx = 0
            if not g.empty:
                _low_prod = g.sort_values('roas').iloc[0]['product']
                if _low_prod in _diag_prods:
                    _default_idx = _diag_prods.index(_low_prod)
            _dp = st.selectbox("진단 상품군", options=_diag_prods,
                               index=_default_idx, key="cohort_ad_diag")
            _fig_diag = cohort_ad_roi_chart(camp_ad, _dp)
            if _fig_diag:
                st.plotly_chart(_fig_diag, key="roi_cohort_ad_diag")
                # 기수별 진단 인사이트
                _dd = camp_ad[camp_ad['product'] == _dp].groupby('cohort', as_index=False).agg(
                    ad=('ad_spend', 'sum'), rev=('live_revenue', 'sum'))
                _dd = _dd[_dd['ad'] > 0].copy()
                if not _dd.empty:
                    _dd['roas'] = _dd['rev'] / _dd['ad']
                    _wc = _dd.loc[_dd['roas'].idxmin()]
                    _mc = _dd.loc[_dd['ad'].idxmax()]
                    _bc = _dd.loc[_dd['roas'].idxmax()]
                    _msg = (f"💡 **{_dp} 진단** — 광고비 최다 투입 기수는 **{_mc['cohort']}"
                            f"({_mc['ad']/1e8:.2f}억, ROAS {_mc['rev']/_mc['ad']:.1f}배)**, "
                            f"효율 최저는 **{_wc['cohort']}({_wc['roas']:.1f}배)**, "
                            f"최고는 **{_bc['cohort']}({_bc['roas']:.1f}배)**입니다. ")
                    if _mc['rev'] / _mc['ad'] < 3:
                        _msg += (f"광고비를 가장 많이 쓴 **{_mc['cohort']}의 효율이 낮아**, "
                                 "해당 기수의 소재·타깃·랜딩을 최우선으로 점검해야 합니다.")
                    else:
                        _msg += "광고비 배분과 효율이 대체로 정렬되어 있습니다."
                    st.info(_msg)

        # 기수별 매출 곡선 (상품군 선택)
        if not cohort_rev.empty:
            st.markdown("**기수별 매출 추이**")
            _prods = [p for p in ['사주', '타로', '부동산', '빌딩']
                      if p in cohort_rev['product'].unique()]
            _psel = st.selectbox("상품군 선택", options=_prods, key="roi_prod")
            fig_co = cohort_revenue_chart(cohort_rev, _psel)
            if fig_co:
                st.plotly_chart(fig_co, key="roi_cohort")
            # 최고/최저 기수 인사이트
            _pd = cohort_rev[cohort_rev['product'] == _psel]
            _pd = _pd[_pd['students'] > 0]
            if not _pd.empty:
                _best = _pd.loc[_pd['revenue'].idxmax()]
                _bestp = _pd.loc[(_pd['revenue'] / _pd['students']).idxmax()]
                st.info(f"💡 **{_psel}** — 최대 매출 기수: **{_best['cohort']}** "
                        f"({_best['revenue']/1e4:,.0f}만원, {_best['students']}명). "
                        f"객단가 최고 기수: **{_bestp['cohort']}** "
                        f"({_bestp['revenue']/_bestp['students']/1e4:,.0f}만원/명).")
        st.divider()

    # ══ 경쟁사 가격 벤치마크 ════════════════════════════════════
    comp = load_competitor_courses()
    if not comp.empty:
        st.subheader("🏷️ 경쟁사 가격 벤치마크")
        st.caption("경쟁사 조사 시트 기반 — 상품군별 시장 가격대와 황금후추(자사) 포지셔닝. "
                   "무료 웨비나 → 고가 전환 구조의 프리미엄 가격 전략을 시장과 비교합니다.")

        _cats = [c for c in ['사주', '타로', '부동산', '빌딩']
                 if c in comp['category'].unique()]
        # 상품군별 포지셔닝 요약 카드
        _own = comp[comp['company'].str.contains('황금후추', na=False)]
        _mkt = comp[~comp['company'].str.contains('황금후추', na=False)]
        pos_rows = []
        for c in _cats:
            o = _own[_own['category'] == c]
            m = _mkt[_mkt['category'] == c]
            if o.empty or m.empty:
                continue
            own_price = int(o['price_max'].iloc[0])
            # 경쟁사 대표가 = (min+max)/2 의 중앙값
            mids = ((m['price_min'] + m['price_max']) / 2)
            mkt_med = int(mids.median())
            ratio = own_price / mkt_med if mkt_med else 0
            pos_rows.append((c, own_price, mkt_med, int(m['price_min'].min()),
                             int(m['price_max'].max()), ratio))

        if pos_rows:
            cols = st.columns(len(pos_rows))
            for col, (c, own_p, mkt_med, mn, mx, ratio) in zip(cols, pos_rows):
                col.metric(
                    f"{c} — 자사 대표가", f"{own_p/1e4:,.0f}만원",
                    delta=f"시장 대비 {ratio:.1f}배",
                    delta_color="off",
                    help=f"경쟁사 대표가(중앙) {mkt_med/1e4:,.0f}만원 · "
                         f"시장범위 {mn/1e4:,.0f}~{mx/1e4:,.0f}만원",
                )

        _sel = st.selectbox("상품군 선택", options=_cats, key="comp_cat")
        fig_c = competitor_price_chart(comp, _sel)
        if fig_c:
            st.plotly_chart(fig_c, key="mkt_comp")

        # 포지셔닝 인사이트
        _sr = next((r for r in pos_rows if r[0] == _sel), None)
        if _sr:
            c, own_p, mkt_med, mn, mx, ratio = _sr
            if ratio >= 1.5:
                _pos = (f"황금후추 **{c}** 대표가는 **{own_p/1e4:,.0f}만원**으로 "
                        f"시장 중앙값({mkt_med/1e4:,.0f}만원)의 **{ratio:.1f}배** — "
                        f"명확한 **프리미엄 포지션**입니다. 무료 웨비나로 신뢰를 쌓아 "
                        f"고가 전환하는 구조여서, 가격보다 **콘텐츠·브랜드 차별성**이 "
                        f"핵심 경쟁력입니다.")
            elif ratio >= 0.8:
                _pos = (f"황금후추 **{c}** 대표가({own_p/1e4:,.0f}만원)는 시장 중앙값 "
                        f"({mkt_med/1e4:,.0f}만원)과 **비슷한 수준**입니다. 가격 경쟁이 "
                        f"치열한 구간이므로 차별화 포인트가 중요합니다.")
            else:
                _pos = (f"황금후추 **{c}** 대표가({own_p/1e4:,.0f}만원)는 시장 중앙값 "
                        f"({mkt_med/1e4:,.0f}만원)보다 **낮은 편**으로, 가격 경쟁력이 있는 "
                        f"포지션입니다.")
            st.info("💡 " + _pos)
        st.divider()

    # ══ 채널별 상세 (외부 채널 metrics) ═════════════════════════
    st.subheader("🔬 채널별 상세 분석")
    df = load_marketing()
    if df.empty:
        st.info("채널별 상세 데이터(채널 metrics)가 없습니다.")
        return

    d0, d1 = df['date'].min(), df['date'].max()
    # 지역 분포(v4.74)와 같은 이유 — 기간만 적혀 있으면 얼마나 지난 값인지
    # 읽히지 않는다. 아래 KPI가 광고비·ROAS·CPA라 현재값으로 오독되기 쉽다.
    _cm_age = None
    try:
        _cm_d = pd.to_datetime(d1).date()
        _cm_age = (date.today().year - _cm_d.year) * 12 + (date.today().month - _cm_d.month)
    except (ValueError, TypeError):
        pass
    st.caption(f"채널 metrics 기간: **{d0} ~ {d1}** — 채널별 일 단위 상세 (외부 시트 이관)"
               + (f" · **{_cm_age}개월 전 자료**" if _cm_age else ""))
    if _cm_age and _cm_age >= 3:
        st.warning(f"⚠️ 아래 채널별 수치는 **{str(d0)[:7]} 한 달치**({_cm_age}개월 전)입니다. "
                   "지금의 채널 성과가 아니라 그때의 기록이므로, 현재 예산 배분 근거로는 "
                   "쓰지 마세요. 최신 채널 시트를 확보하면 그대로 갱신됩니다.", icon="🕰️")

    # ── KPI ──────────────────────────────────────────────
    # 총계는 '전체'(집계행)를 권위값으로, 광고비는 채널 실집행(메타)만 사용
    ch = marketing_channel_summary(df)
    _tot = df[df['channel'] == '전체']
    tot_spend = int(ch['광고비'].sum())          # '전체'행 제외 = 실제 채널 광고비
    if not _tot.empty:
        tot_rev  = int(_tot['revenue'].sum())
        tot_sess = int(_tot['sessions'].sum())
        tot_buy  = int(_tot['purchases'].sum())
    else:
        tot_rev, tot_sess, tot_buy = int(ch['매출'].sum()), int(ch['세션'].sum()), int(ch['구매'].sum())
    roas      = round(tot_rev / tot_spend, 1) if tot_spend else 0
    cpa       = round(tot_spend / tot_buy) if tot_buy else 0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("총 광고비", f"{tot_spend:,}원")
    k2.metric("총 매출", f"{tot_rev:,}원")
    k3.metric("전체 ROAS", f"{roas:,.1f}배", help="총 매출 ÷ 총 광고비 (오가닉 매출 포함)")
    k4.metric("구매 건수", f"{tot_buy:,}건")
    k5, k6, k7, k8 = st.columns(4)
    k5.metric("총 세션(유입)", f"{tot_sess:,}")
    k6.metric("구매 전환율", f"{round(tot_buy/tot_sess*100,2)}%" if tot_sess else "—")
    k7.metric("광고 CPA", f"{cpa:,}원", help="광고비 ÷ 전체 구매 건수")
    _paid_sess = int(ch[ch['광고비'] > 0]['세션'].sum())
    k8.metric("광고 CPС(세션)", f"{round(tot_spend/_paid_sess):,}원" if _paid_sess else "—",
              help="광고비 ÷ 광고 유입 세션")

    st.info("💡 **읽는 법** — 광고비는 주로 **메타**에, 매출은 **오픈채팅·유튜브·오가닉**에 잡힙니다"
            "(광고→방 유입→구매 구조). 그래서 전체 ROAS는 유료+오가닉이 섞인 값이며, "
            "채널별 효율은 아래 세션·구매·전환율로 비교하는 것이 정확합니다.")

    # ── 🎯 목표 대비 평가 (업계 벤치마크 기준선) ──────────────
    _conv_rate = (tot_buy / tot_sess * 100) if tot_sess else 0
    _cps = (tot_spend / _paid_sess) if _paid_sess else 0
    _bench = [
        ("ROAS", roas, 2.0, f"{roas:.1f}배", "≥ 2.0배", roas >= 2.0),
        ("구매 전환율", _conv_rate, 3.0, f"{_conv_rate:.2f}%", "≥ 3%", _conv_rate >= 3.0),
        ("세션 단가(CPС)", _cps, 10000, f"{_cps:,.0f}원", "≤ 10,000원", 0 < _cps <= 10000),
    ]
    st.markdown("**🎯 목표 대비 (업계 벤치마크)**")
    bc = st.columns(len(_bench))
    for col, (name, _v, _t, cur, tgt, ok) in zip(bc, _bench):
        mark = "🟢 달성" if ok else "🔴 미달"
        col.metric(name, cur, delta=f"{mark} (목표 {tgt})", delta_color="off")

    # ── 총 마케팅 비용 통합 (광고비 + 부대비용) ────────────────
    with st.expander("💰 총 마케팅 비용 반영 — 친구톡·소재비 포함 보정 ROAS/CPA"):
        st.caption(f"채널 metrics의 광고비는 **메타 실집행({tot_spend:,}원)**만 포함합니다. "
                   "여기에 CRM 친구톡 발송비·소재 제작비를 더하면 **진짜 마케팅 비용** 기준 "
                   "ROAS·CPA를 볼 수 있습니다. 아래 값은 추정 기본치이며 실제 청구서에 맞게 수정하세요.")
        e1, e2 = st.columns(2)
        with e1:
            _kakao = st.number_input(
                "친구톡/CRM 발송비(원)", min_value=0, step=100000, value=7_870_000,
                help="발송 건수 × 단가(약 15원) 기준 추정. CRM 시트 발송 내역으로 보정 가능.")
        with e2:
            _asset = st.number_input(
                "소재 제작비(원)", min_value=0, step=100000, value=1_300_000,
                help="운영 실비 시트의 디자인·영상 소재 제작비 추정.")
        _total_mkt = tot_spend + int(_kakao) + int(_asset)
        _roas_adj = round(tot_rev / _total_mkt, 1) if _total_mkt else 0
        _cpa_adj = round(_total_mkt / tot_buy) if tot_buy else 0
        t1, t2, t3, t4 = st.columns(4)
        t1.metric("총 마케팅 비용", f"{_total_mkt/1e4:,.0f}만원",
                  delta=f"광고비 대비 +{(_total_mkt-tot_spend)/1e4:,.0f}만원", delta_color="off")
        t2.metric("보정 ROAS", f"{_roas_adj:,.1f}배",
                  delta=f"{_roas_adj-roas:+.1f}배", delta_color="off",
                  help="총 매출 ÷ 총 마케팅 비용")
        t3.metric("보정 CPA", f"{_cpa_adj:,}원",
                  delta=f"{_cpa_adj-cpa:+,}원", delta_color="inverse",
                  help="총 마케팅 비용 ÷ 구매 건수")
        t4.metric("비용 구성", f"광고 {tot_spend/_total_mkt*100:.0f}%" if _total_mkt else "—",
                  delta=f"부대 {(_kakao+_asset)/_total_mkt*100:.0f}%" if _total_mkt else None,
                  delta_color="off")

    # ── 채널별 매출 + 전환율 ──────────────────────────────
    st.divider()
    st.subheader("채널별 성과")
    c_l, c_r = st.columns(2)
    with c_l:
        fig = marketing_channel_chart(df)
        if fig:
            st.plotly_chart(fig, key="mkt_ch_rev")
    with c_r:
        fig2 = marketing_channel_conv_chart(df)
        if fig2:
            st.plotly_chart(fig2, key="mkt_ch_conv")

    # 채널 요약표
    disp = ch.copy()
    disp['광고비'] = disp['광고비'].apply(lambda x: f"{x:,}원" if x else "—")
    disp['세션']   = disp['세션'].apply(lambda x: f"{x:,}")
    disp['구매']   = disp['구매'].apply(lambda x: f"{x:,}건")
    disp['매출']   = disp['매출'].apply(lambda x: f"{x:,}원" if x else "—")
    disp['전환율'] = disp['전환율'].apply(lambda x: f"{x:.2f}%")
    disp = disp.rename(columns={'channel': '채널'})
    st.dataframe(disp, hide_index=True)

    # ── 일별 추이 ────────────────────────────────────────
    st.divider()
    st.subheader("일별 매출 · 광고비 추이")
    figt = marketing_trend_chart(df)
    if figt:
        st.plotly_chart(figt, key="mkt_trend")

    # ── 마케팅 퍼널 ──────────────────────────────────────
    st.divider()
    st.subheader("마케팅 퍼널")
    st.caption("광고비 투입 → 유입(세션) → 구매 → 매출")
    fc1, fc2, fc3, fc4 = st.columns(4)
    fc1.metric("① 광고비", f"{tot_spend/1e4:,.0f}만원")
    fc2.metric("② 유입 세션", f"{tot_sess:,}")
    fc3.metric("③ 구매", f"{tot_buy:,}건")
    fc4.metric("④ 매출", f"{tot_rev/1e8:,.2f}억원")


# ── 탭: 지역 분석 ─────────────────────────────────────────────────

def tab_region():
    st.header("📍 지역 분석")
    region = load_region_signups()
    rc = load_region_cohort()
    city = load_region_city()

    if region.empty:
        st.info("지역별 신청 데이터가 없습니다.")
        return

    st.caption("**돈사공 초급반 9~12기 배송지 주소** 기준 (국내 472건 · 개인정보 제외 지역 통계만). "
               "실물 교재를 배송하는 강의라 배송지 = 실제 거주 지역으로, 광고 타깃 지역 판단의 대표 표본입니다.")
    # 이 데이터는 갱신이 드물어, 기준 시점을 안 적으면 '지금의 지역 분포'로 읽힌다
    _rg_asof = _dataset_asof('지역 분포')
    if _rg_asof:
        try:
            _rg_mo = (date.today().year - int(_rg_asof[:4])) * 12 + \
                     (date.today().month - int(_rg_asof[5:7]))
        except (ValueError, IndexError):
            _rg_mo = None
        st.caption(f"⏳ 기준 시점 **{_rg_asof}**"
                   + (f" (약 {_rg_mo}개월 전)" if _rg_mo and _rg_mo >= 3 else "")
                   + " — 그 이후 유입된 기수는 반영되지 않았습니다. 최신 배송지 리포트를 "
                     "받으면 갱신하세요.")

    # ── 핵심 지표 (요약 KPI 밴드) ─────────────────────────
    _tot = int(region['signups'].sum())
    _cap = int(region[region['region'].isin(CAPITAL_REGIONS)]['signups'].sum())
    _cap_pct = _cap / _tot * 100 if _tot else 0
    _busan = int(region[region['region'] == '부산']['signups'].sum())
    _local_top = region[~region['region'].isin(CAPITAL_REGIONS)].sort_values('signups', ascending=False)
    _n_sido = int((region['signups'] > 0).sum())
    _overseas = 1  # 리포트 기준 해외 1건 별도
    st.markdown(f"""
    <div class="gp-kpi-row">
      <div class="gp-kpi"><p class="k">📋 총 신청 건수</p><div class="v">{_tot + _overseas:,}<small> 건</small></div>
        <p class="s">국내 {_tot:,}건 / 해외 {_overseas}건</p></div>
      <div class="gp-kpi"><p class="k">👥 수도권(서울·경기·인천)</p><div class="v">{_cap:,}<small> 건</small></div>
        <p class="s">전체의 {_cap_pct:.1f}%</p></div>
      <div class="gp-kpi"><p class="k">🗺️ 국내 지역 커버리지</p><div class="v">{_n_sido}<small> 개 시도</small></div>
        <p class="s">최대 비수도권 {_local_top.iloc[0]['region'] if not _local_top.empty else '—'} {int(_local_top.iloc[0]['signups']) if not _local_top.empty else 0}건</p></div>
      <div class="gp-kpi"><p class="k">🌐 해외 신청</p><div class="v">{_overseas}<small> 건</small></div>
        <p class="s">별도 집계</p></div>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # ── 지역별 분포 ──────────────────────────────────────
    st.subheader("지역별 신청 분포")
    # 지도(버블) + 지역 순위 막대 나란히
    mp_l, mp_r = st.columns([1, 1])
    with mp_l:
        fig_map = region_bubble_map(region, capital=tuple(CAPITAL_REGIONS))
        if fig_map:
            st.plotly_chart(fig_map, key="rgn_map")
    with mp_r:
        fig_r = region_distribution_chart(region, capital=tuple(CAPITAL_REGIONS))
        if fig_r:
            st.plotly_chart(fig_r, key="rgn_dist")
    with st.expander("지역별 신청 수 표"):
        rd = region.copy()
        rd = rd.rename(columns={'region': '지역', 'signups': '신청', 'pct': '비율(%)'})
        st.dataframe(rd, hide_index=True, width='stretch')

    # ── 기수별 지역 분포 상세 (per-cohort 카드) ──────────
    detail = load_region_cohort_detail()
    topcity = load_region_cohort_topcity()
    if not detail.empty:
        st.divider()
        st.subheader("기수별 지역 분포 상세")
        st.caption("기수별 지역 랭킹과 주요 상위 도시. 기수마다 수도권 집중도·지역 분산이 어떻게 다른지 비교합니다.")
        _cohs = sorted(detail['cohort'].unique(),
                       key=lambda c: int(''.join(ch for ch in c if ch.isdigit()) or 0))
        _rc_idx = rc.set_index('cohort') if not rc.empty else pd.DataFrame()
        _cols = st.columns(len(_cohs))
        for _col, _coh in zip(_cols, _cohs):
            _d = detail[detail['cohort'] == _coh].sort_values('count', ascending=False)
            _tot_c = int(_d['count'].sum())
            _cap_c = int(_d[_d['region'].isin(CAPITAL_REGIONS)]['count'].sum())
            _cap_pct_c = _cap_c / _tot_c * 100 if _tot_c else 0
            _mx = int(_d['count'].max()) if not _d.empty else 1
            _rows_html = ""
            for _i, (_, _rr) in enumerate(_d.head(6).iterrows(), 1):
                _w = _rr['count'] / _mx * 100
                _rows_html += (
                    f'<div class="gp-rank"><span class="rn">{_i}</span>'
                    f'<span class="rr">{_rr["region"]}</span>'
                    f'<span class="rbar"><i style="width:{_w:.0f}%"></i></span>'
                    f'<span class="rv">{int(_rr["count"])}명·{_rr["pct"]:.0f}%</span></div>')
            _tc = topcity[topcity['cohort'] == _coh].sort_values('count', ascending=False) \
                if not topcity.empty else pd.DataFrame()
            _city_html = ""
            if not _tc.empty:
                _cs = " · ".join(f"{r['city']} {int(r['count'])}" for _, r in _tc.head(3).iterrows())
                _city_html = f'<div class="gp-city">🏙️ 주요 도시 &nbsp;<b>{_cs}</b></div>'
            with _col:
                st.markdown(
                    f'<div class="gp-card"><div class="ch"><b>{_coh}</b>'
                    f'<span class="tot">총 {_tot_c}명 · 수도권 {_cap_pct_c:.0f}%</span></div>'
                    f'{_rows_html}{_city_html}</div>',
                    unsafe_allow_html=True)
        st.caption("막대 = 기수 내 최다 지역 대비 상대 크기. 상위 6개 지역만 표시.")

    # ── 광고 집중 전략 추천 ──────────────────────────────
    st.divider()
    st.subheader("🎯 광고 집중 지역 추천")

    def _rv(name):  # 지역 신청 수 안전 조회 (없으면 0)
        _s = region[region['region'] == name]['signups']
        return int(_s.iloc[0]) if not _s.empty else 0

    _seoul, _gg = _rv('서울'), _rv('경기')
    _sg_pct = (_seoul + _gg) / _tot * 100 if _tot else 0
    st.markdown(
        f"""
- **1순위 — 수도권(서울·경기·인천)**: 전체의 **{_cap_pct:.0f}%**가 집중. 메타·구글 광고 예산의 대부분을
  서울·경기 타깃으로 배정하는 것이 효율적입니다. 특히 서울({_seoul}건)·경기({_gg}건) 2개 시도만으로
  **{_sg_pct:.0f}%**를 차지합니다.
- **2순위 — 부산·경남권**: 비수도권 중 **부산({_busan}건)**이 가장 크고 경남·대구가 뒤를 이어,
  영남권 광역타깃(부산·경남·대구)을 별도 캠페인으로 운영할 가치가 있습니다.
- **3순위 — 대전·충청권**: 대전·충남·충북 합산이 일정 규모를 형성해 중부권 보조 타깃으로 검토.
- **저효율 경계**: 전남·전북·강원·제주는 신청이 적어(각 1% 안팎) 광역 타깃보다는
  전환이 확인될 때만 리타깃팅 위주로 최소 집행을 권장합니다.
"""
    )
    st.info("💡 다른 채널에서도 **수도권 > 부산·경기·인천 집중**이 효율적이라는 결과가 나왔던 것과 "
            "이 배송지 데이터가 일치합니다. 수도권+부산에 광고를 집중하는 전략이 데이터로 뒷받침됩니다.")

    # ── 도시/구 단위 ─────────────────────────────────────
    if not city.empty:
        st.divider()
        st.subheader("상위 도시·구 단위")
        cc_l, cc_r = st.columns([1.2, 1])
        with cc_l:
            fig_c = region_city_chart(city)
            if fig_c:
                st.plotly_chart(fig_c, key="rgn_city")
        with cc_r:
            st.markdown("**세부 타깃 인사이트**")
            st.markdown(
                "- 서울 내 **강남·서초·송파(강남 3구)**가 압도적 — 고관여·고소득 타깃과 일치.\n"
                "- 동작·영등포·양천·용산 등 서울 서남권도 꾸준.\n"
                "- 경기권은 **하남·성남 분당**이 상위 — 신도시 고소득층 공략 유효.\n\n"
                "→ 메타 상세 타깃을 **강남 3구 + 분당·하남** 반경으로 좁히면 CPA 개선 여지가 있습니다.")

    # ── 기수별 수도권 비중 추이 ──────────────────────────
    if not rc.empty:
        st.divider()
        st.subheader("기수별 모집 현황")
        # 기수별 카드 (모집기간·일수·총신청·수도권 비중)
        _rcs = rc.sort_values('cohort')
        _cards = st.columns(len(_rcs))
        for _col, (_, _r) in zip(_cards, _rcs.iterrows()):
            with _col:
                st.markdown(f"**{_r['cohort']}**")
                st.metric("총 신청", f"{int(_r['total'])}명",
                          delta=f"수도권 {_r['capital_pct']:.0f}%", delta_color="off")
                st.caption(f"📅 {_r['start']}\n~ {_r['end']}\n\n⏱️ {int(_r['days'])}일 모집")

        st.markdown("**총 신청 · 수도권 비중 추이**")
        fig_t = region_capital_trend_chart(rc)
        if fig_t:
            st.plotly_chart(fig_t, key="rgn_trend")
        rc_disp = pd.DataFrame({
            '기수': rc['cohort'],
            '모집기간': rc['start'] + ' ~ ' + rc['end'],
            '모집일수': rc['days'].apply(lambda x: f"{x}일"),
            '총신청': rc['total'].apply(lambda x: f"{x}명"),
            '수도권': rc['capital'].apply(lambda x: f"{x}명"),
            '수도권비중': rc['capital_pct'].apply(lambda x: f"{x}%"),
        })
        st.dataframe(rc_disp, hide_index=True)
        _avg_days = rc['days'].mean()
        _corr_hint = ("모집 기간이 길수록 총신청이 느는 경향" if rc['days'].corr(rc['total']) > 0.3
                      else "모집 기간과 총신청의 상관은 뚜렷하지 않음")
        st.caption(f"평균 모집 {_avg_days:.0f}일. {_corr_hint}. "
                   "수도권 비중은 기수별 59~73%로 항상 과반 — 수도권 우선 전략의 근거.")


# ── 경영진 보고: 자동 인사이트 생성 ─────────────────────────────────

def _generate_insight(df_period, rooms, period_label,
                      df_adspend=None, df_conv=None,
                      df_all=None) -> list[str]:
    """기간 데이터를 분석해 한국어 인사이트 문장 리스트를 반환."""
    if df_period.empty:
        return ["해당 기간의 데이터가 없습니다."]

    dates = sorted(df_period['date'].unique())
    if len(dates) < 2:
        return [f"{period_label} 기간 내 데이터가 1일뿐이라 비교 인사이트를 생성하기 어렵습니다."]

    first_date, last_date = dates[0], dates[-1]
    first_total = int(df_period[df_period['date'] == first_date]['members'].sum())
    last_total  = int(df_period[df_period['date'] == last_date]['members'].sum())
    diff = last_total - first_total
    pct  = round(diff / first_total * 100, 1) if first_total > 0 else 0
    sign = "+" if diff >= 0 else ""
    trend_word = "증가" if diff > 0 else ("감소" if diff < 0 else "유지")

    lines = []
    lines.append(
        f"**{period_label}** 전체 채팅방 총원은 **{last_total:,}명**으로, "
        f"시작일({first_date}) 대비 **{sign}{diff:,}명({sign}{pct}%) {trend_word}**했습니다."
    )

    # 전주/전월 비교 (df_all 있을 때만)
    if df_all is not None and not df_all.empty:
        def _ref_total(delta_days: int):
            ref = pd.Timestamp(last_date) - pd.Timedelta(days=delta_days)
            cands = df_all[df_all['date'] <= ref.date()]
            if cands.empty:
                return None, None
            nearest = cands['date'].max()
            return int(df_all[df_all['date'] == nearest]['members'].sum()), nearest

        _wow_total, _wow_ref = _ref_total(7)
        if _wow_total and _wow_total > 0:
            _d = last_total - _wow_total
            _p = round(_d / _wow_total * 100, 1)
            _s = "+" if _d >= 0 else ""
            lines.append(
                f"전주 대비({_wow_ref}): **{_s}{_d:,}명({_s}{_p}%)** "
                f"{'▲' if _d > 0 else ('▼' if _d < 0 else '➡')}"
            )

        _mom_total, _mom_ref = _ref_total(30)
        if _mom_total and _mom_total > 0:
            _d = last_total - _mom_total
            _p = round(_d / _mom_total * 100, 1)
            _s = "+" if _d >= 0 else ""
            lines.append(
                f"전월 대비({_mom_ref}): **{_s}{_d:,}명({_s}{_p}%)** "
                f"{'▲' if _d > 0 else ('▼' if _d < 0 else '➡')}"
            )

    # 방별 증감 분석
    room_changes = {}
    for rn in df_period['room_num'].unique():
        rdf = df_period[df_period['room_num'] == rn].sort_values('date')
        if len(rdf) >= 2:
            room_changes[int(rn)] = int(rdf.iloc[-1]['members']) - int(rdf.iloc[0]['members'])

    if room_changes:
        top_rn  = max(room_changes, key=room_changes.get)
        top_val = room_changes[top_rn]
        bot_rn  = min(room_changes, key=room_changes.get)
        bot_val = room_changes[bot_rn]
        if top_val > 0:
            lines.append(
                f"가장 성장한 채팅방은 **{rooms.get(top_rn, f'채팅방 {top_rn}')}** ("
                f"**+{top_val:,}명**)입니다."
            )
        if bot_val < 0:
            lines.append(
                f"인원이 가장 감소한 채팅방은 **{rooms.get(bot_rn, f'채팅방 {bot_rn}')}** ("
                f"**{bot_val:,}명**)입니다."
            )

        # 전체 성장/감소 방 수
        n_up   = sum(1 for v in room_changes.values() if v > 0)
        n_down = sum(1 for v in room_changes.values() if v < 0)
        n_flat = len(room_changes) - n_up - n_down
        lines.append(
            f"채팅방 {n_up}개 증가 · {n_down}개 감소 · {n_flat}개 유지."
        )

    # 광고비
    if df_adspend is not None and not df_adspend.empty:
        pa = df_adspend[
            (df_adspend['date'] >= first_date) & (df_adspend['date'] <= last_date)
        ]
        if not pa.empty:
            spend = int(pa['spend'].sum())
            if spend > 0:
                if diff > 0:
                    cpm = round(spend / diff)
                    lines.append(
                        f"기간 중 광고비 **{spend:,}원** 집행 → "
                        f"인원 증가 기준 CPM **{cpm:,}원/명**."
                    )
                else:
                    lines.append(f"기간 중 광고비 **{spend:,}원** 집행.")

    # 전환
    if df_conv is not None and not df_conv.empty:
        pc = df_conv[
            (df_conv['date'] >= first_date) & (df_conv['date'] <= last_date)
        ]
        if not pc.empty:
            app_total  = int(pc['applicants'].sum())
            conf_total = int(pc['confirmed'].sum())
            rev_total  = int(pc['revenue'].sum())
            cr = round(conf_total / app_total * 100, 1) if app_total > 0 else 0
            lines.append(
                f"강의 신청 **{app_total:,}명** 중 **{conf_total:,}명** 수강 확정 "
                f"(전환율 **{cr}%**), 매출 **{rev_total:,}원**."
            )

    return lines


# ── 탭: 경영진 보고 ───────────────────────────────────────────────

def tab_report():
    ROOMS = load_rooms()
    st.header("📋 경영진 보고")

    # 데이터 완성도 뱃지
    _df_all = load_all()
    if not _df_all.empty:
        _first = _df_all['date'].min()
        _days_total = (date.today() - _first).days + 1
        _days_in    = _df_all['date'].nunique()
        _comp_pct   = round(_days_in / _days_total * 100, 1)
        _color = "green" if _comp_pct >= 90 else ("orange" if _comp_pct >= 70 else "red")
        st.caption(
            f"데이터 완성도 :{_color}[**{_comp_pct}%**] "
            f"({_days_in}/{_days_total}일 입력) — 기준일: {_df_all['date'].max()}"
        )

    df = load_all()
    if df.empty:
        st.info("데이터가 없습니다. '오늘 입력' 탭에서 먼저 데이터를 입력해주세요.")
        return

    max_date = df['date'].max()
    min_date = df['date'].min()
    today    = date.today()

    # ── 기간 선택 ───────────────────────────────────────────────
    period = st.radio(
        "보고 기간",
        ["이번 주", "이번 달", "최근 3개월", "전체", "직접 설정"],
        horizontal=True,
        key="report_period",
    )

    if period == "이번 주":
        date_from = today - timedelta(days=today.weekday())
        date_to   = max_date
        period_label = "이번 주"
    elif period == "이번 달":
        date_from = date(today.year, today.month, 1)
        date_to   = max_date
        period_label = "이번 달"
    elif period == "최근 3개월":
        date_from = today - timedelta(days=90)
        date_to   = max_date
        period_label = "최근 3개월"
    elif period == "전체":
        date_from = min_date
        date_to   = max_date
        period_label = "전체 기간"
    else:
        rc1, rc2 = st.columns(2)
        with rc1:
            date_from = st.date_input("시작일", value=min_date,
                                      min_value=min_date, max_value=max_date,
                                      key="report_from")
        with rc2:
            date_to = st.date_input("종료일", value=max_date,
                                    min_value=min_date, max_value=max_date,
                                    key="report_to")
        period_label = f"{date_from} ~ {date_to}"

    df_period = df[(df['date'] >= date_from) & (df['date'] <= date_to)]

    if df_period.empty:
        st.warning("선택한 기간에 데이터가 없습니다.")
        return

    period_dates = sorted(df_period['date'].unique())
    first_date   = period_dates[0]
    last_date    = period_dates[-1]

    # ── KPI 4개 ─────────────────────────────────────────────────
    st.divider()
    last_snap  = df_period[df_period['date'] == last_date]
    first_snap = df_period[df_period['date'] == first_date]
    total_now  = int(last_snap['members'].sum())
    total_past = int(first_snap['members'].sum()) if len(period_dates) > 1 else total_now
    diff       = total_now - total_past
    pct        = round(diff / total_past * 100, 1) if total_past > 0 else 0

    # ── 총원 변동 원인 분해 (활성 방 자연증감 vs 종료 방 제외) ──────
    _active_nums = set(load_rooms().keys())
    _arch_df = load_archived_rooms()
    _arch_nums = {int(r['room_num']) for _, r in _arch_df.iterrows()} if not _arch_df.empty else set()
    _sb = first_snap.set_index('room_num')['members']
    _eb = last_snap.set_index('room_num')['members']
    _active_start = int(_sb[[rn for rn in _sb.index if rn in _active_nums]].sum())
    _active_end   = int(_eb[[rn for rn in _eb.index if rn in _active_nums]].sum())
    _arch_start   = int(_sb[[rn for rn in _sb.index if rn in _arch_nums]].sum())
    _active_change = _active_end - _active_start
    _change_breakdown = None
    _closed_in_period = []
    if _arch_start > 0 and len(period_dates) > 1:
        _closed_in_period = [
            {'room': r['room_name'], 'final': int(r['final_members']),
             'date': str(r.get('archived_date', '')), 'reason': str(r.get('archive_reason', '') or '운영 종료')}
            for _, r in _arch_df.sort_values('room_num').iterrows()
            if int(r['room_num']) in set(_sb.index)
        ]
        _active_pct = round(_active_change / _active_start * 100, 1) if _active_start else 0
        _change_breakdown = {
            'start_total': total_past, 'end_total': total_now,
            'active_start': _active_start, 'active_end': _active_end,
            'active_change': _active_change, 'active_pct': _active_pct,
            'archived_removed': -_arch_start, 'archived_count': len(_closed_in_period),
            'archived_detail': _closed_in_period,
        }
        # 화면 안내 배너
        st.info(
            f"📉 **총원 변동 원인** — 기간 총원 {diff:+,}명 중 **{-_arch_start:+,}명**은 "
            f"강의를 마친 **{len(_closed_in_period)}개 방의 정상 종료**로 빠진 구조적 감소이며, "
            f"계속 운영 중인 방은 **{_active_change:+,}명({_active_pct:+.1f}%)**으로 안정적입니다."
        )

    df_adspend = load_adspend()
    df_conv    = load_conversions()

    period_spend = 0
    if not df_adspend.empty:
        period_spend = int(df_adspend[
            (df_adspend['date'] >= first_date) & (df_adspend['date'] <= last_date)
        ]['spend'].sum())

    conv_rate = 0
    if not df_conv.empty:
        pc = df_conv[(df_conv['date'] >= first_date) & (df_conv['date'] <= last_date)]
        if not pc.empty:
            app_t  = int(pc['applicants'].sum())
            conf_t = int(pc['confirmed'].sum())
            conv_rate = round(conf_t / app_t * 100, 1) if app_t > 0 else 0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric(
        "현재 총 인원",
        f"{total_now:,}명",
        f"{diff:+,}명 ({pct:+.1f}%)" if len(period_dates) > 1 else None,
    )
    k2.metric(
        "기간 순증감",
        f"{diff:+,}명",
        f"{first_date} 기준" if len(period_dates) > 1 else "단일 날짜",
        delta_color="normal",
    )
    # 방별 광고비 수기 입력은 비어 있어도 전사 월별 광고비는 쌓여 있다.
    # '없음'만 띄우면 광고를 안 돌린 것처럼 읽히므로 출처를 밝혀 대체 표시한다.
    _co_spend, _co_have, _co_miss = (0, [], [])
    if period_spend == 0:
        _co_spend, _co_have, _co_miss = _adspend_prorated(first_date, last_date)
    if period_spend > 0:
        k3.metric(
            "광고비 집행",
            f"{period_spend:,}원",
            f"CPM {round(period_spend/diff):,}원/명" if diff > 0 else None,
        )
    elif _co_spend > 0:
        k3.metric(
            "전사 광고비(기간 안분)",
            f"{_co_spend:,}원",
            f"인원 1명당 {round(_co_spend/diff):,}원" if diff > 0 else None,
            delta_color="off",
            help="방별 광고비 수기 입력이 없어 **월별 전사 광고비**를 일수로 나눠 배분한 값입니다. "
                 "이 방들만의 광고비가 아니라 전 상품 합계라 참고용입니다.",
        )
    else:
        k3.metric("광고비 집행", "미입력",
                  help="📢 마케팅 분석 → ✏️ 월별 광고비 입력에서 총액을 넣으면 채워집니다.")
    k4.metric(
        "수강 전환율",
        f"{conv_rate}%" if conv_rate > 0 else "방별 입력 없음",
        help=None if conv_rate > 0 else
             "채팅방별 신청·수강확정 수기 입력 기준입니다. 전체 무료→유료 전환율은 "
             "📋 전환 분석 탭에서 주문 실데이터로 보고 있습니다.",
    )
    if _co_spend > 0 and _co_miss:
        # 안분값이 일부 월만 덮으면 '광고비가 줄었다'로 오독된다 — 빠진 달을 밝힌다.
        st.caption("※ 전사 광고비는 "
                   + " · ".join(ganji.ym_label(m, with_ganji=False) for m in _co_miss)
                   + " 미입력 — 그 기간은 0원으로 계산돼 실제보다 적게 보입니다.")

    # ── 전주/전월 비교 KPI ───────────────────────────────────────
    _period_len = (last_date - first_date).days if hasattr(last_date, '__sub__') else 0
    try:
        _period_len = int((pd.Timestamp(last_date) - pd.Timestamp(first_date)).days)
    except Exception:
        _period_len = 0

    # 직전 동일 길이 구간 총원 (가장 가까운 기록 날짜 사용)
    def _nearest_total(target_date):
        """target_date에 가장 가까운 실제 기록일의 총원 합계."""
        d = pd.Timestamp(target_date)
        cands = df[df['date'] <= d.date()].copy()
        if cands.empty:
            return None
        nearest = cands['date'].max()
        return int(df[df['date'] == nearest]['members'].sum()), nearest

    _wow_col, _mom_col, _qoq_col = st.columns(3)

    # WoW (전주 대비): 7일 전 같은 총원
    _wow_date = pd.Timestamp(last_date) - pd.Timedelta(days=7)
    _wow = _nearest_total(_wow_date.date())
    with _wow_col:
        if _wow and _wow[0] > 0:
            _wow_diff = total_now - _wow[0]
            _wow_pct  = round(_wow_diff / _wow[0] * 100, 1)
            st.metric("전주 대비 (7일)", f"{_wow_diff:+,}명",
                      f"{_wow_pct:+.1f}% · 기준 {_wow[1]}",
                      delta_color="normal")
        else:
            st.metric("전주 대비 (7일)", "—", "데이터 부족")

    # MoM (전월 대비): 30일 전
    _mom_date = pd.Timestamp(last_date) - pd.Timedelta(days=30)
    _mom = _nearest_total(_mom_date.date())
    with _mom_col:
        if _mom and _mom[0] > 0:
            _mom_diff = total_now - _mom[0]
            _mom_pct  = round(_mom_diff / _mom[0] * 100, 1)
            st.metric("전월 대비 (30일)", f"{_mom_diff:+,}명",
                      f"{_mom_pct:+.1f}% · 기준 {_mom[1]}",
                      delta_color="normal")
        else:
            st.metric("전월 대비 (30일)", "—", "데이터 부족")

    # QoQ (전분기 대비): 90일 전
    _qoq_date = pd.Timestamp(last_date) - pd.Timedelta(days=90)
    _qoq = _nearest_total(_qoq_date.date())
    with _qoq_col:
        if _qoq and _qoq[0] > 0:
            _qoq_diff = total_now - _qoq[0]
            _qoq_pct  = round(_qoq_diff / _qoq[0] * 100, 1)
            st.metric("전분기 대비 (90일)", f"{_qoq_diff:+,}명",
                      f"{_qoq_pct:+.1f}% · 기준 {_qoq[1]}",
                      delta_color="normal")
        else:
            st.metric("전분기 대비 (90일)", "—", "데이터 부족")

    # ── 자동 인사이트 ────────────────────────────────────────────
    st.divider()
    insight_lines = _generate_insight(
        df_period, ROOMS, period_label,
        df_adspend=df_adspend if not df_adspend.empty else None,
        df_conv=df_conv if not df_conv.empty else None,
        df_all=df,
    )
    # 총원 변동 원인 + 전략 시사점 (종료 방이 있을 때 맨 앞에 삽입)
    if _change_breakdown:
        _bd = _change_breakdown
        _closed_names = ", ".join(d['room'].split('(')[-1].rstrip(')') if '(' in d['room'] else d['room']
                                  for d in _bd['archived_detail'][:5])
        insight_lines.insert(0,
            f"**총원 변동 원인**: 기간 감소 {diff:+,}명 중 **{_bd['archived_removed']:+,}명**은 "
            f"강의를 마친 {_bd['archived_count']}개 방({_closed_names})의 정상 종료에 따른 구조적 감소이며, "
            f"**운영 중인 방은 {_bd['active_change']:+,}명({_bd['active_pct']:+.1f}%)**으로 안정적입니다. "
            f"헤드라인 감소율({pct:.1f}%)을 실제 운영 부진으로 오해하지 않도록 유의가 필요합니다.")
        # 전략 시사점 — 종료 기수 대비 신규 기수 전환 효율
        try:
            _fdf_i = cohort_funnel_data(df, load_campaigns(), load_enrollments())
            _fdf_i = _fdf_i[_fdf_i['conversion'].notna()]
            if not _fdf_i.empty:
                _best = _fdf_i.loc[_fdf_i['conversion'].idxmax()]
                _worst = _fdf_i.loc[_fdf_i['conversion'].idxmin()]
                insight_lines.insert(1,
                    f"**차기 전략 시사점**: 전환율은 **{_best['product']} {_best['cohort']} {_best['conversion']:.1f}%**로 최고, "
                    f"{_worst['product']} {_worst['cohort']} {_worst['conversion']:.1f}%로 최저입니다. "
                    f"방을 닫아 총원이 줄더라도 전환율 높은 상품(예: 타로)의 모객·연계를 강화하면 "
                    f"인원 대비 매출 효율을 높일 수 있습니다.")
        except Exception:
            pass
    with st.container(border=True):
        st.markdown("#### 💡 자동 분석 인사이트")
        for line in insight_lines:
            st.markdown(f"- {line}")

    # ── 차트: 기간 총원 추이 + 채팅방별 현황 ────────────────────
    st.divider()
    fig_trend = period_total_trend(df_period, date_from, date_to)
    fig_snap  = room_snapshot_chart(df_period, ROOMS)

    col_l, col_r = st.columns([3, 2])
    with col_l:
        if fig_trend:
            st.plotly_chart(fig_trend)
    with col_r:
        if fig_snap:
            st.plotly_chart(fig_snap)

    # ── 채팅방별 증감 성과표 ─────────────────────────────────────
    st.divider()
    st.markdown("#### 채팅방별 성과 요약")

    perf_rows = []
    for rn in sorted(ROOMS.keys()):
        rdf = df_period[df_period['room_num'] == rn].sort_values('date')
        if rdf.empty:
            continue
        cur = int(rdf.iloc[-1]['members'])
        prev = int(rdf.iloc[0]['members']) if len(rdf) > 1 else cur
        chg = cur - prev
        pct_r = round(chg / prev * 100, 1) if prev > 0 else 0
        perf_rows.append({
            '채팅방':    ROOMS.get(rn, f"채팅방 {rn}"),
            '현재 인원': f"{cur:,}명",
            '증감':      f"{chg:+,}명",
            '증감률':    f"{pct_r:+.1f}%",
            '평가':      "📈" if chg > 0 else ("📉" if chg < 0 else "➡️"),
            '_members':  cur,
            '_change':   chg,
        })

    if perf_rows:
        perf_df = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith('_')} for r in perf_rows])
        st.dataframe(perf_df, hide_index=True)

    # ── 광고비 요약 (데이터 있을 때만) ──────────────────────────
    ad_rows = []
    if period_spend > 0 and not df_adspend.empty:
        st.divider()
        st.markdown("#### 광고비 집행 내역")
        pa = df_adspend[
            (df_adspend['date'] >= first_date) & (df_adspend['date'] <= last_date)
        ].copy()
        if not pa.empty:
            by_ch = pa.groupby('channel')['spend'].sum().reset_index()
            by_ch.columns = ['채널', '집행 금액(원)']
            by_ch['비중'] = (by_ch['집행 금액(원)'] / by_ch['집행 금액(원)'].sum() * 100).round(1).astype(str) + '%'
            for _, row in by_ch.iterrows():
                ad_rows.append({'채널': row['채널'], '집행 금액(원)': f"{int(row['집행 금액(원)']):,}", '비중': row['비중']})
            by_ch_disp = by_ch.copy()
            by_ch_disp['집행 금액(원)'] = by_ch_disp['집행 금액(원)'].apply(lambda x: f"{int(x):,}")
            st.dataframe(by_ch_disp, hide_index=True)

    # ── 운영 종료 채팅방 비교 (선택) ────────────────────────────
    st.divider()
    df_arch_rep = load_archived_rooms()
    archived_report_rows = []

    if not df_arch_rep.empty:
        include_archived = st.checkbox(
            "🗂️ 종료 채팅방 비교 데이터 보고서에 포함",
            value=False,
            help="비교 분석이 필요할 때만 체크하세요. 기본적으로는 현재 운영 중인 채팅방만 표시됩니다.",
            key="report_include_archived",
        )
        if include_archived:
            st.caption(f"종료 채팅방 {len(df_arch_rep)}개가 아래 보고서에 포함됩니다.")
            _rep_members_by_room = {
                rn_: grp for rn_, grp in df.groupby('room_num')
            } if not df.empty else {}

            for _, ar in df_arch_rep.sort_values('room_num').iterrows():
                rn = int(ar['room_num'])
                rname = ar['room_name']
                arch_dt = str(ar.get('archived_date', '') or '')
                _raw = ar.get('actual_close_date', '')
                actual_dt = '' if pd.isna(_raw) else str(_raw).strip()
                final_m = int(ar.get('final_members', 0))
                reason = str(ar.get('archive_reason', '운영 종료') or '운영 종료')

                rdf = _rep_members_by_room.get(rn, pd.DataFrame())
                if not rdf.empty:
                    rdf = rdf.sort_values('date')
                peak_m  = int(rdf['members'].max())   if not rdf.empty else final_m
                op_days = int((rdf['date'].max() - rdf['date'].min()).days) + 1 if len(rdf) > 1 else 1
                net     = final_m - (int(rdf.iloc[0]['members']) if not rdf.empty else final_m)
                close_display = actual_dt if actual_dt else arch_dt

                archived_report_rows.append({
                    '채팅방':     rname,
                    '실제 종료일': close_display,
                    '처리일':     arch_dt,
                    '최종 인원':  final_m,
                    '최고 인원':  peak_m,
                    '순증감':     net,
                    '운영 기간':  op_days,
                    '종료 사유':  reason,
                })

            arch_disp_df = pd.DataFrame(archived_report_rows)
            arch_disp_df['최종 인원'] = arch_disp_df['최종 인원'].apply(lambda x: f"{x:,}명")
            arch_disp_df['최고 인원'] = arch_disp_df['최고 인원'].apply(lambda x: f"{x:,}명")
            arch_disp_df['순증감']    = arch_disp_df['순증감'].apply(lambda x: f"{x:+,}명")
            arch_disp_df['운영 기간'] = arch_disp_df['운영 기간'].apply(lambda x: f"{x:,}일")
            st.dataframe(arch_disp_df, hide_index=True)

    # ── HTML 보고서 다운로드 ─────────────────────────────────────
    st.divider()
    from report_generator import generate_html_report
    import plotly.io as _pio

    def _fig_to_fragment(fig) -> str:
        """Plotly figure → HTML 조각 (plotly.js 외부 참조, div만 반환)."""
        if fig is None:
            return ""
        try:
            return _pio.to_html(
                fig,
                include_plotlyjs=False,
                full_html=False,
                config={"displayModeBar": False, "responsive": True},
            )
        except Exception:
            return ""

    _snap_fragment  = _fig_to_fragment(fig_snap)
    _trend_fragment = _fig_to_fragment(fig_trend)

    # 전주/전월/전분기 비교 데이터 (보고서용)
    def _ref_snap(delta_days: int):
        ref = pd.Timestamp(last_date) - pd.Timedelta(days=delta_days)
        cands = df[df['date'] <= ref.date()]
        if cands.empty:
            return None, None
        nearest = cands['date'].max()
        return int(df[df['date'] == nearest]['members'].sum()), str(nearest)

    _comparison_rows = []
    for _label, _days in [("전주 대비 (7일)", 7), ("전월 대비 (30일)", 30), ("전분기 대비 (90일)", 90)]:
        _ref_total, _ref_date = _ref_snap(_days)
        if _ref_total and _ref_total > 0:
            _cd = total_now - _ref_total
            _cp = round(_cd / _ref_total * 100, 1)
            _comparison_rows.append({'label': _label, 'diff': _cd, 'pct': _cp, 'ref_date': _ref_date})

    # 전환 퍼널 (등록 데이터가 있는 기수만 보고서에 포함)
    _funnel_rows = None
    try:
        _fdf = cohort_funnel_data(df, load_campaigns(), load_enrollments(), rooms=ROOMS)
        if not _fdf.empty:
            _fd = _fdf[_fdf['conversion'].notna()]
            if not _fd.empty:
                _funnel_rows = [{
                    'label': f"{r['product']} {r['cohort']}",
                    'webinar_peak': int(r['webinar_peak']),
                    'enrolled': int(r['enrolled']),
                    'conversion': float(r['conversion']),
                    'revenue': int(r['revenue']),
                } for _, r in _fd.iterrows()]
    except Exception:
        _funnel_rows = None

    report_html = generate_html_report(
        period_label=period_label,
        first_date=first_date,
        last_date=last_date,
        total_now=total_now,
        diff=diff,
        pct=pct,
        period_spend=period_spend,
        conv_rate=conv_rate,
        insight_lines=insight_lines,
        perf_rows=perf_rows,
        ad_rows=ad_rows if ad_rows else None,
        chart_snap_html=_snap_fragment  or None,
        chart_trend_html=_trend_fragment or None,
        comparison_rows=_comparison_rows or None,
        archived_rows=archived_report_rows or None,
        funnel_rows=_funnel_rows,
    )
    # PDF 보고서 (대기업 업무 보고서 양식) — 서버에서 직접 생성
    _pdf_bytes = None
    try:
        from pdf_report import generate_pdf_report
        # 기간 총원 추이 시리즈 (일자별 총원)
        _trend_series = [
            (str(d), int(df_period[df_period['date'] == d]['members'].sum()))
            for d in sorted(df_period['date'].unique())
        ]
        _mark = None
        if _change_breakdown and _change_breakdown['archived_detail']:
            _md = _change_breakdown['archived_detail'][0]['date']
            _mark = (_md, "방 종료")
        # 종합 전략 요약 (전략 브리핑 + 상품군 통합표) — PDF 자동 삽입
        _strategy_rows = [(_t, _b) for _ic, _t, _b in _strategy_briefing()]
        _pm = _product_master_table()
        _product_master = _pm.to_dict('records') if not _pm.empty else None
        # 고객·전망 지표
        _customer_forecast = None
        try:
            _rp = load_cust_repeat_dist()
            _prr = load_cust_product_repeat()
            _mnr = load_cust_monthly_new_repeat()
            _xs = load_cust_cross_sell()
            _perf2 = load_monthly_performance()
            if not _rp.empty:
                _tc = int(_rp['customers'].sum())
                _rc = int(_rp[_rp['bucket'] != '1회']['customers'].sum())
                _nr = int(_mnr['new_revenue'].sum()) if not _mnr.empty else 0
                _rr2 = int(_mnr['repeat_revenue'].sum()) if not _mnr.empty else 0
                _rrm = 0
                if not _perf2.empty:
                    _cpl = _perf2[_perf2['month'] < date.today().strftime('%Y-%m')]
                    _rrm = _cpl['revenue'].tail(3).mean() if len(_cpl) >= 3 else 0
                _customer_forecast = {
                    'repeat_rate': _rc / _tc * 100 if _tc else 0,
                    'repeat_rev_share': _rr2 / (_nr + _rr2) * 100 if (_nr + _rr2) else 0,
                    'avg_ltv': int(_prr['avg_ltv'].mean()) if not _prr.empty else 0,
                    'cross_sell': float(_xs['rate'].max()) if not _xs.empty else 0,
                    'runrate_month': _rrm,
                    'runrate_year': _rrm * 12,
                }
        except Exception:
            _customer_forecast = None
        _pdf_bytes = generate_pdf_report(
            period_label=period_label,
            first_date=str(first_date), last_date=str(last_date),
            total_now=total_now, diff=diff, pct=pct,
            period_spend=period_spend, conv_rate=conv_rate,
            insight_lines=insight_lines, perf_rows=perf_rows,
            comparison_rows=_comparison_rows or None,
            funnel_rows=_funnel_rows,
            archived_rows=archived_report_rows or None,
            trend_series=_trend_series,
            change_breakdown=_change_breakdown,
            trend_mark=_mark,
            strategy_rows=_strategy_rows or None,
            product_master=_product_master,
            customer_forecast=_customer_forecast,
        )
    except Exception as _e:
        _pdf_bytes = None
        _pdf_err = str(_e)

    _fname = f"채팅방_모객전환_보고서_{period_label.replace(' ', '_').replace('~', '-')}_{date.today()}"
    dc1, dc2 = st.columns(2)
    with dc1:
        if _pdf_bytes:
            st.download_button(
                label="📄 PDF 보고서 다운로드 (바로 출력용)",
                data=_pdf_bytes,
                file_name=f"{_fname}.pdf",
                mime="application/pdf",
                width='stretch',
                type="primary",
            )
        else:
            st.button("📄 PDF 생성 실패", disabled=True, width='stretch')
            st.caption(f"PDF 엔진 오류: {_pdf_err if '_pdf_err' in dir() else '알 수 없음'}")
    with dc2:
        st.download_button(
            label="🖨️ HTML 보고서 (인터랙티브 차트)",
            data=report_html.encode("utf-8"),
            file_name=f"{_fname}.html",
            mime="text/html",
            width='stretch',
        )


# ── 탭 4: 채팅방 설정 ────────────────────────────────────────────

def tab_campaign():
    ROOMS = load_rooms()
    ROOM_NUMBERS = sorted(ROOMS.keys())
    st.header("채팅방 설정")

    # ── 채팅방 관리 ────────────────────────────────────────────
    with st.expander("➕ 채팅방 추가 / 수정 / 삭제", expanded=not bool(ROOMS)):
        st.caption("채팅방 번호와 이름을 등록하세요. 번호가 같으면 이름이 수정됩니다.")

        with st.form("room_form"):
            col_a, col_b = st.columns(2)
            with col_a:
                new_room_num = st.number_input("채팅방 번호", min_value=1, step=1, value=1)
            with col_b:
                new_room_name = st.text_input("채팅방 이름", placeholder="예) 황금후추 돈버는 사주방 1기")
            if st.form_submit_button("저장", type="primary", width='stretch'):
                if not new_room_name.strip():
                    st.error("채팅방 이름을 입력해주세요.")
                else:
                    save_room(int(new_room_num), new_room_name.strip())
                    st.success(f"채팅방 {int(new_room_num)} — '{new_room_name.strip()}' 저장 완료")
                    st.rerun()

        if ROOMS:
            st.divider()
            st.markdown("**현재 등록된 채팅방**")
            st.caption("✏️ 수정 — 번호·이름 모두 변경 가능 / 🗑️ — 즉시 삭제")

            for rn in sorted(ROOMS.keys()):
                editing = (st.session_state._editing_room == rn)

                if editing:
                    # ── 인라인 수정 폼 ────────────────────────────────
                    with st.container(border=True):
                        ec1, ec2, ec3, ec4 = st.columns([1, 1, 4, 2])
                        with ec1:
                            new_rn = st.number_input(
                                "번호", min_value=1, step=1, value=rn,
                                key=f"edit_num_{rn}", label_visibility="collapsed"
                            )
                        with ec2:
                            st.markdown(f"<small style='color:grey'>현재: {rn}</small>",
                                        unsafe_allow_html=True)
                        with ec3:
                            new_name = st.text_input(
                                "이름", value=ROOMS[rn],
                                key=f"edit_name_{rn}", label_visibility="collapsed"
                            )
                        with ec4:
                            cs, cc = st.columns(2)
                            with cs:
                                if st.button("✅", key=f"save_{rn}",
                                             help="저장", width='stretch'):
                                    name_to_save = new_name.strip() or ROOMS[rn]
                                    if int(new_rn) != rn:
                                        # 번호 변경: 기존 삭제 후 새 번호로 등록
                                        delete_room(rn)
                                        save_room(int(new_rn), name_to_save)
                                        st.toast(f"채팅방 {rn} → {int(new_rn)} 변경 완료",
                                                 icon="✅")
                                    else:
                                        save_room(rn, name_to_save)
                                        st.toast(f"채팅방 {rn} 이름 수정 완료", icon="✅")
                                    st.session_state._editing_room = None
                                    load_rooms.clear()
                                    st.rerun()
                            with cc:
                                if st.button("❌", key=f"cancel_{rn}",
                                             help="취소", width='stretch'):
                                    st.session_state._editing_room = None
                                    st.rerun()
                else:
                    # ── 일반 행 ───────────────────────────────────────
                    col_num, col_name, col_edit, col_del = st.columns([1, 5, 1, 1])
                    with col_num:
                        st.write(f"**{rn}**")
                    with col_name:
                        st.write(ROOMS[rn])
                    with col_edit:
                        if st.button("✏️", key=f"edit_{rn}",
                                     help=f"채팅방 {rn} 수정"):
                            st.session_state._editing_room = rn
                            st.rerun()
                    with col_del:
                        if st.button("🗑️", key=f"del_{rn}",
                                     help=f"채팅방 {rn} 삭제"):
                            delete_room(rn)
                            st.toast(f"채팅방 {rn} 삭제 완료", icon="🗑️")
                            st.rerun()

    if not ROOMS:
        st.info("위에서 채팅방을 먼저 추가해주세요.")
        return

    st.divider()
    st.caption("각 채팅방이 어떤 강의 모객을 위해 운영되는지 입력하고 이력을 관리해요.")

    # ── 신규 캠페인 등록 ───────────────────────────────────────
    st.subheader("강의 정보 등록 / 변경")

    campaigns = get_current_campaigns()

    with st.form("campaign_form"):
        col1, col2 = st.columns(2)

        with col1:
            room_num = st.selectbox(
                "채팅방",
                options=ROOM_NUMBERS,
                format_func=lambda x: f"{ROOMS.get(x, f'채팅방 {x}')} (현재: {campaigns.get(x, {}).get('campaign_name', '미등록')})",
            )
            campaign_name = st.text_input(
                "강의명",
                placeholder="예) 돈타공 5기",
            )
            product = st.selectbox("상품 구분", options=PRODUCT_OPTIONS)

        with col2:
            cohort = st.text_input(
                "기수 / 회차",
                placeholder="예) 5기, 3회차",
            )
            start_date = st.date_input("모객 시작일", value=date.today())
            lecture_start_input = st.date_input(
                "개강일 (선택)",
                value=None,
                help="개강일을 입력하면 🎓 강의 분석 탭에서 잔류율 분석이 활성화됩니다.",
            )
            target_count = st.number_input(
                "목표 인원",
                min_value=0,
                value=0,
                step=100,
                help="0이면 목표 미설정. 추이 그래프에 점선으로 표시됩니다.",
            )
            memo = st.text_area(
                "메모",
                placeholder="특이사항 등 자유롭게 입력",
                height=80,
            )

        submitted = st.form_submit_button("💾 저장하기", type="primary", width='stretch')

        if submitted:
            if not campaign_name.strip():
                st.error("강의명을 입력해주세요.")
            else:
                save_campaign(
                    room_num=room_num,
                    campaign_name=campaign_name.strip(),
                    product=product,
                    cohort=cohort.strip(),
                    start_date=str(start_date),
                    memo=memo.strip(),
                    target_count=int(target_count),
                    lecture_start_date=str(lecture_start_input) if lecture_start_input else "",
                )
                st.success(f"✅ {ROOMS.get(room_num)} — '{campaign_name}' 저장 완료")
                st.rerun()

    st.divider()

    # ── 현재 진행 중인 캠페인 목록 ────────────────────────────
    st.subheader("현재 진행 중인 강의 목록")
    campaigns = get_current_campaigns()

    if not campaigns:
        st.info("등록된 강의가 없습니다. 위 양식에서 등록해주세요.")
    else:
        camp_rows = []
        for rn, info in sorted(campaigns.items()):
            camp_rows.append({
                '방 번호': rn,
                '채팅방': ROOMS.get(rn, f'채팅방 {rn}'),
                '강의명': info.get('campaign_name', '-'),
                '상품': info.get('product', '-'),
                '기수': info.get('cohort', '-'),
                '시작일': info.get('start_date', '-'),
                '메모': info.get('memo', '-'),
            })
        st.dataframe(pd.DataFrame(camp_rows), hide_index=True)

        # ── 개강일 빠른 업데이트 ─────────────────────────────────
        with st.expander("📅 개강일 설정 (강의 분석 잔류율 활성화)", expanded=False):
            st.caption("개강일을 등록하면 🎓 강의 분석 탭에서 개강 후 잔류율 차트가 표시됩니다.")
            upd_room = st.selectbox(
                "채팅방 선택",
                options=list(sorted(campaigns.keys())),
                format_func=lambda x: f"{ROOMS.get(x, f'채팅방 {x}')} — {campaigns[x].get('campaign_name', '')}",
                key="upd_lsd_room",
            )
            _cur_lsd = campaigns.get(upd_room, {}).get('lecture_start_date', '')
            _lsd_val = st.date_input(
                "개강일",
                value=pd.to_datetime(_cur_lsd).date() if _cur_lsd and str(_cur_lsd).strip() else None,
                key="upd_lsd_date",
            )
            if st.button("개강일 저장", key="upd_lsd_btn", type="primary"):
                update_lecture_start_date(upd_room, str(_lsd_val) if _lsd_val else "")
                st.success(f"개강일 저장 완료: {_lsd_val}")
                st.rerun()

        # ── 강의 종료 처리 ────────────────────────────────────────
        with st.expander("🏁 강의 종료 처리 (캠페인만 종료, 채팅방 유지)", expanded=False):
            end_room = st.selectbox(
                "종료할 채팅방",
                options=list(sorted(campaigns.keys())),
                format_func=lambda x: f"{ROOMS.get(x, f'채팅방 {x}')} — {campaigns[x].get('campaign_name', '')}",
                key="end_room_select",
            )
            if st.button("강의 종료 처리", key="end_btn"):
                end_campaign(end_room)
                st.success(f"'{campaigns[end_room].get('campaign_name')}' 종료 처리 완료")
                st.rerun()

    # ── 채팅방 운영 종료 처리 ─────────────────────────────────
    st.divider()
    st.subheader("🚪 채팅방 운영 종료 처리")
    st.caption(
        "채팅방에서 나갈 때 사용하세요. 활성 목록에서 제거되지만 **인원 이력·강의 기록은 모두 보존**됩니다. "
        "🎓 강의 분석 탭에서 이후에도 확인 가능합니다."
    )

    if ROOMS:
        df_for_final = load_all()
        arch_room = st.selectbox(
            "운영 종료할 채팅방",
            options=sorted(ROOMS.keys()),
            format_func=lambda x: f"{ROOMS.get(x, f'채팅방 {x}')} (채팅방 {x})",
            key="arch_room_select",
        )
        arch_reason = st.text_input(
            "종료 사유 (선택)",
            placeholder="예) 강의 완료, 채팅방 통합, 운영 중단",
            key="arch_reason_input",
        )
        arch_actual_close = st.date_input(
            "실제 종료일 (선택) — 처리일과 다를 경우 입력",
            value=None,
            key="arch_actual_close_input",
            help="채팅방을 실제로 나간 날짜. 비워두면 오늘(처리일)이 기준이 됩니다.",
        )

        # 최종 인원 자동 조회
        _final_m = 0
        if not df_for_final.empty:
            _rdf = df_for_final[df_for_final['room_num'] == arch_room].sort_values('date')
            if not _rdf.empty:
                _final_m = int(_rdf.iloc[-1]['members'])
        st.caption(f"마지막 기록 인원: **{_final_m:,}명** (자동 저장됩니다)")

        if st.button("🚪 운영 종료 처리", type="primary", key="arch_btn"):
            st.session_state['_pending_archive'] = arch_room

        if st.session_state.get('_pending_archive') == arch_room:
            st.error(
                f"**{ROOMS.get(arch_room)} (채팅방 {arch_room})** 를 운영 종료 처리합니다. "
                "활성 채팅방 목록에서 제거되며 인원 입력 폼에서 사라집니다. 계속하시겠습니까?"
            )
            ca, cb = st.columns(2)
            if ca.button("✅ 확인", type="primary", width='stretch', key="arch_confirm"):
                archive_room(
                    room_num=arch_room,
                    room_name=ROOMS.get(arch_room, f"채팅방 {arch_room}"),
                    final_members=_final_m,
                    reason=arch_reason.strip() or "운영 종료",
                    actual_close_date=str(arch_actual_close) if arch_actual_close else "",
                )
                st.session_state['_pending_archive'] = None
                st.success(f"✅ {ROOMS.get(arch_room)} 운영 종료 처리 완료. 이력은 🎓 강의 분석 탭에서 확인하세요.")
                st.rerun()
            if cb.button("❌ 취소", width='stretch', key="arch_cancel"):
                st.session_state['_pending_archive'] = None
                st.rerun()
    else:
        st.info("등록된 채팅방이 없습니다.")

    st.divider()

    # ── 전체 이력 조회 ─────────────────────────────────────────
    st.subheader("모객 이력 전체 조회")

    all_rooms_for_hist = load_all_room_names()
    _hist_options = sorted(all_rooms_for_hist.keys())
    history_room = st.selectbox(
        "채팅방 선택 (종료 채팅방 포함)",
        options=_hist_options,
        format_func=lambda x: all_rooms_for_hist.get(x, f"채팅방 {x}"),
        key="history_room_select",
    )

    history_df = get_history(history_room)
    if history_df.empty:
        st.info("이력이 없습니다.")
    else:
        history_df['is_current'] = history_df['is_current'].apply(lambda x: '✅ 진행 중' if x else '종료')
        disp_cols = ['room_num', 'campaign_name', 'product', 'cohort',
                     'start_date', 'lecture_start_date', 'end_date', 'is_current', 'memo']
        history_df = history_df[[c for c in disp_cols if c in history_df.columns]]
        col_map = {'room_num': '방 번호', 'campaign_name': '강의명', 'product': '상품',
                   'cohort': '기수', 'start_date': '모객 시작', 'lecture_start_date': '개강일',
                   'end_date': '종료일', 'is_current': '상태', 'memo': '메모'}
        history_df = history_df.rename(columns=col_map)
        st.dataframe(history_df, hide_index=True)


# ── 탭 5: 데이터 관리 ─────────────────────────────────────────────

def tab_data():
    ROOMS = load_rooms()
    ROOM_NUMBERS = sorted(ROOMS.keys())
    st.header("데이터 관리")
    df = load_all()

    # ── 🔄 자동 갱신 상태 ─────────────────────────────────────
    _rs = load_refresh_status()
    if not _rs.empty:
        _r0 = _rs.iloc[-1]
        try:
            _lr = pd.to_datetime(_r0['last_run'])
            _hrs = (pd.Timestamp.now() - _lr).total_seconds() / 3600
        except Exception:
            _hrs = None
        _msg = (f"마지막 자동 갱신 **{_r0['last_run']}** · "
                f"시장 신호 {_r0['market_signals']} · 주문 집계 {_r0['order_aggregates']}")
        # 'rooms'는 나중에 추가된 컬럼이라 옛 기록엔 없다 — 있을 때만 붙인다.
        if str(_r0.get('rooms', '')).strip():
            _msg += f" · 방목록 {_r0['rooms']}"
        _al_st = str(_r0.get('alerts', '')).strip()
        if _al_st:
            _msg += f" · 슬랙 알림 {_al_st}"
        if _hrs is not None and _hrs > 36:
            st.warning(f"⚠️ 자동 갱신이 {_hrs/24:.0f}일째 돌지 않았습니다 — {_msg}")
        else:
            st.success(f"🔄 {_msg}")
        st.caption("하루 3회(09:10·14:10·20:10) + 맥 켤 때 자동 실행. "
                   "주문 엑셀과 `오카방의 모든 것.xlsx`는 `gp-funnel-v2/inbox/`에 "
                   "넣어두면 자동 반영됩니다.")
        # 알림 자동 발송은 이 맥에서 도는 작업이라, 사이트(Cloud) 설정이 아니라
        # 맥의 secrets.toml을 봐야 한다. 꺼져 있으면 사이트를 안 여는 동안
        # 🔴 경고가 아무에게도 전달되지 않으므로 여기서 밝혀 둔다.
        if _al_st == "미설정":
            st.caption("🔔 슬랙 웹훅이 없어 위험 알림을 **맥 알림으로** 보내고 "
                       "있습니다 — 갱신용 맥을 켜 둔 동안에는 도착합니다. "
                       "맥의 `gp-funnel-v2/.streamlit/secrets.toml`에 "
                       "`slack_webhook_url`을 넣으면 팀 슬랙으로 바뀝니다.")
        elif _al_st in ("실패", "전송실패"):
            st.caption(f"🔔 위험 알림 자동 발송이 **{_al_st}** 상태입니다 — "
                       "웹훅 주소를 확인하세요. 고치기 전까지는 🔴 경고가 "
                       "사이트 밖으로 나가지 않습니다.")

    # ── 📅 데이터 현황 (신선도) ───────────────────────────────
    _ds = load_data_sources()
    if not _ds.empty:
        st.subheader("📅 데이터 현황 · 신선도")
        st.caption("사이트가 쓰는 데이터별 **기준 시점·출처·갱신 방법**입니다. "
                   "🟢 최신 · 🟡 스냅샷 · 🔴 갱신 권장 — 오래된 데이터를 제때 갱신하세요.")
        _today = date.today()
        _mem_last = str(df['date'].max()) if not df.empty else None

        def _asof_days(a):
            a = str(a).strip()
            if a == 'auto':
                if _mem_last:
                    try:
                        return (_today - pd.to_datetime(_mem_last).date()).days, _mem_last
                    except Exception:
                        return None, _mem_last
                return None, '—'
            try:
                _d = pd.to_datetime(a).date()
                return (_today - _d).days, a
            except Exception:
                return None, a

        _rows_html = ""
        _stale_rows = []
        for _, r in _ds.iterrows():
            _days, _disp = _asof_days(r['as_of'])
            # 주문 명단은 매일 매출이 쌓이는 데이터라 45일 기준이 너무 느슨하다.
            # 한 달만 밀려도 '마지막 달이 통째로 부분월'이 되어 매출·전환·전망이
            # 전부 낮게 나온다(실제로 27일 밀린 채 🟢 최신으로 표시되고 있었다).
            _live = '강의별_리스트' in str(r['source'])
            _g, _y = (10, 30) if _live else (45, 120)
            if '미사용' in str(r['dataset']):
                # 화면이 쓰지 않는 데이터를 '갱신 권장'으로 재촉하면, 자료를
                # 어렵게 구해 와도 반영될 곳이 없다 — 헛수고를 시키지 않는다.
                # 단 **정말 안 쓰는 데이터에만** 붙여야 한다. 채널 metrics에
                # 잘못 붙어, 마케팅 탭이 2025-06 숫자로 ROAS·CPA를 그리는 동안
                # 이 표는 "갱신 안 해도 된다"고 안내하던 적이 있다(v4.77에서 정정).
                _badge, _col = "⚪ 미사용", "#8A93A3"
            elif _days is None:
                _badge, _col = "—", "#8A93A3"
            elif _days <= _g:
                _badge, _col = "🟢 최신", "#2E7D5B"
            elif _days <= _y:
                _badge, _col = "🟡 스냅샷", "#B77A1B"
            else:
                _badge, _col = "🔴 갱신 권장", "#BC4A38"
                _stale_rows.append(f"{str(r['dataset']).split('(')[0].strip()}({_disp})")
            _age = f"{_days}일 전" if isinstance(_days, int) else ""
            _rows_html += (
                f'<tr><td style="opacity:.6">{r["category"]}</td>'
                f'<td><b>{r["dataset"]}</b><div style="font-size:11px;opacity:.6">{r["source"]}</div></td>'
                f'<td style="white-space:nowrap">{_disp}<div style="font-size:11px;opacity:.55">{_age}</div></td>'
                f'<td style="color:{_col};font-weight:700;white-space:nowrap">{_badge}</td>'
                f'<td style="font-size:12px;opacity:.75">{r["refresh"]}</td></tr>')
        st.markdown(
            '<table class="gp-dtbl" style="width:100%;border-collapse:collapse;font-size:13px">'
            '<thead><tr style="text-align:left">'
            '<th>구분</th><th>데이터 · 출처</th><th>기준 시점</th><th>상태</th><th>갱신 방법</th></tr></thead>'
            f'<tbody>{_rows_html}</tbody></table>',
            unsafe_allow_html=True)
        # 목록을 손으로 적어 두면 판정과 어긋난다 — 실제로 배지는 ⚪ 미사용인데
        # 문구는 "채널 metrics가 오래됐다"고 지목하고 있었다. 판정에서 만든다.
        if _stale_rows:
            st.warning(f"⚠️ 갱신 권장 데이터 **{len(_stale_rows)}종** — "
                       + " · ".join(_stale_rows)
                       + "\n\n최신 자료를 확보해 갱신하면 분석 정확도가 올라갑니다.")
        # ── 📥 주문 명단 올리기 ────────────────────────────────
        # 지금까지 갱신 경로가 '엑셀 받기 → inbox 폴더 복사 → 터미널 명령'이라
        # 특정 맥에서만 가능했고, 그래서 27일이나 밀린 채 방치됐다. 파일을 여기
        # 올리면 브라우저에서 바로 끝나게 한다.
        _ao_up = order_asof()
        _gap_up = (date.today() - _ao_up).days if _ao_up else None
        with st.expander("📥 주문 명단 올리기 — 매출·고객·전환 집계 자동 갱신",
                         expanded=bool(_gap_up and _gap_up >= 14)):
            st.caption("아임웹 → 강의 → 강의별 집계 → **‘강의별 리스트’ 엑셀**을 받아 그대로 올리면 "
                       "매출·고객·리텐션·무료특강 등 **주문 기반 집계가 한 번에 갱신**됩니다. "
                       "터미널도, 담당자 전달도 필요 없습니다.")
            st.caption("🔒 원본 파일은 **저장하지 않습니다** — 읽어서 집계 숫자만 만들고 버립니다. "
                       "이름·연락처 같은 개인정보는 어디에도 남지 않습니다.")
            if _ao_up:
                st.caption(f"현재 기준일: **{_ao_up}**"
                           + (f" ({_gap_up}일 경과)" if _gap_up is not None else ""))
            _up = st.file_uploader("강의별 리스트 엑셀 (.xlsx)", type=['xlsx'], key="ord_up")
            if _up is not None:
                try:
                    with st.spinner("주문 원본을 읽고 집계를 만드는 중…"):
                        _sm, _out = _parse_order_upload(_up.getvalue())
                except Exception as e:
                    _sm = _out = None
                    st.error(f"파일을 읽지 못했습니다 ({type(e).__name__}). "
                             "아임웹에서 받은 **‘강의별 리스트’ 원본 엑셀**이 맞는지 확인해 주세요 "
                             "— 시트 이름(sheet1)이나 컬럼(주문일·상품명·최종결제금액·주문자 이름/번호)이 "
                             "다르면 읽을 수 없습니다.")
                if _out:
                    _newest = _sm['last'].date()
                    _kpi_band([
                        ("📦 총 주문", f"{_sm['rows']:,}<small>건</small>", "무료 신청 포함"),
                        ("🎓 유료 결제", f"{_sm['paid']:,}<small>건</small>", f"고객 {_sm['custs']:,}명"),
                        ("💰 누적 매출", f"{_sm['revenue']/1e8:,.1f}<small>억원</small>", "유료 결제 합계"),
                        ("📅 마지막 주문", f"{_newest}", f"시작 {_sm['first'].date()}"),
                    ])
                    st.write("")
                    _mp_new = _out.get('monthly_performance.csv')
                    if _mp_new is not None and not _mp_new.empty:
                        st.markdown("**새로 들어올 최근 3개월**")
                        _pv = _mp_new.tail(3).copy()
                        _pv['매출'] = (_pv['revenue'] / 1e8).map(lambda v: f"{v:,.2f}억")
                        st.dataframe(_pv[['month', 'free_signups', 'paid_orders', '매출', 'conv_rate']]
                                     .rename(columns={'month': '월', 'free_signups': '무료 신청',
                                                      'paid_orders': '유료 결제', 'conv_rate': '전환율(%)'}),
                                     hide_index=True)
                    _ok_new = True
                    if _ao_up and _newest <= _ao_up:
                        _ok_new = st.checkbox(
                            f"⚠️ 이 파일의 마지막 주문({_newest})이 현재 기준일({_ao_up})보다 "
                            "최신이 아닙니다. 예전 파일을 올린 게 아닌지 확인하세요. "
                            "그래도 이 파일로 덮어쓰기", key="ord_old_ok")
                    if st.button("이 파일로 갱신하기", type="primary",
                                 disabled=not _ok_new, key="ord_apply"):
                        _pb = st.progress(0.0, text="저장 준비 중…")
                        _n = len(_out)

                        def _step(i, name):
                            _pb.progress(i / _n, text=f"{i}/{_n} 저장 중 — {name}")
                        _done, _tot, _fails = save_order_aggregates(_out, _newest, on_step=_step)
                        _pb.empty()
                        if _fails:
                            st.error(f"{_done}/{_tot}종만 저장됐습니다. 실패: {', '.join(_fails)} "
                                     "— 잠시 후 다시 시도해 주세요(기준일은 반영하지 않았습니다).")
                        else:
                            st.cache_data.clear()
                            st.success(f"✅ 집계 {_tot}종 갱신 완료 — 기준일 {_newest}. "
                                       "매출·전환·고객·리텐션·전망이 모두 최신 주문 기준으로 "
                                       "다시 계산됩니다.")
                            st.caption("※ 지역 분포는 주문 명단이 아니라 **배송지 리포트**에서 "
                                       "오는 별도 자료라 이 갱신으로 바뀌지 않습니다.")
                            st.caption("화면을 새로고침하면 반영된 값이 보입니다.")
        st.caption("터미널에서 갱신: `python3 scripts/refresh_order_aggregates.py --write`")

        # ── 📥 자료 수집·갱신 가이드 ──────────────────────────
        with st.expander("📥 자료 수집·갱신 가이드 — 무엇을·어디서·어떻게"):
            st.caption("각 데이터를 최신으로 유지하려면 아래 자료를 모아 전달(또는 입력)하면 됩니다. "
                       "🟢 자동/폼 입력 · 🟡 담당자에게 전달(수작업 이관).")
            _guide = [
                ("🟢 주문 명단 (매출·고객·리텐션·무료특강 15종)",
                 "아임웹 → 강의 → 강의별 집계 → **‘강의별 리스트’ 엑셀 다운로드**(주문일·상품·금액·주문자 포함)",
                 "파일을 담당자에게 전달 → `refresh_order_aggregates.py` 1회 실행이면 15종 집계 자동 갱신. "
                 "개인정보는 저장되지 않고 집계만 만듭니다."),
                ("🟡 강의 집계 (매출·수강생·유료 단계)",
                 "골드포털 → 강의 집계 보고서 **4종(돈사공·돈타공·돈초부공·돈빌공) PDF 생성**",
                 "PDF 4개를 담당자에게 전달 → 기수별 매출·수강생·유료 단계 전환 갱신."),
                ("🟡 광고비 (캠페인별·라이브별)",
                 "통합시트 → 라이브(캠페인)별 광고비 표 (무료강의명·실제판매강의명·광고비·매출)",
                 "해당 표(캡처/시트 링크)를 전달 → 상품군별 광고 ROI·수확체감 갱신."),
                ("🟢 월별 광고비",
                 "광고 플랫폼(메타·구글 등) → **월별 지출 총액**",
                 "📢 마케팅 분석 탭 → ‘월별 광고비 입력’ 폼에 직접 입력(또는 담당자에게 전달)."),
                ("🟡 지역 (배송지 분석) — 현재 낡음(2025-12)",
                 "골드포털 → 최신 기수 **배송지 지역 분석 리포트**(시도·기수별·도시)",
                 "리포트 이미지/파일을 전달 → 지역 분석 탭 전체 갱신."),
                ("🟡 채널 metrics — 현재 낡음(2025-06)",
                 "데이터시트 → **‘채널 metrics’ 탭**(일자별 채널별 광고비·세션·구매·매출)",
                 "최신 시트(링크/캡처)를 전달 → 채널별 효율 분석 갱신."),
                ("🟡 경쟁사 가격",
                 "경쟁사 조사 시트 → 강의 상품·판매가",
                 "갱신본을 전달 → 경쟁사 벤치마크 갱신."),
                ("🔔 슬랙 알림 (선택)",
                 "슬랙 → 채널에 **Incoming Webhook URL 발급**",
                 "Streamlit Cloud → Settings → Secrets **와** 갱신용 맥의 "
                 "`.streamlit/secrets.toml`에 `slack_webhook_url = \"...\"` 추가. "
                 "넣지 않아도 위험 알림은 갱신용 맥의 알림 센터로 갑니다."),
            ]
            _gh = ""
            for _t, _where, _how in _guide:
                _gh += (f'<tr><td style="white-space:nowrap"><b>{_t}</b></td>'
                        f'<td>{_where}</td><td style="opacity:.8">{_how}</td></tr>')
            st.markdown(
                '<table class="gp-dtbl" style="width:100%;border-collapse:collapse;font-size:13px">'
                '<thead><tr style="text-align:left"><th>데이터</th><th>어디서(수집)</th>'
                '<th>어떻게(전달·입력)</th></tr></thead>'
                f'<tbody>{_gh}</tbody></table>', unsafe_allow_html=True)
            st.info("💡 요약 — **주문 명단·월별 광고비**는 자동/폼으로 바로 반영되고, 나머지(강의 집계·광고비·"
                    "지역·채널·경쟁사)는 자료만 모아 전달하면 담당자가 이관합니다. "
                    "가장 시급한 건 🔴로 표시된 **지역·채널 데이터 최신화**입니다.")
        st.divider()

    # ── 누락 날짜 소급 입력 ───────────────────────────────────
    if not df.empty:
        from datetime import timedelta as _td2
        _first = df['date'].min()
        _days_total = (date.today() - _first).days + 1
        _all_range  = set(str(_first + _td2(days=i)) for i in range(_days_total))
        _entered    = set(df['date'].astype(str).unique())
        _missing    = sorted(_all_range - _entered, reverse=True)

        if _missing:
            with st.expander(f"📅 누락 날짜 소급 입력 ({len(_missing)}일 누락)", expanded=True):
                st.caption("아래 날짜는 데이터가 입력되지 않았습니다. 날짜를 선택하여 바로 소급 입력하세요.")

                _sel_missing = st.selectbox(
                    "소급 입력할 날짜 선택",
                    options=_missing,
                    key="missing_date_select",
                )

                # 해당 날짜 전일의 인원을 기본값으로
                _prev_date_cands = df[df['date'].astype(str) < _sel_missing]
                _backfill_prev = {}
                if not _prev_date_cands.empty:
                    _prev_nearest = _prev_date_cands['date'].max()
                    _bp = _prev_date_cands[_prev_date_cands['date'] == _prev_nearest]
                    _backfill_prev = {int(r['room_num']): int(r['members']) for _, r in _bp.iterrows()}

                st.markdown(f"**{_sel_missing} 인원 입력** — 전일({_backfill_prev and _prev_date_cands['date'].max() or '없음'}) 값으로 초기화됨")
                _bf_rows = [
                    {'채팅방번호': rn, '채팅방명': ROOMS.get(rn, f"채팅방 {rn}"), '인원수': _backfill_prev.get(rn, 0)}
                    for rn in ROOM_NUMBERS
                ]
                _bf_edited = st.data_editor(
                    pd.DataFrame(_bf_rows),
                    column_config={
                        '채팅방번호': st.column_config.NumberColumn(disabled=True),
                        '채팅방명':   st.column_config.TextColumn(disabled=True),
                        '인원수':     st.column_config.NumberColumn(min_value=0, step=1, required=True),
                    },
                    hide_index=True,
                    key=f"backfill_editor_{_sel_missing}",
                )
                if st.button("💾 소급 입력 저장", type="primary", key="backfill_save"):
                    _bf_data = [
                        {'room_num': int(r['채팅방번호']), 'room_name': str(r['채팅방명']), 'members': int(r['인원수'])}
                        for _, r in _bf_edited.iterrows() if int(r['인원수']) > 0
                    ]
                    if _bf_data:
                        with st.spinner("저장 중..."):
                            save_daily(_sel_missing, _bf_data)
                        load_all.clear()
                        st.success(f"✅ {_sel_missing} 소급 입력 완료 — {len(_bf_data)}개 채팅방")
                        st.rerun()
                    else:
                        st.warning("입력된 인원이 없습니다.")
        else:
            st.success(f"✅ 누락 날짜 없음 — {_first}부터 오늘까지 모든 날짜 입력 완료")

    st.divider()

    # ── 날짜별 데이터 수정 ─────────────────────────────────────
    st.subheader("날짜별 데이터 수정")
    st.caption("OCR 오류 등으로 잘못 저장된 데이터를 날짜를 선택해 직접 수정할 수 있습니다.")

    existing_dates = sorted(df['date'].astype(str).unique().tolist(), reverse=True) if not df.empty else []

    edit_mode = st.radio(
        "날짜 선택 방식",
        ["기존 날짜 수정", "새 날짜 직접 입력"],
        horizontal=True,
        key="edit_mode_radio",
    )

    if edit_mode == "기존 날짜 수정" and existing_dates:
        edit_date_str = st.selectbox("수정할 날짜", options=existing_dates, key="edit_date_select")
    else:
        edit_date_input = st.date_input("날짜 입력", value=date.today(), key="edit_date_new")
        edit_date_str = str(edit_date_input)

    # 해당 날짜의 현재 데이터 로드
    if not df.empty:
        df_edit = df[df['date'].astype(str) == edit_date_str]
        current = {int(row['room_num']): int(row['members']) for _, row in df_edit.iterrows()}
    else:
        current = {}

    # st.data_editor 기반 인라인 편집
    st.markdown(f"**{edit_date_str} 인원 수정** — 셀을 직접 클릭해 수정 후 저장 버튼을 누르세요.")
    editor_rows = [
        {'채팅방번호': rn, '채팅방명': ROOMS.get(rn, f"채팅방 {rn}"), '인원수': current.get(rn, 0)}
        for rn in ROOM_NUMBERS
    ]
    editor_df = pd.DataFrame(editor_rows)
    edited = st.data_editor(
        editor_df,
        column_config={
            '채팅방번호': st.column_config.NumberColumn(disabled=True),
            '채팅방명':   st.column_config.TextColumn(disabled=True),
            '인원수':     st.column_config.NumberColumn(min_value=0, step=1, required=True),
        },
        hide_index=True,
        key=f"data_editor_{edit_date_str}",
    )
    if st.button("💾 수정 저장", type="primary", key="data_editor_save"):
        room_data = [
            {'room_num': int(row['채팅방번호']), 'room_name': str(row['채팅방명']), 'members': int(row['인원수'])}
            for _, row in edited.iterrows() if int(row['인원수']) > 0
        ]
        if room_data:
            with st.spinner("저장 중..."):
                save_daily(edit_date_str, room_data)
            st.success(f"✅ {edit_date_str} 데이터 수정 완료 — {len(room_data)}개 채팅방")
            st.rerun()
        else:
            st.warning("입력된 인원이 없습니다.")

    st.divider()

    if df.empty:
        st.info("데이터가 없습니다.")
        return

    # ── 전체 데이터 표시 (필터 포함) ──────────────────────────
    st.subheader("전체 데이터")
    _fcol1, _fcol2 = st.columns(2)
    with _fcol1:
        _date_opts = ['전체'] + sorted(df['date'].astype(str).unique().tolist(), reverse=True)
        _sel_date = st.selectbox("날짜 필터", options=_date_opts, key="data_filter_date")
    with _fcol2:
        _room_opts = ['전체'] + [f"{rn} — {nm}" for rn, nm in sorted(ROOMS.items())]
        _sel_room = st.selectbox("채팅방 필터", options=_room_opts, key="data_filter_room")

    show = df.copy()
    if _sel_date != '전체':
        show = show[show['date'].astype(str) == _sel_date]
    if _sel_room != '전체':
        _rn = int(_sel_room.split(' — ')[0])
        show = show[show['room_num'] == _rn]
    show = show.sort_values(['date', 'room_num'], ascending=[False, True]).reset_index(drop=True)
    st.dataframe(show, hide_index=True)
    st.caption(f"{len(show)}행 표시 중 (전체 {len(df)}행)")

    col_csv, col_excel, col_zip = st.columns(3)

    with col_csv:
        csv_bytes = df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            "📥 CSV 다운로드",
            data=csv_bytes,
            file_name=f"채팅방_인원_{date.today()}.csv",
            mime='text/csv',
            width='stretch',
        )

    with col_excel:
        from excel_export import generate_excel
        _campaigns  = get_current_campaigns()
        _df_conv    = load_conversions()
        _df_adspend = load_adspend()
        _df_content = load_content()
        excel_bytes = generate_excel(
            df, _campaigns,
            df_conv=_df_conv,
            df_adspend=_df_adspend,
            df_content=_df_content,
            rooms=ROOMS,
        )
        st.download_button(
            "📊 Excel 보고서 다운로드",
            data=excel_bytes,
            file_name=f"채팅방_인원_보고서_{date.today()}.xlsx",
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            width='stretch',
        )

    with col_zip:
        import zipfile, io as _io
        _zip_buf = _io.BytesIO()
        with zipfile.ZipFile(_zip_buf, 'w', zipfile.ZIP_DEFLATED) as _zf:
            _zip_data = {
                '인원_members.csv':     df,
                '강의_campaigns.csv':   load_campaigns(),
                '전환_conversions.csv': _df_conv,
                '광고비_adspend.csv':   _df_adspend,
                '콘텐츠_content.csv':  _df_content,
                '날짜메모_notes.csv':   load_date_notes(),
            }
            for _fname, _ddf in _zip_data.items():
                if _ddf is not None and not _ddf.empty:
                    _zf.writestr(_fname, _ddf.to_csv(index=False, encoding='utf-8-sig'))
        st.download_button(
            "📦 전체 백업 ZIP",
            data=_zip_buf.getvalue(),
            file_name=f"채팅방_전체백업_{date.today()}.zip",
            mime='application/zip',
            width='stretch',
            help="모든 CSV 데이터를 하나의 ZIP 파일로 다운로드합니다",
        )

    # ── 날짜 데이터 삭제 (2단계 확인) ─────────────────────────
    st.divider()
    st.subheader("날짜 데이터 삭제")
    dates = sorted(df['date'].astype(str).unique().tolist(), reverse=True)
    del_date = st.selectbox("삭제할 날짜", options=dates, key="del_date_select")

    if st.button("🗑️ 삭제 요청", type="secondary"):
        st.session_state.pending_delete_date = del_date

    if st.session_state.pending_delete_date == del_date:
        st.error(
            f"'{del_date}' 데이터를 영구 삭제합니다. 되돌릴 수 없습니다. 계속하시겠습니까?"
        )
        col_yes, col_no = st.columns(2)
        if col_yes.button("✅ 확인 삭제", type="primary", width='stretch'):
            delete_date(del_date)
            st.session_state.pending_delete_date = None
            st.success(f"✅ {del_date} 데이터 삭제 완료")
            st.rerun()
        if col_no.button("❌ 취소", width='stretch'):
            st.session_state.pending_delete_date = None
            st.rerun()


if __name__ == '__main__':
    main()
