(global["webpackJsonp"] = global["webpackJsonp"] || []).push([["pages/login/openid"],{

/***/ 100:
/*!***************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************!*\
  !*** ./node_modules/@dcloudio/vue-cli-plugin-uni/packages/vue-loader/lib/loaders/templateLoader.js??vue-loader-options!./node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-preprocess-loader??ref--15-0!./node_modules/@dcloudio/webpack-uni-mp-loader/lib/template.js!./node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-uni-app-loader/page-meta.js!./node_modules/@dcloudio/vue-cli-plugin-uni/packages/vue-loader/lib??vue-loader-options!./node_modules/@dcloudio/webpack-uni-mp-loader/lib/style.js!./pages/login/openid.vue?vue&type=template&id=4c578c78& ***!
  \***************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************/
/*! exports provided: render, staticRenderFns, recyclableRender, components */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "render", function() { return render; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "staticRenderFns", function() { return staticRenderFns; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "recyclableRender", function() { return recyclableRender; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "components", function() { return components; });
var render = function () {
  var _vm = this
  var _h = _vm.$createElement
  var _c = _vm._self._c || _h
}
var staticRenderFns = []
render._withStripped = true

var recyclableRender = typeof recyclableRender === 'undefined' ? null : recyclableRender
var components = typeof components === 'undefined' ? {} : components


/***/ }),

/***/ 101:
/*!*********************************************************!*\
  !*** ./pages/login/openid.vue?vue&type=script&lang=js& ***!
  \*********************************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _node_modules_babel_loader_lib_index_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_13_1_node_modules_dcloudio_webpack_uni_mp_loader_lib_script_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_index_js_vue_loader_options_node_modules_dcloudio_webpack_uni_mp_loader_lib_style_js_openid_vue_vue_type_script_lang_js___WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! -!../../node_modules/babel-loader/lib!../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-preprocess-loader??ref--13-1!../../node_modules/@dcloudio/webpack-uni-mp-loader/lib/script.js!../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/vue-loader/lib??vue-loader-options!../../node_modules/@dcloudio/webpack-uni-mp-loader/lib/style.js!./openid.vue?vue&type=script&lang=js& */ 102);
/* empty/unused harmony star reexport */ /* harmony default export */ __webpack_exports__["default"] = (_node_modules_babel_loader_lib_index_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_13_1_node_modules_dcloudio_webpack_uni_mp_loader_lib_script_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_index_js_vue_loader_options_node_modules_dcloudio_webpack_uni_mp_loader_lib_style_js_openid_vue_vue_type_script_lang_js___WEBPACK_IMPORTED_MODULE_0__["default"]); 

/***/ }),

/***/ 102:
/*!****************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************!*\
  !*** ./node_modules/babel-loader/lib!./node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-preprocess-loader??ref--13-1!./node_modules/@dcloudio/webpack-uni-mp-loader/lib/script.js!./node_modules/@dcloudio/vue-cli-plugin-uni/packages/vue-loader/lib??vue-loader-options!./node_modules/@dcloudio/webpack-uni-mp-loader/lib/style.js!./pages/login/openid.vue?vue&type=script&lang=js& ***!
  \****************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* WEBPACK VAR INJECTION */(function(uni) {/* harmony import */ var _common_fa_mixin_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! @/common/fa.mixin.js */ 47);
//
//
//
//
//
//
//
//
//
//
//
//
//


/* harmony default export */ __webpack_exports__["default"] = ({
  mixins: [_common_fa_mixin_js__WEBPACK_IMPORTED_MODULE_0__["loginfunc"]],
  onLoad() {
    this.state = this.$util.getQueryString('state');
    this.code = this.$util.getQueryString('code');
    if (this.state && this.code) {
      this.goWxAuth();
    } else {
      this.content = '授权登录失败！';
    }
    this.si = setTimeout(() => {
      this.show = true;
    }, 1000);
  },
  data() {
    return {
      state: '',
      code: '',
      show: false,
      show: false,
      content: '授权登录中...'
    };
  },
  methods: {
    goWxAuth: async function () {
      let data = {
        code: this.code,
        state: this.state,
        platform: 'wechat',
        base: 1 //仅返回用户信息，不绑定账号
      };
      let res = await this.$api.goAuthCallback(data);
      if (!res) {
        this.content = '授权登录失败！';
        return;
      }
      clearTimeout(this.si);
      this.$u.vuex('vuex_openid', res.data.openid);
      let url = this.vuex_lasturl || '/pages/index/index';

      //清空最后页面
      this.$u.vuex('vuex_lasturl', '');
      uni.reLaunch({
        url: url + (url.indexOf("?") > -1 ? "&" : "?") + "from=openid"
      });
      // this.success();
    },
    confirm() {
      window.history.go(-2);
    }
  }
});
/* WEBPACK VAR INJECTION */}.call(this, __webpack_require__(/*! ./node_modules/@dcloudio/uni-mp-weixin/dist/index.js */ 2)["default"]))

/***/ }),

/***/ 97:
/*!***************************************************!*\
  !*** ./main.js?{"page":"pages%2Flogin%2Fopenid"} ***!
  \***************************************************/
/*! no exports provided */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* WEBPACK VAR INJECTION */(function(wx, createPage) {/* harmony import */ var uni_pages__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! uni-pages */ 10);
/* harmony import */ var uni_pages__WEBPACK_IMPORTED_MODULE_0___default = /*#__PURE__*/__webpack_require__.n(uni_pages__WEBPACK_IMPORTED_MODULE_0__);
/* harmony import */ var _dcloudio_uni_stat_dist_uni_stat_public_es_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! @dcloudio/uni-stat/dist/uni-stat-public.es.js */ 11);
/* harmony import */ var vue__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! vue */ 5);
/* harmony import */ var _pages_login_openid_vue__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(/*! ./pages/login/openid.vue */ 98);

// @ts-ignore
wx.__webpack_require_UNI_MP_PLUGIN__ = __webpack_require__;



createPage(_pages_login_openid_vue__WEBPACK_IMPORTED_MODULE_3__["default"]);
/* WEBPACK VAR INJECTION */}.call(this, __webpack_require__(/*! ./node_modules/@dcloudio/uni-mp-weixin/dist/wx.js */ 1)["default"], __webpack_require__(/*! ./node_modules/@dcloudio/uni-mp-weixin/dist/index.js */ 2)["createPage"]))

/***/ }),

/***/ 98:
/*!********************************!*\
  !*** ./pages/login/openid.vue ***!
  \********************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _openid_vue_vue_type_template_id_4c578c78___WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ./openid.vue?vue&type=template&id=4c578c78& */ 99);
/* harmony import */ var _openid_vue_vue_type_script_lang_js___WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! ./openid.vue?vue&type=script&lang=js& */ 101);
/* empty/unused harmony star reexport *//* harmony import */ var _node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_runtime_componentNormalizer_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! ../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/vue-loader/lib/runtime/componentNormalizer.js */ 19);

var renderjs




/* normalize component */

var component = Object(_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_runtime_componentNormalizer_js__WEBPACK_IMPORTED_MODULE_2__["default"])(
  _openid_vue_vue_type_script_lang_js___WEBPACK_IMPORTED_MODULE_1__["default"],
  _openid_vue_vue_type_template_id_4c578c78___WEBPACK_IMPORTED_MODULE_0__["render"],
  _openid_vue_vue_type_template_id_4c578c78___WEBPACK_IMPORTED_MODULE_0__["staticRenderFns"],
  false,
  null,
  null,
  null,
  false,
  _openid_vue_vue_type_template_id_4c578c78___WEBPACK_IMPORTED_MODULE_0__["components"],
  renderjs
)

component.options.__file = "pages/login/openid.vue"
/* harmony default export */ __webpack_exports__["default"] = (component.exports);

/***/ }),

/***/ 99:
/*!***************************************************************!*\
  !*** ./pages/login/openid.vue?vue&type=template&id=4c578c78& ***!
  \***************************************************************/
/*! exports provided: render, staticRenderFns, recyclableRender, components */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_loaders_templateLoader_js_vue_loader_options_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_15_0_node_modules_dcloudio_webpack_uni_mp_loader_lib_template_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_uni_app_loader_page_meta_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_index_js_vue_loader_options_node_modules_dcloudio_webpack_uni_mp_loader_lib_style_js_openid_vue_vue_type_template_id_4c578c78___WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! -!../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/vue-loader/lib/loaders/templateLoader.js??vue-loader-options!../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-preprocess-loader??ref--15-0!../../node_modules/@dcloudio/webpack-uni-mp-loader/lib/template.js!../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-uni-app-loader/page-meta.js!../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/vue-loader/lib??vue-loader-options!../../node_modules/@dcloudio/webpack-uni-mp-loader/lib/style.js!./openid.vue?vue&type=template&id=4c578c78& */ 100);
/* harmony reexport (safe) */ __webpack_require__.d(__webpack_exports__, "render", function() { return _node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_loaders_templateLoader_js_vue_loader_options_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_15_0_node_modules_dcloudio_webpack_uni_mp_loader_lib_template_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_uni_app_loader_page_meta_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_index_js_vue_loader_options_node_modules_dcloudio_webpack_uni_mp_loader_lib_style_js_openid_vue_vue_type_template_id_4c578c78___WEBPACK_IMPORTED_MODULE_0__["render"]; });

/* harmony reexport (safe) */ __webpack_require__.d(__webpack_exports__, "staticRenderFns", function() { return _node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_loaders_templateLoader_js_vue_loader_options_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_15_0_node_modules_dcloudio_webpack_uni_mp_loader_lib_template_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_uni_app_loader_page_meta_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_index_js_vue_loader_options_node_modules_dcloudio_webpack_uni_mp_loader_lib_style_js_openid_vue_vue_type_template_id_4c578c78___WEBPACK_IMPORTED_MODULE_0__["staticRenderFns"]; });

/* harmony reexport (safe) */ __webpack_require__.d(__webpack_exports__, "recyclableRender", function() { return _node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_loaders_templateLoader_js_vue_loader_options_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_15_0_node_modules_dcloudio_webpack_uni_mp_loader_lib_template_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_uni_app_loader_page_meta_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_index_js_vue_loader_options_node_modules_dcloudio_webpack_uni_mp_loader_lib_style_js_openid_vue_vue_type_template_id_4c578c78___WEBPACK_IMPORTED_MODULE_0__["recyclableRender"]; });

/* harmony reexport (safe) */ __webpack_require__.d(__webpack_exports__, "components", function() { return _node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_loaders_templateLoader_js_vue_loader_options_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_15_0_node_modules_dcloudio_webpack_uni_mp_loader_lib_template_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_uni_app_loader_page_meta_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_index_js_vue_loader_options_node_modules_dcloudio_webpack_uni_mp_loader_lib_style_js_openid_vue_vue_type_template_id_4c578c78___WEBPACK_IMPORTED_MODULE_0__["components"]; });



/***/ })

},[[97,"common/runtime","common/vendor"]]]);
//# sourceMappingURL=../../../.sourcemap/mp-weixin/pages/login/openid.js.map