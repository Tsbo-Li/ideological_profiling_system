/**
 * 辅导员端数据入口。
 *
 * 约定：
 * - 文件前半部分：真实 `fetch` / `apiGet` 与对外导出函数（流程一眼能读完）。
 * - 文件末尾 `__MOCK__` 区域：本地演示数据、网络延迟模拟；后端就绪后按函数内 TODO 替换为真实路径即可。
 */
import type {
  ContentOutputSuggestion,
  CounselorDashboard,
  GroupDistributionItem,
  GroupPortrait,
  InterventionRecordPayload,
  RadarScores,
  StudentListItem,
  StudentProfile,
  StudentProfileDetail
} from "../types";
import { apiGet } from "./client";

// -----------------------------------------------------------------------------
// 真实后端（学生画像、总览仪表盘、群体聚类雷达走 HTTP，其余接口待接）
// -----------------------------------------------------------------------------

async function fetchStudentProfileFromApi(studentId: string): Promise<StudentProfile | null> {
  try {
    const p = await apiGet<StudentProfile>(`/api/profile/${encodeURIComponent(studentId)}`);
    return {
      ...p,
      activity_trend: Array.isArray(p.activity_trend) ? p.activity_trend : []
    };
  } catch {
    return null;
  }
}

// -----------------------------------------------------------------------------
// 与后端 `StudentProfile` 对齐的合并（不依赖演示学生表，仅做字段合并）
// -----------------------------------------------------------------------------

function mergeStudentProfile(api: StudentProfile, overlay?: StudentProfileDetail): StudentProfileDetail {
  const radarMerge: RadarScores = {
    ...((overlay?.radar_scores as RadarScores) ?? {}),
    ...((api.radar_scores as RadarScores) ?? {})
  };
  const fromOverlay = overlay?.activity_trend?.length ? overlay.activity_trend : undefined;
  const fromApi = api.activity_trend?.length ? api.activity_trend : undefined;
  const activity_trend = fromOverlay ?? fromApi ?? mockDefaultActivityTrend();

  return {
    student_id: api.student_id,
    basic_tags: [...(api.basic_tags ?? [])],
    behavior_tags: [...(api.behavior_tags ?? [])],
    cognitive_tags: [...(api.cognitive_tags ?? [])],
    radar_scores: radarMerge,
    intervention_action: api.intervention_action ?? overlay?.intervention_action ?? null,
    last_computed_at: api.last_computed_at ?? overlay?.last_computed_at ?? null,
    activity_trend
  };
}

// -----------------------------------------------------------------------------
// 对外 API（实现保持简短；演示阶段委托给末尾 mock）
// -----------------------------------------------------------------------------

export type ClusterDistributionMethod = "behavior_kmeans" | "text_topic" | "temporal";

export async function getCounselorDashboard(): Promise<CounselorDashboard> {
  try {
    return await apiGet<CounselorDashboard>("/api/counselor/dashboard");
  } catch {
    return withMockLatency(mockCounselorDashboard());
  }
}

export async function getClusterDistribution(method: ClusterDistributionMethod): Promise<GroupDistributionItem[]> {
  try {
    const qs = new URLSearchParams({ method });
    return await apiGet<GroupDistributionItem[]>(`/api/counselor/clusters?${qs.toString()}`);
  } catch {
    return withMockLatency(mockClusterDistribution(method));
  }
}

export async function getCounselorGroups(): Promise<GroupPortrait[]> {
  // TODO: return apiGet<GroupPortrait[]>("/api/counselor/groups");
  return withMockLatency(mockCounselorGroups());
}

export async function getStudentsList(params?: {
  keyword?: string;
  riskLevel?: "all" | "high" | "medium" | "low";
}): Promise<StudentListItem[]> {
  // TODO: return apiGet(`/api/counselor/students?${new URLSearchParams(...)}`);
  return withMockLatency(mockFilterStudentList(params));
}

export async function getStudentProfileDetail(studentId: string): Promise<StudentProfileDetail> {
  const raw = studentId.trim();
  const key = raw.toUpperCase();

  const remote = raw ? await fetchStudentProfileFromApi(raw) : null;
  if (remote) {
    const overlay = mockProfileDetailByStudentKey(key);
    return withMockLatency(mergeStudentProfile(remote, overlay));
  }

  const localOnly = mockProfileDetailByStudentKey(key);
  if (localOnly) return withMockLatency(localOnly);

  return withMockLatency(mockUnknownStudentProfile(key));
}

export async function saveInterventionRecord(payload: InterventionRecordPayload): Promise<{ ok: boolean }> {
  if (!payload.studentId.trim() || !payload.record.trim()) {
    throw new Error("studentId 与 record 不能为空");
  }
  // TODO: return apiPost("/api/counselor/interventions", payload);
  return withMockLatency({ ok: true }, 180);
}

export async function getTalkingAssistantDraft(studentId: string): Promise<string[]> {
  // TODO: return apiPost<string[]>("/api/counselor/talking-draft", { studentId });
  const detail = await getStudentProfileDetail(studentId);
  return withMockLatency(mockTalkingAssistantLines(detail), 400);
}

export async function getRecentContentSuggestions(): Promise<ContentOutputSuggestion[]> {
  // TODO: return apiGet<ContentOutputSuggestion[]>("/api/counselor/content-suggestions");
  return withMockLatency(mockContentOutputSuggestions());
}

// =============================================================================
// __MOCK__ 演示数据与延迟（后端就绪后主要改上半部分 TODO，本节可整段删除或收窄）
// =============================================================================

function withMockLatency<T>(data: T, timeoutMs = 220): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(data), timeoutMs));
}

const MOCK_STUDENT_ROWS: StudentListItem[] = [
  {
    student_id: "STU_001",
    class_name: "2023级计算机1班",
    risk_level: "high",
    latest_warning_score: 87,
    latest_active_at: "2026-04-18 22:11",
    tags: ["学业压力", "作息紊乱", "夜间高活跃"]
  },
  {
    student_id: "STU_002",
    class_name: "2023级计算机2班",
    risk_level: "medium",
    latest_warning_score: 63,
    latest_active_at: "2026-04-18 20:43",
    tags: ["娱乐倾向", "短视频高频"]
  },
  {
    student_id: "STU_003",
    class_name: "2023级软件1班",
    risk_level: "low",
    latest_warning_score: 28,
    latest_active_at: "2026-04-18 18:36",
    tags: ["学习投入", "作息规律"]
  },
  {
    student_id: "STU_004",
    class_name: "2023级软件2班",
    risk_level: "medium",
    latest_warning_score: 58,
    latest_active_at: "2026-04-17 23:08",
    tags: ["社交回避", "论坛负向表达"]
  }
];

const MOCK_PROFILE_DETAIL_BY_KEY: Record<string, StudentProfileDetail> = {
  STU_001: {
    student_id: "STU_001",
    basic_tags: ["工科专业", "大二", "住宿生"],
    behavior_tags: ["夜间活跃", "作业临期冲刺", "学习工具高频使用"],
    cognitive_tags: ["考试焦虑", "自我要求较高", "对成绩波动敏感"],
    radar_scores: {
      basic: 72,
      learning: 78,
      preference: 58,
      stability: 46,
      behavior: 74,
      updated_at: "2026-04-18T22:30:00"
    },
    intervention_action: "建议先提供学习规划类参考材料（学院或班级统一渠道），再安排一次面谈。",
    last_computed_at: "2026-04-18T22:30:00",
    activity_trend: [
      { day: "Mon", value: 51 },
      { day: "Tue", value: 58 },
      { day: "Wed", value: 56 },
      { day: "Thu", value: 64 },
      { day: "Fri", value: 67 },
      { day: "Sat", value: 60 },
      { day: "Sun", value: 55 }
    ]
  },
  STU_002: {
    student_id: "STU_002",
    basic_tags: ["工科专业", "大二", "住宿生"],
    behavior_tags: ["短视频高频", "学习时段碎片化"],
    cognitive_tags: ["目标感波动", "外部激励依赖"],
    radar_scores: {
      basic: 70,
      learning: 52,
      preference: 48,
      stability: 54,
      behavior: 58,
      updated_at: "2026-04-18T21:10:00"
    },
    intervention_action: "建议以学习任务拆解为主，配合同伴监督。",
    last_computed_at: "2026-04-18T21:10:00",
    activity_trend: [
      { day: "Mon", value: 46 },
      { day: "Tue", value: 49 },
      { day: "Wed", value: 45 },
      { day: "Thu", value: 53 },
      { day: "Fri", value: 52 },
      { day: "Sat", value: 50 },
      { day: "Sun", value: 47 }
    ]
  }
};

const MOCK_CLUSTER_BY_METHOD: Record<ClusterDistributionMethod, GroupDistributionItem[]> = {
  behavior_kmeans: [
    { name: "学业投入群", value: 122 },
    { name: "高压焦虑群", value: 96 },
    { name: "娱乐倾向群", value: 88 },
    { name: "低活跃观察群", value: 54 }
  ],
  text_topic: [
    { name: "考试压力主题", value: 78 },
    { name: "实习就业主题", value: 65 },
    { name: "人际关系主题", value: 52 },
    { name: "生活消费主题", value: 41 },
    { name: "其它/噪声", value: 124 }
  ],
  temporal: [
    { name: "晨型规律群", value: 89 },
    { name: "夜间高活跃群", value: 71 },
    { name: "碎片化作息群", value: 103 },
    { name: "作息稳定群", value: 97 }
  ]
};

function mockDefaultActivityTrend(): StudentProfileDetail["activity_trend"] {
  return [
    { day: "Mon", value: 40 },
    { day: "Tue", value: 42 },
    { day: "Wed", value: 38 },
    { day: "Thu", value: 41 },
    { day: "Fri", value: 39 },
    { day: "Sat", value: 43 },
    { day: "Sun", value: 40 }
  ];
}

function mockProfileDetailByStudentKey(key: string): StudentProfileDetail | undefined {
  return MOCK_PROFILE_DETAIL_BY_KEY[key];
}

function mockUnknownStudentProfile(key: string): StudentProfileDetail {
  return {
    student_id: key || "UNKNOWN",
    basic_tags: ["基础信息待补充"],
    behavior_tags: [],
    cognitive_tags: [],
    radar_scores: {},
    intervention_action: null,
    last_computed_at: null,
    activity_trend: mockDefaultActivityTrend()
  };
}

function mockCounselorDashboard(): CounselorDashboard {
  return {
    kpis: {
      totalStudents: 360,
      warningStudents: 42,
      highRiskStudents: 14,
      inProgressTasks: 8,
      closedTasks: 35
    },
    groupDistribution: MOCK_CLUSTER_BY_METHOD.behavior_kmeans,
    warningTrend: [
      { day: "周一", value: 11 },
      { day: "周二", value: 13 },
      { day: "周三", value: 12 },
      { day: "周四", value: 15 },
      { day: "周五", value: 16 },
      { day: "周六", value: 14 },
      { day: "周日", value: 12 }
    ],
    alerts: [
      {
        id: "a1",
        title: "连续夜间高活跃 + 学业关键词上升",
        risk_level: "high",
        summary: "涉及 3 人，近 7 日触发阈值；建议本周内面谈排期。",
        created_at: "2026-04-18 21:40"
      },
      {
        id: "a2",
        title: "短视频停留时长异常（班级均值对比）",
        risk_level: "medium",
        summary: "涉及 11 人，可作为班会素材切入点，非紧急个案。",
        created_at: "2026-04-18 18:06"
      },
      {
        id: "a3",
        title: "论坛负向表达聚集（匿名板块）",
        risk_level: "medium",
        summary: "主题与课程负荷相关，建议联动学业辅导资源。",
        created_at: "2026-04-17 22:15"
      }
    ],
    hot_topics: [
      {
        id: "h1",
        platform: "weibo",
        title: "春招补录与实习焦虑讨论升温",
        heat_label: "高",
        captured_at: "2026-04-18 20:00"
      },
      {
        id: "h2",
        platform: "douyin",
        title: "「一周复习法」类短视频传播广",
        heat_label: "中高",
        captured_at: "2026-04-18 19:10"
      },
      {
        id: "h3",
        platform: "xiaohongshu",
        title: "校园生活成本与兼职经验帖增多",
        heat_label: "中",
        captured_at: "2026-04-18 17:35"
      },
      {
        id: "h4",
        platform: "weibo",
        title: "心理健康话题热搜词条周期性出现",
        heat_label: "中",
        captured_at: "2026-04-18 12:00"
      }
    ]
  };
}

function mockClusterDistribution(method: ClusterDistributionMethod): GroupDistributionItem[] {
  return [...(MOCK_CLUSTER_BY_METHOD[method] ?? MOCK_CLUSTER_BY_METHOD.behavior_kmeans)];
}

function mockCounselorGroups(): GroupPortrait[] {
  return [
    {
      name: "学业投入群",
      size: 122,
      topStudent: "STU_003",
      cluster_label: 0,
      representative_behavior_tags: ["图书馆高频", "作息规律"]
    },
    {
      name: "高压焦虑群",
      size: 96,
      topStudent: "STU_001",
      cluster_label: 1,
      representative_behavior_tags: ["夜间活跃", "晚归偏多"]
    },
    {
      name: "娱乐倾向群",
      size: 88,
      topStudent: "STU_002",
      cluster_label: 2,
      representative_behavior_tags: ["游戏流量偏高", "短视频停留长"]
    }
  ];
}

function mockFilterStudentList(params?: {
  keyword?: string;
  riskLevel?: "all" | "high" | "medium" | "low";
}): StudentListItem[] {
  const keyword = params?.keyword?.trim().toLowerCase();
  const riskLevel = params?.riskLevel ?? "all";
  return MOCK_STUDENT_ROWS.filter((item) => {
    const okRisk = riskLevel === "all" || item.risk_level === riskLevel;
    const okKeyword =
      !keyword ||
      item.student_id.toLowerCase().includes(keyword) ||
      item.class_name.toLowerCase().includes(keyword) ||
      item.tags.join(" ").toLowerCase().includes(keyword);
    return okRisk && okKeyword;
  });
}

function mockTalkingAssistantLines(detail: StudentProfileDetail): string[] {
  const tagHint = [...(detail.behavior_tags ?? []), ...(detail.cognitive_tags ?? [])].slice(0, 4).join("、");
  return [
    `开场：先确认近况与课程负荷，避免一上来就谈「风险标签」（学生：${detail.student_id}）。`,
    `可自然提及的标签线索：${tagHint || "（暂无标签，先倾听与核实）"}`,
    `可给出的支持：学业节奏拆解、校内心理咨询预约流程、同伴互助渠道（由学院统一口径补充链接）。`,
    `收尾：约定一小步行动（例如本周固定作息锚点），并说明你会后续跟进而非一次谈话解决所有问题。`
  ];
}

function mockContentOutputSuggestions(): ContentOutputSuggestion[] {
  return [
    {
      id: "draft-001",
      updatedAt: "2026-04-18 09:30",
      audienceHint: "面向高压焦虑倾向学生群体（班会/班级群话术参考）",
      title: "时间管理微习惯：考前两周如何稳住节奏",
      outline: [
        "开篇共情：承认复习节奏被打乱的普遍性，避免说教语气。",
        "给出「最小可行日程」模板：每日 3 个固定锚点时间块。",
        "结尾收口：附上校内学习支持入口（辅导员手动转发链接到班级群）。"
      ],
      tone: "支持性、具象、可操作",
      disclaimers: ["此处为话术与结构建议，不由系统自动推送到学生账号。"]
    },
    {
      id: "draft-002",
      updatedAt: "2026-04-17 16:05",
      audienceHint: "夜间高活跃 + 作息紊乱特征（推文/主题活动预告）",
      title: "「睡好再学」主题活动预告稿（短文案）",
      outline: [
        "用一句数据话术引入夜间活跃现象（匿名化表述）。",
        "列出三个可操作建议：固定熄灯提醒、同伴互助打卡、心理咨询预约流程。",
        "引导线下参与：海报二维码由学工统一发布。"
      ],
      tone: "轻松、同伴视角",
      disclaimers: ["实际发布渠道与审批流程由学院规定，系统仅输出文案建议。"]
    }
  ];
}
