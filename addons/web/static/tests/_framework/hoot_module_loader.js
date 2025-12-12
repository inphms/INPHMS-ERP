// @inphms-module ignore
// ! WARNING: this module must be loaded after `module_loader` but cannot have dependencies !

(function (inphms) {
    "use strict";

    if (inphms.define.name.endsWith("(hoot)")) {
        return;
    }

    const name = `${inphms.define.name} (hoot)`;
    inphms.define = {
        [name](name, dependencies, factory) {
            return inphms.loader.define(name, dependencies, factory, !name.endsWith(".hoot"));
        },
    }[name];
})(globalThis.inphms);
