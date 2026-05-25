(function(){
  const DEFAULT_FORCE_MEDIA_RECORDER_KEY='mic_force_mediarecorder';
  const DEFAULT_TRANSCRIBE_URL='api/transcribe';

  function safeCall(fn){
    if(typeof fn!=='function')return undefined;
    try{return fn.apply(null,Array.prototype.slice.call(arguments,1));}
    catch(_error){return undefined;}
  }

  function optionValue(value){
    return typeof value==='function'?value():value;
  }

  function message(options,key,fallback,arg){
    const messages=options&&options.messages||{};
    const value=Object.prototype.hasOwnProperty.call(messages,key)?messages[key]:fallback;
    if(typeof value==='function'){
      const resolved=value(arg);
      return String(resolved||fallback||'');
    }
    return String(value||fallback||'');
  }

  function getStorageValue(windowRef,key){
    try{return windowRef&&windowRef.localStorage?windowRef.localStorage.getItem(key):null;}
    catch(_error){return null;}
  }

  function setStorageValue(windowRef,key,value){
    try{if(windowRef&&windowRef.localStorage)windowRef.localStorage.setItem(key,value);}
    catch(_error){}
  }

  function preferredAudioMimeType(MediaRecorderRef){
    if(!MediaRecorderRef)return '';
    const candidates=['audio/webm;codecs=opus','audio/webm','audio/ogg;codecs=opus','audio/ogg'];
    return candidates.find(type=>MediaRecorderRef.isTypeSupported&&MediaRecorderRef.isTypeSupported(type))||'';
  }

  function canRecordAudio(env){
    const options=env||{};
    const navigatorRef=options.navigatorRef||(typeof navigator!=='undefined'?navigator:null);
    const windowRef=options.windowRef||(typeof window!=='undefined'?window:null);
    const MediaRecorderRef=options.MediaRecorderRef||(windowRef&&windowRef.MediaRecorder)||(typeof MediaRecorder!=='undefined'?MediaRecorder:null);
    return !!(navigatorRef&&navigatorRef.mediaDevices&&navigatorRef.mediaDevices.getUserMedia&&MediaRecorderRef);
  }

  function isSupported(env){
    const options=env||{};
    const windowRef=options.windowRef||(typeof window!=='undefined'?window:null);
    const SpeechRecognitionRef=options.SpeechRecognitionRef||(windowRef&&(windowRef.SpeechRecognition||windowRef.webkitSpeechRecognition));
    return !!(SpeechRecognitionRef||canRecordAudio(options));
  }

  function appendTranscriptText(current,next){
    const clean=String(next||'').trim();
    const prefix=String(current||'');
    if(!clean)return prefix;
    if(prefix&&!prefix.endsWith(' ')&&!prefix.endsWith('\n'))return `${prefix} ${clean.trimStart()}`;
    return prefix+clean;
  }

  function createController(options){
    const opts=options||{};
    const windowRef=opts.windowRef||(typeof window!=='undefined'?window:null);
    const navigatorRef=opts.navigatorRef||(typeof navigator!=='undefined'?navigator:null);
    const MediaRecorderRef=opts.MediaRecorderRef||(windowRef&&windowRef.MediaRecorder)||(typeof MediaRecorder!=='undefined'?MediaRecorder:null);
    const SpeechRecognitionRef=opts.SpeechRecognitionRef||(windowRef&&(windowRef.SpeechRecognition||windowRef.webkitSpeechRecognition));
    const FormDataRef=opts.FormDataRef||(windowRef&&windowRef.FormData)||(typeof FormData!=='undefined'?FormData:null);
    const FileRef=opts.FileRef||(windowRef&&windowRef.File)||(typeof File!=='undefined'?File:null);
    const fetchRef=opts.fetchRef||(windowRef&&windowRef.fetch?windowRef.fetch.bind(windowRef):(typeof fetch!=='undefined'?fetch:null));
    const BlobRef=opts.BlobRef||(windowRef&&windowRef.Blob)||(typeof Blob!=='undefined'?Blob:null);
    const button=opts.button||null;
    const statusEl=opts.statusEl||null;
    const statusTextEl=opts.statusTextEl||null;
    const forceKey=String(opts.forceMediaRecorderKey||DEFAULT_FORCE_MEDIA_RECORDER_KEY);
    const supported=!!(SpeechRecognitionRef||canRecordAudio({navigatorRef,windowRef,MediaRecorderRef}));
    let forceMediaRecorder=!SpeechRecognitionRef||getStorageValue(windowRef,forceKey)==='1';
    let recognition=(!forceMediaRecorder&&SpeechRecognitionRef)?new SpeechRecognitionRef():null;
    let mediaRecorder=null;
    let mediaStream=null;
    let audioChunks=[];
    let finalText='';
    let prefix='';
    let active=false;
    let busy=false;
    let isRecording=false;
    let discardCurrent=false;
    let recognitionHadError=false;

    function getText(){
      if(typeof opts.getText==='function')return String(opts.getText()||'');
      if(opts.textarea)return String(opts.textarea.value||'');
      return '';
    }

    function setText(value,kind){
      const next=String(value||'');
      if(typeof opts.setText==='function')opts.setText(next,kind||'');
      else if(opts.textarea)opts.textarea.value=next;
      safeCall(opts.onTextChange,next,kind||'');
    }

    function setStatus(messageText,type){
      const text=String(messageText||'');
      if(statusTextEl&&text)statusTextEl.textContent=text;
      safeCall(opts.onStatus,text,type||'info');
    }

    function setBusy(on){
      busy=!!on;
      safeCall(opts.onBusyChange,busy);
      safeCall(opts.onTranscribingChange,busy);
    }

    function updateButtonTitle(on){
      if(!button)return;
      const title=String(optionValue(on?opts.activeTitle:opts.inactiveTitle)||'');
      if(!title)return;
      if(typeof opts.setButtonTooltip==='function')opts.setButtonTooltip(button,title);
      else button.title=title;
    }

    function setRecording(on,settings){
      const recordingOptions=settings||{};
      active=!!on;
      safeCall(opts.onActiveChange,active);
      if(button){
        button.classList.toggle('recording',active);
        updateButtonTitle(active);
      }
      if(statusEl)statusEl.style.display=active?'':'none';
      if(active)setStatus(message(opts,'listening','Listening'),'info');
      if(!active){
        finalText='';
        if(!busy&&!recordingOptions.preservePrefix)prefix='';
      }
    }

    function showError(text,error){
      const messageText=String(text||message(opts,'micNetwork','Microphone or transcription unavailable.'));
      safeCall(opts.onError,messageText,error||null);
      if(typeof opts.showToast==='function')opts.showToast(messageText);
      else setStatus(messageText,'error');
    }

    function clearPendingSend(){
      safeCall(opts.clearPendingSend);
    }

    function hasPendingSend(){
      return !!safeCall(opts.hasPendingSend);
    }

    function consumePendingSend(){
      if(!hasPendingSend())return;
      safeCall(opts.onPendingSend);
    }

    function commitTranscript(text,source){
      const clean=String(text||'').trim();
      const committed=clean?appendTranscriptText(prefix,clean):getText();
      setText(committed,'commit');
      safeCall(opts.onCommit,clean,committed,source||'');
      consumePendingSend();
      prefix='';
    }

    async function transcribeBlob(blob){
      if(!blob||!blob.size){
        clearPendingSend();
        safeCall(opts.onNoSpeech);
        return;
      }
      setBusy(true);
      setStatus(message(opts,'transcribing','Transcribing…'),'info');
      try{
        let transcript='';
        if(typeof opts.transcribeBlob==='function'){
          const data=await opts.transcribeBlob(blob);
          transcript=typeof data==='string'?data:String(data&&data.transcript||data&&data.text||'');
        }else{
          if(!FormDataRef||!fetchRef)throw new Error(message(opts,'transcriptionFailed','Transcription failed'));
          const mimeType=String(blob.type||'audio/webm').trim()||'audio/webm';
          const extension=mimeType.includes('ogg')?'ogg':'webm';
          const filename=String(optionValue(opts.filename)||`voice-input.${extension}`);
          const form=new FormDataRef();
          if(FileRef){
            form.append('file',new FileRef([blob],filename,{type:mimeType}),filename);
          }else{
            form.append('file',blob,filename);
          }
          const response=await fetchRef(String(opts.transcribeUrl||DEFAULT_TRANSCRIBE_URL),{method:'POST',body:form});
          const data=await response.json().catch(()=>({}));
          if(!response.ok)throw new Error(data.error||message(opts,'transcriptionFailed','Transcription failed'));
          transcript=String(data.transcript||data.text||'');
        }
        if(!String(transcript||'').trim()){
          clearPendingSend();
          setStatus(message(opts,'noSpeech','No speech detected.'),'error');
          safeCall(opts.onNoSpeech);
          return;
        }
        commitTranscript(transcript,'media-recorder');
      }catch(error){
        clearPendingSend();
        showError(error&&error.message?error.message:message(opts,'transcriptionFailed','Transcription failed'),error);
      }finally{
        setBusy(false);
      }
    }

    function stopTracks(){
      if(mediaStream&&typeof mediaStream.getTracks==='function'){
        mediaStream.getTracks().forEach(track=>{try{track.stop();}catch(_error){}});
      }
      mediaStream=null;
    }

    function stop(settings){
      const stopOptions=settings||{};
      if(stopOptions.discard)discardCurrent=true;
      if(!active&&!mediaRecorder){
        if(stopOptions.updateStatus!==false&&stopOptions.discard)setStatus(message(opts,'canceled','Dictation canceled.'),'info');
        return;
      }
      if(recognition&&active){
        try{recognition.stop();return;}
        catch(_error){}
      }
      if(mediaRecorder&&mediaRecorder.state!=='inactive'){
        try{mediaRecorder.stop();return;}
        catch(_error){}
      }
      setRecording(false);
      stopTracks();
    }

    async function start(){
      if(isRecording){
        stop();
        isRecording=false;
        return;
      }
      if(active){
        stop();
        return;
      }
      if(!supported){
        showError(message(opts,'unsupported','Voice dictation is not supported in this browser.'));
        return;
      }
      if(typeof opts.canStart==='function'&&!opts.canStart()){
        showError(String(optionValue(opts.canStartMessage)||message(opts,'unsupported','Voice dictation is not available right now.')));
        return;
      }
      isRecording=true;
      discardCurrent=false;
      recognitionHadError=false;
      finalText='';
      prefix=getText();
      if(recognition&&!forceMediaRecorder){
        try{
          recognition.start();
          setRecording(true);
          return;
        }catch(error){
          isRecording=false;
          showError(message(opts,'micNetwork','Unable to start microphone dictation.'),error);
          return;
        }
      }
      if(!canRecordAudio({navigatorRef,windowRef,MediaRecorderRef})||!BlobRef){
        isRecording=false;
        showError(message(opts,'micNetwork','Microphone recording is not supported in this browser.'));
        return;
      }
      setStatus(message(opts,'requesting','Requesting microphone access…'),'info');
      try{
        const constraints=typeof opts.audioConstraints==='function'?opts.audioConstraints():{audio:true};
        mediaStream=await navigatorRef.mediaDevices.getUserMedia(constraints||{audio:true});
        const mimeType=preferredAudioMimeType(MediaRecorderRef);
        mediaRecorder=new MediaRecorderRef(mediaStream,mimeType?{mimeType}:undefined);
        audioChunks=[];
        mediaRecorder.ondataavailable=event=>{if(event.data&&event.data.size)audioChunks.push(event.data);};
        mediaRecorder.onerror=error=>{
          isRecording=false;
          clearPendingSend();
          setRecording(false);
          stopTracks();
          showError(message(opts,'micNetwork','Recording error. Try again.'),error);
        };
        mediaRecorder.onstop=async()=>{
          isRecording=false;
          const chunks=audioChunks.slice();
          const mime=String(mediaRecorder&&mediaRecorder.mimeType||mimeType||'audio/webm');
          mediaRecorder=null;
          audioChunks=[];
          setRecording(false,{preservePrefix:true});
          stopTracks();
          if(discardCurrent){
            discardCurrent=false;
            clearPendingSend();
            prefix='';
            return;
          }
          if(chunks.length){
            await transcribeBlob(new BlobRef(chunks,{type:mime}));
          }else{
            clearPendingSend();
            setStatus(message(opts,'noAudio','No audio captured.'),'error');
            safeCall(opts.onNoSpeech);
          }
        };
        mediaRecorder.start();
        setRecording(true);
      }catch(error){
        isRecording=false;
        clearPendingSend();
        stopTracks();
        showError(message(opts,'micDenied','Microphone access was denied.'),error);
      }
    }

    function toggle(){
      return active?stop():start();
    }

    if(recognition&&!forceMediaRecorder){
      recognition.continuous=false;
      recognition.interimResults=true;
      recognition.lang=String(optionValue(opts.lang)||'en-US');
      recognition.onstart=()=>{finalText='';};
      recognition.onresult=event=>{
        let interim='';
        let final=finalText;
        for(let index=event.resultIndex;index<event.results.length;index+=1){
          const transcript=event.results[index][0].transcript;
          if(event.results[index].isFinal){final+=transcript;finalText=final;}
          else interim+=transcript;
        }
        setText(appendTranscriptText(prefix,final||interim),'preview');
      };
      recognition.onend=()=>{
        isRecording=false;
        const committed=finalText?appendTranscriptText(prefix,finalText):getText();
        const shouldCommit=!recognitionHadError&&!discardCurrent;
        setRecording(false);
        if(shouldCommit){
          setText(committed,'commit');
          safeCall(opts.onCommit,String(finalText||'').trim(),committed,'speech-recognition');
          consumePendingSend();
        }else{
          clearPendingSend();
        }
        discardCurrent=false;
        recognitionHadError=false;
        prefix='';
      };
      recognition.onerror=event=>{
        recognitionHadError=true;
        setRecording(false);
        clearPendingSend();
        isRecording=false;
        const errorName=String(event&&event.error||'');
        if(errorName==='network'||errorName==='not-allowed'){
          setStorageValue(windowRef,forceKey,'1');
          forceMediaRecorder=true;
          recognition=null;
        }
        const fallback={
          'not-allowed':message(opts,'micDenied','Microphone access was denied.'),
          'no-speech':message(opts,'noSpeech','No speech detected.'),
          network:message(opts,'micNetwork','Microphone network error.'),
        };
        showError(fallback[errorName]||message(opts,'micError',`Microphone error: ${errorName}`,errorName),event);
      };
    }

    if(button&&supported){
      button.style.display='';
      button.onclick=event=>{
        if(event&&event.preventDefault)event.preventDefault();
        return toggle();
      };
      updateButtonTitle(false);
    }

    return {
      isSupported:()=>supported,
      isActive:()=>active,
      isBusy:()=>busy,
      start,
      stop,
      toggle,
    };
  }

  window.HermesVoiceInput={
    createController,
    isSupported,
    canRecordAudio,
    preferredAudioMimeType,
    appendTranscriptText,
  };
})();
