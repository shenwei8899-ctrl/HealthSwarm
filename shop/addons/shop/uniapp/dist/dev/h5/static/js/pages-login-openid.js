(window["webpackJsonp"] = window["webpackJsonp"] || []).push([["pages-login-openid"],{

/***/ "6RHp":
/*!*********************************************************!*\
  !*** ./pages/login/openid.vue?vue&type=script&lang=js& ***!
  \*********************************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _node_modules_babel_loader_lib_index_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_13_1_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_16_0_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_uni_app_loader_using_components_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_index_js_vue_loader_options_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_scoped_loader_index_js_openid_vue_vue_type_script_lang_js___WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! -!../../node_modules/babel-loader/lib!../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-preprocess-loader??ref--13-1!../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-preprocess-loader??ref--16-0!../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-uni-app-loader/using-components.js!../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/vue-loader/lib??vue-loader-options!../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-scoped-loader!./openid.vue?vue&type=script&lang=js& */ "gDFO");
/* empty/unused harmony star reexport */ /* harmony default export */ __webpack_exports__["default"] = (_node_modules_babel_loader_lib_index_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_13_1_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_16_0_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_uni_app_loader_using_components_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_index_js_vue_loader_options_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_scoped_loader_index_js_openid_vue_vue_type_script_lang_js___WEBPACK_IMPORTED_MODULE_0__["default"]); 

/***/ }),

/***/ "gDFO":
/*!************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************!*\
  !*** ./node_modules/babel-loader/lib!./node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-preprocess-loader??ref--13-1!./node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-preprocess-loader??ref--16-0!./node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-uni-app-loader/using-components.js!./node_modules/@dcloudio/vue-cli-plugin-uni/packages/vue-loader/lib??vue-loader-options!./node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-scoped-loader!./pages/login/openid.vue?vue&type=script&lang=js& ***!
  \************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _common_fa_mixin_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! @/common/fa.mixin.js */ "xvcv");
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

/***/ }),

/***/ "hjUa":
/*!**********************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************!*\
  !*** ./node_modules/@dcloudio/vue-cli-plugin-uni/packages/vue-loader/lib/loaders/templateLoader.js??vue-loader-options!./node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-preprocess-loader??ref--15-0!./node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-uni-app-loader/filter-modules-template.js!./node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-uni-app-loader/page-meta.js!./node_modules/@dcloudio/vue-cli-plugin-uni/packages/vue-loader/lib??vue-loader-options!./node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-scoped-loader!./pages/login/openid.vue?vue&type=template&id=4c578c78&scoped=true& ***!
  \**********************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************/
/*! no static exports found */
/***/ (function(module, exports) {

throw new Error("Module parse failed: Export 'recyclableRender' is not defined (49:34)\nFile was processed with these loaders:\n * ./node_modules/@dcloudio/vue-cli-plugin-uni/packages/vue-loader/lib/loaders/templateLoader.js\n * ./node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-preprocess-loader/index.js\n * ./node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-uni-app-loader/filter-modules-template.js\n * ./node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-uni-app-loader/page-meta.js\n * ./node_modules/@dcloudio/vue-cli-plugin-uni/packages/vue-loader/lib/index.js\n * ./node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-scoped-loader/index.js\nYou may need an additional loader to handle the result of these loaders.\n| render._withStripped = true\n| \n> export { render, staticRenderFns, recyclableRender, components }");

/***/ }),

/***/ "m13m":
/*!********************************!*\
  !*** ./pages/login/openid.vue ***!
  \********************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _openid_vue_vue_type_template_id_4c578c78_scoped_true___WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ./openid.vue?vue&type=template&id=4c578c78&scoped=true& */ "yR83");
/* harmony import */ var _openid_vue_vue_type_script_lang_js___WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! ./openid.vue?vue&type=script&lang=js& */ "6RHp");
/* empty/unused harmony star reexport *//* harmony import */ var _node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_runtime_componentNormalizer_js__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! ../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/vue-loader/lib/runtime/componentNormalizer.js */ "8MXW");

var renderjs




/* normalize component */

var component = Object(_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_runtime_componentNormalizer_js__WEBPACK_IMPORTED_MODULE_2__["default"])(
  _openid_vue_vue_type_script_lang_js___WEBPACK_IMPORTED_MODULE_1__["default"],
  _openid_vue_vue_type_template_id_4c578c78_scoped_true___WEBPACK_IMPORTED_MODULE_0__["render"],
  _openid_vue_vue_type_template_id_4c578c78_scoped_true___WEBPACK_IMPORTED_MODULE_0__["staticRenderFns"],
  false,
  null,
  "4c578c78",
  null,
  false,
  _openid_vue_vue_type_template_id_4c578c78_scoped_true___WEBPACK_IMPORTED_MODULE_0__["components"],
  renderjs
)

/* hot reload */
if (false) { var api; }
component.options.__file = "pages/login/openid.vue"
/* harmony default export */ __webpack_exports__["default"] = (component.exports);

/***/ }),

/***/ "yR83":
/*!***************************************************************************!*\
  !*** ./pages/login/openid.vue?vue&type=template&id=4c578c78&scoped=true& ***!
  \***************************************************************************/
/*! no static exports found */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_loaders_templateLoader_js_vue_loader_options_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_15_0_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_uni_app_loader_filter_modules_template_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_uni_app_loader_page_meta_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_index_js_vue_loader_options_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_scoped_loader_index_js_openid_vue_vue_type_template_id_4c578c78_scoped_true___WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! -!../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/vue-loader/lib/loaders/templateLoader.js??vue-loader-options!../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-preprocess-loader??ref--15-0!../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-uni-app-loader/filter-modules-template.js!../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-uni-app-loader/page-meta.js!../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/vue-loader/lib??vue-loader-options!../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-scoped-loader!./openid.vue?vue&type=template&id=4c578c78&scoped=true& */ "hjUa");
/* harmony import */ var _node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_loaders_templateLoader_js_vue_loader_options_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_15_0_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_uni_app_loader_filter_modules_template_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_uni_app_loader_page_meta_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_index_js_vue_loader_options_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_scoped_loader_index_js_openid_vue_vue_type_template_id_4c578c78_scoped_true___WEBPACK_IMPORTED_MODULE_0___default = /*#__PURE__*/__webpack_require__.n(_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_loaders_templateLoader_js_vue_loader_options_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_15_0_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_uni_app_loader_filter_modules_template_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_uni_app_loader_page_meta_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_index_js_vue_loader_options_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_scoped_loader_index_js_openid_vue_vue_type_template_id_4c578c78_scoped_true___WEBPACK_IMPORTED_MODULE_0__);
/* harmony reexport (unknown) */ for(var __WEBPACK_IMPORT_KEY__ in _node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_loaders_templateLoader_js_vue_loader_options_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_15_0_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_uni_app_loader_filter_modules_template_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_uni_app_loader_page_meta_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_index_js_vue_loader_options_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_scoped_loader_index_js_openid_vue_vue_type_template_id_4c578c78_scoped_true___WEBPACK_IMPORTED_MODULE_0__) if(["default"].indexOf(__WEBPACK_IMPORT_KEY__) < 0) (function(key) { __webpack_require__.d(__webpack_exports__, key, function() { return _node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_loaders_templateLoader_js_vue_loader_options_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_15_0_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_uni_app_loader_filter_modules_template_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_uni_app_loader_page_meta_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_index_js_vue_loader_options_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_scoped_loader_index_js_openid_vue_vue_type_template_id_4c578c78_scoped_true___WEBPACK_IMPORTED_MODULE_0__[key]; }) }(__WEBPACK_IMPORT_KEY__));


/***/ })

}]);