(function(){
  function overlayScript(){
    const current=document.currentScript;
    if(current&&current.dataset&&current.dataset.hermesPlayOverlay)return current;
    try{
      const scripts=Array.from(document.querySelectorAll('script[data-hermes-play-overlay]'));
      return scripts[scripts.length-1]||current||null;
    }catch(_error){
      return current||null;
    }
  }

  const script=overlayScript();
  if(!script||script.dataset.hermesPlayOverlay==='disabled')return;

  function feedbackCaptureMode(){
    try{
      return new URL(window.location.href).searchParams.get('hermesPlayFeedbackCapture')==='1';
    }catch(_error){
      return false;
    }
  }
  if(feedbackCaptureMode())return;

  function text(value){
    return String(value||'').trim();
  }

  function currentMountPrefix(){
    try{
      const pathname=String((window.location&&window.location.pathname)||'');
      const marker='/play-project/';
      const index=pathname.indexOf(marker);
      if(index>0)return pathname.slice(0,index).replace(/\/+$/,'');
    }catch(_error){
      return '';
    }
    return '';
  }

  function appUrl(path){
    const raw=text(path)||'/';
    try{
      if(/^[a-z][a-z0-9+.-]*:/i.test(raw)||raw.startsWith('//')){
        return new URL(raw, window.location.href).href;
      }
      if(raw.startsWith('/')){
        const mount=currentMountPrefix();
        const rebased=(mount&&raw!==mount&&!raw.startsWith(mount+'/'))?mount+raw:raw;
        return new URL(rebased, window.location.origin).href;
      }
      return new URL(raw, window.location.origin).href;
    }catch(_error){
      return raw;
    }
  }

  function sessionInspectUrl(path){
    const href=appUrl(path);
    try{
      const url=new URL(href, window.location.origin);
      url.searchParams.set('opsSessionInspect','1');
      url.searchParams.set('opsSessionInspectSource','play');
      return url.href;
    }catch(_error){
      const separator=href.indexOf('?')>=0?'&':'?';
      return href+separator+'opsSessionInspect=1&opsSessionInspectSource=play';
    }
  }

  const sessionId=text(script.dataset.hermesPlaySessionId);
  const projectId=text(script.dataset.hermesPlayProjectId);
  const taskId=text(script.dataset.hermesPlayTaskId);
  const runId=text(script.dataset.hermesPlayRunId);
  if(!projectId&&!sessionId)return;
  const fullSessionUrl=sessionId?appUrl(script.dataset.hermesPlaySessionUrl||('/session/'+encodeURIComponent(sessionId))):'';
  const sessionUrl=sessionId?sessionInspectUrl(fullSessionUrl):'';
  const overlayKey=[projectId,runId,taskId,sessionId].filter(Boolean).join(':')||projectId||sessionId||'play-feedback';

  function escapeHtml(value){
    return text(value).replace(/[&<>"']/g,(char)=>({
      '&':'&amp;',
      '<':'&lt;',
      '>':'&gt;',
      '"':'&quot;',
      "'":'&#39;'
    }[char]));
  }

  function readCollapsed(){
    return false;
  }

  function writeCollapsed(_collapsed){
    // Collapse state is intentionally page-local. Persisting it in sessionStorage
    // made desktop notification opens look like the popup never appeared after a
    // previous hide, while fresh mobile browsers still showed it.
  }

  let feedbackApiFetch=null;
  let feedbackApiFrame=null;
  let feedbackState=null;

  function fileStamp(){
    try{
      return new Date().toISOString().replace(/[:.]/g,'-');
    }catch(_error){
      return String(Date.now());
    }
  }

  function projectApiPath(suffix){
    if(!projectId)throw new Error('Feedback needs a linked project before it can be saved.');
    return appUrl('/api/core/projects/'+encodeURIComponent(projectId)+suffix);
  }

  function feedbackApiFetcher(){
    if(feedbackApiFetch)return feedbackApiFetch;
    try{
      if(document&&document.createElement){
        feedbackApiFrame=document.createElement('iframe');
        feedbackApiFrame.hidden=true;
        feedbackApiFrame.tabIndex=-1;
        feedbackApiFrame.setAttribute('aria-hidden','true');
        feedbackApiFrame.style.cssText='position:absolute;width:0;height:0;border:0;clip:rect(0 0 0 0);clip-path:inset(50%);overflow:hidden;';
        const host=document.documentElement||document.body;
        if(host&&host.appendChild)host.appendChild(feedbackApiFrame);
        const frameWindow=feedbackApiFrame.contentWindow;
        if(frameWindow&&typeof frameWindow.fetch==='function')feedbackApiFetch=frameWindow.fetch.bind(frameWindow);
      }
    }catch(_error){
      feedbackApiFetch=null;
    }
    if(!feedbackApiFetch&&typeof window.fetch==='function')feedbackApiFetch=window.fetch.bind(window);
    return feedbackApiFetch;
  }

  async function requestJson(path, options){
    const fetcher=feedbackApiFetcher();
    if(!fetcher)throw new Error('Feedback API is unavailable in this browser.');
    const opts=options||{};
    const headers=Object.assign({'Content-Type':'application/json'},opts.headers||{});
    const init=Object.assign({},opts,{headers,credentials:'same-origin'});
    if(Object.prototype.hasOwnProperty.call(opts,'body')&&opts.body!==undefined){
      init.body=JSON.stringify(opts.body);
    }
    const response=await fetcher(new URL(path,window.location.origin).href,init);
    let payload={};
    try{
      payload=await response.json();
    }catch(_error){
      payload={};
    }
    if(!response.ok){
      throw new Error(text(payload.error)||('Request failed with HTTP '+response.status+'.'));
    }
    return payload;
  }

  function feedbackCaptureUrl(){
    try{
      const url=new URL(window.location.href);
      url.searchParams.set('hermesPlayFeedbackCapture','1');
      return url.href;
    }catch(_error){
      return window.location.href;
    }
  }

  function extractScreenshotDataUrl(payload){
    const screenshot=payload&&(payload.screenshot||payload);
    if(!screenshot||typeof screenshot!=='object')return '';
    const dataUrl=text(screenshot.dataUrl);
    if(dataUrl)return dataUrl;
    const content=text(screenshot.content);
    if(!content)return '';
    const mime=text(screenshot.mimeType||screenshot.mime)||'image/png';
    return 'data:'+mime+';base64,'+content;
  }

  async function captureFeedbackScreenshot(){
    const width=Math.max(360,Math.min(1600,Math.round(window.innerWidth||1280)));
    const height=Math.max(360,Math.min(1400,Math.round(window.innerHeight||900)));
    const payload=await requestJson(projectApiPath('/runtime/inspect/screenshot'),{
      method:'POST',
      body:{
        url:feedbackCaptureUrl(),
        width,
        height,
        delayMs:200,
        timeoutMs:12000,
        fileName:'play-feedback-'+fileStamp()+'.png',
        includeContent:true
      }
    });
    const dataUrl=extractScreenshotDataUrl(payload);
    if(!dataUrl)throw new Error('Screenshot capture did not return image data.');
    return dataUrl;
  }

  function dataUrlToBlob(dataUrl){
    const match=String(dataUrl||'').match(/^data:([^;,]+);base64,(.*)$/);
    if(!match)throw new Error('Screenshot data is not a base64 image.');
    const binary=window.atob(match[2]);
    const bytes=new Uint8Array(binary.length);
    for(let index=0;index<binary.length;index+=1)bytes[index]=binary.charCodeAt(index);
    return new Blob([bytes],{type:match[1]||'image/png'});
  }

  function paintFeedbackImage(canvas,image){
    const sourceWidth=Math.max(1,Math.round(image.width||image.naturalWidth||900));
    const sourceHeight=Math.max(1,Math.round(image.height||image.naturalHeight||520));
    const scale=Math.min(1,1600/sourceWidth,1200/sourceHeight);
    canvas.width=Math.max(1,Math.round(sourceWidth*scale));
    canvas.height=Math.max(1,Math.round(sourceHeight*scale));
    const ctx=canvas.getContext('2d');
    if(!ctx)return;
    ctx.clearRect(0,0,canvas.width,canvas.height);
    ctx.drawImage(image,0,0,canvas.width,canvas.height);
  }

  async function drawDataUrlOnCanvas(canvas,dataUrl){
    const blob=dataUrlToBlob(dataUrl);
    if(typeof window.createImageBitmap==='function'){
      const bitmap=await window.createImageBitmap(blob);
      try{
        paintFeedbackImage(canvas,bitmap);
      }finally{
        if(bitmap&&typeof bitmap.close==='function')bitmap.close();
      }
      return;
    }
    await new Promise((resolve,reject)=>{
      const img=new Image();
      const objectUrl=URL.createObjectURL(blob);
      img.onload=()=>{
        try{
          paintFeedbackImage(canvas,img);
          resolve();
        }catch(error){
          reject(error);
        }finally{
          URL.revokeObjectURL(objectUrl);
        }
      };
      img.onerror=()=>{
        URL.revokeObjectURL(objectUrl);
        reject(new Error('Unable to load captured screenshot.'));
      };
      img.src=objectUrl;
    });
  }

  function drawFeedbackPlaceholder(canvas,title,detail){
    canvas.width=900;
    canvas.height=520;
    const ctx=canvas.getContext('2d');
    if(!ctx)return;
    ctx.fillStyle='#111827';
    ctx.fillRect(0,0,canvas.width,canvas.height);
    ctx.strokeStyle='#334155';
    ctx.lineWidth=4;
    ctx.strokeRect(18,18,canvas.width-36,canvas.height-36);
    ctx.fillStyle='#f8fafc';
    ctx.font='700 28px Inter, system-ui, sans-serif';
    ctx.fillText(title||'Screenshot unavailable',48,92);
    ctx.fillStyle='#cbd5e1';
    ctx.font='500 18px Inter, system-ui, sans-serif';
    const message=String(detail||'You can still send written feedback.').slice(0,180);
    ctx.fillText(message,48,132);
  }

  function canvasPoint(event,canvas){
    const rect=canvas.getBoundingClientRect();
    const scaleX=canvas.width/(rect.width||canvas.width||1);
    const scaleY=canvas.height/(rect.height||canvas.height||1);
    return {
      x:(event.clientX-rect.left)*scaleX,
      y:(event.clientY-rect.top)*scaleY
    };
  }

  function drawFeedbackMarker(event,canvas,start){
    if(!feedbackState||!feedbackState.canDraw)return;
    if(event&&event.preventDefault)event.preventDefault();
    const ctx=canvas.getContext('2d');
    if(!ctx)return;
    const point=canvasPoint(event,canvas);
    ctx.strokeStyle='#ef4444';
    ctx.lineWidth=Math.max(6,Math.round(Math.min(canvas.width,canvas.height)*0.012));
    ctx.lineCap='round';
    ctx.lineJoin='round';
    if(start){
      feedbackState.drawing=true;
      ctx.beginPath();
      ctx.moveTo(point.x,point.y);
      return;
    }
    if(!feedbackState.drawing)return;
    ctx.lineTo(point.x,point.y);
    ctx.stroke();
    feedbackState.drew=true;
  }

  function stopFeedbackMarker(){
    if(feedbackState)feedbackState.drawing=false;
  }

  function bindFeedbackCanvas(canvas){
    if(!canvas||canvas.dataset.hermesFeedbackBound)return;
    canvas.dataset.hermesFeedbackBound='1';
    canvas.addEventListener('pointerdown',(event)=>{
      try{canvas.setPointerCapture(event.pointerId);}catch(_error){}
      drawFeedbackMarker(event,canvas,true);
    });
    canvas.addEventListener('pointermove',(event)=>drawFeedbackMarker(event,canvas,false));
    canvas.addEventListener('pointerup',stopFeedbackMarker);
    canvas.addEventListener('pointercancel',stopFeedbackMarker);
    canvas.addEventListener('pointerleave',stopFeedbackMarker);
  }

  function ensureFeedbackModal(){
    let modal=document.getElementById('hermes-play-feedback-modal');
    if(modal)return modal;
    modal=document.createElement('div');
    modal.id='hermes-play-feedback-modal';
    modal.className='hermes-play-feedback-modal';
    modal.hidden=true;
    modal.innerHTML=`
      <section class="hermes-play-feedback-dialog" role="dialog" aria-modal="true" aria-labelledby="hermes-play-feedback-title">
        <header class="hermes-play-feedback-header">
          <div>
            <h2 id="hermes-play-feedback-title">Send UI feedback</h2>
            <p>Draw with the red marker if the screenshot needs context, then send the feedback into this project.</p>
          </div>
          <button class="hermes-play-feedback-close" type="button" data-hermes-feedback-close aria-label="Close feedback">×</button>
        </header>
        <div class="hermes-play-feedback-body">
          <div class="hermes-play-feedback-step" data-hermes-feedback-step="annotate">
            <p class="hermes-play-feedback-status" data-hermes-feedback-status>Draw on the screenshot with the red marker, or skip the screenshot.</p>
            <div class="hermes-play-feedback-canvas-wrap">
              <canvas class="hermes-play-feedback-canvas" data-hermes-feedback-canvas aria-label="Captured Play screenshot"></canvas>
            </div>
            <div class="hermes-play-feedback-actions">
              <button class="hermes-play-feedback-secondary" type="button" data-hermes-feedback-skip>Skip</button>
              <button class="hermes-play-feedback-primary" type="button" data-hermes-feedback-done>Done</button>
            </div>
          </div>
          <div class="hermes-play-feedback-step" data-hermes-feedback-step="text" hidden>
            <p class="hermes-play-feedback-status">Write the feedback to send with the screenshot.</p>
            <textarea class="hermes-play-feedback-input" data-hermes-feedback-text placeholder="Describe what should be fixed…"></textarea>
            <p class="hermes-play-feedback-status" data-hermes-feedback-send-status></p>
            <div class="hermes-play-feedback-actions">
              <button class="hermes-play-feedback-primary" type="button" data-hermes-feedback-send>Send</button>
            </div>
          </div>
          <div class="hermes-play-feedback-step hermes-play-feedback-sent" data-hermes-feedback-step="sent" hidden>
            <strong>Feedback sent</strong>
            <p class="hermes-play-feedback-status">Feedback sent. You can close this popup and keep playing.</p>
            <button class="hermes-play-feedback-primary" type="button" data-hermes-feedback-close>Close</button>
          </div>
        </div>
      </section>
    `;
    document.body.appendChild(modal);
    bindFeedbackCanvas(modal.querySelector('[data-hermes-feedback-canvas]'));
    modal.querySelector('[data-hermes-feedback-skip]').addEventListener('click',handleFeedbackSkip);
    modal.querySelector('[data-hermes-feedback-done]').addEventListener('click',handleFeedbackDone);
    modal.querySelector('[data-hermes-feedback-send]').addEventListener('click',handleFeedbackSend);
    Array.from(modal.querySelectorAll('[data-hermes-feedback-close]')).forEach((button)=>{
      button.addEventListener('click',closeFeedbackModal);
    });
    return modal;
  }

  function setFeedbackStep(modal,step){
    Array.from(modal.querySelectorAll('[data-hermes-feedback-step]')).forEach((node)=>{
      node.hidden=node.dataset.hermesFeedbackStep!==step;
    });
  }

  function closeFeedbackModal(){
    const modal=document.getElementById('hermes-play-feedback-modal');
    if(modal)modal.hidden=true;
    feedbackState=null;
  }

  function setSendStatus(modal,message){
    const status=modal.querySelector('[data-hermes-feedback-send-status]');
    if(status)status.textContent=message||'';
  }

  function applyMarkerPrefix(value){
    const prefix='Note the red marker.';
    const trimmed=String(value||'').trim();
    if(trimmed.startsWith(prefix))return trimmed;
    return (prefix+'\n'+trimmed).trim();
  }

  async function openFeedbackModal(initialDataUrl,captureError){
    const modal=ensureFeedbackModal();
    const canvas=modal.querySelector('[data-hermes-feedback-canvas]');
    const status=modal.querySelector('[data-hermes-feedback-status]');
    const textarea=modal.querySelector('[data-hermes-feedback-text]');
    if(textarea)textarea.value='';
    setSendStatus(modal,'');
    feedbackState={canDraw:false,drawing:false,drew:false,hasScreenshot:false,screenshotDataUrl:'',sending:false};
    setFeedbackStep(modal,'annotate');
    modal.hidden=false;
    if(initialDataUrl){
      try{
        await drawDataUrlOnCanvas(canvas,initialDataUrl);
        feedbackState.canDraw=true;
        feedbackState.hasScreenshot=true;
        feedbackState.screenshotDataUrl=initialDataUrl;
        if(status)status.textContent='Draw on the screenshot with the red marker, or skip it.';
      }catch(error){
        drawFeedbackPlaceholder(canvas,'Screenshot unavailable',error&&error.message);
        if(status)status.textContent='The screenshot could not be shown. You can still continue with written feedback.';
      }
    }else{
      drawFeedbackPlaceholder(canvas,'Screenshot unavailable',captureError&&captureError.message);
      if(status)status.textContent='The screenshot could not be captured. You can still continue with written feedback.';
    }
  }

  function handleFeedbackSkip(){
    if(!feedbackState)return;
    feedbackState.screenshotDataUrl='';
    feedbackState.hasScreenshot=false;
    feedbackState.drew=false;
    const modal=ensureFeedbackModal();
    setFeedbackStep(modal,'text');
    const textarea=modal.querySelector('[data-hermes-feedback-text]');
    if(textarea)textarea.focus();
  }

  function handleFeedbackDone(){
    if(!feedbackState)return;
    const modal=ensureFeedbackModal();
    const canvas=modal.querySelector('[data-hermes-feedback-canvas]');
    const textarea=modal.querySelector('[data-hermes-feedback-text]');
    if(feedbackState.hasScreenshot&&canvas){
      try{
        feedbackState.screenshotDataUrl=canvas.toDataURL('image/png');
      }catch(_error){
        // Keep the original captured image if canvas export is blocked.
      }
    }
    if(feedbackState.drew&&textarea){
      textarea.value=applyMarkerPrefix(textarea.value);
    }
    setFeedbackStep(modal,'text');
    if(textarea)textarea.focus();
  }

  async function saveFeedback(textValue,screenshotDataUrl){
    const epicResult=await requestJson(projectApiPath('/epics/ensure'),{
      method:'POST',
      body:{title:'User Feedback'}
    });
    const epic=epicResult&&epicResult.epic;
    const epicId=text(epic&&epic.id);
    if(!epicId)throw new Error('User Feedback epic could not be created.');
    const savedText="We recieved this feedback from a user '"+textValue+"' analyze it in depth and fix it";
    const taskResult=await requestJson(projectApiPath('/tasks'),{
      method:'POST',
      body:{epicId,text:savedText,grade:'green',markers:['User Feedback']}
    });
    const task=taskResult&&taskResult.task;
    const createdTaskId=text(task&&task.id);
    if(!createdTaskId)throw new Error('Feedback task could not be created.');
    if(screenshotDataUrl){
      await requestJson(projectApiPath('/tasks/'+encodeURIComponent(createdTaskId)+'/images'),{
        method:'POST',
        body:{content:screenshotDataUrl,mimeType:'image/png',filename:'play-feedback-'+fileStamp()+'.png'}
      });
    }
    return taskResult;
  }

  async function handleFeedbackSend(){
    if(!feedbackState||feedbackState.sending)return;
    const modal=ensureFeedbackModal();
    const textarea=modal.querySelector('[data-hermes-feedback-text]');
    const sendButton=modal.querySelector('[data-hermes-feedback-send]');
    let value=String((textarea&&textarea.value)||'').trim();
    if(feedbackState.drew)value=applyMarkerPrefix(value);
    if(!value){
      setSendStatus(modal,'Write feedback before sending.');
      if(textarea)textarea.focus();
      return;
    }
    feedbackState.sending=true;
    if(sendButton)sendButton.disabled=true;
    setSendStatus(modal,'Sending feedback…');
    try{
      await saveFeedback(value,feedbackState.screenshotDataUrl);
      setFeedbackStep(modal,'sent');
    }catch(error){
      setSendStatus(modal,(error&&error.message)||'Feedback could not be sent.');
    }finally{
      feedbackState.sending=false;
      if(sendButton)sendButton.disabled=false;
    }
  }

  async function startFeedbackFlow(button){
    if(!projectId){
      await openFeedbackModal('',new Error('Feedback needs a linked project before it can be saved.'));
      return;
    }
    const originalLabel=button?button.textContent:'';
    if(button){
      button.disabled=true;
      button.textContent='Capturing…';
    }
    let screenshotDataUrl='';
    let captureError=null;
    try{
      screenshotDataUrl=await captureFeedbackScreenshot();
    }catch(error){
      captureError=error;
    }finally{
      if(button){
        button.disabled=false;
        button.textContent=originalLabel||'Feedback';
      }
    }
    await openFeedbackModal(screenshotDataUrl,captureError);
  }

  function installStyles(){
    if(document.getElementById('hermes-play-session-overlay-styles'))return;
    const style=document.createElement('style');
    style.id='hermes-play-session-overlay-styles';
    style.textContent=`
      .hermes-play-session-overlay{position:fixed;right:18px;bottom:18px;z-index:2147483647;display:flex;flex-direction:column;align-items:flex-end;gap:10px;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#f8fafc;}
      .hermes-play-session-overlay *{box-sizing:border-box;}
      .hermes-play-feedback-button{display:inline-flex;align-items:center;gap:8px;border:1px solid rgba(248,113,113,.62);border-radius:999px;padding:9px 13px;background:linear-gradient(135deg,#dc2626,#7f1d1d);box-shadow:0 16px 38px rgba(127,29,29,.36);color:#fff;font:800 12px/1 inherit;letter-spacing:.01em;cursor:pointer;}
      .hermes-play-feedback-button:hover{transform:translateY(-1px);box-shadow:0 20px 44px rgba(127,29,29,.44);}
      .hermes-play-feedback-button:disabled{cursor:wait;opacity:.72;transform:none;}
      .hermes-play-session-toggle{display:none;align-items:center;gap:8px;min-width:52px;min-height:52px;border:1px solid rgba(148,163,184,.45);border-radius:999px;padding:0 16px;background:linear-gradient(135deg,#4f46e5,#0f172a);box-shadow:0 20px 45px rgba(15,23,42,.34);color:#fff;font:700 14px/1.2 inherit;cursor:pointer;}
      .hermes-play-session-toggle:hover{transform:translateY(-1px);box-shadow:0 24px 52px rgba(15,23,42,.42);}
      .hermes-play-session-toggle-icon{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:50%;background:rgba(255,255,255,.18);font-weight:800;}
      .hermes-play-session-panel{display:flex;flex-direction:column;width:min(440px,calc(100vw - 32px));height:min(680px,calc(100vh - 96px));min-height:320px;overflow:hidden;border:1px solid rgba(148,163,184,.36);border-radius:18px;background:rgba(15,23,42,.96);box-shadow:0 24px 72px rgba(15,23,42,.48);backdrop-filter:blur(16px);}
      .hermes-play-session-header{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:12px 12px 10px 14px;border-bottom:1px solid rgba(148,163,184,.22);background:linear-gradient(135deg,rgba(30,41,59,.98),rgba(15,23,42,.96));}
      .hermes-play-session-title{display:flex;flex-direction:column;gap:2px;min-width:0;}
      .hermes-play-session-title strong{font-size:14px;letter-spacing:.01em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
      .hermes-play-session-title span{font-size:12px;color:#cbd5e1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
      .hermes-play-session-actions{display:flex;align-items:center;gap:8px;}
      .hermes-play-session-action{border:1px solid rgba(148,163,184,.35);border-radius:999px;background:rgba(15,23,42,.72);color:#f8fafc;padding:7px 10px;font:700 12px/1 inherit;text-decoration:none;cursor:pointer;}
      .hermes-play-session-action:hover{background:rgba(79,70,229,.42);}
      .hermes-play-session-frame-wrap{position:relative;display:flex;flex:1;min-height:0;background:#fff;}
      .hermes-play-session-frame{flex:1;width:100%;border:0;background:#fff;}
      .hermes-play-session-frame.is-pending{visibility:hidden;}
      .hermes-play-session-frame[hidden]{display:none;}
      .hermes-play-session-frame-status{position:absolute;inset:auto 12px 12px 12px;display:flex;align-items:center;justify-content:space-between;gap:10px;border:1px solid rgba(148,163,184,.28);border-radius:12px;background:rgba(15,23,42,.92);color:#f8fafc;padding:10px 12px;font-size:12px;box-shadow:0 14px 30px rgba(15,23,42,.28);}
      .hermes-play-session-frame-status[hidden]{display:none;}
      .hermes-play-session-frame-status a{color:#bfdbfe;font-weight:800;text-decoration:none;white-space:nowrap;}
      .hermes-play-session-frame-status a:hover{text-decoration:underline;}
      .hermes-play-session-overlay.is-collapsed .hermes-play-session-panel{display:none;}
      .hermes-play-session-overlay.is-collapsed .hermes-play-session-toggle{display:inline-flex;}
      .hermes-play-feedback-modal{position:fixed;inset:0;z-index:2147483647;display:flex;align-items:center;justify-content:center;padding:22px;background:rgba(15,23,42,.68);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#f8fafc;}
      .hermes-play-feedback-modal[hidden]{display:none;}
      .hermes-play-feedback-dialog{width:min(980px,calc(100vw - 28px));max-height:calc(100vh - 28px);display:flex;flex-direction:column;overflow:hidden;border:1px solid rgba(248,113,113,.36);border-radius:20px;background:#0f172a;box-shadow:0 30px 90px rgba(15,23,42,.62);}
      .hermes-play-feedback-header{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;padding:16px 18px;border-bottom:1px solid rgba(148,163,184,.22);background:linear-gradient(135deg,rgba(127,29,29,.96),rgba(15,23,42,.98));}
      .hermes-play-feedback-header h2{margin:0;font-size:18px;line-height:1.25;}
      .hermes-play-feedback-header p{margin:4px 0 0;color:#fecaca;font-size:13px;line-height:1.45;}
      .hermes-play-feedback-close{border:1px solid rgba(248,250,252,.32);border-radius:999px;background:rgba(15,23,42,.46);color:#fff;width:34px;height:34px;font:800 18px/1 inherit;cursor:pointer;}
      .hermes-play-feedback-body{min-height:0;overflow:auto;padding:18px;}
      .hermes-play-feedback-step[hidden]{display:none;}
      .hermes-play-feedback-status{margin:0 0 12px;color:#cbd5e1;font-size:13px;line-height:1.5;}
      .hermes-play-feedback-canvas-wrap{display:flex;align-items:center;justify-content:center;max-height:min(62vh,720px);overflow:auto;border:1px solid rgba(148,163,184,.28);border-radius:14px;background:#020617;padding:10px;}
      .hermes-play-feedback-canvas{display:block;max-width:100%;height:auto;border-radius:10px;background:#111827;touch-action:none;cursor:crosshair;}
      .hermes-play-feedback-actions{display:flex;justify-content:flex-end;gap:10px;flex-wrap:wrap;margin-top:14px;}
      .hermes-play-feedback-secondary,.hermes-play-feedback-primary{border:1px solid rgba(148,163,184,.4);border-radius:999px;padding:10px 16px;font:800 13px/1 inherit;cursor:pointer;}
      .hermes-play-feedback-secondary{background:rgba(15,23,42,.72);color:#f8fafc;}
      .hermes-play-feedback-primary{background:#dc2626;border-color:#f87171;color:#fff;}
      .hermes-play-feedback-primary:disabled,.hermes-play-feedback-secondary:disabled{cursor:wait;opacity:.65;}
      .hermes-play-feedback-input{width:100%;min-height:150px;resize:vertical;border:1px solid rgba(148,163,184,.34);border-radius:14px;background:#020617;color:#f8fafc;padding:12px 14px;font:500 14px/1.5 inherit;outline:none;}
      .hermes-play-feedback-input:focus{border-color:#f87171;box-shadow:0 0 0 3px rgba(248,113,113,.18);}
      .hermes-play-feedback-sent{display:flex;flex-direction:column;gap:10px;align-items:flex-start;}
      .hermes-play-feedback-sent strong{font-size:18px;}
      @media (max-width:760px){
        .hermes-play-session-overlay{right:12px;bottom:12px;}
        .hermes-play-session-panel{width:calc(100vw - 24px);height:min(620px,calc(100vh - 72px));}
        .hermes-play-session-action.open-label{display:none;}
        .hermes-play-feedback-modal{padding:10px;align-items:stretch;}
        .hermes-play-feedback-dialog{width:100%;max-height:calc(100vh - 20px);}
        .hermes-play-feedback-body{padding:12px;}
      }
    `;
    document.head.appendChild(style);
  }

  function createOverlay(){
    const existing=document.getElementById('hermes-play-session-overlay');
    if(existing){
      if(existing.dataset&&existing.dataset.hermesPlayOverlayKey===overlayKey){
        existing.classList.remove('is-collapsed');
        const frame=existing.querySelector('.hermes-play-session-frame');
        if(frame&&frame.getAttribute('src')!==sessionUrl)frame.setAttribute('src',sessionUrl);
        const fullLink=existing.querySelector('[data-hermes-play-full-session]');
        if(fullLink)fullLink.setAttribute('href',fullSessionUrl);
        return;
      }
      existing.remove();
    }
    installStyles();
    const root=document.createElement('aside');
    root.id='hermes-play-session-overlay';
    root.className='hermes-play-session-overlay';
    root.dataset.hermesPlayOverlayKey=overlayKey;
    root.setAttribute('aria-label','Hermes session access for this Play inspection');
    if(readCollapsed())root.classList.add('is-collapsed');

    const summary=[
      projectId?`Project ${projectId}`:'Play inspection',
      taskId?`Task ${taskId}`:'',
    ].filter(Boolean).join(' • ');

    root.innerHTML=`
      ${projectId?'<button class="hermes-play-feedback-button" type="button" data-hermes-play-feedback title="Send UI feedback">Feedback</button>':''}
      ${sessionId?`<button class="hermes-play-session-toggle" type="button" aria-expanded="false" title="Open Hermes session">
        <span class="hermes-play-session-toggle-icon">H</span><span>Session</span>
      </button>
      <section class="hermes-play-session-panel" aria-label="Hermes session panel">
        <div class="hermes-play-session-header">
          <div class="hermes-play-session-title">
            <strong>Hermes session</strong>
            <span>${escapeHtml(summary||sessionId)}</span>
          </div>
          <div class="hermes-play-session-actions">
            <a class="hermes-play-session-action open-label" data-hermes-play-full-session href="${escapeHtml(fullSessionUrl)}" target="_blank" rel="noopener noreferrer">Open full</a>
            <button class="hermes-play-session-action" type="button" data-hermes-play-collapse>Hide</button>
          </div>
        </div>
        <div class="hermes-play-session-frame-wrap">
          <iframe class="hermes-play-session-frame" src="${escapeHtml(sessionUrl)}" title="Hermes session ${escapeHtml(sessionId)}" loading="lazy"></iframe>
          <div class="hermes-play-session-frame-status" data-hermes-play-session-loading>Loading linked Hermes session…</div>
          <div class="hermes-play-session-frame-status" data-hermes-play-session-frame-fallback hidden>
            <span>Session preview did not finish loading here.</span>
            <a href="${escapeHtml(fullSessionUrl)}" target="_blank" rel="noopener noreferrer">Open full session</a>
          </div>
        </div>
      </section>`:''}
    `;
    const toggle=root.querySelector('.hermes-play-session-toggle');
    const collapse=root.querySelector('[data-hermes-play-collapse]');
    const frame=root.querySelector('.hermes-play-session-frame');
    const feedback=root.querySelector('[data-hermes-play-feedback]');
    const loading=root.querySelector('[data-hermes-play-session-loading]');
    const fallback=root.querySelector('[data-hermes-play-session-frame-fallback]');
    let frameLoadSeen=false;
    let fallbackTimer=null;
    let verifyTimer=null;
    function hideLoading(){
      if(loading)loading.hidden=true;
    }
    function clearFrameTimers(){
      if(fallbackTimer){
        clearTimeout(fallbackTimer);
        fallbackTimer=null;
      }
      if(verifyTimer){
        clearTimeout(verifyTimer);
        verifyTimer=null;
      }
    }
    function frameInspectReady(){
      try{
        const doc=frame&&(frame.contentDocument||(frame.contentWindow&&frame.contentWindow.document));
        if(!doc||!doc.body)return false;
        return !!(doc.body.classList&&doc.body.classList.contains('ops-session-inspect'));
      }catch(_error){
        return false;
      }
    }
    function markFrameReady(){
      clearFrameTimers();
      hideLoading();
      if(frame){
        frame.hidden=false;
        frame.classList.remove('is-pending');
      }
      if(fallback)fallback.hidden=true;
    }
    function showFallback(){
      clearFrameTimers();
      hideLoading();
      if(frame)frame.hidden=true;
      if(fallback)fallback.hidden=false;
    }
    function scheduleFrameVerification(){
      const started=Date.now();
      const check=()=>{
        if(frameInspectReady()){
          markFrameReady();
          return;
        }
        if(Date.now()-started>=6000){
          showFallback();
          return;
        }
        verifyTimer=setTimeout(check,250);
      };
      check();
    }
    if(frame){
      frame.classList.add('is-pending');
      frame.addEventListener('load',()=>{
        frameLoadSeen=true;
        if(fallbackTimer){
          clearTimeout(fallbackTimer);
          fallbackTimer=null;
        }
        scheduleFrameVerification();
      });
      frame.addEventListener('error',showFallback);
      fallbackTimer=setTimeout(()=>{
        if(!frameLoadSeen)showFallback();
      },8000);
    }
    function setCollapsed(collapsed){
      root.classList.toggle('is-collapsed',collapsed);
      if(toggle)toggle.setAttribute('aria-expanded',collapsed?'false':'true');
      writeCollapsed(collapsed);
    }
    if(toggle)toggle.addEventListener('click',()=>setCollapsed(false));
    if(collapse)collapse.addEventListener('click',()=>setCollapsed(true));
    if(feedback)feedback.addEventListener('click',()=>startFeedbackFlow(feedback));
    document.body.appendChild(root);
    setCollapsed(root.classList.contains('is-collapsed'));
  }

  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',createOverlay,{once:true});
  }else{
    createOverlay();
  }
})();
