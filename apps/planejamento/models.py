"""
models.py — BK Planejamento Estratégico
Estrutura de dados espelhando os dataclasses do Streamlit original.
"""
from django.db import models
import json


class PlanningData(models.Model):
    """Registro único por empresa — armazena todo o planejamento em JSON."""
    slug = models.SlugField(default='bk', unique=True)
    dados = models.JSONField(default=dict, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Planejamento'
        verbose_name_plural = 'Planejamentos'

    def __str__(self):
        return f'Planejamento [{self.slug}] — {self.atualizado_em}'

    @classmethod
    def get_or_create_default(cls):
        obj, _ = cls.objects.get_or_create(
            slug='bk',
            defaults={'dados': {
                'partners': [], 'areas': [], 'swot': [], 'okrs': [], 'actions': [],
                'strategic': {
                    'visao': '', 'missao': '', 'valores': '', 'posicionamento': '',
                    'proposta_valor': '', 'publico_alvo': '', 'diferenciais': '',
                    'pilares': '', 'objetivos_estrategicos': '', 'notas': '',
                }
            }}
        )
        return obj
