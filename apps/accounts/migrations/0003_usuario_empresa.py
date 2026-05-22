from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts',     '0002_initial'),
        ('planejamento', '0005_data_empresa_default'),
    ]

    operations = [
        migrations.AddField(
            model_name='usuario',
            name='empresa',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='usuarios',
                to='planejamento.empresa',
                verbose_name='Empresa',
            ),
        ),
    ]
