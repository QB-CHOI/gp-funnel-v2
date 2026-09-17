"""오카방 레지스트리 동기화 — "오카방의 모든 것.xlsx" → data/campaigns.csv.

원본은 hyems3@gmail.com 소유 구글 드라이브 파일로 거의 매일 갱신된다.
launchd는 구글 드라이브에 직접 접근할 수단이 없으므로(서비스 계정·rclone·
드라이브 데스크톱 전부 없음), **로컬에 내려온 사본**을 읽는 방식으로 붙인다.
찾는 위치는 SHEET_PATTERNS 참고 — 드라이브 데스크톱을 깔면 그 경로가,
아니면 inbox/에 떨궈둔 사본이 자동으로 잡힌다.

동기화 범위(의도적으로 좁게):
  · 방 번호가 **숫자**인 행만 = 오카방(웨비나 모집방). 아래쪽 수강생방
    블록은 '통합방'·'초급반'처럼 방 번호가 문자라 자연히 걸러진다.
  · **'삭제' 표시된 방은 새로 추가하지 않는다.** 이미 campaigns.csv에 있는
    방이면 is_current만 False로 내린다. 추적 이전에 사라진 방(18~22 등)까지
    끌어오면 캠페인 목록만 지저분해지고 인원 데이터도 없다.
  · end_date·memo·target_count는 **기존 값을 그대로 보존한다.** 시트의
    '다시보기 기한'은 재시청 만료일이지 캠페인 종료일이 아니다. 이걸
    end_date에 넣으면 차트의 캠페인 구간(_campaign_end_date)이 틀어진다.

실행:
    python3 scripts/sync_rooms_from_drive.py --dry-run   # 차이만 출력
    python3 scripts/sync_rooms_from_drive.py             # private repo에 반영
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

INBOX = os.path.join(ROOT, "inbox")
SHEET_NAME = "오카방&수강생방"

# 찾는 순서 = 신뢰도 순. 드라이브 데스크톱 경로가 있으면 항상 최신이다.
SHEET_PATTERNS = [
    os.path.expanduser("~/Library/CloudStorage/GoogleDrive-*/*/오카방의 모든 것*.xlsx"),
    os.path.expanduser("~/Library/CloudStorage/GoogleDrive-*/*/*/오카방의 모든 것*.xlsx"),
    os.path.join(INBOX, "오카방의 모든 것*.xlsx"),
    os.path.expanduser("~/Downloads/오카방의 모든 것*.xlsx"),
]

# 강의 코드 → 상품. 돈초부공·돈부공·돈초공이 모두 부동산이라 '부/초'를 함께 본다.
PRODUCT_CODES = [
    ("돈사공", "사주"),
    ("돈타공", "타로"),
    ("돈빌공", "빌딩"),
    ("돈초부공", "부동산"),
    ("돈부공", "부동산"),
    ("돈초공", "부동산"),
]

CAMPAIGNS_COLS = ["room_num", "campaign_name", "product", "cohort", "start_date",
                  "lecture_start_date", "end_date", "is_current", "memo", "target_count",
                  "status"]
# 시트가 권위값인 컬럼. 나머지(end_date·memo·target_count)는 앱 쪽이 권위값이라 보존.
SYNCED_COLS = ["campaign_name", "product", "cohort",
               "start_date", "lecture_start_date", "is_current", "status"]


# rclone으로 원본을 직접 받아오기 위한 좌표.
# 파일 ID로 집으므로 드라이브 전체를 동기화하지 않는다 — 매일 89KB 한 개만 받는다.
# 소유자가 남(hyems3@gmail.com)이라 '내 드라이브'에 없고 '공유 문서함'에 있는데,
# copyid는 ID로 직접 집어서 공유 여부와 무관하게 동작한다.
DRIVE_FILE_ID = "11WO5a32_WW7G4mDhRYdrFomjtW3wdA2l"
RCLONE_REMOTE = "gdrive"
SHEET_FILENAME = "오카방의 모든 것.xlsx"


def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def fetch_from_drive():
    """rclone이 설정돼 있으면 마스터 시트를 내려받아 inbox/를 최신으로 만든다.

    설정 전이면 조용히 건너뛴다 — 그 경우 inbox/에 있는 사본(사람이 넣어둔
    스냅샷)으로 계속 동작한다. 즉 이 함수는 '있으면 좋은' 단계지 전제가 아니다.
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
        log("  · rclone 미설정 — 드라이브 내려받기 건너뜀 (inbox/ 사본 사용)")
        return False

    dest = os.path.join(INBOX, SHEET_FILENAME)
    try:
        r = subprocess.run(
            [rclone, "backend", "copyid", f"{RCLONE_REMOTE}:", DRIVE_FILE_ID, dest],
            capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        log("  ⚠️ 드라이브 내려받기 시간 초과 — inbox/ 사본으로 계속")
        return False
    if r.returncode != 0:
        # 네트워크·인증 실패로 죽지 않는다. 옛 사본으로라도 도는 게 낫다.
        log(f"  ⚠️ 드라이브 내려받기 실패 — inbox/ 사본으로 계속: "
            f"{(r.stderr or '').strip().splitlines()[-1] if r.stderr else '원인 불명'}")
        return False
    log(f"  · 드라이브에서 최신본 수신 ({os.path.getsize(dest):,} bytes)")
    return True


def find_sheet(patterns=None):
    """마스터 시트 찾기 — auto_refresh의 NFD/NFC 대응 글롭을 그대로 쓴다."""
    from scripts.auto_refresh import find_order_files
    hits = find_order_files(patterns or SHEET_PATTERNS)
    return hits[-1] if hits else None


def _iso(v):
    """'25.07.21' 또는 엑셀 날짜 → 'YYYY-MM-DD'. 해석 불가면 빈 문자열."""
    if v is None or (isinstance(v, float) and pd.isna(v)) or pd.isna(v):
        return ""
    if isinstance(v, (datetime, pd.Timestamp)):
        return v.date().isoformat()
    s = str(v).strip()
    m = re.match(r"^(\d{2})\.(\d{1,2})\.(\d{1,2})$", s)
    if m:
        yy, mm, dd = (int(x) for x in m.groups())
        return f"20{yy:02d}-{mm:02d}-{dd:02d}"
    try:
        return pd.to_datetime(s).date().isoformat()
    except Exception:
        return ""


def _status(v):
    """'참여코드' 열 → 방 상태.

    운영팀이 이 열을 참여코드 자리이자 상태 표시로 함께 쓴다.
    '대기중'(웨비나 전 모집)·'웨비나종료'(끝남)·그 외는 실제 참여코드(운영 중).
    개강일이 비어 있어도 '웨비나대기'면 아직 정해지지 않은 게 정상이라,
    입력 누락 경고와 구분하기 위해 이 값을 함께 받아 둔다.
    """
    s = str(v or "").strip()
    if not s or s == "nan":
        return ""
    if "대기" in s:
        return "웨비나대기"
    if "종료" in s:
        return "웨비나종료"
    return "모집중"


def _product(name):
    for code, product in PRODUCT_CODES:
        if code in name:
            return product
    return ""


def _cohort(name):
    m = re.search(r"(\d+)\s*기", name)
    return f"{m.group(1)}기" if m else ""


CONTENT_SHEET = "오카방 업로드 계획"
CONTENT_COLS = {2: "사주", 3: "타로", 4: "부동산", 5: "빌딩", 6: "종료방"}


def _content_title(text):
    """발행 문구 → 제목 한 줄. 첫 문장이 곧 후킹이라 그걸 제목으로 쓴다."""
    s = re.sub(r"https?://\S+", "", str(text))
    s = s.replace("📌", " ").replace("👉", " ")
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in s.splitlines()]
    lines = [ln for ln in lines if len(ln) >= 4]
    # 인사말로 시작하는 공지는 다음 줄이 실제 내용이다
    if lines and re.match(r"^안녕하세[요유][,.\s]", lines[0]) and len(lines) > 1:
        return lines[1][:80]
    return lines[0][:80] if lines else ""


def parse_content(path):
    """시트 하단 '오카방 업로드 계획' 블록 → 발행 기록 DataFrame.

    날짜(행) × 상품군(열) 격자에 발행 문구가 들어 있다. 문구 끝의 유튜브
    링크가 실제 콘텐츠이고, 첫 문장이 그날 쓴 후킹이다.
    """
    try:
        raw = pd.read_excel(path, sheet_name=CONTENT_SHEET, header=None)
    except ValueError:                      # 시트가 없는 버전의 파일
        return pd.DataFrame(columns=["date", "channel", "content_type",
                                     "title", "url", "memo"])
    rows = []
    for _, r in raw.iterrows():
        day = _iso(r.get(0))
        if not day:
            continue
        for col, product in CONTENT_COLS.items():
            cell = r.get(col)
            if cell is None or pd.isna(cell) or not str(cell).strip():
                continue
            m = re.search(r"https?://\S+", str(cell))
            url = m.group(0).rstrip(")]},.") if m else ""
            body = str(cell).strip()
            # 이 칸은 '발행할 문구'와 '기획 메모'가 섞여 있다. 링크가 있거나
            # 본문이 긴 것만 실제 발행으로 본다 — '블로그 요약', '돈타공 그로스
            # 구매유도' 같은 짧은 지시 메모까지 발행 기록으로 세면 안 된다.
            if not url and len(body) < 200:
                continue
            title = _content_title(cell)
            if not title and not url:
                continue
            rows.append({
                "date": day, "channel": "오카방",
                "content_type": "유튜브 영상" if "youtu" in url else "게시글",
                "title": title, "url": url, "memo": f"{product} 방 발행",
            })
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def merge_content(sheet_df, current_df):
    """시트 발행 기록을 기존 로그에 더한다. (합쳐진 df, 추가건수)

    앱 폼으로 직접 넣은 기록을 지우지 않도록 **추가만** 한다.
    같은 날 같은 링크(링크가 없으면 같은 제목)면 이미 있는 것으로 본다.
    """
    if sheet_df.empty:
        return current_df, 0

    def _norm(v):
        """빈 칸 표기를 하나로 — CSV를 되읽으면 빈 URL이 'nan'으로 돌아온다."""
        s = str(v).strip()
        return "" if s.lower() in ("nan", "none", "nat", "<na>") else s

    def _key(r):
        return (_norm(r.get("date")), _norm(r.get("url")) or _norm(r.get("title")))

    cur = current_df.copy()
    if not cur.empty:
        # 로더는 date를 datetime.date로 바꿔 주는데 시트 쪽은 문자열이라,
        # 그대로 붙이면 정렬에서 타입이 섞여 터진다. ISO 문자열로 통일.
        cur["date"] = cur["date"].map(_norm)

    seen = {_key(r) for _, r in cur.iterrows()} if not cur.empty else set()
    fresh = [r for _, r in sheet_df.iterrows() if _key(r) not in seen]
    if not fresh:
        return current_df, 0
    merged = pd.concat([cur, pd.DataFrame(fresh)], ignore_index=True)
    return merged.sort_values("date").reset_index(drop=True), len(fresh)


def parse_rooms(path):
    """시트 상단 오카방 블록 → DataFrame(room_num 기준)."""
    raw = pd.read_excel(path, sheet_name=SHEET_NAME, header=0)
    cols = {str(c).strip(): c for c in raw.columns}
    need = ["방 번호", "모집 강의", "개설일", "강의 시작일"]
    missing = [c for c in need if c not in cols]
    if missing:
        raise ValueError(f"시트 컬럼 누락: {missing} — 원본 구조가 바뀐 듯합니다")

    rows = []
    for _, r in raw.iterrows():
        num = pd.to_numeric(r[cols["방 번호"]], errors="coerce")
        if pd.isna(num):          # 수강생방 블록('통합방'·'초급반' 등)
            continue
        name = str(r[cols["모집 강의"]] or "").strip()
        if not name or name == "nan":
            continue
        deleted = str(r[cols.get("구분", "구분")] if "구분" in cols else "").strip() == "삭제"
        rows.append({
            "room_num": int(num),
            "campaign_name": name,
            "product": _product(name),
            "cohort": _cohort(name),
            "start_date": _iso(r[cols["개설일"]]),
            "lecture_start_date": _iso(r[cols["강의 시작일"]]),
            "is_current": not deleted,
            # 참여코드 열은 선택 — 없으면 빈 값으로 두고 기존 동작을 유지한다.
            "status": _status(r[cols["참여코드"]]) if "참여코드" in cols else "",
        })
    return pd.DataFrame(rows).drop_duplicates(subset="room_num", keep="last")


def merge(sheet_df, current_df):
    """시트 → campaigns.csv 병합. (결과 df, 변경내역 리스트) 반환."""
    changes = []
    out = current_df.copy()
    if out.empty:
        out = pd.DataFrame(columns=CAMPAIGNS_COLS)
    # 컬럼이 늘어난 직후(status 신설 등)엔 기존 CSV에 그 열이 없다 — 빈 값으로 채운다.
    for c in CAMPAIGNS_COLS:
        if c not in out.columns:
            out[c] = ""
    out["room_num"] = pd.to_numeric(out["room_num"], errors="coerce").astype("Int64")

    known = set(out["room_num"].dropna().astype(int))
    for _, s in sheet_df.iterrows():
        rn = int(s["room_num"])
        if rn in known:
            idx = out.index[out["room_num"] == rn][0]
            for c in SYNCED_COLS:
                old, new = out.at[idx, c], s[c]
                # 시트가 비어 있으면 기존 값을 지우지 않는다(부분 입력 대비).
                if c in ("start_date", "lecture_start_date", "status") and not new:
                    continue
                if c == "is_current":
                    old = str(old).upper() in ("TRUE", "1", "YES")
                elif pd.isna(old):
                    old = ""
                if old != new:
                    out.at[idx, c] = new
                    changes.append(f"{rn}번 {c}: {old!r} → {new!r}")
        elif s["is_current"]:      # '삭제'된 미추적 방은 새로 끌어오지 않는다
            new_row = {c: "" for c in CAMPAIGNS_COLS}
            new_row.update(s.to_dict())
            new_row["target_count"] = 0
            out = pd.concat([out, pd.DataFrame([new_row])], ignore_index=True)
            changes.append(f"{rn}번 신규 추가: {s['campaign_name']} ({s['product']})")

    out = out.sort_values("room_num").reset_index(drop=True)
    return out[CAMPAIGNS_COLS], changes


def run(dry=False):
    """auto_refresh에서 호출하는 진입점. 변경이 있었으면 True."""
    fetch_from_drive()          # 되면 최신본, 안 되면 기존 사본으로 진행
    path = find_sheet()
    if not path:
        log("  · 오카방 마스터 시트 없음 — 건너뜀 (드라이브 데스크톱 또는 inbox/)")
        return False
    log(f"  · 시트: {os.path.basename(path)}")

    from github_store import (load_campaigns, load_rooms, save_rooms_batch,
                              load_content, _write_csv)
    sheet_df = parse_rooms(path)
    merged, changes = merge(sheet_df, load_campaigns())

    # 콘텐츠 발행 기록 — 같은 시트 하단 블록. 방 목록과 함께 따라온다.
    content_add = 0
    try:
        c_sheet = parse_content(path)
        c_merged, content_add = merge_content(c_sheet, load_content())
        if content_add and not dry:
            _write_csv("data/content_logs.csv", c_merged,
                       f"data: 오카방 발행 기록 동기화 ({content_add}건)")
            load_content.clear()
        if content_add:
            log(f"  {'· [dry-run]' if dry else '✅'} 콘텐츠 발행 기록 "
                f"{content_add}건 {'반영 예정' if dry else '추가'} (누적 {len(c_merged)}건)")
    except Exception as e:              # 콘텐츠는 부가 정보 — 실패해도 방 동기화는 계속
        log(f"  ⚠️ 콘텐츠 블록 처리 실패({type(e).__name__}) — 방 목록은 계속 진행")

    # 일일 입력 화면은 rooms.csv를 돈다. campaigns.csv에만 넣으면 새 방이
    # 입력 목록에 안 떠서 인원이 안 쌓인다 — 진행 중인 방은 여기도 채운다.
    # 이름은 사람이 붙인 별칭('채팅방 37 (부동산2)')이 있어 기존 값은 건드리지 않는다.
    #
    # 새 방 이름에 상품·기수를 함께 적는다. 예전에는 '채팅방 45'처럼 번호만
    # 넣었는데, 아무도 이름을 채우지 않아 보고서 표에 번호만 덩그러니 남았다
    # (2026-09 실측: 42·43·45번이 그 상태로 대표 보고에 나갔다). 시트에 상품과
    # 기수가 이미 있으니 처음부터 붙여 준다. 사람이 나중에 고치는 건 자유다.
    known_rooms = load_rooms()

    def _auto_name(r):
        rn = int(r["room_num"])
        p, c = str(r.get("product", "")).strip(), str(r.get("cohort", "")).strip()
        return f"채팅방 {rn} ({p} {c})" if p and c else f"채팅방 {rn}"

    missing = {int(r["room_num"]): _auto_name(r)
               for _, r in sheet_df.iterrows()
               if r["is_current"] and int(r["room_num"]) not in known_rooms}

    if not changes and not missing:
        log(f"  · 오카방 {len(sheet_df)}개 — 변경 없음")
        return bool(content_add)        # 콘텐츠만 늘어난 경우도 '갱신 있음'
    for c in changes:
        log(f"    · {c}")
    for rn in sorted(missing):
        log(f"    · {rn}번 일일 입력 목록에 추가")
    if dry:
        log(f"  · [dry-run] campaigns.csv {len(changes)}건 · rooms.csv {len(missing)}건 반영 예정")
        return True

    if changes:
        _write_csv("data/campaigns.csv", merged,
                   f"data: 오카방 레지스트리 자동 동기화 ({len(changes)}건)")
        load_campaigns.clear()
        log(f"  ✅ campaigns.csv 갱신 ({len(changes)}건, {len(merged)}행)")
    if missing:
        save_rooms_batch(missing)
        log(f"  ✅ rooms.csv 갱신 ({len(missing)}건 추가)")
    return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="확인만, 쓰지 않음")
    a = ap.parse_args()
    raise SystemExit(0 if run(a.dry_run) is not None else 1)
