export type EnglishTier = 'starter' | 'explorer' | 'master'

export interface EnglishWord {
  word: string
  meaning: string
  emoji: string
}

export const englishDifficulties = [
  { id: 'starter' as const, name: '启蒙', detail: '3-4 个字母', age: '6-8 岁' },
  { id: 'explorer' as const, name: '进阶', detail: '5-6 个字母', age: '7-9 岁' },
  { id: 'master' as const, name: '挑战', detail: '8-10 个字母', age: '8-11 岁' },
]

export const englishWords: Record<EnglishTier, EnglishWord[]> = {
  starter: [
    { word: 'cat', meaning: '猫', emoji: '🐱' },
    { word: 'dog', meaning: '狗', emoji: '🐶' },
    { word: 'sun', meaning: '太阳', emoji: '☀️' },
    { word: 'red', meaning: '红色', emoji: '🔴' },
    { word: 'book', meaning: '书', emoji: '📕' },
    { word: 'milk', meaning: '牛奶', emoji: '🥛' },
    { word: 'fish', meaning: '鱼', emoji: '🐟' },
    { word: 'bird', meaning: '鸟', emoji: '🐦' },
    { word: 'cake', meaning: '蛋糕', emoji: '🍰' },
    { word: 'ball', meaning: '球', emoji: '⚽' },
  ],
  explorer: [
    { word: 'apple', meaning: '苹果', emoji: '🍎' },
    { word: 'rabbit', meaning: '兔子', emoji: '🐰' },
    { word: 'orange', meaning: '橙子', emoji: '🍊' },
    { word: 'flower', meaning: '花', emoji: '🌸' },
    { word: 'school', meaning: '学校', emoji: '🏫' },
    { word: 'pencil', meaning: '铅笔', emoji: '✏️' },
    { word: 'monkey', meaning: '猴子', emoji: '🐵' },
    { word: 'garden', meaning: '花园', emoji: '🌷' },
    { word: 'rocket', meaning: '火箭', emoji: '🚀' },
    { word: 'turtle', meaning: '乌龟', emoji: '🐢' },
  ],
  master: [
    { word: 'elephant', meaning: '大象', emoji: '🐘' },
    { word: 'birthday', meaning: '生日', emoji: '🎂' },
    { word: 'dinosaur', meaning: '恐龙', emoji: '🦖' },
    { word: 'umbrella', meaning: '雨伞', emoji: '☂️' },
    { word: 'butterfly', meaning: '蝴蝶', emoji: '🦋' },
    { word: 'chocolate', meaning: '巧克力', emoji: '🍫' },
    { word: 'strawberry', meaning: '草莓', emoji: '🍓' },
    { word: 'hospital', meaning: '医院', emoji: '🏥' },
    { word: 'mountain', meaning: '山', emoji: '⛰️' },
    { word: 'computer', meaning: '电脑', emoji: '💻' },
  ],
}

export function isEnglishTier(value: unknown): value is EnglishTier {
  return value === 'starter' || value === 'explorer' || value === 'master'
}

export function englishWord(tier: EnglishTier, word: string): EnglishWord | undefined {
  return englishWords[tier].find(item => item.word === word)
}
