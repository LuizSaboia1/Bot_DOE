import streamlit as st
import requests
import io
from pypdf import PdfReader
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Robô Diário Oficial",
    page_icon="⚖️",
    layout="wide" # Usa a tela inteira, melhor para ler textos longos
)

# --- FUNÇÕES AUXILIARES ---

def realcar_termo(linha, termo):
    """
    Substitui o termo encontrado por uma versão colorida e negrito em Markdown.
    Ex: "lei municipal" vira ":orange[**lei municipal**]"
    """
    termo_lower = termo.lower()
    linha_lower = linha.lower()
    
    start = linha_lower.find(termo_lower)
    if start == -1:
        return linha
        
    # Recorta mantendo a caixa original (maiúscula/minúscula)
    prefixo = linha[:start]
    miolo = linha[start:start+len(termo)]
    sufixo = linha[start+len(termo):]
    
    # Sintaxe do Streamlit para cor: :cor[texto]
    return f"{prefixo}:orange[**{miolo}**]{sufixo}"

# --- INTERFACE (FRONT-END) ---

st.title("⚖️ Busca no Diário Oficial do Ceará")
st.markdown("Digite a data e o termo abaixo. O sistema buscará em **todos os cadernos** disponíveis.")

# Formulário para agrupar os inputs e o botão
with st.form("form_busca"):
    col1, col2 = st.columns([1, 3]) # Coluna 1 menor (Data), Coluna 2 maior (Termo)
    
    with col1:
        # O Streamlit já te dá um calendário visual!
        data_selecionada = st.date_input("Selecione a Data", format="DD/MM/YYYY")
    
    with col2:
        termo_busca = st.text_input("Termo ou Frase", placeholder="Ex: licitação, pregão, nome de pessoa...")
    
    # Botão de envio
    botao_pesquisar = st.form_submit_button("🔍 Iniciar Pesquisa")

# --- LÓGICA (BACK-END) ---

if botao_pesquisar:
    if not termo_busca:
        st.warning("Por favor, digite um termo para buscar.")
    else:
        # Formata a data para o padrão da URL (YYYYMMDD)
        # O date_input devolve um objeto 'date', convertemos para string
        data_formatada = data_selecionada.strftime("%Y%m%d")
        dia_formatado = data_selecionada.strftime("%d/%m/%Y")
        
        termo_lower = termo_busca.lower()
        parte = 1
        encontrou_total = 0
        
        # Área de Status (Feedback visual animado)
        status_box = st.status(f"Iniciando busca em {dia_formatado}...", expanded=True)
        
        # Container para os resultados (para eles aparecerem organizados)
        resultados_container = st.container()

        try:
            while True:
                str_parte = f"{parte:02d}"
                url = f"http://imagens.seplag.ce.gov.br/PDF/{data_formatada}/do{data_formatada}p{str_parte}.pdf"
                
                status_box.update(label=f"Baixando e analisando Caderno {str_parte}...")
                
                # Requisição
                try:
                    resposta = requests.get(url, timeout=15)
                    if resposta.status_code == 404:
                        break # Acabaram os cadernos
                    if resposta.status_code != 200:
                        status_box.write(f"⚠️ Erro ao acessar caderno {str_parte}: Código {resposta.status_code}")
                        break
                except Exception as e:
                    st.error(f"Erro de conexão: {e}")
                    break

                # Processamento do PDF
                arquivo_memoria = io.BytesIO(resposta.content)
                leitor = PdfReader(arquivo_memoria)
                
                for num_pag, pagina in enumerate(leitor.pages):
                    texto_original = pagina.extract_text()
                    if not texto_original: continue
                    
                    linhas = texto_original.split('\n')
                    
                    i = 0
                    while i < len(linhas):
                        linha_atual = linhas[i]
                        
                        if termo_lower in linha_atual.lower():
                            encontrou_total += 1
                            
                            # Definição da Janela Visual (Contexto)
                            LINHAS_ANTES = 4
                            LINHAS_DEPOIS = 8
                            
                            inicio = max(0, i - LINHAS_ANTES)
                            fim = min(len(linhas), i + LINHAS_DEPOIS + 1)
                            bloco = linhas[inicio:fim]
                            
                            # --- MONTAGEM DO CARD DE RESULTADO ---
                            with resultados_container:
                                with st.expander(f"📌 Ocorrência #{encontrou_total} | Caderno {str_parte} - Pág {num_pag + 1}", expanded=True):
                                    
                                    # Monta o texto formatado linha a linha
                                    texto_final_md = ""
                                    for idx_bloco, texto_linha in enumerate(bloco):
                                        idx_real = idx_bloco + inicio
                                        
                                        # Se for a linha do termo, realça. Se não, deixa cinza (contexto)
                                        if idx_real == i:
                                            linha_md = realcar_termo(texto_linha, termo_busca)
                                            # Adiciona uma seta para indicar a linha
                                            texto_final_md += f"> {linha_md}  \n" 
                                        else:
                                            # Texto cinza para contexto
                                            texto_final_md += f"<span style='color:gray'>{texto_linha}</span>  \n"
                                    
                                    # Exibe o texto formatado (permite HTML para o cinza)
                                    st.markdown(texto_final_md, unsafe_allow_html=True)
                                    
                                    # Botão para abrir o PDF direto
                                    st.link_button(f"Abrir PDF Original (Pág {num_pag+1})", url)
                            
                            # Pula o loop para não repetir o mesmo contexto
                            i = fim
                        else:
                            i += 1
                
                parte += 1
            
            # Finalização
            status_box.update(label="Busca Finalizada!", state="complete", expanded=False)
            
            if encontrou_total == 0:
                st.info(f"Nenhuma ocorrência encontrada para '{termo_busca}' na data {dia_formatado}.")
            else:
                st.success(f"Busca completa! Foram encontradas **{encontrou_total}** ocorrências.")

        except Exception as e:
            st.error(f"Erro crítico no sistema: {e}")
            
            # --- RODAPÉ DA BARRA LATERAL ---
with st.sidebar:
    st.markdown("---") # Cria uma linha divisória visual
    st.markdown(
        """
        <div style='text-align: center; font-size: 12px; color: gray;'>
            Desenvolvido por <b>Luiz Saboia</b> 🚀<br>
            <i>Versão 1.0</i>
        </div>
        """,
        unsafe_allow_html=True # Permite usar HTML para centralizar e diminuir a letra
    )