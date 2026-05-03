(function(){
  if(window.__HERMES_PLAY_PROXY_COMPAT__===1)return;
  window.__HERMES_PLAY_PROXY_COMPAT__=1;

  const PROXY_PATH_PREFIXES=['/api/trpc','/api/blob','/nakama','/.well-known'];

  function currentScriptSource(){
    const scripts=Array.from(document.querySelectorAll('script[data-hermes-play-proxy-prefix]'));
    return scripts[scripts.length-1]||document.currentScript||null;
  }

  function proxyPrefix(){
    const source=currentScriptSource();
    const raw=source&&source.dataset?String(source.dataset.hermesPlayProxyPrefix||'').trim():'';
    return raw.replace(/\/+$/,'');
  }

  function pathNeedsProxy(pathname){
    const path=String(pathname||'').trim();
    if(!path)return false;
    return PROXY_PATH_PREFIXES.some((prefix)=>path===prefix||path.startsWith(prefix+'/'));
  }

  function parseUrl(raw){
    if(typeof raw!=='string'||!raw.trim())return null;
    try{
      return new URL(raw,window.location.href);
    }catch(_){
      return null;
    }
  }

  function rewriteParsedPath(parsed,prefix){
    if(!parsed||!prefix)return null;
    if(parsed.origin!==window.location.origin)return null;
    if(parsed.pathname===prefix||parsed.pathname.startsWith(prefix+'/'))return null;
    if(!pathNeedsProxy(parsed.pathname))return null;
    return `${prefix}${parsed.pathname}${parsed.search}${parsed.hash}`;
  }

  function rewriteHttpUrl(raw){
    const prefix=proxyPrefix();
    const parsed=parseUrl(raw);
    const rewritten=rewriteParsedPath(parsed,prefix);
    if(!rewritten)return raw;
    const trimmed=String(raw||'').trim();
    if(/^[a-z][a-z0-9+.-]*:/i.test(trimmed))return new URL(rewritten,window.location.origin).toString();
    return rewritten;
  }

  function rewriteSocketUrl(raw){
    const prefix=proxyPrefix();
    const parsed=parseUrl(raw);
    const rewrittenPath=rewriteParsedPath(parsed,prefix);
    if(!rewrittenPath)return raw;
    const rewritten=new URL(rewrittenPath,window.location.origin);
    const trimmed=String(raw||'').trim();
    if(trimmed.startsWith('ws:')||trimmed.startsWith('wss:')){
      rewritten.protocol=trimmed.startsWith('wss:')?'wss:':'ws:';
    }else{
      rewritten.protocol=window.location.protocol==='https:'?'wss:':'ws:';
    }
    return rewritten.toString();
  }

  if(typeof window.fetch==='function'){
    const nativeFetch=window.fetch.bind(window);
    window.fetch=function(input,init){
      if(typeof input==='string'){
        return nativeFetch(rewriteHttpUrl(input),init);
      }
      if(input instanceof Request){
        const nextUrl=rewriteHttpUrl(input.url);
        if(nextUrl!==input.url){
          try{
            return nativeFetch(new Request(nextUrl,input),init);
          }catch(_){}
        }
      }
      return nativeFetch(input,init);
    };
  }

  if(window.XMLHttpRequest&&typeof window.XMLHttpRequest.prototype.open==='function'){
    const nativeOpen=window.XMLHttpRequest.prototype.open;
    window.XMLHttpRequest.prototype.open=function(method,url){
      const args=[...arguments];
      if(typeof url==='string'){
        args[1]=rewriteHttpUrl(url);
      }
      return nativeOpen.apply(this,args);
    };
  }

  if(typeof window.EventSource==='function'){
    const NativeEventSource=window.EventSource;
    function HermesPlayProxyEventSource(url,config){
      return new NativeEventSource(rewriteHttpUrl(url),config);
    }
    HermesPlayProxyEventSource.prototype=NativeEventSource.prototype;
    window.EventSource=HermesPlayProxyEventSource;
  }

  if(typeof window.WebSocket==='function'){
    const NativeWebSocket=window.WebSocket;
    function HermesPlayProxyWebSocket(url,protocols){
      const nextUrl=rewriteSocketUrl(url);
      return protocols===undefined?new NativeWebSocket(nextUrl):new NativeWebSocket(nextUrl,protocols);
    }
    HermesPlayProxyWebSocket.prototype=NativeWebSocket.prototype;
    HermesPlayProxyWebSocket.CONNECTING=NativeWebSocket.CONNECTING;
    HermesPlayProxyWebSocket.OPEN=NativeWebSocket.OPEN;
    HermesPlayProxyWebSocket.CLOSING=NativeWebSocket.CLOSING;
    HermesPlayProxyWebSocket.CLOSED=NativeWebSocket.CLOSED;
    window.WebSocket=HermesPlayProxyWebSocket;
  }
})();
