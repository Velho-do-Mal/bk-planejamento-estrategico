from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('planejamento', '0003_planningdata_plano'),
    ]

    operations = [
        # 1. Criar tabela Empresa
        migrations.CreateModel(
            name='Empresa',
            fields=[
                ('id',          models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('slug',        models.SlugField(unique=True)),
                ('nome',        models.CharField(max_length=200)),
                ('plano',       models.CharField(choices=[('free','Free'),('pago','Pago')], default='free', max_length=20)),
                ('ativa',       models.BooleanField(default=True)),
                ('email',       models.EmailField(blank=True)),
                ('telefone',    models.CharField(blank=True, max_length=20)),
                ('responsavel', models.CharField(blank=True, max_length=200)),
                ('criada_em',   models.DateTimeField(auto_now_add=True)),
            ],
            options={'verbose_name':'Empresa','verbose_name_plural':'Empresas','ordering':['-criada_em']},
        ),
        # 2. Adicionar FK empresa em PlanningData (nullable)
        migrations.AddField(
            model_name='planningdata',
            name='empresa',
            field=models.OneToOneField(
                blank=True, null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='planning',
                to='planejamento.empresa',
            ),
        ),
        # 3. Remover campo plano de PlanningData (migrado para Empresa)
        migrations.RemoveField(model_name='planningdata', name='plano'),
    ]
