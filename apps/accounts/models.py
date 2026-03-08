from django.contrib.auth.models import AbstractUser
from django.db import models

class Usuario(AbstractUser):
    groups = models.ManyToManyField(
        'auth.Group', blank=True, related_name='usuarios'
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission', blank=True, related_name='usuarios'
    )

    class Meta:
        verbose_name = 'Usuário'
        verbose_name_plural = 'Usuários'
AUTH_USER_MODEL = 'accounts.Usuario'