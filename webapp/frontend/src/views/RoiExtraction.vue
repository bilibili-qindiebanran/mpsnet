<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">ROI 提取</h2>
        <p class="page-desc">
          基于 palmlib 提取掌脉感兴趣区域，输出可直接用于训练的数据集
        </p>
      </div>
      <el-tag :type="palmlibReady ? 'success' : 'warning'" effect="light" round size="large">
        {{ palmlibReady ? 'palmlib 已就绪' : 'palmlib 未编译' }}
      </el-tag>
    </div>

    <el-alert
      v-if="!palmlibReady"
      class="mb-16"
      type="warning"
      show-icon
      :closable="false"
      :title="roiStatus.message || 'ROI 模块未就绪，请先编译'"
    >
      <el-button type="primary" size="small" :loading="store.building" @click="buildModule">
        编译模块
      </el-button>
    </el-alert>

    <!-- 新建任务 -->
    <el-card shadow="never" class="mb-16">
      <template #header>
        <span class="section-title" style="margin: 0"><el-icon><Plus /></el-icon> 新建提取任务</span>
      </template>

      <el-tabs v-model="mode">
        <el-tab-pane label="上传图片" name="upload">
          <el-radio-group v-model="uploadMode" size="small" class="mb-12">
            <el-radio-button value="files">选择文件</el-radio-button>
            <el-radio-button value="folder">选择文件夹（保留目录结构）</el-radio-button>
          </el-radio-group>

          <template v-if="uploadMode === 'files'">
            <el-upload
              v-model:file-list="fileList"
              drag
              multiple
              :auto-upload="false"
              accept="image/*"
              :limit="500"
            >
              <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
              <div class="el-upload__text">将图片拖到此处，或<em>点击选择</em></div>
              <template #tip>
                <div class="el-upload__tip">
                  支持多选。若要保持 <span class="mono">Palm_ID/图片</span> 结构，请改用「选择文件夹」
                </div>
              </template>
            </el-upload>
          </template>

          <template v-else>
            <div class="folder-picker">
              <el-button type="primary" plain @click="triggerFolderInput">
                <el-icon><FolderOpened /></el-icon>
                <span style="margin-left: 4px">选择文件夹</span>
              </el-button>
              <span class="text-secondary" style="font-size: 12px">
                选择数据集根目录（内含 Palm_ID 子目录），提交时会自动去掉最外层目录名
              </span>
            </div>
            <input
              ref="folderInput"
              type="file"
              webkitdirectory
              directory
              multiple
              style="display: none"
              @change="onFolderChange"
            />
            <div v-if="folderFiles.length" class="mt-12">
              <el-alert
                type="info"
                :closable="false"
                show-icon
                :title="`已选择 ${folderFiles.length} 个文件，${folderPreview} 个类别`"
              />
              <el-table :data="folderFiles.slice(0, 20)" size="small" class="mt-12" max-height="240">
                <el-table-column label="相对路径" min-width="240">
                  <template #default="{ row }"><span class="mono">{{ row.relative }}</span></template>
                </el-table-column>
                <el-table-column label="大小" width="100">
                  <template #default="{ row }">{{ formatBytes(row.file.size) }}</template>
                </el-table-column>
              </el-table>
              <div v-if="folderFiles.length > 20" class="text-secondary mt-8" style="font-size: 12px">
                仅展示前 20 个文件
              </div>
            </div>
          </template>
        </el-tab-pane>

        <el-tab-pane label="服务器目录" name="server">
          <el-form label-width="110px" class="server-form">
            <el-form-item label="源路径">
              <el-input
                v-model="serverPath"
                placeholder="相对项目根目录，例如 Images/200_samples/ntust-hp（也可填绝对路径）"
                clearable
              >
                <template #append>
                  <el-button @click="browserVisible = true">
                    <el-icon><FolderOpened /></el-icon>
                    <span style="margin-left: 4px">浏览</span>
                  </el-button>
                </template>
              </el-input>
            </el-form-item>
            <el-form-item v-if="suggestions.length" label="快捷路径">
              <el-button
                v-for="item in suggestions"
                :key="item.path"
                size="small"
                plain
                @click="serverPath = item.path"
              >
                {{ item.name }}
                <span class="text-secondary" style="margin-left: 4px">
                  {{ item.n_classes }} 类 / {{ item.n_images }} 张
                </span>
              </el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>

      <el-divider />

      <el-form :inline="true" label-width="0">
        <el-form-item label="任务名称" class="mr-12">
          <el-input v-model="name" placeholder="留空则自动命名" style="width: 220px" />
        </el-form-item>
        <el-form-item label="ROI 边长" class="mr-12">
          <el-input-number v-model="roiSize" :min="32" :max="512" :step="16" />
        </el-form-item>
        <el-form-item>
          <el-tooltip content="开启后额外输出二值掩膜与裁剪手部图，统一存放到 xxx__debug 目录" placement="top">
            <span class="switch-label">保存调试图</span>
          </el-tooltip>
          <el-switch v-model="saveDebug" style="margin-left: 8px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="submit">
            <el-icon><MagicStick /></el-icon>
            <span style="margin-left: 4px">开始提取</span>
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 当前任务详情 -->
    <el-card v-if="currentJob" ref="detailCard" shadow="never" class="mb-16" v-loading="detailLoading">
      <template #header>
        <div class="card-header-row">
          <span class="section-title" style="margin: 0">
            <el-icon><Document /></el-icon> 任务 #{{ currentJob.id }} · {{ currentJob.name }}
          </span>
          <div class="row-gap">
            <JobStatusTag :status="currentJob.status" />
            <el-button
              size="small"
              type="success"
              plain
              :disabled="currentJob.status !== 'success'"
              @click="registerDialog = true"
            >
              <el-icon><Files /></el-icon>
              <span style="margin-left: 4px">登记为数据集</span>
            </el-button>
            <el-button size="small" @click="closeDetail">关闭</el-button>
          </div>
        </div>
      </template>

      <el-descriptions :column="3" border size="small" class="mb-16">
        <el-descriptions-item label="来源类型">
          {{ currentJob.source_type === 'upload' ? '上传图片' : '服务器路径' }}
        </el-descriptions-item>
        <el-descriptions-item label="ROI 边长">{{ currentJob.roi_size }}</el-descriptions-item>
        <el-descriptions-item label="保存调试图">
          {{ currentJob.save_debug ? '是' : '否' }}
        </el-descriptions-item>
        <el-descriptions-item label="输出目录" :span="2">
          <span class="mono text-break">{{ currentJob.output_dir }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="完成时间">
          {{ formatTime(currentJob.finished_at) }}
        </el-descriptions-item>
        <el-descriptions-item label="源路径" :span="3">
          <span class="mono text-break">{{ currentJob.source_path }}</span>
        </el-descriptions-item>
      </el-descriptions>

      <el-progress
        v-if="isActive"
        :percentage="progressPercent"
        :stroke-width="14"
        striped
        striped-flow
        class="mb-16"
      />
      <div class="stat-row mb-16">
        <el-statistic title="总数" :value="currentJob.total || 0" />
        <el-statistic title="成功" :value="currentJob.succeeded || 0" value-style="color:#67c23a" />
        <el-statistic title="失败" :value="currentJob.failed || 0" value-style="color:#f56c6c" />
        <el-statistic title="已生成结果" :value="(currentJob.results || []).length" />
      </div>

      <el-alert
        v-if="currentJob.error"
        type="error"
        show-icon
        :closable="false"
        :title="currentJob.error"
        class="mb-16"
      />

      <template v-if="(currentJob.results || []).length">
        <h4 class="section-title"><el-icon><Picture /></el-icon> 四图对比</h4>
        <el-select v-model="selectedIndex" class="mb-12" style="width: 320px" filterable>
          <el-option
            v-for="(item, index) in currentJob.results"
            :key="index"
            :label="`${item.label} / ${item.stem}`"
            :value="index"
          />
        </el-select>
        <ImageCompare
          v-if="activeResult"
          :items="[
            { key: 'original', label: '原图', path: activeResult.original },
            { key: 'roi', label: 'ROI', path: activeResult.roi },
            { key: 'binary', label: '二值掩膜', path: activeResult.binary },
            { key: 'crop', label: '裁剪手部图', path: activeResult.crop }
          ]"
        />

        <el-divider />
        <h4 class="section-title"><el-icon><Grid /></el-icon> 结果画廊</h4>
        <ResultGallery :results="currentJob.results" />
      </template>

      <el-divider />
      <h4 class="section-title"><el-icon><Tickets /></el-icon> 运行日志</h4>
      <pre class="log-view" style="max-height: 260px">{{ currentJob.log || '暂无日志' }}</pre>
    </el-card>

    <!-- 历史任务 -->
    <el-card shadow="never">
      <template #header>
        <div class="card-header-row">
          <span class="section-title" style="margin: 0"><el-icon><Clock /></el-icon> 历史任务</span>
          <el-button size="small" text type="primary" :loading="listLoading" @click="loadJobs">
            刷新
          </el-button>
        </div>
      </template>

      <el-table :data="jobs" v-loading="listLoading">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="任务名" min-width="160" show-overflow-tooltip />
        <el-table-column label="来源" width="100">
          <template #default="{ row }">
            {{ row.source_type === 'upload' ? '上传' : '服务器' }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }"><JobStatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="进度" width="200">
          <template #default="{ row }">
            <el-progress
              :percentage="percentOf(row)"
              :stroke-width="10"
              :status="row.status === 'failed' ? 'exception' : undefined"
            />
          </template>
        </el-table-column>
        <el-table-column label="成功/总数" width="110">
          <template #default="{ row }">{{ row.succeeded }} / {{ row.total }}</template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openJob(row.id)">查看</el-button>
            <el-button link type="danger" @click="removeJob(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="还没有 ROI 提取任务，先在上方提交一个吧" :image-size="80" />
        </template>
      </el-table>
    </el-card>

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
        <div v-if="browseData.dirs?.length" class="browser-section-title">子目录</div>
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
        <div v-if="browseData.files?.length" class="browser-section-title">图片文件</div>
        <div v-for="file in browseData.files || []" :key="file.path" class="browser-item is-file">
          <el-icon><Picture /></el-icon>
          <span class="browser-name">{{ file.name }}</span>
        </div>
        <el-empty v-if="!(browseData.dirs?.length || browseData.files?.length)" description="空目录" />
      </div>
      <template #footer>
        <el-button @click="browserVisible = false">取消</el-button>
        <el-button type="primary" @click="pickCurrentDir">使用当前目录</el-button>
      </template>
    </el-drawer>

    <!-- 登记数据集 -->
    <el-dialog v-model="registerDialog" title="登记为数据集" width="520px">
      <el-form label-width="110px">
        <el-form-item label="数据集名称" required>
          <el-input v-model="registerForm.name" placeholder="例如 ntust-hp-roi" />
        </el-form-item>
        <el-form-item label="目录">
          <el-input :model-value="currentJob?.output_dir" disabled />
        </el-form-item>
        <el-form-item label="识别后缀">
          <el-input v-model="registerForm.image_extension" style="width: 160px" />
          <span class="text-secondary" style="margin-left: 8px; font-size: 12px">
            ROI 结果文件为 <span class="mono">*_roi.png</span>，可填 <span class="mono">_roi.png</span>
            只匹配 ROI
          </span>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="registerForm.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="registerDialog = false">取消</el-button>
        <el-button type="primary" :loading="registering" @click="registerDataset">登记</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useSystemStore } from '@/stores/system'
import { roiApi, datasetApi, systemApi, formatBytes, formatTime } from '@/api'
import JobStatusTag from '@/components/JobStatusTag.vue'
import ImageCompare from '@/components/ImageCompare.vue'
import ResultGallery from '@/components/ResultGallery.vue'

const store = useSystemStore()
const { roiStatus } = storeToRefs(store)

const palmlibReady = computed(() => Boolean(roiStatus.value?.ready))

const mode = ref('server')
const uploadMode = ref('files')
const fileList = ref([])
const folderFiles = ref([])
const folderInput = ref(null)
const serverPath = ref('')
const suggestions = ref([])

const name = ref('')
const roiSize = ref(128)
const saveDebug = ref(false)
const submitting = ref(false)

const jobs = ref([])
const listLoading = ref(false)
const currentJob = ref(null)
const detailLoading = ref(false)
const selectedIndex = ref(0)
const detailCard = ref(null)
let pollTimer = null

const browserVisible = ref(false)
const browseLoading = ref(false)
const browsePath = ref('')
const browseData = reactive({ path: '', parent: null, dirs: [], files: [] })

const registerDialog = ref(false)
const registering = ref(false)
const registerForm = reactive({ name: '', image_extension: '.png', description: '' })

const isActive = computed(
  () => currentJob.value && ['pending', 'running'].includes(currentJob.value.status)
)

const progressPercent = computed(() => percentOf(currentJob.value || {}))

const activeResult = computed(() => {
  const results = currentJob.value?.results || []
  return results[selectedIndex.value] || results[0] || null
})

const folderPreview = computed(() => {
  const labels = new Set()
  folderFiles.value.forEach((item) => {
    const parts = item.relative.split('/')
    if (parts.length > 1) labels.add(parts[0])
  })
  return labels.size
})

function percentOf(row) {
  const total = row?.total || 0
  if (!total) return row?.status === 'success' ? 100 : 0
  const done = (row.succeeded || 0) + (row.failed || 0)
  return Math.min(100, Math.round((done / total) * 100))
}

async function buildModule() {
  try {
    const result = await store.buildPalmlib()
    ElMessage.success(result.message || '编译成功')
  } catch (err) {
    /* 已提示 */
  }
}

function triggerFolderInput() {
  folderInput.value?.click()
}

function onFolderChange(event) {
  const files = Array.from(event.target.files || [])
  folderFiles.value = files.map((file) => {
    const raw = file.webkitRelativePath || file.name
    const parts = raw.split('/')
    // 去掉最外层被选中的目录名，得到 Palm_ID/图片 结构
    const relative = parts.length > 1 ? parts.slice(1).join('/') : raw
    return { file, relative }
  })
  if (!folderFiles.value.length) ElMessage.warning('未选择到文件')
  event.target.value = ''
}

async function submit() {
  try {
    if (mode.value === 'server') {
      if (!serverPath.value.trim()) {
        ElMessage.warning('请填写服务器源路径')
        return
      }
      submitting.value = true
      const job = await roiApi.extract({
        name: name.value || 'ROI 提取',
        source_path: serverPath.value.trim(),
        roi_size: roiSize.value,
        save_debug: saveDebug.value
      })
      await afterSubmit(job)
    } else if (uploadMode.value === 'files') {
      const files = fileList.value.map((item) => item.raw).filter(Boolean)
      if (!files.length) {
        ElMessage.warning('请先选择图片')
        return
      }
      submitting.value = true
      const job = await roiApi.upload({
        files,
        name: name.value || '上传图片提取',
        roi_size: roiSize.value,
        save_debug: saveDebug.value,
        relative_paths: files.map((file) => file.name)
      })
      fileList.value = []
      await afterSubmit(job)
    } else {
      if (!folderFiles.value.length) {
        ElMessage.warning('请先选择文件夹')
        return
      }
      submitting.value = true
      const job = await roiApi.upload({
        files: folderFiles.value.map((item) => item.file),
        name: name.value || '上传文件夹提取',
        roi_size: roiSize.value,
        save_debug: saveDebug.value,
        relative_paths: folderFiles.value.map((item) => item.relative)
      })
      folderFiles.value = []
      await afterSubmit(job)
    }
  } catch (err) {
    /* 已提示 */
  } finally {
    submitting.value = false
  }
}

async function afterSubmit(job) {
  ElMessage.success(`任务 #${job.id} 已提交`)
  currentJob.value = job
  selectedIndex.value = 0
  await loadJobs()
  scrollToDetail()
  startPolling(job.id)
}

function scrollToDetail() {
  setTimeout(() => {
    detailCard.value?.$el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, 80)
}

function startPolling(id) {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      const job = await roiApi.job(id)
      currentJob.value = job
      if (!['pending', 'running'].includes(job.status)) {
        stopPolling()
        loadJobs()
        if (job.status === 'success') ElMessage.success(`任务 #${id} 完成`)
      }
    } catch (err) {
      stopPolling()
    }
  }, 2000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function loadJobs() {
  listLoading.value = true
  try {
    const data = await roiApi.jobs({ limit: 50 })
    jobs.value = data.items || []
  } finally {
    listLoading.value = false
  }
}

async function openJob(id) {
  detailLoading.value = true
  try {
    const job = await roiApi.job(id)
    currentJob.value = job
    selectedIndex.value = 0
    scrollToDetail()
    if (['pending', 'running'].includes(job.status)) startPolling(id)
    else stopPolling()
  } finally {
    detailLoading.value = false
  }
}

function closeDetail() {
  stopPolling()
  currentJob.value = null
}

async function removeJob(row) {
  try {
    await ElMessageBox.confirm(`确定删除任务 #${row.id}（${row.name}）？输出文件也会一并删除。`, '删除确认', {
      type: 'warning'
    })
  } catch (err) {
    return
  }
  await roiApi.remove(row.id)
  ElMessage.success('已删除')
  if (currentJob.value?.id === row.id) currentJob.value = null
  loadJobs()
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
  serverPath.value = browseData.path
  browserVisible.value = false
}

async function registerDataset() {
  if (!registerForm.name.trim()) {
    ElMessage.warning('请填写数据集名称')
    return
  }
  registering.value = true
  try {
    await datasetApi.create({
      name: registerForm.name.trim(),
      path: currentJob.value.output_dir,
      image_extension: registerForm.image_extension || '.png',
      description: registerForm.description
    })
    ElMessage.success('数据集登记成功')
    registerDialog.value = false
    registerForm.name = ''
    registerForm.description = ''
  } finally {
    registering.value = false
  }
}

async function loadSuggestions() {
  try {
    const data = await datasetApi.suggestions()
    suggestions.value = data.items || []
  } catch (err) {
    suggestions.value = []
  }
}

watch(browserVisible, (value) => {
  if (value) browseTo(browseData.path || '')
})

onMounted(() => {
  store.loadAll().catch(() => {})
  loadJobs()
  loadSuggestions()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.row-gap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.mr-12 {
  margin-right: 12px;
}

.switch-label {
  font-size: 14px;
  color: #606266;
}

.folder-picker {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.stat-row {
  display: flex;
  gap: 40px;
  flex-wrap: wrap;
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

.browser-section-title {
  font-size: 12px;
  color: #909399;
  margin: 12px 0 6px;
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

.browser-item.is-file {
  cursor: default;
  color: #909399;
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
