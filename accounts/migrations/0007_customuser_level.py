from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_auto_20251115_1124'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='level',
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
