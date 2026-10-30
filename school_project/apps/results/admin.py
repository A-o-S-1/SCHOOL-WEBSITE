import csv

from django.contrib import admin, messages
from django.http import HttpResponse
from django.urls import reverse
from django.utils.html import format_html

from . import services
from .models import (
    AcademicSession,
    ClassRoom,
    GradeBand,
    PsychomotorRating,
    PsychomotorSkill,
    ResultEntry,
    SessionResult,
    Student,
    Term,
    TermResult,
)


@admin.register(AcademicSession)
class AcademicSessionAdmin(admin.ModelAdmin):
    list_display = ("label", "start_date", "end_date", "is_current")
    list_editable = ("is_current",)


@admin.register(Term)
class TermAdmin(admin.ModelAdmin):
    list_display = ("__str__", "is_current", "next_term_begins", "next_term_fees")
    list_filter = ("session", "name")
    list_editable = ("is_current",)


@admin.register(ClassRoom)
class ClassRoomAdmin(admin.ModelAdmin):
    list_display = ("name", "level", "arm", "class_teacher", "student_count")
    list_filter = ("level",)
    ordering = ("order", "name")

    def student_count(self, obj):
        return obj.students.count()


class ExportCsvMixin:
    """
    Shared "Export selected as CSV" admin action — used by Student and
    ClassRoom admins. Matches "View and/or Export Combined Population" and
    "View and Export Class-By-Class List" from the original admin panel,
    without needing a separate custom view for each.
    """
    def export_as_csv(self, request, queryset):
        meta = self.model._meta
        field_names = self.csv_fields
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f"attachment; filename={meta.model_name}_export.csv"
        writer = csv.writer(response)
        writer.writerow(field_names)
        for obj in queryset:
            writer.writerow([getattr(obj, field, "") for field in field_names])
        return response

    export_as_csv.short_description = "Export selected as CSV"


@admin.register(Student)
class StudentAdmin(ExportCsvMixin, admin.ModelAdmin):
    list_display = ("admission_number", "full_name", "current_class", "gender", "is_active")
    list_filter = ("current_class", "gender", "is_active")
    search_fields = ("admission_number", "first_name", "last_name")
    actions = ["export_as_csv"]
    csv_fields = ["admission_number", "first_name", "last_name", "current_class", "gender", "guardian_name", "guardian_phone", "is_active"]


@admin.register(GradeBand)
class GradeBandAdmin(admin.ModelAdmin):
    list_display = ("grade_code", "min_score", "max_score", "remark", "order")
    list_editable = ("min_score", "max_score", "remark", "order")
    ordering = ("order",)


@admin.register(PsychomotorSkill)
class PsychomotorSkillAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "order")
    list_filter = ("category",)
    list_editable = ("order",)


@admin.register(PsychomotorRating)
class PsychomotorRatingAdmin(admin.ModelAdmin):
    list_display = ("student", "term", "skill", "rating")
    list_filter = ("term", "skill__category")
    search_fields = ("student__admission_number", "student__first_name", "student__last_name")


@admin.register(ResultEntry)
class ResultEntryAdmin(admin.ModelAdmin):
    change_list_template = "admin/results_tools_link.html"
    list_display = ("student", "subject", "term", "ca_score", "exam_score", "total_display", "grade_display")
    list_filter = ("term", "subject", "student__current_class")
    search_fields = ("student__admission_number", "student__first_name", "student__last_name")
    autocomplete_fields = ["student", "subject"]

    def total_display(self, obj):
        return obj.total_score
    total_display.short_description = "Total"

    def grade_display(self, obj):
        return f"{obj.grade_code} — {obj.remark}"
    grade_display.short_description = "Grade"


@admin.register(TermResult)
class TermResultAdmin(admin.ModelAdmin):
    change_list_template = "admin/results_tools_link.html"
    list_display = ("student", "term", "average", "position_in_class", "is_published", "is_blocked", "print_link")
    list_filter = ("term", "is_published", "is_blocked")
    search_fields = ("student__admission_number", "student__first_name", "student__last_name")
    list_editable = ("is_published", "is_blocked")
    actions = ["publish_results", "unpublish_results", "recalculate_summary", "recalculate_positions"]

    def print_link(self, obj):
        url = reverse("results:staff_result_print", args=[obj.student_id, obj.term_id])
        return format_html('<a href="{}" target="_blank">Print &rarr;</a>', url)
    print_link.short_description = "Print"

    def publish_results(self, request, queryset):
        updated = queryset.update(is_published=True)
        self.message_user(request, f"Published {updated} result(s).", messages.SUCCESS)
    publish_results.short_description = "Publish selected results"

    def unpublish_results(self, request, queryset):
        updated = queryset.update(is_published=False)
        self.message_user(request, f"Unpublished {updated} result(s).", messages.SUCCESS)
    unpublish_results.short_description = "Unpublish selected results"

    def recalculate_summary(self, request, queryset):
        """Recomputes overall_total/average from each selected student's ResultEntry rows."""
        count = 0
        for term_result in queryset:
            services.recalculate_term_result_totals(term_result.student, term_result.term)
            count += 1
        self.message_user(request, f"Recalculated totals for {count} result(s).", messages.SUCCESS)
    recalculate_summary.short_description = "Recalculate totals from result entries"

    def recalculate_positions(self, request, queryset):
        """
        Recalculates per-subject positions/class-averages and per-class
        overall position for every TERM represented in the selection —
        this ranks the WHOLE class, not just the rows you selected, since
        a position only makes sense relative to all of a student's
        classmates.
        """
        terms = {tr.term for tr in queryset}
        total_entries, total_term_results = 0, 0
        for term in terms:
            entries, term_results = services.recalculate_positions_for_term(term)
            total_entries += entries
            total_term_results += term_results
        self.message_user(
            request,
            f"Recalculated positions across {len(terms)} term(s): "
            f"{total_entries} subject entries, {total_term_results} student summaries.",
            messages.SUCCESS,
        )
    recalculate_positions.short_description = "Recalculate positions & class averages (whole class)"

@admin.register(SessionResult)
class SessionResultAdmin(admin.ModelAdmin):
    change_list_template = "admin/results_tools_link.html"
    list_display = ("student", "session", "cumulative_total", "session_average", "overall_position", "promotion_status", "is_published")
    list_filter = ("session", "promotion_status", "is_published")
    search_fields = ("student__admission_number", "student__first_name", "student__last_name")
    list_editable = ("is_published",)
    actions = ["publish_session_results", "unpublish_session_results"]

    def publish_session_results(self, request, queryset):
        updated = queryset.update(is_published=True)
        self.message_user(request, f"Published {updated} session result(s).", messages.SUCCESS)
    publish_session_results.short_description = "Publish selected session results"

    def unpublish_session_results(self, request, queryset):
        updated = queryset.update(is_published=False)
        self.message_user(request, f"Unpublished {updated} session result(s).", messages.SUCCESS)
    unpublish_session_results.short_description = "Unpublish selected session results"
