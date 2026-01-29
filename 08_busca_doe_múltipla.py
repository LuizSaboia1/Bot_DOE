import streamlit as st
import requests
import io
from pypdf import PdfReader
from datetime import datetime, timedelta
import re
import unicodedata

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Robô Diário Oficial",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- CSS: ASSINATURA FIXA E ESTILO ---
st.markdown("""
<style>
    /* 1. ASSINATURA FIXA (POSICIONAMENTO) */
    .fixed-credit-container {
        position: fixed;
        top: 20px;       /* Distância do topo */
        left: 80px;      /* Distância da esquerda (ao lado do menu) */
        z-index: 999999; /* Fica por cima de tudo */
        
        background-color: rgba(255, 255, 255, 0.95); /* Fundo branco */
        padding: 6px 12px;
        border-radius: 8px;
        border: 1px solid #ddd;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        
        text-align: center;
        pointer-events: none; /* Deixa clicar através dele */
        line-height: 1.2;
    }
    
    .credit-text {
        font-family: 'Segoe UI', sans-serif;
        font-size: 11px;
        color: #555;
        font-weight: 600;
        display: block;
    }
    
    .credit-emoji {
        font-size: 16px;
        display: block;
        margin-top: 2px;
    }

    /* 2. MELHORIA VISUAL DO APP */
    .stApp {
        background-color: #f8f9fa;
    }

    /* Cards de Resultado */
    .stExpander {
        background-color: white;
        border-radius: 10px;
        border: 1px solid #eee;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        margin-bottom: 10px;
    }
    
    /* Botão Verde */
    div.stButton > button {
        background-color: #4CAF50;
        color: white;
        border-radius: 8px;
        border: none;
        padding: 10px 24px;
        font-size: 16px;
        font-weight: bold;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        transition: 0.3s;
        width: 100%;
    }
    div.stButton > button:hover {
        background-color: #45a049;
        box-shadow: 0 6px 8px rgba(0,0,0,0.2);
    }
</style>
""", unsafe_allow_html=True)

# --- INJEÇÃO DA ASSINATURA (HTML) ---
st.markdown(
    """
    <div class='fixed-credit-container'>
        <span class='credit-text'>Desenvolvido por<br>Luiz Sabóia</span>
        <span class='credit-emoji'>😉</span>
    </div>
    """,
    unsafe_allow_html=True
)

# --- FUNÇÕES AUXILIARES ---
def remover_acentos(texto):
    if not texto: return ""
    nfkd = unicodedata.normalize('NFKD', texto)
    return "".join([c for c in nfkd if not unicodedata.combining(c)])

def realcar_termo(linha, termo, ignorar_acentos=False):
    if not termo: return linha
    
    termo_busca = termo.lower()
    linha_busca = linha.lower()
    
    if ignorar_acentos:
        termo_busca = remover_acentos(termo_busca)
        linha_busca = remover_acentos(linha_busca)
    
    start = linha_busca.find(termo_busca)
    if start == -1:
        return linha
        
    prefixo = linha[:start]
    miolo = linha[start:start+len(termo)]
    sufixo = linha[start+len(termo):]
    
    return f"{prefixo}:orange[**{miolo}**]{sufixo}"

# --- INTERFACE ---

# Título
st.markdown("<br>", unsafe_allow_html=True) # Um pequeno espaço para não colar no topo
st.markdown("<h1 style='text-align: center; color: #2c3e50;'>⚖️ Robô Diário Oficial</h1>", unsafe_allow_html=True)
st.write("") 

# Container Principal
with st.container():
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        data_inicio = st.date_input("📅 Data Inicial", format="DD/MM/YYYY")
    with col_d2:
        data_fim = st.date_input("📅 Data Final", format="DD/MM/YYYY")

    # --- AQUI ESTÁ A ÚNICA MUDANÇA ---
    termo_1 = st.text_input("🔍 Termo Principal (Obrigatório)", placeholder="Ex: Licitação")
    
    # --- ÁREA AVANÇADA ---
    with st.expander("⚙️ Pesquisa Avançada", expanded=False):
        st.info("Configurações opcionais para refinar sua busca.")
        
        col_adv1, col_adv2 = st.columns(2)
        
        with col_adv1:
            # Mantive o exemplo do segundo termo como estava
            termo_2 = st.text_input("Segundo Termo (Opcional)", placeholder="Ex: Contratação")
            tipo_logica = st.radio("Regra de conexão:", ["E (Ambos no mesmo bloco)", "OU (Qualquer um deles)"], horizontal=True)
            
        with col_adv2:
            st.write("Filtros de Texto:")
            busca_exata = st.checkbox("Busca Exata (ignora palavras parciais)", value=False)
            ignorar_acentos = st.checkbox("Ignorar Acentos (recomendado)", value=True)

    st.write("") 
    botao_pesquisar = st.button("INICIAR PESQUISA")

# --- LÓGICA DE BUSCA ---
if botao_pesquisar:
    
    if not termo_1:
        st.warning("⚠️ O campo 'Termo Principal' é obrigatório.")
    elif data_fim < data_inicio:
        st.error("⚠️ Data Final menor que Inicial.")
    else:
        area_resultados = st.empty() 
        container_resultados = area_resultados.container()
        
        total_geral_encontrado = 0
        status_box = st.status("🚀 Iniciando os motores...", expanded=True)
        
        data_atual = data_inicio
        
        while data_atual <= data_fim:
            dia_formatado = data_atual.strftime("%d/%m/%Y")
            data_url = data_atual.strftime("%Y%m%d")
            
            status_box.update(label=f"📂 Lendo dia **{dia_formatado}**...", state="running")
            
            termos_ativos = [t for t in [termo_1, termo_2] if t]
            termos_processados = []
            for t in termos_ativos:
                t_proc = t.lower()
                if ignorar_acentos: t_proc = remover_acentos(t_proc)
                termos_processados.append(t_proc)
            
            parte = 1 
            
            while True:
                str_parte = f"{parte:02d}"
                url = f"http://imagens.seplag.ce.gov.br/PDF/{data_url}/do{data_url}p{str_parte}.pdf"
                
                try:
                    resposta = requests.get(url, timeout=10)
                    if resposta.status_code in [404, 300]: break 
                    if resposta.status_code != 200: break 
                except: break

                try:
                    arquivo_memoria = io.BytesIO(resposta.content)
                    leitor = PdfReader(arquivo_memoria)
                    
                    for num_pag, pagina in enumerate(leitor.pages):
                        texto_pag = pagina.extract_text()
                        if not texto_pag: continue
                        
                        blocos = texto_pag.split("*** *** ***")
                        
                        for idx_bloco, texto_bloco in enumerate(blocos):
                            
                            bloco_busca = texto_bloco.lower()
                            if ignorar_acentos: bloco_busca = remover_acentos(bloco_busca)
                            
                            resultados_termos = []
                            for t_proc in termos_processados:
                                encontrou_este = False
                                if busca_exata:
                                    padrao = r"\b" + re.escape(t_proc) + r"\b"
                                    if re.search(padrao, bloco_busca): encontrou_este = True
                                else:
                                    if t_proc in bloco_busca: encontrou_este = True
                                resultados_termos.append(encontrou_este)
                            
                            match_final = False
                            if "E (" in tipo_logica:
                                match_final = all(resultados_termos)
                            else:
                                match_final = any(resultados_termos)
                            
                            if match_final:
                                total_geral_encontrado += 1
                                linhas_bloco = [l.strip() for l in texto_bloco.split('\n') if l.strip()]
                                
                                with container_resultados:
                                    with st.expander(f"📌 Resultado #{total_geral_encontrado} | {dia_formatado} | Caderno {str_parte} | Pág {num_pag + 1}", expanded=False):
                                        texto_md = ""
                                        for linha in linhas_bloco:
                                            linha_pintada = realcar_termo(linha, termo_1, ignorar_acentos)
                                            if termo_2:
                                                linha_pintada = realcar_termo(linha_pintada, termo_2, ignorar_acentos)
                                            texto_md += f"{linha_pintada}  \n"
                                        st.markdown(texto_md, unsafe_allow_html=True)
                                        st.link_button(f"Abrir PDF", url)
                except:
                    pass
                parte += 1
            data_atual += timedelta(days=1)
            
        status_box.update(label="Varredura completa!", state="complete", expanded=False)
        if total_geral_encontrado == 0:
            st.info("Nenhum resultado encontrado.")
        else:
            st.success(f"✅ Encontrados **{total_geral_encontrado}** registros.")