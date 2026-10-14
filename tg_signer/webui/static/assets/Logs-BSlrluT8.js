import { _ as _export_sfc, m as watch, o as onMounted, k as onUnmounted, n as createBlock, w as withCtx, q as api, R as asArray, g as ref, r as resolveComponent, h as openBlock, b as createBaseVNode, d as createVNode, f as createTextVNode, J as toDisplayString, a as createElementBlock, P as Fragment, Q as renderList, X as copyText, E as ElMessage } from './index-1SY902xg.js';

const _hoisted_1 = { class: "ts-intro" };
const _hoisted_2 = { class: "logs-controls" };


const _sfc_main = {
  __name: 'Logs',
  setup(__props) {

const files = ref([]);
const selected = ref('');
const limit = ref(200);
const autoRefresh = ref(false);
const content = ref('');
let timer = null;

// 展示相对 logs/ 目录的路径（如 signer-demo/tg-signer.log）而不是纯文件名：
// 子目录日志和主日志都叫 tg-signer.log，只显示文件名分不清谁是谁。
function fileName(fullPath) {
  const parts = String(fullPath).split(/[\\/]/).filter(Boolean);
  const idx = parts.lastIndexOf('logs');
  const tail = idx >= 0 ? parts.slice(idx + 1) : parts.slice(-1);
  return tail.join('/') || fullPath
}

async function refreshFiles() {
  try {
    const { data } = await api.get('/api/logs/files');
    files.value = asArray(data.files);
    if (!selected.value && files.value.length) {
      // 后端已把「非空 + 最新」排在最前，第一个就是最值得先看的日志。
      selected.value = files.value[0];
    }
  } catch {
    files.value = [];
  }
}

async function refresh() {
  const params = { limit: limit.value };
  if (selected.value) params.path = selected.value;
  try {
    const { data } = await api.get('/api/logs', { params });
    content.value = asArray(data.lines).join('\n');
  } catch {
    content.value = '';
  }
}

async function copyLog() {
  try {
    await copyText(content.value);
    ElMessage.success('已复制日志');
  } catch (error) {
    ElMessage.warning('复制失败，请手动选择复制');
  }
}

watch([selected, limit], refresh);
watch(autoRefresh, (value) => {
  clearInterval(timer);
  if (value) timer = setInterval(refresh, 5000);
});
onMounted(() => {
  // 串行：先拿文件列表。选中项一旦被赋值，watch([selected]) 会自己去取内容；
  // 只有在没有任何日志文件时才需要这里兜底再取一次。
  refreshFiles().then(() => {
    if (!selected.value) refresh();
  });
});
onUnmounted(() => clearInterval(timer));

return (_ctx, _cache) => {
  const _component_el_tag = resolveComponent("el-tag");
  const _component_el_option = resolveComponent("el-option");
  const _component_el_select = resolveComponent("el-select");
  const _component_el_input_number = resolveComponent("el-input-number");
  const _component_el_switch = resolveComponent("el-switch");
  const _component_el_button = resolveComponent("el-button");
  const _component_el_input = resolveComponent("el-input");
  const _component_el_card = resolveComponent("el-card");

  return (openBlock(), createBlock(_component_el_card, {
    shadow: "never",
    class: "logs-card"
  }, {
    default: withCtx(() => [
      createBaseVNode("div", _hoisted_1, [
        _cache[3] || (_cache[3] = createBaseVNode("div", null, [
          createBaseVNode("span", { class: "ts-section-label" }, "日志查看器"),
          createBaseVNode("p", { class: "ts-section-caption" }, "按文件查看最近运行输出，支持自动刷新和复制当前内容。")
        ], -1)),
        createVNode(_component_el_tag, {
          type: autoRefresh.value ? 'success' : 'info',
          effect: "light",
          round: ""
        }, {
          default: withCtx(() => [
            createTextVNode(toDisplayString(autoRefresh.value ? '自动刷新已开启' : '手动刷新'), 1)
          ]),
          _: 1
        }, 8, ["type"])
      ]),
      createBaseVNode("div", _hoisted_2, [
        createVNode(_component_el_select, {
          modelValue: selected.value,
          "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((selected).value = $event)),
          placeholder: "选择日志文件",
          class: "log-file-select"
        }, {
          default: withCtx(() => [
            (openBlock(true), createElementBlock(Fragment, null, renderList(files.value, (file) => {
              return (openBlock(), createBlock(_component_el_option, {
                key: file,
                label: fileName(file),
                value: file
              }, null, 8, ["label", "value"]))
            }), 128))
          ]),
          _: 1
        }, 8, ["modelValue"]),
        createVNode(_component_el_input_number, {
          modelValue: limit.value,
          "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((limit).value = $event)),
          min: 50,
          max: 2000,
          step: 50
        }, null, 8, ["modelValue"]),
        createVNode(_component_el_switch, {
          modelValue: autoRefresh.value,
          "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((autoRefresh).value = $event)),
          "active-text": "自动刷新(5s)"
        }, null, 8, ["modelValue"]),
        createVNode(_component_el_button, { onClick: copyLog }, {
          default: withCtx(() => [...(_cache[4] || (_cache[4] = [
            createTextVNode("复制日志", -1)
          ]))]),
          _: 1
        }),
        createVNode(_component_el_button, { onClick: refresh }, {
          default: withCtx(() => [...(_cache[5] || (_cache[5] = [
            createTextVNode("刷新", -1)
          ]))]),
          _: 1
        })
      ]),
      createVNode(_component_el_input, {
        type: "textarea",
        rows: 22,
        "model-value": content.value,
        readonly: "",
        class: "logbox mono",
        placeholder: files.value.length ? '暂无日志内容' : '当前工作目录还没有日志文件',
        "aria-label": "日志内容"
      }, null, 8, ["model-value", "placeholder"])
    ]),
    _: 1
  }))
}
}

};
const Logs = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-02d84368"]]);

export { Logs as default };
