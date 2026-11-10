/**
 * Jest 配置（04-前端实施计划.md §6.2 组件测试层）
 * - ts-jest 转译（项目 tsconfig：commonjs）
 * - node 环境（Store/Service/i18n 纯逻辑测试，页面渲染测试归 FS8 E2E）
 * - @/ 路径别名与 @tarojs/taro 手动 mock
 */
/** @type {import('jest').Config} */
module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  roots: ['<rootDir>/src'],
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
    '^@tarojs/taro$': '<rootDir>/test/mocks/taro.ts',
    // i18next CJS 无 default 导出：ts-jest interop 下 default import 为 undefined，
    // 任何 store/模块在测试环境引用 i18next 一律映射到手动 mock（test/mocks/i18next.ts）
    '^i18next$': '<rootDir>/test/mocks/i18next.ts',
  },
  testMatch: ['**/__tests__/**/*.test.ts'],
  clearMocks: true,
}
