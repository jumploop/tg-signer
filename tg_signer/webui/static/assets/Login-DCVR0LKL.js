import { _ as _export_sfc, o as onMounted, c as checkAuth, a as createElementBlock, b as createBaseVNode, d as createVNode, w as withCtx, e as withKeys, f as createTextVNode, u as useRouter, r as resolveComponent, g as ref, h as openBlock, i as unref, p as promotion_default, l as login, j as errMsg } from './index-DpF7b0Gh.js';
import { E as ElMessage } from './index-C5oA3b00.js';

const _hoisted_1 = { class: "login-wrap" };
const _hoisted_2 = { class: "login-panel" };
const _hoisted_3 = { class: "login-brand" };
const _hoisted_4 = { class: "brand-badge" };


const _sfc_main = {
  __name: 'Login',
  setup(__props) {

const router = useRouter();
const code = ref('');
const loading = ref(false);

async function submit() {
  if (loading.value) return
  if (!code.value) {
    ElMessage.warning('请输入授权码');
    return
  }
  loading.value = true;
  try {
    const data = await login(code.value);
    if (data.ok) {
      ElMessage.success('登录成功');
      router.push('/');
    } else {
      ElMessage.error(data.message || '授权码错误');
    }
  } catch (error) {
    ElMessage.error(errMsg(error) || '登录失败');
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  try {
    const status = await checkAuth();
    if (!status.required) {
      ElMessage.info('本服务未启用授权码，无需登录');
      router.push('/');
    }
  } catch (error) {
    /* 忽略瞬时错误 */
  }
});

return (_ctx, _cache) => {
  const _component_el_icon = resolveComponent("el-icon");
  const _component_el_input = resolveComponent("el-input");
  const _component_el_button = resolveComponent("el-button");

  return (openBlock(), createElementBlock("div", _hoisted_1, [
    createBaseVNode("div", _hoisted_2, [
      createBaseVNode("div", _hoisted_3, [
        createBaseVNode("span", _hoisted_4, [
          createVNode(_component_el_icon, null, {
            default: withCtx(() => [
              createVNode(unref(promotion_default))
            ]),
            _: 1
          })
        ]),
        _cache[1] || (_cache[1] = createBaseVNode("span", { class: "login-eyebrow" }, "PRIVATE CONSOLE", -1)),
        _cache[2] || (_cache[2] = createBaseVNode("h1", null, "tg-signer", -1)),
        _cache[3] || (_cache[3] = createBaseVNode("p", null, "安全进入你的 Telegram 自动化工作台", -1))
      ]),
      createVNode(_component_el_input, {
        modelValue: code.value,
        "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((code).value = $event)),
        type: "password",
        "show-password": "",
        placeholder: "授权码",
        size: "large",
        "aria-label": "授权码",
        onKeyup: withKeys(submit, ["enter"])
      }, null, 8, ["modelValue"]),
      createVNode(_component_el_button, {
        type: "primary",
        size: "large",
        class: "login-btn",
        loading: loading.value,
        onClick: submit
      }, {
        default: withCtx(() => [...(_cache[4] || (_cache[4] = [
          createTextVNode(" 登录 ", -1)
        ]))]),
        _: 1
      }, 8, ["loading"]),
      _cache[5] || (_cache[5] = createBaseVNode("p", { class: "login-hint" }, [
        createTextVNode(" 本服务启用了授权码，请输入环境变量 "),
        createBaseVNode("code", null, "TG_SIGNER_GUI_AUTHCODE"),
        createTextVNode(" 对应的授权码 ")
      ], -1))
    ])
  ]))
}
}

};
const Login = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-bba596a4"]]);

export { Login as default };
