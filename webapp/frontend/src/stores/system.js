import { defineStore } from 'pinia'
import { systemApi, trainApi, roiApi } from '@/api'

export const useSystemStore = defineStore('system', {
  state: () => ({
    info: null,
    stats: null,
    roiStatus: { ready: false, message: '' },
    models: [],
    optionSpec: [],
    defaultParams: {},
    presetsExample: {},
    imageExtensions: ['.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff'],
    loading: false,
    loaded: false,
    building: false
  }),

  getters: {
    optionGroups(state) {
      const groups = []
      state.optionSpec.forEach((item) => {
        const name = item.group || '其他'
        let target = groups.find((group) => group.name === name)
        if (!target) {
          target = { name, items: [] }
          groups.push(target)
        }
        target.items.push(item)
      })
      return groups
    },
    palmlibReady(state) {
      return Boolean(state.roiStatus?.ready)
    }
  },

  actions: {
    async loadAll(force = false) {
      if (this.loaded && !force) return
      this.loading = true
      try {
        const [info, stats, roiStatus, options] = await Promise.all([
          systemApi.info(),
          systemApi.stats(),
          roiApi.status(),
          trainApi.options()
        ])
        this.info = info
        this.stats = stats
        this.roiStatus = roiStatus
        this.models = options.models || []
        this.optionSpec = options.option_spec || []
        this.defaultParams = options.default_params || {}
        this.presetsExample = options.presets_example || {}
        this.imageExtensions = info.image_extensions || this.imageExtensions
        this.loaded = true
      } finally {
        this.loading = false
      }
    },

    async loadStats() {
      this.stats = await systemApi.stats()
      return this.stats
    },

    async loadRoiStatus() {
      this.roiStatus = await roiApi.status()
      return this.roiStatus
    },

    async buildPalmlib() {
      this.building = true
      try {
        const result = await roiApi.build()
        await this.loadRoiStatus()
        return result
      } finally {
        this.building = false
      }
    }
  }
})
