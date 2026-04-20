import { createRouter, createWebHistory } from "vue-router";

import CounselorLayout from "../layouts/CounselorLayout.vue";
import LoginPage from "../pages/LoginPage.vue";
import OverviewPage from "../pages/counselor/OverviewPage.vue";
import GroupAnalysisPage from "../pages/counselor/GroupAnalysisPage.vue";
import IndividualListPage from "../pages/counselor/IndividualListPage.vue";
import IndividualPortraitPage from "../pages/counselor/IndividualPortraitPage.vue";
import ContentStudioPage from "../pages/counselor/ContentStudioPage.vue";
import AdminSystemPage from "../pages/AdminSystemPage.vue";

const AUTH_KEY = "edu_auth_token";
const ROLE_KEY = "edu_role";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", component: LoginPage },
    {
      path: "/",
      component: CounselorLayout,
      children: [
        { path: "", redirect: "/overview" },
        {
          path: "overview",
          component: OverviewPage,
          meta: { title: "总览", roles: ["admin", "counselor"] }
        },
        {
          path: "group-analysis",
          component: GroupAnalysisPage,
          meta: { title: "学生群体分析", roles: ["admin", "counselor"] }
        },
        {
          path: "individuals",
          component: IndividualListPage,
          meta: { title: "个体画像 · 学生列表", roles: ["admin", "counselor"] }
        },
        {
          path: "individuals/:studentId",
          component: IndividualPortraitPage,
          props: true,
          meta: { title: "个体画像 · 详情", roles: ["admin", "counselor"] }
        },
        {
          path: "content-studio",
          component: ContentStudioPage,
          meta: { title: "育人内容生成", roles: ["admin", "counselor"] }
        },
        {
          path: "system",
          component: AdminSystemPage,
          meta: { title: "系统管理", roles: ["admin"] }
        }
      ]
    }
  ]
});

router.beforeEach((to) => {
  const isAuthed = Boolean(localStorage.getItem(AUTH_KEY));
  const role = localStorage.getItem(ROLE_KEY) || "counselor";
  if (to.path !== "/login" && !isAuthed) {
    return "/login";
  }
  if (to.path === "/login" && isAuthed) {
    return "/overview";
  }
  const allowedRoles = to.meta.roles as string[] | undefined;
  if (allowedRoles && !allowedRoles.includes(role)) {
    return "/overview";
  }
  return true;
});

export default router;
