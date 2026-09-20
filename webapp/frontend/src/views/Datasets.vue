<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">数据集</h2>
        <p class="page-desc">
          数据集结构为 <span class="mono">&lt;目录&gt;/&lt;Palm_ID&gt;/&lt;图片&gt;</span>，支持
          <span class="mono">.png</span> 与 <span class="mono">_roi.png</span> 等后缀匹配
        </p>
      </div>
      <el-button :loading="loading" @click="loadAll">
        <el-icon><Refresh /></el-icon>
        <span style="margin-left: 4px">刷新</span>
      </el-button>
    </div>

    <!-- 仓库自带样本 -->
    <el-card shadow="never" class="mb-16" v-loading="suggestionLoading">
      <template #header>
        <span class="section-title" style="margin: 0">
          <el-icon><Star /></el-icon> 推荐数据集（仓库自带样本）
        </span>
      </template>

      <div v-if="suggestions.length" class="card-grid grid-2">
        <div v-for="item in suggestions" :key="item.path" class="suggest-card">
          <div class="suggest-main">
            <div class="suggest-name">
              {{ item.name }}
              <el-tag v-if="item.registered" size="small" type="success" effect="light">已登记</el-tag>
            </div>
            <div class="suggest-path mono">{{ item.path }}</div>
            <div class="text-secondary" style="font-size: 12px">
              {{ item.n_classes }} 个类别 · {{ item.n_images }} 张样本
            </div>
            <div class="suggest-thumbs">
              <el-image
                v-for="(sample, index) in item.samples || []"
                :key="index"
                class="suggest-thumb"
                :src="fileUrl(sample)"
                :preview-src-list="(item.samples || []).map(fileUrl)"
                :initial-index="index"
                fit="cover"
                preview-teleported
              />
            </div>
          </div>
          <el-button
            type="primary"
            size="small"
            :disabled="item.registered"
            @click="oneClickRegister(item)"
          >
            {{ item.registered ? '已登记' : '一键登记' }}
          </el-button>
        </div>
      </div>
      <el-empty v-else description="未找到仓库自带的样本目录" :image-size="70" />
    </el-card>

    <!-- 登记表单 -->
    <el-card shadow="never" class="mb-16">
      <template #header>
        <span class="section-title" style="margin: 0"><el-icon><Plus /></el-icon> 登记新数据集</span>
      </template>

      <el-form :model="form" label-width="110px" class="register-form">
        <el-row :gutter="16">
          <el-col :xs="24" :md="12">
            <el-form-item label="名称" required>
              <el-input v-model="form.name" placeholder="例如 ntust-hp-roi" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :md="12">
            <el-form-item label="识别后缀">
              <el-input v-model="form.image_extension" style="width: 180px">
                <template #append>
                  <el-tooltip content="填 _roi.png 时只匹配 ROI 结果文件" placement="top">
                    <el-icon><QuestionFilled /></el-icon>
                  </el-tooltip>
                </template>
              </el-input>
              <span class="text-secondary" style="margin-left: 8px; font-size: 12px">
                默认 <span class="mono">.png</span>，也可填 <span class="mono">_roi.png</span>
              </span>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="路径" required>
          <el-input v-model="form.path" placeholder="绝对路径，或相对项目根的路径">
            <template #append>
              <el-button @click="browserVisible = true">
                <el-icon><FolderOpened /></el-icon>
                <span style="margin-left: 4px">浏览</span>
              </el-button>
            </template>
          </el-input>
        </el-form-item>

        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="可选" />
        </el-form-item>

        <el-form-item>
          <el-button :loading="scanning" :disabled="!form.path" @click="previewScan">
            <el-icon><View /></el-icon>
            <span style="margin-left: 4px">预览扫描</span>
          </el-button>
          <el-button type="primary" :loading="creating" :disabled="!form.name || !form.path" @click="createDataset">
            <el-icon><Check /></el-icon>
            <span style="margin-left: 4px">登记数据集</span>
          </el-button>
        </el-form-item>
      </el-form>

      <el-alert
        v-if="scanResult"
        :type="scanResult.n_images ? 'success' : 'warning'"
        show-icon
        :closable="false"
        :title="`扫描到 ${scanResult.n_classes} 个类别 / ${scanResult.n_images} 张样本`"
      >
        <div class="scan-preview">
          <div v-for="cls in (scanResult.classes || []).slice(0, 6)" :key="cls.label" class="scan-class">
            <span class="mono">{{ cls.label }}</span>
            <span class="text-secondary">{{ cls.count }} 张</span>
          </div>
          <span v-if="(scanResult.classes || []).length > 6" class="text-secondary">
            等 {{ scanResult.classes.length }} 个类别…
          </span>
        </div>
      </el-alert>
    </el-card>

    <!-- 数据集列表 -->
    <el-card shadow="never">
      <template #header>
        <span class="section-title" style="margin: 0"><el-icon><Files /></el-icon> 已登记数据集</span>
      </template>

      <el-table :data="datasets" v-loading="loading">
        <el-table-column prop="name" label="名称" min-width="160" show-overflow-tooltip />
        <el-table-column label="路径" min-width="240">
          <template #default="{ row }">
            <span class="mono text-break">{{ row.path }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="n_classes" label="类别数" width="90" />
        <el-table-column prop="n_images" label="样本数" width="100" />
        <el-table-column prop="image_extension" label="后缀" width="110">
          <template #default="{ row }"><span class="mono">{{ row.image_extension }}</span></template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="210" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="refreshOne(row)">刷新统计</el-button>
            <el-button link type="primary" @click="openClasses(row)">查看类别</el-button>
            <el-button link type="danger" @click="removeOne(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="还没有登记数据集，可一键登记上方推荐样本" :image-size="80" />
        </template>
      </el-table>
    </el-card>

    <!-- 类别抽屉 -->
    <el-drawer v-model="classesVisible" :title="`类别明细 · ${currentDataset?.name || ''}`" size="640px">
      <div v-loading="classesLoading">
        <div v-if="classes.length" class="classes-toolbar">
          <span class="text-secondary" style="font-size: 12px">共 {{ classes.length }} 个 Palm_ID</span>
          <el-pagination
            v-model:current-page="classPage"
            :page-size="classPageSize"
            :total="classes.length"
            layout="prev, pager, next"
            small
          />
        </div>

        <div v-for="cls in pagedClasses" :key="cls.label" class="class-item">
          <div class="class-head">
            <el-tag size="small" effect="plain">{{ cls.label }}</el-tag>
            <span class="text-secondary" style="font-size: 12px">{{ cls.count }} 张样本</span>
          </div>
          <div class="class-thumbs">
            <el-image
              v-for="(sample, index) in cls.samples || []"
              :key="index"
              class="class-thumb"
              :src="fileUrl(sample)"
              :preview-src-list="(cls.samples || []).map(fileUrl)"
              :initial-index="index"
              fit="cover"
              preview-teleported
              lazy
            />
          </div>
        </div>

        <el-empty v-if="!classesLoading && !classes.length" description="该数据集没有可展示的类别" />
      </div>
    </el-drawer>

    <!-- 目录浏览抽屉 -->
    <el-drawer v-model="browserVisible" title="选择服务器目录" size="520px">
      <div class="browser-head">
        <el-button size="small" :disabled="!browseData.parent" @click="browseTo(browseData.parent)">
          <el-icon><Top /></el-icon>
          <span style="margin-left: 4px">上级</span>
        </el-button>
        <el-input v-model="browsePath" size="small" @keyup.enter="browseTo(browsePath)">
          <template #append>
            <el-button @click="browseTo(browsePath)">跳转</el-button>
          </template>
        </el-input>
      </div>
      <div class="browser-current mono">{{ browseData.path }}</div>
      <div v-loading="browseLoading" class="browser-body">
        <div
          v-for="dir in browseData.dirs || []"
          :key="dir.path"
          class="browser-item"
          @click="browseTo(dir.path)"
        >
          <el-icon><Folder /></el-icon>
          <span class="browser-name">{{ dir.name }}</span>
          <el-icon class="browser-arrow"><ArrowRight /></el-icon>
        </div>
        <el-empty v-if="!(browseData.dirs || []).length" description="没有子目录" />
      </div>
      <template #footer>
        <el-button @click="browserVisible = false">取消</el-button>
        <el-button type="primary" @click="pickCurrentDir">使用当前目录</el-button>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { datasetApi, systemApi, fileUrl, formatTime } from '@/api'

const loading = ref(false)
const datasets = ref([])
const suggestions = ref([])
const suggestionLoading = ref(false)
const scanning = ref(false)
const creating = ref(false)
const scanResult = ref(null)

const form = reactive({ name: '', path: '', image_extension: '.png', description: '' })

const classesVisible = ref(false)
const classesLoading = ref(false)
const classes = ref([])
const currentDataset = ref(null)
const classPage = ref(1)
const classPageSize = 6

const browserVisible = ref(false)
const browseLoading = ref(false)
const browsePath = ref('')
const browseData = reactive({ path: '', parent: null, dirs: [], files: [] })

const pagedClasses = computed(() => {
  const start = (classPage.value - 1) * classPageSize
  return classes.value.slice(start, start + classPageSize)
})

async function loadDatasets() {
  loading.value = true
  try {
    const data = await datasetApi.list()
    datasets.value = data.items || []
  } finally {
    loading.value = false
  }
}

async function loadSuggestions() {
  suggestionLoading.value = true
  try {
    const data = await datasetApi.suggestions()
    suggestions.value = data.items || []
  } catch (err) {
    suggestions.value = []
  } finally {
    suggestionLoading.value = false
  }
}

async function loadAll() {
  await Promise.all([loadDatasets(), loadSuggestions()])
}

async function oneClickRegister(item) {
  try {
    await datasetApi.create({
      name: item.name,
      path: item.path,
      image_extension: '.png',
      description: '仓库自带参考样本'
    })
    ElMessage.success(`已登记数据集 ${item.name}`)
    loadAll()
  } catch (err) {
    /* 已提示 */
  }
}

async function previewScan() {
  if (!form.path) return
  scanning.value = true
  try {
    scanResult.value = await datasetApi.scan(form.path, form.image_extension || '.png')
    ElMessage.success(`扫描完成：${scanResult.value.n_classes} 类 / ${scanResult.value.n_images} 张`)
  } catch (err) {
    scanResult.value = null
  } finally {
    scanning.value = false
  }
}

async function createDataset() {
  creating.value = true
  try {
    await datasetApi.create({
      name: form.name.trim(),
      path: form.path.trim(),
      image_extension: form.image_extension || '.png',
      description: form.description
    })
    ElMessage.success('数据集登记成功')
    form.name = ''
    form.path = ''
    form.description = ''
    scanResult.value = null
    loadAll()
  } finally {
    creating.value = false
  }
}

async function refreshOne(row) {
  const updated = await datasetApi.refresh(row.id)
  Object.assign(row, updated)
  ElMessage.success(`已刷新：${updated.n_classes} 类 / ${updated.n_images} 张`)
}

async function openClasses(row) {
  currentDataset.value = row
  classesVisible.value = true
  classPage.value = 1
  classesLoading.value = true
  try {
    const data = await datasetApi.classes(row.id, 6)
    classes.value = data.items || []
  } finally {
    classesLoading.value = false
  }
}

async function removeOne(row) {
  try {
    await ElMessageBox.confirm(`确定删除数据集「${row.name}」？`, '删除确认', { type: 'warning' })
  } catch (err) {
    return
  }
  await datasetApi.remove(row.id)
  ElMessage.success('已删除')
  loadAll()
}

async function browseTo(path) {
  if (!path) return
  browseLoading.value = true
  try {
    const data = await systemApi.browse(path)
    browseData.path = data.path
    browseData.parent = data.parent
    browseData.dirs = data.dirs || []
    browseData.files = data.files || []
    browsePath.value = data.path
  } catch (err) {
    /* 已提示 */
  } finally {
    browseLoading.value = false
  }
}

function pickCurrentDir() {
  form.path = browseData.path
  browserVisible.value = false
}

watch(browserVisible, (value) => {
  if (value) browseTo(browseData.path || '')
})

onMounted(loadAll)
</script>

<style scoped>
.suggest-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  border: 1px solid #e4e7ed;
  border-radius: 10px;
  padding: 14px;
}

.suggest-main {
  min-width: 0;
}

.suggest-name {
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.suggest-path {
  font-size: 12px;
  color: #909399;
  word-break: break-all;
  margin-bottom: 4px;
}

.suggest-thumbs {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.suggest-thumb {
  width: 56px;
  height: 56px;
  border-radius: 6px;
  border: 1px solid #e4e7ed;
}

.register-form {
  max-width: 900px;
}

.scan-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 6px;
}

.scan-class {
  display: flex;
  gap: 6px;
  font-size: 12px;
}

.classes-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.class-item {
  border: 1px solid #e4e7ed;
  border-radius: 10px;
  padding: 12px;
  margin-bottom: 12px;
}

.class-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.class-thumbs {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(78px, 1fr));
  gap: 8px;
}

.class-thumb {
  width: 100%;
  aspect-ratio: 1 / 1;
  border-radius: 6px;
  border: 1px solid #e4e7ed;
}

.browser-head {
  display: flex;
  gap: 8px;
  align-items: center;
}

.browser-current {
  margin: 10px 0;
  font-size: 12px;
  color: #909399;
  word-break: break-all;
}

.browser-body {
  max-height: calc(100vh - 240px);
  overflow-y: auto;
}

.browser-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}

.browser-item:hover {
  background: #f5f7fa;
}

.browser-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.browser-arrow {
  color: #c0c4cc;
}
</style>
