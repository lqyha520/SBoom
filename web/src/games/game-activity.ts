export const GAME_PAUSE_EVENT = "lc:game-pause";

/** 打开帮助或离开游戏操作区时，通知有连续动画、声音的游戏暂停。 */
export function pauseGameActivity() {
  window.dispatchEvent(new Event(GAME_PAUSE_EVENT));
}
import { nextTick } from "vue";

export async function revealGameHint() {
  await nextTick();
  if (!matchMedia("(max-width: 760px)").matches) return;
  const element = document.querySelector<HTMLElement>(
    ".hint-card, .explore-feedback",
  );
  if (!element) return;
  const bounds = element.getBoundingClientRect();
  if (bounds.top < 72 || bounds.bottom > innerHeight - 90)
    element.scrollIntoView({ block: "center", behavior: "instant" });
}
