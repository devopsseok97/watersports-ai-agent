(function(){
  function qs(id){ return document.getElementById(id); }
  var activeThemeButtonId = null;
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
  function themeButton(){
    return (activeThemeButtonId && qs(activeThemeButtonId)) || qs('themebtn') || qs('tbtn');
  }
  function applyTheme(theme){
    const dark = theme === 'dark';
    if(dark){
      document.documentElement.setAttribute('data-theme', 'dark');
    } else {
      document.documentElement.removeAttribute('data-theme');
    }
    const btn = themeButton();
    if(btn){
      var label = dark ? '밝게' : '어둡게';
      btn.setAttribute('aria-label', label);
      btn.setAttribute('title', label);
      // 아이콘 버튼(SVG 포함)이면 텍스트를 덮어쓰지 않는다
      if(!btn.querySelector('svg')) btn.textContent = label;
    }
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
    activeThemeButtonId = buttonId || null;
    applyTheme(theme);
    const btn = themeButton();
    if(btn) btn.addEventListener('click', function(){ toggleTheme(); });
  }
  window.SurfAdmin = { qs, esc, won, fmtDateTime, todayLabel, applyTheme, toggleTheme, initTheme };
})();
