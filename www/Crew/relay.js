// relay.js — one command channel, two transports.
//
//   local   remote_server.py serves /api/cmd, so the phone POSTs and the display
//           polls. Same Wi-Fi, no third party, lowest latency.
//   cloud   On a static host (GitHub Pages) there is no server at all, so both
//           ends meet on a public MQTT broker over WSS and exchange the very
//           same JSON commands.
//
// Both return the same handle, so the pages don't care which one they got:
//     { mode, room, send(cmd), remoteUrl }

const BROKERS = [
    'wss://broker.hivemq.com:8884/mqtt',
    'wss://test.mosquitto.org:8081/mqtt',
];
const MQTT_SRC = 'https://cdn.jsdelivr.net/npm/mqtt@5/dist/mqtt.min.js';
const ROOM_KEY = 'crew.room';
const topicFor = room => `bluey3d/${room}/cmd`;

// Ambiguous glyphs (0/O, 1/I/l) left out — this gets typed in off a screen.
export function makeRoom() {
    const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    const bytes = new Uint8Array(5);
    crypto.getRandomValues(bytes);
    return [...bytes].map(b => alphabet[b % alphabet.length]).join('');
}

// URL hash wins (that's how the phone is handed a room), then whatever this
// device used last, then a fresh one.
export function resolveRoom({ create = true } = {}) {
    const fromHash = location.hash.replace(/^#/, '').trim().toUpperCase();
    if (/^[A-Z0-9]{4,8}$/.test(fromHash)) {
        localStorage.setItem(ROOM_KEY, fromHash);
        return fromHash;
    }
    const saved = localStorage.getItem(ROOM_KEY);
    if (saved) return saved;
    if (!create) return null;
    const fresh = makeRoom();
    localStorage.setItem(ROOM_KEY, fresh);
    return fresh;
}

async function localRelay() {
    try {
        const res = await fetch('/api/info', { cache: 'no-store' });
        if (!res.ok) return null;
        return await res.json();       // { lan, port }
    } catch {
        return null;                   // static host, or server not running
    }
}

function loadMqtt() {
    if (window.mqtt) return Promise.resolve(window.mqtt);
    return new Promise((resolve, reject) => {
        const s = document.createElement('script');
        s.src = MQTT_SRC;
        s.onload = () => (window.mqtt ? resolve(window.mqtt) : reject(new Error('mqtt global missing')));
        s.onerror = () => reject(new Error('could not load mqtt.js'));
        document.head.appendChild(s);
    });
}

// ── local transport ────────────────────────────────────────────────────
function openLocal(info, { onCommand, onStatus }) {
    const base = `${location.origin}${location.pathname.replace(/[^/]*$/, '')}remote.html`;

    if (onCommand) {
        let since = null;              // null until the first sync, so a backlog
        setInterval(async () => {      // of old commands is never replayed
            try {
                const res = await fetch(`/api/cmd?since=${since ?? 0}`, { cache: 'no-store' });
                if (!res.ok) throw new Error(res.status);
                const data = await res.json();
                if (since !== null) for (const c of data.cmds ?? []) onCommand(c);
                since = data.seq ?? 0;
                onStatus?.(true, 'local');
            } catch {
                onStatus?.(false, 'local');
            }
        }, 400);
    }

    return {
        mode: 'local',
        room: null,
        remoteUrl: info.lan ? `http://${info.lan}:${info.port}/Crew/remote.html` : base,
        async send(cmd) {
            const res = await fetch('/api/cmd', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(cmd),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
        },
    };
}

// ── cloud transport ────────────────────────────────────────────────────
async function openCloud(room, { onCommand, onStatus }) {
    const mqtt = await loadMqtt();
    const topic = topicFor(room);
    let client = null;
    let brokerIdx = 0;

    const connect = () => {
        const url = BROKERS[brokerIdx % BROKERS.length];
        client = mqtt.connect(url, {
            clientId: `crew_${Math.random().toString(16).slice(2, 10)}`,
            connectTimeout: 7000,
            reconnectPeriod: 4000,
            clean: true,
        });

        client.on('connect', () => {
            onStatus?.(true, 'cloud');
            if (onCommand) client.subscribe(topic, { qos: 0 });
        });
        client.on('message', (_t, payload) => {
            try { onCommand?.(JSON.parse(payload.toString())); } catch { /* not ours */ }
        });
        client.on('close', () => onStatus?.(false, 'cloud'));
        client.on('error', () => onStatus?.(false, 'cloud'));
    };

    // If the first broker never comes up, fail over to the second once.
    connect();
    setTimeout(() => {
        if (!client?.connected && brokerIdx === 0) {
            brokerIdx = 1;
            try { client.end(true); } catch { /* already gone */ }
            connect();
        }
    }, 9000);

    const remoteBase = `${location.origin}${location.pathname.replace(/[^/]*$/, '')}remote.html`;
    return {
        mode: 'cloud',
        room,
        remoteUrl: `${remoteBase}#${room}`,
        async send(cmd) {
            if (!client?.connected) throw new Error('not connected');
            client.publish(topic, JSON.stringify(cmd), { qos: 0 });
        },
    };
}

// Prefers the local relay; falls back to the public broker. `onCommand` is only
// passed by the display — the phone just sends.
export async function openChannel({ onCommand, onStatus, room } = {}) {
    const info = await localRelay();
    if (info) return openLocal(info, { onCommand, onStatus });
    return openCloud(room ?? resolveRoom(), { onCommand, onStatus });
}
