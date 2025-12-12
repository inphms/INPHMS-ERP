# Javascript
This should be the boot sequence of javascript first loaded.

## 1. Services

### 1.1 bus.parameters
    File: @bus/bus_parameters_service.js
    Purpose: Returns server with `window.origin`

### 1.2 legacy_multi_tab
    File: @bus/legacy_multi_tab_service.js
    Purpose: creating localstorage services that manages all shared tabs.

Methods:

    generateLocalStorageKey(baseKey)
    - returns `prefix` + baseKey

    getItemFromStorage(k, defaultValue) 
    - get item from localstorage

    setItemInStorage(k, v) 
    - set item in localstorage

    onStorage({key, newValue}) 
    - listener method that is called when 'storage' is called on browser. then use `bus.trigger('shared_value_updated', {key, newValue})` to trigger the event.

return:
```json
    {bus, generateLocalStorageKey,
    getItemFromStorage, setItemInStorage,
    getSharedValue, setSharedValue, removeSharedValue}
```


### 1.3 multi_tab_services, multi_tab
    file: @bus/multi_tab_service.js
    purpose: select which is the best multi tab services by checking `browser.SharedWorker` will fallback to multi_tab_fallback_service.js


### 1.4 multi_tab_shared_worker_service
    file: @bus/multi_tab_shared_worker_service.js

methods:

messageHandler(messageEv) 
- type has to starts with, `ELECTION:` and we switch by type.
    1. ELECTION:IS_MASTER_RESPONSE -> resolve(data.asnwer)
    2. ELECTION:HEARTBEAT_REQUEST -> worker_service.send("ELECTION:HEARTBEAT")
    3. ELECTION:ASSIGN_MASTER -> state = 'MASTER' and bus.trigger('become_main_tab")
    4. ELECTION:UNASSIGN_MASTER -> state = 'REGISTERED' and bus.trigger('no_longer_main_tab')
- startWorker() 
    - call:
        - worker_service.ensureWorkerStarted();
        - worker_service.registerHandler(messageHandler);
        - worker_service.send('ELECTION:REGISTER');
        - change state to 'REGISTERED'
- unregister() 
    - call:
        - worker_service.send("ELECTION:UNREGISTER");
        - state = 'UNREGISTERED'

depends: `worker_service`

return:
```json
    {bus, isOnMainTab, unregister}
```

### 1.5 multi_tab_fallback_service
    file: @bus/multi_tab_fallback_service.js
    purpose: uses pooling heartbeat to startElection and select maintab


### 1.6 bus.outdated_page_watcher
    file: @bus/outdated_page_watcher_service.js
    