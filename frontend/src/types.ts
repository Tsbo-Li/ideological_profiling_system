/**
 * 与后端 `StudentProfileOut.radar_scores`（JSONB）对齐的前端雷达图维度。
 * 流水线可写入其它扩展键；图表主要消费 basic / learning / preference / stability / behavior。
 */
export interface RadarScores {
  basic?: number;
  learning?: number;
  preference?: number;
  stability?: number;
  behavior?: number;
  updated_at?: string;
  [key: string]: unknown;
}

export type WarningTrendPoint = {
  day: string;
  value: number;
};

/** 对齐后端 `/api/profile` JSON（参见 backend/api_server/main.py） */
export type StudentProfile = {
  student_id: string;
  basic_tags: string[];
  behavior_tags: string[];
  cognitive_tags: string[];
  radar_scores: RadarScores;
  intervention_action: string | null;
  last_computed_at: string | null;
  /** 活跃度序列，与库表 `student_profiles.activity_trend` 一致 */
  activity_trend: WarningTrendPoint[];
};

export type RiskLevel = "low" | "medium" | "high";

export type KpiStats = {
  totalStudents: number;
  warningStudents: number;
  highRiskStudents: number;
  inProgressTasks: number;
  closedTasks: number;
};

export type DashboardAlert = {
  id: string;
  title: string;
  risk_level: RiskLevel;
  summary: string;
  created_at: string;
};

export type HotTopic = {
  id: string;
  platform: "weibo" | "douyin" | "xiaohongshu";
  title: string;
  heat_label: string;
  captured_at: string;
};

export type GroupDistributionItem = {
  name: string;
  value: number;
};

export type CounselorDashboard = {
  kpis: KpiStats;
  groupDistribution: GroupDistributionItem[];
  warningTrend: WarningTrendPoint[];
  alerts: DashboardAlert[];
  hot_topics: HotTopic[];
};

/**
 * 对齐数值聚类产物：behavior_tags 来自簇映射；前端展示群体卡片时可附带 cluster_label。
 */
export type GroupPortrait = {
  name: string;
  size: number;
  topStudent: string;
  cluster_label?: number;
  representative_behavior_tags?: string[];
};

export type StudentListItem = {
  student_id: string;
  class_name: string;
  risk_level: RiskLevel;
  latest_warning_score: number;
  latest_active_at: string;
  tags: string[];
};

/** 与 `StudentProfile` 相同；保留别名便于页面语义区分 */
export type StudentProfileDetail = StudentProfile;

export type InterventionRecordPayload = {
  studentId: string;
  actionType: string;
  record: string;
};

/** 辅导员可参考的近期内容输出建议（非系统直推学生，仅工作台展示） */
export type ContentOutputSuggestion = {
  id: string;
  updatedAt: string;
  audienceHint: string;
  title: string;
  outline: string[];
  tone: string;
  disclaimers?: string[];
};

