import { _ as _export_sfc, o as onMounted, k as onUnmounted, m as watch, n as createBlock, w as withCtx, q as api, r as resolveComponent, g as ref, s as useRoute, u as useRouter, h as openBlock, d as createVNode, t as normalizeClass, b as createBaseVNode, i as unref, p as promotion_default, v as close_default, x as setting_default, y as video_play_default, z as user_default, A as chat_dot_round_default, B as avatar_default, C as tickets_default, D as document_default, F as tools_default, f as createTextVNode, G as createCommentVNode, H as switch_button_default, a as createElementBlock, I as menu_default, J as toDisplayString, K as folder_default, L as computed, M as logout, E as ElMessage } from './index-DQY2xS5L.js';

const _hoisted_1 = { class: "brand" };
const _hoisted_2 = { class: "aside-foot" };
const _hoisted_3 = { class: "header-context" };
const _hoisted_4 = ["title"];
const _hoisted_5 = { class: "wd-text" };
const _hoisted_6 = {
  class: "page-intro",
  "aria-labelledby": "page-heading"
};
const _hoisted_7 = { id: "page-heading" };
const _hoisted_8 = {
  class: "workspace-status",
  "aria-live": "polite"
};


const _sfc_main = {
  __name: 'Layout',
  setup(__props) {

const route = useRoute();
const router = useRouter();
const workdir = ref('');
const authRequired = ref(true);
const mobileNavOpen = ref(false);

const titles = {
  configs: '配置管理',
  run: '任务运行',
  accounts: '账号',
  chats: '群组 / 频道',
  users: '用户信息',
  records: '签到记录',
  logs: '运行日志',
  settings: '基础设置',
};
const active = computed(() => '/' + (route.name || 'configs'));
const title = computed(() => titles[route.name] || 'tg-signer WebUI');
const description = computed(() => {
  const descriptions = {
    configs: '集中管理签到、自动化与模型配置，让每次变更都清晰可追溯。',
    run: '启动、停止并实时观察任务运行状态。',
    accounts: '管理 Telegram 登录会话与授权状态。',
    chats: '发现群组与频道，并将目标快速带入配置流程。',
    users: '查看已缓存的账户信息与最近对话。',
    records: '浏览签到历史，快速确认任务执行结果。',
    logs: '检索运行日志，快速定位异常与执行轨迹。',
    settings: '管理工作目录与 WebUI 的基础运行参数。',
  };
  return descriptions[route.name] || 'Telegram 自动化控制台'
});

async function refreshState() {
  try {
    const { data } = await api.get('/api/state');
    workdir.value = data.workdir;
    authRequired.value = data.auth_required;
  } catch (error) {
    /* 瞬时错误忽略 */
  }
}

function doLogout() {
  logout();
  ElMessage.success('已退出登录');
  router.push('/login');
}

function handleKeydown(event) {
  if (event.key === 'Escape' && mobileNavOpen.value) {
    mobileNavOpen.value = false;
  }
}

onMounted(() => {
  refreshState();
  window.addEventListener('keydown', handleKeydown);
});
onUnmounted(() => window.removeEventListener('keydown', handleKeydown));
// 切换页面时同步工作目录（基础设置页可能修改它）
watch(
  () => route.name,
  () => {
    mobileNavOpen.value = false;
    refreshState();
  }
);

return (_ctx, _cache) => {
  const _component_el_icon = resolveComponent("el-icon");
  const _component_el_button = resolveComponent("el-button");
  const _component_el_menu_item = resolveComponent("el-menu-item");
  const _component_el_menu = resolveComponent("el-menu");
  const _component_el_tag = resolveComponent("el-tag");
  const _component_el_aside = resolveComponent("el-aside");
  const _component_el_header = resolveComponent("el-header");
  const _component_router_view = resolveComponent("router-view");
  const _component_el_main = resolveComponent("el-main");
  const _component_el_container = resolveComponent("el-container");

  return (openBlock(), createBlock(_component_el_container, { class: "shell" }, {
    default: withCtx(() => [
      createVNode(_component_el_aside, {
        id: "app-navigation",
        width: "232px",
        class: normalizeClass(["aside", { 'is-open': mobileNavOpen.value }]),
        "aria-label": "主导航"
      }, {
        default: withCtx(() => [
          createBaseVNode("div", _hoisted_1, [
            createVNode(_component_el_icon, { class: "brand-icon" }, {
              default: withCtx(() => [
                createVNode(unref(promotion_default))
              ]),
              _: 1
            }),
            _cache[3] || (_cache[3] = createBaseVNode("span", { class: "brand-name" }, "tg-signer", -1)),
            createVNode(_component_el_button, {
              class: "aside-close",
              text: "",
              "aria-label": "关闭导航",
              onClick: _cache[0] || (_cache[0] = $event => (mobileNavOpen.value = false))
            }, {
              default: withCtx(() => [
                createVNode(_component_el_icon, null, {
                  default: withCtx(() => [
                    createVNode(unref(close_default))
                  ]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _cache[14] || (_cache[14] = createBaseVNode("p", { class: "brand-sub" }, "Telegram 自动化工作台", -1)),
          createVNode(_component_el_menu, {
            "default-active": active.value,
            router: "",
            class: "side-menu"
          }, {
            default: withCtx(() => [
              createVNode(_component_el_menu_item, { index: "/configs" }, {
                default: withCtx(() => [
                  createVNode(_component_el_icon, null, {
                    default: withCtx(() => [
                      createVNode(unref(setting_default))
                    ]),
                    _: 1
                  }),
                  _cache[4] || (_cache[4] = createBaseVNode("span", null, "配置管理", -1))
                ]),
                _: 1
              }),
              createVNode(_component_el_menu_item, { index: "/run" }, {
                default: withCtx(() => [
                  createVNode(_component_el_icon, null, {
                    default: withCtx(() => [
                      createVNode(unref(video_play_default))
                    ]),
                    _: 1
                  }),
                  _cache[5] || (_cache[5] = createBaseVNode("span", null, "任务运行", -1))
                ]),
                _: 1
              }),
              createVNode(_component_el_menu_item, { index: "/accounts" }, {
                default: withCtx(() => [
                  createVNode(_component_el_icon, null, {
                    default: withCtx(() => [
                      createVNode(unref(user_default))
                    ]),
                    _: 1
                  }),
                  _cache[6] || (_cache[6] = createBaseVNode("span", null, "账号", -1))
                ]),
                _: 1
              }),
              createVNode(_component_el_menu_item, { index: "/chats" }, {
                default: withCtx(() => [
                  createVNode(_component_el_icon, null, {
                    default: withCtx(() => [
                      createVNode(unref(chat_dot_round_default))
                    ]),
                    _: 1
                  }),
                  _cache[7] || (_cache[7] = createBaseVNode("span", null, "群组 / 频道", -1))
                ]),
                _: 1
              }),
              createVNode(_component_el_menu_item, { index: "/users" }, {
                default: withCtx(() => [
                  createVNode(_component_el_icon, null, {
                    default: withCtx(() => [
                      createVNode(unref(avatar_default))
                    ]),
                    _: 1
                  }),
                  _cache[8] || (_cache[8] = createBaseVNode("span", null, "用户信息", -1))
                ]),
                _: 1
              }),
              createVNode(_component_el_menu_item, { index: "/records" }, {
                default: withCtx(() => [
                  createVNode(_component_el_icon, null, {
                    default: withCtx(() => [
                      createVNode(unref(tickets_default))
                    ]),
                    _: 1
                  }),
                  _cache[9] || (_cache[9] = createBaseVNode("span", null, "签到记录", -1))
                ]),
                _: 1
              }),
              createVNode(_component_el_menu_item, { index: "/logs" }, {
                default: withCtx(() => [
                  createVNode(_component_el_icon, null, {
                    default: withCtx(() => [
                      createVNode(unref(document_default))
                    ]),
                    _: 1
                  }),
                  _cache[10] || (_cache[10] = createBaseVNode("span", null, "运行日志", -1))
                ]),
                _: 1
              }),
              createVNode(_component_el_menu_item, { index: "/settings" }, {
                default: withCtx(() => [
                  createVNode(_component_el_icon, null, {
                    default: withCtx(() => [
                      createVNode(unref(tools_default))
                    ]),
                    _: 1
                  }),
                  _cache[11] || (_cache[11] = createBaseVNode("span", null, "基础设置", -1))
                ]),
                _: 1
              })
            ]),
            _: 1
          }, 8, ["default-active"]),
          createBaseVNode("div", _hoisted_2, [
            (!authRequired.value)
              ? (openBlock(), createBlock(_component_el_tag, {
                  key: 0,
                  size: "small",
                  effect: "plain",
                  class: "auth-tag"
                }, {
                  default: withCtx(() => [...(_cache[12] || (_cache[12] = [
                    createTextVNode("未启用授权码", -1)
                  ]))]),
                  _: 1
                }))
              : createCommentVNode("", true),
            (authRequired.value)
              ? (openBlock(), createBlock(_component_el_button, {
                  key: 1,
                  text: "",
                  class: "logout-btn",
                  onClick: doLogout
                }, {
                  default: withCtx(() => [
                    createVNode(_component_el_icon, { style: {"margin-right":"4px"} }, {
                      default: withCtx(() => [
                        createVNode(unref(switch_button_default))
                      ]),
                      _: 1
                    }),
                    _cache[13] || (_cache[13] = createTextVNode("退出登录 ", -1))
                  ]),
                  _: 1
                }))
              : createCommentVNode("", true)
          ])
        ]),
        _: 1
      }, 8, ["class"]),
      (mobileNavOpen.value)
        ? (openBlock(), createElementBlock("button", {
            key: 0,
            class: "nav-overlay",
            "aria-label": "关闭导航",
            onClick: _cache[1] || (_cache[1] = $event => (mobileNavOpen.value = false))
          }))
        : createCommentVNode("", true),
      createVNode(_component_el_container, { class: "main-col" }, {
        default: withCtx(() => [
          createVNode(_component_el_header, {
            class: "header",
            height: "72px"
          }, {
            default: withCtx(() => [
              createVNode(_component_el_button, {
                class: "mobile-menu-btn",
                text: "",
                "aria-label": "打开导航",
                "aria-expanded": mobileNavOpen.value,
                "aria-controls": "app-navigation",
                onClick: _cache[2] || (_cache[2] = $event => (mobileNavOpen.value = true))
              }, {
                default: withCtx(() => [
                  createVNode(_component_el_icon, null, {
                    default: withCtx(() => [
                      createVNode(unref(menu_default))
                    ]),
                    _: 1
                  })
                ]),
                _: 1
              }, 8, ["aria-expanded"]),
              createBaseVNode("span", _hoisted_3, [
                _cache[15] || (_cache[15] = createTextVNode("Workspace ", -1)),
                _cache[16] || (_cache[16] = createBaseVNode("span", null, "/", -1)),
                createTextVNode(" " + toDisplayString(title.value), 1)
              ]),
              _cache[17] || (_cache[17] = createBaseVNode("span", { style: {"flex":"1"} }, null, -1)),
              createBaseVNode("span", {
                class: "workdir",
                title: '工作目录：' + workdir.value
              }, [
                createVNode(_component_el_icon, { class: "wd-icon" }, {
                  default: withCtx(() => [
                    createVNode(unref(folder_default))
                  ]),
                  _: 1
                }),
                createBaseVNode("span", _hoisted_5, toDisplayString(workdir.value || '加载中…'), 1)
              ], 8, _hoisted_4)
            ]),
            _: 1
          }),
          createVNode(_component_el_main, { class: "main" }, {
            default: withCtx(() => [
              createBaseVNode("section", _hoisted_6, [
                createBaseVNode("div", null, [
                  _cache[18] || (_cache[18] = createBaseVNode("span", { class: "page-kicker" }, "CONTROL CENTER", -1)),
                  createBaseVNode("h1", _hoisted_7, toDisplayString(title.value), 1),
                  createBaseVNode("p", null, toDisplayString(description.value), 1)
                ]),
                createBaseVNode("div", _hoisted_8, [
                  createBaseVNode("span", {
                    class: normalizeClass(["status-dot", { 'is-loading': !workdir.value }])
                  }, null, 2),
                  createBaseVNode("span", null, toDisplayString(workdir.value ? '工作区就绪' : '正在连接工作区'), 1)
                ])
              ]),
              createVNode(_component_router_view)
            ]),
            _: 1
          })
        ]),
        _: 1
      })
    ]),
    _: 1
  }))
}
}

};
const Layout = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-df88250c"]]);

export { Layout as default };
