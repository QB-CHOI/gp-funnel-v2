"""경영진 보고용 PDF 생성기 (대기업 업무 보고서 양식).

reportlab 순수 파이썬 → Streamlit Cloud에서 시스템 의존성 없이 동작.
한글은 저장소에 내장한 NanumGothic(OFL) 사용.
사이트에서 버튼 한 번으로 PDF 다운로드·출력 가능.
"""
import io
import os
from datetime import date as _date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, SimpleDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
    Table, TableStyle, KeepTogether, Flowable,
)

# ── 폰트 등록 ────────────────────────────────────────────────────
_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")
_FONTS_OK = False


def _register_fonts():
    global _FONTS_OK
    if _FONTS_OK:
        return
    try:
        pdfmetrics.registerFont(TTFont("Nanum", os.path.join(_FONT_DIR, "NanumGothic-Regular.ttf")))
        pdfmetrics.registerFont(TTFont("Nanum-B", os.path.join(_FONT_DIR, "NanumGothic-Bold.ttf")))
        pdfmetrics.registerFont(TTFont("Nanum-EB", os.path.join(_FONT_DIR, "NanumGothic-ExtraBold.ttf")))
        pdfmetrics.registerFontFamily("Nanum", normal="Nanum", bold="Nanum-B")
        _FONTS_OK = True
    except Exception:
        # 폰트 로드 실패 시 기본 폰트로 폴백 (한글 깨질 수 있으나 크래시 방지)
        _FONTS_OK = False


F   = "Nanum"
FB  = "Nanum-B"
FEB = "Nanum-EB"

# ── 색상 (기업 보고서 — 네이비 + 골드 액센트) ────────────────────
NAVY      = colors.HexColor("#1C3A5E")
NAVY_D    = colors.HexColor("#132A45")
GOLD      = colors.HexColor("#B0812A")
INK       = colors.HexColor("#22272E")
INK_SOFT  = colors.HexColor("#5B6470")
LINE      = colors.HexColor("#D9DEE5")
LINE_SOFT = colors.HexColor("#EDF0F4")
BG_SOFT   = colors.HexColor("#F5F7FA")
GOOD      = colors.HexColor("#1E7A3D")
CRIT      = colors.HexColor("#C0392B")
WHITE     = colors.white

PROD_COLOR = {
    "사주": colors.HexColor("#5C6BC0"),
    "타로": colors.HexColor("#E0457B"),
    "부동산": colors.HexColor("#1E9E8A"),
    "빌딩": colors.HexColor("#E8632B"),
}


def _styles():
    return {
        "title":   ParagraphStyle("title", fontName=FEB, fontSize=20, leading=26, textColor=NAVY),
        "subtitle": ParagraphStyle("subtitle", fontName=F, fontSize=10.5, leading=15, textColor=INK_SOFT),
        "sec":     ParagraphStyle("sec", fontName=FEB, fontSize=13, leading=18, textColor=NAVY, spaceBefore=2, spaceAfter=2),
        "h3":      ParagraphStyle("h3", fontName=FB, fontSize=10.5, leading=15, textColor=INK),
        "body":    ParagraphStyle("body", fontName=F, fontSize=9.5, leading=15, textColor=INK),
        "body_s":  ParagraphStyle("body_s", fontName=F, fontSize=8.5, leading=13, textColor=INK_SOFT),
        "cell":    ParagraphStyle("cell", fontName=F, fontSize=8.7, leading=12, textColor=INK),
        "cell_b":  ParagraphStyle("cell_b", fontName=FB, fontSize=8.7, leading=12, textColor=INK),
        "cell_r":  ParagraphStyle("cell_r", fontName=F, fontSize=8.7, leading=12, textColor=INK, alignment=TA_RIGHT),
        "cell_h":  ParagraphStyle("cell_h", fontName=FB, fontSize=8.7, leading=12, textColor=WHITE, alignment=TA_CENTER),
        "kpi_v":   ParagraphStyle("kpi_v", fontName=FEB, fontSize=15, leading=18, textColor=NAVY, alignment=TA_LEFT),
        "kpi_k":   ParagraphStyle("kpi_k", fontName=F, fontSize=8, leading=11, textColor=INK_SOFT),
        "kpi_d":   ParagraphStyle("kpi_d", fontName=FB, fontSize=8, leading=11),
        "bullet":  ParagraphStyle("bullet", fontName=F, fontSize=9.3, leading=15, textColor=INK, leftIndent=10, bulletIndent=0),
    }


# ── 도식: 기수별 전환율 가로 막대 차트 (순수 그리기) ─────────────
class ConversionBars(Flowable):
    """funnel_rows → 기수별 웨비나→유료 전환율 가로 막대 도식."""
    def __init__(self, funnel_rows, width, row_h=17, pad_top=6):
        super().__init__()
        self.rows = sorted(funnel_rows, key=lambda r: r.get("conversion") or 0, reverse=True)
        self.width = width
        self.row_h = row_h
        self.pad_top = pad_top
        self.height = pad_top + row_h * len(self.rows) + 6

    def draw(self):
        c = self.canv
        rows = self.rows
        if not rows:
            return
        label_w = 78
        val_w = 96
        bar_x = label_w + 6
        bar_max = self.width - label_w - val_w - 12
        max_conv = max((r.get("conversion") or 0) for r in rows) or 1
        y = self.height - self.pad_top - self.row_h + 4

        for r in rows:
            conv = r.get("conversion") or 0
            fam = str(r.get("label", "")).split(" ")[0]
            col = PROD_COLOR.get(fam, NAVY)
            # 라벨
            c.setFont(FB, 8.3); c.setFillColor(INK)
            c.drawRightString(label_w, y + 2, str(r.get("label", "")))
            # 막대 배경
            c.setFillColor(LINE_SOFT)
            c.roundRect(bar_x, y, bar_max, self.row_h - 6, 2, fill=1, stroke=0)
            # 막대
            w = max(3, bar_max * (conv / max_conv))
            c.setFillColor(col)
            c.roundRect(bar_x, y, w, self.row_h - 6, 2, fill=1, stroke=0)
            # 값
            c.setFont(FB, 8.3); c.setFillColor(INK)
            c.drawString(bar_x + bar_max + 8, y + 2,
                         f"{conv:.1f}%   ({int(r.get('enrolled',0)):,}명)")
            y -= self.row_h


class TrendLine(Flowable):
    """기간 총원 추이 라인 차트 (면적 채움 + 끝점 강조 + 이벤트 마커).
    series=[(date_str, value), ...], mark=(date_str, label) 선택."""
    def __init__(self, series, width, height=88, mark=None):
        super().__init__()
        self.series = [(str(d), int(v)) for d, v in series if v is not None]
        self.width = width
        self.height = height
        self.mark = mark

    def draw(self):
        c = self.canv
        s = self.series
        if len(s) < 2:
            return
        pad_l, pad_r, pad_t, pad_b = 8, 12, 14, 20
        gw = self.width - pad_l - pad_r
        gh = self.height - pad_t - pad_b
        vals = [v for _, v in s]
        vmin, vmax = min(vals), max(vals)
        rng = (vmax - vmin) or 1
        n = len(s)
        xs = [pad_l + gw * i / (n - 1) for i in range(n)]
        ys = [pad_b + gh * (v - vmin) / rng for v in vals]

        c.setStrokeColor(LINE); c.setLineWidth(0.6)
        c.line(pad_l, pad_b, pad_l + gw, pad_b)
        # 면적
        p = c.beginPath()
        p.moveTo(xs[0], pad_b)
        for x, y in zip(xs, ys):
            p.lineTo(x, y)
        p.lineTo(xs[-1], pad_b); p.close()
        c.setFillColor(colors.HexColor("#E8EEF6"))
        c.drawPath(p, fill=1, stroke=0)
        # 이벤트 마커 (방 종료 시점 수직 점선)
        if self.mark:
            dates = [d for d, _ in s]
            md = str(self.mark[0])
            if md in dates:
                mi = dates.index(md)
                mx = xs[mi]
                c.setStrokeColor(CRIT); c.setLineWidth(0.9); c.setDash(2, 2)
                c.line(mx, pad_b, mx, pad_b + gh)
                c.setDash()
                c.setFont(FB, 6.8); c.setFillColor(CRIT)
                c.drawCentredString(mx, pad_b + gh + 3, f"↓ {self.mark[1]}")
        # 라인
        c.setStrokeColor(NAVY); c.setLineWidth(1.6)
        for i in range(n - 1):
            c.line(xs[i], ys[i], xs[i + 1], ys[i + 1])
        c.setFillColor(GOLD)
        c.circle(xs[-1], ys[-1], 2.6, fill=1, stroke=0)
        c.setFont(F, 7); c.setFillColor(INK_SOFT)
        c.drawString(pad_l, pad_b - 12, s[0][0])
        c.drawRightString(pad_l + gw, pad_b - 12, s[-1][0])
        c.setFont(FB, 7.5); c.setFillColor(NAVY)
        c.drawString(pad_l, ys[0] + 4, f"{vals[0]:,}")
        c.drawRightString(pad_l + gw, ys[-1] + 5, f"{vals[-1]:,}명")


def _section_header(num, title, styles, width):
    """번호 붙은 섹션 헤더 (골드 좌측 바 + 제목). 중첩 없이 배경색 셀 사용."""
    t = Table([["", Paragraph(f"{num}. {title}", styles["sec"])]],
              colWidths=[3*mm, width - 3*mm], rowHeights=[8*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), GOLD),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, 0), 0), ("RIGHTPADDING", (0, 0), (0, 0), 0),
        ("LEFTPADDING", (1, 0), (1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LINEBELOW", (0, 0), (-1, -1), 0.8, NAVY),
    ]))
    return t


def _fmt(n):
    try:
        return f"{int(round(n)):,}"
    except Exception:
        return str(n)


def _clean(s):
    """NaN/NaT/None 유래 문자열을 빈 값으로 정리."""
    s = "" if s is None else str(s).strip()
    return "" if s.lower() in ("nan", "nat", "none") else s


def generate_pdf_report(
    period_label, first_date, last_date,
    total_now, diff, pct, period_spend, conv_rate,
    insight_lines, perf_rows,
    spend_label="광고비 집행", spend_note="", conv_note="", compact=False,
    comparison_rows=None, funnel_rows=None, archived_rows=None,
    trend_series=None, change_breakdown=None, trend_mark=None,
    strategy_rows=None, product_master=None, customer_forecast=None,
    author="마케팅 총괄", report_to="경영진", org="황금후추",
) -> bytes:
    _register_fonts()
    styles = _styles()
    buf = io.BytesIO()
    today = str(_date.today())

    PW, PH = A4
    LM = RM = 17 * mm
    # compact = 대표 보고용 한 장 요약. 여백·섹션 간격·차트 높이를 줄여
    # 개요·KPI·추이·방별 표·인사이트가 A4 한 장에 들어가게 한다.
    TM = (20 if compact else 26) * mm
    BM = (12 if compact else 16) * mm
    _G = 8 if compact else 14        # 주요 섹션 사이 간격
    content_w = PW - LM - RM

    # ── 머리말/꼬리말 (전 페이지) ──
    def _decorate(canvas, doc):
        canvas.saveState()
        # 머리말
        canvas.setFont(FB, 8)
        canvas.setFillColor(INK_SOFT)
        canvas.drawString(LM, PH - 15 * mm, f"{org} · 채팅방 모객·전환 분석 보고서")
        canvas.setFont(F, 7.5)
        canvas.setFillColor(CRIT)
        canvas.drawRightString(PW - RM, PH - 15 * mm, "대외비 (CONFIDENTIAL)")
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.6)
        canvas.line(LM, PH - 17 * mm, PW - RM, PH - 17 * mm)
        # 꼬리말
        canvas.setStrokeColor(LINE)
        canvas.line(LM, BM + 4 * mm, PW - RM, BM + 4 * mm)
        canvas.setFont(F, 7.5)
        canvas.setFillColor(INK_SOFT)
        canvas.drawString(LM, BM, f"작성일 {today}")
        canvas.drawCentredString(PW / 2, BM, org)
        canvas.drawRightString(PW - RM, BM, f"- {doc.page} -")
        canvas.restoreState()

    frame = Frame(LM, BM + 7 * mm, content_w, PH - TM - BM - 7 * mm, id="main")
    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=LM, rightMargin=RM,
                          topMargin=TM, bottomMargin=BM, title="채팅방 모객·전환 분석 보고서")
    doc.addPageTemplates([PageTemplate(id="all", frames=[frame], onPage=_decorate)])

    S = []  # story

    # 섹션 번호는 고정값이 아니라 **실제로 그린 순서**로 매긴다.
    # 자료가 없어 한 섹션이 빠지면(요약본은 퍼널을 뺀다) 번호가 2→4로 튀어서
    # 받는 사람이 '빠진 장이 있나' 하고 의심하게 된다.
    _seq = [0]

    def _sn():
        _seq[0] += 1
        return _seq[0]

    # ── 표제부 ──
    S.append(Paragraph("채팅방 모객 · 전환 분석 보고서", styles["title"]))
    S.append(Spacer(1, 3))
    S.append(Paragraph(f"보고 기간 : {period_label} ({first_date} ~ {last_date})", styles["subtitle"]))
    S.append(Spacer(1, 8))

    # 문서 정보 + 결재란 (대기업 양식)
    iw = content_w * 0.64
    info = Table([
        [Paragraph("보고일자", styles["cell_h"]), Paragraph(today, styles["cell"]),
         Paragraph("작성자", styles["cell_h"]), Paragraph(author, styles["cell"])],
        [Paragraph("보고대상", styles["cell_h"]), Paragraph(report_to, styles["cell"]),
         Paragraph("문서등급", styles["cell_h"]), Paragraph("대외비", styles["cell"])],
    ], colWidths=[iw*0.20, iw*0.30, iw*0.20, iw*0.30])
    info.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), NAVY), ("BACKGROUND", (2, 0), (2, -1), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.6, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), (3 if compact else 5)),
        ("BOTTOMPADDING", (0, 0), (-1, -1), (3 if compact else 5)),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
    ]))

    aw = content_w * 0.30
    # 요약본은 결재란 서명 칸을 낮춘다(칸은 남긴다 — 보고서 양식이라 필요하다).
    approval = Table(
        [[Paragraph("담당", styles["cell_h"]), Paragraph("팀장", styles["cell_h"]), Paragraph("임원", styles["cell_h"])],
         ["", "", ""]],
        colWidths=[aw/3]*3,
        rowHeights=[(6 if compact else 7)*mm, (10 if compact else 15)*mm])
    approval.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.6, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    head = Table([[info, approval]], colWidths=[content_w*0.66, content_w*0.34])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                              ("LEFTPADDING", (0, 0), (0, 0), 0),
                              ("LEFTPADDING", (1, 0), (1, 0), 10),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    S.append(head)
    S.append(Spacer(1, _G))

    # ── 1. 보고 개요 ──
    sign = "+" if diff >= 0 else ""
    trend = "증가" if diff > 0 else ("감소" if diff < 0 else "유지")
    summary = (
        f"보고 기간 종료일({last_date}) 기준 운영 채팅방 총원은 <b>{_fmt(total_now)}명</b>으로, "
        f"기간 시작 대비 <b>{sign}{_fmt(diff)}명({sign}{pct:.1f}%) {trend}</b>하였습니다. "
    )
    if change_breakdown and change_breakdown.get("archived_removed", 0) < 0:
        bd = change_breakdown
        summary += (
            f"<br/><br/>다만 이 감소분의 대부분(<b>{_fmt(bd['archived_removed'])}명</b>)은 "
            f"강의를 마친 <b>{bd['archived_count']}개 채팅방의 정상 종료</b>로 총원에서 제외된 "
            f"구조적 변동이며, 계속 운영 중인 채팅방은 <b>{bd['active_change']:+,}명"
            f"({bd['active_pct']:+.1f}%)</b>으로 안정적입니다. 헤드라인 감소율을 운영 부진으로 "
            f"해석하지 않도록 유의가 필요합니다."
        )
    if funnel_rows:
        tot_e = sum(int(r.get("enrolled", 0)) for r in funnel_rows)
        tot_p = sum(int(r.get("webinar_peak", 0)) for r in funnel_rows)
        tot_r = sum(int(r.get("revenue", 0)) for r in funnel_rows)
        avg_c = (tot_e / tot_p * 100) if tot_p else 0
        summary += (
            f"<br/><br/>분석 대상 {len(funnel_rows)}개 기수의 무료 웨비나 누적 최고인원 {_fmt(tot_p)}명은 "
            f"유료 등록 <b>{_fmt(tot_e)}명</b>으로 이어져 평균 전환율 <b>{avg_c:.1f}%</b>, "
            f"등록 매출 <b>{_fmt(tot_r)}원</b>을 기록하였습니다."
        )
    S.append(_section_header(_sn(), "보고 개요", styles, content_w))
    S.append(Spacer(1, 6))
    box = Table([[Paragraph(summary, styles["body"])]], colWidths=[content_w])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BG_SOFT),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LINEBEFORE", (0, 0), (0, -1), 3, GOLD),
    ]))
    S.append(box)
    S.append(Spacer(1, _G))

    # ── 2. 주요 성과 지표 ──
    S.append(_section_header(_sn(), "주요 성과 지표", styles, content_w))
    S.append(Spacer(1, 6))

    def _kpi_cell(label, value, delta="", dcolor=INK_SOFT):
        inner = [[Paragraph(label, styles["kpi_k"])],
                 [Paragraph(value, styles["kpi_v"])]]
        if delta:
            ds = ParagraphStyle("dx", parent=styles["kpi_d"], textColor=dcolor)
            inner.append([Paragraph(delta, ds)])
        t = Table(inner, colWidths=[(content_w - 3*8) / 4])
        t.setStyle(TableStyle([
            ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        return t

    dcol = GOOD if diff > 0 else (CRIT if diff < 0 else INK_SOFT)
    k_cells = [
        _kpi_cell("현재 총 인원", f"{_fmt(total_now)}명", f"{sign}{_fmt(diff)}명 ({sign}{pct:.1f}%)", dcol),
        _kpi_cell("기간 순증감", f"{sign}{_fmt(diff)}명", f"{first_date}~{last_date}", INK_SOFT),
        # 방별 광고비가 비어 있으면 화면과 똑같이 '전사 광고비(기간 안분)'로
        # 라벨을 바꿔 넣는다. 출처가 다른 값을 같은 이름으로 적으면 안 되지만,
        # 빈칸으로 두면 '광고를 안 썼다'로 읽히는 것도 사실이 아니다.
        _kpi_cell(spend_label, (f"{_fmt(period_spend)}원" if period_spend else "-"),
                  spend_note, INK_SOFT),
        _kpi_cell("수강 전환율", (f"{conv_rate}%" if conv_rate else "-"),
                  (conv_note or ("강의 신청 기준" if conv_rate else "")), INK_SOFT),
    ]
    kpi = Table([k_cells], colWidths=[(content_w) / 4] * 4)
    kpi.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.6, LINE),
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    S.append(kpi)

    # 기간 비교
    if comparison_rows:
        S.append(Spacer(1, 8))
        head_c = [Paragraph(h, styles["cell_h"]) for h in ["구분", "증감", "증감률", "기준일"]]
        rowsc = [head_c]
        for cr in comparison_rows:
            d = cr.get("diff", 0); p = cr.get("pct", 0.0)
            s = "+" if d >= 0 else ""
            col = GOOD if d > 0 else (CRIT if d < 0 else INK_SOFT)
            rowsc.append([
                Paragraph(cr.get("label", ""), styles["cell"]),
                Paragraph(f'<font color="#{col.hexval()[2:]}">{s}{_fmt(d)}명</font>', styles["cell_r"]),
                Paragraph(f'<font color="#{col.hexval()[2:]}">{s}{p:.1f}%</font>', styles["cell_r"]),
                Paragraph(str(cr.get("ref_date", "")), styles["cell_r"]),
            ])
        tc = Table(rowsc, colWidths=[content_w*0.34, content_w*0.22, content_w*0.22, content_w*0.22])
        tc.setStyle(_table_style())
        S.append(tc)

    # 기간 총원 추이 (라인 차트 + 방 종료 마커)
    if trend_series and len(trend_series) >= 2:
        S.append(Spacer(1, 10))
        S.append(Paragraph("기간 총원 추이", styles["h3"]))
        S.append(Spacer(1, 3))
        S.append(TrendLine(trend_series, content_w,
                           height=(46 if compact else 88), mark=trend_mark))
    S.append(Spacer(1, _G))

    # ── 2-1. 총원 변동 원인 분석 (감소 사유 명시) ──
    if change_breakdown and change_breakdown.get("archived_removed", 0) < 0:
        bd = change_breakdown
        blk = [_section_header(f"{_seq[0]}-1", "총원 변동 원인 분석", styles, content_w), Spacer(1, 5),
               Paragraph("헤드라인 총원 변동을 ‘운영 중 방의 자연 증감’과 ‘강의 완료에 따른 방 종료(구조적)’로 "
                         "분해하여, 실제 운영 상태를 정확히 판단할 수 있도록 하였습니다.", styles["body_s"]),
               Spacer(1, 7)]
        # 분해 표 (워터폴 형식)
        s_style = ParagraphStyle("wf", fontName=FB, fontSize=9, leading=13, textColor=INK)
        rows_wf = [
            [Paragraph("구분", styles["cell_h"]), Paragraph("증감", styles["cell_h"]), Paragraph("비고", styles["cell_h"])],
            [Paragraph("기간 시작 총원", styles["cell"]), Paragraph(f"{_fmt(bd['start_total'])}명", styles["cell_r"]),
             Paragraph("종료 방 포함 기준", styles["cell"])],
            [Paragraph("① 운영 중 방 자연 증감", styles["cell"]),
             Paragraph(f'<font color="#{(GOOD if bd["active_change"]>=0 else CRIT).hexval()[2:]}">{bd["active_change"]:+,}명 ({bd["active_pct"]:+.1f}%)</font>', styles["cell_r"]),
             Paragraph("계속 운영 중 — 안정적", styles["cell"])],
            [Paragraph("② 강의 완료 방 종료(구조적)", styles["cell"]),
             Paragraph(f'<font color="#{CRIT.hexval()[2:]}">{bd["archived_removed"]:+,}명</font>', styles["cell_r"]),
             Paragraph(f"{bd['archived_count']}개 방 정상 종료", styles["cell"])],
            [Paragraph("기간 종료 총원", styles["cell_b"]), Paragraph(f"{_fmt(bd['end_total'])}명", styles["cell_r"]),
             Paragraph("현재 운영 방 기준", styles["cell"])],
        ]
        twf = Table(rows_wf, colWidths=[content_w*0.40, content_w*0.30, content_w*0.30])
        twf.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("GRID", (0, 0), (-1, -1), 0.5, LINE),
            ("BACKGROUND", (0, 4), (-1, 4), colors.HexColor("#EEF2F7")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("LINEABOVE", (0, 4), (-1, 4), 1.0, NAVY),
        ]))
        blk.append(twf)
        # 종료 방 상세
        if bd["archived_detail"]:
            blk.append(Spacer(1, 6))
            det = "종료 채팅방 : " + " · ".join(
                f"{d['room']}({_fmt(d['final'])}명, {d['date']})" for d in bd["archived_detail"])
            blk.append(Paragraph(det, styles["body_s"]))
        # 시사점
        blk.append(Spacer(1, 5))
        note = ParagraphStyle("note", fontName=FB, fontSize=8.7, leading=13, textColor=NAVY_D)
        blk.append(Paragraph(
            "▪ 시사점 : 총원 감소의 대부분은 강의 사이클 완료에 따른 계획된 방 종료이며, "
            "이는 오픈채팅 운영의 정상적 수명주기입니다. 다음 기수 모객 시에는 종료 방의 전환 "
            "성과를 참고하여 전환율 높은 상품군을 우선 편성하는 전략이 유효합니다.", note))
        blk.append(Spacer(1, _G))
        S.append(KeepTogether(blk))

    # ── 3. 모객 → 유료 전환 분석 ──
    if funnel_rows:
        block = [_section_header(_sn(), "모객 → 유료 전환 분석", styles, content_w), Spacer(1, 4),
                 Paragraph("무료 웨비나 방 인원이 실제 유료 등록으로 이어진 비율입니다. (입문 강의 기준)", styles["body_s"]),
                 Spacer(1, 6), ConversionBars(funnel_rows, content_w), Spacer(1, 8)]
        # 표
        hf = [Paragraph(h, styles["cell_h"]) for h in ["상품·기수", "웨비나 최고인원", "유료 등록", "전환율", "등록 매출"]]
        rf = [hf]
        for r in sorted(funnel_rows, key=lambda x: x.get("conversion") or 0, reverse=True):
            conv = r.get("conversion")
            rf.append([
                Paragraph(str(r.get("label", "")), styles["cell"]),
                Paragraph(f"{_fmt(r.get('webinar_peak',0))}명", styles["cell_r"]),
                Paragraph(f"{_fmt(r.get('enrolled',0))}명", styles["cell_r"]),
                Paragraph(f'<font color="#1E7A3D"><b>{conv:.1f}%</b></font>' if conv is not None else "-", styles["cell_r"]),
                Paragraph(f"{_fmt(r.get('revenue',0))}원" if r.get("revenue") else "-", styles["cell_r"]),
            ])
        tf = Table(rf, colWidths=[content_w*0.26, content_w*0.20, content_w*0.16, content_w*0.14, content_w*0.24])
        tf.setStyle(_table_style())
        block.append(tf)
        block.append(Spacer(1, _G))
        S.append(KeepTogether(block))

    # ── 채팅방별 운영 현황 ──
    # 요약본에서는 인사이트를 **먼저** 놓는다. 방을 하나도 빼지 않고 다 적으면
    # (방이 11~16개다) 표가 한 장을 넘기는데, 그때 결론이 뒤로 밀리면 첫 장만
    # 보는 사람이 아무것도 못 얻는다. 요약이 앞, 상세가 뒤가 맞다.
    _perf_block = []
    if perf_rows:
        _perf_block.append(Spacer(1, 6))
        # 요약본은 방을 하나도 빼지 않고 다 적는다 — 대표 보고의 핵심이
        # '어느 방이 얼마나 늘고 줄었나'라서, 묶어 버리면 볼 이유가 없어진다.
        # 대신 글자·줄간격을 줄여 한 장 안에 밀어 넣는다.
        if compact:
            _c  = ParagraphStyle("cell_c", parent=styles["cell"], fontSize=7.8, leading=9.6)
            _cr = ParagraphStyle("cell_rc", parent=styles["cell_r"], fontSize=7.8, leading=9.6)
            _ch = ParagraphStyle("cell_hc", parent=styles["cell_h"], fontSize=7.8, leading=9.6)
        else:
            _c, _cr, _ch = styles["cell"], styles["cell_r"], styles["cell_h"]
        hp = [Paragraph(h, _ch) for h in ["채팅방", "현재 인원", "기간 증감", "증감률", "추세"]]
        rp = [hp]
        for r in perf_rows:
            chg = r.get("_change", 0)
            col = GOOD if chg > 0 else (CRIT if chg < 0 else INK_SOFT)
            rp.append([
                Paragraph(str(r.get("채팅방", "")), _c),
                Paragraph(str(r.get("현재 인원", "")), _cr),
                Paragraph(f'<font color="#{col.hexval()[2:]}">{r.get("증감","")}</font>', _cr),
                Paragraph(f'<font color="#{col.hexval()[2:]}">{r.get("증감률","")}</font>', _cr),
                Paragraph(r.get("평가", ""), _cr),
            ])
        tp = Table(rp, colWidths=[content_w*0.36, content_w*0.18, content_w*0.18, content_w*0.16, content_w*0.12])
        tp.setStyle(_table_style(compact))
        _perf_block.append(tp)
        _perf_block.append(Spacer(1, _G))

    # ── 종합 인사이트 및 시사점 ──
    _insight_block = []
    if insight_lines:
        block = [Spacer(1, 6)]
        for ln in insight_lines:
            txt = ln
            # **볼드** → <b>
            parts = txt.split("**")
            txt = "".join(p if i % 2 == 0 else f"<b>{p}</b>" for i, p in enumerate(parts))
            block.append(Paragraph(f"• {txt}", styles["bullet"]))
            block.append(Spacer(1, 3))
        _insight_block = [KeepTogether(block), Spacer(1, 8)]

    # 요약본: 인사이트 → 방별 표.  전체본: 방별 표 → 인사이트(기존 순서).
    # 번호는 **붙이는 시점**에 매긴다 — 순서가 바뀌어도 1,2,3…으로 이어진다.
    _ordered = ([("종합 인사이트 및 시사점", _insight_block),
                 ("채팅방별 운영 현황", _perf_block)] if compact else
                [("채팅방별 운영 현황", _perf_block),
                 ("종합 인사이트 및 시사점", _insight_block)])
    for _title, _blk in _ordered:
        if not _blk:
            continue
        S.append(_section_header(_sn(), _title, styles, content_w))
        for _f in _blk:
            S.append(_f)

    # ── 강의 사업 종합 전략 요약 ──
    if strategy_rows or product_master:
        block = [_section_header(_sn(), "강의 사업 종합 전략 요약", styles, content_w), Spacer(1, 6)]
        if strategy_rows:
            for _title, _body in strategy_rows:
                _b = _body
                parts = _b.split("**")
                _b = "".join(p if i % 2 == 0 else f"<b>{p}</b>" for i, p in enumerate(parts))
                block.append(Paragraph(f"• <b>{_clean(_title)}</b> — {_b}", styles["bullet"]))
                block.append(Spacer(1, 3))
        if product_master:
            block.append(Spacer(1, 5))
            block.append(Paragraph("상품군 통합 요약 (매출·전환·객단가·광고 효율)", styles["h3"]))
            block.append(Spacer(1, 4))
            hh = [Paragraph(h, styles["cell_h"]) for h in
                  ["상품군", "누적매출", "수강생", "전환율", "객단가", "광고비", "광고ROAS"]]
            rr = [hh]
            for r in product_master:
                rr.append([
                    Paragraph(str(r.get("product", "")), styles["cell_b"]),
                    Paragraph(f"{r.get('revenue',0)/1e8:,.2f}억", styles["cell_r"]),
                    Paragraph(f"{_fmt(r.get('students', r.get('paid',0)))}명", styles["cell_r"]),
                    Paragraph(f"{r.get('전환율',0):.1f}%", styles["cell_r"]),
                    Paragraph(f"{r.get('객단가',0)/1e4:,.0f}만", styles["cell_r"]),
                    Paragraph(f"{r.get('ad',0)/1e8:,.2f}억" if r.get('ad',0) else "—", styles["cell_r"]),
                    Paragraph(f"{r.get('광고ROAS',0):.1f}배" if r.get('광고ROAS',0) else "—", styles["cell_r"]),
                ])
            tm = Table(rr, colWidths=[content_w*0.16, content_w*0.16, content_w*0.12,
                                      content_w*0.12, content_w*0.14, content_w*0.15, content_w*0.15])
            tm.setStyle(_table_style())
            block.append(tm)
        # 고객·전망 지표
        if customer_forecast:
            cf = customer_forecast
            block.append(Spacer(1, 6))
            block.append(Paragraph("고객 자산 · 다음 기간 전망", styles["h3"]))
            block.append(Spacer(1, 4))
            _cells = [
                [Paragraph("재구매율", styles["cell_h"]),
                 Paragraph(f"{cf.get('repeat_rate',0):.1f}%", styles["cell"]),
                 Paragraph("재구매 매출 비중", styles["cell_h"]),
                 Paragraph(f"{cf.get('repeat_rev_share',0):.0f}%", styles["cell"])],
                [Paragraph("평균 LTV", styles["cell_h"]),
                 Paragraph(f"{cf.get('avg_ltv',0)/1e4:,.0f}만원", styles["cell"]),
                 Paragraph("교차판매율", styles["cell_h"]),
                 Paragraph(f"{cf.get('cross_sell',0):.0f}%", styles["cell"])],
                [Paragraph("매출 런레이트", styles["cell_h"]),
                 Paragraph(f"{cf.get('runrate_month',0)/1e8:,.2f}억/월", styles["cell"]),
                 Paragraph("연 환산 페이스", styles["cell_h"]),
                 Paragraph(f"{cf.get('runrate_year',0)/1e8:,.0f}억/년", styles["cell"])],
            ]
            tcf = Table(_cells, colWidths=[content_w*0.2, content_w*0.3,
                                           content_w*0.2, content_w*0.3])
            tcf.setStyle(_table_style())
            block.append(tcf)
            block.append(Spacer(1, 3))
            block.append(Paragraph(
                "※ 전망은 개강 시점에 매출이 몰리는 특성상 최근 3개월 평균(런레이트) 기준 참고치입니다.",
                styles["body_s"]))
        S.append(KeepTogether(block))
        S.append(Spacer(1, 8))

    # ── 부록: 운영 종료 채팅방 ──
    if archived_rows:
        S.append(_section_header(_sn(), "[부록] 운영 종료 채팅방 현황", styles, content_w))
        S.append(Spacer(1, 6))
        ha = [Paragraph(h, styles["cell_h"]) for h in ["채팅방", "종료일", "최종 인원", "최고 인원", "순증감", "운영기간"]]
        ra = [ha]
        for r in archived_rows:
            net = r.get("순증감", 0)
            col = GOOD if net > 0 else (CRIT if net < 0 else INK_SOFT)
            _close = _clean(r.get("실제 종료일", "")) or _clean(r.get("처리일", ""))
            ra.append([
                Paragraph(str(r.get("채팅방", "")), styles["cell"]),
                Paragraph(_close, styles["cell_r"]),
                Paragraph(f"{_fmt(r.get('최종 인원',0))}명", styles["cell_r"]),
                Paragraph(f"{_fmt(r.get('최고 인원',0))}명", styles["cell_r"]),
                Paragraph(f'<font color="#{col.hexval()[2:]}">{net:+,}명</font>', styles["cell_r"]),
                Paragraph(f"{_fmt(r.get('운영 기간',0))}일", styles["cell_r"]),
            ])
        ta = Table(ra, colWidths=[content_w*0.26, content_w*0.16, content_w*0.15, content_w*0.15, content_w*0.14, content_w*0.14])
        ta.setStyle(_table_style())
        S.append(ta)

    # 끝에 남은 여백이 페이지를 하나 더 만들어 '머리말만 있는 빈 장'이 붙는다.
    # 대표에게 나가는 문서라 빈 장은 그 자체로 흠이다 — 꼬리 여백을 떼고 만든다.
    while S and isinstance(S[-1], Spacer):
        S.pop()

    doc.build(S)
    return buf.getvalue()


def _table_style(compact=False):
    """compact면 행 여백을 줄인다 — 방이 11개면 위아래 5pt씩만으로도 120pt를
    먹어서, 한 장 요약본의 인사이트가 다음 장으로 밀린다."""
    _p = 2 if compact else 5
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, BG_SOFT]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), _p), ("BOTTOMPADDING", (0, 0), (-1, -1), _p),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ])


# ══════════════ 월간 마케팅 리포트 (대표 보고용 1장) ══════════════
def generate_monthly_report(month_label, kpis, experiments, learnings,
                            next_actions, notes=None):
    """마케터가 매달 대표에게 내는 성과 리포트 1장.

    month_label : "2026년 8월" 등
    kpis        : [(지표, 이번달, 전월, 증감문구)] — 문자열로 준비해 전달
    experiments : [{'product','hook','budget','leads','cpl','conv','verdict'}]
    learnings   : [str]  이번 달 배운 점
    next_actions: [(제목, 근거, 실행)] 다음 달 계획
    notes       : [str]  참고/한계 (선택)
    """
    _register_fonts()
    styles = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=16*mm, rightMargin=16*mm, topMargin=14*mm, bottomMargin=14*mm,
        title=f"{month_label} 마케팅 리포트")
    W = doc.width
    st = []

    # 표지 머리
    st.append(Paragraph(f"{month_label} 마케팅 성과 리포트", styles["title"]))
    st.append(Paragraph(f"황금후추 강의 마케팅 · 작성일 {_date.today()}", styles["subtitle"]))
    st.append(Spacer(1, 7*mm))

    # 1. 주요 지표
    st.append(_section_header(1, "이번 달 주요 지표", styles, W))
    st.append(Spacer(1, 3*mm))
    if kpis:
        rows = [[Paragraph("지표", styles["cell_h"]),
                 Paragraph("이번 달", styles["cell_h"]),
                 Paragraph("전월", styles["cell_h"]),
                 Paragraph("증감", styles["cell_h"])]]
        for k, cur, prev, delta in kpis:
            rows.append([Paragraph(_clean(k), styles["cell_b"]),
                         Paragraph(_clean(cur), styles["cell_r"]),
                         Paragraph(_clean(prev), styles["cell_r"]),
                         Paragraph(_clean(delta), styles["cell_r"])])
        t = Table(rows, colWidths=[W*0.34, W*0.22, W*0.22, W*0.22])
        t.setStyle(_table_style())
        st.append(t)
    else:
        st.append(Paragraph("데이터가 없습니다.", styles["body_s"]))
    st.append(Spacer(1, 6*mm))

    # 2. 실험 결과
    st.append(_section_header(2, "이번 달 실행한 실험", styles, W))
    st.append(Spacer(1, 3*mm))
    if experiments:
        rows = [[Paragraph(h, styles["cell_h"]) for h in
                 ("강의", "소재·후킹", "예산", "리드", "리드단가", "전환", "판정")]]
        for e in experiments:
            rows.append([
                Paragraph(_clean(e.get("product")), styles["cell"]),
                Paragraph(_clean(e.get("hook")), styles["cell"]),
                Paragraph(f"{_fmt(e.get('budget', 0)/1e4)}만", styles["cell_r"]),
                Paragraph(f"{_fmt(e.get('leads', 0))}", styles["cell_r"]),
                Paragraph(f"{_fmt(e.get('cpl', 0))}원", styles["cell_r"]),
                Paragraph(f"{_fmt(e.get('conv', 0))}건", styles["cell_r"]),
                Paragraph(_clean(e.get("verdict")), styles["cell_b"]),
            ])
        t = Table(rows, colWidths=[W*0.11, W*0.28, W*0.12, W*0.11, W*0.14, W*0.11, W*0.13])
        t.setStyle(_table_style())
        st.append(t)
    else:
        st.append(Paragraph(
            "이번 달 기록된 실험이 없습니다. 실험 일지에 등록하면 이 자리에 "
            "자동으로 정리됩니다.", styles["body_s"]))
    st.append(Spacer(1, 6*mm))

    # 3. 배운 점
    st.append(_section_header(3, "배운 점", styles, W))
    st.append(Spacer(1, 3*mm))
    if learnings:
        for i, l in enumerate(learnings, 1):
            st.append(Paragraph(f"{i}. {_clean(l)}", styles["bullet"]))
            st.append(Spacer(1, 1.5*mm))
    else:
        st.append(Paragraph("아직 회고가 기록되지 않았습니다.", styles["body_s"]))
    st.append(Spacer(1, 6*mm))

    # 4. 다음 달 계획
    st.append(_section_header(4, "다음 달 실행 계획", styles, W))
    st.append(Spacer(1, 3*mm))
    if next_actions:
        for i, (title, why, how) in enumerate(next_actions, 1):
            st.append(Paragraph(f"{i}. {_clean(title)}", styles["h3"]))
            if why:
                st.append(Paragraph(f"근거 — {_clean(why)}", styles["body"]))
            if how:
                st.append(Paragraph(f"실행 — {_clean(how)}", styles["body"]))
            st.append(Spacer(1, 3*mm))
    else:
        st.append(Paragraph("계획이 아직 없습니다.", styles["body_s"]))

    if notes:
        st.append(Spacer(1, 4*mm))
        for n in notes:
            st.append(Paragraph(f"※ {_clean(n)}", styles["body_s"]))

    doc.build(st)
    buf.seek(0)
    return buf.getvalue()
