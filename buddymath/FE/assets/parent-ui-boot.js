(function(){
  if (document.querySelector('link[data-ui-fix]')) return;
  var l = document.createElement('link');
  l.rel = 'stylesheet';
  l.href = '/assets/ui-fix.css?v=2';
  l.setAttribute('data-ui-fix', '1');
  document.head.appendChild(l);
  document.documentElement.style.overflow = 'hidden';
  if (document.body) {
    document.body.style.overflow = 'hidden';
    document.body.style.maxHeight = '100dvh';
  }
})();
