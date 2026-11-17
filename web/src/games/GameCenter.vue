<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import GameNav from "./GameNav.vue";
import { games, gameHref, type GameSubject } from "./catalog";
import { localProgress, recentGames } from "./game-storage";
import {
  browseKey,
  discoverGames,
  freshBrowseView,
  parseBrowseView,
  pickGame,
} from "./game-discovery";
import { useGameFavorites } from "./use-game-favorites";

const props = defineProps<{ owner: string; revision: number }>();
const { favorites, notice, toggle } = useGameFavorites(() => props.owner);
function readView() {
  try {
    return parseBrowseView(sessionStorage.getItem(browseKey(props.owner)));
  } catch {
    return freshBrowseView();
  }
}
const view = ref(readView());
const library = ref<HTMLElement | null>(null);
const search = ref<HTMLInputElement | null>(null);
const subjects: Array<GameSubject | ""> = [
  "",
  "数学",
  "语文",
  "英语",
  "逻辑",
  "益智",
  "音乐",
  "自然",
  "探险",
  "创作",
  "反应",
  "生活",
];
const progress = computed(() => {
  void props.revision;
  return Object.fromEntries(
    games.map((game) => [game.id, localProgress(game.id, props.owner)]),
  );
});
const playedCount = computed(
  () => Object.values(progress.value).filter(Boolean).length,
);
const filtered = computed(() =>
  discoverGames(view.value, favorites.value, progress.value),
);
const recent = computed(() => {
  void props.revision;
  return recentGames(props.owner)
    .slice(0, 3)
    .map((item) => ({
      ...games.find((game) => game.id === item.id)!,
      ...item,
    }));
});
const narrowed = computed(
  () =>
    view.value.query ||
    view.value.subject ||
    view.value.age ||
    view.value.collection !== "all",
);
let restoring = true;
let scrollFrame = 0;
function remember(event?: Event) {
  const card =
    event?.target instanceof Element
      ? event.target.closest<HTMLElement>("[data-game]")
      : null;
  if (card) {
    view.value.anchor =
      games.find((game) => game.id === card.dataset.game)?.id || "";
    view.value.offset = card.getBoundingClientRect().top;
  } else if (event) view.value.anchor = "";
  try {
    sessionStorage.setItem(browseKey(props.owner), JSON.stringify(view.value));
  } catch {
    /* 禁用会话存储时仍可正常筛选和游戏。 */
  }
}
function trackScroll() {
  if (!restoring) view.value.scroll = window.scrollY;
}
function clearFilters() {
  Object.assign(view.value, {
    query: "",
    subject: "",
    age: "",
    collection: "all",
    anchor: "",
  });
  remember();
}
function surprise() {
  const game = pickGame(filtered.value, progress.value, view.value.lastPick);
  if (!game) return;
  view.value.lastPick = game.id;
  remember();
  location.hash = gameHref(game.id);
}
function findGames() {
  library.value?.scrollIntoView({
    block: "start",
    behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
      ? "instant"
      : "smooth",
  });
  search.value?.focus({ preventScroll: true });
}
onMounted(async () => {
  window.addEventListener("scroll", trackScroll, { passive: true });
  await nextTick();
  scrollFrame = requestAnimationFrame(() => {
    const card = view.value.anchor
      ? library.value?.querySelector<HTMLElement>(
          `[data-game="${view.value.anchor}"]`,
        )
      : null;
    const top = card
      ? window.scrollY +
        card.getBoundingClientRect().top -
        Math.min(view.value.offset, innerHeight - 180)
      : view.value.scroll;
    window.scrollTo(0, top);
    restoring = false;
  });
});
onBeforeUnmount(() => {
  cancelAnimationFrame(scrollFrame);
  window.removeEventListener("scroll", trackScroll);
  remember();
});
</script>

<template>
  <div class="game-center">
    <GameNav />
    <main class="center-content">
      <header class="center-hero">
        <div class="hero-copy">
          <span class="center-kicker">小小探索，每天都有新收获</span>
          <h1>学习游戏中心<span>让好奇心，带你出发。</span></h1>
          <p>
            算一算、画一画、听一听，也能种植和探险。<br
              class="wide-only"
            />选一个感兴趣的游戏，按自己的节奏开始。
          </p>
          <div class="hero-actions">
            <button class="center-primary" @click="findGames">
              挑选喜欢的游戏 <UIcon name="i-lucide-arrow-down" /></button
            ><button
              class="center-secondary"
              :disabled="!filtered.length"
              @click="surprise"
            >
              <UIcon name="i-lucide-shuffle" />帮我选一个
            </button>
          </div>
          <div class="hero-pills">
            <span
              ><UIcon name="i-lucide-sparkles" />{{
                games.length
              }}
              个学习游戏</span
            ><span><UIcon name="i-lucide-heart" />随时开始，随时休息</span>
          </div>
        </div>
        <div class="hero-art" aria-hidden="true">
          <span class="art-ring"></span
          ><span class="art-card art-one"
            ><UIcon name="i-lucide-rocket" class="size-14" /></span
          ><span class="art-card art-two">Aa</span
          ><span class="art-card art-three">3 + 2</span
          ><span class="art-spark">✦</span><span class="art-dot"></span>
        </div>
      </header>
      <section v-if="recent.length" class="center-recent" aria-label="最近玩过">
        <div class="section-heading">
          <h2>接着上次的探索</h2>
          <span>想停就停，回来接着玩</span>
        </div>
        <div class="recent-grid">
          <a
            v-for="game in recent"
            :key="game.id"
            :href="gameHref(game.id)"
            :aria-label="`继续${game.title}`"
            class="recent-card"
            @click="remember"
            ><span :class="['small-game-icon', game.color]"
              ><UIcon :name="game.icon" class="size-6"
            /></span>
            <div>
              <strong>{{ game.title }}</strong>
              <p>{{ game.label }}</p>
            </div>
            <UIcon name="i-lucide-arrow-up-right"
          /></a>
        </div>
      </section>
      <section ref="library" class="center-library" aria-label="选择学习游戏">
        <div class="section-heading library-heading">
          <div>
            <h2>找到喜欢的游戏</h2>
            <p>年龄仅作参考，选择适合自己的玩法与节奏。</p>
          </div>
          <span>{{ filtered.length }} / {{ games.length }} 个游戏</span>
        </div>
        <div class="discovery-tools">
          <div class="game-search">
            <UIcon name="i-lucide-search" /><input
              ref="search"
              v-model="view.query"
              type="search"
              maxlength="80"
              aria-label="搜索游戏"
              placeholder="搜索名称、玩法，比如：推箱子、画画"
              @input="remember"
            /><button
              v-if="view.query"
              aria-label="清空游戏搜索"
              @click="
                view.query = '';
                search?.focus();
                remember();
              "
            >
              <UIcon name="i-lucide-x" />
            </button>
          </div>
          <label class="age-filter"
            ><UIcon name="i-lucide-sliders-horizontal" /><select
              v-model="view.age"
              aria-label="按年龄筛选"
              @change="remember"
            >
              <option value="">所有年龄</option>
              <option
                v-for="value in 9"
                :key="value"
                :value="String(value + 3)"
              >
                {{ value + 3 }} 岁
              </option>
            </select></label
          >
        </div>
        <div class="subject-filters" role="group" aria-label="按学科筛选">
          <button
            v-for="item in subjects"
            :key="item"
            :aria-pressed="view.subject === item"
            :class="{ selected: view.subject === item }"
            @click="
              view.subject = item;
              remember();
            "
          >
            {{ item || "全部游戏" }}
          </button>
        </div>
        <div class="collection-tools">
          <div role="group" aria-label="游戏收藏与游玩记录">
            <button
              :class="{ selected: view.collection === 'all' }"
              :aria-pressed="view.collection === 'all'"
              @click="
                view.collection = 'all';
                remember();
              "
            >
              全部</button
            ><button
              :class="{ selected: view.collection === 'favorites' }"
              :aria-pressed="view.collection === 'favorites'"
              @click="
                view.collection = 'favorites';
                remember();
              "
            >
              <UIcon name="i-lucide-heart" />我的收藏
              <span>{{ favorites.length }}</span></button
            ><button
              :class="{ selected: view.collection === 'played' }"
              :aria-pressed="view.collection === 'played'"
              @click="
                view.collection = 'played';
                remember();
              "
            >
              玩过的 <span>{{ playedCount }}</span>
            </button>
          </div>
          <select v-model="view.order" aria-label="游戏排序" @change="remember">
            <option value="default">默认排序</option>
            <option value="recent">最近玩过优先</option>
          </select>
        </div>
        <div class="discovery-summary" aria-live="polite">
          <p>
            {{ view.query ? `“${view.query}” · ` : "" }}找到
            {{ filtered.length }} 个游戏<span v-if="view.age">
              · 适合 {{ view.age }} 岁</span
            >
          </p>
          <button v-if="narrowed" @click="clearFilters">清除筛选</button>
        </div>
        <p v-if="notice" class="favorite-notice" role="status">{{ notice }}</p>
        <div v-if="filtered.length" class="game-grid">
          <article
            v-for="game in filtered"
            :key="game.id"
            class="game-card"
            :data-game="game.id"
          >
            <div :class="['game-cover', game.color]">
              <a
                class="game-cover-link"
                :href="gameHref(game.id)"
                :aria-label="`打开${game.title}`"
                @click="remember"
                ><span class="cover-label">{{ game.subject }}</span
                ><span class="cover-icon"
                  ><UIcon :name="game.icon" class="size-11" /></span
                ><span class="cover-orbit" aria-hidden="true"></span
                ><span class="cover-duration">{{ game.duration }}</span></a
              ><button
                class="favorite-button"
                :class="{ saved: favorites.includes(game.id) }"
                :aria-pressed="favorites.includes(game.id)"
                :aria-label="`${favorites.includes(game.id) ? '取消收藏' : '收藏'}${game.title}`"
                @click="toggle(game.id)"
              >
                <UIcon name="i-lucide-heart" />
              </button>
            </div>
            <div class="game-card-body">
              <div class="card-title">
                <h3>{{ game.title }}</h3>
                <span>{{ game.ages[0] }}–{{ game.ages[1] }} 岁</span>
              </div>
              <p class="game-description">{{ game.description }}</p>
              <p class="game-skills">{{ game.skills }}</p>
              <div class="game-card-bottom">
                <span>{{ progress[game.id]?.label || "等你来探索" }}</span
                ><a
                  :href="gameHref(game.id)"
                  :aria-label="`${progress[game.id] ? '继续' : '开始'}${game.title}`"
                  @click="remember"
                  >{{ progress[game.id] ? "继续游戏" : "开始游戏"
                  }}<UIcon name="i-lucide-arrow-right"
                /></a>
              </div>
            </div>
          </article>
        </div>
        <div v-else class="game-empty" role="status">
          <UIcon
            :name="
              view.collection === 'favorites'
                ? 'i-lucide-heart'
                : 'i-lucide-compass'
            "
          />
          <h3>
            {{
              view.collection === "favorites" && !favorites.length
                ? "把喜欢的游戏收起来吧"
                : view.collection === "played" && !playedCount
                  ? "从一个小探索开始吧"
                  : "换个条件，再找找看"
            }}
          </h3>
          <p>
            {{
              view.collection === "favorites" && !favorites.length
                ? "点游戏卡片上的爱心，下次就能更快找到它。"
                : view.collection === "played" && !playedCount
                  ? "开始游戏后，这里就会显示玩过的游戏。"
                  : "这个组合暂时没有游戏，换个年龄、学科或搜索词看看。"
            }}
          </p>
          <button class="center-primary" @click="clearFilters">
            查看全部游戏
          </button>
        </div>
      </section>
      <footer class="center-footer">
        <UIcon name="i-lucide-leaf" />玩一会儿，也记得看看远处、休息眼睛。
      </footer>
    </main>
  </div>
</template>

<style scoped src="./game-center.css"></style>
