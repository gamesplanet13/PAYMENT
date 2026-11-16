/**
 * Games Planet ESP32 Doorbell - internet relay.
 * Deploy to Cloudflare Workers, bind KV namespace RING_EVENTS,
 * and configure DEVICE_TOKEN using Wrangler secret.
 * This does NOT provide video/audio or mobile push notifications.
 */
const corsHeaders={
 'Access-Control-Allow-Origin':'*',
 'Access-Control-Allow-Headers':'Authorization,Content-Type',
 'Access-Control-Allow-Methods':'GET,POST,OPTIONS',
 'Cache-Control':'no-store',
};
function json(data,status=200){return new Response(JSON.stringify(data),{status,headers:{...corsHeaders,'Content-Type':'application/json;charset=utf-8'}})}
function equal(a,b){
 if(a.length!==b.length)return false;
 let diff=0;for(let i=0;i<a.length;i++)diff|=a.charCodeAt(i)^b.charCodeAt(i);
 return diff===0;
}
export default {
 async fetch(request,env){
  if(request.method==='OPTIONS')return new Response(null,{status:204,headers:corsHeaders});
  if(!env.RING_EVENTS||!env.DEVICE_TOKEN)return json({error:'Relay not configured'},503);
  const url=new URL(request.url);
  if(url.pathname==='/health'&&request.method==='GET')return json({service:'Games Planet IoT Doorbell',status:'online'});
  if(!equal(request.headers.get('Authorization')||'','Bearer '+env.DEVICE_TOKEN))return json({error:'Unauthorized'},401);
  if(url.pathname==='/ring'&&request.method==='POST'){
    // Limit runaway button presses; soft rate limiting (KV is eventually consistent).
    const previous=Number(await env.RING_EVENTS.get('last-trigger-time')||0);
    const now=Date.now();
    if(now-previous<2500)return json({ok:true,ignored:true});
    const id=crypto.randomUUID();
    await env.RING_EVENTS.put('last-trigger-time',String(now));
    await env.RING_EVENTS.put('last-ring',JSON.stringify({id,at:now,type:'doorbell'}),{expirationTtl:86400});
    return json({ok:true,id,at:now});
  }
  if(url.pathname==='/events'&&request.method==='GET'){
    const value=await env.RING_EVENTS.get('last-ring','json');
    return json({event:value||null,serverTime:Date.now()});
  }
  return json({error:'Not found'},404);
 }
};
