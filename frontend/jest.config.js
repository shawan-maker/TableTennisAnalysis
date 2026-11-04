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
  },
  testMatch: ['**/__tests__/**/*.test.ts'],
  clearMocks: true,
}
