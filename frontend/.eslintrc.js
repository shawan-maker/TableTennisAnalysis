/**
 * FS8-8 lint 配置——§2.3 红线可自动化子集 + jsx-a11y（Taro 组件映射）
 *
 * 红线映射：
 * 1 禁止 class 组件 → react/function-component-definition（error）
 * 8 无障碍 ARIA → jsx-a11y/recommended + Taro 组件 components 映射
 *   （View→div / Text→span / Image→img 等，否则规则只认原生标签）
 *
 * 红线 2/3（CSS 变量 / t() 化）与 4/5/6/7 属评审与既有 Jest 守卫范畴
 * （i18nKeys 测试 = 红线 3 CI；Service 契约镜像 = 契约测试 CI），
 * eslint 无法静态可靠判定，不在本配置强行落地（评审基线 + 既有测试守卫）。
 */
module.exports = {
  root: true,
  parser: '@typescript-eslint/parser',
  parserOptions: {
    ecmaVersion: 2021,
    sourceType: 'module',
    ecmaFeatures: { jsx: true },
  },
  env: {
    browser: true,
    es2021: true,
    node: true,
  },
  settings: {
    react: { version: 'detect' },
    // Taro 组件 → HTML 语义映射（jsx-a11y 规则对自定义标签默认不生效）
    'jsx-a11y': {
      components: {
        View: 'div',
        Text: 'span',
        Image: 'img',
        Input: 'input',
        Textarea: 'textarea',
        Button: 'button',
        Label: 'label',
        Radio: 'input',
        Checkbox: 'input',
        Switch: 'input',
        Slider: 'input',
        Picker: 'select',
        Form: 'form',
        ScrollView: 'div',
        Swiper: 'div',
        WebView: 'iframe',
        Canvas: 'canvas',
        Video: 'video',
        Navigator: 'a',
      },
    },
  },
  plugins: ['react', 'react-hooks', 'jsx-a11y', '@typescript-eslint'],
  extends: [
    'eslint:recommended',
    'plugin:react/recommended',
    'plugin:react-hooks/recommended',
    'plugin:jsx-a11y/recommended',
    'plugin:@typescript-eslint/recommended',
  ],
  rules: {
    // ── 红线 1：函数组件 ──
    'react/function-component-definition': [
      'error',
      { namedComponents: 'function-declaration', unnamedComponents: 'function-expression' },
    ],
    // ── Hooks 正确性（CI 阻塞）──
    'react-hooks/rules-of-hooks': 'error',
    'react-hooks/exhaustive-deps': 'warn',
    // ── TS 严格度对齐 tsconfig（noImplicitAny: false → 不阻塞 any；
    //    未用变量由 tsc noUnusedLocals/Parameters 守卫）──
    '@typescript-eslint/no-explicit-any': 'off',
    '@typescript-eslint/no-unused-vars': 'warn',
    // ── React/TS 工程适配 ──
    'react/prop-types': 'off', // TS interface 已覆盖
    'react/display-name': 'off',
    'react/react-in-jsx-scope': 'off', // Taro 自动注入
    '@typescript-eslint/no-var-requires': 'off', // Taro config/jest 生态 CJS
    '@typescript-eslint/ban-ts-comment': 'warn',
    // ── jsx-a11y 分级（Taro 无键盘焦点的可点击容器按 warn 记账不阻塞——
    //    交互面键盘可达性由 axe 扫描（FS8-7）与真机验收覆盖）──
    'jsx-a11y/click-events-have-key-events': 'warn',
    'jsx-a11y/no-static-element-interactions': 'warn',
    'jsx-a11y/no-noninteractive-element-interactions': 'warn',
    // weapp Video 组件无 <track> 字幕 API（平台能力缺失，Taro 不转发字幕轨道）；
    // 标注回放是用户自传视频的 AI 叠加演示，无旁白音轨。H5 侧 Taro Video 同
    // 不渲染 track。真机验收（FS8-11）覆盖播放可达性。
    'jsx-a11y/media-has-caption': 'off',
  },
  ignorePatterns: ['dist/', 'node_modules/', 'coverage/', 'lib/', '*.d.ts'],
  overrides: [
    {
      files: ['**/__tests__/**/*.ts?(x)', '**/*.test.ts?(x)'],
      env: { jest: true },
      rules: {
        // 测试内 mock/断言宽松
        '@typescript-eslint/no-non-null-assertion': 'off',
      },
    },
    {
      files: ['e2e/**/*.ts'],
      env: { node: true, jest: false },
      rules: {
        'no-console': 'off', // E2E 探针输出
      },
    },
  ],
}
