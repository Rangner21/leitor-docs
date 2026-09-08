"""
LEITOR DOC - Backend V1
------------------------
Servidor local em Python (Flask) responsável por:
1. Receber um PDF de Ordem de Produção (OP) enviado pelo frontend.
2. Extrair o texto do PDF (via pypdf).
3. Tentar identificar os campos pedidos, usando regras de texto (regex).
4. Devolver um JSON estruturado para o JavaScript exibir na tela.

IMPORTANTE:
- Este backend NÃO inventa dados. Quando um campo não é encontrado,
  ele retorna string vazia "" e o frontend mostra "Não identificado".
- Não há banco de dados, não há login, não há Supabase nesta V1.
- Este projeto é totalmente separado do Rota Sirius.
"""

import io
import re
import unicodedata

from flask import Flask, request, jsonify
from flask_cors import CORS
from pypdf import PdfReader

app = Flask(__name__)
CORS(app)  # permite que o index.html (aberto via Go Live) chame este servidor


# ---------------------------------------------------------------------------
# Utilidades de texto
# ---------------------------------------------------------------------------

def strip_accents(text: str) -> str:
    """Remove acentos para facilitar comparações (RETIRA vs Retira, etc.)."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def extract_pdf_text(file_bytes: bytes) -> str:
    """Extrai todo o texto selecionável do PDF usando pypdf."""
    reader = PdfReader(io.BytesIO(file_bytes))
    pages_text = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages_text.append(text)
    return "\n".join(pages_text)


def find_first(pattern: str, text: str, flags=re.IGNORECASE):
    """Retorna o primeiro grupo de captura encontrado, ou None."""
    match = re.search(pattern, text, flags)
    if match:
        return match.group(1).strip()
    return None


# ---------------------------------------------------------------------------
# Extração de cada campo
# ---------------------------------------------------------------------------

def extract_nf(text: str) -> str:
    """Procura 'Nro. Nota: 875' ou variações (Nota Fiscal, NF, etc.)."""
    patterns = [
        r"Nro\.?\s*Nota[:\s]+(\d+)",
        r"N[uú]mero\s+da\s+NF[:\s]+(\d+)",
        r"Nota\s+Fiscal[:\s]+n?[ºo°]?\s*(\d+)",
        r"\bNF[:\s]+(\d+)",
    ]
    for pattern in patterns:
        result = find_first(pattern, text)
        if result:
            return result
    return ""


def detect_operation_type(text: str) -> str:
    """
    Detecta se a OP indica RETIRA ou FRETE.
    Retorna "Retira", "Transporte" ou "" se não identificado.
    """
    clean = strip_accents(text).upper()

    # Procura por marcações explícitas de tipo de operação/entrega.
    # Não exigimos que a palavra esteja isolada (sem \b), porque a extração
    # do texto do PDF às vezes cola "RETIRA"/"FRETE" em palavras vizinhas
    # sem espaço (mesmo problema visto na captura da marca do módulo).
    if "RETIRA" in clean:
        return "Retira"
    if "FRETE" in clean:
        return "Transporte"
    return ""


def extract_address_block(text: str, is_retira: bool):
    """
    Extrai CEP, cidade, UF, endereço e número.
    Se for RETIRA, todos os campos de endereço ficam vazios (regra de negócio).
    """
    empty = {"cep": "", "cidade": "", "uf": "", "endereco": "", "numero": ""}

    if is_retira:
        return empty

    result = dict(empty)

    # CEP no formato 00000-000 ou 00000000
    cep = find_first(r"CEP[:\s]*([\d]{5}-?[\d]{3})", text)
    if not cep:
        cep = find_first(r"\b(\d{5}-\d{3})\b", text)
    if cep:
        result["cep"] = cep

    # Cidade + UF costumam vir juntos no formato "AQUIRAZ-CE" ou "AQUIRAZ/CE".
    cidade_uf = re.search(
        r"Cidade[:\s]*([A-Za-zÀ-ÿ\s]+?)\s*[-/]\s*([A-Za-z]{2})\b", text, re.IGNORECASE
    )
    if cidade_uf:
        result["cidade"] = cidade_uf.group(1).strip()
        result["uf"] = cidade_uf.group(2).strip().upper()
    else:
        # Formatos alternativos: "Cidade:" e "UF:" em campos separados
        cidade = find_first(r"Cidade[:\s]*([A-Za-zÀ-ÿ\s]+?)(?:\n|,)", text)
        if cidade:
            result["cidade"] = cidade.strip()

        uf = find_first(r"\bUF[:\s]*([A-Za-z]{2})\b", text)
        if uf:
            result["uf"] = uf.upper()

    # Endereço (rua/avenida) + número.
    # Pega a linha inteira que contém "Endereço" e usa o texto após o
    # último ":" da linha (cobre formatos como "Endereço do cliente: Av. X, 500").
    # Exige ":" logo após "Endereço" para não confundir com títulos/seções
    # como "Endereço Entrega" (sem dois-pontos), pegando só o campo de fato.
    endereco_line = find_first(r"Endere[cç]o\s*:\s*(.+)", text)
    if endereco_line:
        # Remove eventual número de CEP que tenha ficado colado na linha
        endereco_limpo = re.sub(r"\d{5}-?\d{3}", "", endereco_line).strip(" ,-")
        if endereco_limpo:
            result["endereco"] = endereco_limpo

    numero = find_first(r"N[uú]mero[:\s]*(\d+)", text)
    if not numero:
        # Fallback: número solto ao final da linha de endereço (ex: "Av. X, 500")
        numero = find_first(r"Endere[cç]o.*?,\s*(\d+)\b", text)
    if numero:
        result["numero"] = numero
    elif result["endereco"] and re.search(r"\bS\s*/?\s*N\b", result["endereco"], re.IGNORECASE):
        # "S/N" no endereço significa "sem número" — mostrar isso explicitamente
        # no campo Número, e tirar a repetição do texto do Endereço.
        result["numero"] = "S/N"
        result["endereco"] = re.sub(
            r",?\s*S\s*/?\s*N\b", "", result["endereco"], flags=re.IGNORECASE
        ).strip(" ,-")

    return result


def extract_module_block(text: str) -> str:
    """
    Isola o trecho do texto referente ao MÓDULO FOTOVOLTAICO,
    para que quantidade/potência/marca sejam lidos apenas dessa linha/bloco
    e não de inversores, cabos, trilhos, etc.
    """
    match = re.search(
        r"M[ÓO]DULO\s+FOTOVOLTAICO.{0,200}", text, re.IGNORECASE | re.DOTALL
    )
    if match:
        return match.group(0)
    return ""


def extract_quantidade(module_block: str) -> str:
    """
    Extrai a quantidade apenas do bloco do módulo fotovoltaico.
    Cobre dois formatos:
    - "Quantidade: 9 UN" (rótulo explícito)
    - "UN 2,000000" (linha de tabela: unidade seguida da quantidade,
      com vírgula decimal, como em relatórios de composição de produção)
    """
    if not module_block:
        return ""

    # Formato com rótulo explícito
    qty = find_first(r"Quantidade[:\s]*(\d+)", module_block)
    if qty:
        return qty

    # Formato de tabela: "UN 2,000000" -> pega a parte inteira antes da vírgula
    match = re.search(r"\bUN\s+(\d+)[.,]\d+", module_block)
    if match:
        return match.group(1)

    # Formato simples "9 UN"
    qty = find_first(r"\b(\d+)\s*UN\b", module_block)
    if qty:
        return qty

    return ""


def extract_potencia(module_block: str) -> str:
    """Extrai a potência (ex: 650W) do bloco do módulo."""
    if not module_block:
        return ""
    pot = find_first(r"(\d{3,4}\s?W)\b", module_block, flags=re.IGNORECASE)
    if pot:
        return pot.replace(" ", "").upper()
    return ""


def extract_marca(module_block: str) -> str:
    """
    Tenta identificar a marca a partir da descrição do módulo.
    Regra observada no documento de teste: 'BIFACIAL Z' -> Marca = Z.
    Procuramos um token curto (letras/números) logo após a palavra BIFACIAL.
    Se não for possível identificar com segurança, retorna vazio.
    """
    if not module_block:
        return ""

    # Captura apenas letras logo após "BIFACIAL", parando no primeiro dígito.
    # Isso cobre tanto "BIFACIAL Z 3448" (com espaço) quanto "BIFACIAL Z3448"
    # (quando a extração do PDF cola a marca com o código do produto).
    match = re.search(r"BIFACIAL\s*([A-Za-zÀ-ÿ]+)", module_block, re.IGNORECASE)
    if match:
        candidate = match.group(1).strip()
        if candidate.upper() not in {"UN", "W", "PLUS"}:
            return candidate.upper()

    return ""


def extract_kam(text: str) -> str:
    """
    Extrai o KAM. Exemplo no documento: 'KAM: 5 - igor.pontes'
    Resultado esperado: 'Igor Pontes'
    """
    raw = find_first(r"KAM[:\s]*\d*\s*-?\s*([a-zA-Z._]+)", text)
    if not raw:
        return ""

    # 'igor.pontes' -> ['igor', 'pontes'] -> 'Igor Pontes'
    parts = re.split(r"[._\s]+", raw)
    parts = [p for p in parts if p]
    nome_formatado = " ".join(p.capitalize() for p in parts)
    return nome_formatado


def extract_observacao(text: str) -> str:
    """Procura um campo de observação explícito. Se não houver, retorna vazio."""
    obs = find_first(r"Observa[cç][ãa]o[:\s]*(.+)", text)
    return obs.strip() if obs else ""


def extract_products_list(text: str):
    """
    Extrai uma lista simples de linhas que parecem ser produtos,
    apenas para exibição em 'PRODUTOS IDENTIFICADOS' (conferência manual).
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    keywords = [
        "MODULO", "MÓDULO", "INVERSOR", "CABO", "GRAMPO",
        "TRILHO", "CONECTOR", "ESTRUTURA", "PARAFUSO",
    ]
    produtos = []
    for line in lines:
        clean_line = strip_accents(line).upper()
        if any(k in clean_line for k in [strip_accents(k).upper() for k in keywords]):
            produtos.append(line)
    return produtos


# ---------------------------------------------------------------------------
# Rota principal
# ---------------------------------------------------------------------------

@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"erro": "Nenhum arquivo enviado."}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"erro": "Nome de arquivo vazio."}), 400

    try:
        file_bytes = file.read()
        text = extract_pdf_text(file_bytes)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"erro": f"Falha ao ler o PDF: {exc}"}), 500

    if not text.strip():
        return jsonify({
            "erro": (
                "Não foi possível extrair texto selecionável deste PDF. "
                "Ele pode ser uma imagem escaneada (será necessário OCR em versão futura)."
            )
        }), 200

    tipo_operacao = detect_operation_type(text)
    is_retira = tipo_operacao == "Retira"

    endereco_info = extract_address_block(text, is_retira)
    module_block = extract_module_block(text)

    resultado = {
        "numero_nf": extract_nf(text),
        "tipo_operacao": tipo_operacao,  # "Retira", "Transporte" ou ""
        "cep": endereco_info["cep"],
        "cidade": endereco_info["cidade"],
        "uf": endereco_info["uf"],
        "endereco": endereco_info["endereco"],
        "numero": endereco_info["numero"],
        "valor_frete": "R$ 0,00" if is_retira else "",
        "quantidade": extract_quantidade(module_block),
        "marca": extract_marca(module_block),
        "potencia": extract_potencia(module_block),
        "kam": extract_kam(text),
        "observacao": extract_observacao(text),
        "produtos_identificados": extract_products_list(text),
        "texto_bruto": text,  # útil para depuração durante os testes da V1
    }

    return jsonify(resultado)


@app.route("/", methods=["GET"])
def health_check():
    return jsonify({"status": "LEITOR DOC backend rodando."})


if __name__ == "__main__":
    print("=" * 60)
    print("LEITOR DOC - Backend iniciado")
    print("Acesse: http://127.0.0.1:5000")
    print("Aguardando requisições do frontend (index.html via Go Live)...")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5000, debug=True)
