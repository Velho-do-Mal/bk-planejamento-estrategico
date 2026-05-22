from django.db import migrations


def link_superuser_empresa(apps, schema_editor):
    """Vincula superusuários existentes à empresa BK."""
    Usuario = apps.get_model('accounts', 'Usuario')
    Empresa = apps.get_model('planejamento', 'Empresa')
    try:
        bk = Empresa.objects.get(slug='bk')
        for u in Usuario.objects.filter(is_superuser=True, empresa__isnull=True):
            u.empresa = bk
            u.save(update_fields=['empresa'])
    except Empresa.DoesNotExist:
        pass


class Migration(migrations.Migration):
    dependencies = [
        ('accounts',     '0003_usuario_empresa'),
        ('planejamento', '0005_data_empresa_default'),
    ]
    operations = [migrations.RunPython(link_superuser_empresa, migrations.RunPython.noop)]
