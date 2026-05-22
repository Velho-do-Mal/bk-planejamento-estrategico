from django.contrib import admin
from .models import PlanningData

@admin.register(PlanningData)
class PlanningDataAdmin(admin.ModelAdmin):
    list_display = ['slug', 'atualizado_em']
    readonly_fields = ['atualizado_em']
