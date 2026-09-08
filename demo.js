// DEMO — Integração entre o modal "Ler Docs" e o modal "Adicionar Nova NF"
// Isto é uma simulação isolada. No Rota Sirius de verdade, os seletores
// de campo (#nf-numero, #nf-cep, etc.) serão os que já existem lá —
// isso aqui é só para validar o FLUXO antes de mexer no sistema real.

const API_URL = "http://127.0.0.1:5000/upload";

// ---------------------------------------------------------------------
// Elementos: modais
// ---------------------------------------------------------------------

const modalNovaNF = document.getElementById("modal-nova-nf");
const modalLerDocs = document.getElementById("modal-ler-docs");

const btnAbrirNovaNF = document.getElementById("btn-abrir-nova-nf");
const btnFecharNF = document.getElementById("btn-fechar-nf");
const btnLerDocs = document.getElementById("btn-ler-docs");
const btnFecharLerDocs = document.getElementById("btn-fechar-ler-docs");

btnAbrirNovaNF.addEventListener("click", () => {
  modalNovaNF.classList.remove("hidden");
});

btnFecharNF.addEventListener("click", () => {
  modalNovaNF.classList.add("hidden");
});

btnLerDocs.addEventListener("click", () => {
  resetarModalLeitura();
  modalLerDocs.classList.remove("hidden");
});

btnFecharLerDocs.addEventListener("click", () => {
  modalLerDocs.classList.add("hidden");
});

// ---------------------------------------------------------------------
// Toggle Transporte / Retira (dentro do modal Nova NF)
// ---------------------------------------------------------------------

const toggleButtons = document.querySelectorAll(".toggle-btn");
toggleButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    toggleButtons.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
  });
});

function setTipoOperacao(tipo) {
  toggleButtons.forEach((b) => {
    b.classList.toggle("active", b.dataset.tipo === tipo);
  });
}

// ---------------------------------------------------------------------
// Lógica de leitura do PDF (igual ao LEITOR DOC original)
// ---------------------------------------------------------------------

const fileInput = document.getElementById("file-input");
const btnLerDoc = document.getElementById("btn-ler-doc");
const fileNameEl = document.getElementById("file-name");

const uploadSection = document.getElementById("upload-section");
const loadingSection = document.getElementById("loading-section");
const errorSection = document.getElementById("error-section");
const errorMessageEl = document.getElementById("error-message");
const resultSection = document.getElementById("result-section");

const fieldsGrid = document.getElementById("fields-grid");
const productsList = document.getElementById("products-list");

const btnCopiar = document.getElementById("btn-copiar");
const btnTranscrever = document.getElementById("btn-transcrever");
const btnNovaLeitura = document.getElementById("btn-nova-leitura");
const btnTentarNovamente = document.getElementById("btn-tentar-novamente");
const copyFeedback = document.getElementById("copy-feedback");

let ultimoResultado = null;

const CAMPOS = [
  { chave: "numero_nf", rotulo: "Número da NF" },
  { chave: "tipo_operacao", rotulo: "Tipo de Operação" },
  { chave: "cep", rotulo: "CEP" },
  { chave: "cidade", rotulo: "Cidade" },
  { chave: "uf", rotulo: "UF" },
  { chave: "endereco", rotulo: "Endereço", wide: true },
  { chave: "numero", rotulo: "Número" },
  { chave: "valor_frete", rotulo: "Valor de Frete" },
  { chave: "quantidade", rotulo: "Quantidade" },
  { chave: "marca", rotulo: "Marca" },
  { chave: "potencia", rotulo: "Potência" },
  { chave: "kam", rotulo: "KAM" },
  { chave: "observacao", rotulo: "Observação", wide: true },
];

function resetarModalLeitura() {
  fileInput.value = "";
  fileNameEl.textContent = "";
  ultimoResultado = null;
  copyFeedback.classList.add("hidden");
  mostrarEstado("upload");
}

function mostrarEstado(estado) {
  uploadSection.classList.add("hidden");
  loadingSection.classList.add("hidden");
  errorSection.classList.add("hidden");
  resultSection.classList.add("hidden");

  if (estado === "upload") uploadSection.classList.remove("hidden");
  if (estado === "loading") loadingSection.classList.remove("hidden");
  if (estado === "error") errorSection.classList.remove("hidden");
  if (estado === "result") resultSection.classList.remove("hidden");
}

btnLerDoc.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  if (!file) return;
  fileNameEl.textContent = file.name;
  enviarArquivo(file);
});

btnTentarNovamente.addEventListener("click", () => mostrarEstado("upload"));

btnNovaLeitura.addEventListener("click", () => {
  resetarModalLeitura();
});

async function enviarArquivo(file) {
  mostrarEstado("loading");
  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await fetch(API_URL, { method: "POST", body: formData });
    if (!response.ok) throw new Error(`Erro do servidor (status ${response.status})`);
    const data = await response.json();
    if (data.erro) {
      exibirErro(data.erro);
      return;
    }
    ultimoResultado = data;
    exibirResultado(data);
  } catch (err) {
    exibirErro(
      "Não foi possível conectar ao servidor Python. Verifique se o backend " +
      "está rodando (python app.py) na porta 5000. Detalhe: " + err.message
    );
  }
}

function exibirErro(mensagem) {
  errorMessageEl.textContent = mensagem;
  mostrarEstado("error");
}

function exibirResultado(data) {
  fieldsGrid.innerHTML = "";

  CAMPOS.forEach(({ chave, rotulo, wide }) => {
    const valorBruto = data[chave];
    const temValor = valorBruto !== null && valorBruto !== undefined && valorBruto !== "";

    const fieldEl = document.createElement("div");
    fieldEl.className = "field" + (wide ? " wide" : "");

    const labelEl = document.createElement("span");
    labelEl.className = "field-label";
    labelEl.textContent = rotulo;

    const valueEl = document.createElement("span");

    if (chave === "tipo_operacao" && temValor) {
      valueEl.className = "field-value " + (valorBruto === "Retira" ? "tag-retira" : "tag-transporte");
      valueEl.textContent = valorBruto;
    } else if (temValor) {
      valueEl.className = "field-value";
      valueEl.textContent = valorBruto;
    } else {
      valueEl.className = "field-value empty";
      valueEl.textContent = "Não identificado";
    }

    fieldEl.appendChild(labelEl);
    fieldEl.appendChild(valueEl);
    fieldsGrid.appendChild(fieldEl);
  });

  productsList.innerHTML = "";
  const produtos = data.produtos_identificados || [];
  if (produtos.length === 0) {
    const li = document.createElement("li");
    li.className = "empty-state";
    li.textContent = "Nenhum produto identificado neste documento.";
    productsList.appendChild(li);
  } else {
    produtos.forEach((produto) => {
      const li = document.createElement("li");
      li.textContent = produto;
      productsList.appendChild(li);
    });
  }

  copyFeedback.classList.add("hidden");
  mostrarEstado("result");
}

btnCopiar.addEventListener("click", async () => {
  if (!ultimoResultado) return;
  const linhas = CAMPOS.map(({ chave, rotulo }) => {
    const valor = ultimoResultado[chave];
    const valorExibido = valor && valor !== "" ? valor : "Não identificado";
    return `${rotulo}: ${valorExibido}`;
  });
  const resumo = linhas.join("\n");
  try {
    await navigator.clipboard.writeText(resumo);
    copyFeedback.classList.remove("hidden");
    setTimeout(() => copyFeedback.classList.add("hidden"), 3000);
  } catch (err) {
    alert("Não foi possível copiar automaticamente. Copie manualmente:\n\n" + resumo);
  }
});

// ---------------------------------------------------------------------
// TRANSCREVER — o coração da integração:
// fecha o modal de leitura e preenche o modal de Nova NF
// ---------------------------------------------------------------------

btnTranscrever.addEventListener("click", () => {
  if (!ultimoResultado) return;
  preencherFormularioNovaNF(ultimoResultado);
  modalLerDocs.classList.add("hidden"); // fecha SÓ o modal de leitura
  // O modal de Nova NF continua aberto, com os campos preenchidos.
});

function destacarCampo(el) {
  if (!el) return;
  el.classList.remove("field-filled");
  void el.offsetWidth; // força reflow pra reiniciar a animação
  el.classList.add("field-filled");
}

function preencherFormularioNovaNF(dados) {
  const set = (id, valor) => {
    const el = document.getElementById(id);
    if (!el) return;
    if (valor !== undefined && valor !== null && valor !== "") {
      el.value = valor;
      destacarCampo(el);
    }
  };

  set("nf-numero", dados.numero_nf);
  set("nf-cep", dados.cep);
  set("nf-cidade", dados.cidade);
  set("nf-endereco", dados.endereco);
  set("nf-numero-casa", dados.numero);
  set("nf-frete", dados.valor_frete);
  set("nf-quantidade", dados.quantidade);
  set("nf-marca", dados.marca);
  set("nf-potencia", dados.potencia);
  set("nf-observacao", dados.observacao);

  // UF: campo é um <select>, precisa selecionar a opção certa
  if (dados.uf) {
    const ufSelect = document.getElementById("nf-uf");
    ufSelect.value = dados.uf;
    destacarCampo(ufSelect);
  }

  // Tipo de operação: ativa o botão certo (Transporte/Retira)
  if (dados.tipo_operacao) {
    setTipoOperacao(dados.tipo_operacao);
  }

  // KAM: também é <select> — tenta encontrar a opção com o nome lido.
  // Se o KAM não existir na lista (nome diferente/não cadastrado),
  // deixamos como está para seleção manual, sem inventar.
  if (dados.kam) {
    const kamSelect = document.getElementById("nf-kam");
    const opcaoExiste = Array.from(kamSelect.options).some(
      (opt) => opt.value.toLowerCase() === dados.kam.toLowerCase()
    );
    if (opcaoExiste) {
      kamSelect.value = dados.kam;
      destacarCampo(kamSelect);
    }
  }
}
