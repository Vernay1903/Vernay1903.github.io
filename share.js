// share.js
(function () {

  /* =========================================
     BUSCA DO SITE
  ========================================= */

  function initSiteSearch() {
    const menu = document.getElementById("sportsMenu");

    if (!menu) return;

    // Evita criar duas vezes
    if (document.getElementById("siteSearchForm")) return;

    const form = document.createElement("form");
    form.className = "site-search";
    form.id = "siteSearchForm";
    form.action = "/buscar.html";
    form.method = "get";
    form.setAttribute("role", "search");

    const label = document.createElement("label");
    label.className = "site-search-label";
    label.setAttribute("for", "siteSearchInput");
    label.textContent = "Buscar no Corte dos Esportes";

    const input = document.createElement("input");
    input.className = "site-search-input";
    input.id = "siteSearchInput";
    input.type = "search";
    input.name = "q";
    input.placeholder = "Buscar no site...";
    input.autocomplete = "off";
    input.setAttribute("aria-label", "Buscar no Corte dos Esportes");

    // Se estiver na página de busca, mantém o termo pesquisado
    try {
      const params = new URLSearchParams(window.location.search);
      const currentQuery = params.get("q");

      if (currentQuery) {
        input.value = currentQuery;
      }
    } catch (e) {
      // Não interfere caso o navegador não suporte
    }

    const button = document.createElement("button");
    button.className = "site-search-button";
    button.type = "submit";
    button.textContent = "Buscar";

    form.appendChild(label);
    form.appendChild(input);
    form.appendChild(button);

    // Entra como último item do menu, depois de Tênis
    menu.appendChild(form);
  }


  /* =========================================
     COMPARTILHAMENTO
  ========================================= */

  function initShare() {
    const shareBtn = document.getElementById("shareBtn");
    const copyBtn  = document.getElementById("copyBtn");
    const msgEl    = document.getElementById("shareMsg");

    if (!shareBtn && !copyBtn) return;

    function setMsg(text) {
      if (!msgEl) return;

      msgEl.textContent = text || "";

      if (text) {
        setTimeout(() => {
          msgEl.textContent = "";
        }, 2500);
      }
    }

    function getShareData() {
      const url = window.location.href;
      const title = document.title || "Corte dos Esportes";
      const text = "Veja essa notícia:";

      return { title, text, url };
    }

    async function copyToClipboard(text) {
      try {
        await navigator.clipboard.writeText(text);
        setMsg("Link copiado!");
        return true;
      } catch (e) {
        setMsg("Copie o link manualmente.");
        return false;
      }
    }

    if (shareBtn) {
      shareBtn.addEventListener("click", async () => {
        const data = getShareData();

        if (navigator.share) {
          try {
            await navigator.share(data);
            setMsg("Compartilhado!");
          } catch (e) {
            // Usuário cancelou ou ocorreu erro
          }
        } else {
          await copyToClipboard(data.url);
        }
      });
    }

    if (copyBtn) {
      copyBtn.addEventListener("click", async () => {
        await copyToClipboard(window.location.href);
      });
    }
  }


  /* =========================================
     INICIALIZAÇÃO
  ========================================= */

  function init() {
    initSiteSearch();
    initShare();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

})();
