'use strict';
(function(){
 const $=s=>document.getElementById(s),role=document.body.dataset.role,other=role==='bell'?'ring':'bell',prefix='gp-bell-2026-',key='gp-bell-'+(role==='bell'?'receiver':'ring')+'-code';
 let code=localStorage.getItem(key);if(!/^\d{5}$/.test(code||'')){code=String(10000+Math.floor(Math.random()*90000));localStorage.setItem(key,code)}$('myCode').textContent=code;$('code').value=localStorage.getItem('gp-bell-target-'+role)||'';
 let peer=null,conn=null,local=null,cam=null,connections=[],state='idle',dialSequence=0,ready=false,muted=false,speakerMuted=false,remoteHasVideo=false;
 const status=s=>$('status').textContent=s,native=(name,arg)=>{try{if(window.BellNative)window.BellNative[name](arg)}catch(_){}};
 const savedKey='gp-bell-saved-'+role, removeKey='gp-bell-remove-'+role;
 function readCodes(key){try{return new Set(JSON.parse(localStorage.getItem(key)||'[]').filter(c=>/^\d{5}$/.test(c)))}catch(_){return new Set()}}
 const contacts=readCodes(savedKey), pending=readCodes(removeKey), removalChannels=new Map(), removalLookups=new Set();
 function renderContacts(){
  const list=$('savedCodes');
  if(list?.replaceChildren)list.replaceChildren(...[...contacts].map(c=>{const item=document.createElement('option');item.value=c;return item}));
 }
 function persistContacts(){
  localStorage.setItem(savedKey,JSON.stringify([...contacts]));
  localStorage.setItem(removeKey,JSON.stringify([...pending]));
  renderContacts();
 }
 function peerCode(c){return typeof c?.peer==='string'?c.peer.match(/(\d{5})$/)?.[1]:null}
 function saveContact(c){
  const target=peerCode(c);if(!target)return;
  pending.delete(target);contacts.add(target);
  $('code').value=target;localStorage.setItem('gp-bell-target-'+role,target);persistContacts();
 }
 function forgetContact(target){
  contacts.delete(target);
  if(localStorage.getItem('gp-bell-target-'+role)===target)localStorage.removeItem('gp-bell-target-'+role);
  if($('code').value===target)$('code').value='';
  persistContacts();
 }
 function receiveRemoval(c,message){
  if(message?.type!=='forget-contact')return false;
  const target=peerCode(c);
  if(target){forgetContact(target);c.send({type:'contact-forgotten'});setTimeout(()=>c.close(),350)}
  return true;
 }
 renderContacts();
 let audioContext=null,ringTimer=null,tone=null;
 const audioButton=$('enableSound'),AudioContext=window.AudioContext||window.webkitAudioContext;
 audioButton.hidden=!!window.BellNative||!AudioContext;
 async function enableAudio(){
  if(window.BellNative||!AudioContext)return;
  audioContext??=new AudioContext();
  await audioContext.resume();
  audioButton.hidden=true;
  if(state==='ringing')startRinging();
 }
 audioButton.onclick=()=>enableAudio().catch(()=>status('घंटी की आवाज़ चालू नहीं हुई। फिर कोशिश करें।'));
 function startRinging(){
  if(window.BellNative){native('startRing');return}
  if(audioContext?.state!=='running'||ringTimer)return;
  const chime=()=>{
   const start=audioContext.currentTime,oscillator=audioContext.createOscillator(),volume=audioContext.createGain();
   oscillator.frequency.setValueAtTime(740,start);
   oscillator.frequency.setValueAtTime(520,start+.15);
   volume.gain.setValueAtTime(.18,start);
   volume.gain.exponentialRampToValueAtTime(.001,start+.42);
   oscillator.connect(volume).connect(audioContext.destination);
   oscillator.start();oscillator.stop(start+.43);
   tone=oscillator;
  };
  chime();ringTimer=setInterval(chime,1700);
 }
 function stopRinging(){
  native('stopRing');
  if(ringTimer){clearInterval(ringTimer);ringTimer=null}
  if(tone){try{tone.stop()}catch(_){}tone=null}
 }
 function update(){let active=state==='active',receiving=state==='ringing';$('dial').hidden=state!=='idle';$('accept').hidden=!receiving;$('hangup').hidden=state==='idle';$('videos').hidden=!(active||receiving||state==='calling');$('controls').hidden=!(active||receiving||state==='calling');$('mic').hidden=!local;$('camera').hidden=!active;$('mic').textContent=muted?'🎙️ माइक चालू करें':'🎙️ माइक बंद करें';$('speaker').textContent=speakerMuted?'🔇 स्पीकर चालू करें':'🔊 स्पीकर बंद करें';$('camera').textContent=cam&&cam.getVideoTracks().some(t=>t.enabled)?'📷 कैमरा बंद करें':'📷 कैमरा चालू करें'}
 function send(x){try{if(conn&&conn.open){conn.send(x);return true}}catch(_){}return false}
 function release(){dialSequence++;stopRinging();native('setCallAudio',false);let a=connections;connections=[];a.forEach(m=>{try{m.close()}catch(_){}});let c=conn;conn=null;if(c)try{c.close()}catch(_){};[local,cam].forEach(s=>{if(s)s.getTracks().forEach(t=>t.stop())});local=cam=null;for(let id of ['audio','remoteVideo','localVideo'])$(id).srcObject=null;state='idle';muted=false;remoteHasVideo=false;update()}
 function startMedia(channel,stream,kind){return channel.lan?channel.call(stream):peer.call(channel.peer,stream,{metadata:{kind}})}
 function setupMedia(m){if(!m)return;connections.push(m);m.on('stream',remote=>{if(!connections.includes(m))return;let hasVideo=remote.getVideoTracks().length>0;let target=hasVideo?$('remoteVideo'):$('audio');target.srcObject=remote;target.muted=speakerMuted;let p=target.play();if(p&&p.catch)p.catch(()=>status('वीडियो या आवाज़ के लिए स्क्रीन छुएँ'));remoteHasVideo=hasVideo;native('setCallAudio',true)});m.on('error',()=>{if(connections.includes(m))status('वीडियो कनेक्शन में दिक्कत। अपना नेटवर्क जाँचें।')})}
 async function microphone(){return navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:false})}
 async function previewCapture(){
  try{return await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:{facingMode:'user'}})}
  catch(e){if(!['NotFoundError','NotReadableError','NotAllowedError','OverconstrainedError'].includes(e.name))throw e;return microphone()}
 }
 function setupData(c,outgoing){conn=c;
 const unanswered=setTimeout(()=>{if(conn===c&&['idle','calling','ringing','answering'].includes(state)){
  send({type:'hangup'});release();status('कॉल का जवाब नहीं मिला।');
 }},45000);
 c.on('close',()=>clearTimeout(unanswered));
 c.on('open',()=>{if(conn!==c)return;if(outgoing){send({type:'ring'});status('घंटी भेजी जा रही है…')}});c.on('data',m=>{if(conn!==c||!m||receiveRemoval(c,m))return;
 if(m.type==='ring'&&state==='idle'){state='ringing';update();startRinging();send({type:'preview-ready'});status('🔔 कॉल आ रही है। कॉल उठाने तक आपका माइक बंद है।');return}
 if(m.type==='preview-ready'&&state==='calling'&&local){let call=startMedia(c,local,'preview');setupMedia(call);status(local.getVideoTracks().length?'आपकी वीडियो भेजी जा रही है। जवाब का इंतज़ार करें।':'आपकी आवाज़ भेजी जा रही है। जवाब का इंतज़ार करें।');return}
 if(m.type==='accepted'&&state==='calling'){saveContact(c);state='active';update();status('कॉल जुड़ गई।');return}
 if(m.type==='busy'){release();status('दूसरा डिवाइस अभी कॉल पर है। थोड़ी देर बाद फिर कॉल करें।');return}
 if(m.type==='hangup'||m.type==='rejected'){release();status('कॉल समाप्त हुई।')}
 });c.on('close',()=>{if(conn===c){release();status('कनेक्शन बंद हुआ।')}});c.on('error',()=>{if(conn===c){release();status('कनेक्शन नहीं मिला।')}})}
 function receiveCall(m,channel){
  if(!conn||(channel?channel!==conn:m.peer!==conn.peer)||!['ringing','answering','calling','active'].includes(state)){m.close();return}
  setupMedia(m);m.answer();
 }
 function receiveConnection(c){
  if(state!=='idle'||conn){
   let replied=false;
   c.on('data',m=>{if(receiveRemoval(c,m))replied=true});
   c.on('open',()=>setTimeout(()=>{if(!replied&&c.open){c.send({type:'busy'});setTimeout(()=>c.close(),350)}},250));
   return;
  }
  setupData(c,false);
 }
 const lan=window.createRingBellLan?.(code,role,receiveConnection,receiveCall);
 if(lan){
  $('wifiPanel').hidden=false;
  $('wifiSearch').onclick=()=>{
   const results=$('wifiResults'),hint=$('wifiStatus');
   results.replaceChildren();
   $('wifiSearch').disabled=true;
   hint.textContent='इस Wi-Fi पर डिवाइस ढूँढ रहे हैं…';
   lan.search('',found=>{
    const button=document.createElement('button');
    button.type='button';button.className='secondary';
    button.textContent=found.name+' · '+found.code+' · कॉल करें';
    button.onclick=()=>{$('code').value=found.code;dial(found)};
    results.append(button);
   },()=>{
    $('wifiSearch').disabled=false;
    hint.textContent=results.childElementCount?'कॉल के लिए डिवाइस चुनें।':'कोई डिवाइस नहीं मिला। दोनों ऐप खोलकर उसी Wi-Fi पर दोबारा खोजें।';
   });
  };
 }
 function findOnLan(target){
  if(!lan)return Promise.resolve(null);
  return new Promise(resolve=>{
   let found=null,finished=false;
   const finish=()=>{if(finished)return;finished=true;clearTimeout(timeout);resolve(found)};
   const timeout=setTimeout(finish,2500);
   try{lan.search(target,result=>{if(result?.code===target){found=result;finish()}},finish)}
   catch(_){finish()}
  });
 }
 async function dial(discovered){
  if(state!=='idle'||conn)return;
  const target=$('code').value.trim();
  if(!/^\d{5}$/.test(target))return status('दूसरे डिवाइस का सही 5 अंकों का कोड डालें।');
  if(pending.delete(target))persistContacts();
  const removal=removalChannels.get(target);if(removal){removalChannels.delete(target);removal.close()}
  const sequence=++dialSequence;
  enableAudio().catch(()=>{});state='capturing';update();
  status('कैमरा और माइक की अनुमति दें…');
  try{
   const s=await previewCapture();
   if(sequence!==dialSequence){s.getTracks().forEach(t=>t.stop());return}
   local=s;$('localVideo').srcObject=s;
  }catch(_){if(sequence===dialSequence){release();status('कैमरा और माइक की अनुमति दें।')}return}
  status('डिवाइस ढूँढ रहे हैं…');
  // When internet signaling is online, do not block a remote call on Wi-Fi discovery.
  const found=discovered||(ready&&peer?.open?null:await findOnLan(target));
  if(sequence!==dialSequence)return;
  if(!found&&(!ready||!peer||!peer.open)){
   release();status('डिवाइस Wi-Fi पर नहीं मिला और इंटरनेट कनेक्शन तैयार नहीं है।');return;
  }
  localStorage.setItem('gp-bell-target-'+role,target);state='calling';update();
  try{
   const id=other==='bell'?prefix+target:prefix+'ring-'+target;
   const c=found?lan.connect(found):peer.connect(id,{reliable:true});
   setupData(c,true);
   status(found?'Wi-Fi पर कॉल जोड़ रहे हैं…':'इंटरनेट से कॉल जोड़ रहे हैं…');
   setTimeout(()=>{if(conn===c&&!c.open){release();status('डिवाइस नहीं मिला। कोड और नेटवर्क जाँचें।')}},25000);
  }catch(_){release();status('कनेक्शन नहीं बना। फिर कोशिश करें।')}
 }
 function tryRemovals(){
  for(const target of pending){
   if(removalChannels.has(target)||removalLookups.has(target))continue;
   removalLookups.add(target);
   (async ()=>{
    const found=ready&&peer?.open?null:await findOnLan(target);
    if(!pending.has(target)||(!found&&(!ready||!peer?.open)))return;
    const id=other==='bell'?prefix+target:prefix+'ring-'+target;
    const c=found?lan.connect(found):peer.connect(id,{reliable:true});
    removalChannels.set(target,c);
    const clear=()=>{if(removalChannels.get(target)===c)removalChannels.delete(target)};
    c.on('open',()=>c.send({type:'forget-contact'}));
    c.on('data',m=>{if(m?.type==='contact-forgotten'){
     pending.delete(target);persistContacts();clear();c.close();
     if(state==='idle')status('दूसरे डिवाइस ने हटाने की पुष्टि की।');
    }});
    c.on('close',clear);c.on('error',clear);
    setTimeout(()=>{if(removalChannels.get(target)===c){clear();c.close()}},6500);
   })().catch(()=>{}).finally(()=>removalLookups.delete(target));
  }
 }
 $('removeTarget').onclick=()=>{
  const target=$('code').value.trim();
  if(!/^\d{5}$/.test(target))return status('हटाने के लिए 5 अंकों का कोड डालें।');
  pending.add(target);forgetContact(target);tryRemovals();
  status('डिवाइस हटाया गया। दूसरे डिवाइस के ऑनलाइन होने पर वहाँ से भी हटेगा।');
 };
 const removalTimer=typeof window.setInterval==='function'?window.setInterval(tryRemovals,6000):null;
 window.addEventListener('online',tryRemovals);
 // IoT ESP32 bell alerts use a separate authenticated Internet relay.
 // They never impersonate a PeerJS camera/voice call.
 if(role==='bell'&&$('iotSettings')){
   const key='gp-bell-iot-v1';
   let config=null,seen='',iotRinging=false,firstRead=true;
   try{config=JSON.parse(localStorage.getItem(key)||'null')}catch(_){}
   const relay=$('iotRelay'),secret=$('iotToken'),label=$('iotStatus');
   if(config){relay.value=config.url||'';secret.value=config.token||''}
   function valid(){
     const url=relay.value.trim().replace(/\\/+$/,'');
     const token=secret.value.trim();
     if(!/^https:\/\/[^\\s/]+(?:\/[^\\s]*)?$/.test(url)||token.length<32)return null;
     return {url,token};
   }
   $('iotSave').onclick=()=>{
     const next=valid();
     if(!next){label.textContent='Enter an HTTPS Worker URL and the same 32+ character secret as the ESP32.';return}
     config=next;localStorage.setItem(key,JSON.stringify(config));firstRead=true;seen='';label.textContent='Saved. Checking Internet relay…';checkRelay();
   };
   async function checkRelay(){
     if(!config||document.hidden)return;
     try{
       const response=await fetch(config.url+'/events',{cache:'no-store',
         headers:{Authorization:'Bearer '+config.token},signal:AbortSignal.timeout(5500)});
       if(!response.ok)throw Error('HTTP '+response.status);
       const packet=await response.json();
       label.textContent='● IoT Internet relay connected';
       const event=packet.event;
       if(event&&typeof event.id==='string'&&Number.isFinite(event.at)){
         const previous=localStorage.getItem('gp-bell-iot-last-event')||'';
         if(firstRead){firstRead=false;seen=previous||event.id}
         if(event.id!==seen&&event.id!==previous&&Date.now()-event.at<90000&&event.at<=Date.now()+10000){
           seen=event.id;localStorage.setItem('gp-bell-iot-last-event',seen);
           if(state==='idle'&&!iotRinging){
             iotRinging=true;
             state='ringing';update();startRinging();
             status('🔔 ESP32 Doorbell: कोई दरवाज़े पर है। इस संस्करण में वीडियो और ऑडियो उपलब्ध नहीं।');
           }
         }else if(!seen){seen=event.id}
       }
     }catch(err){label.textContent='IoT relay offline: '+(err?.message||'connection error')}
   }
   setInterval(checkRelay,2500);
   window.addEventListener('online',checkRelay);
   window.addEventListener('focus',checkRelay);
   $('accept').addEventListener('click',()=>{
     if(iotRinging){iotRinging=false;release();status('ESP32 doorbell acknowledged. Video / two-way audio will be added in the next phase.')}
   },true);
   $('hangup').addEventListener('click',()=>{if(iotRinging){iotRinging=false;release();status('Doorbell alert dismissed.')}},true);
   checkRelay();
 }
 $('dial').onclick=()=>dial(null);
 $('accept').onclick=async()=>{if(state!=='ringing')return;stopRinging();enableAudio().catch(()=>{});state='answering';update();try{const s=await microphone();if(state!=='answering'){s.getTracks().forEach(t=>t.stop());return}local=s;state='active';native('setCallAudio',true);let call=startMedia(conn,local,'return');setupMedia(call);if(!send({type:'accepted'}))throw Error('disconnected');saveContact(conn);update();status('कॉल जुड़ गई। आपका कैमरा बंद है।')}catch(_){send({type:'rejected'});release();status('माइक्रोफोन की अनुमति जाँचें।')}};
 $('hangup').onclick=()=>{send({type:state==='ringing'?'rejected':'hangup'});release();status('कॉल समाप्त हुई।')};
 $('mic').onclick=()=>{if(!local)return;muted=!muted;local.getAudioTracks().forEach(t=>t.enabled=!muted);update()};
 $('camera').onclick=async()=>{if(state!=='active')return;let current=cam||(local&&local.getVideoTracks().length?local:null);if(current){let tracks=current.getVideoTracks();let enable=!tracks.some(t=>t.enabled);tracks.forEach(t=>t.enabled=enable);update();return}try{const s=await navigator.mediaDevices.getUserMedia({video:{facingMode:'user'},audio:false});if(state!=='active'){s.getTracks().forEach(t=>t.stop());return}cam=s;$('localVideo').srcObject=s;setupMedia(startMedia(conn,s,'camera'));update()}catch(_){status('कैमरा की अनुमति दें।')}};
 function volume(){let v=speakerMuted?0:Number($('volume').value);$('audio').muted=speakerMuted;$('remoteVideo').muted=speakerMuted;try{$('audio').volume=v/100;$('remoteVideo').volume=v/100}catch(_){}native('setSpeakerVolume',v)}
 $('speaker').onclick=()=>{speakerMuted=!speakerMuted;volume();update()};$('volume').oninput=()=>{speakerMuted=false;volume();update()};
 window.addEventListener('keydown',e=>{if(e.key==='F8'&&state==='idle'){$('dial').click();e.preventDefault()}});window.addEventListener('beforeunload',()=>{if(removalTimer)clearInterval(removalTimer);send({type:'hangup'});release()});
 if(!window.GurbaniPeer)return status('कनेक्शन लाइब्रेरी नहीं मिली।');let id=role==='bell'?prefix+code:prefix+'ring-'+code;
 GurbaniPeer.start({id:()=>id,
  onPeer:p=>{peer=p;p.on('call',m=>receiveCall(m,null))},
  onStatus:m=>{if(state==='idle'&&!lan)status(m)},
  onOpen:()=>{ready=true;if(state==='idle')status('तैयार है। दूसरे डिवाइस का कोड डालें।')},
  onConnection:receiveConnection,
  onCollision:()=>{ready=false;if(!lan)status('यह कोड व्यस्त है। बाद में दोबारा खोलें।')},
  onTargetUnavailable:e=>{if(conn&&!conn.lan&&String(e?.message||'').endsWith(conn.peer)){release();status('दूसरा डिवाइस नहीं मिला। इंटरनेट और कोड जाँचें।')}},
 });
 if(lan)status('Wi-Fi पर खोजें या दूसरे डिवाइस का कोड डालें।');
 update();
})();
