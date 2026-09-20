<template>
  <div class="app-shell">
    <!-- 桌面侧边栏 -->
    <aside v-if="!isMobile" class="app-sidebar" :class="{ 'is-collapsed': collapsed }">
      <div class="app-logo">
        <div class="app-logo-mark">MP</div>
        <div v-show="!collapsed">
          <div class="app-logo-text">MPSNet 平台</div>
          <div class="app-logo-sub">掌静脉识别</div>
        </div>
      </div>
      <div class="app-sidebar-scroll">
        <el-menu :default-active="activeMenu" :collapse="collapsed" router :collapse-transition="false">
          <el-menu-item v-for="item in menus" :key="item.name" :index="item.path">
            <el-icon><component :is="item.icon" /></el-icon>
            <template #title>{{ item.title }}</template>
          </el-menu-item>
        </el-menu>
      </div>
    </aside>

    <!-- 移动端抽屉 -->
    <el-drawer v-else v-model="drawer" direction="ltr" size="220px" :with-header="false">
      <div class="app-logo" style="height: 56px">
        <div class="app-logo-mark">MP</div>
        <div>
          <div class="app-logo-text">MPSNet 平台</div>
          <div class="app-logo-sub">掌静脉识别</div>
        </div>
      </div>
      <el-menu :default-active="activeMenu" router @select="drawer = false">
        <el-menu-item v-for="item in menus" :key="item.name" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <template #title>{{ item.title }}</template>
        </el-menu-item>
      </el-menu>
    </el-drawer>

    <div class="app-main">
      <header class="app-header">
        <el-button text @click="toggleSidebar">
          <el-icon :size="18"><Expand v-if="collapsed || isMobile" /><Fold v-else /></el-icon>
        </el-button>

        <el-breadcrumb separator="/">
          <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
          <el-breadcrumb-item v-if="parentCrumb" :to="{ name: parentCrumb.name }">
            {{ parentCrumb.title }}
          </el-breadcrumb-item>
          <el-breadcrumb-item v-if="currentTitle && currentTitle !== '总览'">
            {{ currentTitle }}
          </el-breadcrumb-item>
        </el-breadcrumb>

        <div class="app-header-spacer" />

        <el-tooltip :content="palmlibReady ? 'ROI 模块已就绪' : 'ROI 模块未编译'" placement="bottom">
          <el-tag :type="palmlibReady ? 'success' : 'warning'" effect="light" round>
            <el-icon class="mr-4"><CircleCheck v-if="palmlibReady" /><Warning v-else /></el-icon>
            {{ palmlibReady ? 'palmlib 就绪' : 'palmlib 未就绪' }}
          </el-tag>
        </el-tooltip>

        <el-button text @click="reload">
          <el-icon><Refresh /></el-icon>
        </el-button>
      </header>

      <main class="app-content">
        <router-view v-if="alive" />
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import { useSystemStore } from '@/stores/system'

const route = useRoute()
const store = useSystemStore()
const { roiStatus } = storeToRefs(store)

const menus = [
  { name: 'dashboard', path: '/', title: '总览', icon: 'Odometer' },
  { name: 'roi', path: '/roi', title: 'ROI 提取', icon: 'Crop' },
  { name: 'datasets', path: '/datasets', title: '数据集', icon: 'Files' },
  { name: 'training', path: '/training', title: '模型训练', icon: 'Cpu' },
  { name: 'recognition', path: '/recognition', title: '识别验证', icon: 'Aim' },
  { name: 'settings', path: '/settings', title: '系统设置', icon: 'Setting' }
]

const collapsed = ref(false)
const drawer = ref(false)
const isMobile = ref(false)
const alive = ref(true)

const palmlibReady = computed(() => Boolean(roiStatus.value?.ready))
const activeMenu = computed(() => route.path)
const currentTitle = computed(() => route.meta?.title || '')
const parentCrumb = computed(() => {
  if (!route.meta?.parent || !route.meta?.parentName) return null
  return { title: route.meta.parent, name: route.meta.parentName }
})

function syncViewport() {
  isMobile.value = window.innerWidth < 768
  if (!isMobile.value) drawer.value = false
}

function toggleSidebar() {
  if (isMobile.value) {
    drawer.value = true
  } else {
    collapsed.value = !collapsed.value
  }
}

async function reload() {
  alive.value = false
  await store.loadAll(true)
  await new Promise((resolve) => setTimeout(resolve, 0))
  alive.value = true
  ElMessage.success('已刷新')
}

onMounted(() => {
  syncViewport()
  window.addEventListener('resize', syncViewport)
  store.loadAll().catch(() => {})
})

onUnmounted(() => {
  window.removeEventListener('resize', syncViewport)
})
</script>

<style scoped>
.mr-4 {
  margin-right: 4px;
  vertical-align: -1px;
}
</style>
