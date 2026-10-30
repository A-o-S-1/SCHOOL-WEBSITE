"""
Shared result-calculation logic.

Pulled into its own module because it's called from three places that must
stay consistent: the CSV bulk upload, the TermResult admin action, and the
`recalculate_positions` management command. Keeping the ranking rules in
one place means a future change to how ties are handled, for example,
only has to happen once.
"""
import re

from .models import ClassRoom, ResultEntry, TermResult


def normalize_subject_text(text):
    """Strip periods/slashes/ampersands and collapse whitespace, for
    loose matching between a workbook's abbreviated column headers
    (e.g. 'AGRIC. SCI.') and the canonical Subject.name in the database."""
    text = (text or "").upper()
    text = re.sub(r"[.\-/&]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# Known abbreviations used in the school's actual scoresheet column headers,
# mapped to the canonical Subject.name. Extend this if a future workbook
# uses a header we haven't seen yet — the importer reports any header it
# can't resolve rather than silently guessing.
SUBJECT_HEADER_ALIASES = {
    "ENGLISH STUDIES": "English Studies",
    "MATHEMATICS": "Mathematics",
    "INTERMEDIATE SCI": "Intermediate Science",
    "DIGITAL TECH": "Digital Technologies",  # per-level lookup below resolves junior vs senior
    "AGRIC SCI": "Agricultural Science",
    "TECH DRAWING": "Technical Drawing",
    "BUSINESS STD": "Business Studies",
    "P H E": "P.H.E",
    "SOS CIT STD": "Social and Citizenship Studies",
    "C R S": "C.R.S",
    "HOME ECONS": "Home Economics",
    "LITERATURE": "Literature-in-English",  # junior; senior workbooks use 'Literature' directly
    "C C A": "C.C.A",
    "HISTORY": "History",
    "CITIZENSHIP HERITAGE STUDIES": "Citizenship & Heritage Studies",
    "HEALTH SCIENCE": "Health Science",
    "LIVESTOCK FARMING": "Livestock Farming",
    "FINANCIAL ACCOUNTING": "Financial Accounting",
    "COMMERCE": "Commerce",
    "GEOGRAPHY": "Geography",
    "GOVERNMENT": "Government",
    "ECONOMICS": "Economics",
    "PHYSICS": "Physics",
    "CHEMISTRY": "Chemistry",
    "BIOLOGY": "Biology",
}


def resolve_subject(header_text, level):
    """
    Matches a workbook column header (e.g. 'AGRIC. SCI.') to a real Subject
    at the given level ('junior'/'senior'). Tries, in order: exact name
    match, known alias, then a loose prefix match — reports failure rather
    than guessing wrong, since silently attaching a score to the wrong
    subject is worse than rejecting the row. Scoping by level from the
    start also avoids the "which Mathematics?" ambiguity from Step 4 by
    construction — a workbook belongs to one class, hence one level.
    """
    from apps.academics.models import Subject

    normalized_header = normalize_subject_text(header_text)

    exact = Subject.objects.filter(name__iexact=(header_text or "").strip(), level=level).first()
    if exact:
        return exact

    alias_name = SUBJECT_HEADER_ALIASES.get(normalized_header)
    if alias_name:
        aliased = Subject.objects.filter(name__iexact=alias_name, level=level).first()
        if aliased:
            return aliased

    for subject in Subject.objects.filter(level=level):
        if normalize_subject_text(subject.name).startswith(normalized_header):
            return subject

    return None


def classroom_code_to_name(code):
    """
    Converts the school's class code (e.g. 'J1A', 'S2B') to our ClassRoom
    naming convention ('JSS1A', 'SS2B') and level ('junior'/'senior').
    Returns (classroom_name, level) or (None, None) if the code doesn't
    match the expected pattern.
    """
    code = (code or "").strip().upper()
    match = re.match(r"^([JS])(\d)([A-Z])$", code)
    if not match:
        return None, None
    prefix, grade, arm = match.groups()
    if prefix == "J":
        return f"JSS{grade}{arm}", "junior"
    return f"SS{grade}{arm}", "senior"


def ordinal(n):
    """1 -> '1st', 2 -> '2nd', 3 -> '3rd', 11 -> '11th', ..."""
    if 11 <= n % 100 <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def recalculate_term_result_totals(student, term):
    """Recompute one student's term summary with a single score query."""
    from django.db.models import Sum, Count

    aggregate = ResultEntry.objects.filter(student=student, term=term).aggregate(
        total=Sum("ca_score") + Sum("exam_score"), count=Count("id")
    )
    count = aggregate["count"] or 0
    total = aggregate["total"] or 0
    term_result, _ = TermResult.objects.get_or_create(student=student, term=term)
    term_result.overall_total = total
    term_result.average = round(total / count, 1) if count else None
    term_result.save(update_fields=["overall_total", "average"])
    return term_result


def recalculate_positions_for_term(term):
    """Recalculate rankings using bulk_update rather than one UPDATE per row."""
    entries_updated = 0
    term_results_updated = 0

    classrooms = ClassRoom.objects.prefetch_related("students").all()
    for classroom in classrooms:
        student_ids = list(classroom.students.filter(is_active=True).values_list("id", flat=True))
        if not student_ids:
            continue

        entries = list(
            ResultEntry.objects.filter(term=term, student_id__in=student_ids)
            .select_related("subject")
        )
        by_subject = {}
        for entry in entries:
            by_subject.setdefault(entry.subject_id, []).append(entry)

        for subject_entries in by_subject.values():
            subject_entries.sort(key=lambda e: e.total_score, reverse=True)
            average = round(sum(e.total_score for e in subject_entries) / len(subject_entries), 1)
            rank, previous_score = 0, None
            for i, entry in enumerate(subject_entries):
                if entry.total_score != previous_score:
                    rank = i + 1
                    previous_score = entry.total_score
                entry.position_in_subject = ordinal(rank)
                entry.subject_class_average = average
            ResultEntry.objects.bulk_update(
                subject_entries, ["position_in_subject", "subject_class_average"], batch_size=500
            )
            entries_updated += len(subject_entries)

        term_results = list(TermResult.objects.filter(term=term, student_id__in=student_ids))
        term_results.sort(key=lambda tr: (tr.average if tr.average is not None else -1), reverse=True)
        total_in_class = len(term_results)
        rank, previous_average = 0, None
        for i, term_result in enumerate(term_results):
            if term_result.average != previous_average:
                rank = i + 1
                previous_average = term_result.average
            term_result.position_in_class = f"{ordinal(rank)} out of {total_in_class}"
        if term_results:
            TermResult.objects.bulk_update(term_results, ["position_in_class"], batch_size=500)
            term_results_updated += len(term_results)

    return entries_updated, term_results_updated
