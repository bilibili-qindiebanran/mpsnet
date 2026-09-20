import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    component: () => import('@/layouts/AppLayout.vue'),
    children: [
      {
        path: '',
        name: 'dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { title: '总览', icon: 'Odometer' }
      },
      {
        path: 'roi',
        name: 'roi',
        component: () => import('@/views/RoiExtraction.vue'),
        meta: { title: 'ROI 提取', icon: 'Crop' }
      },
      {
        path: 'datasets',
        name: 'datasets',
        component: () => import('@/views/Datasets.vue'),
        meta: { title: '数据集', icon: 'Files' }
      },
      {
        path: 'training',
        name: 'training',
        component: () => import('@/views/Training.vue'),
        meta: { title: '模型训练', icon: 'Cpu' }
      },
      {
        path: 'training/:id',
        name: 'training-detail',
        component: () => import('@/views/TrainingJobDetail.vue'),
        meta: { title: '训练详情', parent: '模型训练', parentName: 'training', hidden: true }
      },
      {
        path: 'recognition',
        name: 'recognition',
        component: () => import('@/views/Recognition.vue'),
        meta: { title: '识别验证', icon: 'Aim' }
      },
      {
        path: 'settings',
        name: 'settings',
        component: () => import('@/views/Settings.vue'),
        meta: { title: '系统设置', icon: 'Setting' }
      }
    ]
  },
  { path: '/:pathMatch(.*)*', redirect: '/' }
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 })
})

router.afterEach((to) => {
  const title = to.meta?.title
  document.title = title ? `${title} · MPSNet 掌静脉识别平台` : 'MPSNet 掌静脉识别平台'
})

export default router
