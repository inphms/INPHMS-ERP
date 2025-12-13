/** @inphms-module alias=@inphms/hoot-mock default=false */

import * as _hootDom from "@inphms/hoot-dom";
import * as _animation from "./mock/animation";
import * as _date from "./mock/date";
import * as _math from "./mock/math";
import * as _navigator from "./mock/navigator";
import * as _network from "./mock/network";
import * as _notification from "./mock/notification";
import * as _window from "./mock/window";

/** @deprecated use `import { advanceFrame } from "@inphms/hoot";` */
export const advanceFrame = _hootDom.advanceFrame;
/** @deprecated use `import { advanceTime } from "@inphms/hoot";` */
export const advanceTime = _hootDom.advanceTime;
/** @deprecated use `import { animationFrame } from "@inphms/hoot";` */
export const animationFrame = _hootDom.animationFrame;
/** @deprecated use `import { cancelAllTimers } from "@inphms/hoot";` */
export const cancelAllTimers = _hootDom.cancelAllTimers;
/** @deprecated use `import { Deferred } from "@inphms/hoot";` */
export const Deferred = _hootDom.Deferred;
/** @deprecated use `import { delay } from "@inphms/hoot";` */
export const delay = _hootDom.delay;
/** @deprecated use `import { freezeTime } from "@inphms/hoot";` */
export const freezeTime = _hootDom.freezeTime;
/** @deprecated use `import { microTick } from "@inphms/hoot";` */
export const microTick = _hootDom.microTick;
/** @deprecated use `import { runAllTimers } from "@inphms/hoot";` */
export const runAllTimers = _hootDom.runAllTimers;
/** @deprecated use `import { setFrameRate } from "@inphms/hoot";` */
export const setFrameRate = _hootDom.setFrameRate;
/** @deprecated use `import { tick } from "@inphms/hoot";` */
export const tick = _hootDom.tick;
/** @deprecated use `import { unfreezeTime } from "@inphms/hoot";` */
export const unfreezeTime = _hootDom.unfreezeTime;

/** @deprecated use `import { disableAnimations } from "@inphms/hoot";` */
export const disableAnimations = _animation.disableAnimations;
/** @deprecated use `import { enableTransitions } from "@inphms/hoot";` */
export const enableTransitions = _animation.enableTransitions;

/** @deprecated use `import { mockDate } from "@inphms/hoot";` */
export const mockDate = _date.mockDate;
/** @deprecated use `import { mockLocale } from "@inphms/hoot";` */
export const mockLocale = _date.mockLocale;
/** @deprecated use `import { mockTimeZone } from "@inphms/hoot";` */
export const mockTimeZone = _date.mockTimeZone;
/** @deprecated use `import { onTimeZoneChange } from "@inphms/hoot";` */
export const onTimeZoneChange = _date.onTimeZoneChange;

/** @deprecated use `import { makeSeededRandom } from "@inphms/hoot";` */
export const makeSeededRandom = _math.makeSeededRandom;

/** @deprecated use `import { mockPermission } from "@inphms/hoot";` */
export const mockPermission = _navigator.mockPermission;
/** @deprecated use `import { mockSendBeacon } from "@inphms/hoot";` */
export const mockSendBeacon = _navigator.mockSendBeacon;
/** @deprecated use `import { mockUserAgent } from "@inphms/hoot";` */
export const mockUserAgent = _navigator.mockUserAgent;
/** @deprecated use `import { mockVibrate } from "@inphms/hoot";` */
export const mockVibrate = _navigator.mockVibrate;

/** @deprecated use `import { mockFetch } from "@inphms/hoot";` */
export const mockFetch = _network.mockFetch;
/** @deprecated use `import { mockLocation } from "@inphms/hoot";` */
export const mockLocation = _network.mockLocation;
/** @deprecated use `import { mockWebSocket } from "@inphms/hoot";` */
export const mockWebSocket = _network.mockWebSocket;
/** @deprecated use `import { mockWorker } from "@inphms/hoot";` */
export const mockWorker = _network.mockWorker;

/** @deprecated use `import { flushNotifications } from "@inphms/hoot";` */
export const flushNotifications = _notification.flushNotifications;

/** @deprecated use `import { mockMatchMedia } from "@inphms/hoot";` */
export const mockMatchMedia = _window.mockMatchMedia;
/** @deprecated use `import { mockTouch } from "@inphms/hoot";` */
export const mockTouch = _window.mockTouch;
/** @deprecated use `import { watchAddedNodes } from "@inphms/hoot";` */
export const watchAddedNodes = _window.watchAddedNodes;
/** @deprecated use `import { watchKeys } from "@inphms/hoot";` */
export const watchKeys = _window.watchKeys;
/** @deprecated use `import { watchListeners } from "@inphms/hoot";` */
export const watchListeners = _window.watchListeners;
