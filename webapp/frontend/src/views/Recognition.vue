<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">识别验证</h2>
        <p class="page-desc">基于训练产物的掌脉识别库构建与 1:N 识别 / 1:1 验证</p>
      </div>
      <el-button :loading="galleriesLoading" @click="loadGalleries">
        <el-icon><Refresh /></el-icon>
        <span style="margin-left: 4px">刷新</span>
      </el-button>
    </div>

    <el-tabs v-model="activeTab">
      <!-- ------------------------------------------------ 识别库管理 -->
      <el-tab-pane label="识别库" name="galleries">
        <el-card shadow="never" class="mb-16">
          <template #header>
            <div class="card-header-row">
              <span class="section-title" style="margin: 0">
                <el-icon><Collection /></el-icon> 识别库列表
              </span>
              <el-button type="primary" size="small" @click="openCreateDialog">
                <el-icon><Plus /></el-icon>
                <span style="margin-left: 4px">新建识别库</span>
              </el-button>
            </div>
          </template>

          <el-table :data="galleries" v-loading="galleriesLoading">
            <el-table-column prop="id" label="ID" width="60" />
            <el-table-column prop="name" label="名称" min-width="170" show-overflow-tooltip />
            <el-table-column prop="model_name" label="模型" width="120" />
            <el-table-column prop="dataset_name" label="数据集" width="140" show-overflow-tooltip>
              <template #default="{ row }">{{ row.dataset_name || '-' }}</template>
            </el-table-column>
            <el-table-column prop="n_classes" label="类别" width="80" />
            <el-table-column prop="n_samples" label="样本" width="80" />
            <el-table-column prop="embedding_dim" label="特征维度" width="100" />
            <el-table-column label="阈值" width="100">
              <template #default="{ row }">{{ formatDecimal(row.threshold, 4) }}</template>
            </el-table-column>
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <JobStatusTag :status="row.status" />
                <div v-if="buildingId === row.id && buildProgress" class="text-secondary" style="font-size: 11px">
                  {{ buildProgress }}
                </div>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="190" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="useGallery(row)">选用</el-button>
                <el-button
                  v-if="['pending', 'failed'].includes(row.status)"
                  link
                  type="warning"
                  @click="buildGallery(row)"
                >
                  构建
                </el-button>
                <el-button link type="danger" @click="removeGallery(row)">删除</el-button>
              </template>
            </el-table-column>
            <template #empty>
              <el-empty description="还没有识别库，先用训练成功的任务构建一个" :image-size="80" />
            </template>
          </el-table>
        </el-card>
      </el-tab-pane>

      <!-- ------------------------------------------------ 1:N 识别 -->
      <el-tab-pane label="1:N 识别" name="identify">
        <el-card shadow="never" class="mb-16">
          <el-form :inline="true">
            <el-form-item label="识别库">
              <el-select
                v-model="galleryId"
                placeholder="选择识别库"
                style="width: 320px"
                @change="onGalleryChange"
              >
                <el-option
                  v-for="item in readyGalleries"
                  :key="item.id"
                  :label="`#${item.id} ${item.name}（${item.n_classes} 类 / 阈值 ${formatDecimal(item.threshold, 4)}）`"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="Top-K">
              <el-input-number v-model="topk" :min="1" :max="20" />
            </el-form-item>
            <el-form-item label="ROI 边长">
              <el-input-number v-model="roiSize" :min="32" :max="512" :step="16" />
            </el-form-item>
          </el-form>

          <el-upload
            drag
            :auto-upload="false"
            :show-file-list="false"
            accept="image/*"
            :disabled="!galleryId"
            :on-change="onIdentifyFile"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">拖拽手掌照片到此处，或<em>点击选择</em>（也可直接 Ctrl/⌘+V 粘贴）</div>
            <template #tip>
              <div class="el-upload__tip">
                {{ galleryId ? '将自动提取 ROI 并检索最相似身份' : '请先选择识别库' }}
              </div>
            </template>
          </el-upload>

          <div class="action-row mt-12">
            <el-button
              type="primary"
              :loading="identifying"
              :disabled="!galleryId || !identifyFile"
              @click="runIdentify"
            >
              <el-icon><Search /></el-icon>
              <span style="margin-left: 4px">开始识别</span>
            </el-button>
            <el-button :disabled="!identifyPreview" @click="clearIdentify">清空</el-button>
          </div>
        </el-card>

        <el-card v-if="identifyResult" shadow="never">
          <template #header>
            <span class="section-title" style="margin: 0">
              <el-icon><Aim /></el-icon> 识别结果
            </span>
          </template>

          <el-result
            :icon="identifyResult.matched ? 'success' : 'warning'"
            :title="identifyResult.matched ? `判定身份：${identifyResult.predicted_label}` : '未匹配到可信身份'"
            :sub-title="`距离 ${formatDecimal(identifyResult.distance, 4)} · 阈值 ${formatDecimal(
              identifyResult.threshold,
              4
            )} · 耗时 ${identifyResult.elapsed_ms} ms`"
          />

          <div class="identify-body">
            <div class="image-compare-wrap">
              <ImageCompare
                :columns="2"
                :items="[
                  { key: 'probe', label: '上传原图', path: identifyResult.probe_path },
                  { key: 'roi', label: '提取 ROI', path: identifyResult.roi_path }
                ]"
              />
              <el-alert
                v-if="!identifyResult.roi_extracted"
                class="mt-12"
                type="warning"
                show-icon
                :closable="false"
                title="ROI 提取失败，已回退为整图缩放"
              />
            </div>

            <div class="candidates-wrap">
              <h4 class="section-title">Top-K 候选</h4>
              <el-table :data="identifyResult.candidates || []" size="small">
                <el-table-column type="index" label="#" width="50" />
                <el-table-column prop="label" label="身份" width="110" />
                <el-table-column label="距离" width="90">
                  <template #default="{ row }">{{ formatDecimal(row.distance, 4) }}</template>
                </el-table-column>
                <el-table-column label="相似度">
                  <template #default="{ row }">
                    <el-progress
                      :percentage="Math.max(0, Math.min(100, Number((row.similarity || 0) * 100)))"
                      :stroke-width="12"
                      :format="() => `${((row.similarity || 0) * 100).toFixed(2)}%`"
                    />
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </div>
        </el-card>
      </el-tab-pane>

      <!-- ------------------------------------------------ 1:1 验证 -->
      <el-tab-pane label="1:1 验证" name="verify">
        <el-card shadow="never" class="mb-16">
          <el-form :inline="true">
            <el-form-item label="识别库">
              <el-select v-model="galleryId" placeholder="选择识别库" style="width: 320px" @change="onGalleryChange">
                <el-option
                  v-for="item in readyGalleries"
                  :key="item.id"
                  :label="`#${item.id} ${item.name}`"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="待验证身份">
              <el-select
                v-model="claim"
                placeholder="选择 Palm_ID"
                style="width: 180px"
                filterable
                allow-create
                :loading="identitiesLoading"
              >
                <el-option v-for="item in identities" :key="item.label" :label="item.label" :value="item.label" />
              </el-select>
            </el-form-item>
            <el-form-item label="阈值">
              <el-input-number
                v-model="verifyThreshold"
                :min="0"
                :max="2"
                :step="0.01"
                :precision="4"
                placeholder="默认用 EER 阈值"
              />
            </el-form-item>
            <el-form-item label="ROI 边长">
              <el-input-number v-model="roiSize" :min="32" :max="512" :step="16" />
            </el-form-item>
          </el-form>

          <el-upload
            drag
            :auto-upload="false"
            :show-file-list="false"
            accept="image/*"
            :disabled="!galleryId || !claim"
            :on-change="onVerifyFile"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">拖拽待验证照片到此处，或<em>点击选择</em></div>
            <template #tip>
              <div class="el-upload__tip">
                {{ galleryId ? (claim ? '将与该身份的全部样本比对' : '请先选择待验证身份') : '请先选择识别库' }}
              </div>
            </template>
          </el-upload>

          <div class="action-row mt-12">
            <el-button
              type="primary"
              :loading="verifying"
              :disabled="!galleryId || !claim || !verifyFile"
              @click="runVerify"
            >
              <el-icon><Select /></el-icon>
              <span style="margin-left: 4px">开始验证</span>
            </el-button>
            <el-button :disabled="!verifyPreview" @click="clearVerify">清空</el-button>
          </div>
        </el-card>

        <el-card v-if="verifyResult" shadow="never">
          <template #header>
            <span class="section-title" style="margin: 0">
              <el-icon><CircleCheck /></el-icon> 验证结果
            </span>
          </template>

          <el-result
            :icon="verifyResult.matched ? 'success' : 'error'"
            :title="verifyResult.matched ? `通过：属于 ${verifyResult.claim}` : `不通过：不属于 ${verifyResult.claim}`"
            :sub-title="`距离 ${formatDecimal(verifyResult.distance, 4)} · 阈值 ${formatDecimal(
              verifyResult.threshold,
              4
            )} · 库内样本 ${verifyResult.n_gallery_samples} 个 · 耗时 ${verifyResult.elapsed_ms} ms`"
          />

          <ImageCompare
            :columns="2"
            :items="[
              { key: 'probe', label: '上传原图', path: verifyResult.probe_path },
              { key: 'roi', label: '提取 ROI', path: verifyResult.roi_path }
            ]"
          />
        </el-card>
      </el-tab-pane>

      <!-- ------------------------------------------------ 识别记录 -->
      <el-tab-pane label="识别记录" name="logs">
        <el-card shadow="never">
          <template #header>
            <div class="card-header-row">
              <span class="section-title" style="margin: 0">
                <el-icon><Clock /></el-icon> 识别记录
              </span>
              <div class="row-gap">
                <el-select
                  v-model="logGalleryId"
                  placeholder="全部识别库"
                  clearable
                  size="small"
                  style="width: 220px"
                  @change="loadLogs"
                >
                  <el-option v-for="item in galleries" :key="item.id" :label="item.name" :value="item.id" />
                </el-select>
                <el-button size="small" :loading="logsLoading" @click="loadLogs">刷新</el-button>
              </div>
            </div>
          </template>

          <el-table :data="logs" v-loading="logsLoading" size="small">
            <el-table-column label="时间" width="170">
              <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="模式" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="row.mode === 'identify' ? 'primary' : 'success'" effect="plain">
                  {{ row.mode === 'identify' ? '1:N 识别' : '1:1 验证' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="predicted_label" label="预测身份" width="130" />
            <el-table-column label="距离" width="100">
              <template #default="{ row }">{{ formatDecimal(row.distance, 4) }}</template>
            </el-table-column>
            <el-table-column label="阈值" width="100">
              <template #default="{ row }">{{ formatDecimal(row.threshold, 4) }}</template>
            </el-table-column>
            <el-table-column label="结果" width="90">
              <template #default="{ row }">
                <el-tag v-if="row.matched === null" size="small" type="info" effect="plain">未知</el-tag>
                <el-tag v-else size="small" :type="row.matched ? 'success' : 'danger'" effect="light">
                  {{ row.matched ? '匹配' : '不匹配' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="耗时" width="90">
              <template #default="{ row }">{{ row.elapsed_ms }} ms</template>
            </el-table-column>
            <el-table-column label="图片" min-width="140">
              <template #default="{ row }">
                <el-image
                  v-if="row.probe_path"
                  class="log-thumb"
                  :src="fileUrl(row.probe_path)"
                  :preview-src-list="[fileUrl(row.roi_path || row.probe_path), fileUrl(row.probe_path)]"
                  fit="cover"
                  preview-teleported
                />
                <span v-else class="text-secondary">-</span>
              </template>
            </el-table-column>
            <template #empty>
              <el-empty description="还没有识别记录" :image-size="70" />
            </template>
          </el-table>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- 新建识别库 -->
    <el-dialog v-model="createDialog" title="新建识别库" width="560px">
      <el-form :model="createForm" label-width="100px">
        <el-form-item label="名称">
          <el-input v-model="createForm.name" placeholder="留空自动命名" />
        </el-form-item>
        <el-form-item label="训练任务" required>
          <el-select v-model="createForm.job_id" placeholder="仅展示训练成功的任务" style="width: 100%">
            <el-option
              v-for="item in candidates"
              :key="item.job_id"
              :label="`#${item.job_id} ${item.job_name}（${item.model_name} / Best EER ${formatMetricPercent(item.best_eer)}）`"
              :value="item.job_id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="数据集" required>
          <el-select v-model="createForm.dataset_id" placeholder="注册样本来源" style="width: 100%">
            <el-option
              v-for="item in candidateDatasets"
              :key="item.id"
              :label="`${item.name}（${item.n_classes} 类 / ${item.n_images} 张）`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="createGallery">创建并构建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  recognitionApi,
  fileUrl,
  formatDecimal,
  formatMetricPercent,
  formatTime,
  openEventStream
} from '@/api'
import JobStatusTag from '@/components/JobStatusTag.vue'
import ImageCompare from '@/components/ImageCompare.vue'

const activeTab = ref('galleries')

const galleries = ref([])
const galleriesLoading = ref(false)
const candidates = ref([])
const candidateDatasets = ref([])
const buildingId = ref(null)
const buildProgress = ref('')
let stream = null

const createDialog = ref(false)
const creating = ref(false)
const createForm = reactive({ name: '', job_id: null, dataset_id: null })

const galleryId = ref(null)
const topk = ref(5)
const roiSize = ref(128)

const identifyFile = ref(null)
const identifyPreview = ref('')
const identifying = ref(false)
const identifyResult = ref(null)

const verifyFile = ref(null)
const verifyPreview = ref('')
const verifying = ref(false)
const verifyResult = ref(null)
const claim = ref('')
const verifyThreshold = ref(null)
const identities = ref([])
const identitiesLoading = ref(false)

const logs = ref([])
const logsLoading = ref(false)
const logGalleryId = ref(null)

const readyGalleries = computed(() =>
  galleries.value.filter((item) => item.status === 'success')
)

function onGalleryChange(id) {
  identifyResult.value = null
  verifyResult.value = null
  claim.value = ''
  identities.value = []
  if (id) loadIdentities(id)
}

async function loadGalleries() {
  galleriesLoading.value = true
  try {
    const data = await recognitionApi.galleries()
    galleries.value = data.items || []
  } finally {
    galleriesLoading.value = false
  }
}

async function loadCandidates() {
  const data = await recognitionApi.candidates()
  candidates.value = data.jobs || []
  candidateDatasets.value = data.datasets || []
}

async function loadLogs() {
  logsLoading.value = true
  try {
    const params = { limit: 100 }
    if (logGalleryId.value) params.gallery_id = logGalleryId.value
    const data = await recognitionApi.logs(params)
    logs.value = data.items || []
  } finally {
    logsLoading.value = false
  }
}

async function loadIdentities(id) {
  identitiesLoading.value = true
  try {
    const data = await recognitionApi.identities(id, 200)
    identities.value = data.items || []
  } catch (err) {
    identities.value = []
  } finally {
    identitiesLoading.value = false
  }
}

function openCreateDialog() {
  createDialog.value = true
  loadCandidates()
}

async function createGallery() {
  if (!createForm.job_id || !createForm.dataset_id) {
    ElMessage.warning('请选择训练任务与数据集')
    return
  }
  creating.value = true
  try {
    const gallery = await recognitionApi.runGallery({
      name: createForm.name.trim(),
      job_id: createForm.job_id,
      dataset_id: createForm.dataset_id
    })
    createDialog.value = false
    createForm.name = ''
    createForm.job_id = null
    createForm.dataset_id = null
    ElMessage.success(`识别库 #${gallery.id} 开始构建`)
    buildingId.value = gallery.id
    buildProgress.value = ''
    watchBuild(gallery.id)
    await loadGalleries()
  } finally {
    creating.value = false
  }
}

function watchBuild(id) {
  closeStream()
  stream = openEventStream(recognitionApi.eventsUrl(id), {
    onMessage: (snapshot) => {
      buildProgress.value = snapshot.progress || ''
      if (snapshot.n_samples) {
        buildProgress.value = `${snapshot.progress || ''} · ${snapshot.n_samples} 样本 / ${snapshot.n_classes || 0} 类`
      }
      const target = galleries.value.find((item) => item.id === id)
      if (target) {
        target.status = snapshot.status
        target.n_samples = snapshot.n_samples
        target.n_classes = snapshot.n_classes
        target.embedding_dim = snapshot.embedding_dim
      }
    },
    onEnd: async () => {
      closeStream()
      buildingId.value = null
      buildProgress.value = ''
      await loadGalleries()
      ElMessage.success('识别库构建流程结束')
    },
    onError: () => {
      buildProgress.value = ''
    }
  })
}

async function buildGallery(row) {
  try {
    await recognitionApi.startGallery(row.id)
  } catch (err) {
    return
  }
  ElMessage.success(`识别库 #${row.id} 开始构建`)
  buildingId.value = row.id
  buildProgress.value = ''
  watchBuild(row.id)
  loadGalleries()
}

async function removeGallery(row) {
  try {
    await ElMessageBox.confirm(`确定删除识别库「${row.name}」？`, '删除确认', { type: 'warning' })
  } catch (err) {
    return
  }
  await recognitionApi.removeGallery(row.id)
  ElMessage.success('已删除')
  if (galleryId.value === row.id) galleryId.value = null
  loadGalleries()
  loadLogs()
}

function useGallery(row) {
  if (row.status !== 'success') {
    ElMessage.warning('该识别库尚未构建完成')
    return
  }
  galleryId.value = row.id
  activeTab.value = 'identify'
  onGalleryChange(row.id)
}

function readPreview(file, target, preview) {
  target.value = file
  if (preview.value) URL.revokeObjectURL(preview.value)
  preview.value = URL.createObjectURL(file)
}

function onIdentifyFile(uploadFile) {
  if (!uploadFile?.raw) return
  readPreview(uploadFile.raw, identifyFile, identifyPreview)
  identifyResult.value = null
}

function onVerifyFile(uploadFile) {
  if (!uploadFile?.raw) return
  readPreview(uploadFile.raw, verifyFile, verifyPreview)
  verifyResult.value = null
}

function clearIdentify() {
  identifyFile.value = null
  if (identifyPreview.value) URL.revokeObjectURL(identifyPreview.value)
  identifyPreview.value = ''
  identifyResult.value = null
}

function clearVerify() {
  verifyFile.value = null
  if (verifyPreview.value) URL.revokeObjectURL(verifyPreview.value)
  verifyPreview.value = ''
  verifyResult.value = null
}

async function runIdentify() {
  identifying.value = true
  try {
    identifyResult.value = await recognitionApi.identify(
      galleryId.value,
      identifyFile.value,
      topk.value,
      roiSize.value
    )
    ElMessage.success('识别完成')
    loadLogs()
  } finally {
    identifying.value = false
  }
}

async function runVerify() {
  verifying.value = true
  try {
    verifyResult.value = await recognitionApi.verify(
      galleryId.value,
      verifyFile.value,
      claim.value,
      verifyThreshold.value,
      roiSize.value
    )
    ElMessage.success('验证完成')
    loadLogs()
  } finally {
    verifying.value = false
  }
}

function handlePaste(event) {
  const items = Array.from(event.clipboardData?.items || [])
  const imageItem = items.find((item) => item.type.startsWith('image/'))
  if (!imageItem) return
  const file = imageItem.getAsFile()
  if (!file) return
  if (activeTab.value === 'identify') {
    readPreview(file, identifyFile, identifyPreview)
    identifyResult.value = null
    ElMessage.success('已粘贴剪贴板图片')
  } else if (activeTab.value === 'verify') {
    readPreview(file, verifyFile, verifyPreview)
    verifyResult.value = null
    ElMessage.success('已粘贴剪贴板图片')
  }
}

function closeStream() {
  stream?.close()
  stream = null
}

onMounted(() => {
  loadGalleries()
  loadCandidates()
  loadLogs()
  document.addEventListener('paste', handlePaste)
})

onUnmounted(() => {
  closeStream()
  document.removeEventListener('paste', handlePaste)
  if (identifyPreview.value) URL.revokeObjectURL(identifyPreview.value)
  if (verifyPreview.value) URL.revokeObjectURL(verifyPreview.value)
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
  gap: 10px;
}

.action-row {
  display: flex;
  gap: 10px;
}

.identify-body {
  display: grid;
  grid-template-columns: 360px minmax(0, 1fr);
  gap: 20px;
}

@media (max-width: 900px) {
  .identify-body {
    grid-template-columns: minmax(0, 1fr);
  }
}

.log-thumb {
  width: 48px;
  height: 48px;
  border-radius: 6px;
  border: 1px solid #e4e7ed;
}
</style>
