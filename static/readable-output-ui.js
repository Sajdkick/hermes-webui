(function(){
  function el(id){
    if(typeof window!=='undefined' && typeof window.$==='function'){
      return window.$(id);
    }
    if(typeof document!=='undefined' && document.getElementById){
      return document.getElementById(id);
    }
    return null;
  }

  function escapeHtml(value){
    return String(value||'')
      .replace(/&/g,'&amp;')
      .replace(/</g,'&lt;')
      .replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;')
      .replace(/'/g,'&#39;');
  }

  function sessionIdFor(sessionLike){
    if(!sessionLike)return '';
    if(typeof sessionLike==='string')return String(sessionLike).trim();
    return String(sessionLike.session_id||'').trim();
  }

  function readableOutputViewKey(artifact){
    const path=String(artifact&&artifact.path||'').trim();
    const updated=String(artifact&&artifact.updated_at||'').trim();
    return path||updated ? path+':'+updated : '';
  }

  function sessionReadableOutputAssetUrl(ref, assetBaseUrl){
    let value=String(ref||'').trim();
    if(!value||/^[a-z][a-z0-9+.-]*:/i.test(value)||value.startsWith('#')||value.startsWith('/'))return value;
    value=value.replace(/^\.\//,'');
    value=value.replace(/^assets\//,'');
    const base=String(assetBaseUrl||'');
    if(!base)return value;
    return base+value.split('/').map(function(part){return encodeURIComponent(part);}).join('/');
  }

  function rewriteSessionReadableOutputAssetRefs(markdown, artifact){
    const base=artifact&&artifact.assetBaseUrl;
    if(!base)return String(markdown||'');
    return String(markdown||'').replace(/(!?\[[^\]\n]*\]\()([^) \t\r\n]+)(\))/g,function(match,prefix,ref,suffix){
      return ''+prefix+sessionReadableOutputAssetUrl(ref,base)+suffix;
    });
  }

  function clearSessionReadableOutput(){
    if(typeof S!=='object' || !S)return;
    S.readableOutput=null;
    S.readableOutputSessionId='';
    S.readableOutputDismissedViewKey='';
    renderSessionReadableOutput();
  }

  function renderSessionReadableOutput(){
    const host=el('sessionReadableOutputHost');
    if(!host)return;
    const sessionId=sessionIdFor(typeof S==='object' && S ? S.session : null);
    const artifact=typeof S==='object' && S && S.readableOutputSessionId===sessionId ? S.readableOutput : null;
    if(!artifact||(!artifact.exists&&!artifact.error)){
      host.hidden=true;
      host.innerHTML='';
      return;
    }
    const viewKey=readableOutputViewKey(artifact);
    if(viewKey && typeof S==='object' && S && S.readableOutputDismissedViewKey===viewKey){
      host.hidden=true;
      host.innerHTML='';
      return;
    }
    const meta=[
      artifact.path||'',
      artifact.size?artifact.size+' bytes':'',
      Array.isArray(artifact.assets)&&artifact.assets.length?artifact.assets.length+' asset'+(artifact.assets.length===1?'':'s'):'',
    ].filter(Boolean);
    const body=artifact.exists
      ? ((typeof renderMd==='function')
          ? renderMd(rewriteSessionReadableOutputAssetRefs(artifact.markdown||'',artifact))
          : '<pre>'+escapeHtml(String(artifact.markdown||''))+'</pre>')
      : '<div class="session-readable-output-empty">'+escapeHtml(String(artifact.error||'Readable output unavailable.'))+'</div>';
    host.hidden=false;
    host.innerHTML='' +
      '<section class="session-readable-output-card" role="dialog" aria-modal="true" aria-labelledby="sessionReadableOutputTitle">' +
        '<div class="session-readable-output-header">' +
          '<div>' +
            '<div class="session-readable-output-title" id="sessionReadableOutputTitle">Readable output</div>' +
            (meta.length?'<div class="session-readable-output-meta">'+meta.map(function(item){return '<span>'+escapeHtml(item)+'</span>';}).join('')+'</div>':'') +
          '</div>' +
          '<div class="session-readable-output-actions">' +
            '<button class="session-readable-output-refresh" type="button" onclick="reloadSessionReadableOutput()">Refresh</button>' +
            '<button class="session-readable-output-dismiss" type="button" onclick="dismissSessionReadableOutput()">Close readable output</button>' +
          '</div>' +
        '</div>' +
        '<div class="preview-md session-readable-output-body">'+body+'</div>' +
      '</section>';
  }

  function dismissSessionReadableOutput(){
    if(typeof S!=='object' || !S)return;
    S.readableOutputDismissedViewKey=readableOutputViewKey(S.readableOutput);
    renderSessionReadableOutput();
  }

  async function loadSessionReadableOutput(sessionLike){
    if(typeof S!=='object' || !S){
      return null;
    }
    const sid=sessionIdFor(sessionLike||S.session);
    if(!sid){
      clearSessionReadableOutput();
      return null;
    }
    try{
      const response=await fetch('/api/ops/sessions/'+encodeURIComponent(sid)+'/readable-output',{credentials:'same-origin'});
      const payload=await response.json().catch(function(){return {};});
      if(!response.ok){
        const message=payload && payload.error ? payload.error : 'Readable output unavailable.';
        throw new Error(message);
      }
      if(sessionIdFor(S.session)!==sid){
        return payload && payload.readableOutput ? payload.readableOutput : null;
      }
      S.readableOutput=(payload&&payload.readableOutput)||{exists:false};
      S.readableOutputSessionId=sid;
      renderSessionReadableOutput();
      return S.readableOutput;
    }catch(error){
      if(sessionIdFor(S.session)!==sid){
        return null;
      }
      S.readableOutput={exists:false,error:error&&error.message?error.message:'Readable output unavailable.'};
      S.readableOutputSessionId=sid;
      renderSessionReadableOutput();
      return null;
    }
  }

  async function reloadSessionReadableOutput(){
    if(typeof S!=='object' || !S)return null;
    S.readableOutputDismissedViewKey='';
    return loadSessionReadableOutput(S.session);
  }

  function installReadableOutputHooks(){
    if(typeof window==='undefined')return;
    if(typeof window.loadSession==='function' && !window._readableOutputLoadSessionWrapped){
      const originalLoadSession=window.loadSession;
      window.loadSession=async function(sid){
        const result=await originalLoadSession.apply(this,arguments);
        if(typeof S==='object' && S && S.session && sessionIdFor(S.session)===String(sid||'')){
          try{await loadSessionReadableOutput(sid);}catch(_){}
        }else{
          clearSessionReadableOutput();
        }
        return result;
      };
      window._readableOutputLoadSessionWrapped=true;
    }
    if(typeof window.newSession==='function' && !window._readableOutputNewSessionWrapped){
      const originalNewSession=window.newSession;
      window.newSession=async function(){
        const result=await originalNewSession.apply(this,arguments);
        clearSessionReadableOutput();
        return result;
      };
      window._readableOutputNewSessionWrapped=true;
    }
  }

  installReadableOutputHooks();
  window.sessionReadableOutputAssetUrl=sessionReadableOutputAssetUrl;
  window.rewriteSessionReadableOutputAssetRefs=rewriteSessionReadableOutputAssetRefs;
  window.renderSessionReadableOutput=renderSessionReadableOutput;
  window.clearSessionReadableOutput=clearSessionReadableOutput;
  window.dismissSessionReadableOutput=dismissSessionReadableOutput;
  window.loadSessionReadableOutput=loadSessionReadableOutput;
  window.reloadSessionReadableOutput=reloadSessionReadableOutput;
})();
