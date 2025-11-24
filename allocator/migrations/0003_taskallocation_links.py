from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('allocator', '0002_job_marketing_comment_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='taskallocation',
            name='writer_final_link',
            field=models.URLField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='taskallocation',
            name='summary_link',
            field=models.URLField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='taskallocation',
            name='process_final_link',
            field=models.URLField(blank=True, null=True),
        ),
    ]
