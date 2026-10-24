import { _ as _export_sfc, m as watch, o as onMounted, r as resolveComponent, N as resolveDirective, O as withDirectives, h as openBlock, n as createBlock, w as withCtx, b as createBaseVNode, d as createVNode, a as createElementBlock, P as Fragment, Q as renderList, f as createTextVNode, J as toDisplayString, q as api, R as asArray, g as ref, L as computed, S as ElMessageBox, E as ElMessage, j as errMsg, T as asObject, U as vShow, G as createCommentVNode, s as useRoute, u as useRouter } from './index-Ceed42FL.js';

const _hoisted_1$3 = { class: "editor-toolbar" };
const _hoisted_2$3 = { class: "toolbar-fields" };
const _hoisted_3$1 = { class: "toolbar-actions" };
const _hoisted_4$1 = { class: "ts-intro editor-status" };
const _hoisted_5$1 = { class: "ts-section-label" };
const _hoisted_6$1 = { class: "hint" };


const _sfc_main$3 = {
  __name: 'ConfigEditor',
  props: {
  kind: String,
  prefillChat: String,
  prefillTitle: String,
  prefillUsername: String,
},
  emits: ['applied'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;

const names = ref([]);
const selected = ref(null);
const name = ref('');
const jsonText = ref('');
const hint = ref('');
const saving = ref(false);
const loading = ref(false);

const editing = computed(() => selected.value !== null && selected.value !== '');
const kindLabel = computed(() =>
  props.kind === 'signer' ? 'Signer 签到配置' : 'Automation 自动化配置'
);

async function refresh() {
  loading.value = true;
  try {
    const { data } = await api.get(`/api/configs/${props.kind}`);
    names.value = asArray(data.names);
    if (!editing.value && names.value.length === 0) {
      hint.value = '暂无配置。填写名称后粘贴 JSON，或点击「填充模板」「新建」开始。';
    }
  } catch (error) {
    hint.value = '配置列表加载失败，请确认 WebUI 服务正常运行。';
  } finally {
    loading.value = false;
  }
}

async function loadRaw(target) {
  if (!target) return
  try {
    const { data } = await api.get(
      `/api/configs/${props.kind}/${encodeURIComponent(target)}`
    );
    name.value = data.name;
    selected.value = data.name;
    jsonText.value = JSON.stringify(data.payload, null, 2);
    hint.value = data.updated_from_old
      ? '该配置已自动迁移为当前结构（保存时将写入新格式）。路径: ' + data.path
      : `正在编辑: ${data.name}。路径: ${data.path}`;
  } catch (error) {
    ElMessage.error('配置加载失败: ' + errMsg(error));
  }
}

function newConfig() {
  // 保留当前编辑器内容，方便「另存为」：清除选择与名称即进入新建模式
  selected.value = null;
  name.value = '';
  hint.value = names.value.length
    ? '新建配置：填写名称并编辑 JSON（可点击「填充模板」）。'
    : '暂无配置。填写名称后粘贴 JSON，或点击「填充模板」开始。';
}

async function fillTemplate() {
  if (jsonText.value.trim() && jsonText.value !== '{}') {
    try {
      await ElMessageBox.confirm(
        '填充模板将覆盖当前编辑器内容，是否继续？',
        '提示',
        { type: 'warning', confirmButtonText: '覆盖', cancelButtonText: '取消' }
      );
    } catch (error) {
      return
    }
  }
  try {
    const { data } = await api.get(`/api/configs/${props.kind}/template`);
    jsonText.value = JSON.stringify(data.payload, null, 2);
    hint.value = editing.value || name.value.trim()
      ? '已填充模板（可继续编辑）。'
      : '已填充模板，填写配置名称后保存。';
    ElMessage.success('已填充模板');
  } catch (error) {
    ElMessage.error(errMsg(error));
  }
}

function parseJson() {
  try {
    return JSON.parse(jsonText.value)
  } catch (error) {
    ElMessage.error('JSON 格式错误: ' + error.message);
    return null
  }
}

async function save() {
  const payload = parseJson();
  if (payload === null) return
  const target = (name.value || '').trim();
  if (!editing.value && !target) {
    ElMessage.warning('请填写配置名称');
    return
  }
  saving.value = true;
  try {
    const saveName = editing.value ? selected.value : target;
    const { data } = await api.post(
      `/api/configs/${props.kind}/${encodeURIComponent(saveName)}`,
      payload
    );
    ElMessage.success(editing.value ? '修改已保存' : `配置 ${data.name} 已创建`);
    name.value = data.name;
    selected.value = data.name;
    hint.value = '路径: ' + data.path;
    await refresh();
  } catch (error) {
    ElMessage.error(errMsg(error));
  } finally {
    saving.value = false;
  }
}

async function remove() {
  const target = selected.value;
  if (!target) return
  try {
    await ElMessageBox.confirm(
      `确认删除配置 ${target}？删除后不可恢复。`,
      '提示',
      { type: 'warning', confirmButtonText: '删除' }
    );
  } catch (error) {
    return
  }
  try {
    await api.delete(`/api/configs/${props.kind}/${encodeURIComponent(target)}`);
    ElMessage.success('已删除');
    newConfig();
    await refresh();
  } catch (error) {
    ElMessage.error(errMsg(error));
  }
}

function fillChatId(payload, chat) {
  if (props.kind === 'signer') {
    if (!Array.isArray(payload.chats) || !payload.chats.length) return null
    payload.chats[0].chat_id = toChatValue(chat);
    return 'chats[0].chat_id'
  }
  if (props.kind === 'automation') {
    const rule = Array.isArray(payload.rules) ? payload.rules[0] : null;
    if (!rule || !Array.isArray(rule.triggers) || !rule.triggers.length) return null
    const trigger = rule.triggers[0];
    if (!trigger.params || typeof trigger.params !== 'object') trigger.params = {};
    trigger.params.chat_id = toChatValue(chat);
    // 过滤器同样锁定该群，避免其他群的消息也命中这条规则
    if (rule.filters && typeof rule.filters === 'object') {
      rule.filters.chat_id = toChatValue(chat);
    }
    return 'rules[0].triggers[0].params.chat_id'
  }
}

// 数字 ID 写成 JSON 数字,保持配置形状一致。engine 的 _match_chat 现在会对
// 数字字符串做 normalize_chat_ref 归一化,即使保存成字符串也能命中。
function toChatValue(raw) {
  const text = String(raw).trim();
  return /^-?\d+$/.test(text) ? Number(text) : text
}

// Signer 任务名优先用群组标题，其次用用户名；同时给一个随机的签到延迟。
// 只在新建时填：模板里的「示例任务」/random_seconds:0 是占位值需要替换，
// 而编辑已有配置时不能抹掉用户自己填的群组名和延迟（与 suggestName 同理）。
function fillSignerExtras(payload) {
  if (props.kind !== 'signer' || editing.value) return null
  const chat = Array.isArray(payload.chats) ? payload.chats[0] : null;
  if (!chat) return null
  const label = (props.prefillTitle || props.prefillUsername || '').trim();
  if (label) chat.name = label;
  payload.random_seconds = 100 + Math.floor(Math.random() * 901);
  return label
}

async function applyPrefill(chat) {
  let payload;
  const current = jsonText.value.trim();
  if (!current || current === '{}') {
    try {
      const { data } = await api.get(`/api/configs/${props.kind}/template`);
      payload = data.payload;
    } catch (error) {
      ElMessage.error(errMsg(error));
      return
    }
  } else {
    try {
      payload = JSON.parse(current);
    } catch (error) {
      ElMessage.error('JSON 格式错误，无法填入: ' + error.message);
      return
    }
  }
  const field = fillChatId(payload, chat);
  if (!field) {
    ElMessage.warning('当前 JSON 结构中没有可填入的 chat_id 字段，请手动编辑');
    return
  }
  const label = fillSignerExtras(payload);
  jsonText.value = JSON.stringify(payload, null, 2);
  await suggestName(chat);
  const extra = label ? `，任务名 = ${label}` : '';
  hint.value = `已填入 ${field} = ${chat}${extra}，确认后点「保存」。`;
  ElMessage.success(`已填入 ${field}: ${chat}${extra}`);
  emit('applied');
}

// 新建模式下自动生成配置名；已在编辑或用户已填名时保持原样。
async function suggestName(chat) {
  if (editing.value || name.value.trim()) return
  try {
    const { data } = await api.get(`/api/configs/${props.kind}/suggest-name`, {
      params: {
        chat_id: chat,
        title: props.prefillTitle || '',
        username: props.prefillUsername || '',
      },
    });
    name.value = data.name;
  } catch (error) {
    ElMessage.warning('自动生成配置名失败，请手动填写');
  }
}

watch(selected, (value) => {
  if (value) loadRaw(value);
});

watch(
  () => props.prefillChat,
  (chat) => {
    if (chat) applyPrefill(String(chat));
  },
  { immediate: true }
);

onMounted(refresh);

return (_ctx, _cache) => {
  const _component_el_option = resolveComponent("el-option");
  const _component_el_select = resolveComponent("el-select");
  const _component_el_input = resolveComponent("el-input");
  const _component_el_button = resolveComponent("el-button");
  const _component_el_tag = resolveComponent("el-tag");
  const _component_el_card = resolveComponent("el-card");
  const _directive_loading = resolveDirective("loading");

  return withDirectives((openBlock(), createBlock(_component_el_card, {
    shadow: "never",
    class: "config-editor"
  }, {
    default: withCtx(() => [
      createBaseVNode("div", _hoisted_1$3, [
        createBaseVNode("div", _hoisted_2$3, [
          createVNode(_component_el_select, {
            modelValue: selected.value,
            "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((selected).value = $event)),
            placeholder: "选择已有配置",
            class: "config-select",
            filterable: "",
            clearable: "",
            onClear: newConfig
          }, {
            default: withCtx(() => [
              (openBlock(true), createElementBlock(Fragment, null, renderList(names.value, (n) => {
                return (openBlock(), createBlock(_component_el_option, {
                  key: n,
                  label: n,
                  value: n
                }, null, 8, ["label", "value"]))
              }), 128))
            ]),
            _: 1
          }, 8, ["modelValue"]),
          createVNode(_component_el_input, {
            modelValue: name.value,
            "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((name).value = $event)),
            placeholder: "配置名称",
            class: "config-name",
            clearable: "",
            disabled: editing.value
          }, null, 8, ["modelValue", "disabled"]),
          createVNode(_component_el_button, { onClick: newConfig }, {
            default: withCtx(() => [...(_cache[3] || (_cache[3] = [
              createTextVNode("新建", -1)
            ]))]),
            _: 1
          }),
          createVNode(_component_el_button, { onClick: fillTemplate }, {
            default: withCtx(() => [...(_cache[4] || (_cache[4] = [
              createTextVNode("填充模板", -1)
            ]))]),
            _: 1
          })
        ]),
        createBaseVNode("div", _hoisted_3$1, [
          createVNode(_component_el_button, {
            type: "primary",
            loading: saving.value,
            onClick: save
          }, {
            default: withCtx(() => [
              createTextVNode(toDisplayString(editing.value ? '保存修改' : '保存'), 1)
            ]),
            _: 1
          }, 8, ["loading"]),
          createVNode(_component_el_button, {
            type: "danger",
            plain: "",
            disabled: !editing.value,
            onClick: remove
          }, {
            default: withCtx(() => [...(_cache[5] || (_cache[5] = [
              createTextVNode(" 删除 ", -1)
            ]))]),
            _: 1
          }, 8, ["disabled"]),
          createVNode(_component_el_button, {
            loading: loading.value,
            onClick: refresh
          }, {
            default: withCtx(() => [...(_cache[6] || (_cache[6] = [
              createTextVNode("刷新", -1)
            ]))]),
            _: 1
          }, 8, ["loading"])
        ])
      ]),
      createBaseVNode("div", _hoisted_4$1, [
        createBaseVNode("div", null, [
          createBaseVNode("span", _hoisted_5$1, toDisplayString(kindLabel.value), 1),
          createBaseVNode("p", _hoisted_6$1, toDisplayString(hint.value), 1)
        ]),
        createVNode(_component_el_tag, {
          type: editing.value ? 'primary' : 'info',
          effect: "light",
          round: ""
        }, {
          default: withCtx(() => [
            createTextVNode(toDisplayString(editing.value ? '编辑中' : '新建模式'), 1)
          ]),
          _: 1
        }, 8, ["type"])
      ]),
      _cache[7] || (_cache[7] = createBaseVNode("div", { class: "ts-intro code-heading" }, [
        createBaseVNode("span", null, "JSON 配置"),
        createBaseVNode("span", { class: "hint" }, "保存前会自动校验 JSON 格式")
      ], -1)),
      createVNode(_component_el_input, {
        modelValue: jsonText.value,
        "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((jsonText).value = $event)),
        type: "textarea",
        rows: 20,
        class: "editor mono",
        placeholder: "{}"
      }, null, 8, ["modelValue"])
    ]),
    _: 1
  })), [
    [_directive_loading, loading.value]
  ])
}
}

};
const ConfigEditor = /*#__PURE__*/_export_sfc(_sfc_main$3, [['__scopeId',"data-v-877538f4"]]);

const _hoisted_1$2 = { class: "ts-intro" };
const _hoisted_2$2 = { class: "hint" };


const _sfc_main$2 = {
  __name: 'LlmConfig',
  setup(__props) {

const apiKey = ref('');
// 服务端只回掩码（如 ****abcd），绝不明文下发。这里单独存掩码、不回填进输入框：
// 回填会让人误以为框里是真实密钥，且 show-password 一开就是「****abcd」这种
// 看着像坏掉的值。改为留空 + 占位符说明，留空即「不修改」。
const apiKeyMask = ref('');
const baseUrl = ref('');
const model = ref('');
const hint = ref('');
const loading = ref(false);
const saving = ref(false);
const testing = ref(false);

const apiKeyConfigured = computed(() => apiKeyMask.value.length > 0);
const apiKeyPlaceholder = computed(() =>
  apiKeyConfigured.value
    ? `已配置（${apiKeyMask.value}），留空表示不修改`
    : '请输入 API Key',
);

async function refresh() {
  loading.value = true;
  try {
    const { data } = await api.get('/api/llm-config');
    const config = asObject(data.config);
    apiKeyMask.value = config.api_key || '';
    apiKey.value = '';
    baseUrl.value = config.base_url || '';
    model.value = config.model || '';
    hint.value = data.has_env
      ? '当前运行时优先使用环境变量配置'
      : '已加载本地配置';
  } catch (error) {
    hint.value = '模型配置加载失败，请确认 WebUI 服务正常运行。';
  } finally {
    loading.value = false;
  }
}

async function submitLlm(endpoint, busy, onSuccess) {
  const typed = apiKey.value.trim();
  if (!typed && !apiKeyConfigured.value) {
    ElMessage.warning('API Key 不能为空');
    return
  }
  busy.value = true;
  try {
    const { data } = await api.post(endpoint, {
      api_key: typed,
      base_url: baseUrl.value,
      model: model.value,
    });
    onSuccess(data);
  } catch (error) {
    ElMessage.error(errMsg(error));
  } finally {
    busy.value = false;
  }
}

async function save() {
  await submitLlm('/api/llm-config', saving, () => {
    ElMessage.success('已保存');
    refresh();
  });
}

async function testConn() {
  await submitLlm('/api/llm-config/test', testing, ({ ok, message }) => {
    ElMessage[ok ? 'success' : 'error'](message);
  });
}

onMounted(refresh);

return (_ctx, _cache) => {
  const _component_el_tag = resolveComponent("el-tag");
  const _component_el_alert = resolveComponent("el-alert");
  const _component_el_input = resolveComponent("el-input");
  const _component_el_form_item = resolveComponent("el-form-item");
  const _component_el_button = resolveComponent("el-button");
  const _component_el_form = resolveComponent("el-form");
  const _component_el_card = resolveComponent("el-card");
  const _directive_loading = resolveDirective("loading");

  return withDirectives((openBlock(), createBlock(_component_el_card, { shadow: "never" }, {
    default: withCtx(() => [
      createBaseVNode("div", _hoisted_1$2, [
        _cache[4] || (_cache[4] = createBaseVNode("div", null, [
          createBaseVNode("span", { class: "ts-section-label" }, "大模型连接"),
          createBaseVNode("p", { class: "ts-section-caption" }, "配置用于 AI 能力的 OpenAI 兼容接口，密钥仅保存在当前工作目录。")
        ], -1)),
        createVNode(_component_el_tag, {
          type: "info",
          effect: "light",
          round: ""
        }, {
          default: withCtx(() => [...(_cache[3] || (_cache[3] = [
            createTextVNode("OpenAI Compatible", -1)
          ]))]),
          _: 1
        })
      ]),
      createVNode(_component_el_alert, {
        title: "环境变量优先级更高",
        description: "如果设置了 OPENAI_API_KEY、OPENAI_BASE_URL 或 OPENAI_MODEL，这里保存的配置将被运行时环境变量覆盖。",
        type: "info",
        "show-icon": "",
        closable: false,
        class: "llm-alert"
      }),
      createVNode(_component_el_form, {
        "label-width": "140px",
        class: "llm-form"
      }, {
        default: withCtx(() => [
          createVNode(_component_el_form_item, { label: "OPENAI_API_KEY" }, {
            default: withCtx(() => [
              createVNode(_component_el_input, {
                modelValue: apiKey.value,
                "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((apiKey).value = $event)),
                type: "password",
                "show-password": "",
                placeholder: apiKeyPlaceholder.value
              }, null, 8, ["modelValue", "placeholder"])
            ]),
            _: 1
          }),
          createVNode(_component_el_form_item, { label: "OPENAI_BASE_URL" }, {
            default: withCtx(() => [
              createVNode(_component_el_input, {
                modelValue: baseUrl.value,
                "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((baseUrl).value = $event)),
                placeholder: "例如 https://api.openai.com/v1"
              }, null, 8, ["modelValue"])
            ]),
            _: 1
          }),
          createVNode(_component_el_form_item, { label: "OPENAI_MODEL" }, {
            default: withCtx(() => [
              createVNode(_component_el_input, {
                modelValue: model.value,
                "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((model).value = $event))
              }, null, 8, ["modelValue"])
            ]),
            _: 1
          }),
          createVNode(_component_el_form_item, null, {
            default: withCtx(() => [
              createVNode(_component_el_button, {
                type: "primary",
                loading: saving.value,
                onClick: save
              }, {
                default: withCtx(() => [...(_cache[5] || (_cache[5] = [
                  createTextVNode("保存", -1)
                ]))]),
                _: 1
              }, 8, ["loading"]),
              createVNode(_component_el_button, {
                loading: testing.value,
                onClick: testConn
              }, {
                default: withCtx(() => [...(_cache[6] || (_cache[6] = [
                  createTextVNode("测试连通性", -1)
                ]))]),
                _: 1
              }, 8, ["loading"]),
              createBaseVNode("span", _hoisted_2$2, toDisplayString(hint.value), 1)
            ]),
            _: 1
          })
        ]),
        _: 1
      })
    ]),
    _: 1
  })), [
    [_directive_loading, loading.value]
  ])
}
}

};
const LlmConfig = /*#__PURE__*/_export_sfc(_sfc_main$2, [['__scopeId',"data-v-fd14b9a6"]]);

const _hoisted_1$1 = { class: "wizard-progress" };
const _hoisted_2$1 = { class: "ts-section-label" };
const _hoisted_3 = { class: "hint" };
const _hoisted_4 = { class: "task-toolbar" };
const _hoisted_5 = { class: "hint" };
const _hoisted_6 = {
  key: 1,
  class: "task-list"
};
const _hoisted_7 = { class: "task-row" };
const _hoisted_8 = { class: "task-index" };
const _hoisted_9 = { class: "task-info" };
const _hoisted_10 = { class: "task-title" };
const _hoisted_11 = { class: "hint" };
const _hoisted_12 = { class: "hint" };
const _hoisted_13 = { class: "task-actions" };
const _hoisted_14 = { class: "wizard-footer" };
const _hoisted_15 = {
  class: "hint",
  style: {"margin-left":"8px"}
};
const _hoisted_16 = { class: "action-editor" };
const _hoisted_17 = { class: "action-fields" };
const _hoisted_18 = {
  key: 3,
  class: "hint"
};
const _hoisted_19 = {
  key: 4,
  class: "hint"
};


const _sfc_main$1 = {
  __name: 'SignerWizard',
  props: {
  visible: Boolean,
},
  emits: ['update:visible'],
  setup(__props, { emit: __emit }) {


const emit = __emit;

const ACTION_OPTIONS = [
  { value: 'send_text', label: '发送普通文本' },
  { value: 'send_dice', label: '发送 Dice emoji' },
  { value: 'click_keyboard', label: '根据文本点击键盘' },
  { value: 'choose_option_by_image', label: '根据图片选择选项' },
  { value: 'reply_calculation', label: '回复计算题' },
];
const DICE_OPTIONS = ['🎲', '🎯', '🏀', '⚽', '🎳', '🎰'];
const ACTION_LABELS = {
  1: '发送文本',
  2: '发送骰子',
  3: '点击按钮',
  4: '图片选选项',
  5: '回复计算题',
};

const step = ref(0);
const taskName = ref('my_sign');
const signAt = ref('06:00:00');
const randomSeconds = ref(0);
const chats = ref([]);
const saving = ref(false);

const taskDialogVisible = ref(false);
const taskIndex = ref(null);
const draft = ref(emptyDraft());

function emptyDraft() {
  return {
    chatId: '',
    name: '',
    threadEnabled: false,
    threadId: null,
    deleteAfter: null,
    actions: [{ type: 'send_text', text: '' }],
  }
}

function parseAction(action) {
  switch (action.action) {
    case 1:
      return { type: 'send_text', text: action.text || '' }
    case 2:
      return { type: 'send_dice', dice: action.dice || '🎲' }
    case 3:
      return { type: 'click_keyboard', text: action.text || '' }
    case 4:
      return { type: 'choose_option_by_image' }
    case 5:
      return { type: 'reply_calculation' }
    default:
      return { type: 'send_text', text: '' }
  }
}

function initFromProps() {
  step.value = 0;
  taskName.value = 'my_sign';
  signAt.value = '06:00:00';
  randomSeconds.value = 0;
  chats.value = [];
}

function actionSummary(actions) {
  if (!actions || !actions.length) return '无动作'
  return actions.map((a) => ACTION_LABELS[a.action] || '动作' + a.action).join(' → ')
}

function openTask(index) {
  taskIndex.value = index;
  if (index === null) {
    draft.value = emptyDraft();
  } else {
    const chat = chats.value[index];
    draft.value = {
      chatId: String(chat.chat_id),
      name: chat.name || '',
      threadEnabled: Boolean(chat.message_thread_id),
      threadId: chat.message_thread_id || null,
      deleteAfter: chat.delete_after || null,
      actions: (chat.actions || []).map(parseAction),
    };
  }
  taskDialogVisible.value = true;
}

function removeTask(index) {
  chats.value.splice(index, 1);
}

function addAction() {
  draft.value.actions.push({ type: 'send_text', text: '' });
}

function removeAction(index) {
  draft.value.actions.splice(index, 1);
}

function onActionTypeChange(act) {
  if (act.type === 'send_dice' && !act.dice) {
    act.dice = '🎲';
  }
}

function parseChatId(raw) {
  const value = String(raw || '').trim();
  if (!value) throw new Error('Chat ID 不能为空')
  if (value.startsWith('@')) {
    if (value.length === 1) throw new Error('用户名不能为空')
    return value
  }
  const num = Number(value);
  if (!Number.isInteger(num)) throw new Error('Chat ID 必须是整数或 @用户名')
  return num
}

function toActionJSON(act) {
  switch (act.type) {
    case 'send_text':
      return { action: 1, text: (act.text || '').trim() }
    case 'send_dice':
      return { action: 2, dice: act.dice || '🎲' }
    case 'click_keyboard':
      return { action: 3, text: (act.text || '').trim() }
    case 'choose_option_by_image':
      return { action: 4 }
    case 'reply_calculation':
      return { action: 5 }
    default:
      throw new Error('未知动作类型')
  }
}

function validateTask() {
  const chatId = parseChatId(draft.value.chatId);
  if (!draft.value.actions.length) {
    throw new Error('至少需要配置一个动作')
  }
  const first = draft.value.actions[0];
  if (first.type !== 'send_text' && first.type !== 'send_dice') {
    throw new Error('第一个动作必须是「发送普通文本」或「发送 Dice emoji」')
  }
  for (const act of draft.value.actions) {
    if (act.type === 'send_text' && !(act.text || '').trim()) {
      throw new Error('「发送普通文本」动作需要填写文本内容')
    }
    if (act.type === 'click_keyboard' && !(act.text || '').trim()) {
      throw new Error('「根据文本点击键盘」动作需要填写按钮文本')
    }
  }
  let threadId = null;
  if (draft.value.threadEnabled) {
    if (draft.value.threadId === null || draft.value.threadId === undefined || draft.value.threadId === '') {
      throw new Error('启用话题后必须填写 message_thread_id')
    }
    threadId = Number(draft.value.threadId);
  }
  return {
    chat_id: chatId,
    message_thread_id: threadId,
    name: (draft.value.name || '').trim() || null,
    delete_after:
      draft.value.deleteAfter === null || draft.value.deleteAfter === undefined || draft.value.deleteAfter === ''
        ? null
        : Number(draft.value.deleteAfter),
    actions: draft.value.actions.map(toActionJSON),
  }
}

function saveTask() {
  try {
    const chat = validateTask();
    if (taskIndex.value === null) {
      chats.value.push(chat);
    } else {
      chats.value[taskIndex.value] = chat;
    }
    taskDialogVisible.value = false;
  } catch (error) {
    ElMessage.warning(error.message);
  }
}

async function saveAll() {
  const name = (taskName.value || '').trim();
  if (!name) {
    ElMessage.warning('任务名称不能为空');
    return
  }
  if (!chats.value.length) {
    ElMessage.warning('请至少添加一个签到任务');
    return
  }
  const payload = {
    chats: chats.value,
    sign_at: (signAt.value || '').trim(),
    random_seconds: Number(randomSeconds.value) || 0,
    sign_interval: 1,
  };
  saving.value = true;
  try {
    const { data } = await api.post(
      `/api/configs/signer/${encodeURIComponent(name)}`,
      payload
    );
    ElMessage.success(`配置 ${data.name} 保存成功`);
    emit('update:visible', false);
  } catch (error) {
    ElMessage.error('保存失败: ' + errMsg(error));
  } finally {
    saving.value = false;
  }
}

return (_ctx, _cache) => {
  const _component_el_step = resolveComponent("el-step");
  const _component_el_steps = resolveComponent("el-steps");
  const _component_el_tag = resolveComponent("el-tag");
  const _component_el_input = resolveComponent("el-input");
  const _component_el_form_item = resolveComponent("el-form-item");
  const _component_el_input_number = resolveComponent("el-input-number");
  const _component_el_form = resolveComponent("el-form");
  const _component_el_button = resolveComponent("el-button");
  const _component_el_empty = resolveComponent("el-empty");
  const _component_el_card = resolveComponent("el-card");
  const _component_el_switch = resolveComponent("el-switch");
  const _component_el_option = resolveComponent("el-option");
  const _component_el_select = resolveComponent("el-select");
  const _component_el_dialog = resolveComponent("el-dialog");

  return (openBlock(), createBlock(_component_el_dialog, {
    "model-value": __props.visible,
    title: "交互式配置向导",
    width: "720px",
    "close-on-click-modal": false,
    "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => (_ctx.$emit('update:visible', $event))),
    onOpen: initFromProps
  }, {
    footer: withCtx(() => [
      createBaseVNode("div", _hoisted_14, [
        (step.value === 1)
          ? (openBlock(), createBlock(_component_el_button, {
              key: 0,
              onClick: _cache[4] || (_cache[4] = $event => (step.value = 0))
            }, {
              default: withCtx(() => [...(_cache[20] || (_cache[20] = [
                createTextVNode("上一步", -1)
              ]))]),
              _: 1
            }))
          : createCommentVNode("", true),
        (step.value === 0)
          ? (openBlock(), createBlock(_component_el_button, {
              key: 1,
              type: "primary",
              onClick: _cache[5] || (_cache[5] = $event => (step.value = 1))
            }, {
              default: withCtx(() => [...(_cache[21] || (_cache[21] = [
                createTextVNode("下一步", -1)
              ]))]),
              _: 1
            }))
          : createCommentVNode("", true),
        (step.value === 1)
          ? (openBlock(), createElementBlock(Fragment, { key: 2 }, [
              createVNode(_component_el_button, {
                onClick: _cache[6] || (_cache[6] = $event => (_ctx.$emit('update:visible', false)))
              }, {
                default: withCtx(() => [...(_cache[22] || (_cache[22] = [
                  createTextVNode("取消", -1)
                ]))]),
                _: 1
              }),
              createVNode(_component_el_button, {
                type: "primary",
                loading: saving.value,
                onClick: saveAll
              }, {
                default: withCtx(() => [...(_cache[23] || (_cache[23] = [
                  createTextVNode("保存配置", -1)
                ]))]),
                _: 1
              }, 8, ["loading"])
            ], 64))
          : createCommentVNode("", true)
      ])
    ]),
    default: withCtx(() => [
      createVNode(_component_el_steps, {
        active: step.value,
        "finish-status": "success",
        "align-center": "",
        style: {"margin-bottom":"20px"}
      }, {
        default: withCtx(() => [
          createVNode(_component_el_step, { title: "基础设置" }),
          createVNode(_component_el_step, { title: "签到任务" })
        ]),
        _: 1
      }, 8, ["active"]),
      createBaseVNode("div", _hoisted_1$1, [
        createBaseVNode("div", null, [
          createBaseVNode("span", _hoisted_2$1, toDisplayString(step.value === 0 ? '基础设置' : '签到任务'), 1),
          createBaseVNode("p", _hoisted_3, toDisplayString(step.value === 0 ? '先定义任务名称和执行时间。' : '为每个群组或频道配置要执行的动作。'), 1)
        ]),
        createVNode(_component_el_tag, {
          type: "info",
          effect: "light",
          round: ""
        }, {
          default: withCtx(() => [
            createTextVNode("第 " + toDisplayString(step.value + 1) + " / 2 步", 1)
          ]),
          _: 1
        })
      ]),
      withDirectives(createVNode(_component_el_form, {
        "label-width": "120px",
        class: "wizard-form"
      }, {
        default: withCtx(() => [
          createVNode(_component_el_form_item, {
            label: "任务名称",
            required: ""
          }, {
            default: withCtx(() => [
              createVNode(_component_el_input, {
                modelValue: taskName.value,
                "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((taskName).value = $event)),
                placeholder: "例如 my_sign"
              }, null, 8, ["modelValue"])
            ]),
            _: 1
          }),
          createVNode(_component_el_form_item, { label: "签到时间" }, {
            default: withCtx(() => [
              createVNode(_component_el_input, {
                modelValue: signAt.value,
                "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((signAt).value = $event)),
                placeholder: "06:00:00 或 0 6 * * *"
              }, null, 8, ["modelValue"]),
              _cache[15] || (_cache[15] = createBaseVNode("div", { class: "hint" }, "支持具体时间（06:00:00）或 Cron 表达式（0 6 * * *）", -1))
            ]),
            _: 1
          }),
          createVNode(_component_el_form_item, { label: "随机延迟（秒）" }, {
            default: withCtx(() => [
              createVNode(_component_el_input_number, {
                modelValue: randomSeconds.value,
                "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((randomSeconds).value = $event)),
                min: 0,
                step: 1
              }, null, 8, ["modelValue"]),
              _cache[16] || (_cache[16] = createBaseVNode("div", {
                class: "hint",
                style: {"margin-left":"8px"}
              }, "在签到时间基础上追加随机延迟，0 表示不延迟", -1))
            ]),
            _: 1
          })
        ]),
        _: 1
      }, 512), [
        [vShow, step.value === 0]
      ]),
      withDirectives(createBaseVNode("div", null, [
        createBaseVNode("div", _hoisted_4, [
          createBaseVNode("span", _hoisted_5, "已添加 " + toDisplayString(chats.value.length) + " 个签到任务", 1),
          createVNode(_component_el_button, {
            type: "primary",
            size: "small",
            onClick: _cache[3] || (_cache[3] = $event => (openTask(null)))
          }, {
            default: withCtx(() => [...(_cache[17] || (_cache[17] = [
              createTextVNode("添加任务", -1)
            ]))]),
            _: 1
          })
        ]),
        (!chats.value.length)
          ? (openBlock(), createBlock(_component_el_empty, {
              key: 0,
              description: "暂无任务，点击「添加任务」开始",
              "image-size": 60
            }))
          : (openBlock(), createElementBlock("div", _hoisted_6, [
              (openBlock(true), createElementBlock(Fragment, null, renderList(chats.value, (chat, idx) => {
                return (openBlock(), createBlock(_component_el_card, {
                  key: idx,
                  shadow: "hover",
                  class: "task-card"
                }, {
                  default: withCtx(() => [
                    createBaseVNode("div", _hoisted_7, [
                      createBaseVNode("span", _hoisted_8, "#" + toDisplayString(idx + 1), 1),
                      createBaseVNode("div", _hoisted_9, [
                        createBaseVNode("div", _hoisted_10, toDisplayString(chat.chat_id), 1),
                        createBaseVNode("div", _hoisted_11, [
                          createTextVNode(toDisplayString(chat.name || '未命名') + " ", 1),
                          (chat.message_thread_id)
                            ? (openBlock(), createElementBlock(Fragment, { key: 0 }, [
                                createTextVNode(" · 话题 " + toDisplayString(chat.message_thread_id), 1)
                              ], 64))
                            : createCommentVNode("", true),
                          (chat.delete_after)
                            ? (openBlock(), createElementBlock(Fragment, { key: 1 }, [
                                createTextVNode(" · 删后 " + toDisplayString(chat.delete_after) + "s", 1)
                              ], 64))
                            : createCommentVNode("", true)
                        ]),
                        createBaseVNode("div", _hoisted_12, toDisplayString(actionSummary(chat.actions)), 1)
                      ]),
                      createBaseVNode("div", _hoisted_13, [
                        createVNode(_component_el_button, {
                          size: "small",
                          onClick: $event => (openTask(idx))
                        }, {
                          default: withCtx(() => [...(_cache[18] || (_cache[18] = [
                            createTextVNode("编辑", -1)
                          ]))]),
                          _: 1
                        }, 8, ["onClick"]),
                        createVNode(_component_el_button, {
                          size: "small",
                          type: "danger",
                          plain: "",
                          onClick: $event => (removeTask(idx))
                        }, {
                          default: withCtx(() => [...(_cache[19] || (_cache[19] = [
                            createTextVNode("删除", -1)
                          ]))]),
                          _: 1
                        }, 8, ["onClick"])
                      ])
                    ])
                  ]),
                  _: 2
                }, 1024))
              }), 128))
            ]))
      ], 512), [
        [vShow, step.value === 1]
      ]),
      createVNode(_component_el_dialog, {
        modelValue: taskDialogVisible.value,
        "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((taskDialogVisible).value = $event)),
        title: taskIndex.value === null ? '添加签到任务' : '编辑签到任务',
        width: "560px",
        "append-to-body": "",
        "close-on-click-modal": false
      }, {
        footer: withCtx(() => [
          createVNode(_component_el_button, {
            onClick: _cache[12] || (_cache[12] = $event => (taskDialogVisible.value = false))
          }, {
            default: withCtx(() => [...(_cache[29] || (_cache[29] = [
              createTextVNode("取消", -1)
            ]))]),
            _: 1
          }),
          createVNode(_component_el_button, {
            type: "primary",
            onClick: saveTask
          }, {
            default: withCtx(() => [...(_cache[30] || (_cache[30] = [
              createTextVNode("确定", -1)
            ]))]),
            _: 1
          })
        ]),
        default: withCtx(() => [
          createVNode(_component_el_form, {
            "label-width": "120px",
            class: "task-form"
          }, {
            default: withCtx(() => [
              createVNode(_component_el_form_item, {
                label: "Chat ID",
                required: ""
              }, {
                default: withCtx(() => [
                  createVNode(_component_el_input, {
                    modelValue: draft.value.chatId,
                    "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((draft.value.chatId) = $event)),
                    placeholder: "整数 ID 或 @username"
                  }, null, 8, ["modelValue"]),
                  _cache[24] || (_cache[24] = createBaseVNode("div", { class: "hint" }, "支持整数 chat_id（如 -1001234567890）或 @username", -1))
                ]),
                _: 1
              }),
              createVNode(_component_el_form_item, { label: "任务名称" }, {
                default: withCtx(() => [
                  createVNode(_component_el_input, {
                    modelValue: draft.value.name,
                    "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((draft.value.name) = $event)),
                    placeholder: "可选，便于识别"
                  }, null, 8, ["modelValue"])
                ]),
                _: 1
              }),
              createVNode(_component_el_form_item, { label: "话题" }, {
                default: withCtx(() => [
                  createVNode(_component_el_switch, {
                    modelValue: draft.value.threadEnabled,
                    "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((draft.value.threadEnabled) = $event))
                  }, null, 8, ["modelValue"]),
                  createVNode(_component_el_input_number, {
                    modelValue: draft.value.threadId,
                    "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((draft.value.threadId) = $event)),
                    min: 0,
                    disabled: !draft.value.threadEnabled,
                    style: {"width":"160px","margin-left":"8px"}
                  }, null, 8, ["modelValue", "disabled"]),
                  createBaseVNode("div", _hoisted_15, toDisplayString(draft.value.threadEnabled ? '群组话题 message_thread_id' : '未启用群组话题'), 1)
                ]),
                _: 1
              }),
              createVNode(_component_el_form_item, { label: "删除消息（秒）" }, {
                default: withCtx(() => [
                  createVNode(_component_el_input_number, {
                    modelValue: draft.value.deleteAfter,
                    "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((draft.value.deleteAfter) = $event)),
                    min: 0,
                    step: 1,
                    clearable: "",
                    style: {"width":"160px"}
                  }, null, 8, ["modelValue"]),
                  _cache[25] || (_cache[25] = createBaseVNode("div", {
                    class: "hint",
                    style: {"margin-left":"8px"}
                  }, "发送后自动删除，留空表示不删除", -1))
                ]),
                _: 1
              }),
              createVNode(_component_el_form_item, {
                label: "动作列表",
                required: ""
              }, {
                default: withCtx(() => [
                  createBaseVNode("div", _hoisted_16, [
                    (openBlock(true), createElementBlock(Fragment, null, renderList(draft.value.actions, (act, ai) => {
                      return (openBlock(), createElementBlock("div", {
                        key: ai,
                        class: "action-row"
                      }, [
                        createBaseVNode("div", _hoisted_17, [
                          createVNode(_component_el_select, {
                            modelValue: act.type,
                            "onUpdate:modelValue": $event => ((act.type) = $event),
                            style: {"width":"210px"},
                            onChange: $event => (onActionTypeChange(act))
                          }, {
                            default: withCtx(() => [
                              (openBlock(), createElementBlock(Fragment, null, renderList(ACTION_OPTIONS, (opt) => {
                                return createVNode(_component_el_option, {
                                  key: opt.value,
                                  label: opt.label,
                                  value: opt.value
                                }, null, 8, ["label", "value"])
                              }), 64))
                            ]),
                            _: 1
                          }, 8, ["modelValue", "onUpdate:modelValue", "onChange"]),
                          (act.type === 'send_text')
                            ? (openBlock(), createBlock(_component_el_input, {
                                key: 0,
                                modelValue: act.text,
                                "onUpdate:modelValue": $event => ((act.text) = $event),
                                placeholder: "要发送的文本",
                                style: {"width":"200px"}
                              }, null, 8, ["modelValue", "onUpdate:modelValue"]))
                            : (act.type === 'click_keyboard')
                              ? (openBlock(), createBlock(_component_el_input, {
                                  key: 1,
                                  modelValue: act.text,
                                  "onUpdate:modelValue": $event => ((act.text) = $event),
                                  placeholder: "要点击的按钮文本",
                                  style: {"width":"200px"}
                                }, null, 8, ["modelValue", "onUpdate:modelValue"]))
                              : (act.type === 'send_dice')
                                ? (openBlock(), createBlock(_component_el_select, {
                                    key: 2,
                                    modelValue: act.dice,
                                    "onUpdate:modelValue": $event => ((act.dice) = $event),
                                    style: {"width":"120px"}
                                  }, {
                                    default: withCtx(() => [
                                      (openBlock(), createElementBlock(Fragment, null, renderList(DICE_OPTIONS, (d) => {
                                        return createVNode(_component_el_option, {
                                          key: d,
                                          label: d,
                                          value: d
                                        }, null, 8, ["label", "value"])
                                      }), 64))
                                    ]),
                                    _: 1
                                  }, 8, ["modelValue", "onUpdate:modelValue"]))
                                : (act.type === 'choose_option_by_image')
                                  ? (openBlock(), createElementBlock("span", _hoisted_18, "自动识别图片并选择选项（需配置大模型）"))
                                  : (act.type === 'reply_calculation')
                                    ? (openBlock(), createElementBlock("span", _hoisted_19, "自动回复消息中的计算题（需配置大模型）"))
                                    : createCommentVNode("", true)
                        ]),
                        createVNode(_component_el_button, {
                          type: "danger",
                          plain: "",
                          size: "small",
                          onClick: $event => (removeAction(ai))
                        }, {
                          default: withCtx(() => [...(_cache[26] || (_cache[26] = [
                            createTextVNode(" 删除 ", -1)
                          ]))]),
                          _: 1
                        }, 8, ["onClick"])
                      ]))
                    }), 128)),
                    createVNode(_component_el_button, {
                      class: "add-action",
                      onClick: addAction
                    }, {
                      default: withCtx(() => [...(_cache[27] || (_cache[27] = [
                        createTextVNode("添加动作", -1)
                      ]))]),
                      _: 1
                    })
                  ]),
                  _cache[28] || (_cache[28] = createBaseVNode("div", { class: "hint" }, "第一个动作必须是「发送普通文本」或「发送 Dice emoji」", -1))
                ]),
                _: 1
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      }, 8, ["modelValue", "title"])
    ]),
    _: 1
  }, 8, ["model-value"]))
}
}

};
const SignerWizard = /*#__PURE__*/_export_sfc(_sfc_main$1, [['__scopeId',"data-v-d43ccafe"]]);

const _hoisted_1 = { class: "ts-intro" };
const _hoisted_2 = { class: "config-tab-intro" };


const _sfc_main = {
  __name: 'Configs',
  setup(__props) {

const route = useRoute();
const router = useRouter();
const activeTab = ref('signer');
const wizardVisible = ref(false);

const TAB_KINDS = ['signer', 'automation', 'llm'];

watch(
  () => route.query.kind,
  (kind) => {
    if (TAB_KINDS.includes(kind)) activeTab.value = kind;
  },
  { immediate: true }
);

const prefillTitle = computed(() => route.query.title || '');
const prefillUsername = computed(() => route.query.username || '');

function prefillChat(kind) {
  return route.query.kind === kind ? route.query.chat || '' : ''
}

function clearPrefill() {
  if (route.query.chat) router.replace({ query: {} });
}

return (_ctx, _cache) => {
  const _component_el_tag = resolveComponent("el-tag");
  const _component_el_button = resolveComponent("el-button");
  const _component_el_tab_pane = resolveComponent("el-tab-pane");
  const _component_el_tabs = resolveComponent("el-tabs");

  return (openBlock(), createElementBlock(Fragment, null, [
    createBaseVNode("div", null, [
      createBaseVNode("div", _hoisted_1, [
        _cache[4] || (_cache[4] = createBaseVNode("div", null, [
          createBaseVNode("span", { class: "ts-section-label" }, "配置中心"),
          createBaseVNode("p", { class: "ts-section-caption" }, "选择配置类型，开始编辑 JSON、运行模板或维护模型连接。")
        ], -1)),
        createVNode(_component_el_tag, {
          type: "info",
          effect: "light",
          round: ""
        }, {
          default: withCtx(() => [...(_cache[3] || (_cache[3] = [
            createTextVNode("JSON 配置", -1)
          ]))]),
          _: 1
        })
      ]),
      createVNode(_component_el_tabs, {
        modelValue: activeTab.value,
        "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((activeTab).value = $event)),
        class: "config-tabs"
      }, {
        default: withCtx(() => [
          createVNode(_component_el_tab_pane, {
            label: "Signer",
            name: "signer"
          }, {
            default: withCtx(() => [
              createBaseVNode("div", _hoisted_2, [
                createVNode(_component_el_button, {
                  type: "primary",
                  plain: "",
                  size: "small",
                  onClick: _cache[0] || (_cache[0] = $event => (wizardVisible.value = true))
                }, {
                  default: withCtx(() => [...(_cache[5] || (_cache[5] = [
                    createTextVNode(" 交互式配置向导 ", -1)
                  ]))]),
                  _: 1
                }),
                _cache[6] || (_cache[6] = createBaseVNode("span", { class: "hint" }, "通过分步表单快速创建签到配置", -1))
              ]),
              createVNode(ConfigEditor, {
                kind: "signer",
                "prefill-chat": prefillChat('signer'),
                "prefill-title": prefillTitle.value,
                "prefill-username": prefillUsername.value,
                onApplied: clearPrefill
              }, null, 8, ["prefill-chat", "prefill-title", "prefill-username"])
            ]),
            _: 1
          }),
          createVNode(_component_el_tab_pane, {
            label: "Automation",
            name: "automation"
          }, {
            default: withCtx(() => [
              createVNode(ConfigEditor, {
                kind: "automation",
                "prefill-chat": prefillChat('automation'),
                "prefill-title": prefillTitle.value,
                "prefill-username": prefillUsername.value,
                onApplied: clearPrefill
              }, null, 8, ["prefill-chat", "prefill-title", "prefill-username"])
            ]),
            _: 1
          }),
          createVNode(_component_el_tab_pane, {
            label: "大模型",
            name: "llm"
          }, {
            default: withCtx(() => [
              createVNode(LlmConfig)
            ]),
            _: 1
          })
        ]),
        _: 1
      }, 8, ["modelValue"])
    ]),
    createVNode(SignerWizard, {
      visible: wizardVisible.value,
      "onUpdate:visible": _cache[2] || (_cache[2] = $event => ((wizardVisible).value = $event))
    }, null, 8, ["visible"])
  ], 64))
}
}

};
const Configs = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-c01cc217"]]);

export { Configs as default };
