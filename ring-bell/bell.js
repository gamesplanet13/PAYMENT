'use strict';
(function(){
 const $=s=>document.getElementById(s),role=document.body.dataset.role,other=role==='bell'?'ring':'bell',prefix='gp-bell-2026-',key='gp-bell-'+(role==='bell'?'receiver':'ring')+'-code';
 let code=localStorage.getItem(key);if(!/^\d{5}$/.test(code||'')){code=String(10000+Math.floor(Math.random()*90000));localStorage.setItem(key,code)}$('myCode').textContent=code;$('code').value=localStorage.getItem('gp-bell-target-'+role)||'';
 let peer=null,conn=null,local=null,cam=null,connections=[],state='idle',ready=false,muted=false,speakerMuted=false,remoteHasVideo=false;
 const status=s=>$('status').textContent=s,native=(name,arg)=>{try{if(window.BellNative)window.BellNative[name](arg)}catch(_){}};
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
 function release(){stopRinging();native('setCallAudio',false);let a=connections;connections=[];a.forEach(m=>{try{m.close()}catch(_){}});let c=conn;conn=null;if(c)try{c.close()}catch(_){};[local,cam].forEach(s=>{if(s)s.getTracks().forEach(t=>t.stop())});local=cam=null;for(let id of ['audio','remoteVideo','localVideo'])$(id).srcObject=null;state='idle';muted=false;remoteHasVideo=false;update()}
 function setupMedia(m){if(!m)return;connections.push(m);m.on('stream',remote=>{if(!connections.includes(m))return;let hasVideo=remote.getVideoTracks().length>0;let target=hasVideo?$('remoteVideo'):$('audio');target.srcObject=remote;target.muted=speakerMuted;let p=target.play();if(p&&p.catch)p.catch(()=>status('वीडियो या आवाज़ के लिए स्क्रीन छुएँ'));remoteHasVideo=hasVideo;native('setCallAudio',true)});m.on('error',()=>{if(connections.includes(m))status('वीडियो कनेक्शन में दिक्कत। इंटरनेट जाँचें।')})}
 async function microphone(){return navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:false})}
 async function previewCapture(){return navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:{facingMode:'user'}})}
 function setupData(c,outgoing){conn=c;
 const unanswered=setTimeout(()=>{if(conn===c&&['idle','calling','ringing','answering'].includes(state)){
  send({type:'hangup'});release();status('कॉल का जवाब नहीं मिला।');
 }},45000);
 c.on('close',()=>clearTimeout(unanswered));
 c.on('open',()=>{if(conn!==c)return;if(outgoing){send({type:'ring'});status('घंटी भेजी जा रही है…')}});c.on('data',m=>{if(conn!==c||!m)return;
 if(m.type==='ring'&&state==='idle'){state='ringing';update();startRinging();send({type:'preview-ready'});status('🔔 कॉल आ रही है। Pick करने तक आपका माइक बंद है।');return}
 if(m.type==='preview-ready'&&state==='calling'&&local){let call=peer.call(c.peer,local,{metadata:{kind:'preview'}});setupMedia(call);status('आपकी वीडियो भेजी जा रही है। जवाब का इंतज़ार करें।');return}
 if(m.type==='accepted'&&state==='calling'){state='active';update();status('कॉल जुड़ गई।');return}
 if(m.type==='busy'){release();status('दूसरा डिवाइस अभी कॉल पर है। थोड़ी देर बाद फिर कॉल करें।');return}
 if(m.type==='hangup'||m.type==='rejected'){release();status('कॉल समाप्त हुई।')}
 });c.on('close',()=>{if(conn===c){release();status('कनेक्शन बंद हुआ।')}});c.on('error',()=>{if(conn===c){release();status('कनेक्शन नहीं मिला।')}})}
 $('dial').onclick=async()=>{let target=$('code').value.trim();if(!/^\d{5}$/.test(target))return status('दूसरे डिवाइस का सही 5 अंकों का कोड डालें।');if(!ready||!peer||!peer.open)return status('इंटरनेट से कनेक्ट हो रहा है।');enableAudio().catch(()=>{});state='capturing';update();status('कैमरा और माइक की अनुमति दें…');try{const s=await previewCapture();if(state!=='capturing'){s.getTracks().forEach(t=>t.stop());return}local=s;$('localVideo').srcObject=s;localStorage.setItem('gp-bell-target-'+role,target);state='calling';update();let id=other==='bell'?prefix+target:prefix+'ring-'+target;let c=peer.connect(id,{reliable:true});setupData(c,true);status('डिवाइस जोड़ रहे हैं…');setTimeout(()=>{if(conn===c&&!c.open){release();status('डिवाइस नहीं मिला। कोड और इंटरनेट जाँचें।')}},25000)}catch(_){release();status('कैमरा और माइक की अनुमति दें।')}};
 $('accept').onclick=async()=>{if(state!=='ringing')return;stopRinging();enableAudio().catch(()=>{});state='answering';update();try{const s=await microphone();if(state!=='answering'){s.getTracks().forEach(t=>t.stop());return}local=s;state='active';native('setCallAudio',true);let call=peer.call(conn.peer,local,{metadata:{kind:'return'}});setupMedia(call);if(!send({type:'accepted'}))throw Error('disconnected');update();status('कॉल जुड़ गई। आपका कैमरा बंद है।')}catch(_){send({type:'rejected'});release();status('माइक्रोफोन की अनुमति जाँचें।')}};
 $('hangup').onclick=()=>{send({type:state==='ringing'?'rejected':'hangup'});release();status('कॉल समाप्त हुई।')};
 $('mic').onclick=()=>{if(!local)return;muted=!muted;local.getAudioTracks().forEach(t=>t.enabled=!muted);update()};
 $('camera').onclick=async()=>{if(state!=='active')return;let current=cam||(local&&local.getVideoTracks().length?local:null);if(current){let tracks=current.getVideoTracks();let enable=!tracks.some(t=>t.enabled);tracks.forEach(t=>t.enabled=enable);update();return}try{const s=await navigator.mediaDevices.getUserMedia({video:{facingMode:'user'},audio:false});if(state!=='active'){s.getTracks().forEach(t=>t.stop());return}cam=s;$('localVideo').srcObject=s;setupMedia(peer.call(conn.peer,s,{metadata:{kind:'camera'}}));update()}catch(_){status('कैमरा की अनुमति दें।')}};
 function volume(){let v=speakerMuted?0:Number($('volume').value);$('audio').muted=speakerMuted;$('remoteVideo').muted=speakerMuted;try{$('audio').volume=v/100;$('remoteVideo').volume=v/100}catch(_){}native('setSpeakerVolume',v)}
 $('speaker').onclick=()=>{speakerMuted=!speakerMuted;volume();update()};$('volume').oninput=()=>{speakerMuted=false;volume();update()};
 window.addEventListener('keydown',e=>{if(e.key==='F8'&&state==='idle'){$('dial').click();e.preventDefault()}});window.addEventListener('beforeunload',()=>{send({type:'hangup'});release()});
 if(!window.GurbaniPeer)return status('कनेक्शन लाइब्रेरी नहीं मिली।');let id=role==='bell'?prefix+code:prefix+'ring-'+code;
 GurbaniPeer.start({id:()=>id,onPeer:p=>{peer=p;p.on('call',m=>{if(!conn||m.peer!==conn.peer||!['ringing','answering','calling','active'].includes(state)){m.close();return}setupMedia(m);m.answer()})},onStatus:m=>{if(state==='idle')status(m)},onOpen:()=>{ready=true;if(state==='idle')status('तैयार है। दूसरे डिवाइस का कोड डालें।')},onConnection:c=>{if(state!=='idle'||conn){
  c.on('open',()=>{c.send({type:'busy'});setTimeout(()=>c.close(),400)});
  return;
 }setupData(c,false)},onCollision:()=>{ready=false;status('यह कोड व्यस्त है। बाद में दोबारा खोलें।')},onTargetUnavailable:()=>{if(state!=='idle'){release();status('दूसरा डिवाइस नहीं मिला। इंटरनेट और कोड जाँचें।')}}});update();
})();
