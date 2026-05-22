from django.urls import path
from . import views

app_name = "planejamento"

urlpatterns = [
    path("",                              views.dashboard,          name="dashboard"),
    path("socios/",                       views.socios,             name="socios"),
    path("estrategia/",                   views.estrategia,         name="estrategia"),
    path("areas/",                        views.areas,              name="areas"),
    path("okrs/",                         views.kpis,               name="okrs"),
    path("okrs/detail/<str:nome>/",       views.kpi_detail_json,    name="okr_detail_json"),
    path("swot/",                         views.swot,               name="swot"),
    path("planos-acao/",                  views.planos_acao,        name="planos_acao"),
    path("relatorios/",                   views.relatorios,         name="relatorios"),
    path("export/json/",                  views.export_json,        name="export_json"),
    path("export/excel/",                 views.export_excel_view,  name="export_excel"),
    path("export/zip/",                   views.export_zip_view,    name="export_zip"),
    path("export/html/",                  views.export_html_view,   name="export_html"),
    path("export/word/",                  views.export_word_view,   name="export_word"),
    path("import/json/",                  views.import_json,        name="import_json"),
]
