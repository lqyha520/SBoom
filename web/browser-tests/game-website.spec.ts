import { expect, test } from "@playwright/test";
import { games } from "../src/games/catalog";

test("搜索、年龄和收藏组合可用，收藏在游戏页与列表间同步并保留筛选", async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#/games");
  await page.getByRole("searchbox", { name: "搜索游戏" }).fill("画画");
  await expect(page.locator(".game-card")).toHaveCount(1);
  await page.getByRole("button", { name: "收藏创意画室", exact: true }).click();
  await page.getByRole("button", { name: "清空游戏搜索" }).click();
  await page.getByRole("searchbox", { name: "搜索游戏" }).fill("推箱子");
  await page.getByRole("button", { name: "收藏推箱子", exact: true }).click();
  await page.getByRole("button", { name: "清空游戏搜索" }).click();
  await page.getByRole("button", { name: "我的收藏 2", exact: true }).click();
  await expect(page.locator(".game-card")).toHaveCount(2);
  await page.getByRole("combobox", { name: "按年龄筛选" }).selectOption("4");
  await expect(page.locator(".game-card")).toHaveCount(1);
  await page.reload();
  await expect(page.getByRole("combobox", { name: "按年龄筛选" })).toHaveValue(
    "4",
  );
  await page.getByRole("link", { name: "开始创意画室", exact: true }).click();
  await expect(page).toHaveTitle("创意画室 · 学习游戏中心");
  await page
    .getByRole("complementary", { name: "游戏快捷操作" })
    .getByRole("button", { name: "已收藏", exact: true })
    .click();
  await page.getByRole("link", { name: "返回游戏列表", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "我的收藏 1", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".game-card")).toHaveCount(0);
  await page.getByRole("button", { name: "查看全部游戏", exact: true }).click();
  await expect(page.locator(".game-card")).toHaveCount(32);
  await page.screenshot({
    path: info.outputPath("website-mobile.png"),
    fullPage: true,
  });
});

test("从长列表打开游戏时回到页首，返回后仍定位原卡片而且保留筛选", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#/games");
  await page.getByRole("button", { name: "益智", exact: true }).click();
  await page.getByRole("combobox", { name: "按年龄筛选" }).selectOption("8");
  const card = page.locator('[data-game="mirror-draw"]');
  await card.scrollIntoViewIfNeeded();
  const before = await card.evaluate(
    (element) => element.getBoundingClientRect().top,
  );
  await card.getByRole("link", { name: "开始镜面对称", exact: true }).click();
  await expect(page.getByRole("heading", { name: "镜面对称." })).toBeVisible();
  await expect.poll(() => page.evaluate(() => scrollY)).toBe(0);
  await page.getByRole("link", { name: "返回游戏列表", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "益智", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("combobox", { name: "按年龄筛选" })).toHaveValue(
    "8",
  );
  await expect
    .poll(async () =>
      Math.abs(
        (await card.evaluate(
          (element) => element.getBoundingClientRect().top,
        )) - before,
      ),
    )
    .toBeLessThan(10);
});

test("帮我选一个遵循筛选并避开上一款；专注模式可以进出", async ({
  page,
}, info) => {
  await page.goto("/#/games");
  await page.getByRole("button", { name: "英语", exact: true }).click();
  await page.getByRole("button", { name: "帮我选一个", exact: true }).click();
  await expect(page.locator("h1")).toBeVisible();
  const first = page.url();
  expect(first).toMatch(/games\/word-(market|spell)$/);
  await page.getByRole("button", { name: "专注游戏", exact: true }).click();
  await expect(page.locator(".games-nav")).toBeHidden();
  await expect(
    page.getByRole("button", { name: "退出专注", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: info.outputPath("focused-desktop.png"),
    fullPage: true,
  });
  await page.keyboard.press("Escape");
  await expect(page.locator(".games-nav")).toBeVisible();
  await page.getByRole("link", { name: "返回游戏列表", exact: true }).click();
  await page.getByRole("button", { name: "帮我选一个", exact: true }).click();
  await expect(page.locator("h1")).toBeVisible();
  expect(page.url()).not.toBe(first);
});

test("手机提示在棋盘上方，常用按钮可见且反馈不会藏在屏幕之外", async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#/games/sokoban");
  await expect(page.getByRole("heading", { name: "推箱子." })).toBeVisible();
  const tools = await page.locator(".board-tools").boundingBox();
  const stage = await page.locator(".puzzle-stage").boundingBox();
  expect(tools!.y).toBeLessThan(stage!.y);
  const button = page.getByRole("button", { name: "给我提示", exact: true });
  expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await button.click();
  await expect(page.getByRole("status", { name: "游戏提示" })).toBeInViewport();
  await page.screenshot({
    path: info.outputPath("hint-mobile.png"),
    fullPage: true,
  });
});

test("打开帮助和切出窗口会暂停接接乐，食物保留在原位置再继续", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#/games/animal-catch");
  await page.getByRole("button", { name: "开始接食物", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "暂停游戏", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "怎么玩", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  const position = await page.locator('[data-drop="0"]').getAttribute("style");
  await page.waitForTimeout(250);
  expect(await page.locator('[data-drop="0"]').getAttribute("style")).toBe(
    position,
  );
  await page.getByRole("button", { name: "知道啦", exact: true }).click();
  await page.getByRole("button", { name: "继续接食物", exact: true }).click();
  await page.evaluate(() => window.dispatchEvent(new Event("blur")));
  await expect(
    page.getByRole("button", { name: "继续接食物", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "暂停游戏", exact: true }),
  ).toHaveCount(0);
});

test("音乐等待浏览器解锁期间打开帮助，异步完成后也不能重新启动", async ({
  page,
}) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, "AudioContext", {
      value: class {
        state = "suspended";
        async resume() {
          await new Promise((resolve) => setTimeout(resolve, 350));
          this.state = "running";
        }
        async close() {
          this.state = "closed";
        }
      },
    });
  });
  await page.goto("/#/games/rhythm-band");
  await page.getByRole("button", { name: "听一遍示范", exact: true }).click();
  await page.getByRole("button", { name: "怎么玩", exact: true }).click();
  await page.getByRole("button", { name: "知道啦", exact: true }).click();
  await page.waitForTimeout(450);
  await expect(
    page.getByRole("button", { name: "停止演奏", exact: true }),
  ).toHaveCount(0);
  await expect(page.locator("[data-playing-note]")).toHaveCount(0);
});

test("损坏的偏好和未知链接可恢复，收藏写入失败也能继续游戏", async ({
  page,
}) => {
  await page.addInitScript(() => {
    localStorage.setItem("lc_game_favorites_v1_guest", "{");
    sessionStorage.setItem("lc_game_browse_v1_guest", "{");
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = function (key, value) {
      if (key.includes("favorites")) throw new Error("quota");
      original.call(this, key, value);
    };
  });
  await page.goto("/#/games/missing");
  await expect(page.getByText("这个游戏地址暂时无法使用")).toBeVisible();
  await page.getByRole("searchbox", { name: "搜索游戏" }).fill("推箱子");
  await page.getByRole("button", { name: "收藏推箱子", exact: true }).click();
  await expect(
    page.getByText("浏览器暂时无法保存收藏，本次浏览仍可使用。"),
  ).toBeVisible();
  await page.getByRole("link", { name: "开始推箱子", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "已收藏", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "返回游戏列表", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "取消收藏推箱子", exact: true }),
  ).toBeVisible();
});

test("32 款游戏手机端均能打开、使用快捷操作，图标无外部依赖", async ({
  page,
}, info) => {
  test.setTimeout(120000);
  const errors: string[] = [],
    external: string[] = [],
    api: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    if (request.url().includes("/api/")) api.push(request.url());
  });
  await page.route(
    /https:\/\/(?:api\.iconify\.design|api\.simplesvg\.com|api\.unisvg\.com)\//,
    (route) => {
      external.push(route.request().url());
      return route.abort();
    },
  );
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    for (const game of games) {
      await page.goto("/#/games/" + game.id);
      await expect(page.locator("h1")).toBeVisible();
      await expect(page).toHaveTitle(game.title + " · 学习游戏中心");
      await expect(
        page.getByRole("link", { name: "返回游戏列表", exact: true }),
      ).toBeInViewport();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    }
  }
  await page.screenshot({
    path: info.outputPath("games-small-screen.png"),
    fullPage: true,
  });
  expect(errors).toEqual([]);
  expect(external).toEqual([]);
  expect(api).toEqual([]);
});
