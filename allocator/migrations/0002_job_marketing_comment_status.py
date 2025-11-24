from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('allocator', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='marketing_comment_status',
            field=models.CharField(choices=[('pending', 'Pending Review'), ('approved', 'Approved'), ('rejected', 'Needs Update')], default='pending', max_length=16),
        ),
        migrations.AddField(
            model_name='job',
            name='allocator_comment',
            field=models.TextField(blank=True, null=True),
        ),
    ]
