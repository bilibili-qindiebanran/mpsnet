<template>
  <div class="page" v-loading="loading">
    <div class="page-head">
      <div>
        <h2 class="page-title">总览</h2>
        <p class="page-desc">MPSNet 掌静脉识别平台 · ROI 提取 / 数据集 / 训练 / 识别的全流程状态</p>
      </div>
      <el-button :loading="loading" @click="load">
        <el-icon><Refresh /></el-icon>
        <span style="margin-left: 4px">刷新</span>
      </el-button>
    </div>

    <!-- palmlib 提示条 -->
    <el-alert
      v-if="roiStatus && !roiStatus.ready"
      class="mb-16"
      type="warning"
      show-icon
      :closable="false"
      title="ROI 提取模块（palmlib）尚未编译"
    >
      <template #default>
        <div class="alert-row">
          <span>{{ roiStatus.message }}</span>
          <el-button
            type="primary"
            size="small"
            :loading="store.building"
            @click="buildModule"
          >
            编译模块
          </el-button>
        </div>
      </template>
    </el-alert>
    <el-alert
      v-else-if="roiStatus"
      class="mb-16"
      type="success"
      show-icon
      :closable="false"
      :title="roiStatus.message || 'ROI 提取模块已就绪'"
    />

    <!-- 统计卡片 -->
    <div class="card-grid grid-4">
      <StatCard
        label="数据集"
        :value="stats.datasets ?? 0"
        :hint="`${stats.dataset_images ?? 0} 张样本`"
        icon="Files"
        color="#409eff"
        clickable
        @click="$router.push('/datasets')"
      />
      <StatCard
        label="ROI 提取任务"
        :value="stats.roi_jobs ?? 0"
        :hint="`已生成 ${stats.roi_images ?? 0} 张 ROI`"
        icon="Crop"
        color="#67c23a"
        clickable
        @click="$router.push('/roi')"
      />
      <StatCard
        label="训练任务"
        :value="stats.train_jobs ?? 0"
        :hint="`运行中 ${stats.running_jobs ?? 0} 个`"
        icon="Cpu"
        color="#e6a23c"
        clickable
        @click="$router.push('/training')"
      />
      <StatCard
        label="识别库 / 识别次数"
        :value="`${stats.galleries ?? 0} / ${stats.recognitions ?? 0}`"
        hint="识别库数 / 累计识别"
        icon="Aim"
        color="#909399"
        clickable
        @click="$router.push('/recognition')"
      />
    </div>

    <div class="card-grid grid-3 mt-16">
      <el-card shadow="never">
        <h3 class="section-title"><el-icon><TrendCharts /></el-icon> 最优 EER</h3>
        <div class="big-metric">
          {{ stats.best_eer === null || stats.best_eer === undefined ? '-' : formatMetricPercent(stats.best_eer) }}
        </div>
        <div class="text-secondary" style="font-size: 12px">所有训练任务中的最小等错误率</div>
      </el-card>

      <el-card shadow="never">
        <h3 class="section-title"><el-icon><PieChart /></el-icon> 训练状态分布</h3>
        <div v-if="statusEntries.length" class="status-list">
          <div v-for="entry in statusEntries" :key="entry.status" class="status-row">
            <JobStatusTag :status="entry.status" />
            <span class="status-count">{{ entry.count }}</span>
          </div>
        </div>
        <el-empty v-else description="暂无训练任务" :image-size="60" />
      </el-card>

      <el-card shadow="never">
        <h3 class="section-title"><el-icon><Promotion /></el-icon> 快捷入口</h3>
        <div class="quick-actions">
          <el-button type="primary" plain @click="$router.push('/roi')">
            <el-icon><Crop /></el-icon><span style="margin-left: 4px">去提 ROI</span>
          </el-button>
          <el-button type="primary" plain @click="$router.push('/training')">
            <el-icon><Cpu /></el-icon><span style="margin-left: 4px">去训练</span>
          </el-button>
          <el-button type="primary" plain @click="$router.push('/recognition')">
            <el-icon><Aim /></el-icon><span style="margin-left: 4px">去识别</span>
          </el-button>
        </div>
        <div class="text-secondary mt-12" style="font-size: 12px">
          推荐流程：ROI 提取 → 登记数据集 → 训练 MPSNet → 构建识别库
        </div>
      </el-card>
    </div>

    <el-card class="mt-16" shadow="never">
      <template #header>
        <div class="card-header-row">
          <span class="section-title" style="margin: 0"><el-icon><List /></el-icon> 最近训练任务</span>
          <el-button text type="primary" @click="$router.push('/training')">查看全部</el-button>
        </div>
      </template>

      <el-table :data="recentJobs" @row-click="(row) => $router.push(`/training/${row.id}`)">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="任务名" min-width="200" show-overflow-tooltip />
        <el-table-column prop="model_name" label="模型" width="130" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }"><JobStatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="Best EER" width="110">
          <template #default="{ row }">{{ formatMetricPercent(row.best_eer) }}</template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <template #empty>
          <el-empty description="还没有训练任务，先去「模型训练」创建一个吧" :image-size="80" />
        </template>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import { useSystemStore } from '@/stores/system'
import { trainApi, formatMetricPercent, formatTime } from '@/api'
import StatCard from '@/components/StatCard.vue'
import JobStatusTag from '@/components/JobStatusTag.vue'

const store = useSystemStore()
const { roiStatus } = storeToRefs(store)

const loading = ref(false)
const stats = reactive({})
const recentJobs = ref([])
let timer = null

const statusEntries = computed(() => {
  const map = stats.train_status || {}
  return Object.entries(map).map(([status, count]) => ({ status, count }))
})

async function load() {
  loading.value = true
  try {
    const [statsData, jobsData] = await Promise.all([store.loadStats(), trainApi.jobs({ limit: 5 })])
    Object.assign(stats, statsData)
    recentJobs.value = jobsData.items || []
    await store.loadRoiStatus()
  } finally {
    loading.value = false
  }
}

async function buildModule() {
  try {
    const result = await store.buildPalmlib()
    ElMessage.success(result.message || '编译成功')
  } catch (err) {
    /* 错误已由拦截器提示 */
  }
}

onMounted(() => {
  load()
  timer = setInterval(() => {
    if (stats.running_jobs > 0) load()
  }, 5000)
})

onUnmounted(() => {
  clearInterval(timer)
})
</script>

<style scoped>
.alert-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.big-metric {
  font-size: 30px;
  font-weight: 600;
  color: #409eff;
  line-height: 1.3;
}

.status-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.status-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.status-count {
  font-size: 16px;
  font-weight: 600;
}

.quick-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
