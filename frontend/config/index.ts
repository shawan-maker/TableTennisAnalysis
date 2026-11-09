import { defineConfig, type UserConfigExport } from '@tarojs/cli'
import TsconfigPathsPlugin from 'tsconfig-paths-webpack-plugin'
import path from 'path'

import devConfig from './dev'
import prodConfig from './prod'

// https://taro-docs.jd.com/docs/next/config#defineconfig-辅助函数
export default defineConfig<'webpack5'>(async (merge, _ctx) => {
  const baseConfig: UserConfigExport<'webpack5'> = {
    projectName: 'pingpong-ai-frontend',
    date: '2026-11-4',
    // 设计系统基于 375 逻辑像素（8px 网格 + NutUI），designWidth 取 375
    // 使编译时 1 设计 px = 2 rpx = 1 逻辑 px，与 H5 端视觉一致
    designWidth: 375,
    deviceRatio: {
      640: 2.34 / 2,
      750: 1,
      375: 2,
      828: 1.81 / 2
    },
    sourceRoot: 'src',
    outputRoot: 'dist',
    plugins: [
      '@tarojs/plugin-generator'
    ],
    defineConstants: {
    },
    copy: {
      patterns: [
      ],
      options: {
      }
    },
    framework: 'react',
    compiler: 'webpack5',
    // 设计样例统一 import '@nutui/nutui-react'；Taro 端实际使用 Taro 构建包
    // （@nutui/nutui-react 4.x beta 无 taro 构建，故采用 2.7.14 taro 线 + alias 映射）。
    alias: {
      '@nutui/nutui-react': '@nutui/nutui-react-taro'
    },
    cache: {
      enable: false // Webpack 持久化缓存配置，建议开启。默认配置请参考：https://docs.taro.zone/docs/config-detail#cache
    },
    mini: {
      postcss: {
        pxtransform: {
          enable: true,
          config: {

          }
        },
        cssModules: {
          enable: false, // 默认为 false，如需使用 css modules 功能，则设为 true
          config: {
            namingPattern: 'module', // 转换模式，取值为 global/module
            generateScopedName: '[name]__[local]___[hash:base64:5]'
          }
        }
      },
      webpackChain(chain) {
        chain.resolve.plugin('tsconfig-paths').use(TsconfigPathsPlugin)
      }
    },
    h5: {
      publicPath: '/',
      staticDirectory: 'static',
      // FS8-P0 修复：terser 压缩产物运行时损坏（NutUI useCustomEventsPath 顶层
      // `new _Events` 有引用无定义 → ReferenceError 页面空白，仅 TabBar 渲染）。
      // 编译成功 ≠ 产物可用，E2E 冒烟抓得。切换 esbuild 压缩（BaseConfig L105 原生支持）。
      // esbuild 默认 target es5 不支持 const/let 降级（Transform failed 1233 errors），
      // 覆盖为 es2017（chromium / 微信 webview / 现代 H5 浏览器均支持）。
      // 根因实为 UMD 入口变形（见 baseConfig.alias 注记），压缩器无辜；
      // 二分排除记录：concatenateModules/usedExports 均非元凶，已回滚。
      // @ts-expect-error IH5Config 类型未声明 jsMinimizer（仅公共配置声明），
      // 但 H5 构建 Taro 会平铺合并 h5 段（运行时生效，esbuild 切换已实证）；
      // 上移顶层会连带切换 weapp 压缩管线（未验证），故原地保留。
      jsMinimizer: 'esbuild',
      esbuild: {
        minify: {
          config: {
            target: 'es2017'
          }
        }
      },
      output: {
        filename: 'js/[name].[hash:8].js',
        chunkFilename: 'js/[name].[chunkhash:8].js'
      },
      miniCssExtractPluginOption: {
        ignoreOrder: true,
        filename: 'css/[name].[hash].css',
        chunkFilename: 'css/[name].[chunkhash].css'
      },
      postcss: {
        autoprefixer: {
          enable: true,
          config: {}
        },
        cssModules: {
          enable: false, // 默认为 false，如需使用 css modules 功能，则设为 true
          config: {
            namingPattern: 'module', // 转换模式，取值为 global/module
            generateScopedName: '[name]__[local]___[hash:base64:5]'
          }
        }
      },
      webpackChain(chain) {
        chain.resolve.plugin('tsconfig-paths').use(TsconfigPathsPlugin)
        // FS7-P3: 关闭 devtool（source map）降低 sealing 阶段峰值内存。
        // （原 terserPlugin parallel:false OOM 缓解已随 jsMinimizer: 'esbuild' 切换移除，
        //  esbuild 单进程压缩无并行 worker 堆占用问题。）
        chain.devtool(false)
        // FS8-P0 修复：NutUI 必须走 ESM 入口。默认前缀 alias（config.alias 注入的
        // `@nutui/nutui-react` → 包名）先于精确 key 命中，包名再按 mainFields 解析到
        // main 字段的 UMD 入口（dist/nutui.react.umd.js）。UMD 工厂体内 Taro 为工厂
        // 参数（非 import 绑定），babel-plugin-transform-taroapi（plugin-platform-h5 给
        // babel-loader 注入，packageName='@tarojs/taro'，apis 集含 Events）对 `new Taro.Events()`
        // 做 rename 时无法关联到任何 import 声明 → 生成无定义自由变量 `new _Events()`
        // → 36 个 NutUI chunk 运行时 ReferenceError `_Events is not defined`
        // （页面空白仅 TabBar 渲染；ESM 路径的命名导入则 babel rename 与 webpack ESM
        // 接线自洽）。故删除前缀 key，改用 $ 精确匹配 + 绝对路径指向 ESM 索引。
        // weapp 端不受影响（本段仅 h5 构建执行）。
        const nutuiEsm = path.resolve(
          __dirname,
          '../node_modules/@nutui/nutui-react-taro/dist/esm/nutui-react.es.js'
        )
        // FS8-P0 修复收口：resolve.alias 玄学未命中（compiler.options 最终配置正确但
        // NutUI 仍解析到 UMD main），改用 NormalModuleReplacementPlugin 在
        // NormalModuleFactory beforeResolve 层直接重写 request（早于 resolve 全流程）。
        // 仅匹配裸名（-taro 可选后缀），不影响 app.ts 的 /dist/style.css 子路径样式。
        const webpack = require('webpack')
        chain.plugin('nutui-esm-replace').use(webpack.NormalModuleReplacementPlugin, [
          /^@nutui\/nutui-react(-taro)?$/,
          nutuiEsm,
        ])
        chain.optimization.set('concatenateModules', false)
      }
    }
  }

  if (process.env.NODE_ENV === 'development') {
    // 本地开发构建配置（不混淆压缩）
    return merge({}, baseConfig, devConfig)
  }
  // 生产构建配置（默认开启压缩混淆等）
  return merge({}, baseConfig, prodConfig)
})
