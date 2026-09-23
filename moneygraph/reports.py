"""Portable PDF summaries and individual account reports from analysis only."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import threading
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import CondPageBreak, HRFlowable, LongTable, Paragraph, SimpleDocTemplate, TableStyle

from .assistant import FEATURE_LABELS, FLAG_LABELS, LIMIT_NOTE, ROLE_LABELS, get_node, identifier, node_index, number, text_data

FONT_PATH = Path(__file__).resolve().parent / "assets" / "fonts" / "DejaVuSans.ttf"
FONT_NAME = "AqshaDejaVu"
_FONT_LOCK = threading.Lock()
INK = colors.HexColor("#19392e")
MUTED = colors.HexColor("#526a60")
LINE = colors.HexColor("#d6e3db")
PALE = colors.HexColor("#f0f5f1")
PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 44
CONTENT_WIDTH = PAGE_WIDTH - MARGIN * 2


def _register_font() -> None:
    with _FONT_LOCK:
        if FONT_NAME not in pdfmetrics.getRegisteredFontNames():
            if not FONT_PATH.is_file():
                raise ValueError("Bundled PDF font missing: moneygraph/assets/fonts/DejaVuSans.ttf")
            pdfmetrics.registerFont(TTFont(FONT_NAME, str(FONT_PATH)))
            pdfmetrics.registerFontFamily(FONT_NAME, normal=FONT_NAME, bold=FONT_NAME, italic=FONT_NAME, boldItalic=FONT_NAME)


def _styles() -> dict:
    base = dict(fontName=FONT_NAME, textColor=INK, alignment=TA_LEFT, splitLongWords=True)
    return {
        "title": ParagraphStyle("AqshaTitle", fontSize=23, leading=29, spaceAfter=13, **base),
        "subtitle": ParagraphStyle("AqshaSubtitle", fontSize=11, leading=16, spaceAfter=13, **base),
        "body": ParagraphStyle("AqshaBody", fontSize=9, leading=14, spaceAfter=7, **base),
        "small": ParagraphStyle("AqshaSmall", fontSize=7.7, leading=11.3, spaceAfter=4, **base),
        "section": ParagraphStyle("AqshaSection", fontSize=13, leading=18, spaceBefore=15, spaceAfter=9, **base),
        "item": ParagraphStyle("AqshaItem", fontSize=10, leading=14, spaceBefore=7, spaceAfter=4, keepWithNext=True, **base),
        "table": ParagraphStyle("AqshaCell", fontSize=8, leading=11.5, spaceAfter=0, **base),
        "table_header": ParagraphStyle("AqshaTableHeader", fontName=FONT_NAME, fontSize=7.8, leading=11, textColor=colors.white),
    }


def _safe_text(value, limit: int = 12000) -> str:
    value = text_data(value, limit)
    # ReportLab paragraph markup is authored here only; source text is escaped.
    value = value.translate({ord(char): "-" for char in "\u2010\u2011\u2012\u2013\u2014\u2212"})
    return escape(value)


def _paragraph(value, styles, kind="body") -> Paragraph:
    return Paragraph(_safe_text(value), styles[kind])


def _table(headers: list[str], rows: list[list], widths: list[float], styles: dict) -> LongTable:
    cells = [[_paragraph(header, styles, "table_header") for header in headers]]
    cells.extend([_paragraph(value, styles, "table") for value in row] for row in rows)
    table = LongTable(cells, colWidths=widths, repeatRows=1, hAlign="LEFT", splitByRow=1, splitInRow=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, INK),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, LINE),
    ]))
    return table


def _page_decoration(canvas: Canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont(FONT_NAME, 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN, PAGE_HEIGHT - 29, "AQSHA TRACE / ЗЕРТТЕУ ЕСЕБІ")
    canvas.setStrokeColor(LINE)
    canvas.line(MARGIN, PAGE_HEIGHT - 36, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 36)
    canvas.line(MARGIN, 37, PAGE_WIDTH - MARGIN, 37)
    canvas.setFont(FONT_NAME, 7)
    canvas.drawString(MARGIN, 24, "Жергілікті талдау. Рөлдер - тексерілетін гипотезалар.")
    canvas.drawRightString(PAGE_WIDTH - MARGIN, 24, f"Бет {doc.page}")
    canvas.restoreState()


def build_report(analysis: dict, gid=None) -> bytes:
    """Create an in-memory PDF with an embedded, redistributable Unicode font.

    ``gid=None`` produces an overall summary; a supplied exact int64 ID produces
    an individual account card. Unknown IDs raise ValueError. No input data is
    changed and no filesystem output is written by this function.
    """
    nodes = node_index(analysis)
    selected = get_node(analysis, gid) if gid is not None else None
    _register_font()
    styles = _styles()
    output = BytesIO()
    meta = analysis.get("meta") or {}
    source_mode = "СИНТЕТИКАЛЫҚ ДЕМО" if meta.get("demo") else "ЖҮКТЕЛГЕН ДЕРЕКТЕР"
    cited: set[str] = set()
    story = []

    def p(value, kind="body"):
        story.append(_paragraph(value, styles, kind))

    def section(value):
        story.append(CondPageBreak(85))
        p(value, "section")

    def cite(value) -> str:
        key = identifier(value)
        if key in nodes:
            cited.add(key)
        return "GID " + key

    p("Шоттың зерттеу карточкасы" if selected else "Қаржы желісін талдау", "title")
    if selected:
        p(cite(selected["gid"]), "subtitle")
    p(source_mode + " | " + str(meta.get("period_start") or "Кезең белгісіз") + " - " + str(meta.get("period_end") or ""), "small")
    p("Дерек көзі: analysis.json. Талдау жасалған уақыт: " + str(meta.get("generated_at") or "берілмеген"), "small")
    p(LIMIT_NOTE, "body")
    story.append(HRFlowable(width="100%", thickness=1, color=LINE, spaceBefore=5, spaceAfter=8))

    if selected:
        role = ROLE_LABELS.get(selected.get("role"), selected.get("role", "Берілмеген"))
        section("01 / Рөл және тексеру басымдығы")
        p(role, "subtitle")
        rows = [
            ["Тексеру басымдығы", number(float(selected.get("priority_score") or 0) * 100, 1) + " / 100"],
            ["Рөл белгісінің күші", number(float(selected.get("role_score") or 0) * 100, 1) + " / 100"],
            ["Қадам / бастапқы шот", str(selected.get("depth", "?")) + (" / Иә" if selected.get("is_seed") else " / Жоқ")],
            ["Қауымдастық", str(selected.get("cluster_id", "?"))],
            ["Бақыланған кіріс", number(selected.get("in_kzt"), 2) + " KZT"],
            ["Бақыланған шығыс", number(selected.get("out_kzt"), 2) + " KZT"],
            ["Кіріс / шығыс контрагенттері", number(selected.get("in_degree")) + " / " + number(selected.get("out_degree"))],
            ["Кіріс / шығыс аударымдары", number(selected.get("in_tx")) + " / " + number(selected.get("out_tx"))],
            ["Шығыс / кіріс қатынасы", number(selected.get("pass_through"), 3) if selected.get("pass_through") is not None else "Толық емес: пайдаланылмайды"],
            ["Жоларалық орталықтық", number(selected.get("betweenness"), 6)],
            ["Салмақталған PageRank", number(selected.get("pagerank"), 6)],
        ]
        story.append(_table(["Көрсеткіш", "Бақыланған мән"], rows, [CONTENT_WIDTH * .53, CONTENT_WIDTH * .47], styles))
        p("Сақталған негіздеме: " + text_data(selected.get("evidence")), "body")
        contributions = sorted((selected.get("priority_contributions") or {}).items(), key=lambda pair: (-float(pair[1]), pair[0]))
        if contributions:
            p("Ұпайдың құрамдас үлестері", "item")
            story.append(_table(["Белгі", "100 ұпай шкаласына үлесі"],
                                [[FEATURE_LABELS.get(name, name), "+" + number(float(value) * 100, 2)] for name, value in contributions],
                                [CONTENT_WIDTH * .67, CONTENT_WIDTH * .33], styles))
        section("02 / Уақыттық белгілер және бақылау шегі")
        temporal = selected.get("temporal") or {}
        p("Белсенді күндер: " + number(temporal.get("active_days")) + "; бір күндегі ең көп төлеуші: "
          + number(temporal.get("synchronized_payers")) + "; сол/келесі күндегі ағын сәйкестігі: "
          + number(temporal.get("fast_forward_ratio"), 3) + ".")
        p("Бұл күндік сәйкестік. Бір күн ішіндегі операция реті мен дәл сол қаражаттың қайта жіберілгені дәлелденбейді.")
        flags = selected.get("flags") or []
        p("Белгілер: " + ("; ".join(FLAG_LABELS.get(flag, flag) for flag in flags) if flags else "арнайы белгі тіркелмеген"))
        p("Келесі дерек сұрауы: " + (text_data(selected.get("next_request")) or "Сұрау жазылмаған."))
        relevant_edges = [edge for edge in analysis.get("edges", [])
                          if identifier(selected["gid"]) in {identifier(edge["src"]), identifier(edge["dst"])}]
        relevant_edges.sort(key=lambda edge: (-float(edge.get("sum_kzt") or 0), int(identifier(edge["src"])), int(identifier(edge["dst"]))))
        if relevant_edges:
            p(f"Ірі бақыланған байланыстар: {min(8, len(relevant_edges))} / {len(relevant_edges)}", "item")
            story.append(_table(["Төлеуші GID", "Алушы GID", "Сома, KZT", "Саны"],
                                [[cite(edge["src"]), cite(edge["dst"]), number(edge.get("sum_kzt"), 2), number(edge.get("n_tx"))]
                                 for edge in relevant_edges[:8]],
                                [CONTENT_WIDTH * .29, CONTENT_WIDTH * .29, CONTENT_WIDTH * .28, CONTENT_WIDTH * .14], styles))
    else:
        section("01 / Дерек көлемі және қамту")
        stats = [["Шоттар", number(meta.get("n_nodes")), "Бастапқы шоттар", number(meta.get("n_seeds"))],
                 ["Бағытталған байланыстар", number(meta.get("n_edges")), "Транзакциялар", number(meta.get("n_transactions"))],
                 ["Қауымдастықтар", number(meta.get("n_clusters")), "Әлсіз компоненттер", number((analysis.get("quality") or {}).get("weak_components"))]]
        story.append(_table(["Көрсеткіш", "Саны", "Көрсеткіш", "Саны"], stats,
                            [CONTENT_WIDTH * .34, CONTENT_WIDTH * .16, CONTENT_WIDTH * .34, CONTENT_WIDTH * .16], styles))
        p("Жиынтық бақыланған ағын: " + number(meta.get("total_kzt"), 2) + " KZT. Бұл шот қалдығы немесе залал сомасы емес.")
        role_counts = analysis.get("role_counts") or {}
        p("Рөлдер: " + "; ".join(ROLE_LABELS.get(role, role) + " - " + number(count) for role, count in role_counts.items()))
        section("02 / Бірінші кезекте тексерілетін шоттар")
        ranked = sorted(nodes.values(), key=lambda node: (-float(node.get("priority_score") or 0), int(identifier(node["gid"]))))[:20]
        if ranked:
            story.append(_table(["№", "GID", "Рөл", "Ұпай", "Негіздеме"],
                                [[str(position), cite(node["gid"]), ROLE_LABELS.get(node.get("role"), node.get("role")),
                                  number(float(node.get("priority_score") or 0) * 100, 1), text_data(node.get("evidence"), 700)]
                                 for position, node in enumerate(ranked, 1)],
                                [32, 112, 96, 40, CONTENT_WIDTH - 280], styles))
        else:
            p("Талдауда шоттар жоқ.")
        section("03 / Қауымдастықтар және дерек шектері")
        clusters = sorted(analysis.get("clusters") or [], key=lambda cluster: (-float(cluster.get("sum_kzt_internal") or 0), cluster.get("cluster_id", 0)))
        for cluster in clusters[:6]:
            refs = ", ".join(cite(value) for value in cluster.get("top_gids", [])[:3])
            p(f"Қауымдастық {cluster.get('cluster_id')} | {number(cluster.get('n_nodes'))} шот | "
              f"{number(cluster.get('sum_kzt_internal'), 2)} KZT", "item")
            p(text_data(cluster.get("hypothesis")) + (" Негізгі шоттар: " + refs if refs else ""))
        if len(clusters) > 6:
            p(f"Көлемі бойынша 6 / {len(clusters)} қауымдастық берілген. Толық тізім: clusters.csv.", "small")
        quality = analysis.get("quality") or {}
        p("4-қадамдағы шекара: " + number(quality.get("boundary_nodes")) + "; оқшау бастапқы шоттар: "
          + number(quality.get("isolated_seeds")) + "; шығыссыз бастапқы шоттар: " + number(quality.get("seeds_without_outgoing"))
          + "; шығыс кірістен жоғары шоттар: " + number(quality.get("outflow_exceeds_inflow")) + ".")
        for request in (quality.get("requests") or [])[:6]:
            if identifier(request["gid"]) in nodes:
                p(cite(request["gid"]) + ": " + text_data(request.get("request")), "small")

    section("Үлгілер және тексерілетін дәлелдер")
    insights = analysis.get("insights") or {}
    selected_key = identifier(selected["gid"]) if selected else None
    found = 0
    for key, heading, cap in (("events", "Уақыттық және құрылымдық белгілер", 6),
                              ("cycles", "Бағытталған циклдер", 3),
                              ("routes", "Қайталанатын бағыттар", 3)):
        records = [item for item in insights.get(key, [])
                   if selected_key is None or selected_key in {identifier(value) for value in item.get("gids", [])}]
        if not records:
            continue
        p(f"{heading}: {min(len(records), cap)} / {len(records)} нәтиже", "item")
        for item in records[:cap]:
            found += 1
            refs = ", ".join(cite(value) for value in item.get("gids", []) if identifier(value) in nodes)
            p(text_data(item.get("id"), 80) + " | " + text_data(item.get("title"), 160), "item")
            if item.get("date"):
                p("Оқиға күні: " + text_data(item["date"], 100), "small")
            p(text_data(item.get("evidence"), 1600))
            if key == "routes":
                if item.get("n_occurrences") is not None:
                    p("Бақыланған күндік сәйкестіктер: " + number(item["n_occurrences"]), "small")
                for occurrence in (item.get("occurrences") or [])[:3]:
                    dates = occurrence.get("dates") or []
                    if dates:
                        p("Күндер тізбегі: " + " -> ".join(text_data(day, 30) for day in dates)
                          + ". Бір күн ішіндегі нақты рет белгісіз.", "small")
            elif key == "cycles" and item.get("observed_dates"):
                dates = item["observed_dates"]
                p("Цикл қабырғаларындағы бақыланған күндер: " + ", ".join(text_data(day, 30) for day in dates[:8])
                  + (f"; барлығы {len(dates)} күн" if len(dates) > 8 else "")
                  + ". Бұл құрылымдық цикл; қаражат осы ретпен қайтты деген дәлел емес.", "small")
            if refs:
                p("Дәлелге қатысатын шоттар: " + refs, "small")
    if not found:
        p("Осы есепке қатысты сақталған үлгі табылмады. Бұл нақты желіде мұндай әрекет болмағанын дәлелдемейді.")
    p("Іздеу тереңдігі мен нәтиже саны шектеулі болуы мүмкін. Толық оқиғалар, маршруттар және есептеу шектері analysis.json / insights ішінде.", "small")

    section("Әдістеме және қорытындының шектеулері")
    p("Бағытталған графта кіріс/шығыс сомалары, контрагенттер, аударым саны, PageRank және жоларалық орталықтық есептеледі. "
      "Рөлдер ашық ережелермен тағайындалады. Басымдық белгілердің салмақталған қосындысы; қауымдастықтар ағын сомалары біріктірілген "
      "бағытсыз проекцияда Louvain әдісімен бөлінеді.")
    weights = meta.get("priority_weights") or {}
    if weights:
        p("Басымдық салмақтары: " + "; ".join(FEATURE_LABELS.get(name, name) + " " + number(float(value) * 100, 0) + "%"
                                              for name, value in weights.items()), "small")
    p("Кезең, 5 000 KZT шегі, тек банкішілік аударымдар және төрт қадамдық шығыс бойынша кеңейту көріністі шектейді. "
      "Depth=4 немесе шығыстың болмауы соңғы алушыны дәлелдемейді. Seed кірісі толық емес; басқа шоттардың да үзіндіден тыс кірісі болуы мүмкін. "
      "Бір ақшаның тізбекпен жылжығаны, ортақ бақылау немесе қылмыстық мақсат тек осы графтан анықталмайды.")
    p("Ground truth берілмеген: рөл дәлдігі, precision/recall және ықтималдық калибрлеуі өлшенбеген. "
      "Бұл есеп адам тексеруін бағыттайды және нақты шотты бұғаттау туралы шешім шығармайды.")
    for warning in (meta.get("warnings") or [])[:8]:
        p("Дерек ескертуі: " + text_data(warning, 900), "small")
    section("Дерекке сілтемелер")
    p("Негізгі дерек: осы талдаудың analysis.json файлы; nodes[gid], edges[src,dst], clusters[cluster_id], "
      "quality.requests және insights жазбалары. Рөлдер мен топтар: nodes_roles.csv, clusters.csv, top_nodes.csv.", "small")
    if cited:
        p("Осы есепте сілтеме жасалған нақты идентификаторлар: " + "; ".join("GID " + key for key in sorted(cited, key=int)), "small")
    p("Клиенттің аты-жөні, ЖСН, мекенжайы немесе басқа сыртқы сипаттары қосылмаған. "
      "Деректердегі мәтіндер дерек ретінде көрсетілген; олар орындауға арналған нұсқаулар емес.", "small")

    doc = SimpleDocTemplate(output, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=53, bottomMargin=51, title="AQSHA TRACE - investigation report",
                            author="AQSHA TRACE local analysis", subject="Observed transaction network; hypotheses only")
    def make_canvas(*args, **kwargs):
        kwargs["invariant"] = 1
        return Canvas(*args, **kwargs)

    doc.build(story, onFirstPage=_page_decoration, onLaterPages=_page_decoration, canvasmaker=make_canvas)
    return output.getvalue()
