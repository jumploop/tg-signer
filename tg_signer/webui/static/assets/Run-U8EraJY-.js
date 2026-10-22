import { _ as _export_sfc, m as watch, o as onMounted, k as onUnmounted, n as createBlock, w as withCtx, q as api, r as resolveComponent, g as ref, h as openBlock, b as createBaseVNode, d as createVNode, f as createTextVNode, J as toDisplayString, a as createElementBlock, P as Fragment, Q as renderList, i as unref, V as info_filled_default, L as computed, E as ElMessage, j as errMsg } from './index-COQHa1_g.js';

const _hoisted_1 = { class: "ts-intro" };
const _hoisted_2 = { class: "selection-count" };
const _hoisted_3 = { class: "ts-callout run-note" };
const _hoisted_4 = {
  key: 1,
  class: "hint"
};


const _sfc_main = {
  __name: 'Run',
  setup(__props) {

const kind = ref('signer');
const account = ref('');
const accounts = ref([]);
const taskNames = ref([]);
const selectedTasks = ref([]);
const loadingTasks = ref(false);
const tasks = ref({});
const taskNamesByKey = ref({});
const starting = ref(false);
const stopping = ref(false);
let timer = null;

const KIND_LABELS = {
  signer: 'Signer（签到）',
  automation: 'Automation（自动化）',
};

const rows = computed(() =>
  Object.entries(tasks.value).map(([key, running]) => {
    const [k, acc] = key.split(':');
    return {
      key,
      kind: k,
      account: acc || key,
      running,
      tasks: taskNamesByKey.value[key] || [],
    }
  })
);
const runningCount = computed(() => rows.value.filter((row) => row.running).length);

const allSelected = computed(
  () => taskNames.value.length > 0 && selectedTasks.value.length === taskNames.value.length
);
const someSelected = computed(
  () => selectedTasks.value.length > 0 && selectedTasks.value.length < taskNames.value.length
);

function kindLabel(k) {
  return KIND_LABELS[k] || k
}

async function refresh() {
  try {
    const [runData, accData] = await Promise.all([
      api.get('/api/run'),
      api.get('/api/accounts'),
    ]);
    tasks.value = runData.data.tasks || {};
    taskNamesByKey.value = runData.data.task_names || {};
    accounts.value = accData.data;
  } catch (error) {
    /* 轮询期间忽略瞬时错误 */
  }
}

function toggleSelectAll(checked) {
  selectedTasks.value = checked ? [...taskNames.value] : [];
}

async function loadTasks() {
  loadingTasks.value = true;
  try {
    const { data } = await api.get(`/api/configs/${kind.value}`);
    taskNames.value = data.names || [];
  } catch (error) {
    taskNames.value = [];
  } finally {
    loadingTasks.value = false;
  }
}

watch(kind, () => {
  selectedTasks.value = [];
  loadTasks();
});

async function postRun(path, payload, onSuccess = showMsg) {
  try {
    const { data } = await api.post(path, payload);
    onSuccess(data);
    refresh();
  } catch (error) {
    ElMessage.error(errMsg(error));
  }
}

async function start() {
  if (!account.value) {
    ElMessage.warning('请选择账号');
    return
  }
  if (!selectedTasks.value.length) {
    ElMessage.warning('请选择至少一个任务');
    return
  }
  starting.value = true;
  await postRun(
    '/api/run/start',
    {
      kind: kind.value,
      tasks: selectedTasks.value,
      account: account.value,
    },
    (data) => {
      showMsg(data);
      if (data.ok) selectedTasks.value = [];
    }
  );
  starting.value = false;
}

async function stop() {
  if (!account.value) {
    ElMessage.warning('请选择账号');
    return
  }
  stopping.value = true;
  await postRun('/api/run/stop', {
    kind: kind.value,
    account: account.value,
  });
  stopping.value = false;
}

async function stopRow(row) {
  await postRun('/api/run/stop', {
    kind: row.kind,
    account: row.account,
  });
}

async function shutdownAll() {
  await postRun('/api/run/shutdown', undefined, (data) => {
    ElMessage.success('已停止 ' + data.stopped.length + ' 个进程');
  });
}

function showMsg(data) {
  if (data.ok) {
    ElMessage.success(data.message);
  } else {
    ElMessage.warning(data.message);
  }
}

onMounted(() => {
  refresh();
  loadTasks();
  timer = setInterval(refresh, 5000);
});
onUnmounted(() => clearInterval(timer));

return (_ctx, _cache) => {
  const _component_el_tag = resolveComponent("el-tag");
  const _component_el_option = resolveComponent("el-option");
  const _component_el_select = resolveComponent("el-select");
  const _component_el_form_item = resolveComponent("el-form-item");
  const _component_el_checkbox = resolveComponent("el-checkbox");
  const _component_el_button = resolveComponent("el-button");
  const _component_el_form = resolveComponent("el-form");
  const _component_el_icon = resolveComponent("el-icon");
  const _component_el_table_column = resolveComponent("el-table-column");
  const _component_el_empty = resolveComponent("el-empty");
  const _component_el_table = resolveComponent("el-table");
  const _component_el_card = resolveComponent("el-card");

  return (openBlock(), createBlock(_component_el_card, { shadow: "never" }, {
    default: withCtx(() => [
      createBaseVNode("div", _hoisted_1, [
        _cache[3] || (_cache[3] = createBaseVNode("div", null, [
          createBaseVNode("span", { class: "ts-section-label" }, "启动控制"),
          createBaseVNode("p", { class: "ts-section-caption" }, "选择账号和任务范围，集中启动或停止后台进程。")
        ], -1)),
        createVNode(_component_el_tag, {
          type: runningCount.value ? 'success' : 'info',
          effect: "light",
          round: ""
        }, {
          default: withCtx(() => [
            createTextVNode(toDisplayString(runningCount.value ? `${runningCount.value} 个进程运行中` : '当前无运行进程'), 1)
          ]),
          _: 1
        }, 8, ["type"])
      ]),
      createVNode(_component_el_form, {
        inline: "",
        class: "run-form"
      }, {
        default: withCtx(() => [
          createVNode(_component_el_form_item, { label: "类型" }, {
            default: withCtx(() => [
              createVNode(_component_el_select, {
                modelValue: kind.value,
                "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((kind).value = $event)),
                class: "kind-select"
              }, {
                default: withCtx(() => [
                  createVNode(_component_el_option, {
                    label: "Signer（签到）",
                    value: "signer"
                  }),
                  createVNode(_component_el_option, {
                    label: "Automation（自动化）",
                    value: "automation"
                  })
                ]),
                _: 1
              }, 8, ["modelValue"])
            ]),
            _: 1
          }),
          createVNode(_component_el_form_item, { label: "账号" }, {
            default: withCtx(() => [
              createVNode(_component_el_select, {
                modelValue: account.value,
                "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((account).value = $event)),
                placeholder: "选择账号",
                class: "account-select",
                filterable: ""
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
              }, 8, ["modelValue"])
            ]),
            _: 1
          }),
          createVNode(_component_el_form_item, { label: "任务" }, {
            default: withCtx(() => [
              createVNode(_component_el_checkbox, {
                "model-value": allSelected.value,
                indeterminate: someSelected.value,
                disabled: !taskNames.value.length,
                onChange: toggleSelectAll
              }, {
                default: withCtx(() => [...(_cache[4] || (_cache[4] = [
                  createTextVNode(" 全选 ", -1)
                ]))]),
                _: 1
              }, 8, ["model-value", "indeterminate", "disabled"]),
              createVNode(_component_el_select, {
                modelValue: selectedTasks.value,
                "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((selectedTasks).value = $event)),
                multiple: "",
                filterable: "",
                "collapse-tags": "",
                "collapse-tags-tooltip": "",
                placeholder: "从配置列表选择任务（可多选）",
                class: "task-select",
                loading: loadingTasks.value
              }, {
                default: withCtx(() => [
                  (openBlock(true), createElementBlock(Fragment, null, renderList(taskNames.value, (name) => {
                    return (openBlock(), createBlock(_component_el_option, {
                      key: name,
                      label: name,
                      value: name
                    }, null, 8, ["label", "value"]))
                  }), 128))
                ]),
                _: 1
              }, 8, ["modelValue", "loading"]),
              createBaseVNode("span", _hoisted_2, " 已选择 " + toDisplayString(selectedTasks.value.length) + " 个任务 ", 1)
            ]),
            _: 1
          }),
          createVNode(_component_el_form_item, null, {
            default: withCtx(() => [
              createVNode(_component_el_button, {
                type: "primary",
                loading: starting.value,
                onClick: start
              }, {
                default: withCtx(() => [...(_cache[5] || (_cache[5] = [
                  createTextVNode("启动", -1)
                ]))]),
                _: 1
              }, 8, ["loading"]),
              createVNode(_component_el_button, {
                loading: stopping.value,
                onClick: stop
              }, {
                default: withCtx(() => [...(_cache[6] || (_cache[6] = [
                  createTextVNode("停止当前", -1)
                ]))]),
                _: 1
              }, 8, ["loading"]),
              createVNode(_component_el_button, {
                type: "danger",
                plain: "",
                onClick: shutdownAll
              }, {
                default: withCtx(() => [...(_cache[7] || (_cache[7] = [
                  createTextVNode("全部停止", -1)
                ]))]),
                _: 1
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      }),
      createBaseVNode("div", _hoisted_3, [
        createVNode(_component_el_icon, null, {
          default: withCtx(() => [
            createVNode(unref(info_filled_default))
          ]),
          _: 1
        }),
        _cache[8] || (_cache[8] = createBaseVNode("span", null, " 同一账号同类型的多个任务会合并到一个子进程运行（共享 Client，避免 SQLite session 文件锁冲突），请一次性选择全部任务后启动；日志写入 <workdir>/logs/，可在「日志」页查看。 ", -1))
      ]),
      _cache[10] || (_cache[10] = createBaseVNode("div", { class: "ts-table-heading" }, [
        createBaseVNode("span", null, "运行中的进程"),
        createBaseVNode("span", { class: "ts-table-heading__meta" }, "每 5 秒自动刷新")
      ], -1)),
      createVNode(_component_el_table, { data: rows.value }, {
        empty: withCtx(() => [
          createVNode(_component_el_empty, {
            description: "暂无运行中的进程",
            "image-size": 60
          })
        ]),
        default: withCtx(() => [
          createVNode(_component_el_table_column, {
            label: "类型",
            width: "180"
          }, {
            default: withCtx(({ row }) => [
              createTextVNode(toDisplayString(kindLabel(row.kind)), 1)
            ]),
            _: 1
          }),
          createVNode(_component_el_table_column, {
            prop: "account",
            label: "账号",
            width: "200"
          }),
          createVNode(_component_el_table_column, {
            label: "任务",
            "min-width": "220"
          }, {
            default: withCtx(({ row }) => [
              (row.tasks.length)
                ? (openBlock(true), createElementBlock(Fragment, { key: 0 }, renderList(row.tasks, (name) => {
                    return (openBlock(), createBlock(_component_el_tag, {
                      key: name,
                      size: "small",
                      type: "info",
                      class: "task-tag"
                    }, {
                      default: withCtx(() => [
                        createTextVNode(toDisplayString(name), 1)
                      ]),
                      _: 2
                    }, 1024))
                  }), 128))
                : (openBlock(), createElementBlock("span", _hoisted_4, "-"))
            ]),
            _: 1
          }),
          createVNode(_component_el_table_column, {
            label: "状态",
            width: "120"
          }, {
            default: withCtx(({ row }) => [
              createVNode(_component_el_tag, {
                type: row.running ? 'success' : 'info'
              }, {
                default: withCtx(() => [
                  createTextVNode(toDisplayString(row.running ? '运行中' : '已停止'), 1)
                ]),
                _: 2
              }, 1032, ["type"])
            ]),
            _: 1
          }),
          createVNode(_component_el_table_column, {
            label: "操作",
            width: "140"
          }, {
            default: withCtx(({ row }) => [
              createVNode(_component_el_button, {
                size: "small",
                disabled: !row.running,
                onClick: $event => (stopRow(row))
              }, {
                default: withCtx(() => [...(_cache[9] || (_cache[9] = [
                  createTextVNode(" 停止 ", -1)
                ]))]),
                _: 1
              }, 8, ["disabled", "onClick"])
            ]),
            _: 1
          })
        ]),
        _: 1
      }, 8, ["data"])
    ]),
    _: 1
  }))
}
}

};
const Run = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-e2a9a108"]]);

export { Run as default };
