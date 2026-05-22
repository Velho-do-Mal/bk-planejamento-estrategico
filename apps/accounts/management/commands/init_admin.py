import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

class Command(BaseCommand):
    help = 'Cria empresa padrão + superusuário se não existir nenhum'

    def handle(self, *args, **options):
        from apps.planejamento.models import Empresa, PlanningData
        Usuario = get_user_model()

        # 1. Criar empresa padrão BK
        empresa, criada = Empresa.objects.get_or_create(
            slug='bk',
            defaults={'nome': os.environ.get('EMPRESA_NOME','BK Engenharia'),
                      'plano': 'pago', 'ativa': True,
                      'email': os.environ.get('ADMIN_EMAIL','')}
        )
        if criada:
            self.stdout.write(self.style.SUCCESS(f'Empresa "{empresa.nome}" criada.'))

        # 2. Criar PlanningData para a empresa
        PlanningData.get_or_create_for(empresa)

        # 3. Criar superusuário se não existir
        if Usuario.objects.filter(is_superuser=True).exists():
            self.stdout.write('Superusuário já existe — nenhuma ação necessária.')
            # Garantir que superusuários existentes tenham empresa
            for u in Usuario.objects.filter(is_superuser=True, empresa__isnull=True):
                u.empresa = empresa; u.save(update_fields=['empresa'])
            return

        username = os.environ.get('ADMIN_USERNAME', 'velho')
        password = os.environ.get('ADMIN_PASSWORD', 'velhodomal1976')
        email    = os.environ.get('ADMIN_EMAIL', '')

        Usuario.objects.create_superuser(
            username=username, password=password,
            email=email, empresa=empresa,
        )
        self.stdout.write(self.style.SUCCESS(
            f'Superusuário "{username}" criado na empresa "{empresa.nome}". '
            f'TROQUE A SENHA após o primeiro acesso!'
        ))
