"""강의 일정 캘린더 동기화 — 구글 시트 → data/webinar_schedule.csv.

원본은 CS 폴더의 "2026년 황금후추 강의 일정 캘린더(멤버쉽 추가 수정)"이고,
운영팀이 거의 매일 손본다. 오카방 시트와 같은 방식(rclone)으로 받아온다.

왜 필요한가:
  웨비나 일정은 앱에 **사람이 손으로** 넣게 돼 있었고, 그래서 2건(2026-08-20·
  08-21)만 들어 있었다. 둘 다 과거다. 그 사이 캘린더에는 24건이 잡혀 있었고
  그중 6건이 미래다. 앱은 '웨비나 없는 장기 모집방' 경고를 162일째 띄우고
  있었는데, 정작 그 방의 웨비나 날짜는 이 캘린더에 이미 적혀 있었다.
  일정이 있어야 회차 추적도, 모객 준비 조언도 선다.

읽는 범위(의도적으로 좁게):
  · **`확정`이 든 시트만 읽는다.** 이 파일은 시트가 38개인데 한 달에 여러
    판이 있다 — `📌9월_확정`(확정본) 옆에 `9월_기존`·`9월_1차`·`9월_2차`,
    2027년은 `수정 중`까지 있다. 확정본만 골라야 초안 일정을 진짜로 착각하지
    않는다.
  · **웨비나와 개강일(1강)만 가져온다.** 같은 달력에 임장·수료식·기념일까지
    섞여 있다. 한 번에 다 가져오면 어디가 틀렸는지 못 찾는다.
  · **사람이 넣은 일정은 건드리지 않는다.** 같은 날짜·상품이 이미 있으면
    그대로 두고, 우리가 만든 행(id가 `cal-`로 시작)만 갱신한다.

달력 구조(실측):
  본문은 주 단위 격자다. 날짜 칸이 12행부터 4열 간격(B·F·J·N·R·V·Z)으로
  놓이고, 그 **아래 3행·오른쪽 4열 범위**에 그날 일정이 적힌다. 위쪽 2~9행은
  지난달 미니 달력이라 건너뛴다.

실행:
    python3 scripts/sync_schedule_from_drive.py --dry-run   # 차이만 출력
    python3 scripts/sync_schedule_from_drive.py             # private repo에 반영
"""
import argparse
import datetime as dt
import glob
import os
import re
import shutil
import subprocess
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

INBOX = os.path.join(ROOT, "inbox")
DRIVE_FILE_ID = "1UqFPtMRAFgVjocF14z-bIQwjLwNpQUMaGQai1yNblNY"
RCLONE_REMOTE = "gdrive"
SHEET_FILENAME = "황금후추 강의 일정 캘린더.xlsx"

# 달력에 쓰는 강의 별칭 → 앱의 상품 구분(PRODUCT_OPTIONS).
# 부동산은 '돈초부공'과 '돈부공' 두 이름이 섞여 쓰인다(2026-03은 돈초부공 7기,
# 2026-09는 돈부공 8기). 같은 줄기로 본다.
PRODUCT_MAP = {
    "돈사공": "사주",
    "돈타공": "타로",
    "돈초부공": "부동산",
    "돈부공": "부동산",
    "돈빌공": "빌딩",
}

ID_PREFIX = "cal-"          # 이 접두어가 붙은 행만 우리가 갱신한다


def log(msg):
    print(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def fetch_from_drive():
    """rclone이 설정돼 있으면 캘린더를 내려받아 inbox/를 최신으로 만든다.

    실패해도 죽지 않는다 — inbox/에 있던 사본으로 계속 도는 편이 낫다.
    (오카방 동기화와 같은 판단)
    """
    rclone = shutil.which("rclone")
    if not rclone:
        return False
    try:
        remotes = subprocess.run([rclone, "listremotes"], capture_output=True,
                                 text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    if f"{RCLONE_REMOTE}:" not in remotes:
        log("  · rclone 미설정 — 내려받기 건너뜀 (inbox/ 사본 사용)")
        return False

    dest = os.path.join(INBOX, SHEET_FILENAME)
    try:
        r = subprocess.run(
            [rclone, "backend", "copyid", f"{RCLONE_REMOTE}:",
             "--drive-export-formats", "xlsx", DRIVE_FILE_ID, dest],
            capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        log("  ⚠️ 내려받기 시간 초과 — inbox/ 사본으로 계속")
        return False
    if r.returncode != 0:
        tail = (r.stderr or "").strip().splitlines()
        log(f"  ⚠️ 내려받기 실패 — inbox/ 사본으로 계속: "
            f"{tail[-1] if tail else '원인 불명'}")
        return False
    log(f"  · 드라이브에서 최신본 수신 ({os.path.getsize(dest):,} bytes)")
    return True


def find_sheet():
    for pat in (os.path.join(INBOX, SHEET_FILENAME),
                os.path.join(INBOX, "*강의 일정 캘린더*.xlsx"),
                os.path.expanduser("~/Downloads/*강의 일정 캘린더*.xlsx")):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[0]
    return None


def _cell_events(ws, r, c):
    """날짜 칸(r,c) 아래에 적힌 일정 문구를 모은다."""
    out = []
    for rr in range(r + 1, r + 4):
        for cc in range(c, c + 4):
            if cc > ws.max_column or rr > ws.max_row:
                continue
            v = ws.cell(rr, cc).value
            if isinstance(v, str) and v.strip():
                out.append(" ".join(v.split()))
    return out


def scan_events(path) -> list:
    """확정본 전체를 한 번만 훑어 (날짜, 일정 문구) 목록을 만든다.

    2.6MB짜리 통합문서라 여는 데만 25초가 걸린다. 웨비나·개강일을 따로
    읽으면 하루 3회 도는 작업에 55초가 그냥 나간다 — 한 번 훑고 나눠 쓴다.
    """
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=False)
    sheets = [n for n in wb.sheetnames if "확정" in n]
    if not sheets:
        raise RuntimeError("'확정' 시트가 하나도 없다 — 파일 구조가 바뀌었는지 확인 필요")

    out = []
    for name in sheets:
        ws = wb[name]
        for r in range(12, ws.max_row + 1):          # 12행 위는 지난달 미니 달력
            for c in range(1, ws.max_column + 1):
                v = ws.cell(r, c).value
                if not isinstance(v, (dt.datetime, dt.date)):
                    continue
                d = v.date() if isinstance(v, dt.datetime) else v
                if d.year < 2025:        # 연도 없는 칸이 1900년으로 들어온다
                    continue
                for text in _cell_events(ws, r, c):
                    out.append((d, text))
    wb.close()
    return out


def parse_webinars(events) -> pd.DataFrame:
    """훑어 둔 일정에서 웨비나만 골라 [date, product, topic]으로 돌려준다."""
    rows = []
    for d, text in events:
        if "웨비나" not in text:
            continue
        m = re.match(r"(돈[가-힣]{1,3}공)", text)
        product = PRODUCT_MAP.get(m.group(1)) if m else None
        if not product:          # 모르는 이름은 버린다 — '기타'로 밀어넣지 않는다
            continue
        mt = re.search(r"\(([^)]*기)\)", text)
        rows.append({"date": d, "product": product,
                     "topic": mt.group(1).strip() if mt else ""})

    df = pd.DataFrame(rows).drop_duplicates(subset=["date", "product"])
    return df.sort_values("date").reset_index(drop=True)


def parse_lecture_starts(events) -> dict:
    """확정본에서 기수별 **개강일(1강)**을 뽑는다 → {(상품, 기수번호): 날짜}.

    모집방(오카방)은 입문 과정으로 들어오는 자리다. 달력에는 같은 기수의
    중급·고급·심화·해석연구반 1강도 함께 적히는데, 그건 수강생을 올려 보내는
    사다리지 모객 퍼널이 아니다. **단계가 없거나 초급/기초인 것만** 개강일로
    본다 — 안 그러면 모집방 개강일이 중급반 날짜로 덮인다.
    """
    LADDER = ("중급", "고급", "심화", "해석연구", "전문가", "창업")
    out = {}
    for d, text in events:
        m = re.match(r"(돈[가-힣]{1,3}공)\s*([가-힣]*)\s*(\d+)기\s*-\s*1강", text)
        if not m:
            continue
        alias, stage, num = m.group(1), m.group(2), int(m.group(3))
        product = PRODUCT_MAP.get(alias)
        if not product or any(k in stage for k in LADDER):
            continue
        key = (product, num)
        if key not in out or d < out[key]:   # 같은 기수가 여럿이면 가장 이른 날
            out[key] = d
    return out


def merge_lecture_starts(starts, campaigns):
    """개강일이 **비어 있는** 진행 중인 방만 채운다.

    이미 값이 있는 방은 건드리지 않는다 — 사람이 넣었을 수도 있고, 달력의
    기수 표기가 방 이름과 어긋날 수도 있다. 다만 값이 크게 어긋나면(연도가
    다르면) 잘못 들어간 값일 수 있으니 **보고만** 한다. 고치는 판단은 사람 몫이다.
    """
    if campaigns is None or campaigns.empty:
        return campaigns, [], []
    out = campaigns.copy()
    cur = out["is_current"].astype(str).str.lower().isin(["true", "1", "yes"])
    filled, odd = [], []
    for idx in out[cur].index:
        name = str(out.at[idx, "campaign_name"])
        product = str(out.at[idx, "product"])
        m = re.search(r"(\d+)\s*기", name)
        if not m:
            continue
        found = starts.get((product, int(m.group(1))))
        if not found:
            continue
        old = str(out.at[idx, "lecture_start_date"] or "").strip()
        if old in ("", "nan", "NaT"):
            out.at[idx, "lecture_start_date"] = found.isoformat()
            filled.append(f"{int(out.at[idx, 'room_num'])}번 {name} 개강일 "
                          f"→ {found}")
        elif old[:4] != str(found.year):
            odd.append(f"{int(out.at[idx, 'room_num'])}번 {name}: 저장값 {old} "
                       f"vs 달력 {found} — 확인 필요(자동으로 고치지 않음)")
    return out, filled, odd


def merge(sheet_df, existing):
    """사람이 넣은 일정은 보존하고, 우리 행만 더하거나 갱신한다."""
    from github_store import WEBINAR_SCHEDULE_COLS

    out = existing.copy() if existing is not None else pd.DataFrame()
    if out.empty:
        out = pd.DataFrame(columns=WEBINAR_SCHEDULE_COLS)
    for c in WEBINAR_SCHEDULE_COLS:
        if c not in out.columns:
            out[c] = ""
    out["date"] = pd.to_datetime(out["date"], errors="coerce")

    today = dt.date.today()
    changes = []
    for _, s in sheet_df.iterrows():
        d, product, topic = s["date"], s["product"], s["topic"]
        same = out[(out["date"].dt.date == d)
                   & (out["product"].astype(str) == product)]
        if not same.empty:
            idx = same.index[0]
            # 사람이 직접 넣은 행은 손대지 않는다. 우리 행만 주제를 맞춘다.
            if str(out.at[idx, "id"]).startswith(ID_PREFIX) and topic \
                    and str(out.at[idx, "topic"]) != topic:
                changes.append(f"{d} {product} 주제: "
                               f"{out.at[idx, 'topic']!r} → {topic!r}")
                out.at[idx, "topic"] = topic
            continue
        row = {c: "" for c in WEBINAR_SCHEDULE_COLS}
        row.update({
            "id": f"{ID_PREFIX}{d}-{product}",
            "date": pd.Timestamp(d),
            "product": product,
            "topic": topic,
            "target_signups": 0,
            "budget": 0,
            "status": "완료" if d < today else "예정",
        })
        out = pd.concat([out, pd.DataFrame([row])], ignore_index=True)
        changes.append(f"신규 {d} {product} {topic}".rstrip())

    out = out.sort_values("date").reset_index(drop=True)
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    return out[WEBINAR_SCHEDULE_COLS], changes


def run(dry=False):
    """auto_refresh에서 호출하는 진입점. 변경이 있었으면 True."""
    fetch_from_drive()
    path = find_sheet()
    if not path:
        log("  · 강의 일정 캘린더 없음 — 건너뜀 (rclone 미설정이면 inbox/에 두세요)")
        return False
    log(f"  · 시트: {os.path.basename(path)}")

    from github_store import load_webinar_schedule, _write_csv, \
        WEBINAR_SCHEDULE_PATH

    events = scan_events(path)
    log(f"  · 확정본 일정 {len(events)}건 훑음")
    sheet_df = parse_webinars(events)
    if sheet_df.empty:
        log("  ⚠️ 확정본에서 웨비나를 하나도 못 읽었다 — 기존 일정을 그대로 둔다")
        return False
    log(f"  · 확정본에서 웨비나 {len(sheet_df)}건 확인")

    merged, changes = merge(sheet_df, load_webinar_schedule())
    for c in changes[:12]:
        log(f"    - {c}")
    if len(changes) > 12:
        log(f"    … 외 {len(changes) - 12}건")

    if changes and not dry:
        _write_csv(WEBINAR_SCHEDULE_PATH, merged,
                   f"data: 강의 일정 캘린더 동기화 (웨비나 {len(changes)}건)")
        load_webinar_schedule.clear()
        log(f"  ✅ 웨비나 일정 {len(changes)}건 반영 (총 {len(merged)}건)")
    elif changes:
        log(f"  · [dry-run] 웨비나 {len(changes)}건 반영 예정 (총 {len(merged)}건)")
    else:
        log("  · 웨비나 일정 변경 없음")

    # ── 개강일 — 모집방이 기다리고 있는 값 ────────────────────────
    # 웨비나 표만 채워서는 '웨비나 없는 장기 모집방' 경고가 안 풀린다.
    # 그 판정이 보는 것은 모집방의 개강일이기 때문이다.
    from github_store import (load_campaigns, CAMPAIGNS_PATH)
    starts = parse_lecture_starts(events)
    log(f"  · 확정본에서 개강일 {len(starts)}건 확인")
    cmp_out, filled, odd = merge_lecture_starts(starts, load_campaigns())
    for f in filled:
        log(f"    - {f}")
    for o in odd:
        log(f"    ⚠️ {o}")
    if filled and not dry:
        _write_csv(CAMPAIGNS_PATH, cmp_out,
                   f"data: 강의 일정 캘린더에서 개강일 {len(filled)}건 채움")
        load_campaigns.clear()
        log(f"  ✅ 개강일 {len(filled)}건 반영")
    elif filled:
        log(f"  · [dry-run] 개강일 {len(filled)}건 반영 예정")

    return bool(changes or filled)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run(dry=args.dry_run)
