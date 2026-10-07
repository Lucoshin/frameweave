<template>
  <div class="weibo-image-publish-panel">
    <div v-if="accountId && hasAccountOverride(accountId)" style="margin-bottom: 12px;">
      <el-button size="small" @click="resetOverride">恢复为渠道默认</el-button>
    </div>

    <div class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">描述</div>
      <el-input v-model="form.description" type="textarea" :rows="5" placeholder="请输入微博正文..." maxlength="2000" show-word-limit :disabled="disabled" />
    </div>

    <div class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">标签</div>
      <div class="setting-hint">输入话题内容,按回车确认(微博图集会拼成 #话题1 #话题2)</div>
      <el-input v-model="tagInput" placeholder="输入话题内容,按回车添加" @keyup.enter="addTag" clearable :disabled="disabled" />
      <div v-if="form.tags && form.tags.length > 0" class="tags-list">
        <el-tag v-for="(tag, index) in form.tags" :key="index" closable @close="removeTag(index)" size="small" :disable-transitions="false">#{{ tag }}</el-tag>
      </div>
    </div>

    <div class="settings-row">
      <div class="setting-card" style="grid-column: 1 / -1">
        <div class="setting-label">内容声明</div>
        <el-select v-model="form.aiContent" placeholder="请选择" :disabled="disabled" style="width: 100%;">
          <el-option
            v-for="opt in statementOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { PLATFORMS } from '@/config/platforms'
import { useChannelForm } from '@/composables/useChannelForm'
import { useAutoExtractHashtags } from '@/utils/hashtag'

const props = defineProps({
  accountId: { type: [Number, Object], default: null },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['config-changed'])

// 内容声明 options 来自 settingsFields.contentStatement(不是 aiContent!)
const statementField = PLATFORMS.WEIBO.settingsFields.find(f => f.key === 'contentStatement')
const statementOptions = computed(() => statementField?.options || [])

const WEIBO_DEFAULTS = {
  title: '',
  description: '',
  tags: [],
  enableTimer: false,
  scheduleTime: '',
  aiContent: '',
  isOriginal: false,
}

const { form, hasAccountOverride, resetOverride, publicApi } = useChannelForm(
  WEIBO_DEFAULTS,
  { props, emit },
  {
    validateFn: () => ({ valid: true, errors: [] }),
  },
)

// 微博图集没有独立标题输入，草稿中的 title 与描述保持一致。
watch(() => form.description, (v) => { form.title = v || '' })

const tagInput = ref('')

function addTag() {
  const tag = tagInput.value.trim()
  if (!tag) return
  if (!form.tags) form.tags = []
  if (form.tags.includes(tag)) { ElMessage.warning('话题已存在'); return }
  form.tags.push(tag)
  tagInput.value = ''
}

function removeTag(index) { form.tags.splice(index, 1) }

// 自动提取描述中的 #xxx 到标签数组并随草稿保存。
useAutoExtractHashtags({
  form,
  descKey: 'description',
  tagKey: 'tags',
})

defineExpose(publicApi)
</script>

<style scoped>
.weibo-image-publish-panel {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 12px;
}

.settings-row {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
}

.settings-row .setting-card {
  min-width: 0;
}

.setting-card {
  border: 1px solid rgba($accent-rose, 0.15);
  background: rgba($accent-rose, 0.04);
  border-radius: 8px;
  padding: 16px;
}

.setting-label {
  font-size: 13px;
  font-weight: 600;
  color: #E6162D;
  margin-bottom: 8px;
}

.setting-hint {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 8px;
  line-height: 1.5;
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
</style>
