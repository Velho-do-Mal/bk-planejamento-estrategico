"""
views.py — BK Planejamento Estratégico
Porta toda a lógica do streamlit_app.py para Django views.
"""
import json
import io
import zipfile
from datetime import date, datetime
from typing import List, Optional

import numpy as np
import pandas as pd
import plotly.graph_objs as go
import plotly.express as px

from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from .models import PlanningData


# ============================================================
# PALETA BK
# ============================================================
BK_BLUE = "#1565C0"
BK_BLUE_LIGHT = "#42A5F5"
BK_TEAL = "#00897B"
BK_GREEN = "#43A047"
BK_ORANGE = "#FB8C00"
BK_RED = "#E53935"
BK_PURPLE = "#7B1FA2"
BK_GRAY = "#546E7A"

SWOT_COLORS = {
    "Força": "#43A047",
    "Fraqueza": "#E53935",
    "Oportunidade": "#1565C0",
    "Ameaça": "#FB8C00",
}
STATUS_COLORS = {
    "Concluído": BK_GREEN,
    "Em andamento": BK_ORANGE,
    "Pendente": BK_GRAY,
    "Atrasado": BK_RED,
}


# ============================================================
# HELPERS DE DADOS
# ============================================================

def get_planning() -> dict:
    obj = PlanningData.get_or_create_default()
    dados = obj.dados or {}
    dados.setdefault("partners", [])
    dados.setdefault("areas", [])
    dados.setdefault("swot", [])
    dados.setdefault("actions", [])
    dados.setdefault("strategic", {
        "visao": "",
        "missao": "",
        "valores": "",
        "posicionamento": "",
        "proposta_valor": "",
        "publico_alvo": "",
        "diferenciais": "",
        "pilares": "",
        "objetivos_estrategicos": "",
        "notas": "",
    })
    
    # Normalizar dados antigos: migrar 'okrs' para 's' se existir
    if "okrs" in dados and dados["okrs"]:
        if "s" not in dados or not dados["s"]:
            dados["s"] = dados["okrs"]
        # Remover chave 'okrs' antiga
        del dados["okrs"]
        obj.dados = dados
        obj.save()
    
    dados.setdefault("s", [])
    
    return dados


def save_planning(dados: dict):
    obj = PlanningData.get_or_create_default()
    obj.dados = dados
    obj.save()


def _clean_text(value, default=""):
    return str(value if value is not None else default).strip()


def _normalize_partner_rows(rows: list) -> list:
    normalized = []
    for row in rows:
        nome = _clean_text(row.get("nome"))
        if not nome:
            continue
        normalized.append({
            "nome": nome,
            "cargo": _clean_text(row.get("cargo")),
            "email": _clean_text(row.get("email")),
            "telefone": _clean_text(row.get("telefone")),
            "observacoes": _clean_text(row.get("observacoes")),
        })
    return normalized


def _normalize_area_rows(rows: list) -> list:
    normalized = []
    for row in rows:
        area = _clean_text(row.get("area"))
        if not area:
            continue
        normalized.append({
            "area": area,
            "responsavel": _clean_text(row.get("responsavel")),
            "email": _clean_text(row.get("email")),
            "observacoes": _clean_text(row.get("observacoes")),
        })
    return normalized


def _group_swot_items(swot_items: list) -> dict:
    grupos = {
        "Força": [],
        "Fraqueza": [],
        "Oportunidade": [],
        "Ameaça": [],
    }
    for item in swot_items or []:
        tipo = _clean_text(item.get("tipo"))
        descricao = _clean_text(item.get("descricao"))
        prioridade = _clean_text(item.get("prioridade"), "Média")
        if tipo in grupos and descricao:
            grupos[tipo].append({
                "tipo": tipo,
                "descricao": descricao,
                "prioridade": prioridade or "Média",
            })
    return grupos


def _safe_date(s) -> Optional[date]:
    if not s:
        return None
    try:
        if isinstance(s, date):
            return s
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _ensure_okr_meses(okr: dict) -> dict:
    """Garante que o item tenha 36 meses com previsto/realizado."""
    try:
        if not isinstance(okr, dict):
            okr = {}

        meses = okr.get("meses", [])
        if not isinstance(meses, list):
            meses = []

        meses_corrigidos = []
        for i in range(36):
            if i < len(meses) and isinstance(meses[i], dict):
                mes = meses[i]
            else:
                mes = {}

            # Converter valores com tratamento de erro
            try:
                previsto = float(mes.get("previsto", 0) or 0)
            except (TypeError, ValueError):
                previsto = 0.0
            
            try:
                realizado = float(mes.get("realizado", 0) or 0)
            except (TypeError, ValueError):
                realizado = 0.0

            meses_corrigidos.append({
                "previsto": previsto,
                "realizado": realizado,
            })

        okr["meses"] = meses_corrigidos
        return okr
    except Exception as e:
        # Se algo der muito errado, retornar estrutura padrao
        import traceback
        traceback.print_exc()
        return {
            "meses": [{"previsto": 0.0, "realizado": 0.0} for _ in range(36)]
        }


def _month_labels_for_okr(okr: dict) -> List[str]:
    inicio_str = okr.get("inicio", "")
    try:
        if inicio_str:
            dt = datetime.strptime(str(inicio_str)[:7], "%Y-%m")
        else:
            dt = datetime(date.today().year, 1, 1)
    except Exception:
        dt = datetime(date.today().year, 1, 1)

    labels = []
    for i in range(36):
        m = (dt.month - 1 + i) % 12 + 1
        y = dt.year + (dt.month - 1 + i) // 12
        labels.append(f"{m:02d}/{y}")
    return labels


# ============================================================
# GRÁFICOS PLOTLY
# ============================================================

def _fig_layout(fig, title="", height=380):
    fig.update_layout(
        title=title,
        height=height,
        margin=dict(l=40, r=20, t=40 if title else 20, b=40),
        paper_bgcolor="white",
        plot_bgcolor="#F8FAFC",
        font=dict(family="Segoe UI, sans-serif", size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def fig_okr_monthly(okr: dict) -> str:
    okr = _ensure_okr_meses(okr)
    labels = _month_labels_for_okr(okr)
    prev = [float(m.get("previsto", 0)) for m in okr["meses"]]
    real = [float(m.get("realizado", 0)) for m in okr["meses"]]
    unidade = okr.get("unidade", "")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Planejado",
        x=labels,
        y=prev,
        marker_color=BK_BLUE_LIGHT,
        opacity=0.7
    ))
    fig.add_trace(go.Scatter(
        name="Realizado",
        x=labels,
        y=real,
        mode="lines+markers",
        line=dict(color=BK_GREEN, width=2.5),
        marker=dict(size=6)
    ))
    _fig_layout(fig, f"Mensal — {okr.get('nome', '')} ({unidade})", height=360)
    return fig.to_json()


def fig_okr_cumulative(okr: dict) -> str:
    okr = _ensure_okr_meses(okr)
    labels = _month_labels_for_okr(okr)
    prev = [float(m.get("previsto", 0)) for m in okr["meses"]]
    real = [float(m.get("realizado", 0)) for m in okr["meses"]]
    cum_prev = list(np.cumsum(prev))
    cum_real = list(np.cumsum(real))

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        name="Acumulado Planejado",
        x=labels,
        y=cum_prev,
        mode="lines",
        line=dict(color=BK_BLUE, dash="dash", width=2)
    ))
    fig.add_trace(go.Scatter(
        name="Acumulado Realizado",
        x=labels,
        y=cum_real,
        mode="lines+markers",
        line=dict(color=BK_GREEN, width=2.5),
        fill="tozeroy",
        fillcolor="rgba(67,160,71,0.08)"
    ))
    _fig_layout(fig, f"Acumulado — {okr.get('nome', '')}", height=320)
    return fig.to_json()


def fig_okr_gauge(okr: dict) -> str:
    okr = _ensure_okr_meses(okr)
    tp = sum(float(m.get("previsto", 0)) for m in okr["meses"])
    tr = sum(float(m.get("realizado", 0)) for m in okr["meses"])
    pct = (tr / tp * 100) if tp > 0 else 0
    color = BK_GREEN if pct >= 90 else (BK_ORANGE if pct >= 70 else BK_RED)

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=pct,
        number={"suffix": "%", "font": {"size": 22}},
        title={"text": okr.get("nome", "")[:25], "font": {"size": 11}},
        gauge={
            "axis": {"range": [0, 150], "tickwidth": 1},
            "bar": {"color": color},
            "steps": [
                {"range": [0, 70], "color": "#FEE2E2"},
                {"range": [70, 90], "color": "#FEF3C7"},
                {"range": [90, 150], "color": "#D1FAE5"},
            ],
            "threshold": {"line": {"color": BK_BLUE, "width": 3}, "value": 100},
        }
    ))
    fig.update_layout(
        height=220,
        margin=dict(l=20, r=20, t=40, b=10),
        paper_bgcolor="white",
        font=dict(family="Segoe UI"),
    )
    return fig.to_json()


def fig_swot_quadrant(swot_items: list) -> str:
    fig = go.Figure()
    quadrants = {
        "Força": (0.25, 0.75, "#D1FAE5", "#065F46"),
        "Oportunidade": (0.75, 0.75, "#DBEAFE", "#1E3A8A"),
        "Fraqueza": (0.25, 0.25, "#FEE2E2", "#991B1B"),
        "Ameaça": (0.75, 0.25, "#FEF3C7", "#92400E"),
    }

    for tipo, (cx, cy, bg, fg) in quadrants.items():
        x0 = 0 if cx < 0.5 else 0.5
        x1 = 0.5 if cx < 0.5 else 1
        y0 = 0 if cy < 0.5 else 0.5
        y1 = 0.5 if cy < 0.5 else 1
        fig.add_shape(
            type="rect",
            x0=x0, x1=x1, y0=y0, y1=y1,
            xref="paper", yref="paper",
            fillcolor=bg,
            line=dict(color="#CBD5E1", width=1)
        )
        fig.add_annotation(
            x=cx, y=cy + 0.18,
            xref="paper", yref="paper",
            text=f"<b>{tipo}</b>",
            showarrow=False,
            font=dict(size=13, color=fg),
            bgcolor=bg
        )

    for tipo, (cx, cy, bg, fg) in quadrants.items():
        items = [s for s in swot_items if s.get("tipo") == tipo]
        for i, item in enumerate(items):
            jitter_x = (i % 3 - 1) * 0.06
            jitter_y = -(i // 3) * 0.07
            fig.add_trace(go.Scatter(
                x=[cx + jitter_x],
                y=[cy - 0.05 + jitter_y],
                mode="markers+text",
                marker=dict(
                    size=14,
                    color=SWOT_COLORS.get(tipo, BK_GRAY),
                    line=dict(color="white", width=2)
                ),
                text=[item.get("prioridade", "")[:1]],
                textfont=dict(color="white", size=8),
                textposition="middle center",
                hovertext=item.get("descricao", ""),
                hoverinfo="text",
                name=tipo,
                showlegend=(i == 0),
            ))

    fig.update_layout(
        height=400,
        paper_bgcolor="white",
        xaxis=dict(showticklabels=False, showgrid=False, zeroline=False, range=[0, 1]),
        yaxis=dict(showticklabels=False, showgrid=False, zeroline=False, range=[0, 1]),
        margin=dict(l=10, r=10, t=30, b=10),
        title="Matriz SWOT",
        font=dict(family="Segoe UI"),
    )
    return fig.to_json()


def fig_actions_status(dados: dict) -> Optional[str]:
    actions = dados.get("actions", [])
    if not actions:
        return None

    counts = {}
    for a in actions:
        status = a.get("status", "Pendente")
        counts[status] = counts.get(status, 0) + 1

    fig = go.Figure(go.Pie(
        labels=list(counts.keys()),
        values=list(counts.values()),
        hole=0.5,
        marker=dict(colors=[STATUS_COLORS.get(k, BK_GRAY) for k in counts.keys()]),
        textinfo="label+percent",
    ))
    _fig_layout(fig, "Status dos Planos de Ação", height=320)
    return fig.to_json()


def fig_actions_timeline(dados: dict) -> Optional[str]:
    actions = dados.get("actions", [])
    today = date.today()
    rows = []

    for a in actions:
        d_ini = _safe_date(a.get("data_inicio")) or today
        d_fim = _safe_date(a.get("data_vencimento")) or today
        if d_ini > d_fim:
            d_fim = d_ini

        rows.append({
            "Tarefa": a.get("titulo", "")[:35],
            "Início": d_ini,
            "Fim": d_fim,
            "Status": a.get("status", "Pendente"),
            "Responsável": a.get("responsavel", ""),
        })

    if not rows:
        return None

    df = pd.DataFrame(rows).sort_values("Início")
    fig = px.timeline(
        df,
        x_start="Início",
        x_end="Fim",
        y="Tarefa",
        color="Status",
        hover_data=["Responsável"],
        color_discrete_map=STATUS_COLORS,
    )
    fig.update_yaxes(autorange="reversed")
    _fig_layout(fig, "Linha do Tempo — Planos de Ação", height=max(300, len(rows) * 35 + 80))
    return fig.to_json()


def fig_okrs_overview(dados: dict) -> Optional[str]:
    okrs = dados.get("s", [])
    if not okrs:
        return None

    names, prevs, reals, pcts = [], [], [], []
    for o in okrs:
        o = _ensure_okr_meses(o)
        tp = sum(float(m.get("previsto", 0)) for m in o["meses"])
        tr = sum(float(m.get("realizado", 0)) for m in o["meses"])
        pct = (tr / tp * 100) if tp > 0 else 0

        names.append(o.get("nome", "")[:30])
        prevs.append(tp)
        reals.append(tr)
        pcts.append(pct)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Planejado",
        x=names,
        y=prevs,
        marker_color=BK_BLUE_LIGHT,
        opacity=0.7
    ))
    fig.add_trace(go.Bar(
        name="Realizado",
        x=names,
        y=reals,
        marker_color=BK_GREEN
    ))
    fig.add_trace(go.Scatter(
        name="% Realização",
        x=names,
        y=pcts,
        mode="markers+text",
        yaxis="y2",
        marker=dict(size=10, color=BK_ORANGE),
        text=[f"{p:.0f}%" for p in pcts],
        textposition="top center"
    ))
    fig.update_layout(
        barmode="group",
        height=380,
        yaxis2=dict(overlaying="y", side="right", title="% Realização", range=[0, 160]),
        paper_bgcolor="white",
        plot_bgcolor="#F8FAFC",
        margin=dict(l=40, r=60, t=40, b=60),
        font=dict(family="Segoe UI"),
        title="Visão Geral KPIs — Planejado vs Realizado",
    )
    return fig.to_json()


# ============================================================
# EXPORTAÇÕES
# ============================================================

def export_excel(dados: dict) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        if dados.get("partners"):
            pd.DataFrame(dados["partners"]).to_excel(writer, sheet_name="Sócios_Gestores", index=False)

        if dados.get("areas"):
            pd.DataFrame(dados["areas"]).to_excel(writer, sheet_name="Áreas", index=False)

        if dados.get("swot"):
            pd.DataFrame(dados["swot"]).to_excel(writer, sheet_name="SWOT", index=False)

        if dados.get("s"):
            rows = []
            for o in dados["s"]:
                o = _ensure_okr_meses(o)
                row = {
                    "nome": o.get("nome"),
                    "area": o.get("area"),
                    "unidade": o.get("unidade"),
                    "inicio": o.get("inicio"),
                }
                for i, m in enumerate(o["meses"]):
                    row[f"M{i+1:02d}_prev"] = m.get("previsto", 0)
                    row[f"M{i+1:02d}_real"] = m.get("realizado", 0)
                rows.append(row)

            pd.DataFrame(rows).to_excel(writer, sheet_name="KPIs", index=False)

        if dados.get("actions"):
            pd.DataFrame(dados["actions"]).to_excel(writer, sheet_name="Planos_Ação", index=False)

        strategic = dados.get("strategic", {})
        pd.DataFrame([strategic]).to_excel(writer, sheet_name="Estratégia", index=False)

    return output.getvalue()


def export_csv_zip(dados: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for key, name in [
            ("partners", "socios.csv"),
            ("areas", "areas.csv"),
            ("swot", "swot.csv"),
            ("actions", "planos_acao.csv"),
        ]:
            if dados.get(key):
                df = pd.DataFrame(dados[key])
                zf.writestr(name, df.to_csv(index=False))
    return buf.getvalue()


def build_html_report(dados: dict) -> str:
    today = date.today().strftime("%d/%m/%Y")
    strategic = dados.get("strategic", {})
    okrs = dados.get("s", [])
    actions = dados.get("actions", [])
    swot = dados.get("swot", [])

    total_prev = sum(float(m.get("previsto", 0)) for o in okrs for m in _ensure_okr_meses(o)["meses"])
    total_real = sum(float(m.get("realizado", 0)) for o in okrs for m in _ensure_okr_meses(o)["meses"])
    pct_geral = (total_real / total_prev * 100) if total_prev > 0 else 0
    n_concluidos = sum(1 for a in actions if a.get("status") == "Concluído")
    n_atrasados = sum(
        1 for a in actions
        if a.get("status") != "Concluído"
        and _safe_date(a.get("data_vencimento"))
        and _safe_date(a.get("data_vencimento")) < date.today()
    )

    okr_rows = ""
    for o in okrs:
        o = _ensure_okr_meses(o)
        tp = sum(float(m.get("previsto", 0)) for m in o["meses"])
        tr = sum(float(m.get("realizado", 0)) for m in o["meses"])
        pct = (tr / tp * 100) if tp > 0 else 0
        cor = "#059669" if pct >= 95 else ("#D97706" if pct >= 70 else "#DC2626")
        semaforo = "🟢" if pct >= 95 else ("🟡" if pct >= 70 else "🔴")
        okr_rows += f"""<tr>
            <td>{semaforo}</td><td>{o.get('nome','')}</td><td>{o.get('area','')}</td>
            <td>{o.get('unidade','')}</td>
            <td style="color:{cor};font-weight:700">{pct:.1f}%</td>
            <td>{sum(1 for m in o['meses'] if float(m.get('realizado',0)) != 0)}/36</td>
        </tr>"""

    swot_rows = ""
    for item in swot:
        cor = SWOT_COLORS.get(item.get("tipo", ""), BK_GRAY)
        swot_rows += f"""<tr>
            <td style="color:{cor};font-weight:600">{item.get('tipo','')}</td>
            <td>{item.get('descricao','')}</td>
            <td>{item.get('prioridade','')}</td>
        </tr>"""

    action_rows = ""
    for a in actions:
        sc = STATUS_COLORS.get(a.get("status", ""), BK_GRAY)
        action_rows += f"""<tr>
            <td>{a.get('titulo','')}</td><td>{a.get('area','')}</td>
            <td>{a.get('responsavel','')}</td><td>{a.get('data_vencimento','')}</td>
            <td style="color:{sc};font-weight:600">{a.get('status','')}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>Relatório Planejamento Estratégico — BK Engenharia</title>
<style>
  body {{ font-family: 'Segoe UI', sans-serif; background: #F0F4F8; margin: 0; padding: 20px; color: #1a202c; }}
  .hero {{ background: linear-gradient(135deg, #1565C0, #00897B); color: white; padding: 32px; border-radius: 12px; margin-bottom: 24px; }}
  .hero h1 {{ margin: 0; font-size: 26px; }} .hero p {{ margin: 6px 0 0; opacity: .85; }}
  .okr-row {{ display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }}
  .okr {{ background: white; border-radius: 10px; padding: 18px 24px; text-align: center;
          box-shadow: 0 2px 8px rgba(0,0,0,.07); border-top: 3px solid #1565C0; min-width: 130px; flex:1; }}
  .okr .val {{ font-size: 30px; font-weight: 700; color: #1565C0; }}
  .okr .lbl {{ font-size: 11px; color: #64748B; text-transform: uppercase; letter-spacing: .5px; margin-top: 4px; }}
  .card {{ background: white; border-radius: 10px; padding: 20px 24px; margin-bottom: 20px;
           box-shadow: 0 2px 8px rgba(0,0,0,.06); }}
  .card h2 {{ font-size: 15px; color: #1565C0; border-bottom: 2px solid #E3F2FD; padding-bottom: 8px; margin-top: 0; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ background: #1565C0; color: white; padding: 8px 10px; text-align: left; }}
  td {{ padding: 7px 10px; border-bottom: 1px solid #E2E8F0; }}
  tr:nth-child(even) td {{ background: #F8FAFC; }}
  .field-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
  .field strong {{ display: block; font-size: 11px; color: #64748B; text-transform: uppercase; letter-spacing: .4px; margin-bottom: 4px; }}
  .field span {{ font-size: 13px; }}
  .footer {{ text-align: center; color: #94A3B8; font-size: 12px; margin-top: 32px; }}
</style>
</head>
<body>
<div class="hero">
  <h1>📊 Planejamento Estratégico — BK Engenharia e Tecnologia</h1>
  <p>Gerado em {today} &nbsp;|&nbsp; Horizonte: 36 meses</p>
</div>

<div class="okr-row">
  <div class="okr"><div class="val">{len(okrs)}</div><div class="lbl">KPIs</div></div>
  <div class="okr"><div class="val" style="color:{'#059669' if pct_geral>=90 else ('#D97706' if pct_geral>=70 else '#DC2626')}">{pct_geral:.1f}%</div><div class="lbl">Realização Geral</div></div>
  <div class="okr"><div class="val">{len(actions)}</div><div class="lbl">Planos de Ação</div></div>
  <div class="okr"><div class="val" style="color:#059669">{n_concluidos}</div><div class="lbl">Concluídos</div></div>
  <div class="okr"><div class="val" style="color:#DC2626">{n_atrasados}</div><div class="lbl">Atrasados</div></div>
</div>

<div class="card">
  <h2>🧭 Norte Estratégico</h2>
  <div class="field-grid">
    <div class="field"><strong>Visão</strong><span>{strategic.get('visao') or '—'}</span></div>
    <div class="field"><strong>Missão</strong><span>{strategic.get('missao') or '—'}</span></div>
    <div class="field"><strong>Valores</strong><span>{strategic.get('valores') or '—'}</span></div>
    <div class="field"><strong>Posicionamento</strong><span>{strategic.get('posicionamento') or '—'}</span></div>
    <div class="field"><strong>Proposta de Valor</strong><span>{strategic.get('proposta_valor') or '—'}</span></div>
    <div class="field"><strong>Público-Alvo</strong><span>{strategic.get('publico_alvo') or '—'}</span></div>
    <div class="field"><strong>Diferenciais</strong><span>{strategic.get('diferenciais') or '—'}</span></div>
    <div class="field"><strong>Pilares</strong><span>{strategic.get('pilares') or '—'}</span></div>
  </div>
</div>

{'<div class="card"><h2>📈 KPIs — Saúde Geral</h2><table><thead><tr><th></th><th>Nome</th><th>Área</th><th>Unidade</th><th>% Realização</th><th>Meses Preenchidos</th></tr></thead><tbody>' + okr_rows + '</tbody></table></div>' if okrs else ''}

{'<div class="card"><h2>⚖️ Análise SWOT</h2><table><thead><tr><th>Tipo</th><th>Descrição</th><th>Prioridade</th></tr></thead><tbody>' + swot_rows + '</tbody></table></div>' if swot else ''}

{'<div class="card"><h2>✅ Planos de Ação</h2><table><thead><tr><th>Título</th><th>Área</th><th>Responsável</th><th>Vencimento</th><th>Status</th></tr></thead><tbody>' + action_rows + '</tbody></table></div>' if actions else ''}

<div class="footer">BK Engenharia e Tecnologia &nbsp;|&nbsp; Planejamento Estratégico &nbsp;|&nbsp; {today}</div>
</body></html>"""
    return html


# ============================================================
# VIEWS DJANGO
# ============================================================

@login_required
def dashboard(request):
    dados = get_planning()
    today = date.today()

    okrs = dados.get("s", [])
    actions = dados.get("actions", [])

    total_prev = sum(float(m.get("previsto", 0)) for o in okrs for m in _ensure_okr_meses(o)["meses"])
    total_real = sum(float(m.get("realizado", 0)) for o in okrs for m in _ensure_okr_meses(o)["meses"])
    pct_real = (total_real / total_prev * 100) if total_prev > 0 else 0

    n_atrasados = sum(
        1 for a in actions
        if a.get("status") != "Concluído"
        and _safe_date(a.get("data_vencimento"))
        and _safe_date(a.get("data_vencimento")) < today
    )
    n_concluidos = sum(1 for a in actions if a.get("status") == "Concluído")
    n_andamento = sum(1 for a in actions if a.get("status") == "Em andamento")

    fig_overview_json = fig_okrs_overview(dados)
    fig_status_json = fig_actions_status(dados)
    fig_swot_json = fig_swot_quadrant(dados.get("swot", [])) if dados.get("swot") else None
    gauges = [fig_okr_gauge(o) for o in okrs[:4]]

    atrasados = []
    for a in actions:
        dv = _safe_date(a.get("data_vencimento"))
        if a.get("status") != "Concluído" and dv and dv < today:
            dias = (today - dv).days
            atrasados.append({**a, "dias_atraso": dias})
    atrasados.sort(key=lambda x: x["dias_atraso"], reverse=True)

    return render(request, "planejamento/dashboard.html", {
        "dados": dados,
        "n_okrs": len(okrs),
        "n_s": len(okrs),
        "pct_real": round(pct_real, 1),
        "pct_real_color": BK_GREEN if pct_real >= 90 else (BK_ORANGE if pct_real >= 70 else BK_RED),
        "n_actions": len(actions),
        "n_concluidos": n_concluidos,
        "n_atrasados": n_atrasados,
        "n_andamento": n_andamento,
        "fig_overview_json": fig_overview_json,
        "fig_status_json": fig_status_json,
        "fig_swot_json": fig_swot_json,
        "gauges_json": gauges,
        "atrasados": atrasados[:10],
    })


@login_required
def socios(request):
    dados = get_planning()
    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add":
            nome = request.POST.get("nome", "").strip()
            if nome:
                dados["partners"].append({
                    "nome": nome,
                    "cargo": request.POST.get("cargo", ""),
                    "email": request.POST.get("email", ""),
                    "telefone": request.POST.get("telefone", ""),
                    "observacoes": request.POST.get("observacoes", ""),
                })
                save_planning(dados)
                messages.success(request, "Sócio/Gestor adicionado!")
            else:
                messages.warning(request, "Informe o nome.")

        elif action == "delete":
            idx = int(request.POST.get("idx", -1))
            if 0 <= idx < len(dados["partners"]):
                dados["partners"].pop(idx)
                save_planning(dados)
                messages.success(request, "Excluído.")

        elif action == "save_table":
            rows_json = request.POST.get("rows_json", "[]")
            try:
                rows = json.loads(rows_json)
                dados["partners"] = _normalize_partner_rows(rows)
                save_planning(dados)
                messages.success(request, "Sócios/Gestores salvos!")
            except Exception as e:
                messages.error(request, f"Erro: {e}")

        return redirect("planejamento:socios")

    return render(request, "planejamento/socios.html", {"dados": dados})


@login_required
def estrategia(request):
    dados = get_planning()
    if request.method == "POST":
        fields = [
            "visao", "missao", "valores", "posicionamento",
            "proposta_valor", "publico_alvo", "diferenciais",
            "pilares", "objetivos_estrategicos", "notas"
        ]
        for f in fields:
            dados["strategic"][f] = request.POST.get(f, "")
        save_planning(dados)
        messages.success(request, "Estratégia salva!")
        return redirect("planejamento:estrategia")

    return render(request, "planejamento/estrategia.html", {"dados": dados})


@login_required
def areas(request):
    dados = get_planning()
    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add":
            area = request.POST.get("area", "").strip()
            if area:
                dados["areas"].append({
                    "area": area,
                    "responsavel": request.POST.get("responsavel", ""),
                    "email": request.POST.get("email", ""),
                    "observacoes": request.POST.get("observacoes", ""),
                })
                save_planning(dados)
                messages.success(request, "Área adicionada!")
            else:
                messages.warning(request, "Informe a área.")

        elif action == "delete":
            idx = int(request.POST.get("idx", -1))
            if 0 <= idx < len(dados["areas"]):
                dados["areas"].pop(idx)
                save_planning(dados)
                messages.success(request, "Excluído.")

        elif action == "save_table":
            rows_json = request.POST.get("rows_json", "[]")
            try:
                rows = json.loads(rows_json)
                dados["areas"] = _normalize_area_rows(rows)
                save_planning(dados)
                messages.success(request, "Áreas salvas!")
            except Exception as e:
                messages.error(request, f"Erro: {e}")

        return redirect("planejamento:areas")

    return render(request, "planejamento/areas.html", {"dados": dados})


@login_required
def swot(request):
    dados = get_planning()

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save_table":
            rows_json = request.POST.get("rows_json", "[]")
            try:
                rows = json.loads(rows_json)
                dados["swot"] = [
                    {
                        "tipo": _clean_text(r.get("tipo")),
                        "descricao": _clean_text(r.get("descricao")),
                        "prioridade": _clean_text(r.get("prioridade"), "Média") or "Média",
                    }
                    for r in rows
                    if _clean_text(r.get("descricao")) and not r.get("excluir", False)
                ]
                save_planning(dados)
                messages.success(request, "SWOT salva!")
            except Exception as e:
                messages.error(request, f"Erro: {e}")

        return redirect("planejamento:swot")

    fig_swot_json = fig_swot_quadrant(dados.get("swot", [])) if dados.get("swot") else None
    swot_groups = _group_swot_items(dados.get("swot", []))

    return render(request, "planejamento/swot.html", {
        "dados": dados,
        "fig_swot_json": fig_swot_json,
        "swot_groups": swot_groups,
        "tipos": ["Força", "Fraqueza", "Oportunidade", "Ameaça"],
        "prioridades": ["Alta", "Média", "Baixa"],
    })


@login_required
def s(request):
    dados = get_planning()
    dados.setdefault("s", [])
    dados["s"] = [_ensure_okr_meses(o) for o in dados["s"]]

    unidade_opts = ["R$", "%", "un", "clientes", "projetos", "h", "dias", "índice"]
    month_cols = [f"M{i:02d}" for i in range(1, 37)]

    if request.method == "POST":
        action = request.POST.get("action", "").strip()

        if action == "save_meta":
            rows_json = request.POST.get("rows_json", "[]")
            try:
                rows = json.loads(rows_json)
                antigos = [_ensure_okr_meses(dict(o)) for o in dados.get("s", [])]
                novos = []

                for idx, row in enumerate(rows):
                    if row.get("excluir"):
                        continue

                    nome = _clean_text(row.get("nome"))
                    if not nome:
                        continue

                    existente = antigos[idx] if idx < len(antigos) else None
                    meses = existente.get("meses", []) if existente else []
                    while len(meses) < 36:
                        meses.append({"previsto": 0.0, "realizado": 0.0})

                    novos.append({
                        "nome": nome,
                        "area": _clean_text(row.get("area")),
                        "unidade": _clean_text(row.get("unidade"), "un"),
                        "descricao": _clean_text(row.get("descricao")),
                        "inicio": _clean_text(row.get("inicio")),
                        "meses": meses[:36],
                    })

                dados["s"] = novos
                save_planning(dados)
                messages.success(request, "KPIs salvos com sucesso.")
            except Exception as e:
                messages.error(request, f"Erro ao salvar KPIs: {e}")

            return redirect("planejamento:okrs")

        elif action == "save_previsto":
            rows_json = request.POST.get("rows_json", "[]")
            try:
                rows = json.loads(rows_json)
                if not isinstance(rows, list):
                    raise ValueError("rows_json deve ser uma lista")

                s_list = dados.get("s", [])
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    try:
                        idx = int(row.get("idx", -1))
                    except (TypeError, ValueError):
                        continue
                    if idx < 0 or idx >= len(s_list):
                        continue
                    okr = s_list[idx]
                    if not isinstance(okr, dict):
                        continue
                    # Garantir 36 meses sem resetar realizado
                    meses = okr.setdefault("meses", [])
                    while len(meses) < 36:
                        meses.append({"previsto": 0.0, "realizado": 0.0})
                    for i in range(36):
                        key = f"M{i+1:02d}"
                        if key in row:
                            try:
                                meses[i]["previsto"] = float(row[key] or 0)
                            except (TypeError, ValueError):
                                pass

                save_planning(dados)
                messages.success(request, "Planejado salvo com sucesso.")
            except Exception as e:
                import traceback
                traceback.print_exc()
                messages.error(request, f"Erro ao salvar planejado: {str(e)}")

            return redirect("planejamento:okrs")

        elif action == "save_realizado":
            rows_json = request.POST.get("rows_json", "[]")
            try:
                rows = json.loads(rows_json)
                if not isinstance(rows, list):
                    raise ValueError("rows_json deve ser uma lista")

                s_list = dados.get("s", [])
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    try:
                        idx = int(row.get("idx", -1))
                    except (TypeError, ValueError):
                        continue
                    if idx < 0 or idx >= len(s_list):
                        continue
                    okr = s_list[idx]
                    if not isinstance(okr, dict):
                        continue
                    # Garantir 36 meses sem resetar previsto
                    meses = okr.setdefault("meses", [])
                    while len(meses) < 36:
                        meses.append({"previsto": 0.0, "realizado": 0.0})
                    for i in range(36):
                        key = f"M{i+1:02d}"
                        if key in row:
                            try:
                                meses[i]["realizado"] = float(row[key] or 0)
                            except (TypeError, ValueError):
                                pass

                save_planning(dados)
                messages.success(request, "Realizado salvo com sucesso.")
            except Exception as e:
                import traceback
                traceback.print_exc()
                messages.error(request, f"Erro ao salvar realizado: {str(e)}")

            return redirect("planejamento:okrs")

    s_list = [_ensure_okr_meses(dict(o)) for o in dados.get("s", [])]

    context = {
        "dados": dados,
        "s_list": s_list,
        "okrs_list": s_list,
        "okrs_list": s_list,
        "unidade_opts": unidade_opts,
        "month_cols": month_cols,
        "fig_overview_json": fig_okrs_overview(dados),
    }
    return render(request, "planejamento/okrs.html", context)


@login_required
def _detail_json(request, nome):
    dados = get_planning()
    okrs = dados.get("s", [])

    okr = None
    for item in okrs:
        if str(item.get("nome", "")).strip() == str(nome).strip():
            okr = _ensure_okr_meses(item)
            break

    if not okr:
        return JsonResponse({"error": "KPI não encontrada."}, status=404)

    tp = sum(float(m.get("previsto", 0) or 0) for m in okr["meses"])
    tr = sum(float(m.get("realizado", 0) or 0) for m in okr["meses"])
    pct = round((tr / tp * 100), 1) if tp > 0 else 0.0

    labels = _month_labels_for_okr(okr)
    table = []

    for i, mes in enumerate(okr["meses"]):
        prev = float(mes.get("previsto", 0) or 0)
        real = float(mes.get("realizado", 0) or 0)
        diff = real - prev

        if real >= prev and prev > 0:
            status = "Acima/atingido"
        elif real > 0 and real < prev:
            status = "Abaixo"
        else:
            status = "Sem realização"

        table.append({
            "mes": labels[i],
            "prev": prev,
            "real": real,
            "diff": diff,
            "status": status,
        })

    payload = {
        "nome": okr.get("nome", ""),
        "unidade": okr.get("unidade", ""),
        "tp": tp,
        "tr": tr,
        "pct": pct,
        "fig_gauge": fig_okr_gauge(okr),
        "fig_monthly": fig_okr_monthly(okr),
        "fig_cumulative": fig_okr_cumulative(okr),
        "table": table,
    }
    return JsonResponse(payload)


@login_required
def planos_acao(request):
    dados = get_planning()
    today = date.today()

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add":
            titulo = request.POST.get("titulo", "").strip()
            if not titulo:
                messages.warning(request, "Informe o título.")
            else:
                dados["actions"].append({
                    "titulo": titulo,
                    "area": request.POST.get("area", ""),
                    "responsavel": request.POST.get("responsavel", ""),
                    "okr": request.POST.get("okr", ""),
                    "descricao": request.POST.get("descricao", ""),
                    "data_inicio": request.POST.get("data_inicio", ""),
                    "data_vencimento": request.POST.get("data_vencimento", ""),
                    "status": request.POST.get("status", "Pendente"),
                    "observacoes": request.POST.get("observacoes", ""),
                    "como_fazer": request.POST.get("como_fazer", ""),
                })
                save_planning(dados)
                messages.success(request, f'Plano "{titulo}" adicionado!')

        elif action == "save_table":
            rows_json = request.POST.get("rows_json", "[]")
            try:
                rows = json.loads(rows_json)
                dados["actions"] = [
                    r for r in rows
                    if r.get("titulo", "").strip() and not r.get("excluir", False)
                ]
                save_planning(dados)
                messages.success(request, "Planos salvos!")
            except Exception as e:
                messages.error(request, f"Erro: {e}")

        return redirect("planejamento:planos_acao")

    n_total = len(dados["actions"])
    n_concluidos = sum(1 for a in dados["actions"] if a.get("status") == "Concluído")
    n_andamento = sum(1 for a in dados["actions"] if a.get("status") == "Em andamento")
    n_atrasados = sum(
        1 for a in dados["actions"]
        if a.get("status") != "Concluído"
        and _safe_date(a.get("data_vencimento"))
        and _safe_date(a.get("data_vencimento")) < today
    )

    fig_status = fig_actions_status(dados)
    fig_timeline = fig_actions_timeline(dados)

    fig_resp_json = None
    if dados["actions"]:
        resp_atraso = {}
        for a in dados["actions"]:
            dv = _safe_date(a.get("data_vencimento"))
            if dv and a.get("status") != "Concluído" and dv < today:
                dias = (today - dv).days
                r = a.get("responsavel", "N/A")
                resp_atraso[r] = resp_atraso.get(r, 0) + dias

        if resp_atraso:
            df_r = pd.DataFrame(list(resp_atraso.items()), columns=["Responsável", "Atraso"])
            fig_r = px.bar(
                df_r,
                x="Responsável",
                y="Atraso",
                title="Atraso total por Responsável (dias)",
                color="Atraso",
                color_continuous_scale=[BK_ORANGE, BK_RED]
            )
            _fig_layout(fig_r, height=320)
            fig_resp_json = fig_r.to_json()

    return render(request, "planejamento/planos_acao.html", {
        "dados": dados,
        "today": today.isoformat(),
        "n_total": n_total,
        "n_concluidos": n_concluidos,
        "n_andamento": n_andamento,
        "n_atrasados": n_atrasados,
        "fig_status_json": fig_status,
        "fig_timeline_json": fig_timeline,
        "fig_resp_json": fig_resp_json,
        "status_opts": ["Pendente", "Em andamento", "Concluído"],
    })


@login_required
def relatorios(request):
    dados = get_planning()
    today = date.today()
    okrs = dados.get("s", [])
    actions = dados.get("actions", [])
    swot = dados.get("swot", [])

    n_atrasados = sum(
        1 for a in actions
        if a.get("status") != "Concluído"
        and _safe_date(a.get("data_vencimento"))
        and _safe_date(a.get("data_vencimento")) < today
    )
    n_concluidos = sum(1 for a in actions if a.get("status") == "Concluído")

    saude = []
    for o in okrs:
        o = _ensure_okr_meses(o)
        tp = sum(float(m.get("previsto", 0)) for m in o["meses"])
        tr = sum(float(m.get("realizado", 0)) for m in o["meses"])
        pct = (tr / tp * 100) if tp > 0 else 0
        filled = sum(1 for m in o["meses"] if float(m.get("realizado", 0)) != 0)
        semaforo = "🟢" if pct >= 95 else ("🟡" if pct >= 70 else "🔴")
        color = BK_GREEN if pct >= 95 else (BK_ORANGE if pct >= 70 else BK_RED)
        saude.append({
            "semaforo": semaforo,
            "nome": o.get("nome"),
            "area": o.get("area"),
            "unidade": o.get("unidade"),
            "pct": round(pct, 1),
            "filled": filled,
            "color": color,
        })

    recs = []
    threats = [s for s in swot if s.get("tipo") == "Ameaça" and s.get("prioridade") == "Alta"]
    opps = [s for s in swot if s.get("tipo") == "Oportunidade" and s.get("prioridade") == "Alta"]
    weaknesses = [s for s in swot if s.get("tipo") == "Fraqueza" and s.get("prioridade") == "Alta"]

    if threats:
        recs.append(f"🔴 {len(threats)} Ameaça(s) Alta — crie planos de mitigação com responsável e prazo.")
    if opps:
        recs.append(f"🔵 {len(opps)} Oportunidade(s) Alta — transforme em 1–2 OKRs por pilar estratégico.")
    if weaknesses:
        recs.append(f"🟡 {len(weaknesses)} Fraqueza(s) Alta — endereçar com planos de ação de curto prazo.")
    if n_atrasados:
        recs.append(f"⚠️ {n_atrasados} plano(s) atrasado(s) — priorize replanejamento: escopo, capacidade, nova data.")
    if okrs:
        recs.append("📅 Estabeleça revisão mensal do realizado e revisão trimestral dos OKRs e prioridades.")

    low_fill = [o["nome"] for o in okrs if sum(1 for m in _ensure_okr_meses(o)["meses"] if m.get("realizado", 0) != 0) < 3]
    if low_fill:
        recs.append(f"📊 KPIs com pouco histórico: {', '.join(low_fill[:3])} — preencha o realizado mensalmente.")
    if not recs:
        recs.append("✅ Preencha Visão/Missão, SWOT e OKRs para gerar recomendações automáticas.")

    return render(request, "planejamento/relatorios.html", {
        "dados": dados,
        "saude": saude,
        "_saude": saude,
        "recs": recs,
        "n_concluidos": n_concluidos,
        "n_atrasados": n_atrasados,
    })


# ============================================================
# EXPORTS
# ============================================================

@login_required
def export_json(request):
    dados = get_planning()
    content = json.dumps(dados, ensure_ascii=False, indent=2)
    resp = HttpResponse(content, content_type="application/json")
    resp["Content-Disposition"] = 'attachment; filename="planejamento_export.json"'
    return resp


@login_required
def export_excel_view(request):
    dados = get_planning()
    xlsx = export_excel(dados)
    resp = HttpResponse(
        xlsx,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    resp["Content-Disposition"] = 'attachment; filename="planejamento_completo.xlsx"'
    return resp


@login_required
def export_zip_view(request):
    dados = get_planning()
    z = export_csv_zip(dados)
    resp = HttpResponse(z, content_type="application/zip")
    resp["Content-Disposition"] = 'attachment; filename="planning_csvs.zip"'
    return resp


@login_required
def export_html_view(request):
    dados = get_planning()
    html = build_html_report(dados)
    resp = HttpResponse(html, content_type="text/html; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="relatorio_planejamento.html"'
    return resp


@login_required
def import_json(request):
    if request.method == "POST" and request.FILES.get("json_file"):
        try:
            content = request.FILES["json_file"].read().decode("utf-8")
            dados = json.loads(content)
            save_planning(dados)
            messages.success(request, "JSON importado e salvo!")
        except Exception as e:
            messages.error(request, f"Erro ao importar: {e}")
    return redirect("planejamento:dashboard")


# Compatibilidade com nomes antigos
okrs = s
okr_detail_json = _detail_json
fig_s_overview = fig_okrs_overview
fig__gauge = fig_okr_gauge
fig__monthly = fig_okr_monthly
fig__cumulative = fig_okr_cumulative
_ensure__meses = _ensure_okr_meses
_month_labels_for_ = _month_labels_for_okr
