import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = 'Cria superusuário padrão se não existir nenhum'

    def handle(self, *args, **options):
        User = get_user_model()

        if User.objects.filter(is_superuser=True).exists():
            self.stdout.write('Admin já existe — nenhuma ação necessária.')
            return

        username = os.environ.get('ADMIN_USERNAME', 'velho')
        password = os.environ.get('ADMIN_PASSWORD', 'velhodomal1976')
        email    = os.environ.get('ADMIN_EMAIL',    '')

        User.objects.create_superuser(
            username=username,
            password=password,
            email=email,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'Superusuário "{username}" criado com sucesso!'
            )
        )
