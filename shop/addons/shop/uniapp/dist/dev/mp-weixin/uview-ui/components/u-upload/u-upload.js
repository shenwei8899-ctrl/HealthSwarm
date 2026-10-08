(global["webpackJsonp"] = global["webpackJsonp"] || []).push([["uview-ui/components/u-upload/u-upload"],{

/***/ 1005:
/*!***************************************************!*\
  !*** ./uview-ui/components/u-upload/u-upload.vue ***!
  \***************************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _u_upload_vue_vue_type_template_id_0d33af60_scoped_true___WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ./u-upload.vue?vue&type=template&id=0d33af60&scoped=true& */ 1006);
/* harmony import */ var _u_upload_vue_vue_type_script_lang_js___WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! ./u-upload.vue?vue&type=script&lang=js& */ 1008);
/* empty/unused harmony star reexport *//* harmony import */ var _u_upload_vue_vue_type_style_index_0_id_0d33af60_lang_scss_scoped_true___WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! ./u-upload.vue?vue&type=style&index=0&id=0d33af60&lang=scss&scoped=true& */ 1010);
/* harmony import */ var _node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_runtime_componentNormalizer_js__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(/*! ../../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/vue-loader/lib/runtime/componentNormalizer.js */ 19);

var renderjs





/* normalize component */

var component = Object(_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_runtime_componentNormalizer_js__WEBPACK_IMPORTED_MODULE_3__["default"])(
  _u_upload_vue_vue_type_script_lang_js___WEBPACK_IMPORTED_MODULE_1__["default"],
  _u_upload_vue_vue_type_template_id_0d33af60_scoped_true___WEBPACK_IMPORTED_MODULE_0__["render"],
  _u_upload_vue_vue_type_template_id_0d33af60_scoped_true___WEBPACK_IMPORTED_MODULE_0__["staticRenderFns"],
  false,
  null,
  "0d33af60",
  null,
  false,
  _u_upload_vue_vue_type_template_id_0d33af60_scoped_true___WEBPACK_IMPORTED_MODULE_0__["components"],
  renderjs
)

component.options.__file = "uview-ui/components/u-upload/u-upload.vue"
/* harmony default export */ __webpack_exports__["default"] = (component.exports);

/***/ }),

/***/ 1006:
/*!**********************************************************************************************!*\
  !*** ./uview-ui/components/u-upload/u-upload.vue?vue&type=template&id=0d33af60&scoped=true& ***!
  \**********************************************************************************************/
/*! exports provided: render, staticRenderFns, recyclableRender, components */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_loaders_templateLoader_js_vue_loader_options_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_15_0_node_modules_dcloudio_webpack_uni_mp_loader_lib_template_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_uni_app_loader_page_meta_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_index_js_vue_loader_options_node_modules_dcloudio_webpack_uni_mp_loader_lib_style_js_u_upload_vue_vue_type_template_id_0d33af60_scoped_true___WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! -!../../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/vue-loader/lib/loaders/templateLoader.js??vue-loader-options!../../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-preprocess-loader??ref--15-0!../../../node_modules/@dcloudio/webpack-uni-mp-loader/lib/template.js!../../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-uni-app-loader/page-meta.js!../../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/vue-loader/lib??vue-loader-options!../../../node_modules/@dcloudio/webpack-uni-mp-loader/lib/style.js!./u-upload.vue?vue&type=template&id=0d33af60&scoped=true& */ 1007);
/* harmony reexport (safe) */ __webpack_require__.d(__webpack_exports__, "render", function() { return _node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_loaders_templateLoader_js_vue_loader_options_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_15_0_node_modules_dcloudio_webpack_uni_mp_loader_lib_template_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_uni_app_loader_page_meta_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_index_js_vue_loader_options_node_modules_dcloudio_webpack_uni_mp_loader_lib_style_js_u_upload_vue_vue_type_template_id_0d33af60_scoped_true___WEBPACK_IMPORTED_MODULE_0__["render"]; });

/* harmony reexport (safe) */ __webpack_require__.d(__webpack_exports__, "staticRenderFns", function() { return _node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_loaders_templateLoader_js_vue_loader_options_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_15_0_node_modules_dcloudio_webpack_uni_mp_loader_lib_template_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_uni_app_loader_page_meta_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_index_js_vue_loader_options_node_modules_dcloudio_webpack_uni_mp_loader_lib_style_js_u_upload_vue_vue_type_template_id_0d33af60_scoped_true___WEBPACK_IMPORTED_MODULE_0__["staticRenderFns"]; });

/* harmony reexport (safe) */ __webpack_require__.d(__webpack_exports__, "recyclableRender", function() { return _node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_loaders_templateLoader_js_vue_loader_options_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_15_0_node_modules_dcloudio_webpack_uni_mp_loader_lib_template_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_uni_app_loader_page_meta_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_index_js_vue_loader_options_node_modules_dcloudio_webpack_uni_mp_loader_lib_style_js_u_upload_vue_vue_type_template_id_0d33af60_scoped_true___WEBPACK_IMPORTED_MODULE_0__["recyclableRender"]; });

/* harmony reexport (safe) */ __webpack_require__.d(__webpack_exports__, "components", function() { return _node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_loaders_templateLoader_js_vue_loader_options_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_15_0_node_modules_dcloudio_webpack_uni_mp_loader_lib_template_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_uni_app_loader_page_meta_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_index_js_vue_loader_options_node_modules_dcloudio_webpack_uni_mp_loader_lib_style_js_u_upload_vue_vue_type_template_id_0d33af60_scoped_true___WEBPACK_IMPORTED_MODULE_0__["components"]; });



/***/ }),

/***/ 1007:
/*!**********************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************!*\
  !*** ./node_modules/@dcloudio/vue-cli-plugin-uni/packages/vue-loader/lib/loaders/templateLoader.js??vue-loader-options!./node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-preprocess-loader??ref--15-0!./node_modules/@dcloudio/webpack-uni-mp-loader/lib/template.js!./node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-uni-app-loader/page-meta.js!./node_modules/@dcloudio/vue-cli-plugin-uni/packages/vue-loader/lib??vue-loader-options!./node_modules/@dcloudio/webpack-uni-mp-loader/lib/style.js!./uview-ui/components/u-upload/u-upload.vue?vue&type=template&id=0d33af60&scoped=true& ***!
  \**********************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************/
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
  var l0 = !_vm.disabled
    ? _vm.__map(_vm.lists, function (item, index) {
        var $orig = _vm.__get_orig(item)
        var g0 = _vm.showUploadList ? _vm.$u.addUnit(_vm.width) : null
        var g1 = _vm.showUploadList ? _vm.$u.addUnit(_vm.height) : null
        return {
          $orig: $orig,
          g0: g0,
          g1: g1,
        }
      })
    : null
  _vm.$initSSP()
  var g2 = !_vm.disabled ? _vm.lists.length : null
  var g3 =
    !_vm.disabled && _vm.maxCount > g2 && !_vm.customBtn
      ? _vm.$u.addUnit(_vm.width)
      : null
  var g4 =
    !_vm.disabled && _vm.maxCount > g2 && !_vm.customBtn
      ? _vm.$u.addUnit(_vm.height)
      : null
  _vm.$mp.data = Object.assign(
    {},
    {
      $root: {
        l0: l0,
        g2: g2,
        g3: g3,
        g4: g4,
      },
    }
  )
  if (_vm.$scope.data.scopedSlotsCompiler === "augmented") {
    _vm.$setSSP("file", {
      file: _vm.lists,
    })
  }
  _vm.$callSSP()
}
var staticRenderFns = []
render._withStripped = true

var recyclableRender = typeof recyclableRender === 'undefined' ? null : recyclableRender
var components = typeof components === 'undefined' ? {} : components


/***/ }),

/***/ 1008:
/*!****************************************************************************!*\
  !*** ./uview-ui/components/u-upload/u-upload.vue?vue&type=script&lang=js& ***!
  \****************************************************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _node_modules_babel_loader_lib_index_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_13_1_node_modules_dcloudio_webpack_uni_mp_loader_lib_script_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_index_js_vue_loader_options_node_modules_dcloudio_webpack_uni_mp_loader_lib_style_js_u_upload_vue_vue_type_script_lang_js___WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! -!../../../node_modules/babel-loader/lib!../../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-preprocess-loader??ref--13-1!../../../node_modules/@dcloudio/webpack-uni-mp-loader/lib/script.js!../../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/vue-loader/lib??vue-loader-options!../../../node_modules/@dcloudio/webpack-uni-mp-loader/lib/style.js!./u-upload.vue?vue&type=script&lang=js& */ 1009);
/* empty/unused harmony star reexport */ /* harmony default export */ __webpack_exports__["default"] = (_node_modules_babel_loader_lib_index_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_13_1_node_modules_dcloudio_webpack_uni_mp_loader_lib_script_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_index_js_vue_loader_options_node_modules_dcloudio_webpack_uni_mp_loader_lib_style_js_u_upload_vue_vue_type_script_lang_js___WEBPACK_IMPORTED_MODULE_0__["default"]); 

/***/ }),

/***/ 1009:
/*!***********************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************!*\
  !*** ./node_modules/babel-loader/lib!./node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-preprocess-loader??ref--13-1!./node_modules/@dcloudio/webpack-uni-mp-loader/lib/script.js!./node_modules/@dcloudio/vue-cli-plugin-uni/packages/vue-loader/lib??vue-loader-options!./node_modules/@dcloudio/webpack-uni-mp-loader/lib/style.js!./uview-ui/components/u-upload/u-upload.vue?vue&type=script&lang=js& ***!
  \***********************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* WEBPACK VAR INJECTION */(function(uni) {//
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

/**
 * upload 图片上传
 * @description 该组件用于上传图片场景
 * @tutorial https://www.uviewui.com/components/upload.html
 * @property {String} action 服务器上传地址
 * @property {String Number} max-count 最大选择图片的数量（默认99）
 * @property {Boolean} custom-btn 如果需要自定义选择图片的按钮，设置为true（默认false）
 * @property {Boolean} show-progress 是否显示进度条（默认true）
 * @property {Boolean} disabled 是否启用(显示/移仓)组件（默认false）
 * @property {String} image-mode 预览图片等显示模式，可选值为uni的image的mode属性值（默认aspectFill）
 * @property {String} del-icon 右上角删除图标名称，只能为uView内置图标
 * @property {String} del-bg-color 右上角关闭按钮的背景颜色
 * @property {String | Number} index 在各个回调事件中的最后一个参数返回，用于区别是哪一个组件的事件
 * @property {String} del-color 右上角关闭按钮图标的颜色
 * @property {Object} header 上传携带的头信息，对象形式
 * @property {Object} form-data 上传额外携带的参数
 * @property {String} name 上传文件的字段名，供后端获取使用（默认file）
 * @property {Array<String>} size-type original 原图，compressed 压缩图，默认二者都有（默认['original', 'compressed']）
 * @property {Array<String>} source-type 选择图片的来源，album-从相册选图，camera-使用相机，默认二者都有（默认['album', 'camera']）
 * @property {Boolean} preview-full-image	是否可以通过uni.previewImage预览已选择的图片（默认true）
 * @property {Boolean} multiple	是否开启图片多选，部分安卓机型不支持（默认true）
 * @property {Boolean} deletable 是否显示删除图片的按钮（默认true）
 * @property {String Number} max-size 选择单个文件的最大大小，单位B(byte)，默认不限制（默认Number.MAX_VALUE）
 * @property {Array<Object>} file-list 默认显示的图片列表，数组元素为对象，必须提供url属性
 * @property {Boolean} upload-text 选择图片按钮的提示文字（默认“选择图片”）
 * @property {Boolean} auto-upload 选择完图片是否自动上传，见上方说明（默认true）
 * @property {Boolean} show-tips 特殊情况下是否自动提示toast，见上方说明（默认true）
 * @property {Boolean} show-upload-list 是否显示组件内部的图片预览（默认true）
 * @event {Function} on-oversize 图片大小超出最大允许大小
 * @event {Function} on-preview 全屏预览图片时触发
 * @event {Function} on-remove 移除图片时触发
 * @event {Function} on-success 图片上传成功时触发
 * @event {Function} on-change 图片上传后，无论成功或者失败都会触发
 * @event {Function} on-error 图片上传失败时触发
 * @event {Function} on-progress 图片上传过程中的进度变化过程触发
 * @event {Function} on-uploaded 所有图片上传完毕触发
 * @event {Function} on-choose-complete 每次选择图片后触发，只是让外部可以得知每次选择后，内部的文件列表
 * @example <u-upload :action="action" :file-list="fileList" ></u-upload>
 */
/* harmony default export */ __webpack_exports__["default"] = ({
  name: 'u-upload',
  props: {
    //是否显示组件自带的图片预览功能
    showUploadList: {
      type: Boolean,
      default: true
    },
    // 后端地址
    action: {
      type: String,
      default: ''
    },
    // 最大上传数量
    maxCount: {
      type: [String, Number],
      default: 52
    },
    //  是否显示进度条
    showProgress: {
      type: Boolean,
      default: true
    },
    // 是否启用
    disabled: {
      type: Boolean,
      default: false
    },
    // 预览上传的图片时的裁剪模式，和image组件mode属性一致
    imageMode: {
      type: String,
      default: 'aspectFill'
    },
    // 头部信息
    header: {
      type: Object,
      default() {
        return {};
      }
    },
    // 额外携带的参数
    formData: {
      type: Object,
      default() {
        return {};
      }
    },
    // 上传的文件字段名
    name: {
      type: String,
      default: 'file'
    },
    // 所选的图片的尺寸, 可选值为original compressed
    sizeType: {
      type: Array,
      default() {
        return ['original', 'compressed'];
      }
    },
    sourceType: {
      type: Array,
      default() {
        return ['album', 'camera'];
      }
    },
    // 是否在点击预览图后展示全屏图片预览
    previewFullImage: {
      type: Boolean,
      default: true
    },
    // 是否开启图片多选，部分安卓机型不支持
    multiple: {
      type: Boolean,
      default: true
    },
    // 是否展示删除按钮
    deletable: {
      type: Boolean,
      default: true
    },
    // 文件大小限制，单位为byte
    maxSize: {
      type: [String, Number],
      default: Number.MAX_VALUE
    },
    // 显示已上传的文件列表
    fileList: {
      type: Array,
      default() {
        return [];
      }
    },
    // 上传区域的提示文字
    uploadText: {
      type: String,
      default: '选择图片'
    },
    // 是否自动上传
    autoUpload: {
      type: Boolean,
      default: true
    },
    // 是否显示toast消息提示
    showTips: {
      type: Boolean,
      default: true
    },
    // 是否通过slot自定义传入选择图标的按钮
    customBtn: {
      type: Boolean,
      default: false
    },
    // 内部预览图片区域和选择图片按钮的区域宽度
    width: {
      type: [String, Number],
      default: 200
    },
    // 内部预览图片区域和选择图片按钮的区域高度
    height: {
      type: [String, Number],
      default: 200
    },
    // 右上角关闭按钮的背景颜色
    delBgColor: {
      type: String,
      default: '#fa3534'
    },
    // 右上角关闭按钮的叉号图标的颜色
    delColor: {
      type: String,
      default: '#ffffff'
    },
    // 右上角删除图标名称，只能为uView内置图标
    delIcon: {
      type: String,
      default: 'close'
    },
    // 如果上传后的返回值为json字符串，是否自动转json
    toJson: {
      type: Boolean,
      default: true
    },
    // 上传前的钩子，每个文件上传前都会执行
    beforeUpload: {
      type: Function,
      default: null
    },
    // 移除文件前的钩子
    beforeRemove: {
      type: Function,
      default: null
    },
    // 允许上传的图片后缀
    limitType: {
      type: Array,
      default() {
        // 支付宝小程序真机选择图片的后缀为"image"
        // https://opendocs.alipay.com/mini/api/media-image
        return ['png', 'jpg', 'jpeg', 'webp', 'gif', 'image'];
      }
    },
    // 在各个回调事件中的最后一个参数返回，用于区别是哪一个组件的事件
    index: {
      type: [Number, String],
      default: ''
    }
  },
  mounted() {},
  data() {
    return {
      lists: [],
      isInCount: true,
      uploading: false
    };
  },
  watch: {
    fileList: {
      immediate: true,
      handler(val) {
        val.map(value => {
          // 首先检查内部是否已经添加过这张图片，因为外部绑定了一个对象给fileList的话(对象引用)，进行修改外部fileList
          // 时，会触发watch，导致重新把原来的图片再次添加到this.lists
          // 数组的some方法意思是，只要数组元素有任意一个元素条件符合，就返回true，而另一个数组的every方法的意思是数组所有元素都符合条件才返回true
          let tmp = this.lists.some(val => {
            return val.url == value.url;
          });
          // 如果内部没有这个图片(tmp为false)，则添加到内部
          !tmp && this.lists.push({
            url: value.url,
            error: false,
            progress: 100
          });
        });
      }
    },
    // 监听lists的变化，发出事件
    lists(n) {
      this.$emit('on-list-change', n, this.index);
    }
  },
  methods: {
    // 清除列表
    clear() {
      this.lists = [];
    },
    // 重新上传队列中上传失败的所有文件
    reUpload() {
      this.uploadFile();
    },
    // 选择图片
    selectFile() {
      if (this.disabled) return;
      const {
        name = '',
        maxCount,
        multiple,
        maxSize,
        sizeType,
        lists,
        camera,
        compressed,
        maxDuration,
        sourceType
      } = this;
      let chooseFile = null;
      const newMaxCount = maxCount - lists.length;
      // 设置为只选择图片的时候使用 chooseImage 来实现
      chooseFile = new Promise((resolve, reject) => {
        uni.chooseImage({
          count: multiple ? newMaxCount > 9 ? 9 : newMaxCount : 1,
          sourceType: sourceType,
          sizeType,
          success: resolve,
          fail: reject
        });
      });
      chooseFile.then(res => {
        let file = null;
        let listOldLength = this.lists.length;
        res.tempFiles.map((val, index) => {
          // 检查文件后缀是否允许，如果不在this.limitType内，就会返回false
          if (!this.checkFileExt(val)) return;

          // 如果是非多选，index大于等于1或者超出最大限制数量时，不处理
          if (!multiple && index >= 1) return;
          if (val.size > maxSize) {
            this.$emit('on-oversize', val, this.lists, this.index);
            this.showToast('超出允许的文件大小');
          } else {
            if (maxCount <= lists.length) {
              this.$emit('on-exceed', val, this.lists, this.index);
              this.showToast('超出最大允许的文件个数');
              return;
            }
            lists.push({
              url: val.path,
              progress: 0,
              error: false,
              file: val
            });
          }
        });
        // 每次图片选择完，抛出一个事件，并将当前内部选择的图片数组抛出去
        this.$emit('on-choose-complete', this.lists, this.index);
        if (this.autoUpload) this.uploadFile(listOldLength);
      }).catch(error => {
        this.$emit('on-choose-fail', error);
      });
    },
    // 提示用户消息
    showToast(message, force = false) {
      if (this.showTips || force) {
        uni.showToast({
          title: message,
          icon: 'none'
        });
      }
    },
    // 该方法供用户通过ref调用，手动上传
    upload() {
      this.uploadFile();
    },
    // 对失败的图片重新上传
    retry(index) {
      this.lists[index].progress = 0;
      this.lists[index].error = false;
      this.lists[index].response = null;
      uni.showLoading({
        title: '重新上传'
      });
      this.uploadFile(index);
    },
    // 上传图片
    async uploadFile(index = 0) {
      if (this.disabled) return;
      if (this.uploading) return;
      // 全部上传完成
      if (index >= this.lists.length) {
        this.$emit('on-uploaded', this.lists, this.index);
        return;
      }
      // 检查是否是已上传或者正在上传中
      if (this.lists[index].progress == 100) {
        if (this.autoUpload == false) this.uploadFile(index + 1);
        return;
      }
      // 执行before-upload钩子
      if (this.beforeUpload && typeof this.beforeUpload === 'function') {
        // 执行回调，同时传入索引和文件列表当作参数
        // 在微信，支付宝等环境(H5正常)，会导致父组件定义的customBack()函数体中的this变成子组件的this
        // 通过bind()方法，绑定父组件的this，让this.customBack()的this为父组件的上下文
        // 因为upload组件可能会被嵌套在其他组件内，比如u-form，这时this.$parent其实为u-form的this，
        // 非页面的this，所以这里需要往上历遍，一直寻找到最顶端的$parent，这里用了this.$u.$parent.call(this)
        // 明白意思即可，无需纠结this.$u.$parent.call(this)的细节
        let beforeResponse = this.beforeUpload.bind(this.$u.$parent.call(this))(index, this.lists);
        // 判断是否返回了promise
        if (!!beforeResponse && typeof beforeResponse.then === 'function') {
          await beforeResponse.then(res => {
            // promise返回成功，不进行动作，继续上传
          }).catch(err => {
            // 进入catch回调的话，继续下一张
            return this.uploadFile(index + 1);
          });
        } else if (beforeResponse === false) {
          // 如果返回false，继续下一张图片的上传
          return this.uploadFile(index + 1);
        } else {
          // 此处为返回"true"的情形，这里不写代码，就跳过此处，继续执行当前的上传逻辑
        }
      }
      // 检查上传地址
      if (!this.action) {
        this.showToast('请配置上传地址', true);
        return;
      }
      this.lists[index].error = false;
      this.uploading = true;
      // 创建上传对象
      const task = uni.uploadFile({
        url: this.action,
        filePath: this.lists[index].url,
        name: this.name,
        formData: this.formData,
        header: this.header,
        success: res => {
          // 判断是否json字符串，将其转为json格式
          let data = this.toJson && this.$u.test.jsonString(res.data) ? JSON.parse(res.data) : res.data;
          if (![200, 201, 204].includes(res.statusCode)) {
            this.uploadError(index, data);
          } else {
            // 上传成功
            this.lists[index].response = data;
            this.lists[index].progress = 100;
            this.lists[index].error = false;
            this.$emit('on-success', data, index, this.lists, this.index);
          }
        },
        fail: e => {
          this.uploadError(index, e);
        },
        complete: res => {
          uni.hideLoading();
          this.uploading = false;
          this.uploadFile(index + 1);
          this.$emit('on-change', res, index, this.lists, this.index);
        }
      });
      task.onProgressUpdate(res => {
        if (res.progress > 0) {
          this.lists[index].progress = res.progress;
          this.$emit('on-progress', res, index, this.lists, this.index);
        }
      });
    },
    // 上传失败
    uploadError(index, err) {
      this.lists[index].progress = 0;
      this.lists[index].error = true;
      this.lists[index].response = null;
      this.$emit('on-error', err, index, this.lists, this.index);
      this.showToast('上传失败，请重试');
    },
    // 删除一个图片
    deleteItem(index) {
      uni.showModal({
        title: '提示',
        content: '您确定要删除此项吗？',
        success: async res => {
          if (res.confirm) {
            // 先检查是否有定义before-remove移除前钩子
            // 执行before-remove钩子
            if (this.beforeRemove && typeof this.beforeRemove === 'function') {
              // 此处钩子执行 原理同before-remove参数，见上方注释
              let beforeResponse = this.beforeRemove.bind(this.$u.$parent.call(this))(index, this.lists);
              // 判断是否返回了promise
              if (!!beforeResponse && typeof beforeResponse.then === 'function') {
                await beforeResponse.then(res => {
                  // promise返回成功，不进行动作，继续上传
                  this.handlerDeleteItem(index);
                }).catch(err => {
                  // 如果进入promise的reject，终止删除操作
                  this.showToast('已终止移除');
                });
              } else if (beforeResponse === false) {
                // 返回false，终止删除
                this.showToast('已终止移除');
              } else {
                // 如果返回true，执行删除操作
                this.handlerDeleteItem(index);
              }
            } else {
              // 如果不存在before-remove钩子，
              this.handlerDeleteItem(index);
            }
          }
        }
      });
    },
    // 执行移除图片的动作，上方代码只是判断是否可以移除
    handlerDeleteItem(index) {
      // 如果文件正在上传中，终止上传任务，进度在0 < progress < 100则意味着正在上传
      if (this.lists[index].process < 100 && this.lists[index].process > 0) {
        typeof this.lists[index].uploadTask != 'undefined' && this.lists[index].uploadTask.abort();
      }
      this.lists.splice(index, 1);
      this.$forceUpdate();
      this.$emit('on-remove', index, this.lists, this.index);
      this.showToast('移除成功');
    },
    // 用户通过ref手动的形式，移除一张图片
    remove(index) {
      // 判断索引的合法范围
      if (index >= 0 && index < this.lists.length) {
        this.lists.splice(index, 1);
        this.$emit('on-list-change', this.lists, this.index);
      }
    },
    // 预览图片
    doPreviewImage(url, index) {
      if (!this.previewFullImage) return;
      const images = this.lists.map(item => item.url || item.path);
      uni.previewImage({
        urls: images,
        current: url,
        success: () => {
          this.$emit('on-preview', url, this.lists, this.index);
        },
        fail: () => {
          uni.showToast({
            title: '预览图片失败',
            icon: 'none'
          });
        }
      });
    },
    // 判断文件后缀是否允许
    checkFileExt(file) {
      // 检查是否在允许的后缀中
      let noArrowExt = false;
      // 获取后缀名
      let fileExt = '';
      const reg = /.+\./;
      // 如果是H5，需要从name中判断

      // 非H5，需要从path中读取后缀

      fileExt = file.path.replace(reg, "").toLowerCase();

      // 使用数组的some方法，只要符合limitType中的一个，就返回true
      noArrowExt = this.limitType.some(ext => {
        // 转为小写
        return ext.toLowerCase() === fileExt;
      });
      if (!noArrowExt) this.showToast(`不允许选择${fileExt}格式的文件`);
      return noArrowExt;
    }
  }
});
/* WEBPACK VAR INJECTION */}.call(this, __webpack_require__(/*! ./node_modules/@dcloudio/uni-mp-weixin/dist/index.js */ 2)["default"]))

/***/ }),

/***/ 1010:
/*!*************************************************************************************************************!*\
  !*** ./uview-ui/components/u-upload/u-upload.vue?vue&type=style&index=0&id=0d33af60&lang=scss&scoped=true& ***!
  \*************************************************************************************************************/
/*! no static exports found */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _node_modules_mini_css_extract_plugin_dist_loader_js_ref_9_oneOf_1_0_node_modules_css_loader_dist_cjs_js_ref_9_oneOf_1_1_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_loaders_stylePostLoader_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_9_oneOf_1_2_node_modules_postcss_loader_src_index_js_ref_9_oneOf_1_3_node_modules_dcloudio_vue_cli_plugin_uni_packages_sass_loader_dist_cjs_js_ref_9_oneOf_1_4_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_9_oneOf_1_5_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_index_js_vue_loader_options_node_modules_dcloudio_webpack_uni_mp_loader_lib_style_js_u_upload_vue_vue_type_style_index_0_id_0d33af60_lang_scss_scoped_true___WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! -!../../../node_modules/mini-css-extract-plugin/dist/loader.js??ref--9-oneOf-1-0!../../../node_modules/css-loader/dist/cjs.js??ref--9-oneOf-1-1!../../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/vue-loader/lib/loaders/stylePostLoader.js!../../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-preprocess-loader??ref--9-oneOf-1-2!../../../node_modules/postcss-loader/src??ref--9-oneOf-1-3!../../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/sass-loader/dist/cjs.js??ref--9-oneOf-1-4!../../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-preprocess-loader??ref--9-oneOf-1-5!../../../node_modules/@dcloudio/vue-cli-plugin-uni/packages/vue-loader/lib??vue-loader-options!../../../node_modules/@dcloudio/webpack-uni-mp-loader/lib/style.js!./u-upload.vue?vue&type=style&index=0&id=0d33af60&lang=scss&scoped=true& */ 1011);
/* harmony import */ var _node_modules_mini_css_extract_plugin_dist_loader_js_ref_9_oneOf_1_0_node_modules_css_loader_dist_cjs_js_ref_9_oneOf_1_1_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_loaders_stylePostLoader_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_9_oneOf_1_2_node_modules_postcss_loader_src_index_js_ref_9_oneOf_1_3_node_modules_dcloudio_vue_cli_plugin_uni_packages_sass_loader_dist_cjs_js_ref_9_oneOf_1_4_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_9_oneOf_1_5_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_index_js_vue_loader_options_node_modules_dcloudio_webpack_uni_mp_loader_lib_style_js_u_upload_vue_vue_type_style_index_0_id_0d33af60_lang_scss_scoped_true___WEBPACK_IMPORTED_MODULE_0___default = /*#__PURE__*/__webpack_require__.n(_node_modules_mini_css_extract_plugin_dist_loader_js_ref_9_oneOf_1_0_node_modules_css_loader_dist_cjs_js_ref_9_oneOf_1_1_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_loaders_stylePostLoader_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_9_oneOf_1_2_node_modules_postcss_loader_src_index_js_ref_9_oneOf_1_3_node_modules_dcloudio_vue_cli_plugin_uni_packages_sass_loader_dist_cjs_js_ref_9_oneOf_1_4_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_9_oneOf_1_5_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_index_js_vue_loader_options_node_modules_dcloudio_webpack_uni_mp_loader_lib_style_js_u_upload_vue_vue_type_style_index_0_id_0d33af60_lang_scss_scoped_true___WEBPACK_IMPORTED_MODULE_0__);
/* harmony reexport (unknown) */ for(var __WEBPACK_IMPORT_KEY__ in _node_modules_mini_css_extract_plugin_dist_loader_js_ref_9_oneOf_1_0_node_modules_css_loader_dist_cjs_js_ref_9_oneOf_1_1_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_loaders_stylePostLoader_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_9_oneOf_1_2_node_modules_postcss_loader_src_index_js_ref_9_oneOf_1_3_node_modules_dcloudio_vue_cli_plugin_uni_packages_sass_loader_dist_cjs_js_ref_9_oneOf_1_4_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_9_oneOf_1_5_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_index_js_vue_loader_options_node_modules_dcloudio_webpack_uni_mp_loader_lib_style_js_u_upload_vue_vue_type_style_index_0_id_0d33af60_lang_scss_scoped_true___WEBPACK_IMPORTED_MODULE_0__) if(["default"].indexOf(__WEBPACK_IMPORT_KEY__) < 0) (function(key) { __webpack_require__.d(__webpack_exports__, key, function() { return _node_modules_mini_css_extract_plugin_dist_loader_js_ref_9_oneOf_1_0_node_modules_css_loader_dist_cjs_js_ref_9_oneOf_1_1_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_loaders_stylePostLoader_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_9_oneOf_1_2_node_modules_postcss_loader_src_index_js_ref_9_oneOf_1_3_node_modules_dcloudio_vue_cli_plugin_uni_packages_sass_loader_dist_cjs_js_ref_9_oneOf_1_4_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_9_oneOf_1_5_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_index_js_vue_loader_options_node_modules_dcloudio_webpack_uni_mp_loader_lib_style_js_u_upload_vue_vue_type_style_index_0_id_0d33af60_lang_scss_scoped_true___WEBPACK_IMPORTED_MODULE_0__[key]; }) }(__WEBPACK_IMPORT_KEY__));
 /* harmony default export */ __webpack_exports__["default"] = (_node_modules_mini_css_extract_plugin_dist_loader_js_ref_9_oneOf_1_0_node_modules_css_loader_dist_cjs_js_ref_9_oneOf_1_1_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_loaders_stylePostLoader_js_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_9_oneOf_1_2_node_modules_postcss_loader_src_index_js_ref_9_oneOf_1_3_node_modules_dcloudio_vue_cli_plugin_uni_packages_sass_loader_dist_cjs_js_ref_9_oneOf_1_4_node_modules_dcloudio_vue_cli_plugin_uni_packages_webpack_preprocess_loader_index_js_ref_9_oneOf_1_5_node_modules_dcloudio_vue_cli_plugin_uni_packages_vue_loader_lib_index_js_vue_loader_options_node_modules_dcloudio_webpack_uni_mp_loader_lib_style_js_u_upload_vue_vue_type_style_index_0_id_0d33af60_lang_scss_scoped_true___WEBPACK_IMPORTED_MODULE_0___default.a); 

/***/ }),

/***/ 1011:
/*!*****************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************!*\
  !*** ./node_modules/mini-css-extract-plugin/dist/loader.js??ref--9-oneOf-1-0!./node_modules/css-loader/dist/cjs.js??ref--9-oneOf-1-1!./node_modules/@dcloudio/vue-cli-plugin-uni/packages/vue-loader/lib/loaders/stylePostLoader.js!./node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-preprocess-loader??ref--9-oneOf-1-2!./node_modules/postcss-loader/src??ref--9-oneOf-1-3!./node_modules/@dcloudio/vue-cli-plugin-uni/packages/sass-loader/dist/cjs.js??ref--9-oneOf-1-4!./node_modules/@dcloudio/vue-cli-plugin-uni/packages/webpack-preprocess-loader??ref--9-oneOf-1-5!./node_modules/@dcloudio/vue-cli-plugin-uni/packages/vue-loader/lib??vue-loader-options!./node_modules/@dcloudio/webpack-uni-mp-loader/lib/style.js!./uview-ui/components/u-upload/u-upload.vue?vue&type=style&index=0&id=0d33af60&lang=scss&scoped=true& ***!
  \*****************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************/
/*! no static exports found */
/***/ (function(module, exports, __webpack_require__) {

// extracted by mini-css-extract-plugin
    if(false) { var cssReload; }
  

/***/ })

}]);
//# sourceMappingURL=../../../../.sourcemap/mp-weixin/uview-ui/components/u-upload/u-upload.js.map
;(global["webpackJsonp"] = global["webpackJsonp"] || []).push([
    'uview-ui/components/u-upload/u-upload-create-component',
    {
        'uview-ui/components/u-upload/u-upload-create-component':(function(module, exports, __webpack_require__){
            __webpack_require__('2')['createComponent'](__webpack_require__(1005))
        })
    },
    [['uview-ui/components/u-upload/u-upload-create-component']]
]);
