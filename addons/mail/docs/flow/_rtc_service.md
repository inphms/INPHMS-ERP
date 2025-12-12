# JAVASCRIPT

## RTC SERVICE
File: @mail/discuss/call/common/rtc_service.js
Depends:
    - bus_service
    - discuss.p2p
    - discuss.pip_service
    - discuss.ptt_extension
    - mail.fullscreen
    - mail.sound_effects
    - mail.store
    - legacy_multi_tab
    - notification
    - presence

### mail.store

purpose: storing data for mail flow

### device.pip_service

purpose: Picture-in-Picture services, managing small floating window

### discuss.p2p

purpose: P2P connection

flow:
- PeerToPeer()
- route = "/mail/rtc/session/notify_call_members"
- bus_service.subscribe(discuss.channel.rtc.session/peer_notification, ...)