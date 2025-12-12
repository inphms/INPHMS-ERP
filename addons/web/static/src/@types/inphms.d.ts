interface InphmsModuleErrors {
    cycle?: string | null;
    failed?: Set<string>;
    missing?: Set<string>;
    unloaded?: Set<string>;
}

interface InphmsModuleFactory {
    deps: string[];
    fn: InphmsModuleFactoryFn;
    ignoreMissingDeps: boolean;
}

class InphmsModuleLoader {
    bus: EventTarget;
    checkErrorProm: Promise<void> | null;
    debug: boolean;
    /**
     * Mapping [name => factory]
     */
    factories: Map<string, InphmsModuleFactory>;
    /**
     * Names of failed modules
     */
    failed: Set<string>;
    /**
     * Names of modules waiting to be started
     */
    jobs: Set<string>;
    /**
     * Mapping [name => module]
     */
    modules: Map<string, InphmsModule>;

    constructor(root?: HTMLElement);

    addJob: (name: string) => void;

    define: (
        name: string,
        deps: string[],
        factory: InphmsModuleFactoryFn,
        lazy?: boolean
    ) => InphmsModule;

    findErrors: (jobs?: Iterable<string>) => InphmsModuleErrors;

    findJob: () => string | null;

    reportErrors: (errors: InphmsModuleErrors) => Promise<void>;

    sortFactories: () => void;

    startModule: (name: string) => InphmsModule;

    startModules: () => void;
}

type InphmsModule = Record<string, any>;

type InphmsModuleFactoryFn = (require: (dependency: string) => InphmsModule) => InphmsModule;

declare const inphms: {
    csrf_token: string;
    debug: string;
    define: InphmsModuleLoader["define"];
    loader: InphmsModuleLoader;
};
