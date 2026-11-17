import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { defineComponent, nextTick, ref } from "vue";
import { mount } from "@vue/test-utils";
import { games, gameFromHash } from "../games/catalog";
import {
  discoverGames,
  favoriteKey,
  freshBrowseView,
  parseBrowseView,
  parseFavorites,
  pickGame,
} from "../games/game-discovery";
import { useGameFavorites } from "../games/use-game-favorites";

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

it("组合搜索名称、常用玩法和多个词，年龄与收藏条件同时生效", () => {
  const view = {
    ...freshBrowseView(),
    query: "画画",
    age: "4",
    collection: "favorites" as const,
  };
  expect(
    discoverGames(view, ["creative-studio", "sokoban"], {}).map(
      (game) => game.id,
    ),
  ).toEqual(["creative-studio"]);
  expect(
    discoverGames({ ...view, query: "画画 数学" }, ["creative-studio"], {}),
  ).toEqual([]);
  expect(
    discoverGames(
      { ...freshBrowseView(), query: "ＷＯＲＤ ＳＰＥＬＬ" },
      [],
      {},
    ).map((game) => game.id),
  ).toEqual(["word-spell"]);
  expect(
    discoverGames({ ...freshBrowseView(), query: "种菜" }, [], {}).map(
      (game) => game.id,
    ),
  ).toEqual(["little-farm"]);
});

it("最近玩过排序稳定，未玩游戏不丢失；游玩记录只显示有存档的游戏", () => {
  const progress = {
    sokoban: { playedAt: 20 },
    "rocket-math": { playedAt: 50 },
  };
  const ordered = discoverGames(
    { ...freshBrowseView(), order: "recent" },
    [],
    progress,
  );
  expect(ordered).toHaveLength(32);
  expect(ordered.slice(0, 2).map((game) => game.id)).toEqual([
    "rocket-math",
    "sokoban",
  ]);
  expect(ordered.slice(2)).toEqual(
    games.filter((game) => !(game.id in progress)),
  );
  expect(
    discoverGames(
      { ...freshBrowseView(), collection: "played" },
      [],
      progress,
    ).map((game) => game.id),
  ).toEqual(["rocket-math", "sokoban"]);
});

it("帮我选一个在当前筛选中优先尝试新游戏，只有一个结果和空结果也能处理", () => {
  const options = games.filter((game) => game.subject === "英语");
  expect(
    pickGame(options, { "word-spell": { playedAt: 1 } }, "", () => 0)?.id,
  ).toBe("word-market");
  expect(pickGame(options, {}, "word-market", () => 1)?.id).toBe("word-spell");
  expect(pickGame([options[0]], {}, options[0].id)?.id).toBe(options[0].id);
  expect(pickGame([], {}, "")).toBeUndefined();
});

it("旧的或损坏的收藏与筛选不会生成无效游戏链接", () => {
  expect(parseFavorites('["sokoban","removed","sokoban",null]')).toEqual([
    "sokoban",
  ]);
  expect(parseFavorites("{")).toEqual([]);
  const value = parseBrowseView(
    JSON.stringify({
      query: "x".repeat(300),
      age: "99",
      subject: "removed",
      collection: "broken",
      order: "broken",
      scroll: -50,
      anchor: "removed",
      offset: 99999,
    }),
  );
  expect(value).toEqual({
    ...freshBrowseView(),
    query: "x".repeat(80),
    offset: 2000,
  });
  expect(parseBrowseView("{")).toEqual(freshBrowseView());
  expect(gameFromHash("#/games/sokoban/?from=share")?.id).toBe("sokoban");
  expect(gameFromHash("#/games/missing")).toBeUndefined();
});

it("收藏同步到当前页面，按账号隔离，并响应其他标签页的收藏变化", async () => {
  const owner = ref("discovery-one");
  let state!: ReturnType<typeof useGameFavorites>;
  const wrapper = mount(
    defineComponent({
      setup() {
        state = useGameFavorites(owner);
        return () => null;
      },
    }),
  );
  state.toggle("sokoban");
  expect(JSON.parse(localStorage.getItem(favoriteKey(owner.value))!)).toEqual([
    "sokoban",
  ]);
  owner.value = "discovery-two";
  await nextTick();
  expect(state.favorites.value).toEqual([]);
  localStorage.setItem(favoriteKey(owner.value), '["creative-studio"]');
  window.dispatchEvent(
    new StorageEvent("storage", { key: favoriteKey(owner.value) }),
  );
  expect(state.favorites.value).toEqual(["creative-studio"]);
  owner.value = "discovery-one";
  await nextTick();
  expect(state.favorites.value).toEqual(["sokoban"]);
  wrapper.unmount();
});

it("收藏写入失败时保留本次浏览的选择，返回页面后仍可使用并明确提示", () => {
  let state!: ReturnType<typeof useGameFavorites>;
  const component = defineComponent({
    setup() {
      state = useGameFavorites("discovery-storage-blocked");
      return () => null;
    },
  });
  const first = mount(component);
  vi.spyOn(localStorage, "setItem").mockImplementation(() => {
    throw new Error("quota");
  });
  state.toggle("sokoban");
  expect(state.notice.value).toContain("本次浏览仍可使用");
  first.unmount();
  const second = mount(component);
  expect(state.favorites.value).toEqual(["sokoban"]);
  expect(state.notice.value).toContain("暂时无法保存收藏");
  second.unmount();
});
