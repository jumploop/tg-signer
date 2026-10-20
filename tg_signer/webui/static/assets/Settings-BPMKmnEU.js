import { _ as _export_sfc, o as onMounted, n as createBlock, w as withCtx, q as api, E as ElMessage, j as errMsg, r as resolveComponent, g as ref, h as openBlock, b as createBaseVNode, d as createVNode, f as createTextVNode } from './index-vbFgu0lp.js';

const _sfc_main = {
  __name: 'Settings',
  setup(__props) {

const workdir = ref('');
const logPath = ref('');
const loading = ref(false);
const saving = ref(false);

async function refresh() {
  loading.value = true;
  try {
    const { data } = await api.get('/api/state');
    workdir.value = data.workdir;
    logPath.value = data.log_path;
  } catch (error) {
    ElMessage.error('设置加载失败: ' + errMsg(error));
  } finally {
    loading.value = false;
  }
}

async function apply() {
  if (!workdir.value.trim()) {
    ElMessage.warning('工作目录不能为空');
    return
  }
  saving.value = true;
  try {
    const { data } = await api.post('/api/state', {
      workdir: workdir.value.trim(),
    });
    workdir.value = data.workdir;
    logPath.value = data.log_path;
    ElMessage.success('已切换工作目录');
  } catch (error) {
    ElMessage.error(errMsg(error));
    // 切换失败时后端并未生效，输入框里那个路径是无效值。不回滚的话用户看到的
    // 就是一个「填了但没用上」的目录，正是「显示的路径和实际不一致」的来源。
    await refresh();
  } finally {
    saving.value = false;
  }
}

onMounted(refresh);

return (_ctx, _cache) => {
  const _component_el_alert = resolveComponent("el-alert");
  const _component_el_input = resolveComponent("el-input");
  const _component_el_form_item = resolveComponent("el-form-item");
  const _component_el_button = resolveComponent("el-button");
  const _component_el_form = resolveComponent("el-form");
  const _component_el_card = resolveComponent("el-card");

  return (openBlock(), createBlock(_component_el_card, {
    shadow: "never",
    class: "settings-card"
  }, {
    default: withCtx(() => [
      _cache[3] || (_cache[3] = createBaseVNode("div", { class: "settings-intro" }, [
        createBaseVNode("span", { class: "ts-section-label" }, "工作区设置"),
        createBaseVNode("p", { class: "ts-section-caption" }, "调整 WebUI 使用的本地目录，配置和运行记录会跟随此目录读取。")
      ], -1)),
      createVNode(_component_el_alert, {
        title: "切换工作目录不会自动迁移已有数据",
        description: "应用前请确认目标目录存在，并了解其中的配置、日志和签到记录会重新从该目录读取。",
        type: "info",
        "show-icon": "",
        closable: false,
        class: "settings-alert"
      }),
      createVNode(_component_el_form, {
        "label-width": "120px",
        class: "settings-form"
      }, {
        default: withCtx(() => [
          createVNode(_component_el_form_item, { label: "工作目录" }, {
            default: withCtx(() => [
              createVNode(_component_el_input, {
                modelValue: workdir.value,
                "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((workdir).value = $event))
              }, null, 8, ["modelValue"])
            ]),
            _: 1
          }),
          createVNode(_component_el_form_item, { label: "主日志路径" }, {
            default: withCtx(() => [
              createVNode(_component_el_input, {
                "model-value": logPath.value,
                readonly: ""
              }, null, 8, ["model-value"])
            ]),
            _: 1
          }),
          createVNode(_component_el_form_item, null, {
            default: withCtx(() => [
              createVNode(_component_el_button, {
                type: "primary",
                loading: saving.value,
                onClick: apply
              }, {
                default: withCtx(() => [...(_cache[1] || (_cache[1] = [
                  createTextVNode("应用并刷新", -1)
                ]))]),
                _: 1
              }, 8, ["loading"]),
              createVNode(_component_el_button, {
                loading: loading.value,
                onClick: refresh
              }, {
                default: withCtx(() => [...(_cache[2] || (_cache[2] = [
                  createTextVNode("重新加载", -1)
                ]))]),
                _: 1
              }, 8, ["loading"])
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
const Settings = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-b24d0b9c"]]);

export { Settings as default };
