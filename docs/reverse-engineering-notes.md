# Reverse Engineering Notes

Key findings from decompiling and analyzing the official BTicino/Netatmo Android app (`com.netatmo.camera`). These notes document the internal architecture of the app's WebRTC implementation, which informed the design of pybticino's `SignalingClient`.

## App State Machine

The app's WebRTC call setup follows a strict state machine with the following transitions:

```
IDLE
  └─► INITIALIZING_OPERATOR
        └─► INIT_PEER_CONNECTION
              └─► CREATE_OFFER
                    └─► SET_LOCAL_SDP
                          └─► SEND_LOCAL_OFFER
                                └─► SET_REMOTE_SDP
                                      └─► COMPLETED
```

### State Transition Details

| State | Action | Next State |
|-------|--------|------------|
| `IDLE` | Call initiated by user or incoming ring | `INITIALIZING_OPERATOR` |
| `INITIALIZING_OPERATOR` | Initialize WebRTC infrastructure, create `JavaAudioDeviceModule` | `INIT_PEER_CONNECTION` |
| `INIT_PEER_CONNECTION` | Create `PeerConnectionFactory`, configure ICE servers, create `PeerConnection` | `CREATE_OFFER` |
| `CREATE_OFFER` | Add audio track (disabled), call `createOffer()` with media constraints | `SET_LOCAL_SDP` |
| `SET_LOCAL_SDP` | Call `setLocalDescription()` with the generated offer | `SEND_LOCAL_OFFER` |
| `SEND_LOCAL_OFFER` | Send the SDP offer via the signaling WebSocket | `SET_REMOTE_SDP` |
| `SET_REMOTE_SDP` | Receive device answer, call `setRemoteDescription()` | `COMPLETED` |
| `COMPLETED` | WebRTC media is flowing | Terminal state |

### Timeout

Each state transition has a **20-second timeout**. If the transition does not complete within 20 seconds, the state machine performs a no-op (does not advance). After reaching `COMPLETED`, timeouts have no effect.

## PeerConnection Configuration

The app configures the PeerConnection with the following parameters:

```
Bundle Policy:          BALANCED
RTCP Mux Policy:        REQUIRE
ICE Candidate Pool:     0
ICE Transport Policy:   ALL
Continual Gathering:    GATHER_CONTINUALLY
TCP Candidates:         DISABLED
Key Type:               ECDSA
```

### ICE Candidate Filtering

The app filters ICE candidates before sending them through signaling:

- **UDP only**: TCP candidates are discarded
- **No loopback**: Candidates with loopback addresses (127.x.x.x) are filtered out
- All other UDP candidates (host, srflx, relay) are forwarded

## Audio Setup

### JavaAudioDeviceModule

The audio device module is configured with:

| Parameter | Value |
|-----------|-------|
| Sample rate | 48000 Hz |
| Channels | Mono |
| Echo cancellation | Enabled (`setWebRtcBasedAcousticEchoCanceler`) |
| Noise suppression | Enabled (`setWebRtcBasedNoiseSuppressor`) |
| Auto gain control | Enabled (`setWebRtcBasedAutomaticGainControl`) |

### Audio Track

| Property | Value |
|----------|-------|
| Label | `ARDAMSa0` |
| Kind | Audio |
| Initial state | Created, then immediately disabled via `setEnabled(false)` |
| Added to | PeerConnection before `createOffer()` |

Despite being disabled, the track generates a real SSRC in the SDP and the RTP sender emits silence packets. This is critical for activating the device's microphone (see [WebRTC Audio](webrtc-audio.md)).

### MediaConstraints

Applied when calling `createOffer()`:

```
OfferToReceiveAudio = true
OfferToReceiveVideo = true
```

## SDP Handling

### No SDP Manipulation

The app does **not** modify the SDP produced by `createOffer()` in any way. The SDP is sent to the signaling server exactly as WebRTC generates it. This means:

- The direction (`sendrecv`) comes naturally from having an audio track
- The SSRC comes naturally from the track's sender
- No manual injection of `a=ssrc:` lines
- No direction rewriting

### SDP Characteristics

The offer SDP produced by the app with the above configuration looks like:

```
v=0
o=- <session-id> 2 IN IP4 127.0.0.1
s=-
t=0 0
a=group:BUNDLE 0 1
a=msid-semantic: WMS <stream-id>

m=audio 9 UDP/TLS/RTP/SAVPF 111
a=mid:0
a=sendrecv
a=rtpmap:111 opus/48000/2
a=ssrc:<local-ssrc> cname:<local-cname>
a=ssrc:<local-ssrc> msid:<stream-id> ARDAMSa0

m=video 9 UDP/TLS/RTP/SAVPF 96 97 98 99 100 101 102 103
a=mid:1
a=recvonly
a=rtpmap:96 VP8/90000
a=rtpmap:97 VP9/90000
a=rtpmap:103 H264/90000
...
```

Key observations:

- Audio is `sendrecv` (due to local audio track)
- Video is `recvonly` (no local video track)
- Audio has a real SSRC
- Video has no SSRC

## Signaling Protocol

### Message Ack Timeout

Each signaling message sent to the server has a **10-second ack timeout**. If the server does not acknowledge the message within 10 seconds, the app considers the operation failed.

### No Keepalive During Sessions

The app does **not** send any keepalive, ping, or heartbeat messages during active WebRTC sessions. The WebSocket connection is maintained by TCP keepalive only.

### Signaling Messages Match pybticino

All signaling message formats observed in the decompiled app match pybticino's `SignalingClient` implementation exactly:

- Offer message structure
- Answer message structure
- ICE candidate structure
- Terminate message structure
- Subscribe message structure

## Network Architecture

### WebSocket Connections

The app maintains two separate WebSocket connections (same as pybticino):

| Connection | URL | Purpose |
|-----------|-----|---------|
| Push WS | `wss://app-ws.netatmo.net/ws/` | Long-lived connection for event notifications |
| Signaling WS | `wss://app-ws.netatmo.net/appws/` | On-demand connection for WebRTC signaling |

### TURN/STUN

The app fetches ICE server credentials from the Netatmo API before establishing peer connections. These credentials include TURN server URLs, usernames, and time-limited passwords.

### WebSocket Library

The app uses OkHttp's WebSocket implementation for both connections, with default SSL/TLS settings.

## Call Flow (Offer Mode -- On-Demand Viewing)

The complete call flow as observed in the app:

1. User taps "View Camera" in the app
2. App transitions to `INITIALIZING_OPERATOR`
3. App fetches TURN servers from `/turn` endpoint
4. App creates `JavaAudioDeviceModule` (48kHz, mono, echo/noise processing)
5. App creates `PeerConnectionFactory`
6. App creates `PeerConnection` with ICE servers and configuration
7. App creates audio source and track (`ARDAMSa0`)
8. App adds audio track to PeerConnection
9. App **disables** the audio track (`setEnabled(false)`)
10. App calls `createOffer()` with constraints
11. App calls `setLocalDescription()` with the offer
12. App connects to signaling WS (`appws/`) and subscribes
13. App sends the SDP offer via signaling
14. App receives ack with `session_id` and `tag_id`
15. App receives answer SDP from device
16. App calls `setRemoteDescription()` with the answer
17. ICE candidates are exchanged bidirectionally
18. WebRTC media begins flowing (video from device, silence audio from app)
19. State machine reaches `COMPLETED`
20. User hangs up: app sends `terminate` via signaling

## Call Flow (Answer Mode -- Incoming Call)

1. Push WS receives `BNC1-rtc` event with offer SDP
2. App displays incoming call UI
3. User taps "Answer"
4. App follows steps 3-9 above (TURN, PeerConnection, audio track)
5. App sets session state from push event parameters
6. App calls `createOffer()` (note: even in answer mode, the app creates an offer from its own PeerConnection)
7. App converts the browser-generated offer to an "answer" (changes DTLS `actpass` to `active`)
8. App sends the answer via signaling WS
9. ICE candidates are exchanged
10. WebRTC media begins flowing
11. The device's original offer SDP is used as the remote description

## Key Implementation Insights

### Discoveries That Informed pybticino

1. **Separate WebSocket endpoints**: The push and signaling WebSockets use different paths and `app_type` values. Mixing them up causes authentication failures or missing events.

2. **Ack field handling**: Only the first ack (for the offer) contains `session_id`/`tag_id`. Subsequent acks have null values. Overwriting session state with nulls breaks terminate.

3. **Audio track is required but disabled**: The seemingly paradoxical setup of creating then immediately disabling an audio track is the key to activating the device's microphone.

4. **No SDP manipulation needed**: The app proves that a clean SDP (as produced by WebRTC with the right track setup) works perfectly. SDP manipulation in the HA integration is only needed because the browser's offer lacks an audio track.

5. **20-second state timeout**: The relatively short timeout means the signaling setup must be fast. Pre-connecting the signaling WS and pre-fetching TURN servers is important.

6. **ICE filtering**: Only UDP candidates are forwarded. TCP candidates are always discarded.

7. **No keepalive**: The absence of application-level keepalive simplifies the implementation. Earlier versions of pybticino that sent WebSocket pings actually caused connection drops after ~10 minutes.
