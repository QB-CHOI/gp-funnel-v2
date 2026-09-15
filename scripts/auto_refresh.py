"""데이터 자동 갱신 — launchd가 매일 호출하는 진입점.

네 가지를 순서대로 처리한다. 어느 하나가 실패해도 나머지는 계속 진행한다.

  1) 시장 신호   : 키워드 분석툴 캐시 → market_signals.csv   (매일 자동)
  2) 주문 집계   : 새 '강의별_리스트*.xlsx'가 있을 때만 15종 재생성
  3) 오행 집계   : 위 2)가 돌았을 때만 함께 갱신
  4) 오카방 방목록: '오카방의 모든 것.xlsx' → campaigns.csv  (매일 자동)
  5) 알림 발송   : 위험·주의 알림을 슬랙으로                 (바뀔 때 + 하루 1회)

설계 원칙
  · **내용이 같으면 푸시하지 않는다** — 매일 도는 작업이라 동일 커밋이
    쌓이면 이력이 지저분해지고 API 호출만 낭비된다.
  · 주문 엑셀은 사람이 아임웹에서 내려받아야 하므로 자동화할 수 없다.
    대신 ~/Downloads에 새 파일이 생기면 자동으로 알아채 반영한다.
  · 구글 드라이브도 직접 못 읽는다(서비스 계정·rclone·드라이브 데스크톱 없음).
    4)는 **로컬에 내려온 사본**을 읽는다 — 드라이브 데스크톱을 깔면 그 경로가
    자동으로 잡히고, 그 전까지는 inbox/에 둔 사본을 쓴다.
  · 실패해도 조용히 죽지 않고 로그에 남긴다(launchd는 화면이 없다).
  · **알림은 사람이 사이트를 열지 않아도 도착해야 한다.** 판정은 화면과
    똑같이 alerts.generate_alerts()를 쓰되, 하루 3회 도는 작업이라
    같은 내용을 세 번 보내면 알림 자체를 무시하게 되므로 억제한다.

실행:
    python3 scripts/auto_refresh.py            # 전체
    python3 scripts/auto_refresh.py --dry-run  # 확인만, 쓰지 않음
"""
import argparse
import glob
import hashlib
import io
import json
import logging
import os
import subprocess
import sys
import traceback
import warnings
from datetime import datetime

import pandas as pd

# 여기서 쓰는 라이브러리(github_store)가 streamlit을 끌어오는데, 화면 없이 돌면
# "missing ScriptRunContext!"·"No runtime found"를 매 호출마다 경고로 찍는다.
# 무해하지만 로그의 99%가 이 줄이라 정작 진짜 오류가 묻힌다(err.log 493KB).
#
# 부모 로거만 낮추면 안 된다 — streamlit은 자기 로거마다 레벨을 직접 걸어서
# 부모 설정이 덮인다(실제로 78줄이 그대로 남았다). 등록된 로거 전부와 앞으로
# 만들어질 로거까지 함께 낮추는 streamlit.logger.set_log_level을 쓴다.
try:
    import streamlit.logger as _st_logger
    _st_logger.set_log_level("error")
except Exception:                       # streamlit 내부 구조가 바뀌어도 죽지 않게
    logging.getLogger("streamlit").setLevel(logging.ERROR)

# urllib3의 LibreSSL 경고도 실행마다 여러 줄 찍힌다(누적 95줄). 시스템 파이썬을
# 쓰는 한 없앨 수 없는 환경 경고인데, v4.83부터 **진짜 실패**가 stderr로 오므로
# (github_store._report) 그 신호가 이 줄들에 묻히면 안 된다.
warnings.filterwarnings("ignore", message=".*OpenSSL.*")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

STATE_PATH = os.path.join(ROOT, ".auto_refresh_state.json")

# launchd가 stdout·stderr을 여기로 흘린다. 아무도 지우지 않으므로 스스로 줄인다.
LOG_PATHS = [os.path.expanduser("~/Library/Logs/gp-funnel-refresh.log"),
             os.path.expanduser("~/Library/Logs/gp-funnel-refresh.err.log")]
LOG_MAX = 2 * 1024 * 1024      # 2MB 넘으면 최근 부분만 남긴다
LOG_KEEP = 200 * 1024

# 주문 엑셀을 찾는 위치(순서대로). inbox가 먼저인 이유:
# macOS는 Downloads·Documents·Desktop을 TCC로 보호해서 launchd가 읽지 못한다.
# 프로젝트 안 inbox/는 보호 대상이 아니라 권한 설정 없이도 동작한다.
INBOX = os.path.join(ROOT, "inbox")
ORDER_PATTERNS = [
    os.path.join(INBOX, "강의별_리스트*.xlsx"),
    os.path.expanduser("~/Downloads/강의별_리스트*.xlsx"),
]


def find_order_files(patterns=None):
    """주문 엑셀 찾기 — macOS 한글 파일명 정규화(NFD) 대응.

    macOS는 파일명을 NFD(자모 분리)로 저장하는데 소스의 문자열 리터럴은
    NFC라서 glob이 그냥은 매칭되지 않는다. 두 형태를 모두 시도한다.
    """
    import unicodedata
    found = []
    for pattern in (patterns or ORDER_PATTERNS):
        for pat in (pattern,
                    unicodedata.normalize("NFD", pattern),
                    unicodedata.normalize("NFC", pattern)):
            try:
                hits = glob.glob(pat)
            except OSError:
                continue
            for f in hits:
                if f not in found:
                    found.append(f)
    return sorted(found, key=os.path.getmtime)


FDA_HELP = (
    "macOS 보호 폴더(Documents·Downloads)는 자동 실행 프로세스가 읽지 못합니다.\n"
    "     해결 A) 주문 엑셀을 gp-funnel-v2/inbox/ 에 두면 권한 없이 동작합니다.\n"
    "     해결 B) 시스템 설정 → 개인정보 보호 및 보안 → 전체 디스크 접근 권한에\n"
    "            /usr/bin/python3 을 추가하면 원래 위치도 읽습니다."
)


def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def trim_logs():
    """로그가 너무 커지면 최근 부분만 남기고 자른다.

    launchd가 append 모드로 잡고 있는 파일이라 이름을 바꾸면 열린 fd가 새 파일을
    따라가 버린다. 제자리에서 truncate하는 것만 안전하다.
    """
    for p in LOG_PATHS:
        try:
            if os.path.getsize(p) <= LOG_MAX:
                continue
            with open(p, encoding="utf-8", errors="replace") as f:
                f.seek(max(0, os.path.getsize(p) - LOG_KEEP))
                tail = f.read()
            os.truncate(p, 0)
            with open(p, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] "
                        f"--- 이전 기록을 잘라냈습니다(최근 {LOG_KEEP // 1024}KB만 보존) ---\n")
                f.write(tail[tail.find("\n") + 1:])
        except OSError:
            pass          # 로그 정리 실패로 본 작업을 멈추지는 않는다


def _state():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(s):
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except OSError as e:
        log(f"  ⚠️ 상태 저장 실패: {e}")


def _remote_same(path, df):
    """원격 CSV와 내용이 같은지. 같으면 푸시를 건너뛴다."""
    try:
        from github_store import _read_csv
        cur = _read_csv(path, list(df.columns))
        if cur.empty:
            return False
        a = cur.to_csv(index=False).encode()
        b = df.to_csv(index=False).encode()
        return hashlib.md5(a).hexdigest() == hashlib.md5(b).hexdigest()
    except Exception:
        return False


def _push(path, df, message, dry):
    if _remote_same(path, df):
        log(f"  · {path} 변경 없음 — 건너뜀")
        return False
    if dry:
        log(f"  · [dry-run] {path} 갱신 예정 ({len(df)}행)")
        return True
    from github_store import _write_csv
    _write_csv(path, df, message)
    log(f"  ✅ {path} 갱신 ({len(df)}행)")
    return True


# ── 1) 시장 신호 ─────────────────────────────────────────────
def refresh_market_signals(dry):
    log("① 시장 신호 (키워드 분석툴)")
    try:
        from scripts.sync_market_signals import build, PROCESSED
    except ImportError as e:
        log(f"  ⚠️ 모듈 로드 실패: {e}")
        return False
    if not os.path.isdir(PROCESSED):
        log("  · 키워드 분석툴 데이터 없음 — 건너뜀")
        return False
    # 파일이 실제로 읽히는지 먼저 확인. macOS TCC(개인정보 보호) 때문에
    # launchd에서는 디렉터리는 보이는데 내용이 안 읽히는 경우가 있다.
    try:
        n_cache = len(os.listdir(PROCESSED))
    except PermissionError:
        log("  🔒 접근 거부 — 키워드 분석툴 캐시를 읽을 수 없습니다")
        log(f"     {FDA_HELP}")
        return False
    log(f"  · 캐시 파일 {n_cache}개 확인")
    notes = []
    try:
        df = build(notes)
    except PermissionError:
        log("  🔒 파일 읽기 거부 — 권한 필요")
        log(f"     {FDA_HELP}")
        return False
    except Exception as e:
        log(f"  ⚠️ 추출 실패: {type(e).__name__}: {e}")
        return False
    for n in notes:
        log(f"  · {n}")
    if df.empty:
        log("  · 추출된 신호 없음 — 건너뜀")
        return False
    collected = df["collected"].iloc[0] if "collected" in df.columns else "?"
    return _push("data/market_signals.csv", df,
                 f"data: 시장 신호 자동 갱신 ({collected})", dry)


# ── 2)·3) 주문 원본 기반 집계 ────────────────────────────────
def refresh_order_based(dry):
    log("② 주문 집계 · ③ 오행 집계")
    files = find_order_files()
    if not files:
        log("  · 주문 엑셀 없음 — 건너뜀 (inbox/ 또는 ~/Downloads)")
        return False
    latest = files[-1]
    sig = f"{os.path.basename(latest)}|{int(os.path.getmtime(latest))}"
    st = _state()
    if st.get("order_file") == sig:
        log(f"  · 새 주문 파일 없음 ({os.path.basename(latest)}) — 건너뜀")
        return False

    log(f"  · 새 주문 파일 감지: {os.path.basename(latest)}")
    changed = False
    try:
        from scripts.refresh_order_aggregates import load_orders, build_all
        o = load_orders(latest)
        for fname, df in build_all(o).items():
            if isinstance(df, tuple):      # (df, 검증문자열) 형태 대응
                df = df[0]
            if _push(f"data/{fname}", df, f"data: 주문 집계 자동 갱신 ({fname})", dry):
                changed = True
    except Exception as e:
        log(f"  ⚠️ 주문 집계 실패: {e}")
        log(traceback.format_exc(limit=2))

    try:
        from scripts.build_ohaeng_period import build as build_oh
        from scripts.refresh_order_aggregates import load_orders as _lo
        df_oh = build_oh(_lo(latest))
        if _push("data/ohaeng_period.csv", df_oh,
                 "data: 오행 시기 집계 자동 갱신", dry):
            changed = True
    except Exception as e:
        log(f"  ⚠️ 오행 집계 실패: {e}")

    if not dry:
        st["order_file"] = sig
        st["order_refreshed_at"] = datetime.now().isoformat(timespec="seconds")
        _save_state(st)
    return changed


# ── 4) 오카방 레지스트리 ─────────────────────────────────────
def refresh_rooms(dry):
    log("④ 오카방 방목록 (구글 드라이브 시트)")
    try:
        from scripts.sync_rooms_from_drive import run
        return run(dry)
    except Exception as e:
        log(f"  ⚠️ 방목록 동기화 실패: {type(e).__name__}: {e}")
        log(traceback.format_exc(limit=2))
        return False


def refresh_schedule(dry):
    log("⑤ 강의 일정 캘린더 (구글 드라이브 시트)")
    try:
        from scripts.sync_schedule_from_drive import run
        return run(dry)
    except Exception as e:
        # 일정은 부가 정보다 — 여기서 죽어도 방목록·알림은 계속 돌아야 한다.
        log(f"  ⚠️ 일정 동기화 실패: {type(e).__name__}: {e}")
        log(traceback.format_exc(limit=2))
        return False


# ── 5) 알림 발송 ─────────────────────────────────────────────
def _webhook():
    """슬랙 웹훅 주소 — 앱과 같은 자리(.streamlit/secrets.toml)에서 읽는다."""
    try:
        import streamlit as st
        return st.secrets.get("slack_webhook_url", "")
    except Exception:
        return ""


def _notify_mac(title: str, body: str) -> bool:
    """맥 알림 센터로 띄운다 — 슬랙이 없을 때의 대체 경로.

    이 작업은 마케터의 맥에서 launchd로 도니 알림을 띄울 자리가 이미 있다.
    슬랙 웹훅이 준비될 때까지 위험 경고가 아무 데도 도달하지 않는 것보다는
    화면 오른쪽 위에라도 뜨는 편이 낫다.
    """
    body = body.replace('"', "'")[:230]     # 알림은 길면 잘린다 — 앞부분만
    try:
        return subprocess.run(
            ["osascript", "-e",
             f'display notification "{body}" with title "{title}"'],
            capture_output=True, timeout=10).returncode == 0
    except Exception:
        return False


def send_alerts(dry):
    """위험·주의 알림을 사람에게. 상태 문자열을 돌려준다(사이트에 그대로 표시).

    이 단계가 생긴 이유: 알림 판정은 정확했는데 **아무도 사이트를 열지 않아**
    주문 명단이 27일 → 32일까지 밀렸다. 경고가 화면 안에만 있으면 없는 것과
    같다. 대신 하루 3회 그대로 밀면 곧 무시하게 되므로 두 경우만 보낸다.

      · 알림 구성이 바뀐 때 — 새 경고가 생겼거나 해결됐을 때 즉시
      · 🔴 위험이 남아 있는 날 — 하루 한 번만 다시 알림

    정보(🔵)는 보내지 않는다. 매일 뜨는 안내라 알림으로는 소음이다.

    **웹훅이 없어도 판정은 한다.** 예전에는 웹훅이 비어 있으면 여기서 바로
    빠져나가서, 슬랙을 설정하지 않은 넉 달 동안 알림이 **한 번도** 나가지
    않았고 로그에 무엇이 걸렸는지조차 남지 않았다. 지금은 판정을 먼저 하고,
    슬랙이 있으면 슬랙으로·없으면 맥 알림으로 보낸다. 어느 쪽이든 무엇을
    보냈는지 로그에 남긴다.
    """
    log("⑥ 알림 점검")
    hook = _webhook()
    if not hook:
        log("  · 슬랙 웹훅 미설정 — 맥 알림으로 대신 보냅니다 "
            "(.streamlit/secrets.toml에 slack_webhook_url을 넣으면 슬랙으로)")
    try:
        from alerts import alert_signature, generate_alerts, slack_message
        from github_store import send_slack_alert
        items = [a for a in generate_alerts() if a["sev"] in ("critical", "warning")]
    except Exception as e:
        log(f"  ⚠️ 알림 판정 실패: {type(e).__name__}: {e}")
        log(traceback.format_exc(limit=2))
        return "실패"

    sig = alert_signature(items)
    st = _state()
    today = datetime.now().strftime("%Y-%m-%d")
    n_crit = sum(1 for a in items if a["sev"] == "critical")
    log(f"  · 위험 {n_crit} · 주의 {len(items) - n_crit}")

    if not items:
        if not dry:
            st["alert_sig"] = ""
            _save_state(st)
        log("  · 보낼 알림 없음")
        return "없음"

    changed = sig != st.get("alert_sig", "")
    daily = bool(n_crit) and st.get("alert_sent_on", "") != today
    if not (changed or daily):
        log("  · 같은 알림 — 오늘 이미 보냄, 건너뜀")
        return "억제"

    why = "구성 변경" if changed else "위험 잔존 일일 알림"
    ch = "슬랙" if hook else "맥 알림"
    for a in items:                     # 무엇이 걸렸는지 로그에 남긴다
        log(f"    · {'🔴' if a['sev'] == 'critical' else '🟡'} {a.get('title', a)}")
    if dry:
        log(f"  · [dry-run] {ch} 발송 예정 ({why}, {len(items)}건)")
        return f"발송예정 {len(items)}건"

    if hook:
        sent = send_slack_alert(hook, slack_message(items))
    else:
        head = f"🔴 위험 {n_crit}건" if n_crit else f"🟡 주의 {len(items)}건"
        sent = _notify_mac(
            f"황금후추 강의 분석 — {head}",
            " · ".join(str(a.get("title", "")) for a in items))
    if not sent:
        # 보낸 걸로 기록하면 안 된다 — 다음 실행이 '이미 보냄'으로 건너뛴다.
        log(f"  ⚠️ {ch} 전송 실패"
            + (" — 웹훅 주소를 확인하세요" if hook else ""))
        return "전송실패"
    st["alert_sig"] = sig
    st["alert_sent_on"] = today
    _save_state(st)
    log(f"  ✅ {ch} 발송 ({why}, {len(items)}건)")
    return f"발송 {len(items)}건"


def main():
    trim_logs()
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="확인만, 쓰지 않음")
    a = ap.parse_args()

    log("=" * 52)
    log(f"데이터 자동 갱신 시작{' (dry-run)' if a.dry_run else ''}")
    results = []
    for fn in (refresh_market_signals, refresh_order_based, refresh_rooms,
               refresh_schedule):
        try:
            results.append(fn(a.dry_run))
        except Exception as e:
            log(f"  ⚠️ 예외: {e}")
            log(traceback.format_exc(limit=3))
            results.append(False)

    # 알림은 데이터를 다 갱신한 뒤에 판정한다 — 방금 올라간 값이 반영돼야
    # '오래됐다'는 경고가 해소된 걸 그 자리에서 알 수 있다.
    try:
        alert_status = send_alerts(a.dry_run)
    except Exception as e:
        log(f"  ⚠️ 알림 예외: {e}")
        log(traceback.format_exc(limit=3))
        alert_status = "실패"

    st = _state()
    st["last_run"] = datetime.now().isoformat(timespec="seconds")
    st["last_changed"] = any(results)
    if not a.dry_run:
        _save_state(st)
        # 실행 결과를 사이트에서도 볼 수 있게 기록.
        # (로그는 이 맥에만 있어서, 자동 갱신이 멈춰도 눈치채기 어렵다)
        try:
            from github_store import _write_csv
            _write_csv("data/refresh_status.csv", pd.DataFrame([{
                "last_run": st["last_run"],
                "market_signals": "갱신" if results[0] else "변경없음/실패",
                "order_aggregates": "갱신" if results[1] else "변경없음/실패",
                "rooms": "갱신" if results[2] else "변경없음/실패",
                "schedule": "갱신" if results[3] else "변경없음/실패",
                "changed": "예" if any(results) else "아니오",
                "alerts": alert_status,
            }]), f"chore: 자동 갱신 상태 {st['last_run']}")
        except Exception as e:
            log(f"  ⚠️ 상태 기록 실패: {e}")
    log(f"완료 — 갱신 {'있음' if any(results) else '없음'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
