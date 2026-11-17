import { games, type GameId, type GameInfo, type GameSubject } from "./catalog";

export type GameCollection = "all" | "favorites" | "played";
export type GameOrder = "default" | "recent";
export interface GameBrowseView {
  query: string;
  subject: GameSubject | "";
  age: string;
  collection: GameCollection;
  order: GameOrder;
  scroll: number;
  lastPick: GameId | "";
  anchor: GameId | "";
  offset: number;
}
export type GameProgress = Record<string, { playedAt: number } | null>;
export const favoriteKey = (owner = "") =>
  owner ? `lc_u${owner}_game_favorites_v1` : "lc_game_favorites_v1_guest";
export const browseKey = (owner = "") =>
  owner ? `lc_u${owner}_game_browse_v1` : "lc_game_browse_v1_guest";
export const GAME_FAVORITE_EVENT = "lc:game-favorites";
export const freshBrowseView = (): GameBrowseView => ({
  query: "",
  subject: "",
  age: "",
  collection: "all",
  order: "default",
  scroll: 0,
  lastPick: "",
  anchor: "",
  offset: 0,
});

export function parseFavorites(raw: string | null): GameId[] {
  try {
    const value: unknown = JSON.parse(raw || "null");
    if (!Array.isArray(value)) return [];
    return games
      .filter((game) => value.includes(game.id))
      .map((game) => game.id);
  } catch {
    return [];
  }
}

export function parseBrowseView(raw: string | null): GameBrowseView {
  const result = freshBrowseView();
  try {
    const value = JSON.parse(raw || "null") as Partial<GameBrowseView> | null;
    if (!value || typeof value !== "object") return result;
    if (typeof value.query === "string")
      result.query = value.query.slice(0, 80);
    if (games.some((game) => game.subject === value.subject))
      result.subject = value.subject!;
    if (typeof value.age === "string" && /^(?:[4-9]|1[0-2])$/.test(value.age))
      result.age = value.age;
    if (value.collection === "favorites" || value.collection === "played")
      result.collection = value.collection;
    if (value.order === "recent") result.order = value.order;
    if (typeof value.scroll === "number" && Number.isFinite(value.scroll))
      result.scroll = Math.max(0, Math.min(100000, value.scroll));
    if (games.some((game) => game.id === value.lastPick))
      result.lastPick = value.lastPick!;
    if (games.some((game) => game.id === value.anchor))
      result.anchor = value.anchor!;
    if (typeof value.offset === "number" && Number.isFinite(value.offset))
      result.offset = Math.max(-2000, Math.min(2000, value.offset));
  } catch {
    /* 失效的筛选记录不影响进入游戏。 */
  }
  return result;
}

const normalized = (value: string) =>
  value.normalize("NFKC").toLocaleLowerCase().trim();
const aliases: Partial<Record<GameId, string>> = {
  "creative-studio": "画画 绘画 涂鸦",
  "little-farm": "种菜 种地 养动物",
  "animal-catch": "接水果 接食物",
  "rhythm-band": "打鼓 编曲 演奏",
};
export function discoverGames(
  view: GameBrowseView,
  favorites: GameId[],
  progress: GameProgress,
): GameInfo[] {
  const words = normalized(view.query).split(/\s+/).filter(Boolean);
  const result = games.filter((game) => {
    if (view.subject && game.subject !== view.subject) return false;
    if (
      view.age &&
      (game.ages[0] > Number(view.age) || game.ages[1] < Number(view.age))
    )
      return false;
    if (view.collection === "favorites" && !favorites.includes(game.id))
      return false;
    if (view.collection === "played" && !progress[game.id]) return false;
    const text = normalized(
      `${game.title} ${game.subject} ${game.skills} ${game.description} ${game.id.replace(/-/g, " ")} ${aliases[game.id] || ""}`,
    );
    return words.every((word) => text.includes(word));
  });
  if (view.order === "recent")
    result.sort(
      (a, b) =>
        (progress[b.id]?.playedAt || 0) - (progress[a.id]?.playedAt || 0),
    );
  return result;
}

/** 优先尝试尚未玩过的游戏，并避免连续选中上一款。 */
export function pickGame(
  options: GameInfo[],
  progress: GameProgress,
  previous: GameId | "",
  random = Math.random,
): GameInfo | undefined {
  const available = options.filter((game) => game.id !== previous);
  const candidates = available.length ? available : options;
  const unseen = candidates.filter((game) => !progress[game.id]);
  const pool = unseen.length ? unseen : candidates;
  return pool[
    Math.min(pool.length - 1, Math.max(0, Math.floor(random() * pool.length)))
  ];
}
