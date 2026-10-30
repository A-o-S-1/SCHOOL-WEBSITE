from django import forms


class ScoreCSVUploadForm(forms.Form):
    """
    Bulk score upload. Expected CSV columns (header row required):
        admission_number, subject, ca_score, exam_score
    One term is chosen for the whole file — every row in one upload
    belongs to the same term, since that's how a teacher/admin naturally
    works (marking one term's scores in one sitting).
    """
    term = forms.ChoiceField(label="Term")
    csv_file = forms.FileField(label="CSV File")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import Term
        self.fields["term"].choices = [
            (t.id, str(t)) for t in Term.objects.select_related("session").all()
        ]

    def clean_csv_file(self):
        f = self.cleaned_data["csv_file"]
        if not f.name.lower().endswith(".csv"):
            raise forms.ValidationError("Please upload a .csv file.")
        return f


class MasterSheetForm(forms.Form):
    RESULT_TYPE_CHOICES = [
        ("term", "Single Term"),
        ("session_cumulative", "Session Cumulative (Annual Broadsheet)"),
    ]
    
    result_type = forms.ChoiceField(label="Result Type", choices=RESULT_TYPE_CHOICES, initial="term")
    term = forms.ChoiceField(label="Term", required=False)
    session = forms.ChoiceField(label="Session", required=False)
    classroom = forms.ChoiceField(label="Class")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import AcademicSession, ClassRoom, Term
        self.fields["term"].choices = [
            (t.id, str(t)) for t in Term.objects.select_related("session").all()
        ]
        self.fields["session"].choices = [
            (s.id, s.label) for s in AcademicSession.objects.all()
        ]
        self.fields["classroom"].choices = [
            (c.id, c.name) for c in ClassRoom.objects.all()
        ]


class WorkbookUploadForm(forms.Form):
    """
    Upload the school's actual result workbook — one file per class/arm,
    containing REGISTER, 1ST/2ND/3RD TERM, and BROADSHEET sheets exactly
    as the school's real template produces them. This single upload
    creates missing Student records from REGISTER, scores from whichever
    term sheets have data, and the annual summary from BROADSHEET.
    """
    session = forms.ChoiceField(label="Academic Session")
    workbook_file = forms.FileField(label="Workbook (.xlsx)")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import AcademicSession
        self.fields["session"].choices = [
            (s.id, s.label) for s in AcademicSession.objects.all()
        ]

    def clean_workbook_file(self):
        f = self.cleaned_data["workbook_file"]
        if not f.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Please upload a .xlsx workbook file.")
        return f


class PromotionResultForm(forms.Form):
    """Form for selecting a class and session to print promotion results."""
    session = forms.ChoiceField(label="Academic Session")
    classroom = forms.ChoiceField(label="Class")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import AcademicSession, ClassRoom
        self.fields["session"].choices = [
            (s.id, s.label) for s in AcademicSession.objects.all()
        ]
        self.fields["classroom"].choices = [
            (c.id, c.name) for c in ClassRoom.objects.all()
        ]
