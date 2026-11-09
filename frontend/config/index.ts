import { defineConfig, type UserConfigExport } from '@tarojs/cli'
import TsconfigPathsPlugin from 'tsconfig-paths-webpack-plugin'

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
    // （@nutui/nutui-react 4.x beta 无 taro 构建，故采用 2.7.14 taro 线 + alias 映射）
    alias: {
      '@nutui/nutui-react': '@nutui/nutui-react-taro',
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
        // FS7-P3: H5 生产构建 OOM 缓解（本机 FreeGB<5；Taro BaseConfig.setMinimizer 硬编码
        // TerserPlugin parallel:true，多 worker 各占独立堆 → Fatal process out of memory: Zone）。
        // webpackChain 回调在 setMinimizer 之后执行，此处将注册名 terserPlugin 的 minimizer
        // 改为单进程压缩；同时关闭 devtool（source map）降低 sealing 阶段峰值内存。
        chain.devtool(false)
        const terser = (chain.optimization as any).minimizers.get('terserPlugin')
        if (terser) {
          terser.tap((args: any[]) => {
            if (args[0]) args[0].parallel = false
            return args
          })
        }
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
