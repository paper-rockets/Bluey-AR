# BLUEY3d

Browser toys built on a procedural rig engine (`rig_engine.js`) driven by
MediaPipe pose tracking. Three.js for rendering, no build step — plain ES
modules loaded straight from the HTML.

## Crew

`Crew/crew.html` — all four characters on screen at once, each dancing its own
dance and reacting independently to your movement (wave, cheer, or just move
around and they'll join in). Music player, starfield, floating notes, and a
phone remote.

## Running it

The apps need to be served over HTTP (ES modules and `fetch` don't work from
`file://`):

```bash
py remote_server.py 8937
```

Then open <http://localhost:8937/Crew/crew.html>.

`remote_server.py` is a plain static file server plus a small in-memory command
relay, so a phone on the same Wi-Fi can drive the display. It prints both URLs
on startup.

## Phone remote

The display shows the remote's address in its top-right corner. Open that on a
phone: switch characters, control music, trigger reactions.

It works two ways, picked automatically (`Crew/relay.js`):

- **Local** — when `remote_server.py` is serving, the phone POSTs to `/api/cmd`
  and the display polls it. Same Wi-Fi, nothing leaves the network, lowest
  latency. No room code needed.
- **Cloud** — on a static host like GitHub Pages there is no server to relay
  through, so both ends meet on a public MQTT broker over WSS. The display
  generates a 5-character **room code** and shows it; the remote link already
  carries it in the URL hash (`remote.html#W5NKB`), or you can type it in on the
  phone. Both devices must be in the same room.

The cloud path leans on free public brokers (HiveMQ, with Mosquitto as
fallback). They're best-effort with no uptime guarantee, and the room code is
the only thing keeping a channel private — fine for switching cartoon
characters, don't build anything sensitive on it. The local path is preferred
whenever it's available.

## Music

Drop `.mp3` files into `Music/`. They're picked up automatically on any server
that lists directories; `FALLBACK_TRACKS` in `Crew/crew.html` is the hardcoded
list used when the host doesn't.

The music player also drives the visuals — low-end energy pulses each character
and spawns floating notes.

## Credits

Bluey, Bingo, Kuromi and Pompompurin are the property of their respective
rights holders. This is a personal, non-commercial fan project.
