from django.contrib.auth.models import AbstractUser
from django.db import models


class Usuario(AbstractUser):
    """Usuário customizado da aplicação."""
    groups = models.ManyToManyField(
        'auth.Group', blank=True, related_name='usuarios'
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission', blank=True, related_name='usuarios'
    )

    class Meta:
        verbose_name = 'Usuário'
        verbose_name_plural = 'Usuários'

# ATENÇÃO: AUTH_USER_MODEL deve estar em bk_plan/settings.py — não aqui.
