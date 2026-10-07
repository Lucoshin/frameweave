<template>
  <div class="xiaohongshu-image-publish-panel">
    <div class="xhs-warning">
      <el-icon><WarningFilled /></el-icon>
      <span>由于小红书反检测机制比较恶心，如果出现被警告的情况！请立即停止使用小红书渠道！</span>
    </div>

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
      <div class="setting-hint">输入标签内容，按回车确认</div>
      <el-input v-model="tagInput" placeholder="输入标签内容，按回车添加" @keyup.enter="addTag" clearable :disabled="disabled" />
      <div v-if="form.tags && form.tags.length > 0" class="tags-list">
        <el-tag v-for="(tag, index) in form.tags" :key="index" closable @close="removeTag(index)" size="small" :disable-transitions="false">#{{ tag }}</el-tag>
      </div>
    </div>

    <div class="settings-row">
      <div class="setting-card">
        <div class="setting-label">原创声明</div>
        <el-switch v-model="form.isOriginal" :disabled="disabled" />
      </div>

      <div class="setting-card">
        <div class="setting-label">内容类型声明</div>
        <el-select v-model="form.aiContent" placeholder="请选择" :disabled="disabled" style="width: 100%;">
          <el-option label="无" value="" />
          <el-option
            v-for="opt in aiContentOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </div>

      <div class="setting-card">
        <div class="setting-label">定时发布</div>
        <div class="setting-hint">不选时间表示立即发布，选择时间即定时发布</div>
        <el-date-picker
          v-model="form.scheduleTime"
          type="datetime"
          placeholder="选择发布时间（留空立即发布）"
          :disabled="disabled"
          style="width: 100%;"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { WarningFilled } from '@element-plus/icons-vue'
import { PLATFORMS } from '@/config/platforms'
import { useChannelForm } from '@/composables/useChannelForm'
import { useAutoExtractHashtags } from '@/utils/hashtag'

const props = defineProps({
  accountId: { type: [Number, Object], default: null },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['config-changed'])

const aiContentField = PLATFORMS.XIAOHONGSHU.settingsFields.find(f => f.key === 'aiContent')
const aiContentOptions = computed(() => aiContentField?.options || [])

const XHS_DEFAULTS = { ...PLATFORMS.XIAOHONGSHU.defaultSettings, tags: [], isOriginal: false }

const { form, hasAccountOverride, resetOverride, publicApi } = useChannelForm(
  XHS_DEFAULTS,
  { props, emit },
  {
    validateFn: (accountId, merged) => {
      const errors = []
      if (!merged.title || !merged.title.trim()) errors.push('标题不能为空')
      return { valid: errors.length === 0, errors }
    },
  },
)

const tagInput = ref('')

function addTag() {
  const tag = tagInput.value.trim()
  if (!tag) return
  if (!form.tags) form.tags = []
  if (form.tags.includes(tag)) { ElMessage.warning('标签已存在'); return }
  form.tags.push(tag)
  tagInput.value = ''
}

function removeTag(index) { form.tags.splice(index, 1) }

// 自动提取描述中的 #xxx 到标签数组,小红书标签上限 10
useAutoExtractHashtags({
  form,
  descKey: 'description',
  tagKey: 'tags',
  maxTags: 10,
})

defineExpose(publicApi)
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.xiaohongshu-image-publish-panel {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 12px;
}

.settings-row {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

@media (max-width: 1200px) {
  .settings-row {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 900px) {
  .settings-row {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 600px) {
  .settings-row {
    grid-template-columns: 1fr;
  }
}

.settings-row .setting-card {
  min-width: 0;
}

.xhs-warning {
  grid-column: 1 / -1;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 12px;
  background: rgba(245, 108, 108, 0.08);
  border: 1px solid rgba(245, 108, 108, 0.3);
  border-radius: 8px;
  color: #f56c6c;
  font-size: 13px;
  line-height: 1.6;
}

.xhs-warning .el-icon {
  flex-shrink: 0;
  margin-top: 2px;
}

.setting-card {
  border: 1px solid rgba($brand-start, 0.15);
  background: rgba($brand-start, 0.04);
  border-radius: 8px;
  padding: 16px;
}

.setting-label {
  font-size: 13px;
  font-weight: 600;
  color: #1769e8;
  margin-bottom: 8px;
}

.setting-hint {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 8px;
  line-height: 1.5;
}
</style>
