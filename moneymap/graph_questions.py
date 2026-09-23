"""Bounded Kazakh/Russian questions over already computed local evidence.

This is a deterministic intent router, not general language understanding.
Question text is never evaluated, executed, or placed in a provider payload.
Every numeric argument must resolve exactly; unsupported filters are rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from moneymap.ai_facts import build_evidence
from moneymap.data import _exact_integer


MAX_QUESTION_CHARS = 600


class GraphQuestionError(ValueError):
    """A safe, fixed explanation; never includes submitted question text."""


@dataclass(frozen=True)
class GraphQuestion:
    task: str
    arguments: dict


def parse_question(question: str, *, available_gids, cluster_ids) -> GraphQuestion:
    """Recognize one supported task, preserving int64 IDs without float casts."""
    if not isinstance(question, str) or not question.strip():
        raise GraphQuestionError("Сұрақты және қажет болса толық gid мәнін жазыңыз.")
    if len(question) > MAX_QUESTION_CHARS:
        raise GraphQuestionError("Сұрақ 600 таңбадан аспауы керек.")
    text = unicodedata.normalize("NFC", question).lower().replace("ё", "е")
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"\b(топ|top)-(\d+)", r"\1 \2", text)
    if re.search(r"sk-|nvapi-|api[_ -]?key|bearer|\.env|құпия|парол|секрет", text):
        raise GraphQuestionError("Бұл өріс тек граф сұрақтарына арналған; кілттер мен құпияларды енгізбеңіз.")
    if re.search(r"бұғат|блокир|замороз|кінәлі|кінәсіз|винов|қылмыскер|преступник|алаяқ|мошенник", text):
        raise GraphQuestionError("Граф кінәлілікті немесе бұғаттау шешімін анықтамайды. Клиенттің рөлі мен бақылау шектеулерін сұраңыз.")
    if re.search(r"\d[eE][+-]?\d|\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[./]\d{1,2}[./]\d{2,4}|[<>`=]|\b(?:select|import|exec|eval)\b", text):
        raise GraphQuestionError("Күн, сома шарты, код немесе күрделі өрнек қолдау таппайды. Бір тапсырманы толық gid арқылы сұраңыз.")
    if re.search(r"бүгін|кеше|сегодня|вчера|шілде|июл|соңғы\s+\d|последни\w*\s+\d|\d\s*(?:күн|дн|теңге|тенге|₸|kzt)", text):
        raise GraphQuestionError("Мәтіндік сұрақта күн не сома бойынша сүзгі қолданылмайды; жауап толық жүктелген кезеңге қатысты.")

    number_pattern = r"(?<!\w)[+-]?\d+(?!\w)"
    raw_numbers = re.findall(number_pattern, text)
    if re.search(r"\d", re.sub(number_pattern, "", text)):
        raise GraphQuestionError("Сандарды толық әрі бөлек жазыңыз, мысалы: gid 1005. Жабысып жазылған немесе жартылай оқылған идентификатор қабылданбайды.")
    # Do not accept partly parsed identifiers (decimal/scientific notation,
    # grouped digits, gid embedded in a word, or more than five arguments).
    if re.search(r"\d\.\d", text) or len(raw_numbers) > 5:
        raise GraphQuestionError("Ең көбі бес толық, бөлінбеген бүтін gid қолданыңыз; ондық не ғылыми жазылым қабылданбайды.")
    numbers = []
    for value in raw_numbers:
        try:
            if len(value.lstrip("+-")) > 19:
                raise ValueError("size")
            numbers.append(_exact_integer(value))
        except (ValueError, TypeError, OverflowError):
            raise GraphQuestionError("Идентификатор int64 аралығындағы толық бүтін сан болуы керек.") from None

    available = {_exact_integer(value) for value in available_gids}
    clusters = {_exact_integer(value) for value in cluster_ids}
    common = bool(re.search(r"ортақ|общ\w*\s+получател|common\s+recipient", text))
    path = bool(re.search(r"жол|маршрут|путь|пути|цепочк", text))
    completeness = bool(re.search(r"жетісп|шектеу|не\s+хватает|недостат|огранич|дополнительн|сұрат|полнот|толық\w*\s+дерек|дерек\w*\s+толық", text))
    if not completeness and re.search(r"\bне\b|\bнет\b|емес|жоқ|жіберме|аударма|түспе|алмағ|неотправ|неполуч|\bnot\b|without|\bтек\b|только|\bonly\b", text):
        raise GraphQuestionError("Терістеу немесе «тек/только» сияқты қосымша шарттар қолдау таппайды. Көрінетін байланыстарды не жалпы тексеру кезегін сұраңыз.")
    if not completeness and re.search(
        r"январ|феврал|март|апрел|\bма[йя]\b|июн|июл|август|сентябр|октябр|ноябр|декабр|"
        r"қаңтар|ақпан|наурыз|сәуір|мамыр|маусым|шілде|тамыз|қыркүйек|қазан|қараша|желтоқсан|"
        r"недел|месяц|апта|күндер|кезең|период|кроме|исключ|қоспай|свыше|больше|меньше|"
        r"сома\w*\s+(?:жоғары|төмен|артық)|(?:жоғары|төмен|артық)\s+сома", text
    ):
        raise GraphQuestionError("Қосымша уақыт, сома немесе алып тастау шарты қолдау таппайды. Бір тапсырманы сүзгісіз сұраңыз.")
    cluster = "кластер" in text or "cluster" in text
    explicit_top = bool(re.search(r"\b(?:топ|top)\b", text))
    ranking = bool(re.search(r"приоритет|басым|алдымен|бірінші|перв|очеред|кімді\s+тексер", text))
    client_reference = bool(re.search(r"(?:gid|клиент|узел)\s+[+-]?\d|неге|почему|маңыз|важ|рөл|роль", text))
    top = explicit_top or (ranking and not client_reference)
    special = [common, path, completeness, cluster, top]
    if sum(special) > 1:
        raise GraphQuestionError("Бір сұрақта бірнеше тапсырма байқалды. Клиент, кезек, кластер, ортақ алушылар, seed жолы немесе дерек толықтығының бірін сұраңыз.")

    def clients(minimum=1, maximum=1):
        if not minimum <= len(numbers) <= maximum:
            raise GraphQuestionError("Осы сұраққа бір толық gid қажет." if maximum == 1 else "Ортақ алушылар үшін екіден беске дейін толық gid жазыңыз.")
        if len(set(numbers)) != len(numbers):
            raise GraphQuestionError("Клиент gid мәндері қайталанбауы керек.")
        if any(value not in available for value in numbers):
            raise GraphQuestionError("Көрсетілген gid деректер жиынында жоқ. Толық идентификаторды клиенттер кестесінен алыңыз.")
        return [str(value) for value in numbers]

    if common:
        if not re.search(r"алушы|алушылар|получател|recipient", text):
            raise GraphQuestionError("Қолдау бар сұрақ: бірнеше клиенттің ортақ тікелей алушылары.")
        return GraphQuestion("common_recipients", {"gids": clients(2, 5)})
    if path:
        if not re.search(r"\bseed\b|сид|бастапқы", text):
            raise GraphQuestionError("Жол сұрағы бастапқы seed-клиенттерден бір клиентке дейінгі бағытталған жолдарды көрсетеді. Мысалы: «Seed-тен gid 1005-ке жол»." )
        return GraphQuestion("seed_paths", {"gid": clients()[0]})
    if completeness:
        if not numbers and re.search(r"gid|клиент|түйін|узел", text) and not re.search(r"барлық|всех|все\b|желі|желінің|сеть|сети|граф", text):
            raise GraphQuestionError("Жеке клиенттің дерек толықтығы үшін толық gid жазыңыз; бүкіл жиын үшін «желінің дерек шектеулері» деп сұраңыз.")
        return GraphQuestion("data_completeness", {"gid": clients()[0]} if numbers else {})
    if cluster:
        if len(numbers) != 1 or numbers[0] not in clusters:
            raise GraphQuestionError("Деректерде бар бір кластер нөмірін жазыңыз.")
        return GraphQuestion("cluster_summary", {"cluster_id": numbers[0]})
    if top:
        if re.search(r"кіріс|шығыс|сома|сумм|оборот|ақша|деньг|seed|сид|бастапқы|транзит|таратушы|жинақтаушы|үлестіруші|үйлестіруші|соңғы\s+алушы|terminal|peripheral|consolidator|coordinator|distributor|transit|pagerank|betweenness|орталық|централ|төмен|низк|наимен|минимал|операци|аударым|перевод|байланыс", text):
            raise GraphQuestionError("Топ сұрағы барлық клиентті есептелген тексеру басымдығының кему ретімен сұрыптайды. Рөл, seed, сома немесе басқа көрсеткіш бойынша сүзгі/сұрыптау қолдау таппайды.")
        if len(numbers) > 1 or (numbers and not 1 <= numbers[0] <= 10):
            raise GraphQuestionError("Тексеру кезегі үшін 1–10 аралығында бір сан жазыңыз; әдепкісі — 5.")
        return GraphQuestion("top_priority", {"top_n": numbers[0] if numbers else 5})

    incoming = bool(re.search(r"кіріс|вход|получил|түсті|түскен|кімнен|от\s+кого", text))
    outgoing = bool(re.search(r"шығыс|выход|исход|отправ|жібер|кімге|кому", text))
    flow = incoming or outgoing or bool(re.search(r"ақша|аударым|поток|перевод|оборот", text))
    if flow:
        direction = "incoming" if incoming and not outgoing else "outgoing" if outgoing and not incoming else "both"
        return GraphQuestion("client_flows", {"gid": clients()[0], "direction": direction})
    if re.search(r"түсіндір|объясн|анықтама|справк|есеп|отчет|рөл|роль|маңыз|важ|неге|почему|приоритет|басым", text):
        return GraphQuestion("explain_client", {"gid": clients()[0]})
    raise GraphQuestionError("Бұл сұрақты сенімді түрде тани алмадым. Төмендегі үлгілерді қолданыңыз немесе дайын тапсырманы таңдаңыз.")


def answer_question(analysis, roles, question):
    """Return canonical computed facts; the raw text is deliberately discarded."""
    parsed = parse_question(question, available_gids=analysis.graph, cluster_ids=roles.clusters.cluster_id)
    return build_evidence(analysis, roles, parsed.task, **parsed.arguments)
