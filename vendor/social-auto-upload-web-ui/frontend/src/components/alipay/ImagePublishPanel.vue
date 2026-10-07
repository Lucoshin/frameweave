<template>
  <div class="alipay-image-publish-panel">
    <div v-if="accountId && hasAccountOverride(accountId)" style="margin-bottom: 12px;">
      <el-button size="small" @click="resetOverride">恢复为渠道默认</el-button>
    </div>

    <div class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">标题 <span class="required">*</span></div>
      <el-input v-model="form.title" placeholder="一个好的标题，能获得更多人的喜欢哦" maxlength="30" show-word-limit :disabled="disabled" />
    </div>

    <div class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">描述</div>
      <el-input v-model="form.description" type="textarea" :rows="5" placeholder="请输入描述..." maxlength="1000" show-word-limit :disabled="disabled" />
    </div>

    <div class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">标签</div>
      <div class="setting-hint">输入话题内容,按回车确认(发布时拼成 #话题1 #话题2)</div>
      <el-input v-model="tagInput" placeholder="输入话题内容,按回车添加" @keyup.enter="addTag" clearable :disabled="disabled" />
      <div v-if="form.tags && form.tags.length > 0" class="tags-list">
        <el-tag v-for="(tag, index) in form.tags" :key="index" closable @close="removeTag(index)" size="small" :disable-transitions="false">#{{ tag }}</el-tag>
      </div>
    </div>

    <div class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">音乐</div>
      <div class="setting-hint">请在支付宝真实投稿页面选择音乐。</div>
      <!-- 已选音乐展示 -->
      <div v-if="form.music && form.music.title" class="music-selected">
        <div class="music-cover-mini">
          <img v-if="form.music.coverUrl" :src="form.music.coverUrl" :alt="form.music.title" @error="onMusicImgError" />
          <el-icon v-else><Headset /></el-icon>
        </div>
        <span class="music-name">{{ form.music.title }}</span>
        <el-button text size="small" type="danger" @click="clearMusic" :disabled="disabled">移除</el-button>
      </div>
    </div>

    <div class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">作者声明</div>
      <div class="setting-hint">可选。选择作者声明</div>
      <div style="display: flex; gap: 8px; align-items: center;">
        <el-select v-model="form.authorStatement" placeholder="请选择作者声明（可选）" :disabled="disabled" clearable style="flex: 1;">
          <el-option label="内容由AI生成" value="内容由AI生成" />
        </el-select>
        <el-button v-if="form.authorStatement" text size="small" @click="form.authorStatement = ''" :disabled="disabled">清空</el-button>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Headset } from '@element-plus/icons-vue'
import { useChannelForm } from '@/composables/useChannelForm'
import { useAutoExtractHashtags } from '@/utils/hashtag'

const props = defineProps({
  accountId: { type: [Number, Object], default: null },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['config-changed'])

// 支付宝图集默认字段
const ALIPAY_DEFAULTS = {
  title: '',
  description: '',
  tags: [],
  music: null, // { musicId, title, coverUrl, audioUrl, duration }
  authorStatement: '',
}

const { form, hasAccountOverride, resetOverride, publicApi } = useChannelForm(
  ALIPAY_DEFAULTS,
  { props, emit },
  {
    validateFn: (accountId, merged) => {
      const errors = []
      if (!merged.title || !merged.title.trim()) {
        errors.push('请填写标题(≤30 字)')
      }
      return { valid: errors.length === 0, errors }
    },
  },
)

const tagInput = ref('')

function addTag() {
  const tag = tagInput.value.trim()
  if (!tag) return
  if (!form.tags) form.tags = []
  if (form.tags.includes(tag)) return
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

function clearMusic() {
  form.music = null
}

function onMusicImgError(e) {
  e.target.style.display = 'none'
}

defineExpose(publicApi)
</script>

<style scoped>
.alipay-image-publish-panel {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 12px;
}

.setting-card {
  border: 1px solid rgba($info-color, 0.15);
  background: rgba($info-color, 0.04);
  border-radius: 8px;
  padding: 16px;
}

.setting-label {
  font-size: 13px;
  font-weight: 600;
  color: #1677FF;
  margin-bottom: 8px;
}

.required {
  color: #f56c6c;
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

.music-selected {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: var(--bg-elevated);
  border: 1px solid rgba($info-color, 0.2);
  border-radius: 6px;
}

.music-cover-mini {
  width: 32px;
  height: 32px;
  border-radius: 4px;
  overflow: hidden;
  background: var(--bg-inset);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  flex-shrink: 0;
}

.music-cover-mini img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.music-name {
  flex: 1;
  font-size: 13px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
