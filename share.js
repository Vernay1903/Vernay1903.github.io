// share.js
(function () {

  /* =========================================
     GOOGLE ANALYTICS
  ========================================= */

  function initAnalytics() {
    const measurementId = "G-ZTYJ0TYZYC";

    // Evita carregar/configurar a mesma tag duas vezes
    const existingTag = document.querySelector(
      'script[src*="googletagmanager.com/gtag/js?id=' + measurementId + '"]'
    );

    if (existingTag) return;

    window.dataLayer = window.dataLayer || [];

    window.gtag = window.gtag || function () {
      window.dataLayer.push(arguments);
    };

    const script = document.createElement("script");
    script.async = true;
    script.src =
      "https://www.googletagmanager.com/gtag/js?id=" +
      encodeURIComponent(measurementId);

    document.head.appendChild(script);

    window.gtag("js", new Date());
    window.gtag("config", measurementId);
  }


  /* =========================================
     TESTE CLEVER ADVERTISING — REMOVER APÓS 24 HORAS
  ========================================= */

  function initCleverAdvertising() {
    // A homepage já possui o script diretamente no index.html.
    // Evita duplicar a publicidade nessa página.
    if (
      document.getElementById("clever-core") ||
      document.getElementById("CleverCoreLoader107238")
    ) return;

    const frame = window.frameElement;
    const script = document.createElement("script");

    script.id = "CleverCoreLoader107238";
    script.src = "https://scripts.cleverwebserver.com/567b728004b82e4aea26086072ee6e59.js";
    script.async = true;
    script.type = "text/javascript";
    script.setAttribute("data-target", window.name || (frame && frame.getAttribute("id")));
    script.setAttribute("data-callback", "put-your-callback-function-here");
    script.setAttribute("data-callback-url-click", "put-your-click-macro-here");
    script.setAttribute("data-callback-url-view", "put-your-view-macro-here");

    // O mesmo carregador fornecido pela Clever, nas páginas que usam share.js.
    const anchor = document.getElementsByTagName("script")[0];
    if (anchor && anchor.parentNode) {
      anchor.parentNode.insertBefore(script, anchor);
    } else {
      (document.head || document.body).appendChild(script);
    }
  }


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
    initAnalytics();
    initCleverAdvertising();
    initSiteSearch();
    initShare();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

})();
