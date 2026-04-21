<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from "vue";
import UiCard from "../../components/UiCard.vue";
import {
  createContentJob,
  getContentGenerationContext,
  getLatestContentDrafts,
  listContentDrafts,
  streamContentJob
} from "../../api/counselor";

const loading = ref(true);
const ctx = ref<any>(null);
const ctxOpen = ref(false);

const articleLoading = ref(false);
const videoLoading = ref(false);
const articleError = ref("");
const videoError = ref("");

const articleText = ref("");
const videoScript = ref("");
const videoScriptByMode = ref<Record<"video" | "video_prompt", string>>({
  video: "",
  video_prompt: ""
});
const videoMode = ref<"video" | "video_prompt">("video");

const articleHistoryOpen = ref(false);
const articleHistory = ref<any[]>([]);
const videoHistoryOpen = ref(false);
const videoHistory = ref<any[]>([]);

const articleJobId = ref<number | null>(null);
const videoJobId = ref<number | null>(null);
const videoJobIdByMode = ref<Record<"video" | "video_prompt", number | null>>({
  video: null,
  video_prompt: null
});

const LS_ARTICLE = "content_job_article";
const LS_VIDEO = "content_job_video";
const LS_VIDEO_PROMPT = "content_job_video_prompt";

onMounted(async () => {
  loading.value = true;
  try {
    ctx.value = await getContentGenerationContext();
    const latest = await getLatestContentDrafts();
    if (latest?.article?.text) articleText.value = String(latest.article.text);
    if (latest?.video?.text) videoScriptByMode.value.video = String(latest.video.text);
    if (latest?.video_prompt?.text) videoScriptByMode.value.video_prompt = String(latest.video_prompt.text);
    videoScript.value = videoScriptByMode.value[videoMode.value] || "";

    // Resume unfinished jobs if present.
    const savedArticle = Number(localStorage.getItem(LS_ARTICLE) || "");
    if (savedArticle) {
      articleJobId.value = savedArticle;
      void resumeJob("article");
    }
    const savedVideo = Number(localStorage.getItem(LS_VIDEO) || "");
    const savedPrompt = Number(localStorage.getItem(LS_VIDEO_PROMPT) || "");
    if (savedVideo) videoJobIdByMode.value.video = savedVideo;
    if (savedPrompt) videoJobIdByMode.value.video_prompt = savedPrompt;
    videoJobId.value = videoJobIdByMode.value[videoMode.value];
    if (videoJobId.value) void resumeJob(videoMode.value);
  } finally {
    loading.value = false;
  }

  document.addEventListener("visibilitychange", onVisibilityChange);
});

watch(videoMode, (nextMode) => {
  videoJobId.value = videoJobIdByMode.value[nextMode];
  videoScript.value = videoScriptByMode.value[nextMode] || "";
  if (videoHistoryOpen.value) void loadVideoHistory();
  if (videoJobId.value) void resumeJob(nextMode);
});

onUnmounted(() => {
  document.removeEventListener("visibilitychange", onVisibilityChange);
});

function onVisibilityChange() {
  if (document.visibilityState === "visible") {
    if (articleJobId.value) void resumeJob("article");
    videoJobId.value = videoJobIdByMode.value[videoMode.value];
    if (videoJobId.value) void resumeJob(videoMode.value);
  }
}

async function resumeJob(kind: "article" | "video" | "video_prompt") {
  if (kind === "article") {
    if (!articleJobId.value) return;
    articleLoading.value = true;
    try {
      const start = articleText.value.length;
      await streamContentJob(
        articleJobId.value,
        start,
        (chunk) => {
          articleText.value += chunk;
        },
        (status) => {
          articleLoading.value = false;
          if (status === "done" || status === "error" || status === "cancelled") {
            localStorage.removeItem(LS_ARTICLE);
            articleJobId.value = null;
          }
        }
      );
    } catch {
      articleLoading.value = false;
    }
    return;
  }

  const targetJobId = videoJobIdByMode.value[kind];
  if (!targetJobId) return;
  videoLoading.value = true;
  try {
    const start = (videoScriptByMode.value[kind] || "").length;
    await streamContentJob(
      targetJobId,
      start,
      (chunk) => {
        videoScriptByMode.value[kind] = (videoScriptByMode.value[kind] || "") + chunk;
        if (videoMode.value === kind) {
          videoScript.value = videoScriptByMode.value[kind];
        }
      },
      (status) => {
        videoLoading.value = false;
        if (status === "done" || status === "error" || status === "cancelled") {
          localStorage.removeItem(kind === "video_prompt" ? LS_VIDEO_PROMPT : LS_VIDEO);
          videoJobIdByMode.value[kind] = null;
          if (videoMode.value === kind) {
            videoJobId.value = null;
          }
        }
      }
    );
  } catch {
    videoLoading.value = false;
  }
}

async function generateArticle() {
  articleLoading.value = true;
  articleError.value = "";
  articleText.value = "";
  try {
    const job = await createContentJob("article");
    articleJobId.value = Number(job?.id ?? null);
    if (articleJobId.value) localStorage.setItem(LS_ARTICLE, String(articleJobId.value));
    await resumeJob("article");
  } finally {
    articleLoading.value = false;
  }
}

async function generateVideo() {
  videoLoading.value = true;
  videoError.value = "";
  try {
    const kind = videoMode.value;
    videoScriptByMode.value[kind] = "";
    videoScript.value = "";
    const job = await createContentJob(kind);
    videoJobIdByMode.value[kind] = Number(job?.id ?? null);
    videoJobId.value = videoJobIdByMode.value[kind];
    const key = kind === "video_prompt" ? LS_VIDEO_PROMPT : LS_VIDEO;
    if (videoJobIdByMode.value[kind]) localStorage.setItem(key, String(videoJobIdByMode.value[kind]));
    await resumeJob(kind);
  } finally {
    videoLoading.value = false;
  }
}

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // ignore
  }
}

function applyHistory(item: any) {
  const kind = String(item?.kind || "");
  if (kind === "article") articleText.value = String(item?.text || "");
  if (kind === "video" || kind === "video_prompt") {
    const targetKind = kind as "video" | "video_prompt";
    videoScriptByMode.value[targetKind] = String(item?.text || "");
    videoMode.value = targetKind;
    videoScript.value = videoScriptByMode.value[targetKind];
  }

  // If this history item is still generating, re-bind job id so we can resume streaming.
  const jobStatus = String(item?.job_status || "");
  const jobId = Number(item?.job_id ?? 0);
  if (jobStatus === "running" && jobId) {
    if (kind === "article") {
      articleJobId.value = jobId;
      localStorage.setItem(LS_ARTICLE, String(jobId));
      void resumeJob("article");
    }
    if (kind === "video" || kind === "video_prompt") {
      const targetKind = kind as "video" | "video_prompt";
      videoJobIdByMode.value[targetKind] = jobId;
      videoJobId.value = jobId;
      localStorage.setItem(targetKind === "video_prompt" ? LS_VIDEO_PROMPT : LS_VIDEO, String(jobId));
      void resumeJob(targetKind);
    }
  }
}

async function loadArticleHistory() {
  articleHistory.value = await listContentDrafts({ kind: "article", limit: 30, offset: 0 });
}

async function loadVideoHistory() {
  videoHistory.value = await listContentDrafts({ kind: videoMode.value, limit: 30, offset: 0 });
}
</script>

<template>
  <div class="page">
    <UiCard title="长文草稿（公众号 / 班会）">
      <p class="lead">结合近期热点与群体画像，AI 流式生成可编辑的长文草稿。</p>
      <div v-if="loading" class="hint">加载中…</div>
      <div v-else>
        <div class="bar">
          <button type="button" class="btn" :disabled="articleLoading" @click="generateArticle">
            {{ articleLoading ? "生成中…" : "生成长文草稿" }}
          </button>
          <button type="button" class="btn ghost" :disabled="!articleText" @click="copyText(articleText)">
            复制
          </button>
          <button type="button" class="btn ghost" @click="ctxOpen = !ctxOpen">
            {{ ctxOpen ? "隐藏生成上下文" : "查看生成上下文" }}
          </button>
          <button type="button" class="btn ghost" @click="articleHistoryOpen = !articleHistoryOpen; if (articleHistoryOpen) loadArticleHistory();">
            {{ articleHistoryOpen ? "隐藏历史" : "历史草稿" }}
          </button>
        </div>
        <p v-if="articleError" class="warn">模型调用异常，已启用兜底生成：{{ articleError }}</p>
        <textarea v-model="articleText" class="ta" rows="18" spellcheck="false" />
        <pre v-if="ctxOpen" class="ctx">{{ JSON.stringify(ctx, null, 2) }}</pre>
        <div v-if="articleHistoryOpen" class="hist">
          <ul class="hist-list">
            <li v-for="h in articleHistory" :key="h.id" class="hist-item">
              <button type="button" class="hist-btn" @click="applyHistory(h)">
                <span class="k">article</span>
                <span class="t">{{ h.display_title || h.title || "（无标题）" }}</span>
                <span class="d">{{ h.display_date || "" }}</span>
              </button>
            </li>
          </ul>
        </div>
      </div>
    </UiCard>

    <UiCard title="短视频内容草稿">
      <div class="bar">
        <label class="sel-lbl">模式</label>
        <select v-model="videoMode" class="sel">
          <option value="video">脚本与分镜</option>
          <option value="video_prompt">文生视频提示词</option>
        </select>
        <button type="button" class="btn" :disabled="videoLoading" @click="generateVideo">
          {{ videoLoading ? "生成中…" : "生成视频草稿" }}
        </button>
        <button type="button" class="btn ghost" :disabled="!videoScript" @click="copyText(videoScript)">复制</button>
        <button type="button" class="btn ghost" @click="videoHistoryOpen = !videoHistoryOpen; if (videoHistoryOpen) loadVideoHistory();">
          {{ videoHistoryOpen ? "隐藏历史" : "历史草稿" }}
        </button>
      </div>
      <p v-if="videoError" class="warn">模型调用异常，已启用兜底生成：{{ videoError }}</p>
      <textarea v-model="videoScript" class="ta" rows="12" spellcheck="false" />
      <p class="hint">由 AI 基于热点与群体画像自动生成，可继续人工编辑完善。</p>
      <div v-if="videoHistoryOpen" class="hist">
        <ul class="hist-list">
          <li v-for="h in videoHistory" :key="h.id" class="hist-item">
            <button type="button" class="hist-btn" @click="applyHistory(h)">
              <span class="k">{{ h.kind }}</span>
              <span class="t">{{ h.display_title || h.title || "（无标题）" }}</span>
              <span class="d">{{ h.display_date || "" }}</span>
            </button>
          </li>
        </ul>
      </div>
    </UiCard>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-width: 960px;
}
.lead {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--muted);
}
.hint {
  color: var(--muted);
}
.bar {
  display: flex;
  gap: 10px;
  margin: 0 0 10px;
  align-items: center;
}
.btn {
  padding: 8px 12px;
  border-radius: 10px;
  border: 1px solid rgba(106, 169, 255, 0.45);
  background: linear-gradient(180deg, #2a65ff, #1c49b6);
  color: #fff;
  font-size: 13px;
  cursor: pointer;
}
.btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.btn.ghost {
  background: #0c1426;
  color: var(--text);
}
.sel-lbl {
  font-size: 12px;
  color: var(--muted);
}
.sel {
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: #0c1426;
  color: var(--text);
  font-size: 13px;
}
.warn {
  margin: 0 0 10px;
  color: #ffb3b3;
  font-size: 12px;
}
.ta {
  width: 100%;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: #0c1426;
  color: var(--text);
  font-family: inherit;
  font-size: 13px;
  line-height: 1.5;
  resize: vertical;
}
.ctx {
  margin: 10px 0 0;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: rgba(12, 20, 38, 0.45);
  color: var(--muted);
  font-size: 12px;
  overflow: auto;
  max-height: 320px;
}
.hist {
  margin: 10px 0 0;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: rgba(12, 20, 38, 0.45);
}
.hist-bar {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 10px;
}
.hist-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 260px;
  overflow: auto;
}
.hist-item {
  margin: 0;
}
.hist-btn {
  width: 100%;
  display: grid;
  grid-template-columns: 110px 1fr 160px;
  gap: 10px;
  align-items: center;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: #0c1426;
  color: var(--text);
  cursor: pointer;
  text-align: left;
  font-size: 12px;
}
.hist-btn:hover {
  border-color: rgba(106, 169, 255, 0.45);
}
.hist-btn .k {
  color: var(--muted);
}
.hist-btn .t {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.hist-btn .d {
  color: var(--muted);
  text-align: right;
}
.ta + .hint {
  margin-top: 10px;
  font-size: 12px;
}
</style>
