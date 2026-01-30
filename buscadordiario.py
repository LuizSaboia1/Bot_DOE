import streamlit as st
import requests
import io
import pdfplumber
import pandas as pd
import re
import os
import plotly.express as px
from datetime import datetime, timedelta

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Extrator Pro - DOE/CE", layout="wide")

# --- CSS ---
st.markdown("""
<style>
    .stApp { background-color: #f0f2f6; }
    div[data-testid="stMetricValue"] { font-size: 1.5rem; color: #0e4da4; }
    div[data-testid="stDataFrameResizable"] { width: 100%; }
    .stProgress > div > div > div > div { background-color: #0e4da4; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; background-color: #fff; border-radius: 5px; box-shadow: 0 1px 2px rgba(0,0,0,0.1); }
    .stTabs [aria-selected="true"] { background-color: #e3f2fd; color: #0e4da4; border-bottom: 2px solid #0e4da4; }
</style>
""", unsafe_allow_html=True)

# --- FUNÇÕES ---

def limpar_texto_multilinha(texto):
    if not texto: return ""
    return " ".join(texto.split())

def limpar_valor_monetario(texto):
    if not texto: return 0.0
    try:
        limpo = texto.upper().replace('R$', '').replace('.', '').replace(',', '.').strip()
        return float(limpo)
    except:
        return 0.0

def formatar_moeda_br(valor):
    if not isinstance(valor, (float, int)): return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def truncar_texto(texto, max_chars=20):
    if not texto: return "Não Identificado"
    if len(texto) > max_chars:
        return texto[:max_chars] + "..."
    return texto

def classificar_tipo_aditivo(objeto, valor):
    tipos = []
    objeto_upper = objeto.upper() if objeto else ""
    termos_prazo = ["PRORROGA", "VIGÊNCIA", "PRAZO", "12 MESES", "DOZE MESES", "DILAÇÃO"]
    termos_valor = ["ACRÉSCIMO", "REAJUSTE", "REALINHAMENTO", "SUPRESSÃO", "REPACTUAÇÃO", "VALOR GLOBAL"]
    
    if any(x in objeto_upper for x in termos_prazo): tipos.append("PRAZO")
    if valor > 0 or any(x in objeto_upper for x in termos_valor): tipos.append("VALOR")
    if not tipos: return "Outros"
    return " + ".join(tipos)

def extrair_dados_pagina(texto_pagina, data_ref, nome_arquivo, num_pag, url_arquivo):
    dados_extraidos = []
    padrao_bloco = r"(EXTRATO D[EO] ADITIVO.*?)(?=\nEXTRATO|\nSECRETARIA|\nPREFEITURA|\nESTADO DO CEARÁ|\*\*\*|$)"
    blocos = re.findall(padrao_bloco, texto_pagina, flags=re.DOTALL | re.IGNORECASE)
    
    for bloco in blocos:
        item = {
            "Data": data_ref,
            "Órgão": "Não identificado",
            "Contratado(a)": "", 
            "Valor Float": 0.0,
            "Objeto": "",
            "Tipo": "",
            "Link": f"{url_arquivo}#page={num_pag}"
        }
        
        match_orgao = re.search(r"CONTRATANTE\s*[:\-\.]\s*(.*?)(?=\n\s*[IVX]+|\n\s*CONTRATAD|\n\s*CNPJ|\n\s*OBJETO)", bloco, re.DOTALL | re.IGNORECASE)
        if match_orgao: item["Órgão"] = limpar_texto_multilinha(match_orgao.group(1))
            
        match_empresa = re.search(r"CONTRATAD[OA]\s*[:\-\.]\s*(.*?)(?=\n\s*[IVX]+|\n\s*OBJETO|\n\s*FUNDAMENTAÇÃO|\n\s*CNPJ|\n\s*VIGÊNCIA)", bloco, re.DOTALL | re.IGNORECASE)
        if match_empresa: item["Contratado(a)"] = limpar_texto_multilinha(match_empresa.group(1))
            
        match_valor = re.search(r"R\$\s*([\d\.,]+)", bloco)
        if match_valor: item["Valor Float"] = limpar_valor_monetario(match_valor.group(1))
            
        match_objeto = re.search(r"OBJETO\s*[:\-\.]\s*(.*?)(?=\n\s*[IVX]+|\n\s*VALOR|\n\s*DOTAÇÃO|\n\s*VIGÊNCIA|\n\s*SIGNATÁRIOS|\n\s*DATA|\n\s*FUNDAMENTAÇÃO)", bloco, re.DOTALL | re.IGNORECASE)
        if match_objeto: item["Objeto"] = limpar_texto_multilinha(match_objeto.group(1))
        
        item["Tipo"] = classificar_tipo_aditivo(item["Objeto"], item["Valor Float"])
        item["Valor Formatado"] = formatar_moeda_br(item["Valor Float"])
        
        dados_extraidos.append(item)
    return dados_extraidos

# --- UI PRINCIPAL ---

st.title("⚖️ Extrator de Aditivos - DOE/CE")

with st.sidebar:
    st.header("⚙️ Configurações")
    dt_inicio = st.date_input("Data Inicial", datetime.today(), format="DD/MM/YYYY")
    dt_fim = st.date_input("Data Final", datetime.today(), format="DD/MM/YYYY")
    st.divider()
    st.subheader("📊 Visualização")
    # Adicionada a opção "🏢 Contratado" na ordenação
    criterio_ordem = st.radio("Ordenar Tabela por:", ("📅 Data", "💰 Valor", "🏛️ Contratante", "🏢 Contratado"))
    st.divider()
    btn_executar = st.button("🚀 INICIAR VARREDURA", type="primary")

# --- FASE 1: EXECUÇÃO ---

if btn_executar:
    if dt_fim < dt_inicio:
        st.error("Data Final deve ser maior que Inicial.")
    else:
        if 'resultados_busca' in st.session_state:
            del st.session_state['resultados_busca']

        st.divider()
        st.subheader("📡 Monitoramento em Tempo Real")
        
        col1, col2, col3, col4 = st.columns(4)
        m_dias = col1.empty()
        m_pags = col2.empty()
        m_palavras = col3.empty()
        m_aditivos = col4.empty()
        
        st.write("")
        barra_progresso = st.progress(0)
        status_log = st.empty()
        
        lista_temp = []
        dias_totais = (dt_fim - dt_inicio).days + 1
        dias_proc = 0
        total_pags = 0
        total_words = 0
        total_ads = 0
        
        data_cursor = dt_inicio
        
        while data_cursor <= dt_fim:
            url_date = data_cursor.strftime("%Y%m%d")
            data_str = data_cursor.strftime("%d/%m/%Y")
            
            status_log.markdown(f"🗓️ **Pesquisando dia {data_str}...**")
            
            parte = 1
            max_partes = 10 
            
            while parte <= max_partes:
                nome_arq = f"do{url_date}p{f'{parte:02d}'}.pdf"
                url_web = f"http://imagens.seplag.ce.gov.br/PDF/{url_date}/{nome_arq}"
                
                status_log.markdown(f"🗓️ **Dia {data_str}** &nbsp;&nbsp; ➡️ &nbsp;&nbsp; 📄 *Verificando: {nome_arq}*")
                
                arquivo_para_abrir = None
                origem = ""
                
                if os.path.exists(nome_arq):
                    arquivo_para_abrir = open(nome_arq, "rb")
                    origem = "Local"
                else:
                    try:
                        headers = {'User-Agent': 'Mozilla/5.0'}
                        check = requests.head(url_web, headers=headers, timeout=5)
                        if check.status_code == 200:
                            status_log.markdown(f"🗓️ **Dia {data_str}** &nbsp;&nbsp; ➡️ &nbsp;&nbsp; ⬇️ *Baixando: {url_web}*")
                            resp = requests.get(url_web, headers=headers, timeout=10)
                            arquivo_para_abrir = io.BytesIO(resp.content)
                            origem = "Web"
                        elif check.status_code == 404:
                            if parte == 1: status_log.warning(f"❌ Dia {data_str}: Arquivo não encontrado.")
                            break 
                        else: break
                    except: break

                if arquivo_para_abrir:
                    try:
                        with pdfplumber.open(arquivo_para_abrir) as pdf:
                            total_p_pdf = len(pdf.pages)
                            for i, page in enumerate(pdf.pages):
                                status_log.markdown(f"🗓️ **Dia {data_str}** &nbsp;&nbsp; ➡️ &nbsp;&nbsp; 👁️ *Lendo {nome_arq} (Pág {i+1}/{total_p_pdf})*")
                                texto = page.extract_text(layout=True) or ""
                                total_words += len(texto.split())
                                total_pags += 1
                                
                                novos = extrair_dados_pagina(texto, data_str, nome_arq, i+1, url_web)
                                if novos:
                                    lista_temp.extend(novos)
                                    total_ads += len(novos)
                                
                                if i % 2 == 0:
                                    m_pags.metric("Páginas Lidas", total_pags)
                                    m_palavras.metric("Palavras Lidas", f"{total_words:,.0f}".replace(",", "."))
                                    m_aditivos.metric("Aditivos Encontrados", total_ads)
                                    
                        if origem == "Local": arquivo_para_abrir.close()
                    except: pass
                
                parte += 1 
            
            dias_proc += 1
            m_dias.metric("Dias Processados", f"{dias_proc}/{dias_totais}")
            barra_progresso.progress(dias_proc / dias_totais)
            data_cursor += timedelta(days=1)
            
        st.session_state['resultados_busca'] = lista_temp
        barra_progresso.progress(1.0)
        status_log.success("✅ Processamento Finalizado!")

# --- FASE 2: VISUALIZAÇÃO ---

if 'resultados_busca' in st.session_state and st.session_state['resultados_busca']:
    lista_final = st.session_state['resultados_busca']
    df = pd.DataFrame(lista_final)
    df['Data_Sort'] = pd.to_datetime(df['Data'], dayfirst=True, errors='coerce')
    
    st.divider()
    
    tab_tabela, tab_grafico = st.tabs(["📋 Tabela Detalhada", "📊 Dashboard & Gráficos"])
    
    # === ABA 1: TABELA DETALHADA ===
    with tab_tabela:
        total_geral = df['Valor Float'].sum()
        total_geral_fmt = formatar_moeda_br(total_geral)
        
        st.markdown(f"### 📋 Registros Encontrados: {len(df)} | Valor Total dos Aditivos no Período: :green[{total_geral_fmt}]")
        
        # Lógica de Ordenação Atualizada
        if "Valor" in criterio_ordem: 
            df_view = df.sort_values(by="Valor Float", ascending=False)
        elif "Contratante" in criterio_ordem: 
            df_view = df.sort_values(by="Órgão", ascending=True)
        elif "Contratado" in criterio_ordem: # Nova Lógica
            df_view = df.sort_values(by="Contratado(a)", ascending=True)
        else: 
            df_view = df.sort_values(by=['Data_Sort', 'Link'])

        st.dataframe(
            df_view[["Data", "Órgão", "Contratado(a)", "Tipo", "Valor Formatado", "Objeto", "Link"]],
            column_config={
                "Data": st.column_config.TextColumn("Data Publicação", width="small"),
                "Valor Formatado": st.column_config.TextColumn("Valor (R$)", width="medium"),
                "Link": st.column_config.LinkColumn("PDF", display_text="📄 Abrir"),
                "Objeto": st.column_config.TextColumn("Objeto", width="large"),
                "Órgão": st.column_config.TextColumn("Órgão", width="medium"),
                "Contratado(a)": st.column_config.TextColumn("Contratado(a)", width="medium"),
            },
            hide_index=True,
            use_container_width=True,
            height=600
        )
        
        df_csv = df_view.copy()
        df_csv['Valor Excel'] = df_csv['Valor Float'].apply(lambda x: str(x).replace('.', ','))
        csv_data = df_csv[["Data", "Órgão", "Contratado(a)", "Tipo", "Valor Excel", "Objeto", "Link"]].to_csv(index=False, sep=';', encoding='utf-8-sig')
        st.download_button("📥 Baixar Tabela (.csv)", csv_data, "aditivos.csv", "text/csv")

    # === ABA 2: DASHBOARD ===
    with tab_grafico:
        st.subheader("📈 Painel de Análise")
        
        if df.empty:
            st.warning("Sem dados para gerar gráficos.")
        else:
            df_valores = df[df['Valor Float'] > 0]
            
            # 1. EVOLUÇÃO MENSAL
            df['Mes_Ano'] = df['Data_Sort'].dt.strftime('%m/%Y')
            df['Sort_Mes'] = df['Data_Sort'].dt.strftime('%Y-%m')
            
            qtd_meses = df['Mes_Ano'].nunique()
            
            if qtd_meses > 1:
                st.markdown("##### 📅 Total Acumulado por Mês")
                df_mensal = df.groupby(['Sort_Mes', 'Mes_Ano'])['Valor Float'].sum().reset_index()
                df_mensal = df_mensal.sort_values('Sort_Mes')
                
                fig_bar_mes = px.bar(
                    df_mensal, x='Mes_Ano', y='Valor Float',
                    text_auto='.2s', color_discrete_sequence=['#0e4da4']
                )
                fig_bar_mes.update_layout(xaxis_title="Mês", yaxis_title="Valor Total (R$)")
                st.plotly_chart(fig_bar_mes, use_container_width=True)

            st.divider()
            
            # 2. TOP 5 CONTRATANTES E CONTRATADOS
            col_g1, col_g2 = st.columns(2)
            
            with col_g1:
                st.markdown("##### 🏛️ Top 5 Contratantes (Órgãos)")
                if not df_valores.empty:
                    top5_orgaos = df_valores.groupby('Órgão')['Valor Float'].sum().nlargest(5).reset_index()
                    top5_orgaos['Nome Legenda'] = top5_orgaos['Órgão'].apply(lambda x: truncar_texto(x, 20))
                    
                    fig_pie1 = px.pie(
                        top5_orgaos, values='Valor Float', names='Nome Legenda', hole=0.4,
                        hover_data=['Órgão']
                    )
                    fig_pie1.update_layout(
                        legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5)
                    )
                    st.plotly_chart(fig_pie1, use_container_width=True)
                else:
                    st.info("Sem dados monetários.")

            with col_g2:
                st.markdown("##### 🏢 Top 5 Contratados (Empresas)")
                if not df_valores.empty:
                    top5_empresas = df_valores.groupby('Contratado(a)')['Valor Float'].sum().nlargest(5).reset_index()
                    top5_empresas['Nome Legenda'] = top5_empresas['Contratado(a)'].apply(lambda x: truncar_texto(x, 20))
                    
                    fig_pie2 = px.pie(
                        top5_empresas, values='Valor Float', names='Nome Legenda', hole=0.4,
                        hover_data=['Contratado(a)']
                    )
                    fig_pie2.update_layout(
                        legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5)
                    )
                    st.plotly_chart(fig_pie2, use_container_width=True)
                else:
                    st.info("Sem dados monetários.")

elif 'resultados_busca' in st.session_state and not st.session_state['resultados_busca']:
    st.warning("Pesquisa finalizada. Nenhum aditivo encontrado.")