"""
Result Portal models.

Split across this file for readability, in the order a result actually
gets built: calendar (session/term) -> people (classroom/student) ->
grading rules -> the result itself. Legacy scratch-card and lookup-log
records remain in the schema for deployed-data compatibility; staff login
is now the only result-access path.
"""
import secrets
import string

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


# ==============================================================================
# School calendar
# ==============================================================================
class AcademicSession(models.Model):
    """A school year, e.g. '2025/2026'. Only one should be marked current at a time."""

    label = models.CharField(max_length=20, unique=True, help_text="e.g. 2025/2026")
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(
        default=False,
        help_text="The session currently in progress. Only one session should be current — "
        "saving this as current automatically un-marks any other session.",
    )

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return self.label

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_current:
            # Enforce "only one current session" here rather than in a form/admin
            # validator, so it holds true no matter how the row gets saved.
            AcademicSession.objects.exclude(pk=self.pk).update(is_current=False)


class Term(models.Model):
    """One of the three terms within an academic session."""

    TERM_CHOICES = [
        ("first", "First Term"),
        ("second", "Second Term"),
        ("third", "Third Term"),
    ]

    session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE, related_name="terms")
    name = models.CharField(max_length=10, choices=TERM_CHOICES)
    is_current = models.BooleanField(
        default=False,
        help_text="The term currently in progress. Only one term should be current.",
    )
    next_term_begins = models.DateField(
        blank=True, null=True, help_text="Shown on the result sheet as the resumption date."
    )
    next_term_fees = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True,
        help_text="Optional — shown on the result sheet if set.",
    )
    vacation_date = models.DateField(blank=True, null=True)

    class Meta:
        ordering = ["session__start_date", "name"]
        unique_together = ["session", "name"]

    def __str__(self):
        return f"{self.get_name_display()} — {self.session.label}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_current:
            Term.objects.exclude(pk=self.pk).update(is_current=False)

    @classmethod
    def get_current(cls):
        return cls.objects.filter(is_current=True).first()


# ==============================================================================
# People
# ==============================================================================
class ClassRoom(models.Model):
    """
    A specific class arm, e.g. 'JSS1A', 'SS2B'. Kept as its own model (rather
    than a free-text field on Student) so results can be aggregated and
    ranked per class, and so a class teacher can be assigned.
    """

    LEVEL_CHOICES = [
        ("jss1", "JSS 1"), ("jss2", "JSS 2"), ("jss3", "JSS 3"),
        ("ss1", "SS 1"), ("ss2", "SS 2"), ("ss3", "SS 3"),
    ]

    name = models.CharField(max_length=20, unique=True, help_text="e.g. JSS1A")
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES)
    arm = models.CharField(max_length=5, help_text="e.g. A, B, C")
    class_teacher = models.ForeignKey(
        "staff.StaffMember", on_delete=models.SET_NULL, blank=True, null=True, related_name="classes_taught"
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

    @property
    def subject_level(self):
        """
        Maps this classroom's level ('jss1'..'ss3') to the vocabulary used
        by academics.Subject.level ('junior'/'senior') — needed because
        subject names like 'Mathematics' exist at BOTH levels, and score
        upload needs to know which one a given class's students take.
        """
        return "junior" if self.level.startswith("jss") else "senior"


class Student(models.Model):
    """A student record identified by the school's admission number."""

    GENDER_CHOICES = [("M", "Male"), ("F", "Female")]

    admission_number = models.CharField(max_length=20, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    date_of_birth = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True)
    current_class = models.ForeignKey(ClassRoom, on_delete=models.SET_NULL, null=True, related_name="students")
    passport_photo = models.ImageField(upload_to="students/", blank=True, null=True)
    guardian_name = models.CharField(max_length=150, blank=True)
    guardian_phone = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True, help_text="Unchecking this hides the student from new result entry without deleting their records.")
    admitted_date = models.DateField(default=timezone.now)

    class Meta:
        ordering = ["last_name", "first_name"]
        permissions = [
            ("access_student_results", "Can access student results dashboard"),
        ]

    def __str__(self):
        return f"{self.full_name} ({self.admission_number})"

    @property
    def full_name(self):
        parts = [self.last_name, self.first_name, self.middle_name]
        return " ".join(p for p in parts if p)


# ==============================================================================
# Grading rules
# ==============================================================================
class GradeBand(models.Model):
    """
    One row of the grading scale, e.g. '70-100 = A, Excellent'.

    Design decision: this is a database table, not a hardcoded Python dict —
    seeded with our best reading of the school's existing report card, but
    fully editable from /admin/ if any boundary needs correcting, with zero
    code changes or redeployment required.
    """

    min_score = models.PositiveSmallIntegerField()
    max_score = models.PositiveSmallIntegerField()
    grade_code = models.CharField(max_length=5, help_text="e.g. A, B, C")
    remark = models.CharField(max_length=50, help_text="e.g. Excellent, Credit, Fail")
    order = models.PositiveIntegerField(default=0, help_text="Display order, highest grade first.")

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.grade_code} ({self.min_score}-{self.max_score}): {self.remark}"

    def clean(self):
        if self.min_score > self.max_score:
            raise ValidationError("Minimum score cannot be greater than maximum score.")

    @classmethod
    def for_score(cls, score):
        """Returns the matching GradeBand for a given score, or None if the
        scale has a gap (which would itself indicate a data-entry mistake
        worth fixing in the admin rather than crashing the result page)."""
        return cls.objects.filter(min_score__lte=score, max_score__gte=score).first()


class PsychomotorSkill(models.Model):
    """One rated skill on the report card, e.g. 'Handwriting' or 'Punctuality'."""

    CATEGORY_CHOICES = [
        ("psychomotor", "Psychomotor Skills"),
        ("social", "Social Behaviour"),
    ]

    name = models.CharField(max_length=100)
    category = models.CharField(max_length=15, choices=CATEGORY_CHOICES)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["category", "order"]
        unique_together = ["name", "category"]

    def __str__(self):
        return self.name


class PsychomotorRating(models.Model):
    """A student's 1-5 rating for one skill, for one term."""

    RATING_CHOICES = [(5, "5 — Excellent"), (4, "4 — Good"), (3, "3 — Fair"), (2, "2 — Poor"), (1, "1 — Very Poor")]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="psychomotor_ratings")
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name="psychomotor_ratings")
    skill = models.ForeignKey(PsychomotorSkill, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES)

    class Meta:
        unique_together = ["student", "term", "skill"]
        ordering = ["skill__category", "skill__order"]

    def __str__(self):
        return f"{self.student} — {self.skill}: {self.rating}"


# ==============================================================================
# Results
# ==============================================================================
class ResultEntry(models.Model):
    """
    One subject's score for one student in one term: CA + Exam = Total.

    Design decision: grade/remark are NOT stored — they're computed from
    GradeBand.for_score() at render/save time. Storing them would risk them
    silently going stale if someone edits the grading scale later; computing
    them live guarantees the report always reflects the current scale.
    """

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="result_entries")
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name="result_entries")
    subject = models.ForeignKey("academics.Subject", on_delete=models.CASCADE, related_name="result_entries")

    ca_score = models.DecimalField(max_digits=5, decimal_places=1, default=0, help_text="Continuous assessment score (out of 30).")
    exam_score = models.DecimalField(max_digits=5, decimal_places=1, default=0, help_text="Examination score (out of 70).")

    position_in_subject = models.CharField(
        max_length=10, blank=True,
        help_text="e.g. 1st, 2nd — recalculated by the 'Recalculate positions' admin action.",
    )
    subject_class_average = models.DecimalField(
        max_digits=5, decimal_places=1, blank=True, null=True,
        help_text="Recalculated by the 'Recalculate positions' admin action.",
    )

    class Meta:
        unique_together = ["student", "term", "subject"]
        ordering = ["subject__name"]
        verbose_name_plural = "Result entries"

    def __str__(self):
        return f"{self.student} — {self.subject} ({self.term})"

    def clean(self):
        if self.ca_score is not None and self.ca_score > 30:
            raise ValidationError({"ca_score": "CA score cannot exceed 30."})
        if self.exam_score is not None and self.exam_score > 70:
            raise ValidationError({"exam_score": "Exam score cannot exceed 70."})

    @property
    def total_score(self):
        return (self.ca_score or 0) + (self.exam_score or 0)

    @property
    def grade_band(self):
        return GradeBand.for_score(self.total_score)

    @property
    def grade_code(self):
        band = self.grade_band
        return band.grade_code if band else "—"

    @property
    def remark(self):
        band = self.grade_band
        return band.remark if band else "Ungraded"


class TermResult(models.Model):
    """
    Per-student, per-term summary — the "cover sheet" of a result: overall
    total/average, class position, remarks, and staff-managed release/hold
    flags.

    Publication does not expose a result publicly. The IT dashboard remains
    authenticated, and blocked results are withheld from print actions.
    """

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="term_results")
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name="term_results")

    overall_total = models.DecimalField(max_digits=7, decimal_places=1, blank=True, null=True)
    average = models.DecimalField(max_digits=5, decimal_places=1, blank=True, null=True)
    position_in_class = models.CharField(max_length=10, blank=True, help_text="e.g. 1st out of 40")
    overall_performance = models.CharField(max_length=50, blank=True, help_text="e.g. Excellent, Good")
    promotion_status = models.CharField(max_length=100, blank=True, default="As in cumulative result")

    class_teacher_remark = models.TextField(blank=True)
    administrator_remark = models.TextField(blank=True)

    is_published = models.BooleanField(
        default=False,
        help_text="Marks this result approved for release; access remains staff-only.",
    )
    is_blocked = models.BooleanField(
        default=False,
        help_text="Withholds this result from IT dashboard print actions (e.g. a fees hold).",
    )

    generated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["student", "term"]
        ordering = ["-term__session__start_date", "position_in_class"]

    def __str__(self):
        return f"{self.student} — {self.term}"

# ==============================================================================
# Legacy scratch-card records. Kept for deployed-data compatibility only;
# result access is now restricted to authenticated staff accounts.
# ==============================================================================
def generate_pin():
    """12-digit numeric PIN — matches the WAEC/NECO-style scratch card format
    parents already recognize, generated with the `secrets` module (not
    `random`) since this is a security credential, not cosmetic data."""
    return "".join(secrets.choice(string.digits) for _ in range(12))


def generate_serial():
    """A human-typeable serial number, e.g. MDS-7F3K9Q2R."""
    alphabet = string.ascii_uppercase + string.digits
    return "MDS-" + "".join(secrets.choice(alphabet) for _ in range(8))


class ScratchCardBatch(models.Model):
    """
    Tracks one bulk-generation run of scratch cards, e.g. "500 cards for
    First Term 2025/2026". Not sold or activated itself — just groups the
    ScratchCards it created so an admin can find/export/print them together.
    """

    label = models.CharField(max_length=150, help_text="e.g. First Term 2025/2026 Batch 1")
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, help_text="Informational only — price charged per card when sold offline.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Scratch card batches"

    def __str__(self):
        return f"{self.label} ({self.quantity} cards)"


class ScratchCard(models.Model):
    """
    One PIN+Serial pair. A card is single-use: once a lookup with this
    card succeeds, it's marked used and can never unlock a result again —
    exactly like a physical WAEC scratch card. An admin can manually
    reactivate one (e.g. "Activate Supplementary Scratch Card" from the
    original admin panel) for a legitimate re-check.
    """

    batch = models.ForeignKey(ScratchCardBatch, on_delete=models.SET_NULL, null=True, related_name="cards")
    pin = models.CharField(max_length=12, unique=True, default=generate_pin)
    serial_number = models.CharField(max_length=20, unique=True, default=generate_serial)
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(blank=True, null=True)
    used_for_student = models.ForeignKey(Student, on_delete=models.SET_NULL, blank=True, null=True, related_name="scratch_cards_used")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.serial_number} ({'used' if self.is_used else 'active'})"

    def mark_used(self, student):
        self.is_used = True
        self.used_at = timezone.now()
        self.used_for_student = student
        self.save(update_fields=["is_used", "used_at", "used_for_student"])


# ==============================================================================
# Audit logging
# ==============================================================================
class ResultCheckLog(models.Model):
    """
    Every result-lookup attempt, successful or not. Exists for two reasons:
    security auditing (spotting brute-force patterns against admission
    numbers or PINs) and rate limiting (the lookup view checks recent rows
    from this table before allowing another attempt from the same IP).

    Deliberately does NOT store the raw PIN that was attempted — only
    whether it succeeded — so this table can't itself become a source of
    leaked valid PINs if it were ever exposed.
    """

    admission_number_attempted = models.CharField(max_length=20)
    ip_address = models.GenericIPAddressField()
    was_successful = models.BooleanField(default=False)
    attempted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-attempted_at"]
        indexes = [
            models.Index(fields=["ip_address", "attempted_at"]),
            models.Index(fields=["admission_number_attempted", "attempted_at"]),
        ]

    def __str__(self):
        status = "OK" if self.was_successful else "FAILED"
        return f"{self.admission_number_attempted} from {self.ip_address} — {status}"


# ==============================================================================
# Session-level cumulative summary (the "annual broadsheet")
# ==============================================================================
class SessionResult(models.Model):
    """
    One student's cumulative record for a whole ACADEMIC SESSION (all three
    terms combined) — matches the school's own "Annual Cumulative Broadsheet"
    sheet. This is a separate concept from TermResult: a term result is
    entered by staff as scores come in; a session result is finalized once
    at year-end and carries the promotion decision, which is a staff
    judgment call, not something derivable purely from the numbers.

    Design decision: term totals are STORED here (copied from the school's
    own broadsheet at import time) rather than always summing the three
    TermResult rows live. The school's broadsheet is the authoritative
    record of what was decided — recomputing it silently from possibly
    incomplete TermResult data could disagree with what was actually
    published to parents and staff at the time.
    """

    PROMOTION_CHOICES = [
        ("promoted", "Promoted"),
        ("promoted_on_trial", "Promoted on Trial"),
        ("repeat", "Repeat"),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="session_results")
    session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE, related_name="session_results")

    first_term_total = models.DecimalField(max_digits=7, decimal_places=1, blank=True, null=True)
    second_term_total = models.DecimalField(max_digits=7, decimal_places=1, blank=True, null=True)
    third_term_total = models.DecimalField(max_digits=7, decimal_places=1, blank=True, null=True)
    cumulative_total = models.DecimalField(max_digits=8, decimal_places=1, blank=True, null=True)
    session_average = models.DecimalField(max_digits=5, decimal_places=1, blank=True, null=True)
    overall_position = models.CharField(max_length=10, blank=True, help_text="e.g. 2nd out of 41")
    promotion_status = models.CharField(max_length=20, choices=PROMOTION_CHOICES, blank=True)

    is_published = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["student", "session"]
        ordering = ["-session__start_date"]
        verbose_name = "Session Result (Annual Broadsheet)"

    def __str__(self):
        return f"{self.student} — {self.session}"
