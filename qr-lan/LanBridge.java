package in.gamesplanet.qrlan;
import android.app.Activity;

import android.os.Build;
import android.webkit.JavascriptInterface;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
import org.json.JSONObject;

public final class LanBridge {
    private static final int DISCOVERY_PORT = 46824;
    private static final int MAX_FRAME = 128 * 1024;
    private static final String DISCOVERY = "GP_QR_CONNECTION_DISCOVER_V1";
    private final Activity activity;
    private final EventSink event;
    public interface EventSink { void emit(String kind, String id, String payload); }
    private final ExecutorService workers = Executors.newCachedThreadPool();
    private final Map<String, Link> links = new ConcurrentHashMap<>();
    private final Map<String, InetSocketAddress> targets = new ConcurrentHashMap<>();
    private final Set<Socket> sockets = Collections.newSetFromMap(new ConcurrentHashMap<>());
    private volatile boolean running = true;
    private volatile ServerSocket server;
    private volatile DatagramSocket discovery;
    private volatile android.net.wifi.WifiManager.MulticastLock wifiLock;
    private volatile String code;
    private volatile String role;

    public LanBridge(Activity activity, EventSink event) { this.activity = activity; this.event = event; }

    @JavascriptInterface public synchronized void start(String code, String role) {
        if (!running || code == null || !code.matches("[0-9]{5}") ||
            !("projection".equals(role) || "control".equals(role))) return;
        boolean listening = this.code != null;
        this.code = code;
        this.role = role;
        if (!listening) workers.execute(this::listen);
    }

    private void listen() {
        try {
            try {
                android.net.wifi.WifiManager wifi = (android.net.wifi.WifiManager)
                    activity.getApplicationContext().getSystemService(android.content.Context.WIFI_SERVICE);
                if (wifi != null) {
                    wifiLock = wifi.createMulticastLock("gp-qr-discovery");
                    wifiLock.setReferenceCounted(false);
                    wifiLock.acquire();
                }
            } catch (SecurityException ignored) {}
            server = new ServerSocket(0);
            if (!running) { server.close(); return; }
            workers.execute(this::advertise);
            while (running) {
                Socket socket = server.accept();
                if (sockets.size() >= 12) { socket.close(); continue; }
                sockets.add(socket);
                workers.execute(() -> accept(socket));
            }
        } catch (IOException ignored) {
            if (running) event.emit("listen-error", "", "");
        }
    }

    private boolean requestValid(JSONObject msg, String nonce) {
        return DISCOVERY.equals(msg.optString("type")) && nonce.matches("[a-f0-9-]{36}")
            && role.equals(msg.optString("role"))
            && (msg.optString("code").isEmpty() || code.equals(msg.optString("code")));
    }

    private void advertise() {
        try (DatagramSocket udp = new DatagramSocket(null)) {
            discovery = udp;
            udp.setReuseAddress(true);
            udp.setBroadcast(true);
            udp.bind(new InetSocketAddress(DISCOVERY_PORT));
            while (running) {
                DatagramPacket packet = new DatagramPacket(new byte[512], 512);
                udp.receive(packet);
                try {
                    JSONObject msg = new JSONObject(new String(packet.getData(), 0, packet.getLength(), StandardCharsets.UTF_8));
                    String nonce = msg.optString("nonce");
                    if (!requestValid(msg, nonce)) continue;
                    JSONObject reply = new JSONObject();
                    reply.put("type", DISCOVERY).put("nonce", nonce).put("role", role).put("code", code)
                         .put("port", server.getLocalPort()).put("name", Build.MODEL == null ? role : Build.MODEL);
                    byte[] data = reply.toString().getBytes(StandardCharsets.UTF_8);
                    udp.send(new DatagramPacket(data, data.length, packet.getSocketAddress()));
                } catch (org.json.JSONException ignored) {}
            }
        } catch (IOException ignored) {}
    }

    @JavascriptInterface public void search(String id, String targetCode) {
        if (!running || code == null || id == null || !id.matches("[a-f0-9-]{1,48}") ||
            targetCode == null || !targetCode.matches("([0-9]{5})?")) return;
        workers.execute(() -> findPeers(id, targetCode));
    }

    private Set<InetAddress> broadcastAddresses() throws IOException {
        Set<InetAddress> addresses = new LinkedHashSet<>();
        addresses.add(InetAddress.getByName("255.255.255.255"));
        for (NetworkInterface network : Collections.list(NetworkInterface.getNetworkInterfaces())) {
            if (!network.isUp() || network.isLoopback()) continue;
            for (InterfaceAddress ip : network.getInterfaceAddresses()) {
                if (ip.getBroadcast() != null) addresses.add(ip.getBroadcast());
            }
        }
        return addresses;
    }

    private void findPeers(String id, String targetCode) {
        String opposite = "projection".equals(role) ? "control" : "projection";
        String nonce = UUID.randomUUID().toString();
        try (DatagramSocket udp = new DatagramSocket()) {
            udp.setBroadcast(true);
            udp.setSoTimeout(400);
            JSONObject req = new JSONObject();
            req.put("type", DISCOVERY).put("nonce", nonce).put("role", opposite).put("code", targetCode);
            byte[] data = req.toString().getBytes(StandardCharsets.UTF_8);
            Set<InetAddress> addresses = broadcastAddresses();
            Set<String> seen = new HashSet<>();
            long end = android.os.SystemClock.elapsedRealtime() + (targetCode.isEmpty() ? 4200 : 1500);
            long resend = 0;
            while (running && android.os.SystemClock.elapsedRealtime() < end) {
                long now = android.os.SystemClock.elapsedRealtime();
                if (now >= resend) {
                    for (InetAddress address : addresses) {
                        try { udp.send(new DatagramPacket(data, data.length, address, DISCOVERY_PORT)); }
                        catch (IOException ignored) {}
                    }
                    resend = now + 700;
                }
                DatagramPacket packet = new DatagramPacket(new byte[1024], 1024);
                try { udp.receive(packet); } catch (SocketTimeoutException again) { continue; }
                try {
                    JSONObject reply = new JSONObject(new String(packet.getData(), 0, packet.getLength(), StandardCharsets.UTF_8));
                    String remoteCode = reply.optString("code");
                    int port = reply.optInt("port");
                    if (!DISCOVERY.equals(reply.optString("type")) || !nonce.equals(reply.optString("nonce"))
                        || !opposite.equals(reply.optString("role")) || !remoteCode.matches("[0-9]{5}")
                        || (!targetCode.isEmpty() && !targetCode.equals(remoteCode)) || port < 1 || port > 65535) continue;
                    InetSocketAddress address = new InetSocketAddress(packet.getAddress(), port);
                    if (!seen.add(remoteCode + "@" + address)) continue;
                    String key = UUID.randomUUID().toString();
                    if (targets.size() >= 128) targets.clear();
                    targets.put(key, address);
                    String name = reply.optString("name", opposite);
                    event.emit("found", id, new JSONObject().put("target", key).put("code", remoteCode)
                        .put("name", name.substring(0, Math.min(name.length(), 80))).toString());
                    if (!targetCode.isEmpty()) break;
                } catch (org.json.JSONException ignored) {}
            }
        } catch (Exception ignored) {
        } finally { event.emit("search-done", id, ""); }
    }

    @JavascriptInterface public void dial(String id, String target, String remoteCode) {
        if (!running || target == null || id == null || !id.matches("[a-f0-9-]{36}") || remoteCode == null || !remoteCode.matches("[0-9]{5}")) return;
        InetSocketAddress address = targets.get(target);
        if (address == null) { event.emit("closed", id, ""); return; }
        workers.execute(() -> {
            try (Socket socket = new Socket()) {
                sockets.add(socket);
                try {
                    socket.connect(address, 2500);
                    socket.setSoTimeout(5000);
                    socket.setTcpNoDelay(true);
                    Link link = new Link(socket);
                    link.write(new JSONObject().put("code", code).put("role", role).put("target", remoteCode).toString());
                    if (!"OK".equals(link.read())) return;
                    socket.setSoTimeout(0);
                    links.put(id, link);
                    event.emit("open", id, remoteCode);
                    pump(id, link);
                } finally { sockets.remove(socket); }
            } catch (Exception ignored) {
            } finally {
                links.remove(id);
                event.emit("closed", id, "");
            }
        });
    }

    private void accept(Socket socket) {
        String id = UUID.randomUUID().toString();
        try (Socket incoming = socket) {
            incoming.setSoTimeout(5000);
            incoming.setTcpNoDelay(true);
            Link link = new Link(incoming);
            JSONObject hello = new JSONObject(link.read());
            String remoteRole = "projection".equals(role) ? "control" : "projection";
            String remoteCode = hello.optString("code");
            if (!code.equals(hello.optString("target")) || !remoteRole.equals(hello.optString("role")) || !remoteCode.matches("[0-9]{5}")) return;
            link.write("OK");
            incoming.setSoTimeout(0);
            links.put(id, link);
            event.emit("incoming", id, remoteCode);
            pump(id, link);
        } catch (Exception ignored) {
        } finally {
            sockets.remove(socket);
            if (links.remove(id) != null) event.emit("closed", id, "");
        }
    }

    private void pump(String id, Link link) throws IOException {
        while (running) event.emit("frame", id, link.read());
    }

    @JavascriptInterface public void send(String id, String data) {
        Link link = id == null ? null : links.get(id);
        if (link == null || data == null || data.length() > MAX_FRAME) return;
        link.enqueue(data);
    }

    @JavascriptInterface public void close(String id) {
        Link link = id == null ? null : links.remove(id);
        if (link != null) link.close();
    }

    public void shutdown() {
        running = false;
        try { if (server != null) server.close(); } catch (IOException ignored) {}
        if (discovery != null) discovery.close();
        if (wifiLock != null && wifiLock.isHeld()) wifiLock.release();
        for (Socket socket : sockets) { try { socket.close(); } catch (IOException ignored) {} }
        links.clear();
        workers.shutdownNow();
    }

    private final class Link {
        final Socket socket;
        final DataInputStream input;
        final DataOutputStream output;
        final ArrayDeque<String> pending = new ArrayDeque<>();
        boolean draining;

        Link(Socket socket) throws IOException {
            this.socket = socket;
            input = new DataInputStream(new BufferedInputStream(socket.getInputStream()));
            output = new DataOutputStream(new BufferedOutputStream(socket.getOutputStream()));
        }
        String read() throws IOException {
            int length = input.readInt();
            if (length < 1 || length > MAX_FRAME) throw new IOException("Invalid frame");
            byte[] data = new byte[length];
            input.readFully(data);
            return new String(data, StandardCharsets.UTF_8);
        }
        void write(String value) throws IOException {
            byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
            if (bytes.length > MAX_FRAME) throw new IOException("Frame too large");
            output.writeInt(bytes.length);
            output.write(bytes);
            output.flush();
        }
        synchronized void enqueue(String data) {
            if (!running || socket.isClosed()) return;
            if (pending.size() >= 64) { close(); return; }
            pending.add(data);
            if (!draining) {
                draining = true;
                try { workers.execute(this::drain); }
                catch (RejectedExecutionException ignored) { close(); }
            }
        }
        private void drain() {
            while (running) {
                String value;
                synchronized (this) {
                    value = pending.poll();
                    if (value == null) { draining = false; return; }
                }
                try { write(value); } catch (IOException e) { close(); return; }
            }
        }
        void close() { try { socket.close(); } catch (IOException ignored) {} }
    }
}
