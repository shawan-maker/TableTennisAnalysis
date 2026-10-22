# 垂直切片开发 — 前端模板

> 本模板指导前端切片的完整开发流程：准备 → 实现 → 验证。
> 前置依赖：必须先阅读 `00-common-conventions.md`。

---

## 1. 切片准备清单

- [ ] 阅读本模块的功能规格书
- [ ] 阅读本切片的 API 契约（接口路径、请求/响应格式）
- [ ] 阅读设计系统规范（`templates/02-design-system.md`）
- [ ] 阅读 **至少一个** 已有类似页面：
  - `frontend/src/views/test/DefectListView.vue` — 列表页参考
  - `frontend/src/views/test/DefectDetailView.vue` — 详情页参考
  - `frontend/src/api/apiTest.js` — API 模块参考
- [ ] 确认本切片范围（哪些页面 + 哪些 API 调用）

---

## 2. API 模块

```javascript
// frontend/src/api/{module}.js
import request from '@/utils/request'

/**
 * 获取{资源}列表。
 * @param {Object} params - 查询参数
 * @param {number} params.project_id - 项目ID（必填）
 * @param {number} [params.page=1] - 页码
 * @param {number} [params.page_size=20] - 每页条数
 * @param {string} [params.q] - 搜索关键词
 * @param {string} [params.status] - 状态筛选
 */
export function listMyEntities(params = {}) {
  return request.get('/my-entities', {
    params: { page: 1, page_size: 20, ...params },
  })
}

/** 获取详情。 */
export function getMyEntity(id) {
  return request.get(`/my-entities/${id}`)
}

/** 创建。 */
export function createMyEntity(data) {
  return request.post('/my-entities', data)
}

/** 更新。 */
export function updateMyEntity(id, data) {
  return request.patch(`/my-entities/${id}`, data)
}

/** 删除。 */
export function deleteMyEntity(id) {
  return request.delete(`/my-entities/${id}`)
}

/** 批量删除。 */
export function batchDeleteMyEntities(ids) {
  return request.post('/my-entities/batch-delete', { ids })
}
```

**注册到 index.js**：
```javascript
// frontend/src/api/index.js
export * from './myModule'  // 新增
```

---

## 3. 列表页模板

```vue
<!--
  {模块名}列表页。
  布局：列表页模板（见 02-design-system.md 第8.1节）
  功能：列表展示、搜索筛选、CRUD 操作
  API：{后端模块} API
-->
<template>
  <div class="{view-name} app-card">
    <!-- 页面标题 -->
    <PageHeader :title="t('page.{module}.title')" />

    <!-- 搜索筛选区 -->
    <FilterBar @search="load" @reset="resetFilters">
      <template #primary>
        <el-button type="primary" :disabled="!canEdit" @click="openCreate">
          {{ t('common.create') }}
        </el-button>
      </template>
      <el-input v-model="filters.q"
                :placeholder="t('common.searchPlaceholder')" clearable />
      <el-select v-model="filters.status"
                 :placeholder="t('page.{module}.statusFilter')" clearable>
        <el-option v-for="(v, k) in STATUS_MAP" :key="k"
                   :label="v.label" :value="k" />
      </el-select>
    </FilterBar>

    <!-- 数据表格 -->
    <PaginatedTable
      v-model:page="page" v-model:page-size="pageSize"
      :data="items" :loading="loading" :total="total"
      @page-change="load" @size-change="load"
    >
      <AppTableColumn prop="name" variant="content"
                      :label="t('common.name')" />
      <AppTableColumn prop="status" variant="fixed"
                      :label="t('common.status')" :width="120">
        <template #default="{ row }">
          <StatusTag :status="row.status" :map="STATUS_MAP" />
        </template>
      </AppTableColumn>
      <AppTableColumn prop="created_at" variant="fixed"
                      :label="t('common.createdAt')" :width="180" />
      <AppTableColumn actions variant="fixed"
                      :label="t('common.actions')" :width="200">
        <template #default="{ row }">
          <el-button link type="primary" @click="goDetail(row)">
            {{ t('common.view') }}
          </el-button>
          <el-button link type="primary" :disabled="!canEdit"
                     @click="openEdit(row)">
            {{ t('common.edit') }}
          </el-button>
          <ConfirmDelete @confirm="remove(row)">
            <el-button link type="danger" :disabled="!canEdit">
              {{ t('common.delete') }}
            </el-button>
          </ConfirmDelete>
        </template>
      </AppTableColumn>
    </PaginatedTable>

    <!-- 创建/编辑弹窗 -->
    <MyFormDialog v-model="dialogVisible" :item="editItem" @submit="save" />
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'

import { listMyEntities, deleteMyEntity } from '@/api/myModule'
import { usePagination } from '@/composables/usePagination'
import { usePermission } from '@/composables/usePermission'
import { MY_ENTITY_STATUS_MAP } from '@/utils/constants'

import PageHeader from '@/components/common/PageHeader.vue'
import FilterBar from '@/components/common/FilterBar.vue'
import PaginatedTable from '@/components/common/PaginatedTable.vue'
import AppTableColumn from '@/components/common/AppTableColumn.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import ConfirmDelete from '@/components/common/ConfirmDelete.vue'

const { t } = useI18n()
const router = useRouter()
const { canEdit } = usePermission()
const { page, pageSize, total } = usePagination()

const filters = reactive({ q: '', status: '' })
const items = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const editItem = ref(null)

/** 加载列表数据。 */
async function load() {
  loading.value = true
  try {
    const res = await listMyEntities({
      page: page.value,
      page_size: pageSize.value,
      q: filters.q || undefined,
      status: filters.status || undefined,
    })
    items.value = res.data.data?.items ?? []
    total.value = res.data.data?.total ?? 0
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  filters.q = ''
  filters.status = ''
  load()
}

function openCreate() {
  editItem.value = null
  dialogVisible.value = true
}

function openEdit(row) {
  editItem.value = { ...row }
  dialogVisible.value = true
}

async function save(data) {
  if (editItem.value?.id) {
    await updateMyEntity(editItem.value.id, data)
  } else {
    await createMyEntity(data)
  }
  ElMessage.success(t('common.saved'))
  dialogVisible.value = false
  load()
}

async function remove(row) {
  await deleteMyEntity(row.id)
  ElMessage.success(t('common.deleted'))
  load()
}

function goDetail(row) {
  router.push({ name: 'MyEntityDetail', params: { id: row.id } })
}

onMounted(load)
</script>
```

---

## 4. 详情页模板（简要）

```vue
<template>
  <div class="{view-name}-detail app-card">
    <PageHeader :title="detail.name || t('page.{module}.detail')" />

    <!-- 基础信息 -->
    <el-descriptions :column="2" border>
      <el-descriptions-item :label="t('common.name')">{{ detail.name }}</el-descriptions-item>
      <el-descriptions-item :label="t('common.status')">
        <StatusTag :status="detail.status" :map="STATUS_MAP" />
      </el-descriptions-item>
      <el-descriptions-item :label="t('common.createdAt')">{{ formatDateTime(detail.created_at) }}</el-descriptions-item>
    </el-descriptions>

    <!-- Tab 切换区 -->
    <el-tabs v-model="activeTab">
      <el-tab-pane :label="t('page.{module}.tab1')" name="tab1">
        <!-- Tab 内容 -->
      </el-tab-pane>
    </el-tabs>
  </div>
</template>
```

---

## 5. 表单弹窗模板

```vue
<template>
  <el-dialog v-model="visible" :title="isEdit ? t('common.edit') : t('common.create')"
             width="640px" @close="handleClose">
    <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
      <el-form-item :label="t('common.name')" prop="name">
        <el-input v-model="form.name" :maxlength="255" show-word-limit />
      </el-form-item>
      <el-form-item :label="t('common.description')" prop="description">
        <el-input v-model="form.description" type="textarea" :rows="3" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">{{ t('common.cancel') }}</el-button>
      <el-button type="primary" :loading="submitting" @click="handleSubmit">
        {{ t('common.save') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({ modelValue: Boolean, item: Object })
const emit = defineEmits(['update:modelValue', 'submit'])

const { t } = useI18n()
const formRef = ref(null)
const submitting = ref(false)

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const isEdit = computed(() => !!props.item?.id)

const form = ref({ name: '', description: '' })

const rules = {
  name: [{ required: true, message: () => t('validation.required'), trigger: 'blur' }],
}

watch(() => props.modelValue, (v) => {
  if (v && props.item) {
    form.value = { name: props.item.name, description: props.item.description }
  } else if (v) {
    form.value = { name: '', description: '' }
  }
})

async function handleSubmit() {
  await formRef.value.validate()
  submitting.value = true
  try {
    emit('submit', { ...form.value })
  } finally {
    submitting.value = false
  }
}

function handleClose() {
  formRef.value?.resetFields()
}
</script>
```

---

## 6. Composable 使用指南

| Composable | 用途 | 何时使用 |
|-----------|------|---------|
| `usePagination()` | 返回 `{ page, pageSize, total }` refs | 所有列表页 |
| `usePermission()` | 返回 `{ canEdit, canView, isOwner }` | 有编辑/删除操作的页面 |
| `useProjectScope()` | 返回 `{ projectId, requireProjectId }` | 项目范围内的页面 |
| `usePolling(fn, interval)` | 定时轮询 | 有异步操作需轮询状态的页面 |
| `useResizable()` | 拖拽调整大小 | SplitView 面板 |

---

## 7. 常量/枚举同步

在 `frontend/src/utils/constants.js` 中添加：

```javascript
export const MY_ENTITY_STATUS_MAP = {
  draft:     { type: 'info',    label: '草稿' },
  active:    { type: 'success', label: '启用' },
  archived:  { type: '',       label: '已归档' },
}
```

**type 映射**：`success`（绿）、`warning`（橙）、`info`（灰）、`danger`（红）、`primary`（蓝）、`''`（默认）

---

## 8. i18n 条目

```json
// zh-CN.json 新增
{
  "page": {
    "{module}": {
      "title": "{模块中文名}",
      "statusFilter": "按状态筛选",
      "detail": "{模块}详情"
    }
  }
}

// en-US.json 新增
{
  "page": {
    "{module}": {
      "title": "{Module English Name}",
      "statusFilter": "Filter by status",
      "detail": "{Module} Detail"
    }
  }
}
```

---

## 9. 路由配置

```javascript
// frontend/src/router/routes/{module}.js
export default [
  {
    path: '/my-module',
    name: 'MyModule',
    component: () => import('@/views/{module}/MyModuleListView.vue'),
    meta: { titleKey: 'menu.myModule', projectRequired: true },
  },
  {
    path: '/my-module/:id',
    name: 'MyModuleDetail',
    component: () => import('@/views/{module}/MyModuleDetailView.vue'),
    meta: { titleKey: 'menu.myModuleDetail', projectRequired: true },
  },
]
```

**meta 键说明**：
- `titleKey`：i18n 键，用于文档标题
- `projectRequired: true`：需要先选择项目
- `requiresAuth: true`：需要登录（通常由父路由设置）

---

## 10. 验证清单

### 构建验证
```bash
cd frontend && npx vite build --mode development
```

### 视觉验证
- [ ] 列表页布局符合设计系统模板（PageHeader + FilterBar + PaginatedTable）
- [ ] 表格列宽合理（长内容列自适应，短内容列固定宽度）
- [ ] 状态标签颜色正确（与 STATUS_MAP 一致）
- [ ] 空数据显示空状态组件（非空白页面）
- [ ] 分页器正常显示（有数据时显示，无数据时隐藏）
- [ ] 编辑/删除按钮在无权限时禁用

### 功能验证
- [ ] 搜索/筛选功能正常
- [ ] 创建/编辑弹窗打开和关闭正常
- [ ] 表单验证提示正确
- [ ] 删除确认弹窗正常
- [ ] 操作成功/失败提示正确

### i18n 验证
- [ ] 切换到英文后所有文本有翻译
- [ ] 无硬编码的中文/英文字符串

---

## 反幻觉约束

- **ALL** 列表页必须使用 `PageHeader` + `FilterBar` + `PaginatedTable` + `AppTableColumn` 组合，**禁止** 自建表格布局
- **ALL** API 函数必须使用 verb-noun 命名：`listX`, `getX`, `createX`, `updateX`, `deleteX`
- **ALL** 用户可见文本必须使用 `t('key')`，**禁止** 硬编码字符串
- **ALL** 项目范围内的页面必须使用 `useProjectScope()` 获取 projectId
- **禁止** 使用 Options API，只使用 `<script setup>`
- **禁止** 硬编码颜色值，使用 CSS 变量或 SCSS 变量
- **禁止** 安装新的 npm 包（除非现有包确实无法满足）
