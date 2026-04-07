from django.db import migrations

def normalize_okrs_to_s(apps, schema_editor):
    """Migração para normalizar dados antigos de 'okrs' para 's'"""
    PlanningData = apps.get_model('planejamento', 'PlanningData')
    
    for obj in PlanningData.objects.all():
        dados = obj.dados or {}
        
        # Se existir 'okrs' e 's' estiver vazio ou não existir, migrar
        if 'okrs' in dados and dados['okrs']:
            if 's' not in dados or not dados['s']:
                dados['s'] = dados['okrs']
            # Remover chave 'okrs' antiga
            if 'okrs' in dados:
                del dados['okrs']
            obj.dados = dados
            obj.save()

def reverse_normalize(apps, schema_editor):
    """Reverter a migração (opcional)"""
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('planejamento', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(normalize_okrs_to_s, reverse_normalize),
    ]
