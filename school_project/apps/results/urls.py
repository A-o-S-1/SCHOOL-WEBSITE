from django.urls import path

from . import views

app_name = "results"

urlpatterns = [
    path("staff/upload-scores/", views.ScoreUploadView.as_view(), name="upload_scores"),
    path("staff/upload-workbook/", views.WorkbookUploadView.as_view(), name="upload_workbook"),
    path("staff/master-sheet/", views.MasterSheetView.as_view(), name="master_sheet"),
    path("staff/promotion-results/", views.PromotionResultView.as_view(), name="promotion_results"),
    path("staff/result/<int:student_id>/<int:term_id>/", views.StaffResultPrintView.as_view(), name="staff_result_print"),
    path("staff/class-results/", views.StaffClassResultsPrintView.as_view(), name="staff_class_results_print"),
]
