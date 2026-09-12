/**
 * 题型中文名映射（管理端展示用）。
 * 与工作台 web/src/constants.ts 的 TYPE_NAME 保持同值——admin 是独立构建的
 * 应用无法共享模块，改这里时请同步改工作台那份（或反过来），两边互为镜像。
 */
export const TYPE_NAME: Record<string, string> = {
  quiz: '选择题',
  fill_blank: '填空题',
  match_pair: '连线配对',
  challenge: '闯关挑战',
  oral_math: '口算题',
  reading: '阅读理解',
  vertical_calc: '竖式计算',
  recursive_calc: '脱式计算',
  smart_calc: '简便计算',
  number_split: '数的分成',
  compare: '比大小',
  true_false: '判断题',
  word_problem: '应用题',
}
