from django.db import migrations


def criar_empresa_bk(apps, schema_editor):
    """Cria empresa padrão BK e vincula ao PlanningData existente."""
    Empresa      = apps.get_model('planejamento', 'Empresa')
    PlanningData = apps.get_model('planejamento', 'PlanningData')

    empresa, _ = Empresa.objects.get_or_create(
        slug='bk',
        defaults={'nome': 'BK Engenharia', 'plano': 'pago', 'ativa': True},
    )
    for pd in PlanningData.objects.filter(empresa__isnull=True):
        pd.empresa = empresa
        pd.save(update_fields=['empresa'])


def reverter(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('planejamento', '0004_empresa_multitenant'),
    ]

    operations = [
        migrations.RunPython(criar_empresa_bk, reverter),
    ]
