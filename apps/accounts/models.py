from django.contrib.auth.models import AbstractUser
from django.db import models


class Usuario(AbstractUser):
    empresa = models.ForeignKey(
        'planejamento.Empresa',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='usuarios',
        verbose_name='Empresa',
    )
    groups = models.ManyToManyField('auth.Group', blank=True, related_name='usuarios')
    user_permissions = models.ManyToManyField('auth.Permission', blank=True, related_name='usuarios')

    class Meta:
        verbose_name        = 'Usuário'
        verbose_name_plural = 'Usuários'

    def __str__(self):
        empresa = self.empresa.nome if self.empresa else '—'
        return f'{self.username} ({empresa})'
