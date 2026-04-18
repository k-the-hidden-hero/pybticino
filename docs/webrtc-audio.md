# WebRTC Audio Mechanism

This document describes how the BTicino device's microphone is activated during WebRTC calls, discovered through reverse engineering of the official BTicino/Netatmo Android app.

## The Problem

When connecting to a BTicino intercom via WebRTC from a browser, the video stream works but **audio is silent** -- the device sends audio packets with an audioLevel of approximately 0.00003 (effectively zero). The device's microphone is not active.

Simply setting `a=sendrecv` in the SDP offer and adding a fake SSRC line is **not sufficient** to activate the microphone. The device requires actual RTP audio packets to be sent before it will enable its own microphone.

## How the Official App Does It

Analysis of the decompiled BTicino/Netatmo Android app (`com.netatmo.camera`) reveals the following audio setup:

### Audio Device Module

The app creates a `JavaAudioDeviceModule` with specific parameters:

- **Sample rate**: 48 kHz
- **Channels**: Mono
- **Echo cancellation**: Enabled
- **Noise suppression**: Enabled
- **Automatic gain control**: Enabled

### Audio Track Creation

Before creating the SDP offer, the app:

1. Creates a local audio source with constraints
2. Creates an audio track with the label `"ARDAMSa0"`
3. Adds the track to the PeerConnection
4. Immediately **disables** the track: `audioTrack.setEnabled(false)`

The critical insight is that even with the track disabled:

- The RTP sender is still active
- Silence packets are generated and sent
- The SSRC appears naturally in the SDP offer
- The device sees real RTP data arriving and activates its microphone

### MediaConstraints

The app uses these media constraints when creating offers:

```
OfferToReceiveAudio = true
OfferToReceiveVideo = true
```

No SDP manipulation is performed -- the SDP is sent exactly as produced by `createOffer()`.

## SDP Comparison

The key difference is in what the SDP contains and how the device responds:

### Browser (No Audio Track)

When the browser creates an offer without adding an audio track:

```
m=audio 9 UDP/TLS/RTP/SAVPF 111
a=mid:0
a=recvonly
(no a=ssrc line)
```

Device answer:

```
m=audio 9 UDP/TLS/RTP/SAVPF 111
a=sendonly
```

Result: Device sends audio packets containing silence (audioLevel ~0.00003).

### Browser (With Silence Oscillator)

When the browser creates an audio track using the AudioContext API:

```
m=audio 9 UDP/TLS/RTP/SAVPF 111
a=mid:0
a=sendrecv
a=ssrc:XXXXXXXX cname:xxxxxxxxxx
a=ssrc:XXXXXXXX msid:stream-id track-id
```

Device answer:

```
m=audio 9 UDP/TLS/RTP/SAVPF 111
a=sendrecv
a=ssrc:YYYYYYYY cname:userXXXX@host-XXXX
a=ssrc:YYYYYYYY msid:userXXXX@host-XXXX webrtctransceiverN
```

Result: Device activates microphone and sends **real audio** with meaningful audioLevel values.

### Official App (Disabled Mic Track)

The app's SDP offer looks nearly identical to the browser-with-oscillator case:

```
m=audio 9 UDP/TLS/RTP/SAVPF 111
a=mid:0
a=sendrecv
a=ssrc:XXXXXXXX cname:xxxxxxxxxxxx
a=ssrc:XXXXXXXX msid:stream-id ARDAMSa0
```

Device answer: Same as browser with oscillator -- `sendrecv` with real audio.

## Why Real RTP Matters

The device firmware appears to check whether actual RTP audio packets are arriving on the audio channel before enabling its own microphone. This is likely a power-saving or noise-reduction measure:

1. **No RTP arriving** (recvonly, no SSRC): Device assumes one-way monitoring and keeps mic off
2. **RTP arriving** (sendrecv with real SSRC, silence packets flowing): Device interprets this as an active call and enables the microphone

The SSRC in the SDP is necessary but not sufficient -- it's the actual RTP packet flow that triggers mic activation.

## Browser Solution: Silence Oscillator

To replicate the app's behavior in a browser, create a silent audio track using the Web Audio API:

```javascript
// Create an AudioContext and a silent oscillator
const audioContext = new AudioContext();
const oscillator = audioContext.createOscillator();
oscillator.frequency.value = 0; // 0 Hz = silence
const destination = audioContext.createMediaStreamDestination();
oscillator.connect(destination);
oscillator.start();

// Extract the audio track from the oscillator's stream
const silentAudioTrack = destination.stream.getAudioTracks()[0];

// Add to PeerConnection BEFORE creating the offer
peerConnection.addTrack(silentAudioTrack, destination.stream);

// Now createOffer() will naturally produce:
// - a=sendrecv (because there's a local audio track)
// - a=ssrc:XXXX (because the track has a real SSRC)
const offer = await peerConnection.createOffer();
```

This approach:

- Makes Chrome/Firefox generate `sendrecv` + real SSRC naturally
- Causes the RTP sender to emit silence packets (real RTP, just with zero audio)
- The device sees incoming RTP and activates its microphone
- No SDP manipulation is needed

## Device SDP Answer Reference

When audio is properly activated, the device's SDP answer includes:

```
m=audio 9 UDP/TLS/RTP/SAVPF 111
c=IN IP4 0.0.0.0
a=rtcp:9 IN IP4 0.0.0.0
a=mid:0
a=rtpmap:111 OPUS/48000/2
a=fmtp:111 minptime=10;useinbandfec=1;sprop-maxcapturerate=16000;sprop-stereo=1
a=sendrecv
a=setup:active
a=ssrc:XXXXXXXX cname:userXXXX@host-XXXX
a=ssrc:XXXXXXXX msid:userXXXX@host-XXXX webrtctransceiver0
```

Audio codec details:

| Parameter | Value | Notes |
|-----------|-------|-------|
| Codec | OPUS | Payload type 111 |
| Clock rate | 48000 Hz | Standard for OPUS |
| Channels | 2 (stereo) | Though actual capture is mono |
| Min ptime | 10 ms | Minimum packet time |
| In-band FEC | Enabled | Forward error correction |
| Max capture rate | 16000 Hz | 16 kHz capture (wideband) |
| Stereo | 1 | Stereo encoding supported |

## Video SDP Reference

The device's video SDP answer (included here for completeness):

```
m=video 9 UDP/TLS/RTP/SAVPF 103
c=IN IP4 0.0.0.0
a=rtcp:9 IN IP4 0.0.0.0
a=mid:1
a=rtpmap:103 H264/90000
a=rtcp-fb:103 nack pli
a=rtcp-fb:103 ccm fir
a=framerate:15
a=fmtp:103 level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=42001f
a=sendonly
a=setup:active
a=ssrc:YYYYYYYY cname:userXXXX@host-XXXX
a=ssrc:YYYYYYYY msid:userXXXX@host-XXXX webrtctransceiver1
```

Video parameters:

| Parameter | Value | Notes |
|-----------|-------|-------|
| Codec | H.264 | Payload type 103 |
| Profile | Constrained Baseline | profile-level-id 42001f |
| Frame rate | 15 fps | Fixed |
| Packetization | Mode 1 | NAL unit packetization |
| RTCP feedback | NACK, PLI, FIR | Packet loss recovery |
| Direction | sendonly | Device sends video, does not receive |

## Integration Notes

### For Home Assistant (bticino_intercom)

The HA WebRTC camera entity handles the SDP translation between the browser and the device:

1. **Browser offer has `recvonly` audio**: The entity rewrites it to `sendrecv` and injects a synthetic SSRC before sending to the device
2. **Device answers with `sendrecv`**: The entity rewrites it to `sendonly` before returning to the browser (since the browser's original offer was `recvonly`, RFC 3264 requires `sendonly` in the answer)
3. **Browser natively sends `sendrecv`** (e.g., with a two-way audio card): No rewriting needed -- the SDP passes through unchanged

### For Standalone Usage

When using `SignalingClient` directly (not through HA), you need to ensure your SDP offer includes:

1. `a=sendrecv` for the audio m-section
2. A real `a=ssrc:` line in the audio section
3. A real audio track added to the PeerConnection before creating the offer

The simplest approach in a browser is the silence oscillator technique described above.
