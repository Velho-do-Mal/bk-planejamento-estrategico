"""
views.py — BK Planejamento Estratégico (Multi-Tenant)
Cada usuário pertence a uma Empresa. Todos os dados são isolados por empresa.
"""
import copy, io, json, zipfile
from datetime import date, datetime
from typing import List, Optional

import numpy as np
import pandas as pd
import plotly.graph_objs as go
import plotly.express as px

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .models import Empresa, PlanningData, PLANO_LIMITES

# ─── Paleta ──────────────────────────────────────────────────────────────────
BK_BLUE       = "#1565C0"
BK_BLUE_LIGHT = "#42A5F5"
BK_TEAL       = "#00897B"
BK_GREEN      = "#43A047"
BK_ORANGE     = "#FB8C00"
BK_RED        = "#E53935"
BK_GRAY       = "#546E7A"

SWOT_COLORS = {
    "Força": "#43A047", "Fraqueza": "#E53935",
    "Oportunidade": "#1565C0", "Ameaça": "#FB8C00",
}
STATUS_COLORS = {
    "Concluído": BK_GREEN, "Em andamento": BK_ORANGE,
    "Pendente": BK_GRAY, "Atrasado": BK_RED,
}

# ─── Helpers multi-tenant ────────────────────────────────────────────────────

def _get_empresa(request) -> Empresa:
    """Retorna a empresa do usuário logado. Superuser sem empresa → BK padrão."""
    if hasattr(request.user, 'empresa') and request.user.empresa:
        return request.user.empresa
    empresa, _ = Empresa.objects.get_or_create(
        slug='bk', defaults={'nome': 'BK Engenharia', 'plano': 'pago'}
    )
    return empresa


def get_planning(empresa: Empresa) -> dict:
    obj  = PlanningData.get_or_create_for(empresa)
    dados = obj.dados or {}
    dados.setdefault("partners", [])
    dados.setdefault("areas",    [])
    dados.setdefault("swot",     [])
    dados.setdefault("actions",  [])
    dados.setdefault("strategic", {
        "visao": "", "missao": "", "valores": "", "posicionamento": "",
        "proposta_valor": "", "publico_alvo": "", "diferenciais": "",
        "pilares": "", "objetivos_estrategicos": "", "notas": "",
    })
    if "okrs" in dados and dados["okrs"]:
        if "s" not in dados or not dados["s"]:
            dados["s"] = dados.pop("okrs")
        else:
            del dados["okrs"]
    dados.setdefault("s", [])
    return dados


def save_planning(dados: dict, empresa: Empresa):
    copia   = copy.deepcopy(dados)
    updated = PlanningData.objects.filter(empresa=empresa).update(dados=copia)
    if not updated:
        PlanningData.objects.create(empresa=empresa, slug=empresa.slug, dados=copia)


def get_plano_info(empresa: Empresa) -> dict:
    return {"plano": empresa.plano, "limites": empresa.get_limites(), "empresa": empresa}


# ─── Helpers gerais ──────────────────────────────────────────────────────────

def _clean_text(value, default=""):
    return str(value if value is not None else default).strip()

def _safe_date(s) -> Optional[date]:
    if not s: return None
    try:
        return s if isinstance(s, date) else datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except Exception:
        return None

def _ensure_okr_meses(okr: dict) -> dict:
    try:
        meses = okr.get("meses", []) if isinstance(okr, dict) else []
        if not isinstance(meses, list): meses = []
        mc = []
        for i in range(36):
            mes = meses[i] if i < len(meses) and isinstance(meses[i], dict) else {}
            try:    p = float(mes.get("previsto",  0) or 0)
            except: p = 0.0
            try:    r = float(mes.get("realizado", 0) or 0)
            except: r = 0.0
            mc.append({"previsto": p, "realizado": r})
        okr["meses"] = mc
        return okr
    except Exception:
        return {"meses": [{"previsto": 0.0, "realizado": 0.0} for _ in range(36)]}

def _month_labels_for_okr(okr: dict) -> List[str]:
    try:
        dt = datetime.strptime(str(okr.get("inicio",""))[:7], "%Y-%m") if okr.get("inicio") else datetime(date.today().year, 1, 1)
    except Exception:
        dt = datetime(date.today().year, 1, 1)
    return [f"{(dt.month-1+i)%12+1:02d}/{dt.year+(dt.month-1+i)//12}" for i in range(36)]

def _normalize_partner_rows(rows):
    return [{"nome": _clean_text(r.get("nome")), "cargo": _clean_text(r.get("cargo")),
             "email": _clean_text(r.get("email")), "telefone": _clean_text(r.get("telefone")),
             "observacoes": _clean_text(r.get("observacoes"))}
            for r in rows if not r.get("excluir") and _clean_text(r.get("nome"))]

def _normalize_area_rows(rows):
    return [{"area": _clean_text(r.get("area")), "responsavel": _clean_text(r.get("responsavel")),
             "email": _clean_text(r.get("email")), "observacoes": _clean_text(r.get("observacoes"))}
            for r in rows if not r.get("excluir") and _clean_text(r.get("area"))]

def _group_swot_items(swot_items):
    g = {"Força": [], "Fraqueza": [], "Oportunidade": [], "Ameaça": []}
    for item in (swot_items or []):
        t = _clean_text(item.get("tipo"))
        d = _clean_text(item.get("descricao"))
        if t in g and d:
            g[t].append({"tipo": t, "descricao": d, "prioridade": _clean_text(item.get("prioridade"),"Média") or "Média"})
    return g

# ─── Gráficos ────────────────────────────────────────────────────────────────

def _fig_layout(fig, title="", height=380):
    fig.update_layout(title=title, height=height, margin=dict(l=40,r=20,t=40 if title else 20,b=40),
                      paper_bgcolor="white", plot_bgcolor="#F8FAFC",
                      font=dict(family="Segoe UI",size=12),
                      legend=dict(orientation="h",yanchor="bottom",y=1.02,xanchor="right",x=1))
    return fig

def fig_okr_monthly(okr):
    okr = _ensure_okr_meses(okr); labels = _month_labels_for_okr(okr)
    prev = [float(m.get("previsto",0)) for m in okr["meses"]]
    real = [float(m.get("realizado",0)) for m in okr["meses"]]
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Planejado", x=labels, y=prev, marker_color=BK_BLUE_LIGHT, opacity=0.7))
    fig.add_trace(go.Scatter(name="Realizado", x=labels, y=real, mode="lines+markers",
                             line=dict(color=BK_GREEN, width=2.5), marker=dict(size=6)))
    _fig_layout(fig, f"Mensal — {okr.get('nome','')} ({okr.get('unidade','')})", 360)
    return fig.to_json()

def fig_okr_cumulative(okr):
    okr = _ensure_okr_meses(okr); labels = _month_labels_for_okr(okr)
    cp = list(np.cumsum([float(m.get("previsto",0)) for m in okr["meses"]]))
    cr = list(np.cumsum([float(m.get("realizado",0)) for m in okr["meses"]]))
    fig = go.Figure()
    fig.add_trace(go.Scatter(name="Acum. Planejado", x=labels, y=cp, mode="lines",
                             line=dict(color=BK_BLUE, dash="dash", width=2)))
    fig.add_trace(go.Scatter(name="Acum. Realizado", x=labels, y=cr, mode="lines+markers",
                             line=dict(color=BK_GREEN, width=2.5),
                             fill="tozeroy", fillcolor="rgba(67,160,71,0.08)"))
    _fig_layout(fig, f"Acumulado — {okr.get('nome','')}", 320)
    return fig.to_json()

def fig_okr_gauge(okr):
    okr = _ensure_okr_meses(okr)
    tp = sum(float(m.get("previsto",0)) for m in okr["meses"])
    tr = sum(float(m.get("realizado",0)) for m in okr["meses"])
    pct = (tr/tp*100) if tp > 0 else 0
    color = BK_GREEN if pct >= 90 else (BK_ORANGE if pct >= 70 else BK_RED)
    fig = go.Figure(go.Indicator(mode="gauge+number", value=pct,
        number={"suffix":"%","font":{"size":22}},
        title={"text":okr.get("nome","")[:25],"font":{"size":11}},
        gauge={"axis":{"range":[0,150]},"bar":{"color":color},
               "steps":[{"range":[0,70],"color":"#FEE2E2"},{"range":[70,90],"color":"#FEF3C7"},{"range":[90,150],"color":"#D1FAE5"}],
               "threshold":{"line":{"color":BK_BLUE,"width":3},"value":100}}))
    fig.update_layout(height=220, margin=dict(l=20,r=20,t=40,b=10), paper_bgcolor="white")
    return fig.to_json()

def fig_swot_quadrant(swot_items):
    fig = go.Figure()
    quadrants = {"Força":(0.25,0.75,"#D1FAE5"),"Oportunidade":(0.75,0.75,"#DBEAFE"),
                 "Fraqueza":(0.25,0.25,"#FEE2E2"),"Ameaça":(0.75,0.25,"#FEF3C7")}
    for tipo,(cx,cy,bg) in quadrants.items():
        fig.add_shape(type="rect",x0=0 if cx<0.5 else 0.5,x1=0.5 if cx<0.5 else 1,
                      y0=0 if cy<0.5 else 0.5,y1=0.5 if cy<0.5 else 1,
                      xref="paper",yref="paper",fillcolor=bg,line=dict(color="#CBD5E1",width=2))
    for tipo,(cx,cy,bg) in quadrants.items():
        items = [s for s in (swot_items or []) if s.get("tipo") == tipo]
        x_dot = 0.04 if cx < 0.5 else 0.54
        y_top = (cy+0.45) if cy > 0.5 else (cy+0.44)
        for i, item in enumerate(items[:6]):
            desc = item.get("descricao",""); desc = desc[:36]+"…" if len(desc)>38 else desc
            fig.add_trace(go.Scatter(x=[x_dot],y=[y_top - i*0.085],
                mode="markers+text",
                marker=dict(size=11,color=SWOT_COLORS.get(tipo,BK_GRAY),line=dict(color="white",width=1.5)),
                text=[f"  {desc}"],textfont=dict(color="black",size=11),textposition="middle right",
                hovertext=f"<b>{tipo}</b> | {item.get('prioridade','')}",
                hoverinfo="text",name=tipo,showlegend=(i==0),legendgroup=tipo))
    corners = [(0.01,0.99,"FORÇAS","#065F46"),(0.51,0.99,"OPORTUNIDADES","#1E3A8A"),
               (0.01,0.50,"FRAQUEZAS","#991B1B"),(0.51,0.50,"AMEAÇAS","#92400E")]
    for x,y,lbl,color in corners:
        fig.add_annotation(x=x,y=y,xref="paper",yref="paper",text=f"<b>{lbl}</b>",
                           showarrow=False,font=dict(size=10,color=color),
                           xanchor="left",yanchor="top",bgcolor="rgba(255,255,255,0.6)",borderpad=2)
    fig.update_layout(height=440,paper_bgcolor="white",
                      xaxis=dict(showticklabels=False,showgrid=False,zeroline=False,range=[0,1]),
                      yaxis=dict(showticklabels=False,showgrid=False,zeroline=False,range=[0,1]),
                      margin=dict(l=10,r=120,t=36,b=10),
                      title=dict(text="Matriz SWOT",font=dict(size=14,color=BK_BLUE)),
                      font=dict(family="Segoe UI"),hoverlabel=dict(bgcolor="white",font_size=12),
                      legend=dict(orientation="v",x=1.02,y=0.5,xanchor="left",yanchor="middle"))
    return fig.to_json()

def fig_okrs_overview(dados):
    okrs = dados.get("s",[])
    if not okrs: return None
    names,prevs,reals,pcts = [],[],[],[]
    for o in okrs:
        o = _ensure_okr_meses(o)
        tp = sum(float(m.get("previsto",0)) for m in o["meses"])
        tr = sum(float(m.get("realizado",0)) for m in o["meses"])
        names.append(o.get("nome","")[:28]); prevs.append(tp); reals.append(tr)
        pcts.append((tr/tp*100) if tp > 0 else 0)
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Planejado",x=names,y=prevs,marker_color=BK_BLUE_LIGHT,opacity=0.7))
    fig.add_trace(go.Bar(name="Realizado",x=names,y=reals,marker_color=BK_GREEN))
    fig.add_trace(go.Scatter(name="% Realização",x=names,y=pcts,mode="markers+text",yaxis="y2",
                             marker=dict(size=10,color=BK_ORANGE),
                             text=[f"{p:.0f}%" for p in pcts],textposition="top center"))
    fig.update_layout(barmode="group",height=380,yaxis2=dict(overlaying="y",side="right",title="% Realização",range=[0,160]),
                      paper_bgcolor="white",plot_bgcolor="#F8FAFC",margin=dict(l=40,r=60,t=40,b=60),
                      font=dict(family="Segoe UI"),title="Visão Geral KPIs — Planejado vs Realizado")
    return fig.to_json()

def fig_actions_status(dados):
    actions = dados.get("actions",[])
    if not actions: return None
    counts = {}
    for a in actions:
        s = a.get("status","Pendente"); counts[s] = counts.get(s,0)+1
    fig = go.Figure(go.Pie(labels=list(counts.keys()),values=list(counts.values()),hole=0.5,
                           marker=dict(colors=[STATUS_COLORS.get(k,BK_GRAY) for k in counts]),
                           textinfo="label+percent"))
    _fig_layout(fig,"Status dos Planos de Ação",320)
    return fig.to_json()

def fig_actions_timeline(dados):
    actions = dados.get("actions",[]); today = date.today(); rows = []
    for a in actions:
        di = _safe_date(a.get("data_inicio")) or today
        df = _safe_date(a.get("data_vencimento")) or today
        if di > df: df = di
        rows.append({"Tarefa":a.get("titulo","")[:35],"Início":di,"Fim":df,
                     "Status":a.get("status","Pendente"),"Responsável":a.get("responsavel","")})
    if not rows: return None
    df2 = pd.DataFrame(rows).sort_values("Início")
    fig = px.timeline(df2,x_start="Início",x_end="Fim",y="Tarefa",color="Status",
                      hover_data=["Responsável"],color_discrete_map=STATUS_COLORS)
    fig.update_yaxes(autorange="reversed")
    _fig_layout(fig,"Linha do Tempo — Planos de Ação",max(300,len(rows)*35+80))
    return fig.to_json()

# ─── Exportações ─────────────────────────────────────────────────────────────

def export_excel(dados):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        if dados.get("partners"): pd.DataFrame(dados["partners"]).to_excel(w,sheet_name="Socios",index=False)
        if dados.get("areas"):    pd.DataFrame(dados["areas"]).to_excel(w,sheet_name="Areas",index=False)
        if dados.get("swot"):     pd.DataFrame(dados["swot"]).to_excel(w,sheet_name="SWOT",index=False)
        if dados.get("actions"):  pd.DataFrame(dados["actions"]).to_excel(w,sheet_name="Planos_Acao",index=False)
        if dados.get("s"):
            rows = []
            for o in dados["s"]:
                o = _ensure_okr_meses(o)
                row = {"nome":o.get("nome"),"area":o.get("area"),"unidade":o.get("unidade")}
                for i,m in enumerate(o["meses"]):
                    row[f"M{i+1:02d}_prev"]=m.get("previsto",0); row[f"M{i+1:02d}_real"]=m.get("realizado",0)
                rows.append(row)
            pd.DataFrame(rows).to_excel(w,sheet_name="KPIs",index=False)
        pd.DataFrame([dados.get("strategic",{})]).to_excel(w,sheet_name="Estrategia",index=False)
    return buf.getvalue()

def _create_kpi_chart_image(okr):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    okr = _ensure_okr_meses(okr); labels = _month_labels_for_okr(okr)
    pv = [float(m.get("previsto",0)) for m in okr["meses"]]
    rv = [float(m.get("realizado",0)) for m in okr["meses"]]
    last = max((i for i in range(36) if pv[i]!=0 or rv[i]!=0), default=11)
    n = max(last+1,12); labels,pv,rv = labels[:n],pv[:n],rv[:n]
    fig,ax = plt.subplots(figsize=(14,3.8)); x = np.arange(n)
    ax.bar(x,rv,color="#43A047",alpha=0.85,label="Realizado",width=0.65,zorder=3)
    ax.plot(x,pv,color="#1565C0",linewidth=2.5,marker="o",markersize=5,label="Planejado (Meta)",zorder=4)
    ax.set_xticks(x); ax.set_xticklabels(labels,rotation=45,ha="right",fontsize=7)
    ax.set_ylabel(okr.get("unidade",""),fontsize=9); ax.legend(fontsize=9,loc="upper left")
    ax.grid(axis="y",alpha=0.25,zorder=0); ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    plt.tight_layout(); buf=io.BytesIO(); fig.savefig(buf,format="png",dpi=150,bbox_inches="tight",facecolor="white")
    plt.close(fig); buf.seek(0); return buf.getvalue()

def build_word_report(dados, empresa: Empresa):
    from docx import Document
    from docx.shared import Inches, Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    doc = Document(); today_str = date.today().strftime("%d/%m/%Y")
    strategic = dados.get("strategic",{}); okrs = dados.get("s",[]); actions = dados.get("actions",[]); swot_list = dados.get("swot",[])
    C_BLUE=RGBColor(21,101,192); C_GREEN=RGBColor(67,160,71); C_GRAY=RGBColor(84,110,122)
    C_WHITE=RGBColor(255,255,255); C_RED=RGBColor(229,57,53); C_ORG=RGBColor(251,140,0)
    for sec in doc.sections:
        sec.top_margin=Cm(2); sec.bottom_margin=Cm(2); sec.left_margin=Cm(2.5); sec.right_margin=Cm(2.5)
    def _shd(cell,hex_fill):
        tc=cell._tc; tcPr=tc.get_or_add_tcPr(); shd=OxmlElement("w:shd")
        shd.set(qn("w:fill"),hex_fill); shd.set(qn("w:color"),"auto"); shd.set(qn("w:val"),"clear"); tcPr.append(shd)
    def _header(table,headers,fill="1565C0"):
        for j,h in enumerate(headers):
            c=table.rows[0].cells[j]; c.text=h
            for r in c.paragraphs[0].runs: r.font.bold=True; r.font.color.rgb=C_WHITE
            _shd(c,fill)
    def _cpct(pct): return C_GREEN if pct>=95 else (C_ORG if pct>=70 else C_RED)
    # Capa
    for _ in range(4): doc.add_paragraph()
    h=doc.add_heading(f"Planejamento Estratégico",0); h.alignment=WD_ALIGN_PARAGRAPH.CENTER
    for r in h.runs: r.font.color.rgb=C_BLUE
    p=doc.add_paragraph(empresa.nome); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r=p.runs[0]; r.font.size=Pt(16); r.font.bold=True; r.font.color.rgb=C_BLUE
    d=doc.add_paragraph(f"Gerado em {today_str}  |  Horizonte: 36 meses"); d.alignment=WD_ALIGN_PARAGRAPH.CENTER
    doc.add_page_break()
    # Norte Estratégico
    h1=doc.add_heading("Norte Estratégico",1)
    for r in h1.runs: r.font.color.rgb=C_BLUE
    fields=[("Visão",strategic.get("visao")or"—"),("Missão",strategic.get("missao")or"—"),
            ("Valores",strategic.get("valores")or"—"),("Proposta de Valor",strategic.get("proposta_valor")or"—"),
            ("Público-Alvo",strategic.get("publico_alvo")or"—"),("Diferenciais",strategic.get("diferenciais")or"—"),
            ("Pilares",strategic.get("pilares")or"—")]
    tbl=doc.add_table(rows=len(fields),cols=2); tbl.style="Table Grid"
    for i,(lbl,val) in enumerate(fields):
        row=tbl.rows[i]; row.cells[0].text=lbl; row.cells[1].text=val
        r0=row.cells[0].paragraphs[0].runs[0]; r0.font.bold=True; r0.font.color.rgb=C_BLUE
        row.cells[0].width=Cm(5); row.cells[1].width=Cm(12)
    if strategic.get("objetivos_estrategicos"):
        doc.add_paragraph(); p=doc.add_paragraph()
        r=p.add_run("Objetivos Estratégicos"); r.font.bold=True; r.font.color.rgb=C_BLUE
        doc.add_paragraph(strategic["objetivos_estrategicos"])
    doc.add_page_break()
    # KPIs resumo
    if okrs:
        h1=doc.add_heading("Dashboard de KPIs — Resumo",1)
        for r in h1.runs: r.font.color.rgb=C_BLUE
        headers=["KPI","Área","Un.","Total Planejado","Total Realizado","% Realização","Meses Preench."]
        tbl=doc.add_table(rows=1+len(okrs),cols=len(headers)); tbl.style="Table Grid"; _header(tbl,headers)
        for i,o in enumerate(okrs):
            o=_ensure_okr_meses(o)
            tp=sum(float(m.get("previsto",0)) for m in o["meses"])
            tr=sum(float(m.get("realizado",0)) for m in o["meses"])
            pct=(tr/tp*100) if tp>0 else 0
            filled=sum(1 for m in o["meses"] if float(m.get("realizado",0))!=0)
            row=tbl.rows[i+1]; row.cells[0].text=o.get("nome",""); row.cells[1].text=o.get("area","")
            row.cells[2].text=o.get("unidade",""); row.cells[3].text=f"{tp:.2f}"; row.cells[4].text=f"{tr:.2f}"
            row.cells[5].text=f"{pct:.1f}%"; row.cells[6].text=f"{filled}/36"
            r5=row.cells[5].paragraphs[0].runs[0]; r5.font.bold=True; r5.font.color.rgb=_cpct(pct)
        doc.add_page_break()
        # KPIs com gráficos
        h1=doc.add_heading("KPIs — Análise Detalhada",1)
        for r in h1.runs: r.font.color.rgb=C_BLUE
        for o in okrs:
            o=_ensure_okr_meses(o)
            tp=sum(float(m.get("previsto",0)) for m in o["meses"])
            tr=sum(float(m.get("realizado",0)) for m in o["meses"])
            pct=(tr/tp*100) if tp>0 else 0; sem="🟢" if pct>=95 else("🟡" if pct>=70 else"🔴")
            h2=doc.add_heading(f"{sem} {o.get('nome','')} ({o.get('unidade','')})",2)
            for r in h2.runs: r.font.color.rgb=C_BLUE
            sp=doc.add_paragraph(); r=sp.add_run(f"Área: {o.get('area','—')}  |  "); r.font.color.rgb=C_GRAY
            r=sp.add_run(f"Planejado: {tp:.2f}  |  "); r.font.color.rgb=C_BLUE
            r=sp.add_run(f"Realizado: {tr:.2f}  |  "); r.font.color.rgb=_cpct(pct)
            r=sp.add_run(f"Realização: {pct:.1f}%"); r.font.bold=True; r.font.color.rgb=_cpct(pct)
            try:
                img=_create_kpi_chart_image(o); doc.add_picture(io.BytesIO(img),width=Cm(16))
                doc.paragraphs[-1].alignment=WD_ALIGN_PARAGRAPH.CENTER
            except Exception as e:
                doc.add_paragraph(f"[Gráfico indisponível: {e}]")
            doc.add_paragraph()
        doc.add_page_break()
    # SWOT
    if swot_list:
        h1=doc.add_heading("Análise SWOT",1)
        for r in h1.runs: r.font.color.rgb=C_BLUE
        SWOT_FG={"Força":RGBColor(6,95,70),"Fraqueza":RGBColor(153,27,27),"Oportunidade":RGBColor(30,58,138),"Ameaça":RGBColor(146,64,14)}
        tbl=doc.add_table(rows=1+len(swot_list),cols=3); tbl.style="Table Grid"; _header(tbl,["Tipo","Descrição","Prioridade"])
        for i,item in enumerate(swot_list):
            tipo=item.get("tipo",""); row=tbl.rows[i+1]
            row.cells[0].text=tipo; row.cells[1].text=item.get("descricao",""); row.cells[2].text=item.get("prioridade","")
            r0=row.cells[0].paragraphs[0].runs[0]; r0.font.bold=True; r0.font.color.rgb=SWOT_FG.get(tipo,C_GRAY)
        doc.add_page_break()
    # Planos de Ação — TODAS AS COLUNAS
    h1=doc.add_heading("Planos de Ação",1)
    for r in h1.runs: r.font.color.rgb=C_BLUE
    if actions:
        today=date.today()
        STATUS_RBG={"Concluído":C_GREEN,"Em andamento":C_ORG,"Pendente":C_GRAY,"Atrasado":C_RED}
        headers=["#","Título","Descrição","KPI Vinculada","Área","Responsável","D. Início","Vencimento","Como Fazer / Obs.","Prioridade","Status"]
        tbl=doc.add_table(rows=1+len(actions),cols=len(headers)); tbl.style="Table Grid"; _header(tbl,headers)
        col_widths=[Cm(0.7),Cm(3.0),Cm(2.8),Cm(2.2),Cm(1.8),Cm(2.2),Cm(1.5),Cm(1.5),Cm(3.0),Cm(1.5),Cm(1.6)]
        for j,w in enumerate(col_widths):
            for row in tbl.rows: row.cells[j].width=w
        for i,a in enumerate(actions):
            status=a.get("status","Pendente"); dv_str=a.get("data_vencimento","")or""
            di_str=a.get("data_inicio","")or""
            atrasado=(status!="Concluído" and _safe_date(a.get("data_vencimento")) and _safe_date(a.get("data_vencimento"))<today)
            cf_obs=" | ".join(filter(None,[a.get("como_fazer",""),a.get("observacoes","")]))or"—"
            row=tbl.rows[i+1]
            row.cells[0].text=str(i+1); row.cells[1].text=a.get("titulo","—")or"—"
            row.cells[2].text=a.get("descricao","—")or"—"; row.cells[3].text=a.get("okr","—")or"—"
            row.cells[4].text=a.get("area","—")or"—"; row.cells[5].text=a.get("responsavel","—")or"—"
            row.cells[6].text=di_str or"—"
            dvc=row.cells[7]; dvc.text=f"{dv_str} (!)" if atrasado else (dv_str or"—")
            if atrasado:
                for r in dvc.paragraphs[0].runs: r.font.bold=True; r.font.color.rgb=C_RED
            row.cells[8].text=cf_obs; row.cells[9].text=a.get("prioridade","—")or"—"
            sc=row.cells[10]; sc.text=status
            for r in sc.paragraphs[0].runs: r.font.bold=True; r.font.color.rgb=STATUS_RBG.get(status,C_GRAY)
    else:
        doc.add_paragraph("Nenhum plano de ação cadastrado.")
    fp=doc.add_paragraph(f"{empresa.nome}  |  Planejamento Estratégico  |  {today_str}")
    fp.alignment=WD_ALIGN_PARAGRAPH.CENTER
    for r in fp.runs: r.font.size=Pt(9); r.font.color.rgb=C_GRAY
    buf=io.BytesIO(); doc.save(buf); buf.seek(0); return buf.getvalue()

def build_html_report(dados, empresa: Empresa):
    today_str=date.today().strftime("%d/%m/%Y"); strategic=dados.get("strategic",{})
    okrs=dados.get("s",[]); total_prev=sum(float(m.get("previsto",0)) for o in okrs for m in _ensure_okr_meses(o)["meses"])
    total_real=sum(float(m.get("realizado",0)) for o in okrs for m in _ensure_okr_meses(o)["meses"])
    pct=(total_real/total_prev*100) if total_prev>0 else 0
    return f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8">
<title>{empresa.nome} — Planejamento</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>body{{font-family:'Segoe UI',sans-serif;background:#F0F4F8;padding:20px;color:#1a202c}}
.hero{{background:linear-gradient(135deg,#1565C0,#00897B);color:white;padding:32px;border-radius:12px;margin-bottom:24px}}
.card{{background:white;border-radius:10px;padding:20px 24px;margin-bottom:20px;box-shadow:0 2px 8px rgba(0,0,0,.06)}}</style></head>
<body><div class="hero"><h1>📊 {empresa.nome} — Planejamento Estratégico</h1>
<p>Gerado em {today_str} | {len(okrs)} KPIs | Realização geral: {pct:.1f}%</p></div>
<div class="card"><h2>🧭 Norte Estratégico</h2>
<p><b>Visão:</b> {strategic.get('visao')or'—'}</p>
<p><b>Missão:</b> {strategic.get('missao')or'—'}</p></div></body></html>"""

# ─── Views ───────────────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    empresa = _get_empresa(request); dados = get_planning(empresa)
    today = date.today(); okrs = dados.get("s",[]); actions = dados.get("actions",[])
    tp = sum(float(m.get("previsto",0)) for o in okrs for m in _ensure_okr_meses(o)["meses"])
    tr = sum(float(m.get("realizado",0)) for o in okrs for m in _ensure_okr_meses(o)["meses"])
    pct_real = (tr/tp*100) if tp > 0 else 0
    n_atrasados = sum(1 for a in actions if a.get("status")!="Concluído" and _safe_date(a.get("data_vencimento")) and _safe_date(a.get("data_vencimento"))<today)
    n_concluidos = sum(1 for a in actions if a.get("status")=="Concluído")
    n_andamento  = sum(1 for a in actions if a.get("status")=="Em andamento")
    atrasados = sorted([{**a,"dias_atraso":(today-_safe_date(a.get("data_vencimento"))).days}
                        for a in actions if a.get("status")!="Concluído" and _safe_date(a.get("data_vencimento")) and _safe_date(a.get("data_vencimento"))<today],
                       key=lambda x:x["dias_atraso"],reverse=True)
    return render(request,"planejamento/dashboard.html",{
        "dados":dados,"n_okrs":len(okrs),"pct_real":round(pct_real,1),
        "pct_real_color":BK_GREEN if pct_real>=90 else(BK_ORANGE if pct_real>=70 else BK_RED),
        "n_actions":len(actions),"n_concluidos":n_concluidos,"n_atrasados":n_atrasados,"n_andamento":n_andamento,
        "fig_overview_json":fig_okrs_overview(dados),"fig_status_json":fig_actions_status(dados),
        "fig_swot_json":fig_swot_quadrant(dados.get("swot",[])) if dados.get("swot") else None,
        "gauges_json":[fig_okr_gauge(o) for o in okrs[:4]],"atrasados":atrasados[:10],
        "empresa":empresa,"plano_info":get_plano_info(empresa),
    })


@login_required
def socios(request):
    empresa = _get_empresa(request); dados = get_planning(empresa)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add":
            nome = request.POST.get("nome","").strip()
            if nome:
                dados["partners"].append({"nome":nome,"cargo":request.POST.get("cargo",""),
                    "email":request.POST.get("email",""),"telefone":request.POST.get("telefone",""),
                    "observacoes":request.POST.get("observacoes","")})
                save_planning(dados,empresa); messages.success(request,"Sócio/Gestor adicionado!")
            else: messages.warning(request,"Informe o nome.")
        elif action == "save_table":
            try:
                rows = json.loads(request.POST.get("rows_json","[]"))
                dados["partners"] = _normalize_partner_rows(rows)
                save_planning(dados,empresa); messages.success(request,"Sócios/Gestores salvos!")
            except Exception as e: messages.error(request,f"Erro: {e}")
        return redirect("planejamento:socios")
    return render(request,"planejamento/socios.html",{"dados":dados,"empresa":empresa})


@login_required
def estrategia(request):
    empresa = _get_empresa(request); dados = get_planning(empresa)
    if request.method == "POST":
        for f in ["visao","missao","valores","posicionamento","proposta_valor","publico_alvo","diferenciais","pilares","objetivos_estrategicos","notas"]:
            dados["strategic"][f] = request.POST.get(f,"")
        save_planning(dados,empresa); messages.success(request,"Estratégia salva!")
        return redirect("planejamento:estrategia")
    return render(request,"planejamento/estrategia.html",{"dados":dados,"empresa":empresa})


@login_required
def areas(request):
    empresa = _get_empresa(request); dados = get_planning(empresa)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add":
            area = request.POST.get("area","").strip()
            if area:
                dados["areas"].append({"area":area,"responsavel":request.POST.get("responsavel",""),
                    "email":request.POST.get("email",""),"observacoes":request.POST.get("observacoes","")})
                save_planning(dados,empresa); messages.success(request,"Área adicionada!")
            else: messages.warning(request,"Informe a área.")
        elif action == "save_table":
            try:
                rows = json.loads(request.POST.get("rows_json","[]"))
                dados["areas"] = _normalize_area_rows(rows)
                save_planning(dados,empresa); messages.success(request,"Áreas salvas!")
            except Exception as e: messages.error(request,f"Erro: {e}")
        return redirect("planejamento:areas")
    return render(request,"planejamento/areas.html",{"dados":dados,"empresa":empresa})


@login_required
def swot(request):
    empresa = _get_empresa(request); dados = get_planning(empresa)
    info = get_plano_info(empresa)
    if request.method == "POST":
        if not info["limites"]["swot_editar"] and empresa.plano == "free":
            messages.warning(request,"SWOT completo disponível apenas no Plano Pago.")
            return redirect("planejamento:swot")
        if request.POST.get("action") == "save_table":
            try:
                rows = json.loads(request.POST.get("rows_json","[]"))
                dados["swot"] = [{"tipo":_clean_text(r.get("tipo")),"descricao":_clean_text(r.get("descricao")),
                                   "prioridade":_clean_text(r.get("prioridade"),"Média")or"Média"}
                                 for r in rows if _clean_text(r.get("descricao")) and not r.get("excluir",False)]
                save_planning(dados,empresa); messages.success(request,"SWOT salva!")
            except Exception as e: messages.error(request,f"Erro: {e}")
        return redirect("planejamento:swot")
    fig_swot_json = fig_swot_quadrant(dados.get("swot",[])) if dados.get("swot") else None
    return render(request,"planejamento/swot.html",{
        "dados":dados,"fig_swot_json":fig_swot_json,"swot_groups":_group_swot_items(dados.get("swot",[])),
        "tipos":["Força","Fraqueza","Oportunidade","Ameaça"],"prioridades":["Alta","Média","Baixa"],
        "plano_info":info,"empresa":empresa,
    })


@login_required
def kpis(request):
    empresa = _get_empresa(request); dados = get_planning(empresa)
    dados.setdefault("s",[])
    dados["s"] = [_ensure_okr_meses(o) for o in dados["s"]]
    info = get_plano_info(empresa)
    unidade_opts = ["R$","%","un","clientes","projetos","h","dias","índice"]
    month_cols   = [f"M{i:02d}" for i in range(1,37)]

    if request.method == "POST":
        action = request.POST.get("action","").strip()

        if action == "save_meta":
            try:
                rows = json.loads(request.POST.get("rows_json","[]"))
                max_kpis = info["limites"]["max_kpis"]
                antigos_by_nome = {_clean_text(o.get("nome","")): _ensure_okr_meses(dict(o))
                                   for o in dados.get("s",[]) if _clean_text(o.get("nome",""))}
                novos = []
                for row in rows:
                    if row.get("excluir"): continue
                    nome = _clean_text(row.get("nome"))
                    if not nome: continue
                    existente = antigos_by_nome.get(nome)
                    meses = existente.get("meses",[]) if existente else []
                    while len(meses) < 36: meses.append({"previsto":0.0,"realizado":0.0})
                    novos.append({"nome":nome,"area":_clean_text(row.get("area")),
                                  "unidade":_clean_text(row.get("unidade"),"un"),
                                  "descricao":_clean_text(row.get("descricao")),
                                  "inicio":_clean_text(row.get("inicio")),"meses":meses[:36]})
                if max_kpis is not None and len(novos) > max_kpis:
                    novos = novos[:max_kpis]
                    messages.warning(request,f"Plano Free: máximo de {max_kpis} KPI(s). Faça upgrade para adicionar mais.")
                dados["s"] = novos; save_planning(dados,empresa)
                messages.success(request,"KPIs salvos com sucesso.")
            except Exception as e: messages.error(request,f"Erro ao salvar KPIs: {e}")
            return redirect("planejamento:okrs")

        elif action in ("save_previsto","save_realizado"):
            campo = "previsto" if action=="save_previsto" else "realizado"
            is_ajax = request.headers.get("X-Requested-With")=="XMLHttpRequest"
            try:
                rows = json.loads(request.POST.get("rows_json","[]"))
                s_list = dados.get("s",[])
                for row in rows:
                    if not isinstance(row,dict): continue
                    try: idx = int(row.get("idx",-1))
                    except: continue
                    if idx<0 or idx>=len(s_list): continue
                    okr = s_list[idx]
                    if not isinstance(okr,dict): continue
                    meses = okr.setdefault("meses",[])
                    while len(meses)<36: meses.append({"previsto":0.0,"realizado":0.0})
                    for i in range(36):
                        key = f"M{i+1:02d}"
                        if key in row:
                            try: meses[i][campo]=float(row[key] or 0)
                            except: pass
                save_planning(dados,empresa)
                if is_ajax:
                    nz = sum(1 for o in dados.get("s",[]) for m in o.get("meses",[]) if (m.get(campo) or 0)!=0)
                    return JsonResponse({"status":"ok","msg":f"{'Planejado' if campo=='previsto' else 'Realizado'} salvo.","non_zero":nz})
                messages.success(request,"Salvo com sucesso.")
            except Exception as e:
                if request.headers.get("X-Requested-With")=="XMLHttpRequest":
                    return JsonResponse({"status":"error","msg":str(e)},status=400)
                messages.error(request,f"Erro: {e}")
            return redirect("planejamento:okrs")

    s_list = [_ensure_okr_meses(dict(o)) for o in dados.get("s",[])]
    return render(request,"planejamento/okrs.html",{
        "dados":dados,"s_list":s_list,"okrs_list":s_list,
        "unidade_opts":unidade_opts,"month_cols":month_cols,
        "fig_overview_json":fig_okrs_overview(dados),
        "plano_info":info,"empresa":empresa,
    })


@login_required
def kpi_detail_json(request, nome):
    empresa = _get_empresa(request); dados = get_planning(empresa)
    okr = next((o for o in dados.get("s",[]) if str(o.get("nome","")).strip()==str(nome).strip()), None)
    if not okr: return JsonResponse({"error":"KPI não encontrada."},status=404)
    okr = _ensure_okr_meses(okr)
    tp = sum(float(m.get("previsto",0) or 0) for m in okr["meses"])
    tr = sum(float(m.get("realizado",0) or 0) for m in okr["meses"])
    pct = round((tr/tp*100),1) if tp>0 else 0.0
    labels = _month_labels_for_okr(okr)
    table = [{"mes":labels[i],"prev":float(m.get("previsto",0) or 0),"real":float(m.get("realizado",0) or 0),
              "diff":float(m.get("realizado",0) or 0)-float(m.get("previsto",0) or 0),
              "status":"Acima/atingido" if float(m.get("realizado",0))>=float(m.get("previsto",0)) and float(m.get("previsto",0))>0 else ("Abaixo" if float(m.get("realizado",0))>0 else "Sem realização")}
             for i,m in enumerate(okr["meses"])]
    return JsonResponse({"nome":okr.get("nome",""),"unidade":okr.get("unidade",""),"tp":tp,"tr":tr,"pct":pct,
                         "fig_gauge":fig_okr_gauge(okr),"fig_monthly":fig_okr_monthly(okr),
                         "fig_cumulative":fig_okr_cumulative(okr),"table":table})


@login_required
def planos_acao(request):
    empresa = _get_empresa(request)
    info = get_plano_info(empresa)
    if not info["limites"]["planos_acao"]:
        return render(request,"planejamento/plano_bloqueado.html",{
            "recurso":"Planos de Ação","icone":"📋",
            "descricao":"Gerencie tarefas, prazos e responsáveis vinculados às suas KPIs."})
    dados = get_planning(empresa); today = date.today()
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add":
            titulo = request.POST.get("titulo","").strip()
            if not titulo: messages.warning(request,"Informe o título.")
            else:
                dados["actions"].append({"titulo":titulo,"area":request.POST.get("area",""),
                    "responsavel":request.POST.get("responsavel",""),"okr":request.POST.get("okr",""),
                    "descricao":request.POST.get("descricao",""),"data_inicio":request.POST.get("data_inicio",""),
                    "data_vencimento":request.POST.get("data_vencimento",""),"status":request.POST.get("status","Pendente"),
                    "observacoes":request.POST.get("observacoes",""),"como_fazer":request.POST.get("como_fazer",""),
                    "prioridade":request.POST.get("prioridade","Média")})
                save_planning(dados,empresa); messages.success(request,f'Plano "{titulo}" adicionado!')
        elif action == "save_table":
            try:
                rows = json.loads(request.POST.get("rows_json","[]"))
                dados["actions"] = [r for r in rows if r.get("titulo","").strip() and not r.get("excluir",False)]
                save_planning(dados,empresa); messages.success(request,"Planos salvos!")
            except Exception as e: messages.error(request,f"Erro: {e}")
        return redirect("planejamento:planos_acao")
    n_conc = sum(1 for a in dados["actions"] if a.get("status")=="Concluído")
    n_and  = sum(1 for a in dados["actions"] if a.get("status")=="Em andamento")
    n_atrs = sum(1 for a in dados["actions"] if a.get("status")!="Concluído" and _safe_date(a.get("data_vencimento")) and _safe_date(a.get("data_vencimento"))<today)
    return render(request,"planejamento/planos_acao.html",{
        "dados":dados,"today":today.isoformat(),"n_total":len(dados["actions"]),
        "n_concluidos":n_conc,"n_andamento":n_and,"n_atrasados":n_atrs,"n_pendente":len(dados["actions"])-n_conc-n_and,
        "fig_status_json":fig_actions_status(dados),"fig_timeline_json":fig_actions_timeline(dados),
        "status_opts":["Pendente","Em andamento","Concluído"],"empresa":empresa,
    })


@login_required
def relatorios(request):
    empresa = _get_empresa(request); dados = get_planning(empresa)
    today = date.today(); okrs = dados.get("s",[]); actions = dados.get("actions",[]); swot = dados.get("swot",[])
    n_atrs = sum(1 for a in actions if a.get("status")!="Concluído" and _safe_date(a.get("data_vencimento")) and _safe_date(a.get("data_vencimento"))<today)
    n_conc = sum(1 for a in actions if a.get("status")=="Concluído")
    n_and  = sum(1 for a in actions if a.get("status")=="Em andamento")
    n_pend = sum(1 for a in actions if a.get("status")=="Pendente")
    tp_g=0; tr_g=0; saude=[]; kpi_charts=[]
    for o in okrs:
        o=_ensure_okr_meses(o); tp=sum(float(m.get("previsto",0)) for m in o["meses"]); tr=sum(float(m.get("realizado",0)) for m in o["meses"])
        tp_g+=tp; tr_g+=tr; pct=(tr/tp*100) if tp>0 else 0; filled=sum(1 for m in o["meses"] if float(m.get("realizado",0))!=0)
        sem="🟢" if pct>=95 else("🟡" if pct>=70 else"🔴"); color=BK_GREEN if pct>=95 else(BK_ORANGE if pct>=70 else BK_RED)
        saude.append({"semaforo":sem,"nome":o.get("nome"),"area":o.get("area"),"unidade":o.get("unidade"),
                      "pct":round(pct,1),"tp":round(tp,2),"tr":round(tr,2),"filled":filled,"color":color})
        labels=_month_labels_for_okr(o); prevs=[float(m.get("previsto",0)) for m in o["meses"]]; reals=[float(m.get("realizado",0)) for m in o["meses"]]
        fig_bar=go.Figure(data=[go.Bar(name="Planejado",x=labels,y=prevs,marker_color=BK_BLUE_LIGHT,opacity=0.85),go.Bar(name="Realizado",x=labels,y=reals,marker_color=BK_GREEN)])
        fig_bar.update_layout(barmode="group",height=240,margin=dict(l=40,r=10,t=16,b=50),legend=dict(orientation="h",y=1.08),paper_bgcolor="white",plot_bgcolor="white",xaxis=dict(tickangle=-45,tickfont=dict(size=9)))
        fig_gauge=go.Figure(go.Indicator(mode="gauge+number",value=round(pct,1),number={"suffix":"%","font":{"size":22,"color":color}},
            gauge={"axis":{"range":[0,120]},"bar":{"color":color},"steps":[{"range":[0,70],"color":"#FEE2E2"},{"range":[70,95],"color":"#FEF3C7"},{"range":[95,120],"color":"#D1FAE5"}],"threshold":{"line":{"color":"#1565C0","width":2},"thickness":0.75,"value":100}}))
        fig_gauge.update_layout(height=180,margin=dict(l=10,r=10,t=10,b=10),paper_bgcolor="white")
        kpi_charts.append({"nome":o.get("nome"),"area":o.get("area"),"unidade":o.get("unidade"),"tp":round(tp,2),"tr":round(tr,2),"pct":round(pct,1),"semaforo":sem,"color":color,"fig_bar":fig_bar.to_json(),"fig_gauge":fig_gauge.to_json()})
    pct_g=(tr_g/tp_g*100) if tp_g>0 else 0
    by_status={};by_area={}
    for a in actions:
        sv=a.get("status","Pendente");av=a.get("area","—")
        by_status[sv]=by_status.get(sv,0)+1; by_area[av]=by_area.get(av,0)+1
    fig_st=""; fig_ar=""
    if by_status:
        f=go.Figure(go.Pie(labels=list(by_status.keys()),values=list(by_status.values()),marker_colors=[STATUS_COLORS.get(k,BK_GRAY) for k in by_status],hole=0.4,textinfo="label+percent",textfont_size=11))
        f.update_layout(height=260,margin=dict(l=10,r=10,t=10,b=10),paper_bgcolor="white",showlegend=False); fig_st=f.to_json()
    if by_area:
        sa=sorted(by_area.items(),key=lambda x:x[1],reverse=True)
        f=go.Figure(go.Bar(x=[i[0] for i in sa],y=[i[1] for i in sa],marker_color=BK_BLUE,text=[i[1] for i in sa],textposition="outside"))
        f.update_layout(height=260,margin=dict(l=10,r=10,t=16,b=60),paper_bgcolor="white",plot_bgcolor="white",xaxis=dict(tickangle=-30,tickfont=dict(size=10)),yaxis=dict(showgrid=True,gridcolor="#E2E8F0")); fig_ar=f.to_json()
    recs=[]
    threats=[s for s in swot if s.get("tipo")=="Ameaça" and s.get("prioridade")=="Alta"]
    opps=[s for s in swot if s.get("tipo")=="Oportunidade" and s.get("prioridade")=="Alta"]
    if threats: recs.append(f"🔴 {len(threats)} Ameaça(s) Alta — crie planos de mitigação imediatos.")
    if opps:    recs.append(f"🔵 {len(opps)} Oportunidade(s) Alta — transforme em KPIs estratégicos.")
    if n_atrs:  recs.append(f"⚠️ {n_atrs} plano(s) atrasado(s) — replaneje: escopo, capacidade, nova data.")
    if okrs:    recs.append("📅 Estabeleça revisão mensal do realizado e trimestral das prioridades.")
    if not recs: recs.append("✅ Preencha Visão/Missão, SWOT e KPIs para gerar recomendações automáticas.")
    return render(request,"planejamento/relatorios.html",{
        "dados":dados,"saude":saude,"recs":recs,"total_prev_geral":round(tp_g,2),"total_real_geral":round(tr_g,2),
        "pct_geral":round(pct_g,1),"kpi_charts":kpi_charts,"actions":actions,"n_total_ac":len(actions),
        "n_concluidos":n_conc,"n_andamento":n_and,"n_pendente":n_pend,"n_atrasados":n_atrs,
        "fig_ac_status_json":fig_st,"fig_ac_area_json":fig_ar,"today_str":today.isoformat(),
        "plano_info":get_plano_info(empresa),"empresa":empresa,
    })


# ─── Exportações ─────────────────────────────────────────────────────────────

@login_required
def export_json(request):
    info = get_plano_info(_get_empresa(request))
    if not info["limites"]["json_export"]:
        messages.warning(request,"Exportação JSON disponível apenas no Plano Pago."); return redirect("planejamento:relatorios")
    dados = get_planning(_get_empresa(request))
    resp = HttpResponse(json.dumps(dados,ensure_ascii=False,indent=2),content_type="application/json")
    resp["Content-Disposition"]='attachment; filename="planejamento_export.json"'; return resp

@login_required
def export_excel_view(request):
    empresa = _get_empresa(request); info = get_plano_info(empresa)
    if not info["limites"]["excel_export"]:
        messages.warning(request,"Exportação Excel disponível apenas no Plano Pago."); return redirect("planejamento:relatorios")
    dados = get_planning(empresa)
    resp = HttpResponse(export_excel(dados),content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"]='attachment; filename="planejamento_completo.xlsx"'; return resp

@login_required
def export_zip_view(request):
    empresa = _get_empresa(request); dados = get_planning(empresa)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf,"w") as zf:
        for key,name in [("partners","socios.csv"),("areas","areas.csv"),("swot","swot.csv"),("actions","planos_acao.csv")]:
            if dados.get(key): zf.writestr(name,pd.DataFrame(dados[key]).to_csv(index=False))
    resp = HttpResponse(buf.getvalue(),content_type="application/zip")
    resp["Content-Disposition"]='attachment; filename="planning_csvs.zip"'; return resp

@login_required
def export_html_view(request):
    empresa = _get_empresa(request); dados = get_planning(empresa)
    resp = HttpResponse(build_html_report(dados,empresa),content_type="text/html; charset=utf-8")
    resp["Content-Disposition"]='attachment; filename="relatorio_planejamento.html"'; return resp

@login_required
def export_word_view(request):
    empresa = _get_empresa(request); info = get_plano_info(empresa)
    if not info["limites"]["word_export"]:
        messages.warning(request,"Relatório Word disponível apenas no Plano Pago."); return redirect("planejamento:relatorios")
    dados = get_planning(empresa)
    try:
        docx_bytes = build_word_report(dados,empresa)
        resp = HttpResponse(docx_bytes,content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        resp["Content-Disposition"]='attachment; filename="relatorio_planejamento.docx"'; return resp
    except Exception as e:
        import traceback; traceback.print_exc()
        messages.error(request,f"Erro ao gerar Word: {e}"); return redirect("planejamento:relatorios")

@login_required
def import_json(request):
    empresa = _get_empresa(request)
    if request.method == "POST" and request.FILES.get("json_file"):
        try:
            dados = json.loads(request.FILES["json_file"].read().decode("utf-8"))
            save_planning(dados,empresa); messages.success(request,"JSON importado!")
        except Exception as e: messages.error(request,f"Erro: {e}")
    return redirect("planejamento:dashboard")


# ─── Administração de Empresas (superuser) ───────────────────────────────────

@login_required
def empresas_admin(request):
    if not request.user.is_superuser:
        messages.error(request,"Acesso restrito a administradores."); return redirect("planejamento:dashboard")
    if request.method == "POST":
        action = request.POST.get("action","")
        empresa_id = request.POST.get("empresa_id")
        if action == "toggle_plano":
            e = get_object_or_404(Empresa,pk=empresa_id)
            e.plano = "pago" if e.plano=="free" else "free"
            e.save(update_fields=["plano"]); messages.success(request,f'Plano de "{e.nome}" → {e.plano}.')
        elif action == "toggle_ativa":
            e = get_object_or_404(Empresa,pk=empresa_id)
            e.ativa = not e.ativa; e.save(update_fields=["ativa"])
            messages.success(request,f'Empresa "{e.nome}" {"ativada" if e.ativa else "desativada"}.')
        elif action == "delete":
            e = get_object_or_404(Empresa,pk=empresa_id)
            if e.slug == "bk": messages.warning(request,"Empresa padrão não pode ser excluída.")
            else: nome=e.nome; e.delete(); messages.success(request,f'Empresa "{nome}" excluída.')
        return redirect("planejamento:empresas_admin")
    empresas = Empresa.objects.annotate(n_usuarios=Count("usuarios")).order_by("-criada_em")
    total_mrr = Empresa.objects.filter(plano="pago",ativa=True).count() * 29.90
    return render(request,"planejamento/empresas.html",{
        "empresas":empresas,"total_mrr":round(total_mrr,2),
        "n_pago":Empresa.objects.filter(plano="pago",ativa=True).count(),
        "n_free":Empresa.objects.filter(plano="free",ativa=True).count(),
        "n_total":Empresa.objects.filter(ativa=True).count(),
    })


@login_required
def configurar_plano(request):
    if not request.user.is_superuser:
        messages.error(request,"Acesso restrito."); return redirect("planejamento:dashboard")
    empresa = _get_empresa(request)
    if request.method == "POST":
        novo = request.POST.get("plano","free")
        if novo in ("free","pago"):
            empresa.plano = novo; empresa.save(update_fields=["plano"])
            messages.success(request,f"Plano alterado para {'Free' if novo=='free' else 'Pago'}.")
        return redirect("planejamento:configurar_plano")
    return render(request,"planejamento/configurar_plano.html",{
        "plano_atual":empresa.plano,"limites":empresa.get_limites(),"empresa":empresa,
    })


# ─── Aliases de compatibilidade ──────────────────────────────────────────────
okrs = kpis
okr_detail_json = kpi_detail_json
