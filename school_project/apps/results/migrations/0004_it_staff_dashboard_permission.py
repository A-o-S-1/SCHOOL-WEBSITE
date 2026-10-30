from django.db import migrations, models


def create_it_staff_group(apps, schema_editor):
    database = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    group, _ = Group.objects.using(database).get_or_create(name="IT Staff")
    content_type, _ = ContentType.objects.using(database).get_or_create(
        app_label="results",
        model="student",
    )
    permission, _ = Permission.objects.using(database).get_or_create(
        content_type=content_type,
        codename="access_student_results",
        defaults={"name": "Can access student results dashboard"},
    )
    group.permissions.set([permission])


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("results", "0003_alter_gradeband_grade_code_sessionresult"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="student",
            options={
                "ordering": ["last_name", "first_name"],
                "permissions": [
                    ("access_student_results", "Can access student results dashboard"),
                ],
            },
        ),
        migrations.AlterField(
            model_name="termresult",
            name="is_published",
            field=models.BooleanField(
                default=False,
                help_text="Marks this result approved for release; access remains staff-only.",
            ),
        ),
        migrations.AlterField(
            model_name="termresult",
            name="is_blocked",
            field=models.BooleanField(
                default=False,
                help_text="Withholds this result from IT dashboard print actions (e.g. a fees hold).",
            ),
        ),
        migrations.RunPython(create_it_staff_group, migrations.RunPython.noop),
    ]