(function(){
  'use strict';
  if(window.__HERMES_UI_PROXY_COMPAT__===1)return;
  window.__HERMES_UI_PROXY_COMPAT__=1;

  function currentScriptSource(){
    var scripts=Array.prototype.slice.call(document.querySelectorAll('script[data-hermes-ui-proxy-prefix]'));
    return scripts[scripts.length-1]||document.currentScript||null;
  }

  function proxyPrefix(){
    var source=currentScriptSource();
    var raw=source&&source.dataset?String(source.dataset.hermesUiProxyPrefix||'').trim():'';
    var prefix=raw.replace(/\/+$/,'');
    if(prefix)window.__HERMES_UI_PROXY_PREFIX__=prefix;
    return prefix;
  }

  function parseUrl(raw){
    if(raw instanceof URL)return raw;
    if(typeof raw!=='string'||!raw.trim())return null;
    try{return new URL(raw,window.location.href);}catch(_){return null;}
  }

  function shouldRewrite(parsed,prefix){
    if(!parsed||!prefix)return false;
    if(parsed.origin!==window.location.origin)return false;
    if(parsed.pathname===prefix||parsed.pathname.indexOf(prefix+'/')===0)return false;
    if(parsed.pathname.indexOf('/static/ui-proxy-compat.js')===0)return false;
    return parsed.pathname.charAt(0)==='/';
  }

  function rewriteParsed(parsed,prefix){
    if(!shouldRewrite(parsed,prefix))return null;
    return prefix+parsed.pathname+parsed.search+parsed.hash;
  }

  function rewriteHttpUrl(raw){
    var prefix=proxyPrefix();
    var parsed=parseUrl(raw);
    var rewritten=rewriteParsed(parsed,prefix);
    if(!rewritten)return raw;
    var trimmed=String(raw||'').trim();
    if(/^[a-z][a-z0-9+.-]*:/i.test(trimmed))return new URL(rewritten,window.location.origin).toString();
    return rewritten;
  }

  function rewriteNavigationUrl(raw){
    if(raw===undefined||raw===null)return raw;
    var prefix=proxyPrefix();
    var parsed=parseUrl(raw);
    if(!parsed&&typeof raw!=='string')parsed=parseUrl(String(raw));
    var rewritten=rewriteParsed(parsed,prefix);
    if(!rewritten)return raw;
    var trimmed=String(raw||'').trim();
    if(raw instanceof URL||/^[a-z][a-z0-9+.-]*:/i.test(trimmed))return new URL(rewritten,window.location.origin).toString();
    return rewritten;
  }

  function rewriteSocketUrl(raw){
    var prefix=proxyPrefix();
    var parsed=parseUrl(raw);
    var rewrittenPath=rewriteParsed(parsed,prefix);
    if(!rewrittenPath)return raw;
    var rewritten=new URL(rewrittenPath,window.location.origin);
    var trimmed=String(raw||'').trim();
    if(trimmed.indexOf('wss:')===0)rewritten.protocol='wss:';
    else if(trimmed.indexOf('ws:')===0)rewritten.protocol='ws:';
    else rewritten.protocol=window.location.protocol==='https:'?'wss:':'ws:';
    return rewritten.toString();
  }

  function appPath(){
    var prefix=proxyPrefix();
    var path=window.location.pathname||'/';
    if(prefix&&(path===prefix||path.indexOf(prefix+'/')===0))path=path.slice(prefix.length)||'/';
    return path+window.location.search+window.location.hash;
  }

  function postParent(type,payload){
    if(window.parent===window)return;
    var message=payload||{};
    message.hermesUiMode=1;
    message.type=type;
    try{window.parent.postMessage(message,window.location.origin);}catch(_){/* best effort */}
  }

  function pagePayload(reason){
    return {
      reason:reason||'',
      title:String(document.title||''),
      url:window.location.href,
      path:window.location.pathname+window.location.search+window.location.hash,
      appPath:appPath(),
      readyState:document.readyState||''
    };
  }

  var lastPageContextKey='';
  function emitPageContext(reason){
    var payload=pagePayload(reason);
    var key=[payload.title,payload.url,payload.readyState].join('\n');
    if(key===lastPageContextKey&&reason!=='request')return;
    lastPageContextKey=key;
    postParent('hermes-ui-preview-context',payload);
  }

  function schedulePageContext(reason){
    window.setTimeout(function(){emitPageContext(reason);},0);
  }

  if(typeof window.fetch==='function'){
    var nativeFetch=window.fetch.bind(window);
    window.fetch=function(input,init){
      if(typeof input==='string')return nativeFetch(rewriteHttpUrl(input),init);
      if(input instanceof Request){
        var nextUrl=rewriteHttpUrl(input.url);
        if(nextUrl!==input.url){
          try{return nativeFetch(new Request(nextUrl,input),init);}catch(_){}
        }
      }
      return nativeFetch(input,init);
    };
  }

  if(window.history&&typeof window.history.pushState==='function'){
    var nativePushState=window.history.pushState.bind(window.history);
    window.history.pushState=function(state,title,url){
      var result;
      if(arguments.length>=3)result=nativePushState(state,title,rewriteNavigationUrl(url));
      else result=nativePushState.apply(window.history,arguments);
      schedulePageContext('pushState');
      return result;
    };
  }

  if(window.history&&typeof window.history.replaceState==='function'){
    var nativeReplaceState=window.history.replaceState.bind(window.history);
    window.history.replaceState=function(state,title,url){
      var result;
      if(arguments.length>=3)result=nativeReplaceState(state,title,rewriteNavigationUrl(url));
      else result=nativeReplaceState.apply(window.history,arguments);
      schedulePageContext('replaceState');
      return result;
    };
  }

  document.addEventListener('click',function(event){
    var node=event.target;
    while(node&&node.nodeType===1&&node.tagName!=='A')node=node.parentNode;
    if(!node||node.tagName!=='A')return;
    var href=node.getAttribute('href');
    var rewritten=rewriteNavigationUrl(href);
    if(typeof rewritten==='string'&&rewritten!==href)node.setAttribute('href',rewritten);
  },true);

  var inspectorEnabled=false;
  var inspectorHoverTarget=null;
  var inspectorSelectedTargets=[];

  function cssIdent(value){
    var text=String(value||'');
    if(window.CSS&&typeof window.CSS.escape==='function')return window.CSS.escape(text);
    return text.replace(/[^a-zA-Z0-9_-]/g,function(ch){return'\\'+ch;});
  }

  function cssString(value){
    return String(value||'').replace(/\\/g,'\\\\').replace(/"/g,'\\"');
  }

  function elementClasses(el){
    if(!el||!el.classList)return '';
    var names=[];
    for(var i=0;i<el.classList.length&&names.length<3;i++){
      var name=String(el.classList[i]||'').trim();
      if(name&&name.indexOf('hermes-ui-inspector')<0)names.push(name);
    }
    return names.join(' ');
  }

  function attr(el,name){
    if(!el||!el.getAttribute)return '';
    return String(el.getAttribute(name)||'').trim();
  }

  function nthOfType(el){
    if(!el||!el.parentElement)return 1;
    var tag=el.tagName;
    var index=0;
    var children=el.parentElement.children||[];
    for(var i=0;i<children.length;i++){
      if(children[i].tagName===tag)index++;
      if(children[i]===el)return index||1;
    }
    return 1;
  }

  function selectorPart(el){
    var tag=String(el&&el.tagName||'element').toLowerCase();
    var id=attr(el,'id');
    if(id)return tag+'#'+cssIdent(id);
    var testAttr='';
    var testId='';
    if(attr(el,'data-testid')){testAttr='data-testid';testId=attr(el,'data-testid');}
    else if(attr(el,'data-test')){testAttr='data-test';testId=attr(el,'data-test');}
    else if(attr(el,'data-cy')){testAttr='data-cy';testId=attr(el,'data-cy');}
    if(testId)return tag+'['+testAttr+'="'+cssString(testId)+'"]';
    var aria=attr(el,'aria-label');
    if(aria)return tag+'[aria-label="'+cssString(aria)+'"]';
    var classes=elementClasses(el).split(/\s+/).filter(Boolean).slice(0,2);
    var part=tag;
    for(var i=0;i<classes.length;i++)part+='.'+cssIdent(classes[i]);
    if(el.parentElement){
      var same=0;
      var children=el.parentElement.children||[];
      for(var j=0;j<children.length;j++)if(children[j].tagName===el.tagName)same++;
      if(same>1)part+=':nth-of-type('+nthOfType(el)+')';
    }
    return part;
  }

  function uniqueSelector(selector){
    try{return document.querySelectorAll(selector).length===1;}catch(_){return false;}
  }

  function createSelector(el){
    if(!el||el.nodeType!==1)return '';
    var id=attr(el,'id');
    if(id){
      var idSelector='#'+cssIdent(id);
      if(uniqueSelector(idSelector))return idSelector;
    }
    var parts=[];
    var node=el;
    var depth=0;
    while(node&&node.nodeType===1&&node!==document.documentElement&&depth<6){
      parts.unshift(selectorPart(node));
      var candidate=parts.join(' > ');
      if(uniqueSelector(candidate))return candidate;
      node=node.parentElement;
      depth++;
    }
    return parts.join(' > ');
  }

  function normalizedText(value,limit){
    var text=String(value||'').replace(/\s+/g,' ').trim();
    var max=limit||180;
    return text.length>max?text.slice(0,max-1)+'…':text;
  }

  function inspectorTarget(raw){
    var node=raw;
    while(node&&node.nodeType!==1)node=node.parentNode;
    if(!node||!node.getAttribute)return null;
    if(node.getAttribute('data-hermes-ui-inspector-overlay'))return null;
    if(node.closest&&node.closest('[data-hermes-ui-inspector-overlay]'))return null;
    if(node===document.documentElement)return document.body||node;
    return node;
  }

  function overlayBox(kind){
    var selector='[data-hermes-ui-inspector-overlay="'+kind+'"]';
    var box=document.querySelector(selector);
    if(box)return box;
    box=document.createElement('div');
    box.setAttribute('data-hermes-ui-inspector-overlay',kind);
    box.setAttribute('aria-hidden','true');
    (document.body||document.documentElement).appendChild(box);
    return box;
  }

  function hideOverlay(kind){
    var box=document.querySelector('[data-hermes-ui-inspector-overlay="'+kind+'"]');
    if(box)box.style.display='none';
  }

  function hideSelectedOverlays(){
    Array.prototype.slice.call(document.querySelectorAll('[data-hermes-ui-inspector-overlay^="selected"]')).forEach(function(box){
      box.style.display='none';
    });
  }

  function drawSelectedOverlays(){
    hideSelectedOverlays();
    for(var i=0;i<inspectorSelectedTargets.length;i++)drawOverlay(inspectorSelectedTargets[i],'selected-'+i);
  }

  function drawOverlay(el,kind){
    if(!el||!el.getBoundingClientRect){hideOverlay(kind);return;}
    var rect=el.getBoundingClientRect();
    if(!rect||(!rect.width&&!rect.height)){hideOverlay(kind);return;}
    var box=overlayBox(kind);
    var selected=String(kind||'').indexOf('selected')===0;
    var color=selected?'#22c55e':'#38bdf8';
    var fill=selected?'rgba(34,197,94,.13)':'rgba(56,189,248,.10)';
    box.style.cssText='position:fixed;z-index:2147483646;pointer-events:none;box-sizing:border-box;display:block;left:'+Math.max(0,rect.left)+'px;top:'+Math.max(0,rect.top)+'px;width:'+Math.max(0,rect.width)+'px;height:'+Math.max(0,rect.height)+'px;border:2px '+(selected?'solid':'dashed')+' '+color+';background:'+fill+';border-radius:4px;box-shadow:0 0 0 1px rgba(2,6,23,.55),0 10px 30px rgba(2,6,23,.22);';
  }

  function elementDescriptor(el){
    var rect=el&&el.getBoundingClientRect?el.getBoundingClientRect():null;
    return {
      tag:String(el&&el.tagName||'').toLowerCase(),
      id:attr(el,'id'),
      className:elementClasses(el),
      selector:createSelector(el),
      role:attr(el,'role'),
      ariaLabel:attr(el,'aria-label')||attr(el,'title'),
      name:attr(el,'name'),
      type:attr(el,'type'),
      href:attr(el,'href'),
      src:attr(el,'src'),
      text:normalizedText((el&&el.innerText)||((el&&el.textContent)||''),220),
      rect:rect?{x:rect.left,y:rect.top,width:rect.width,height:rect.height}:null
    };
  }

  function selectedElementDescriptors(){
    return inspectorSelectedTargets.filter(function(el){return !!(el&&el.isConnected!==false);}).map(elementDescriptor);
  }

  function emitSelectedElements(pageReason){
    var elements=selectedElementDescriptors();
    postParent('hermes-ui-element-selected',{
      page:pagePayload(pageReason||'select'),
      element:elements.length?elements[elements.length-1]:null,
      elements:elements,
      selectionCount:elements.length
    });
  }

  function emitInspectorState(){
    postParent('hermes-ui-inspector-state',{enabled:!!inspectorEnabled,selectionCount:inspectorSelectedTargets.length});
  }

  function clearInspectorSelections(){
    inspectorSelectedTargets=[];
    hideSelectedOverlays();
    emitSelectedElements('clear');
    emitInspectorState();
  }

  function setInspectorEnabled(enabled){
    inspectorEnabled=!!enabled;
    document.documentElement.classList.toggle('hermes-ui-inspector-active',inspectorEnabled);
    if(!inspectorEnabled){
      inspectorHoverTarget=null;
      hideOverlay('hover');
    }
    emitInspectorState();
  }

  function onInspectorMove(event){
    if(!inspectorEnabled)return;
    var target=inspectorTarget(event.target);
    if(!target)return;
    inspectorHoverTarget=target;
    drawOverlay(target,'hover');
  }

  function onInspectorClick(event){
    if(!inspectorEnabled)return;
    var target=inspectorTarget(event.target||inspectorHoverTarget);
    if(!target)return;
    event.preventDefault();
    event.stopPropagation();
    if(event.stopImmediatePropagation)event.stopImmediatePropagation();
    var existing=inspectorSelectedTargets.indexOf(target);
    if(existing>=0)inspectorSelectedTargets.splice(existing,1);
    else inspectorSelectedTargets.push(target);
    drawSelectedOverlays();
    emitSelectedElements(existing>=0?'deselect':'select');
  }

  function onInspectorKeydown(event){
    if(!inspectorEnabled)return;
    if(event.key==='Escape'||event.key==='Esc'){
      event.preventDefault();
      setInspectorEnabled(false);
    }
  }

  document.addEventListener('mousemove',onInspectorMove,true);
  document.addEventListener('mouseover',onInspectorMove,true);
  document.addEventListener('click',onInspectorClick,true);
  document.addEventListener('keydown',onInspectorKeydown,true);
  window.addEventListener('scroll',function(){
    if(inspectorEnabled&&inspectorHoverTarget)drawOverlay(inspectorHoverTarget,'hover');
    drawSelectedOverlays();
  },true);
  window.addEventListener('resize',function(){
    if(inspectorEnabled&&inspectorHoverTarget)drawOverlay(inspectorHoverTarget,'hover');
    drawSelectedOverlays();
    schedulePageContext('resize');
  });

  window.addEventListener('message',function(event){
    if(event.origin!==window.location.origin)return;
    var data=event.data||{};
    if(!data||data.hermesUiMode!==1)return;
    if(data.type==='hermes-ui-inspector-toggle')setInspectorEnabled(!!data.enabled);
    else if(data.type==='hermes-ui-clear-highlights')clearInspectorSelections();
    else if(data.type==='hermes-ui-request-context')emitPageContext('request');
  });

  window.addEventListener('popstate',function(){schedulePageContext('popstate');});
  window.addEventListener('hashchange',function(){schedulePageContext('hashchange');});
  window.addEventListener('pageshow',function(){schedulePageContext('pageshow');});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',function(){schedulePageContext('DOMContentLoaded');},{once:true});
  else schedulePageContext('loaded');
  if(window.MutationObserver){
    var titleEl=document.querySelector('title');
    if(titleEl){
      try{new MutationObserver(function(){schedulePageContext('title');}).observe(titleEl,{childList:true,characterData:true,subtree:true});}catch(_){/* best effort */}
    }
  }

  if(window.XMLHttpRequest&&typeof window.XMLHttpRequest.prototype.open==='function'){
    var nativeOpen=window.XMLHttpRequest.prototype.open;
    window.XMLHttpRequest.prototype.open=function(method,url){
      var args=Array.prototype.slice.call(arguments);
      if(typeof url==='string')args[1]=rewriteHttpUrl(url);
      return nativeOpen.apply(this,args);
    };
  }

  if(typeof window.EventSource==='function'){
    var NativeEventSource=window.EventSource;
    function HermesUiProxyEventSource(url,config){
      return new NativeEventSource(rewriteHttpUrl(url),config);
    }
    HermesUiProxyEventSource.prototype=NativeEventSource.prototype;
    window.EventSource=HermesUiProxyEventSource;
  }

  if(typeof window.WebSocket==='function'){
    var NativeWebSocket=window.WebSocket;
    function HermesUiProxyWebSocket(url,protocols){
      var nextUrl=rewriteSocketUrl(url);
      return protocols===undefined?new NativeWebSocket(nextUrl):new NativeWebSocket(nextUrl,protocols);
    }
    HermesUiProxyWebSocket.prototype=NativeWebSocket.prototype;
    HermesUiProxyWebSocket.CONNECTING=NativeWebSocket.CONNECTING;
    HermesUiProxyWebSocket.OPEN=NativeWebSocket.OPEN;
    HermesUiProxyWebSocket.CLOSING=NativeWebSocket.CLOSING;
    HermesUiProxyWebSocket.CLOSED=NativeWebSocket.CLOSED;
    window.WebSocket=HermesUiProxyWebSocket;
  }
})();
