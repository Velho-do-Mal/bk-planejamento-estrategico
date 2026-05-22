from django.db import models
from django.utils.text import slugify

PLANO_CHOICES = [('free', 'Free'), ('pago', 'Pago')]

PLANO_LIMITES = {
    'free': {
        'max_kpis': 1, 'planos_acao': False, 'word_export': False,
        'excel_export': False, 'json_export': False,
        'max_usuarios': 1, 'swot_editar': False,
    },
    'pago': {
        'max_kpis': None, 'planos_acao': True, 'word_export': True,
        'excel_export': True, 'json_export': True,
        'max_usuarios': None, 'swot_editar': True,
    },
}

class Empresa(models.Model):
    slug        = models.SlugField(unique=True)
    nome        = models.CharField(max_length=200)
    plano       = models.CharField(max_length=20, default='free', choices=PLANO_CHOICES)
    ativa       = models.BooleanField(default=True)
    email       = models.EmailField(blank=True)
    telefone    = models.CharField(max_length=20, blank=True)
    responsavel = models.CharField(max_length=200, blank=True)
    criada_em   = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Empresa'
        verbose_name_plural = 'Empresas'
        ordering            = ['-criada_em']

    def __str__(self):
        return f'{self.nome} ({self.plano})'

    def get_limites(self) -> dict:
        return PLANO_LIMITES.get(self.plano, PLANO_LIMITES['pago'])

    @staticmethod
    def gerar_slug(nome: str) -> str:
        base = slugify(nome)[:40] or 'empresa'
        slug, n = base, 1
        while Empresa.objects.filter(slug=slug).exists():
            slug = f'{base}-{n}'; n += 1
        return slug


class PlanningData(models.Model):
    empresa     = models.OneToOneField(Empresa, on_delete=models.CASCADE,
                                       related_name='planning', null=True, blank=True)
    slug        = models.SlugField(default='bk', unique=True)   # mantido p/ compatibilidade
    dados       = models.JSONField(default=dict, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Planejamento'
        verbose_name_plural = 'Planejamentos'

    def __str__(self):
        nome = self.empresa.nome if self.empresa else self.slug
        return f'Planejamento [{nome}] — {self.atualizado_em:%d/%m/%Y}'

    @classmethod
    def get_or_create_for(cls, empresa: 'Empresa'):
        obj, _ = cls.objects.get_or_create(
            empresa=empresa,
            defaults={
                'slug': empresa.slug,
                'dados': {
                    'partners': [], 'areas': [], 'swot': [], 's': [], 'actions': [],
                    'strategic': {
                        'visao': '', 'missao': '', 'valores': '', 'posicionamento': '',
                        'proposta_valor': '', 'publico_alvo': '', 'diferenciais': '',
                        'pilares': '', 'objetivos_estrategicos': '', 'notas': '',
                    }
                }
            }
        )
        return obj

    # ── legado (slug='bk') ─────────────────────────────────────────
    @classmethod
    def get_or_create_default(cls):
        try:
            empresa = Empresa.objects.get(slug='bk')
        except Empresa.DoesNotExist:
            empresa = Empresa.objects.create(slug='bk', nome='BK Engenharia', plano='pago', ativa=True)
        return cls.get_or_create_for(empresa)
