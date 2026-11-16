import {
  onBeforeUnmount,
  onMounted,
  ref,
  toValue,
  watch,
  type MaybeRefOrGetter,
} from "vue";
import type { GameId } from "./catalog";
import {
  favoriteKey,
  GAME_FAVORITE_EVENT,
  parseFavorites,
} from "./game-discovery";
const temporaryFavorites = new Map<string, GameId[]>();
const temporaryNotice = "浏览器暂时无法保存收藏，本次浏览仍可使用。";

export function useGameFavorites(owner: MaybeRefOrGetter<string>) {
  const favorites = ref<GameId[]>([]);
  const notice = ref("");
  function read() {
    const temporary = temporaryFavorites.get(toValue(owner));
    if (temporary) {
      favorites.value = [...temporary];
      notice.value = temporaryNotice;
      return;
    }
    try {
      favorites.value = parseFavorites(
        localStorage.getItem(favoriteKey(toValue(owner))),
      );
    } catch {
      favorites.value = [];
    }
  }
  function toggle(id: GameId) {
    favorites.value = favorites.value.includes(id)
      ? favorites.value.filter((value) => value !== id)
      : [...favorites.value, id];
    notice.value = "";
    try {
      localStorage.setItem(
        favoriteKey(toValue(owner)),
        JSON.stringify(favorites.value),
      );
      temporaryFavorites.delete(toValue(owner));
    } catch {
      notice.value = temporaryNotice;
      temporaryFavorites.set(toValue(owner), [...favorites.value]);
    }
    window.dispatchEvent(
      new CustomEvent(GAME_FAVORITE_EVENT, {
        detail: {
          owner: toValue(owner),
          ids: [...favorites.value],
          temporary: !!notice.value,
        },
      }),
    );
  }
  function changed(event: Event) {
    const detail = (
      event as CustomEvent<{
        owner: string;
        ids: GameId[];
        temporary?: boolean;
      }>
    ).detail;
    if (detail?.owner === toValue(owner)) {
      favorites.value = parseFavorites(JSON.stringify(detail.ids));
      notice.value = detail.temporary ? temporaryNotice : "";
    }
  }
  function storage(event: StorageEvent) {
    if (event.key === null || event.key === favoriteKey(toValue(owner))) {
      temporaryFavorites.delete(toValue(owner));
      notice.value = "";
      read();
    }
  }
  watch(
    () => toValue(owner),
    () => {
      notice.value = "";
      read();
    },
    { immediate: true },
  );
  onMounted(() => {
    window.addEventListener(GAME_FAVORITE_EVENT, changed);
    window.addEventListener("storage", storage);
  });
  onBeforeUnmount(() => {
    window.removeEventListener(GAME_FAVORITE_EVENT, changed);
    window.removeEventListener("storage", storage);
  });
  return { favorites, notice, toggle };
}
