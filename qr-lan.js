'use strict';

window.createQRLan = function (code, role, onConnection) {
  const bridge = window.GPQrLan;
  if (!bridge || typeof RTCPeerConnection !== 'function') return null;
  const links = new Map();
  const searches = new Map();
  const uuid = () => Array.from(crypto.getRandomValues(new Uint8Array(18)),
    byte => byte.toString(16).padStart(2, '0')).join('');

  async function description(pc) {
    if (pc.iceGatheringState !== 'complete') {
      await new Promise(resolve => {
        const timer = setTimeout(done, 2800);
        function done() {
          clearTimeout(timer);
          pc.removeEventListener('icegatheringstatechange', check);
          resolve();
        }
        function check() { if (pc.iceGatheringState === 'complete') done(); }
        pc.addEventListener('icegatheringstatechange', check);
      });
    }
    return pc.localDescription;
  }

  function connectRTC(id, isCaller) {
    const pc = new RTCPeerConnection({iceServers: []});
    const listeners = new Map();
    let channel;
    const signal = value => bridge.send(id, JSON.stringify(value));
    const c = {
      lan: true,
      open: false,
      on(name, handler) {
        const list = listeners.get(name) || [];
        list.push(handler);
        listeners.set(name, list);
      },
      emit(name, value) {
        for (const handler of listeners.get(name) || []) handler(value);
      },
      send(value) { if(c.open) channel.send(JSON.stringify(value)); },
      close() {
        if (!links.delete(id)) return;
        c.open = false;
        channel?.close();
        pc.close();
        bridge.close(id);
        c.emit('close');
      },
      start() {
        bind(pc.createDataChannel('games-planet-qr', {ordered:true}));
        (async () => {
          await pc.setLocalDescription(await pc.createOffer());
          signal(await description(pc));
        })().catch(() => c.close());
      },
      async frame(value) {
        if (!isCaller && value.type === 'offer') {
          await pc.setRemoteDescription(value);
          await pc.setLocalDescription(await pc.createAnswer());
          signal(await description(pc));
        } else if (isCaller && value.type === 'answer' && pc.signalingState === 'have-local-offer') {
          await pc.setRemoteDescription(value);
        }
      }
    };
    function bind(data) {
      channel = data;
      data.onopen = () => { c.open = true; c.emit('open'); };
      data.onmessage = event => {
        try { c.emit('data', JSON.parse(event.data)); } catch (_) {}
      };
      data.onclose = () => c.close();
      data.onerror = () => c.close();
    }
    pc.ondatachannel = event => bind(event.channel);
    pc.onconnectionstatechange = () => { if (pc.connectionState === 'failed') c.close(); };
    links.set(id, c);
    setTimeout(() => { if (!c.open) c.close(); }, 11000);
    return c;
  }

  window.gpQRLanEvent = (kind, id, payload) => {
    if (kind === 'found') { searches.get(id)?.found(JSON.parse(payload)); return; }
    if (kind === 'search-done') {
      const search = searches.get(id);
      searches.delete(id);
      search?.done();
      return;
    }
    if (kind === 'incoming') {
      if (role === 'projection') onConnection(connectRTC(id, false));
      else bridge.close(id);
      return;
    }
    const c = links.get(id);
    if (!c) { if (kind === 'open') bridge.close(id); return; }
    if (kind === 'open') c.start();
    if (kind === 'closed') c.close();
    if (kind === 'frame') c.frame(JSON.parse(payload)).catch(() => c.close());
  };
  bridge.start(code, role);
  return {
    search(code, found, done) {
      const id = uuid();
      searches.set(id, {found, done});
      bridge.search(id, code);
    },
    connect(target) {
      const id = uuid();
      const c = connectRTC(id, true);
      bridge.dial(id, target.target, target.code);
      return c;
    },
    close() {
      for (const c of links.values()) c.close();
      searches.clear();
    }
  };
};
