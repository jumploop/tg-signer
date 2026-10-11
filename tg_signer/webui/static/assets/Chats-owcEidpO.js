import { E as ElMessage } from './index-BtUHGqts.js';
import { _ as _export_sfc, o as onMounted, n as createBlock, w as withCtx, q as api, Q as asArray, j as errMsg, r as resolveComponent, g as ref, u as useRouter, M as resolveDirective, h as openBlock, b as createBaseVNode, d as createVNode, f as createTextVNode, I as toDisplayString, a as createElementBlock, O as Fragment, P as renderList, t as normalizeClass, N as withDirectives, aw as copyText } from './index-BpR2pxEj.js';

const _hoisted_1 = { class: "chats-intro" };
const _hoisted_2 = { class: "chats-controls" };


const _sfc_main = {
  __name: 'Chats',
  setup(__props) {

const router = useRouter();
const accounts = ref([]);
const account = ref('');
const chats = ref([]);
const loading = ref(false);
const cacheLoading = ref(false);
const statusText = ref('');

async function refreshAccounts() {
  try {
    const { data } = await api.get('/api/accounts');
    accounts.value = asArray(data);
  } catch (error) {
    statusText.value = '账号列表加载失败，请确认 WebUI 服务正常运行。';
  }
}

async function refreshCache() {
  cacheLoading.value = true;
  try {
    const { data } = await api.get('/api/chats');
    chats.value = asArray(data);
    if (chats.value.length) {
      statusText.value = `已读取缓存，共 ${chats.value.length} 个群组/频道`;
      ElMessage.success(`已读取缓存，共 ${chats.value.length} 个群组/频道`);
    } else {
      statusText.value =
        '缓存为空：还没有账号缓存。请先在「账号管理」登录账号，或点「实时获取」写入缓存。';
      ElMessage.warning('缓存为空，请先登录账号或实时获取最近对话');
    }
  } catch (error) {
    statusText.value = '缓存读取失败，请稍后重试。';
    ElMessage.error('读取缓存失败: ' + errMsg(error));
  } finally {
    cacheLoading.value = false;
  }
}

async function fetchLive() {
  if (!account.value) {
    ElMessage.warning('请选择账号');
    return
  }
  loading.value = true;
  try {
    const { data } = await api.post('/api/chats/fetch', {
      account: account.value,
    });
    ElMessage[data.ok ? 'success' : 'error'](data.message);
    if (data.ok) {
      chats.value = asArray(data.chats);
      statusText.value = `实时获取 ${chats.value.length} 个对话`;
    }
  } catch (error) {
    ElMessage.error(errMsg(error));
  } finally {
    loading.value = false;
  }
}

async function copyId(id) {
  try {
    await copyText(id);
    ElMessage.success('已复制: ' + id);
  } catch (error) {
    ElMessage.warning('复制失败，请手动复制');
  }
}

function chatValue(row) {
  // 群组/频道的数字 ID 通用且稳定，优先填它；只有拿不到 ID 时才退回 @username。
  const id = row.id;
  if (id !== undefined && id !== null && id !== '') return String(id)
  return row.username ? '@' + row.username : ''
}

function applyToConfig(target, row) {
  const value = chatValue(row);
  const label = target === 'signer' ? 'Signer（签到）' : 'Automation（自动化）';
  router.push({
    name: 'configs',
    query: {
      kind: target,
      chat: value,
      title: row.title || '',
      username: row.username || '',
    },
  });
  ElMessage.info(`正在前往配置管理页，将 ${value} 填入 ${label} 配置`);
}

onMounted(() => {
  refreshAccounts();
  refreshCache();
});

return (_ctx, _cache) => {
  const _component_el_tag = resolveComponent("el-tag");
  const _component_el_option = resolveComponent("el-option");
  const _component_el_select = resolveComponent("el-select");
  const _component_el_button = resolveComponent("el-button");
  const _component_el_table_column = resolveComponent("el-table-column");
  const _component_el_dropdown_item = resolveComponent("el-dropdown-item");
  const _component_el_dropdown_menu = resolveComponent("el-dropdown-menu");
  const _component_el_dropdown = resolveComponent("el-dropdown");
  const _component_el_empty = resolveComponent("el-empty");
  const _component_el_table = resolveComponent("el-table");
  const _component_el_card = resolveComponent("el-card");
  const _directive_loading = resolveDirective("loading");

  return (openBlock(), createBlock(_component_el_card, {
    shadow: "never",
    class: "chats-card"
  }, {
    default: withCtx(() => [
      createBaseVNode("div", _hoisted_1, [
        _cache[1] || (_cache[1] = createBaseVNode("div", null, [
          createBaseVNode("span", { class: "section-label" }, "对话资源"),
          createBaseVNode("p", { class: "section-caption" }, "从已登录账号读取群组和频道，快速复制 ID 或填入配置。")
        ], -1)),
        createVNode(_component_el_tag, {
          type: "info",
          effect: "light",
          round: ""
        }, {
          default: withCtx(() => [
            createTextVNode(toDisplayString(chats.value.length) + " 个对话", 1)
          ]),
          _: 1
        })
      ]),
      createBaseVNode("div", _hoisted_2, [
        createVNode(_component_el_select, {
          modelValue: account.value,
          "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((account).value = $event)),
          placeholder: "选择账号（需已登录）",
          class: "account-select"
        }, {
          default: withCtx(() => [
            (openBlock(true), createElementBlock(Fragment, null, renderList(accounts.value, (a) => {
              return (openBlock(), createBlock(_component_el_option, {
                key: a.account,
                label: a.account,
                value: a.account
              }, null, 8, ["label", "value"]))
            }), 128))
          ]),
          _: 1
        }, 8, ["modelValue"]),
        createVNode(_component_el_button, {
          type: "primary",
          loading: loading.value,
          onClick: fetchLive
        }, {
          default: withCtx(() => [...(_cache[2] || (_cache[2] = [
            createTextVNode(" 实时获取最近 50 个对话 ", -1)
          ]))]),
          _: 1
        }, 8, ["loading"]),
        createVNode(_component_el_button, {
          loading: cacheLoading.value,
          onClick: refreshCache
        }, {
          default: withCtx(() => [...(_cache[3] || (_cache[3] = [
            createTextVNode("读取缓存", -1)
          ]))]),
          _: 1
        }, 8, ["loading"])
      ]),
      createBaseVNode("div", {
        class: normalizeClass(["status-line", { 'is-empty': !statusText.value }]),
        role: "status",
        "aria-live": "polite"
      }, [
        _cache[4] || (_cache[4] = createBaseVNode("span", { class: "status-dot" }, null, -1)),
        createBaseVNode("span", null, toDisplayString(statusText.value || '尚未读取对话数据'), 1)
      ], 2),
      _cache[9] || (_cache[9] = createBaseVNode("div", { class: "table-heading" }, [
        createBaseVNode("span", null, "群组 / 频道"),
        createBaseVNode("span", { class: "table-heading__meta" }, "支持复制到 Signer 或 Automation")
      ], -1)),
      withDirectives((openBlock(), createBlock(_component_el_table, {
        data: chats.value,
        "max-height": "560",
        class: "chats-table"
      }, {
        empty: withCtx(() => [
          createVNode(_component_el_empty, {
            description: "暂无群组/频道数据：请在「账号管理」登录账号，或选择账号后点「实时获取最近 50 个对话」写入缓存，再用「读取缓存」查看",
            "image-size": 60
          })
        ]),
        default: withCtx(() => [
          createVNode(_component_el_table_column, {
            prop: "id",
            label: "ID",
            width: "140"
          }),
          createVNode(_component_el_table_column, {
            prop: "title",
            label: "标题"
          }),
          createVNode(_component_el_table_column, {
            prop: "type",
            label: "类型",
            width: "120"
          }),
          createVNode(_component_el_table_column, {
            prop: "username",
            label: "用户名"
          }),
          createVNode(_component_el_table_column, {
            label: "操作",
            width: "220"
          }, {
            default: withCtx(({ row }) => [
              createVNode(_component_el_button, {
                size: "small",
                onClick: $event => (copyId(row.id))
              }, {
                default: withCtx(() => [...(_cache[5] || (_cache[5] = [
                  createTextVNode("复制ID", -1)
                ]))]),
                _: 1
              }, 8, ["onClick"]),
              createVNode(_component_el_dropdown, {
                size: "small",
                onCommand: (cmd) => applyToConfig(cmd, row)
              }, {
                dropdown: withCtx(() => [
                  createVNode(_component_el_dropdown_menu, null, {
                    default: withCtx(() => [
                      createVNode(_component_el_dropdown_item, { command: "signer" }, {
                        default: withCtx(() => [...(_cache[7] || (_cache[7] = [
                          createTextVNode("填入 Signer（签到）", -1)
                        ]))]),
                        _: 1
                      }),
                      createVNode(_component_el_dropdown_item, { command: "automation" }, {
                        default: withCtx(() => [...(_cache[8] || (_cache[8] = [
                          createTextVNode("填入 Automation（自动化）", -1)
                        ]))]),
                        _: 1
                      })
                    ]),
                    _: 1
                  })
                ]),
                default: withCtx(() => [
                  createVNode(_component_el_button, {
                    size: "small",
                    type: "primary",
                    plain: ""
                  }, {
                    default: withCtx(() => [...(_cache[6] || (_cache[6] = [
                      createTextVNode("复制到配置", -1)
                    ]))]),
                    _: 1
                  })
                ]),
                _: 1
              }, 8, ["onCommand"])
            ]),
            _: 1
          })
        ]),
        _: 1
      }, 8, ["data"])), [
        [_directive_loading, loading.value || cacheLoading.value]
      ])
    ]),
    _: 1
  }))
}
}

};
const Chats = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-ecb86368"]]);

export { Chats as default };
