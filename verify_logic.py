"""계산 로직 회귀 검사 — 네트워크 없이 1초 안에 끝난다.

실행: python3 verify_logic.py

`verify_app.py`는 **지금 데이터로** 화면이 그려지는지를 본다. 그래서 계산이
틀려도 예외만 안 나면 통과한다 — 실제로 지금까지 사이트를 조용히 망가뜨린 건
대부분 그런 종류였다(부분월을 완결월로 봐서 전망이 10% 낮게 나온 v4.70,
건수는 4인데 이름은 3개만 나오던 v4.75, 웨비나 대기를 입력 누락으로 경고하던
v4.75). 데이터가 바뀌면 재현되지도 않는다.

여기서는 **고쳤던 버그를 그대로 재현하는 입력**을 넣고 결과를 못 박는다.
같은 실수가 다시 들어오면 푸시가 막힌다. 각 검사에 어느 버전에서 왜 생겼는지
근거를 적어 둔다 — 나중에 이 단언이 걸리적거릴 때 지워도 되는 것인지
판단하려면 그 맥락이 있어야 한다.

원격 데이터를 읽지 않는다. 읽어야 하는 함수(order_asof)는 값을 갈아 끼운다.
"""
import logging
import sys
from datetime import date

import pandas as pd

# github_store가 streamlit을 끌어오는데 화면 없이 돌면 "No runtime found"를 매
# 호출마다 찍는다 — 검사 결과 7줄이 경고 46줄에 묻힌다(v4.79와 같은 처리).
try:
    import streamlit.logger as _st_logger
    _st_logger.set_log_level("error")
except Exception:
    logging.getLogger("streamlit").setLevel(logging.ERROR)

FAILS = []
PASSED = 0


def check(name, got, want, why):
    """got == want 를 확인. 어긋나면 무엇이 왜 중요한지와 함께 모아 둔다."""
    global PASSED
    ok = got == want
    if ok:
        PASSED += 1
    else:
        FAILS.append(f"{name}\n        기대 {want!r} / 실제 {got!r}\n        └ {why}")
    return ok


# ── 1) 부분월 판정 (v4.70) ────────────────────────────────────────
def test_complete_months():
    """주문 스냅샷이 달 중간에서 끊긴 달을 '완결월'로 세면 안 된다.

    v4.70: 원본이 7/19 export인데 2026-07을 완결월로 계산에 넣어 매출이
    6,744만원(6월은 9.4억)으로 찍히고, 런레이트가 4.47억(정상 4.94억)으로
    10% 낮게 나왔다. '오늘 날짜'가 아니라 '주문 원본의 마지막 날짜'가 기준이다.
    """
    import github_store as gs

    df = pd.DataFrame({'month': ['2026-05', '2026-06', '2026-07', '2026-08'],
                       'revenue': [1, 2, 3, 4]})
    _orig = gs.order_asof
    try:
        gs.order_asof = lambda: date(2026, 7, 19)      # 7/19까지만 담긴 스냅샷
        got = list(gs.complete_months(df)['month'])
        check("부분월 제외 (주문 스냅샷 7/19)", got, ['2026-05', '2026-06'],
              "7월은 19일치만 담긴 부분월 — 완결월로 세면 매출·런레이트가 낮게 나온다")

        gs.order_asof = lambda: None                   # 기준일을 모를 때
        got = list(gs.complete_months(df)['month'])
        want = [m for m in ['2026-05', '2026-06', '2026-07', '2026-08']
                if m < date.today().strftime('%Y-%m')]
        check("기준일 없으면 당월만 제외", got, want,
              "as_of를 못 읽어도 최소한 진행 중인 당월은 빠져야 한다")

        check("빈 입력은 그대로", len(gs.complete_months(pd.DataFrame())), 0,
              "데이터가 아직 없을 때 예외로 죽지 않아야 한다")
    finally:
        gs.order_asof = _orig


# ── 2) 웨비나 대기 분리 (v4.75) ───────────────────────────────────
def test_lecture_date_split():
    """개강일이 비어 있어도 '웨비나 전'이면 정상이다.

    v4.75: 웨비나 전이라 개강일이 아직 존재하지도 않는 방 4개를 '입력 누락'으로
    2주 넘게 경고했다. 사람이 할 수 있는 일이 없는 알림은 다른 알림까지
    무시하게 만든다.
    """
    from alerts import lecture_date_split

    df = pd.DataFrame([
        {'campaign_name': '돈사공 13기', 'lecture_start_date': '', 'is_current': True,
         'status': '웨비나대기'},
        {'campaign_name': '돈빌공 6기', 'lecture_start_date': '', 'is_current': True,
         'status': '모집중'},
        {'campaign_name': '돈타공 4기', 'lecture_start_date': '2026-03-24',
         'is_current': True, 'status': '모집중'},
        {'campaign_name': '옛날 방', 'lecture_start_date': '', 'is_current': False,
         'status': '모집중'},
    ])
    miss, wait = lecture_date_split(df)
    check("진짜 누락만 경고", list(miss['campaign_name']), ['돈빌공 6기'],
          "웨비나 대기(개강일이 아직 없는 게 정상)와 종료된 방은 빠져야 한다")
    check("웨비나 대기는 따로", list(wait['campaign_name']), ['돈사공 13기'],
          "경고가 아니라 '개강 대기'로 보여 주는 대상")

    # status 열이 생기기 전 CSV로도 동작해야 한다(동기화 전 하위호환)
    old = df.drop(columns=['status'])
    miss2, wait2 = lecture_date_split(old)
    check("status 없으면 예전처럼 전부 누락", len(miss2), 2,
          "열이 없다고 빈 결과를 내면 경고가 통째로 잠든다")
    check("status 없으면 대기는 0건", len(wait2), 0, "구분할 근거가 없을 때의 안전한 기본값")


# ── 3) 이름 나열 (v4.75) ──────────────────────────────────────────
def test_name_list():
    """건수와 실제로 적힌 이름 수가 어긋나면 안 된다.

    v4.75: '4건'이라 써 놓고 이름은 3개만 나와, 나머지 하나를 찾을 방법이 없었다.
    """
    from alerts import name_list

    df = pd.DataFrame({'campaign_name': ['가', '나', '다', '라']})
    check("넘치면 '외 N건'", name_list(df), "가, 나, 다 외 1건",
          "이름을 자를 거면 몇 개를 잘랐는지 반드시 밝혀야 한다")
    check("한도 이하면 전부", name_list(df.head(2)), "가, 나",
          "3개 이하는 접지 않는다")


# ── 4) 기준선 계산 (v4.78) ────────────────────────────────────────
def test_open_to_live_days():
    """'얼마나 오래 대기하면 이상한가'를 손으로 정하지 않고 실적에서 뽑는다."""
    from alerts import open_to_live_days

    cmp_df = pd.DataFrame([{'product': 'p', 'cohort': f'{i}기',
                            'start_date': '2026-01-01'} for i in range(6)])
    live = ['2026-01-11', '2026-01-21', '2026-01-31',
            '2026-02-10', '2026-02-20', '2026-05-01']
    ad = pd.DataFrame([{'product': 'p', 'cohort': f'{i}기', 'live_date': live[i]}
                       for i in range(6)])
    got = open_to_live_days(cmp_df, ad, q=0.9)
    check("90분위 기준선", got, 85,
          "10·20·30·40·50·120일 → 선형보간 90분위 = 50+0.5*(120-50) = 85일. "
          "대부분이 끝낸 기간을 선으로 쓰되 최장(120)에 끌려가지 않는다")

    check("표본 부족하면 None", open_to_live_days(cmp_df.head(3), ad.head(3)), None,
          "몇 건 안 되는 이력으로 기준선을 만들면 근거가 아니라 착시다")
    check("빈 입력은 None", open_to_live_days(pd.DataFrame(), pd.DataFrame()), None,
          "데이터가 없으면 조용히 기본값으로 넘어가야 한다")


# ── 5) 알림 발송 억제 (v4.76) ─────────────────────────────────────
def test_alert_signature():
    """하루 3회 도는 자동 갱신이 같은 알림을 세 번 보내지 않게 하는 값.

    본문에는 '40일 경과'처럼 매일 변하는 숫자가 들어 있다. 지문이 본문까지
    보면 매번 달라져 억제가 통째로 풀린다 — 심각도와 제목만 봐야 한다.
    """
    from alerts import alert_signature, slack_message

    a = [{'sev': 'critical', 'title': '주문 명단 갱신 필요', 'msg': '40일 경과'},
         {'sev': 'warning', 'title': '광고 저효율 기수', 'msg': 'ROAS 1.5배'}]
    b = [{'sev': 'warning', 'title': '광고 저효율 기수', 'msg': 'ROAS 1.4배'},
         {'sev': 'critical', 'title': '주문 명단 갱신 필요', 'msg': '41일 경과'}]
    check("순서·본문이 달라도 같은 지문", alert_signature(a), alert_signature(b),
          "매일 바뀌는 일수 때문에 같은 알림이 새 알림으로 보이면 안 된다")

    c = [{'sev': 'critical', 'title': '총원 급락', 'msg': ''}] + a
    check("구성이 바뀌면 다른 지문", alert_signature(c) != alert_signature(a), True,
          "새 경고가 생기면 억제를 뚫고 즉시 알려야 한다")
    check("빈 목록은 빈 지문", alert_signature([]), "",
          "보낼 게 없는 상태를 저장해 둬야 다음에 생겼을 때 '변경'으로 잡힌다")

    msg = slack_message(a)
    check("슬랙 볼드 변환", "*주문 명단 갱신 필요*" in msg and "**" not in msg, True,
          "슬랙은 별 하나가 볼드 — 마크다운 그대로 보내면 별이 그대로 보인다")
    check("심각도 아이콘", msg.count("🔴") == 1 and msg.count("🟡") == 1, True,
          "위험과 주의를 한눈에 가를 수 있어야 한다")


# ── 6) 절기 기준 월주 (v4.49) ─────────────────────────────────────
def test_ganji_jeolgi():
    """월주는 양력 1일이 아니라 절입일에 바뀐다.

    v4.49: 달력월로 집계하면 매월 앞 5일(전체 18%)이 다른 오행에 배정된다.
    절기표를 코드에 심어 런타임 의존성 없이 처리한다.
    """
    import ganji

    check("절입 전은 지난달 (2026-06-03)", ganji.saju_month_of(date(2026, 6, 3)),
          (2026, 5), "6월이지만 망종 전이라 아직 癸巳月 — 달력월로 자르면 오배정된다")
    check("절입일부터 이번 달 (2026-06-06)", ganji.saju_month_of(date(2026, 6, 6)),
          (2026, 6), "절입일 당일부터 새 월주")
    check("2026-06 절입일", ganji.jeolgi_day(2026, 6), 6, "내장 절기표가 바뀌면 즉시 드러나야 한다")
    check("2026-05 월주", ganji.month_ganji(2026, 5), '癸巳', "v4.49 검증 당시 값")
    check("2026 년주", ganji.year_ganji(2026), '丙午', "년주는 입춘 기준")


# ── 7) 읽기 실패를 쓰기로 흘려보내지 않기 (v4.83) ────────────────
def test_read_write_guard():
    """원격 CSV를 **못 읽은 것**을 '비어 있다'로 보면 원본이 통째로 날아간다.

    v4.83: 저장 경로 27곳이 모두 '읽고 → 합치고 → 통째로 쓰기'인데,
    _read_csv가 연결 오류·401·403·5xx를 전부 404(빈 파일)와 같은 빈 표로
    돌려주고 있었다. 실제로 두 번 터졌다 — 2026-08-22 rooms.csv의 사람이 붙인
    별칭 8개가 기본값으로 되돌아갔고, 2026-08-29 campaigns.csv가 16행에서
    11행으로 줄어 종료된 방 5개(돈빌공 5기·돈사공 11기 계열)가 사라졌다.
    화면 없는 자동 갱신이라 st.error()는 아무 데도 안 찍혀 흔적조차 없었다.
    """
    import base64
    import requests
    import github_store as gs

    class Res:
        def __init__(self, code, payload=None):
            self.status_code = code; self._p = payload or {}
        @property
        def ok(self): return 200 <= self.status_code < 300
        def json(self): return self._p

    _get, _put, _read = gs._SESSION.get, gs._SESSION.put, gs._read_csv
    gs._RETRY_WAIT = 0          # 실패를 일부러 만들어 내는 검사 — 기다릴 이유가 없다
    try:
        # 실패와 '아직 없는 파일'은 반드시 달라야 한다
        gs._SESSION.get = lambda *a, **k: Res(404)
        check("404는 빈 표", gs._read_csv("x.csv", ["a"]).empty, True,
              "아직 만들어지지 않은 파일 — 이건 정상이라 빈 표가 맞다")

        for code in (500, 403, 401):
            gs._SESSION.get = lambda *a, _c=code, **k: Res(_c)
            raised = False
            try:
                gs._read_csv("x.csv", ["a"])
            except gs.RemoteReadError:
                raised = True
            check(f"HTTP {code}는 예외", raised, True,
                  "못 읽은 것을 빈 표로 돌려주면 그 위에 덮어써져 원본이 사라진다")

        def boom(*a, **k): raise requests.exceptions.ConnectionError("끊김")
        gs._SESSION.get = boom
        raised = False
        try:
            gs._read_csv("x.csv", ["a"])
        except gs.RemoteReadError:
            raised = True
        check("연결 끊김은 예외", raised, True, "위와 같은 이유")

        # 행이 줄어드는 저장은 의도를 밝힌 경우에만
        cur = base64.b64encode(b"room_num,room_name\n1,a\n2,b\n3,c\n").decode()
        gs._SESSION.get = lambda *a, **k: Res(200, {"sha": "x", "content": cur})
        puts = []
        gs._SESSION.put = lambda *a, **k: (puts.append(1), Res(200))[1]

        shrunk = pd.DataFrame([{"room_num": 1, "room_name": "a"}])
        blocked = False
        try:
            gs._write_csv("data/rooms.csv", shrunk, "축소")
        except RuntimeError:
            blocked = True
        check("3행 → 1행 저장은 거부", blocked, True,
              "campaigns.csv가 16행에서 11행으로 줄어든 그 경로")
        check("거부되면 PUT을 보내지 않는다", puts, [],
              "막았다면서 실제로 보내면 아무 의미가 없다")

        puts.clear()
        gs._write_csv("data/rooms.csv", shrunk, "의도된 삭제", allow_shrink=True)
        check("allow_shrink면 삭제는 그대로", len(puts), 1,
              "사고는 막되 사람이 지우는 기능은 살아 있어야 한다")

        puts.clear()
        grown = pd.DataFrame([{"room_num": i, "room_name": "x"} for i in range(1, 5)])
        gs._write_csv("data/rooms.csv", grown, "추가")
        check("행이 늘면 통과", len(puts), 1, "정상 저장까지 막으면 안 된다")

        # 자동 등록이 사람이 붙인 별칭을 덮어쓰면 안 된다
        gs._read_csv = lambda p, c: pd.DataFrame(
            [{"room_num": 37, "room_name": "채팅방 37 (부동산2)"}])
        puts.clear()
        gs.save_rooms_batch({37: "채팅방 37"})
        check("이미 있는 방은 저장 자체를 안 한다", puts, [],
              "들어오는 이름은 기본값 — 별칭 8개가 이렇게 날아갔다")
    finally:
        gs._SESSION.get, gs._SESSION.put, gs._read_csv = _get, _put, _read
        gs._RETRY_WAIT = 1.5


# ── 8) 웹훅이 없어도 알림은 사람에게 간다 (v4.84) ────────────────
def test_alert_delivery_without_webhook():
    """슬랙을 설정하지 않았다고 알림을 통째로 건너뛰면 안 된다.

    v4.84: `send_alerts`가 웹훅이 비면 **판정도 하지 않고** 바로 빠져나갔다.
    그래서 v4.76이 만든 '사이트를 열지 않아도 도착하는 알림'이 넉 달 동안
    한 번도 나가지 않았고, 무엇이 걸렸는지 로그에도 안 남았다(하루 3회
    '슬랙 웹훅 미설정 — 건너뜀'만 반복). 웹훅이 없으면 맥 알림으로 보낸다.
    """
    import os
    import sys as _sys
    _here = os.path.dirname(os.path.abspath(__file__))
    if _here not in _sys.path:
        _sys.path.insert(0, _here)
    _sp = os.path.join(_here, "scripts")
    if _sp not in _sys.path:
        _sys.path.insert(0, _sp)

    import alerts as al
    import auto_refresh as ar

    items = [{'sev': 'critical', 'title': '주문 명단 갱신 필요', 'msg': 'x'},
             {'sev': 'warning',  'title': '광고 저효율 기수',   'msg': 'y'}]
    sent, logs, state = [], [], {}
    _orig = (ar._webhook, ar._notify_mac, ar.log, ar._state, ar._save_state,
             al.generate_alerts)
    try:
        ar._webhook     = lambda: ""                 # 슬랙 미설정 상태
        ar._notify_mac  = lambda t, b: (sent.append((t, b)), True)[1]
        ar.log          = logs.append
        ar._state       = lambda: state
        ar._save_state  = lambda s: state.update(s)
        al.generate_alerts = lambda: items

        status = ar.send_alerts(dry=False)
        check("웹훅 없어도 발송한다", len(sent), 1,
              "'미설정 — 건너뜀'으로 끝나면 알림은 없는 것과 같다")
        check("위험 건수를 제목에 담는다", "위험 1건" in sent[0][0], True,
              "제목만 보고 급한지 판단할 수 있어야 한다")
        check("결과 문자열", status, "발송 2건", "사이트 데이터 관리 탭에 그대로 표시된다")
        check("무엇이 걸렸는지 로그에 남긴다",
              sum(1 for l in logs if '주문 명단 갱신 필요' in str(l)), 1,
              "발송 여부만 남기면 나중에 무엇이 문제였는지 알 수 없다")

        # 같은 알림을 하루에 두 번 밀지 않는다(v4.76 억제 규칙이 살아 있는가)
        sent.clear()
        check("같은 알림은 하루 한 번", ar.send_alerts(dry=False), "억제",
              "하루 3회 도는 작업이라 그대로 밀면 곧 무시하게 된다")
        check("억제됐으면 실제로 안 보낸다", sent, [], "위와 같은 이유")
    finally:
        (ar._webhook, ar._notify_mac, ar.log, ar._state, ar._save_state,
         al.generate_alerts) = _orig


# ── 9) 지역 조언에 기준 시점이 붙어 있는가 (v4.85) ──────────────
def test_region_advice_carries_asof():
    """8개월 된 배송지 스냅샷으로 '광고 예산을 여기 쓰세요'라고 말하면 안 된다.

    v4.85: 지역 분포는 주문 명단이 아니라 **배송지 리포트**(2025-12)에서 오는
    별도 자료다. v4.74가 지역 분포 탭에만 기준 시점을 붙였고, 같은 데이터로
    광고 예산 배정을 지시하는 세 곳(종합 보고 KPI·전략 브리핑·소재 브리프)은
    빠져 있어 '지금의 지역 분포'로 읽혔다. 돈 쓰는 결정에 직접 붙는 문구다.
    """
    import os
    import re
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app.py')).read()
    lines = src.splitlines()

    # 지역 데이터를 읽는 자리마다 근처에 기준 시점 표기가 있어야 한다.
    uses = [i for i, l in enumerate(lines) if 'load_region_signups()' in l]
    check("지역 데이터 사용처를 찾았다", len(uses) >= 3, True,
          "사용처가 줄었다면 이 검사도 함께 손봐야 한다")
    for i in uses:
        near = "\n".join(lines[i:i + 120])
        check(f"지역 조언에 기준 시점 (line {i + 1})",
              ('_asof_tag(' in near) or ('_dataset_asof(' in near), True,
              "언제 것인지 없으면 8개월 전 분포를 현재로 읽는다")

    # 주문 업로드 성공 메시지가 '지역까지 갱신됐다'고 말하면 거짓이다.
    # 성공 문구만 본다 — 바로 뒤 캡션은 '지역은 안 바뀐다'는 설명이라 제외
    _succ = re.search(r'집계 \{_tot\}종 갱신 완료(.*?)st\.caption', src, re.S)
    check("업로드 성공 메시지를 찾았다", bool(_succ), True, "문구가 바뀌면 검사도 갱신")
    if _succ:
        check("성공 메시지가 지역을 포함하지 않는다", '지역' in _succ.group(0), False,
              "지역은 배송지 리포트에서 오므로 주문 업로드로 갱신되지 않는다")



def test_partial_order_upload_blocked():
    """일부 상품만 뽑은 주문 파일로 전체 집계를 덮지 못하게 (v4.90).

    부분 파일도 열 구성이 전체와 똑같다. 그대로 갱신하면 그 파일에 없는
    상품의 매출·고객·리텐션이 통째로 사라지는데, 마지막 주문일이 더 최신이라
    기존의 '옛 파일' 경고에도 걸리지 않는다. 실제로 2026-09 서적 파일이
    751건·마지막 주문 09-15로 기준일(07-19)보다 최신이었다.
    """
    import pandas as pd
    import app

    def _sm(cats, first):
        idx = list(cats) or ['서적']
        return {'first': pd.Timestamp(first), 'last': pd.Timestamp('2026-09-15'),
                'by_product': pd.DataFrame(
                    {'건수': [1] * len(idx), '인원': [1] * len(idx),
                     '매출': [1] * len(idx)}, index=idx)}

    full, why = app._order_upload_scope(_sm(['서적'], '2026-08-13'))
    check("서적만 든 파일", full, False, "전체 갱신을 막아야 한다")
    check("서적 파일 사유", len(why) >= 1, True, "왜 막혔는지 알려줘야 한다")

    full, _ = app._order_upload_scope(_sm(['사주'], '2026-08-20'))
    check("한 상품군만", full, False, "상품군 1종은 전체 파일이 아니다")

    full, _ = app._order_upload_scope(_sm(['사주', '타로', '부동산', '빌딩'],
                                          '2024-09-07'))
    check("네 상품군 전체 기간", full, True, "정상 파일은 통과해야 한다")

    # 상품군은 충분한데 기간이 잘린 파일 — 과거가 날아간다
    full, why = app._order_upload_scope(_sm(['사주', '타로', '부동산', '빌딩'],
                                            '2026-05-01'))
    check("기간이 잘린 파일", full, False, "과거가 사라지는 파일도 막아야 한다")




def test_cpa_denominator_excludes_closed_rooms():
    """1명당 광고비 분모에서 '방 종료로 상쇄된 순증감'을 쓰지 않는다 (v4.99).

    강의를 마친 방을 닫은 기간에는 총원 순증감이 구조적으로 눌린다. 그걸
    분모로 쓰면 단가가 폭등한 것처럼 보인다 — 실측(최근 3개월): 광고비
    132,333,333원 ÷ 순증감 267명 = 495,630원/명. 실제 모객 3,840명 기준으로는
    34,462원이다. 14배 차이라 그대로 보고되면 판단이 뒤집힌다.
    """
    spend, diff, active = 132333333, 267, 3840

    def cpa(breakdown):
        base = diff
        if (breakdown and breakdown.get('archived_removed', 0) < 0
                and breakdown.get('active_change', 0) > 0):
            base = breakdown['active_change']
        return round(spend / base) if base > 0 else None

    check("종료 방 있을 때", cpa({'archived_removed': -3573, 'active_change': active}),
          34462, "실제 모객으로 나눠야 한다")
    check("종료 방 없을 때", cpa(None), round(spend / diff),
          "종료가 없으면 순증감이 곧 모객이다")
    check("분해는 있지만 종료 없음", cpa({'archived_removed': 0, 'active_change': 100}),
          round(spend / diff), "구조적 감소가 없으면 바꾸지 않는다")



TESTS = [
    ("부분월 판정 (v4.70)", test_complete_months),
    ("웨비나 대기 분리 (v4.75)", test_lecture_date_split),
    ("이름 나열 (v4.75)", test_name_list),
    ("대기 기준선 (v4.78)", test_open_to_live_days),
    ("알림 억제 (v4.76)", test_alert_signature),
    ("절기 기준 월주 (v4.49)", test_ganji_jeolgi),
    ("읽기 실패 → 쓰기 차단 (v4.83)", test_read_write_guard),
    ("웹훅 없이도 알림 발송 (v4.84)", test_alert_delivery_without_webhook),
    ("지역 조언 기준 시점 (v4.85)", test_region_advice_carries_asof),
    ("부분 주문 파일 차단 (v4.90)", test_partial_order_upload_blocked),
    ("1명당 광고비 분모 (v4.99)", test_cpa_denominator_excludes_closed_rooms),
]


def main() -> int:
    print("계산 로직 회귀 검사")
    for label, fn in TESTS:
        before = len(FAILS)
        try:
            fn()
        except Exception as e:                 # 검사 자체가 터진 것도 실패다
            FAILS.append(f"{label} — 검사 실행 중 예외: {type(e).__name__}: {e}")
        mark = "✅" if len(FAILS) == before else "🚨"
        print(f"   {mark} {label}")

    print()
    if FAILS:
        print(f"❌ 실패 {len(FAILS)}건 / 통과 {PASSED}건")
        for f in FAILS:
            print(f"   🚨 {f}")
        print("\n고친 버그가 되돌아왔거나, 의도적으로 바꿨다면 이 검사도 함께 고치세요.")
        return 1
    print(f"✅ 통과 — {PASSED}개 단언 모두 정상")
    return 0


if __name__ == "__main__":
    sys.exit(main())
