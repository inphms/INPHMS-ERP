import { beforeEach, describe, expect, test } from "@inphms/hoot";
import { getService, makeMockEnv } from "@web/../tests/web_test_helpers";

describe.current.tags("headless");

let titleService;

beforeEach(async () => {
    await makeMockEnv();
    titleService = getService("title");
});

test("simple title", () => {
    titleService.setParts({ one: "MyInphms" });
    expect(titleService.current).toBe("MyInphms");
});

test("add title part", () => {
    titleService.setParts({ one: "MyInphms", two: null });
    expect(titleService.current).toBe("MyInphms");
    titleService.setParts({ three: "Import" });
    expect(titleService.current).toBe("MyInphms - Import");
});

test("modify title part", () => {
    titleService.setParts({ one: "MyInphms" });
    expect(titleService.current).toBe("MyInphms");
    titleService.setParts({ one: "Zopenerp" });
    expect(titleService.current).toBe("Zopenerp");
});

test("delete title part", () => {
    titleService.setParts({ one: "MyInphms" });
    expect(titleService.current).toBe("MyInphms");
    titleService.setParts({ one: null });
    expect(titleService.current).toBe("Inphms");
});

test("all at once", () => {
    titleService.setParts({ one: "MyInphms", two: "Import" });
    expect(titleService.current).toBe("MyInphms - Import");
    titleService.setParts({ one: "Zopenerp", two: null, three: "Sauron" });
    expect(titleService.current).toBe("Zopenerp - Sauron");
});

test("get title parts", () => {
    expect(titleService.current).toBe("");
    titleService.setParts({ one: "MyInphms", two: "Import" });
    expect(titleService.current).toBe("MyInphms - Import");
    const parts = titleService.getParts();
    expect(parts).toEqual({ one: "MyInphms", two: "Import" });
    parts.action = "Export";
    expect(titleService.current).toBe("MyInphms - Import"); // parts is a copy!
});
