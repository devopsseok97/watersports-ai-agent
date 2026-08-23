(function(){
  function qs(id){ return document.getElementById(id); }
  function esc(value){
    return String(value || '')
      .replace(/&/g,'&amp;')
      .replace(/</g,'&lt;')
      .replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;');
  }
  function won(value){
    return (Number(value) || 0).toLocaleString('ko-KR') + '원';
  }
  function fmtDateTime(value){
    if(!value) return '-';
    const d = new Date(value);
    return d.toLocaleString('ko-KR',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});
  }
  function todayLabel(){
    const d = new Date();
    return d.toLocaleDateString('ko-KR',{month:'long',day:'numeric',weekday:'short'});
  }
  function applyTheme(theme){
    const dark = theme === 'dark';
    document.documentElement.toggleAttribute('data-theme', dark);
    const btn = qs('themebtn') || qs('tbtn');
    if(btn) btn.textContent = dark ? '밝게' : '어둡게';
  }
  function toggleTheme(){
    const cur = document.documentElement.hasAttribute('data-theme') ? 'dark' : 'light';
    const next = cur === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem('dash_theme', next); } catch(e) {}
    applyTheme(next);
    return next;
  }
  function initTheme(buttonId){
    let theme = 'light';
    try { theme = localStorage.getItem('dash_theme') || 'light'; } catch(e) {}
    applyTheme(theme);
    const btn = buttonId ? qs(buttonId) : (qs('themebtn') || qs('tbtn'));
    if(btn) btn.addEventListener('click', function(){ toggleTheme(); });
  }
  window.SurfAdmin = { qs, esc, won, fmtDateTime, todayLabel, applyTheme, toggleTheme, initTheme };
})();
