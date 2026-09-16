"""주문 원본(강의별_리스트 xlsx) → 파생 집계 CSV 일괄 재생성.

사장님이 새 주문 명단을 받으면, 이 스크립트 한 번으로 사이트의 모든
'주문 기반' 집계(월별×강의·고객 LTV/재구매/리텐션·무료특강 후킹 등 15종)를
재생성한다. 개인정보(이름·번호)는 저장하지 않고 집계 수치만 만든다.

사용:
  # 검증만 (기본, 쓰지 않음) — 재생성값과 합계를 출력
  python3 scripts/refresh_order_aggregates.py [주문파일.xlsx]

  # private 저장소(QB-CHOI/gp-funnel-data)에 실제 반영
  python3 scripts/refresh_order_aggregates.py [주문파일.xlsx] --write

파일 인자를 생략하면 ~/Downloads 의 가장 최신 '강의별_리스트*.xlsx' 를 쓴다.
--write 는 gh CLI 인증(repo 스코프)이 필요하다.

⚠️ PDF/이미지/시트 기반 데이터(cohort_revenue·course_summary·cohort_stage·
region_*·campaign_adspend·competitor_courses·monthly_performance 등)는
주문 원본에서 안 나오므로 이 스크립트가 건드리지 않는다.
"""
import base64
import glob
import os
import subprocess
import sys

import pandas as pd

# 저장소 루트를 import 경로에 넣는다 — 스크립트를 scripts/에서 실행하면
# sys.path[0]이 scripts/라 루트의 github_store를 못 찾는다.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATA_REPO = "QB-CHOI/gp-funnel-data"
PRODUCTS = ["사주", "타로", "부동산", "빌딩"]


# 유료 서적·교재. 강의가 아니다.
# 이름에 '사주'·'타로'가 들어 있어 그냥 두면 1.5만원짜리 책이 300만원짜리
# 강의 매출에 섞이고, 책만 산 사람이 '강의 고객'으로 잡혀 재구매율·LTV가
# 부풀려진다(2026-09 실측: 한 달 746명·1,122만원).
# 무료 전자책·이벤트('[무료 전자책]', '[전자책 무료나눔 이벤트]',
# '[부동산 기초 전자책 … 이벤트]')는 **일부러 뺐다** — 0원 리드 수집이라
# 상품별 퍼널(신청→결제)의 분모로 쓰이고 있다. 여기로 옮기면 전환율이 깨진다.
BOOK_KEYS = ("[전자책]", "[입문서", "교재 추가 구매", "나를 설명하는 사주",
             "책 배송")


# ── 공통 분류기 ────────────────────────────────────────────────────
def product_of(name: str) -> str:
    x = str(name)
    if any(k in x for k in BOOK_KEYS):
        return "서적"
    if any(k in x for k in ["돈사공", "사주", "재물운", "운세", "명리"]):
        return "사주"
    if any(k in x for k in ["돈빌공", "빌딩", "건물"]):
        return "빌딩"
    if any(k in x for k in ["돈타공", "타로", "소울카드"]):
        return "타로"
    if any(k in x for k in ["돈초", "돈부공", "부동산", "내 집 마련", "분양", "규제"]):
        return "부동산"
    return "기타"


def webinar_topic(name: str):
    x = str(name)
    rules = [
        ("재물운 투자법", ("사주", "재물운 투자법")),
        ("사주 LIVE", ("사주", "사주 LIVE 특강")),
        ("돈이 따르는 운명", ("사주", "돈이 따르는 운명")),
        ("강남 부자 사주", ("사주", "강남 부자 사주")),
        ("건물 9채", ("빌딩", "건물 9채의 비법")),
        ("480억 건물주", ("빌딩", "480억 건물주의 비법")),
        ("무혈입성", ("부동산", "OO지역 무혈입성")),
        ("수도권 저평가", ("부동산", "수도권 저평가 단지")),
        ("2차 부동산 상승", ("부동산", "2차 부동산 상승")),
        ("전매제한", ("부동산", "분양권 전매제한")),
        ("대선", ("부동산", "대선 이후 매수 전략")),
        ("소울카드", ("타로", "소울카드 궁합")),
        ("돈 버는 타로", ("타로", "돈 버는 타로")),
        ("타로카드 한 장", ("타로", "타로카드 한 장")),
    ]
    for kw, res in rules:
        if kw == "규제":  # (안 씀) 예약
            continue
        if kw in x:
            return res
    if "규제" in x and "대응" in x:
        return ("부동산", "새 규제 대응 전략")
    return ("기타", "기타")


_BOOK = "전자책|달력|입춘문|선물|나눔|이벤트|리스트|해석집"


# ── 로드 & 파생 컬럼 ───────────────────────────────────────────────
def load_orders(path: str) -> pd.DataFrame:
    o = pd.read_excel(path, sheet_name="sheet1")
    o["pay"] = pd.to_numeric(o["최종결제금액"], errors="coerce").fillna(0)
    o["d"] = pd.to_datetime(o["주문일"], errors="coerce")
    o["cust"] = (o["주문자 이름"].astype(str).str.strip() + "|"
                 + o["주문자 번호"].astype(str).str.strip())
    o = o[~o["cust"].str.startswith("nan|")]
    o["product"] = o["상품명"].map(product_of)
    return o


# ── 집계 생성기 (각각 (파일명, DataFrame, 검증문자열) 반환) ─────────────
def build_all(o: pd.DataFrame) -> dict:
    out = {}
    paid = o[(o["pay"] > 0) & o["d"].notna()].copy()
    paid["month"] = paid["d"].dt.strftime("%Y-%m")
    paid_cust_prods = {c: set(g["product"]) for c, g in paid.groupby("cust")}
    paid_cust = set(paid["cust"])

    # 1) monthly_by_course (기타 제외)
    rows = []
    dd = o[(o["d"].notna())].copy()
    dd["month"] = dd["d"].dt.strftime("%Y-%m")
    for (m, p), g in dd[dd["product"] != "기타"].groupby(["month", "product"]):
        rows.append({"month": m, "product": p,
                     "paid_revenue": int(g.loc[g["pay"] > 0, "pay"].sum()),
                     "paid_orders": int((g["pay"] > 0).sum()),
                     "free_signups": int((g["pay"] == 0).sum())})
    out["monthly_by_course.csv"] = pd.DataFrame(rows).sort_values(["month", "product"])

    # 1-1) monthly_performance (전 상품 합계 — 런레이트·전망·월간 보고서의 근거)
    # 원래 '주문 원본에서 안 나온다'고 보고 손으로 관리하던 파일인데, 실제로는
    # 여기서 정확히 재현된다(2026-06: 무료 4,287·유료 345·매출 9.4억 일치).
    # 수동 관리로 두면 주문 명단을 갱신해도 이 파일만 옛날 값으로 남아,
    # 매출 추이와 전망이 통째로 뒤처진다.
    mp = []
    for m, g in dd.groupby("month"):
        _free = int((g["pay"] == 0).sum())
        _paid = int((g["pay"] > 0).sum())
        mp.append({"month": m, "free_signups": _free, "paid_orders": _paid,
                   "revenue": int(g.loc[g["pay"] > 0, "pay"].sum()),
                   "conv_rate": round(_paid / _free * 100, 2) if _free else 0.0})
    out["monthly_performance.csv"] = pd.DataFrame(mp).sort_values("month")

    # 고객 단위 공통
    g = paid.groupby("cust")
    oc = g.size()
    spend = g["pay"].sum()
    paid["mi"] = paid["d"].dt.year * 12 + paid["d"].dt.month
    first_mi = paid.groupby("cust")["mi"].transform("min")
    paid["k"] = paid["mi"] - first_mi
    # 홈 상품 = 첫 구매일의 '최고 결제' 상품(동일 첫날 다상품 구매 시 결정적 타이브레이크)
    _fd = paid[paid["d"] == paid.groupby("cust")["d"].transform("min")]
    home = (_fd.sort_values(["pay", "product"], ascending=[False, True])
            .groupby("cust")["product"].first())
    paid["home"] = paid["cust"].map(home)
    last_mi = paid["mi"].max()

    # 2) cust_repeat_dist
    rb = oc.map(lambda c: "1회" if c == 1 else ("2회" if c == 2 else ("3~4회" if c <= 4 else "5회+")))
    rd = rb.value_counts().reindex(["1회", "2회", "3~4회", "5회+"]).fillna(0).astype(int)
    out["cust_repeat_dist.csv"] = pd.DataFrame({"bucket": rd.index, "customers": rd.values})

    # 3) cust_ltv_dist
    def lb(v):
        v /= 1e4
        return ("~100만" if v < 100 else "100~300만" if v < 300 else "300~500만"
                if v < 500 else "500~1000만" if v < 1000 else "1000만+")
    ld = spend.map(lb).value_counts().reindex(
        ["~100만", "100~300만", "300~500만", "500~1000만", "1000만+"]).fillna(0).astype(int)
    out["cust_ltv_dist.csv"] = pd.DataFrame({"bucket": ld.index, "customers": ld.values})

    # 4) cust_product_repeat
    pr = []
    for p in PRODUCTS:
        sub = paid[paid["product"] == p]
        cc = sub.groupby("cust").size()
        pr.append({"product": p, "buyers": int(cc.shape[0]),
                   "repeat_buyers": int((cc >= 2).sum()),
                   "repeat_rate": round((cc >= 2).mean() * 100, 1) if len(cc) else 0,
                   "avg_ltv": int(sub.groupby("cust")["pay"].sum().mean()) if len(cc) else 0})
    out["cust_product_repeat.csv"] = pd.DataFrame(pr)

    # 5) cust_cross_sell (co-occurrence)
    xs = []
    for a in PRODUCTS:
        buyers = [c for c, ps in paid_cust_prods.items() if a in ps]
        for b in PRODUCTS:
            if a == b:
                continue
            also = sum(1 for c in buyers if b in paid_cust_prods[c])
            xs.append({"from": a, "to": b, "rate": round(also / len(buyers) * 100, 1) if buyers else 0,
                       "count": also})
    out["cust_cross_sell.csv"] = pd.DataFrame(xs)

    # 6) cust_monthly_new_repeat
    ps = paid.sort_values("d")
    ps["is_new"] = ps["d"] == ps.groupby("cust")["d"].transform("min")
    mr = []
    for m, gm in ps.groupby("month"):
        new, rep = gm[gm["is_new"]], gm[~gm["is_new"]]
        mr.append({"month": m, "new_customers": int(new["cust"].nunique()),
                   "repeat_orders": int(len(rep)), "new_revenue": int(new["pay"].sum()),
                   "repeat_revenue": int(rep["pay"].sum())})
    out["cust_monthly_new_repeat.csv"] = pd.DataFrame(mr).sort_values("month")

    # 7) cust_repeat_timing
    gaps = g["mi"].apply(lambda s: (sorted(s.unique())[1] - sorted(s.unique())[0])
                         if s.nunique() >= 2 else None).dropna()
    tb = gaps.map(lambda v: "1개월" if v == 1 else ("2~3개월" if v <= 3 else
                  ("4~6개월" if v <= 6 else "7개월+")))
    td = tb.value_counts().reindex(["1개월", "2~3개월", "4~6개월", "7개월+"]).fillna(0).astype(int)
    out["cust_repeat_timing.csv"] = pd.DataFrame({"bucket": td.index, "customers": td.values})

    # 8~9) 리텐션 커브 & 매트릭스 (우측 절단)
    paid["acq"] = paid.groupby("cust")["d"].transform("min").dt.strftime("%Y-%m")
    rm = []
    for acq, sub in paid.groupby("acq"):
        csize = sub["cust"].nunique()
        acq_mi = sub["mi"].min()
        for k in range(1, 7):
            if acq_mi + k > last_mi:
                continue
            rm.append({"acq": acq, "k": k, "cohort_size": csize,
                       "active": sub[sub["k"] == k]["cust"].nunique()})
    rmdf = pd.DataFrame(rm)
    curve = rmdf.groupby("k").apply(
        lambda s: round(s["active"].sum() / s["cohort_size"].sum() * 100, 1)).reset_index()
    curve.columns = ["k", "pct"]
    out["cust_retention_curve.csv"] = curve
    out["cust_retention_matrix.csv"] = rmdf.assign(
        pct=(rmdf["active"] / rmdf["cohort_size"] * 100).round(1))[["acq", "k", "pct", "cohort_size"]]

    # 10~12) 상품군별 리텐션 (홈 상품 기준)
    p_time, p_ret, p_nb = [], [], []
    for p in PRODUCTS:
        sub = paid[paid["home"] == p]
        cg = sub.groupby("cust")
        cc = cg.size()
        gaps_p = cg["mi"].apply(lambda s: (sorted(s.unique())[1] - sorted(s.unique())[0])
                                if s.nunique() >= 2 else None).dropna()
        tdp = (gaps_p.map(lambda v: "1개월" if v == 1 else ("2~3개월" if v <= 3 else
               ("4~6개월" if v <= 6 else "7개월+"))).value_counts())
        for b in ["1개월", "2~3개월", "4~6개월", "7개월+"]:
            p_time.append({"product": p, "bucket": b, "customers": int(tdp.get(b, 0))})
        eg = sub.groupby("cust")["mi"].min()
        for k in range(1, 7):
            elig = eg[eg + k <= last_mi].index
            if len(elig) == 0:
                continue
            active = sub[(sub["cust"].isin(elig)) & (sub["k"] == k)]["cust"].nunique()
            p_ret.append({"product": p, "k": k, "pct": round(active / len(elig) * 100, 1)})
        same = diff = 0
        for c, g2 in sub.groupby("cust"):
            g2 = g2.sort_values("d")
            secs = g2[g2["mi"] > g2["mi"].min()]
            if len(secs):
                if secs.iloc[0]["product"] == p:
                    same += 1
                else:
                    diff += 1
        tot = same + diff
        p_nb.append({"product": p, "home_customers": int(cc.shape[0]),
                     "repeat_rate": round((cc >= 2).mean() * 100, 1) if len(cc) else 0,
                     "same_pct": round(same / tot * 100, 1) if tot else 0,
                     "diff_pct": round(diff / tot * 100, 1) if tot else 0})
    out["cust_product_timing.csv"] = pd.DataFrame(p_time)
    out["cust_product_retention.csv"] = pd.DataFrame(p_ret)
    out["cust_product_nextbuy.csv"] = pd.DataFrame(p_nb)

    # 13) cust_crosssell_path (순차 다음구매)
    xp = []
    for p in PRODUCTS:
        sub = paid[paid["home"] == p]
        dest = {}
        for c, g2 in sub.groupby("cust"):
            g2 = g2.sort_values("d")
            secs = g2[g2["mi"] > g2["mi"].min()]
            if len(secs):
                nx = secs.iloc[0]["product"]
                if nx != p and nx in PRODUCTS:
                    dest[nx] = dest.get(nx, 0) + 1
        tot = sum(dest.values())
        for dp in PRODUCTS:
            if dp == p:
                continue
            c = dest.get(dp, 0)
            xp.append({"home": p, "dest": dp, "customers": c,
                       "pct": round(c / tot * 100, 1) if tot else 0})
    out["cust_crosssell_path.csv"] = pd.DataFrame(xp)

    # 14~15) webinar topics & conversion
    fn = o["상품명"].astype(str)
    is_book = fn.str.contains(_BOOK, regex=True)
    free = o[(o["pay"] == 0) & (~is_book)].copy()
    tp = [webinar_topic(x) for x in free["상품명"].astype(str)]
    free["wp"] = [t[0] for t in tp]
    free["topic"] = [t[1] for t in tp]
    free = free[free["wp"] != "기타"]
    wt = (free.groupby(["wp", "topic"]).size().reset_index(name="signups")
          .rename(columns={"wp": "product"}).sort_values("signups", ascending=False))
    out["webinar_topics.csv"] = wt
    wc = []
    for (p, t), gg in free.groupby(["wp", "topic"]):
        custs = set(gg["cust"])
        conv = [c for c in custs if c in paid_cust]
        sc = [c for c in conv if p in paid_cust_prods.get(c, set())]
        wc.append({"product": p, "topic": t, "unique_signups": len(custs),
                   "converters": len(conv),
                   "conv_rate": round(len(conv) / len(custs) * 100, 1) if custs else 0,
                   "self_converters": len(sc),
                   "self_rate": round(len(sc) / len(custs) * 100, 1) if custs else 0,
                   "self_share": round(len(sc) / len(conv) * 100, 0) if conv else 0})
    out["webinar_conversion.csv"] = pd.DataFrame(wc).sort_values("converters", ascending=False)
    return out


def put(path: str, df: pd.DataFrame):
    enc = base64.b64encode(df.to_csv(index=False).encode()).decode()
    sha = subprocess.run(["gh", "api", f"repos/{DATA_REPO}/contents/data/{path}", "--jq", ".sha"],
                         capture_output=True, text=True).stdout.strip()
    args = ["gh", "api", "--method", "PUT", f"repos/{DATA_REPO}/contents/data/{path}",
            "-f", f"message=주문 집계 자동 갱신: {path}", "-f", f"content={enc}", "--jq", ".commit.sha"]
    if sha:
        args += ["-f", f"sha={sha}"]
    r = subprocess.run(args, capture_output=True, text=True)
    return r.returncode == 0, (r.stdout.strip()[:10] if r.returncode == 0 else r.stderr[:120])


def main():
    args = [a for a in sys.argv[1:] if a != "--write"]
    write = "--write" in sys.argv
    if args:
        path = args[0]
    else:
        cands = sorted(glob.glob(os.path.expanduser("~/Downloads/강의별_리스트*.xlsx")))
        if not cands:
            print("❌ 주문 파일을 찾을 수 없습니다. 경로를 인자로 주세요."); return 1
        path = cands[-1]
    print(f"📄 주문 원본: {path}")
    o = load_orders(path)
    print(f"   총 {len(o):,}행 · 유료 {int((o['pay']>0).sum()):,} · 고유 고객 {o['cust'].nunique():,}")
    out = build_all(o)

    print(f"\n=== 재생성 집계 {len(out)}종 (검증) ===")
    for name, df in out.items():
        note = ""
        if name == "monthly_by_course.csv":
            note = f"매출합 {df['paid_revenue'].sum()/1e8:.1f}억 · {df['month'].nunique()}개월"
        elif name == "webinar_conversion.csv":
            note = f"총 전환자 {int(df['converters'].sum()):,}"
        elif "customers" in df.columns:
            note = f"합 {int(df['customers'].sum()):,}"
        print(f"  {name:<34} {len(df):>3}행  {note}")

    if not write:
        print("\n(검증 모드 — 저장 안 함. 반영하려면 --write 추가)")
        return 0
    print("\n=== private 저장소 반영 ===")
    ok = 0
    for name, df in out.items():
        s, msg = put(name, df)
        ok += s
        print(f"  {'✅' if s else '🚨'} {name}: {msg}")
    print(f"\n{ok}/{len(out)} 저장 완료")
    if ok == len(out):
        # 기준일을 함께 갱신해야 사이트가 '어느 달까지 완결됐나'를 바르게 본다
        _asof = o["d"].max().date()
        try:
            from github_store import update_order_asof
            print(f"  {'✅' if update_order_asof(_asof) else '⚠️'} 기준일 {_asof} 반영")
        except Exception as e:
            print(f"  ⚠️ 기준일 반영 실패({type(e).__name__}) — 데이터 현황에서 수동 확인 필요")
    return 0 if ok == len(out) else 1


if __name__ == "__main__":
    sys.exit(main())
