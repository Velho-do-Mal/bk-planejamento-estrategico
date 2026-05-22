from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('planejamento', '0002_normalize_okrs_to_s'),
    ]

    operations = [
        migrations.AddField(
            model_name='planningdata',
            name='plano',
            field=models.CharField(
                choices=[('free', 'Free'), ('pago', 'Pago')],
                default='pago',
                max_length=20,
            ),
        ),
    ]
