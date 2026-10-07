<template>
  <div class="kuaishou-image-publish-panel">
    <div v-if="accountId && hasAccountOverride(accountId)" style="margin-bottom: 12px;">
      <el-button size="small" @click="resetOverride">恢复为渠道默认</el-button>
    </div>

    <div class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">标题</div>
      <el-input v-model="form.title" placeholder="请输入标题..." maxlength="100" show-word-limit :disabled="disabled" />
    </div>

    <div class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">描述</div>
      <el-input v-model="form.description" type="textarea" :rows="5" placeholder="请输入描述..." maxlength="2000" show-word-limit :disabled="disabled" />
    </div>

    <div class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">标签</div>
      <div class="setting-hint">输入标签内容，按回车确认（最多 4 个）</div>
      <el-input v-model="tagInput" placeholder="输入标签内容，按回车添加" @keyup.enter="addTag" clearable :disabled="disabled" />
      <div v-if="form.tags && form.tags.length > 0" class="tags-list">
        <el-tag v-for="(tag, index) in form.tags" :key="index" closable @close="removeTag(index)" size="small" :disable-transitions="false">#{{ tag }}</el-tag>
      </div>
    </div>

    <div class="setting-card">
      <div class="setting-label">作者声明</div>
      <el-select v-model="form.aiContent" placeholder="请选择作者声明" clearable style="width: 100%" :disabled="disabled">
        <el-option v-for="opt in declarationOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
      </el-select>
    </div>

    <div class="setting-card">
      <div class="setting-label">定时发布</div>
      <el-date-picker
        v-model="form.scheduleTime"
        type="datetime"
        placeholder="选择日期时间"
        format="YYYY-MM-DD HH:mm:ss"
        value-format="YYYY-MM-DD HH:mm:ss"
        style="width: 100%"
        :disabled="disabled"
      />
    </div>

    <div class="setting-card">
      <div class="setting-label">选择音乐</div>
      <div class="setting-hint">请在快手真实投稿页面选择音乐。</div>
      <div v-if="form.selectedMusicId">
        已保存：{{ form.musicTitle || form.selectedMusicId }}
        <el-button text size="small" :disabled="disabled" @click="clearMusic">清除已保存音乐</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { PLATFORMS } from '@/config/platforms'
import { useChannelForm } from '@/composables/useChannelForm'
import { useAutoExtractHashtags } from '@/utils/hashtag'

const props = defineProps({
  accountId: { type: [Number, Object], default: null },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['config-changed'])

const KS_DEFAULTS = { ...PLATFORMS.KUAISHOU.defaultSettings, tags: [] }

const declarationOptions = computed(() => {
  const field = PLATFORMS.KUAISHOU.settingsFields.find(f => f.key === 'aiContent')
  return field?.options || []
})

function clearMusic() {
  form.selectedMusicId = ''
  form.selectedMusicData = null
  form.musicTitle = ''
}

const { form, hasAccountOverride, resetOverride, publicApi } = useChannelForm(
  KS_DEFAULTS,
  { props, emit },
  {
    validateFn: (accountId, merged) => {
      const errors = []
      if (!merged.title || !merged.title.trim()) errors.push('标题不能为空')
      if (!merged.aiContent) errors.push('请选择自主声明')
      const tc = merged.tags?.length || 0
      if (tc > KS_MAX_TAGS) errors.push(`标签最多 ${KS_MAX_TAGS} 个,当前 ${tc} 个`)
      return { valid: errors.length === 0, errors }
    },
  },
)

const tagInput = ref('')

// 快手标签上限(快手平台最多添加 4 个标签)
const KS_MAX_TAGS = 4

function addTag() {
  const tag = tagInput.value.trim()
  if (!tag) return
  if (!form.tags) form.tags = []
  if (form.tags.includes(tag)) { ElMessage.warning('标签已存在'); return }
  if (form.tags.length >= KS_MAX_TAGS) {
    ElMessage.warning(`标签最多 ${KS_MAX_TAGS} 个`)
    return
  }
  form.tags.push(tag)
  tagInput.value = ''
}

function removeTag(index) { form.tags.splice(index, 1) }

// 自动提取描述中的 #xxx 到标签数组(快手最多 4 个)
useAutoExtractHashtags({
  form,
  descKey: 'description',
  tagKey: 'tags',
  maxTags: KS_MAX_TAGS,
})

defineExpose(publicApi)
</script>

<style scoped>
.kuaishou-image-publish-panel {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 12px;
}

.setting-card {
  border: 1px solid rgba($warning-color, 0.15);
  background: rgba($warning-color, 0.04);
  border-radius: 8px;
  padding: 16px;
}

.setting-label {
  font-size: 13px;
  font-weight: 600;
  color: #f59e0b;
  margin-bottom: 8px;
}

.setting-hint {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 8px;
  line-height: 1.5;
}
</style>
