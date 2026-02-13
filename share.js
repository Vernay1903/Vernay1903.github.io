// share.js
(function () {
  const shareBtn = document.getElementById("shareBtn");
  const copyBtn  = document.getElementById("copyBtn");
  const msgEl    = document.getElementById("shareMsg");

  if (!shareBtn && !copyBtn) return;

  function setMsg(text){
    if(!msgEl) return;
    msgEl.textContent = text || "";
    if(text){
      setTimeout(() => { msgEl.textContent = ""; }, 2500);
    }
  }

  function getShareData(){
    const url = window.location.href;
    const title = document.title || "Corte dos Esportes";
    const text = "Veja essa notícia:";
    return { title, text, url };
  }

  async function copyToClipboard(text){
    try{
      await navigator.clipboard.writeText(text);
      setMsg("Link copiado!");
      return true;
    }catch(e){
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
          // usuário cancelou ou erro
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
})();
