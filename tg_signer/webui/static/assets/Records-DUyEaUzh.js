import { _ as _export_sfc, o as onMounted, n as createBlock, w as withCtx, q as api, R as asArray, E as ElMessage, j as errMsg, r as resolveComponent, g as ref, N as resolveDirective, h as openBlock, b as createBaseVNode, d as createVNode, f as createTextVNode, J as toDisplayString, O as withDirectives, a as createElementBlock, P as Fragment, Q as renderList, L as computed } from './index-Ceed42FL.js';

const _hoisted_1 = { class: "ts-intro" };
const _hoisted_2 = { class: "record-metrics" };
const _hoisted_3 = { class: "record-metric" };
const _hoisted_4 = { class: "ts-metric-value" };
const _hoisted_5 = { class: "record-metric" };
const _hoisted_6 = { class: "ts-metric-value" };
const _hoisted_7 = { class: "record-filter" };
const _hoisted_8 = { class: "ts-table-heading" };
const _hoisted_9 = { class: "ts-table-heading__meta" };
const _hoisted_10 = { key: 1 };


const _sfc_main = {
  __name: 'Records',
  setup(__props) {

const records = ref([]);
const filterText = ref('');
const loading = ref(false);
const filtered = computed(() =>
  records.value.filter((record) => !filterText.value || record.task.includes(filterText.value))
);
const totalRecords = computed(() =>
  records.value.reduce((sum, record) => sum + record.records.length, 0)
);

async function refresh() {
  loading.value = true;
  try {
    const { data } = await api.get('/api/records');
    records.value = asArray(data);
  } catch (error) {
    ElMessage.error('签到记录加载失败: ' + errMsg(error));
  } finally {
    loading.value = false;
  }
}

onMounted(refresh);

return (_ctx, _cache) => {
  const _component_el_button = resolveComponent("el-button");
  const _component_el_input = resolveComponent("el-input");
  const _component_el_table_column = resolveComponent("el-table-column");
  const _component_el_empty = resolveComponent("el-empty");
  const _component_el_table = resolveComponent("el-table");
  const _component_el_card = resolveComponent("el-card");
  const _directive_loading = resolveDirective("loading");

  return (openBlock(), createBlock(_component_el_card, { shadow: "never" }, {
    default: withCtx(() => [
      createBaseVNode("div", _hoisted_1, [
        _cache[2] || (_cache[2] = createBaseVNode("div", null, [
          createBaseVNode("span", { class: "ts-section-label" }, "签到历史"),
          createBaseVNode("p", { class: "ts-section-caption" }, "按任务查看签到日期、执行时间和历史记录数量。")
        ], -1)),
        createVNode(_component_el_button, {
          loading: loading.value,
          onClick: refresh
        }, {
          default: withCtx(() => [...(_cache[1] || (_cache[1] = [
            createTextVNode("刷新", -1)
          ]))]),
          _: 1
        }, 8, ["loading"])
      ]),
      createBaseVNode("div", _hoisted_2, [
        createBaseVNode("div", _hoisted_3, [
          createBaseVNode("span", _hoisted_4, toDisplayString(records.value.length), 1),
          _cache[3] || (_cache[3] = createBaseVNode("span", { class: "ts-metric-label" }, "任务数", -1))
        ]),
        createBaseVNode("div", _hoisted_5, [
          createBaseVNode("span", _hoisted_6, toDisplayString(totalRecords.value), 1),
          _cache[4] || (_cache[4] = createBaseVNode("span", { class: "ts-metric-label" }, "签到记录", -1))
        ]),
        createBaseVNode("div", _hoisted_7, [
          createVNode(_component_el_input, {
            modelValue: filterText.value,
            "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((filterText).value = $event)),
            placeholder: "按任务名过滤",
            clearable: ""
          }, null, 8, ["modelValue"])
        ])
      ]),
      createBaseVNode("div", _hoisted_8, [
        _cache[5] || (_cache[5] = createBaseVNode("span", null, "任务记录", -1)),
        createBaseVNode("span", _hoisted_9, "当前显示 " + toDisplayString(filtered.value.length) + " 个任务", 1)
      ]),
      withDirectives((openBlock(), createBlock(_component_el_table, { data: filtered.value }, {
        empty: withCtx(() => [
          createVNode(_component_el_empty, {
            description: "暂无签到记录，运行签到任务后在此查看",
            "image-size": 60
          })
        ]),
        default: withCtx(() => [
          createVNode(_component_el_table_column, {
            prop: "task",
            label: "任务"
          }),
          createVNode(_component_el_table_column, {
            prop: "user_id",
            label: "User ID",
            width: "140"
          }),
          createVNode(_component_el_table_column, {
            label: "记录数",
            width: "100"
          }, {
            default: withCtx(({ row }) => [
              createTextVNode(toDisplayString(row.records.length), 1)
            ]),
            _: 1
          }),
          createVNode(_component_el_table_column, {
            label: "最近签到",
            width: "200"
          }, {
            default: withCtx(({ row }) => [
              (row.records.length)
                ? (openBlock(), createElementBlock(Fragment, { key: 0 }, [
                    createTextVNode(toDisplayString(row.records[0].sign_date) + " " + toDisplayString(row.records[0].signed_at), 1)
                  ], 64))
                : (openBlock(), createElementBlock("span", _hoisted_10, "-"))
            ]),
            _: 1
          }),
          createVNode(_component_el_table_column, {
            label: "记录",
            "min-width": "280"
          }, {
            default: withCtx(({ row }) => [
              (openBlock(true), createElementBlock(Fragment, null, renderList(row.records, (record) => {
                return (openBlock(), createElementBlock("div", {
                  key: record.sign_date,
                  class: "rec"
                }, [
                  createBaseVNode("code", null, toDisplayString(record.sign_date), 1),
                  createTextVNode(" → " + toDisplayString(record.signed_at), 1)
                ]))
              }), 128))
            ]),
            _: 1
          })
        ]),
        _: 1
      }, 8, ["data"])), [
        [_directive_loading, loading.value]
      ])
    ]),
    _: 1
  }))
}
}

};
const Records = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-a898f5b3"]]);

export { Records as default };
