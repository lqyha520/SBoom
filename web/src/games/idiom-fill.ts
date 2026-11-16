import { contentDeck,rememberContent,validContentHistory,type ContentHistory } from './challenge-journey'
import { randomInt, shuffle, type Rng } from './random'

export type IdiomDifficulty = 'starter' | 'explorer' | 'master'

export interface IdiomSource {
  id: string
  text: string
  blank: number
  answer: string
  options: string[]
  pinyin: string
  meaning: string
}

export interface IdiomQuestion {
  idiomId: string
  options: string[]
}

export interface IdiomRound {
  version: 1
  difficulty: IdiomDifficulty
  questions: IdiomQuestion[]
  index: number
  correct: number
  mistakes: number
  answered: string | null
  finished: boolean
}

export interface IdiomSave extends ContentHistory {
  version: 1
  difficulty: IdiomDifficulty
  round: IdiomRound
  best: Record<IdiomDifficulty, number>
  totalCorrect: number
  rounds: number
}

export const IDIOM_QUESTIONS = 8

export const idiomDifficulties = [
  { id: 'starter' as const, name: '初识', detail: '常用成语', age: '6-8 岁' },
  { id: 'explorer' as const, name: '进阶', detail: '易混字形', age: '8-10 岁' },
  { id: 'master' as const, name: '挑战', detail: '高阶成语', age: '9-12 岁' },
]

const starterIdioms: IdiomSource[] = [
  { id: 'yixinyiyi', text: '一心一意', blank: 3, answer: '意', options: ['意', '义', '艺', '议'], pinyin: 'yī xīn yī yì', meaning: '形容心思专一，没有别的念头。' },
  { id: 'sanxineryi', text: '三心二意', blank: 2, answer: '二', options: ['二', '两', '再', '双'], pinyin: 'sān xīn èr yì', meaning: '形容犹豫不决，或心思不专一。' },
  { id: 'jingdizhiwa', text: '井底之蛙', blank: 3, answer: '蛙', options: ['蛙', '娃', '洼', '哇'], pinyin: 'jǐng dǐ zhī wā', meaning: '比喻见识狭窄的人。' },
  { id: 'huashetianzu', text: '画蛇添足', blank: 3, answer: '足', options: ['足', '走', '手', '竹'], pinyin: 'huà shé tiān zú', meaning: '比喻做了多余的事，反而不合适。' },
  { id: 'shouzhudaitu', text: '守株待兔', blank: 2, answer: '待', options: ['待', '侍', '持', '特'], pinyin: 'shǒu zhū dài tù', meaning: '比喻不主动努力，只想靠运气得到成果。' },
  { id: 'wangyangbulao', text: '亡羊补牢', blank: 2, answer: '补', options: ['补', '捕', '哺', '卜'], pinyin: 'wáng yáng bǔ láo', meaning: '比喻出了问题及时补救，还不算晚。' },
  { id: 'yanerdaoling', text: '掩耳盗铃', blank: 3, answer: '铃', options: ['铃', '玲', '岭', '领'], pinyin: 'yǎn ěr dào líng', meaning: '比喻自己欺骗自己，明明掩盖不住。' },
  { id: 'duiniutanqin', text: '对牛弹琴', blank: 3, answer: '琴', options: ['琴', '勤', '芹', '禽'], pinyin: 'duì niú tán qín', meaning: '比喻对不懂道理的人讲道理，白费口舌。' },
  { id: 'kezhouqiujian', text: '刻舟求剑', blank: 3, answer: '剑', options: ['剑', '箭', '建', '健'], pinyin: 'kè zhōu qiú jiàn', meaning: '比喻拘泥成法，不知道随情况变化。' },
  { id: 'hujiahuwei', text: '狐假虎威', blank: 3, answer: '威', options: ['威', '微', '危', '违'], pinyin: 'hú jiǎ hǔ wēi', meaning: '比喻依仗别人的势力来欺压人。' },
  {"id": "new-starter-1", "text": "一帆风顺", "pinyin": "yī fān fēng shùn", "meaning": "比喻事情进展顺利。", "blank": 1, "answer": "帆", "options": ["帆", "凡", "反", "返"]},
  {"id": "new-starter-2", "text": "五颜六色", "pinyin": "wǔ yán liù sè", "meaning": "形容颜色很多。", "blank": 1, "answer": "颜", "options": ["颜", "言", "炎", "严"]},
  {"id": "new-starter-3", "text": "七上八下", "pinyin": "qī shàng bā xià", "meaning": "形容心里慌乱、不安。", "blank": 2, "answer": "八", "options": ["八", "四", "九", "六"]},
  {"id": "new-starter-4", "text": "十全十美", "pinyin": "shí quán shí měi", "meaning": "形容十分完美。", "blank": 3, "answer": "美", "options": ["美", "米", "每", "妹"]},
  {"id": "new-starter-5", "text": "专心致志", "pinyin": "zhuān xīn zhì zhì", "meaning": "把心思集中在一件事情上。", "blank": 3, "answer": "志", "options": ["志", "智", "治", "至"]},
  {"id": "new-starter-6", "text": "全神贯注", "pinyin": "quán shén guàn zhù", "meaning": "把全部精神集中起来。", "blank": 2, "answer": "贯", "options": ["贯", "惯", "灌", "罐"]},
  {"id": "new-starter-7", "text": "自言自语", "pinyin": "zì yán zì yǔ", "meaning": "自己对自己说话。", "blank": 3, "answer": "语", "options": ["语", "雨", "宇", "羽"]},
  {"id": "new-starter-8", "text": "大惊小怪", "pinyin": "dà jīng xiǎo guài", "meaning": "对并不奇怪的事情过分惊讶。", "blank": 3, "answer": "怪", "options": ["怪", "快", "块", "筷"]},
  {"id": "new-starter-9", "text": "千方百计", "pinyin": "qiān fāng bǎi jì", "meaning": "想尽各种办法。", "blank": 3, "answer": "计", "options": ["计", "记", "际", "济"]},
  {"id": "new-starter-10", "text": "欢天喜地", "pinyin": "huān tiān xǐ dì", "meaning": "形容非常高兴。", "blank": 2, "answer": "喜", "options": ["喜", "洗", "细", "戏"]},
  {"id": "new-starter-11", "text": "山清水秀", "pinyin": "shān qīng shuǐ xiù", "meaning": "形容山水景色优美。", "blank": 1, "answer": "清", "options": ["清", "晴", "请", "情"]},
  {"id": "new-starter-12", "text": "鸟语花香", "pinyin": "niǎo yǔ huā xiāng", "meaning": "鸟鸣花香，形容春天的美好景色。", "blank": 1, "answer": "语", "options": ["语", "羽", "雨", "宇"]},
  {"id": "new-starter-13", "text": "春暖花开", "pinyin": "chūn nuǎn huā kāi", "meaning": "春天气候温暖，百花开放。", "blank": 1, "answer": "暖", "options": ["暖", "缓", "爱", "援"]},
  {"id": "new-starter-14", "text": "万里无云", "pinyin": "wàn lǐ wú yún", "meaning": "形容晴朗的天空。", "blank": 3, "answer": "云", "options": ["云", "运", "允", "耘"]},
  {"id": "new-starter-15", "text": "和风细雨", "pinyin": "hé fēng xì yǔ", "meaning": "温和的风和细小的雨，也比喻态度温和。", "blank": 2, "answer": "细", "options": ["细", "戏", "系", "希"]},
  {"id": "new-starter-16", "text": "百发百中", "pinyin": "bǎi fā bǎi zhòng", "meaning": "每次都击中目标，比喻很有把握。", "blank": 3, "answer": "中", "options": ["中", "忠", "钟", "终"]},
  {"id": "new-starter-17", "text": "东张西望", "pinyin": "dōng zhāng xī wàng", "meaning": "向四周看。", "blank": 3, "answer": "望", "options": ["望", "忘", "旺", "汪"]},
  {"id": "new-starter-18", "text": "手舞足蹈", "pinyin": "shǒu wǔ zú dǎo", "meaning": "形容高兴得舞动手脚。", "blank": 3, "answer": "蹈", "options": ["蹈", "道", "到", "倒"]},
  {"id": "new-starter-19", "text": "风和日丽", "pinyin": "fēng hé rì lì", "meaning": "风很温和，阳光明亮。", "blank": 3, "answer": "丽", "options": ["丽", "利", "力", "历"]},
  {"id": "new-starter-20", "text": "千山万水", "pinyin": "qiān shān wàn shuǐ", "meaning": "形容山水很多，路途遥远。", "blank": 1, "answer": "山", "options": ["山", "杉", "删", "衫"]},
  {"id": "new-starter-21", "text": "井井有条", "pinyin": "jǐng jǐng yǒu tiáo", "meaning": "形容安排整齐、有条理。", "blank": 3, "answer": "条", "options": ["条", "调", "挑", "跳"]},
  {"id": "new-starter-22", "text": "坐井观天", "pinyin": "zuò jǐng guān tiān", "meaning": "比喻眼界狭窄。", "blank": 2, "answer": "观", "options": ["观", "关", "官", "冠"]},
  {"id": "new-starter-23", "text": "画饼充饥", "pinyin": "huà bǐng chōng jī", "meaning": "比喻用空想来安慰自己。", "blank": 3, "answer": "饥", "options": ["饥", "机", "鸡", "积"]},
  {"id": "new-starter-24", "text": "愚公移山", "pinyin": "yú gōng yí shān", "meaning": "比喻坚持努力，不怕困难。", "blank": 2, "answer": "移", "options": ["移", "疑", "宜", "仪"]},
]

const explorerIdioms: IdiomSource[] = [
  { id: 'beigongsheying', text: '杯弓蛇影', blank: 3, answer: '影', options: ['影', '映', '应', '硬'], pinyin: 'bēi gōng shé yǐng', meaning: '比喻因疑神疑鬼而引起恐惧。' },
  { id: 'jinggongzhiniao', text: '惊弓之鸟', blank: 0, answer: '惊', options: ['惊', '京', '精', '经'], pinyin: 'jīng gōng zhī niǎo', meaning: '比喻受过惊吓，遇到类似情况就害怕的人。' },
  { id: 'wangmeizhike', text: '望梅止渴', blank: 3, answer: '渴', options: ['渴', '喝', '竭', '揭'], pinyin: 'wàng méi zhǐ kě', meaning: '比喻用空想来安慰自己。' },
  { id: 'pofuchenzhou', text: '破釜沉舟', blank: 1, answer: '釜', options: ['釜', '斧', '府', '辅'], pinyin: 'pò fǔ chén zhōu', meaning: '比喻下定决心，不顾一切干到底。' },
  { id: 'woxinchangdan', text: '卧薪尝胆', blank: 1, answer: '薪', options: ['薪', '新', '心', '欣'], pinyin: 'wò xīn cháng dǎn', meaning: '形容刻苦自励，发愤图强。' },
  { id: 'xuezhongsongtan', text: '雪中送炭', blank: 3, answer: '炭', options: ['炭', '碳', '汤', '烫'], pinyin: 'xuě zhōng sòng tàn', meaning: '比喻在别人急需时给予帮助。' },
  { id: 'jinshangtianhua', text: '锦上添花', blank: 2, answer: '添', options: ['添', '填', '甜', '忝'], pinyin: 'jǐn shàng tiān huā', meaning: '比喻使美好的事物更加美好。' },
  { id: 'xiongyouchengzhu', text: '胸有成竹', blank: 3, answer: '竹', options: ['竹', '足', '烛', '逐'], pinyin: 'xiōng yǒu chéng zhú', meaning: '比喻做事之前已经有充分的把握。' },
  { id: 'lanyuchongshu', text: '滥竽充数', blank: 1, answer: '竽', options: ['竽', '芋', '鱼', '于'], pinyin: 'làn yú chōng shù', meaning: '比喻没有真才实学的人混在行家里面充数。' },
  { id: 'hualongdianjing', text: '画龙点睛', blank: 3, answer: '睛', options: ['睛', '晴', '精', '请'], pinyin: 'huà lóng diǎn jīng', meaning: '比喻在关键处点明要旨，使内容更加生动。' },
  {"id": "new-explorer-1", "text": "自相矛盾", "pinyin": "zì xiāng máo dùn", "meaning": "自己的言行前后不一致。", "blank": 3, "answer": "盾", "options": ["盾", "吨", "顿", "遁"]},
  {"id": "new-explorer-2", "text": "盲人摸象", "pinyin": "máng rén mō xiàng", "meaning": "比喻只了解一部分就作出判断。", "blank": 2, "answer": "摸", "options": ["摸", "模", "磨", "摩"]},
  {"id": "new-explorer-3", "text": "叶公好龙", "pinyin": "yè gōng hào lóng", "meaning": "比喻口头爱好某事，实际并不喜欢。", "blank": 1, "answer": "公", "options": ["公", "工", "功", "攻"]},
  {"id": "new-explorer-4", "text": "鹬蚌相争", "pinyin": "yù bàng xiāng zhēng", "meaning": "比喻双方争执，让第三者得利。", "blank": 0, "answer": "鹬", "options": ["鹬", "玉", "鱼", "雨"]},
  {"id": "new-explorer-5", "text": "不耻下问", "pinyin": "bù chǐ xià wèn", "meaning": "不以向地位或学问不如自己的人请教为耻。", "blank": 1, "answer": "耻", "options": ["耻", "齿", "止", "尺"]},
  {"id": "new-explorer-6", "text": "勤学苦练", "pinyin": "qín xué kǔ liàn", "meaning": "认真学习，刻苦练习。", "blank": 0, "answer": "勤", "options": ["勤", "琴", "芹", "禽"]},
  {"id": "new-explorer-7", "text": "举一反三", "pinyin": "jǔ yī fǎn sān", "meaning": "从一件事推知其他同类事。", "blank": 2, "answer": "反", "options": ["反", "返", "饭", "范"]},
  {"id": "new-explorer-8", "text": "温故知新", "pinyin": "wēn gù zhī xīn", "meaning": "复习旧知识，得到新认识。", "blank": 1, "answer": "故", "options": ["故", "顾", "固", "姑"]},
  {"id": "new-explorer-9", "text": "实事求是", "pinyin": "shí shì qiú shì", "meaning": "根据实际情况作出正确判断。", "blank": 1, "answer": "事", "options": ["事", "市", "式", "世"]},
  {"id": "new-explorer-10", "text": "学以致用", "pinyin": "xué yǐ zhì yòng", "meaning": "把学到的知识用于实践。", "blank": 2, "answer": "致", "options": ["致", "至", "志", "制"]},
  {"id": "new-explorer-11", "text": "闻鸡起舞", "pinyin": "wén jī qǐ wǔ", "meaning": "比喻有志向的人及时奋发努力。", "blank": 0, "answer": "闻", "options": ["闻", "文", "纹", "蚊"]},
  {"id": "new-explorer-12", "text": "水滴石穿", "pinyin": "shuǐ dī shí chuān", "meaning": "比喻坚持不懈就能取得成果。", "blank": 3, "answer": "穿", "options": ["穿", "川", "串", "船"]},
  {"id": "new-explorer-13", "text": "金石为开", "pinyin": "jīn shí wéi kāi", "meaning": "比喻诚心能产生很大的力量。", "blank": 0, "answer": "金", "options": ["金", "今", "斤", "巾"]},
  {"id": "new-explorer-14", "text": "半途而废", "pinyin": "bàn tú ér fèi", "meaning": "事情没有完成就停止。", "blank": 1, "answer": "途", "options": ["途", "图", "徒", "涂"]},
  {"id": "new-explorer-15", "text": "坚持不懈", "pinyin": "jiān chí bù xiè", "meaning": "坚持到底，毫不松懈。", "blank": 3, "answer": "懈", "options": ["懈", "解", "械", "谢"]},
  {"id": "new-explorer-16", "text": "精益求精", "pinyin": "jīng yì qiú jīng", "meaning": "已经很好，还要求更好。", "blank": 1, "answer": "益", "options": ["益", "意", "义", "易"]},
  {"id": "new-explorer-17", "text": "因材施教", "pinyin": "yīn cái shī jiào", "meaning": "根据学习者的特点采用不同的教育方法。", "blank": 1, "answer": "材", "options": ["材", "才", "财", "裁"]},
  {"id": "new-explorer-18", "text": "聚精会神", "pinyin": "jù jīng huì shén", "meaning": "集中精神，专心致志。", "blank": 0, "answer": "聚", "options": ["聚", "具", "俱", "距"]},
  {"id": "new-explorer-19", "text": "目不转睛", "pinyin": "mù bù zhuǎn jīng", "meaning": "眼睛一直盯着看，形容非常专注。", "blank": 3, "answer": "睛", "options": ["睛", "晴", "情", "请"]},
  {"id": "new-explorer-20", "text": "津津有味", "pinyin": "jīn jīn yǒu wèi", "meaning": "形容兴味浓厚。", "blank": 0, "answer": "津", "options": ["津", "今", "斤", "金"]},
  {"id": "new-explorer-21", "text": "妙笔生花", "pinyin": "miào bǐ shēng huā", "meaning": "比喻文章写得精彩。", "blank": 0, "answer": "妙", "options": ["妙", "秒", "苗", "描"]},
  {"id": "new-explorer-22", "text": "点石成金", "pinyin": "diǎn shí chéng jīn", "meaning": "比喻把不好的文字修改得很好。", "blank": 1, "answer": "石", "options": ["石", "十", "时", "识"]},
  {"id": "new-explorer-23", "text": "引人入胜", "pinyin": "yǐn rén rù shèng", "meaning": "吸引人进入美好的境界。", "blank": 3, "answer": "胜", "options": ["胜", "盛", "圣", "剩"]},
  {"id": "new-explorer-24", "text": "迫不及待", "pinyin": "pò bù jí dài", "meaning": "急切得不能再等待。", "blank": 3, "answer": "待", "options": ["待", "侍", "持", "特"]},
]

const masterIdioms: IdiomSource[] = [
  { id: 'yiguzuoqi', text: '一鼓作气', blank: 1, answer: '鼓', options: ['鼓', '股', '古', '故'], pinyin: 'yī gǔ zuò qì', meaning: '比喻趁劲头大的时候，一口气把事情做完。' },
  { id: 'nanyuanbeizhe', text: '南辕北辙', blank: 3, answer: '辙', options: ['辙', '撤', '澈', '彻'], pinyin: 'nán yuán běi zhé', meaning: '比喻行动和目的正好相反。' },
  { id: 'shirupozhu', text: '势如破竹', blank: 0, answer: '势', options: ['势', '事', '是', '世'], pinyin: 'shì rú pò zhú', meaning: '形容节节胜利，毫无阻碍。' },
  { id: 'chuleibacui', text: '出类拔萃', blank: 3, answer: '萃', options: ['萃', '碎', '翠', '粹'], pinyin: 'chū lèi bá cuì', meaning: '形容超出同类之上，非常优秀。' },
  { id: 'luoyibujue', text: '络绎不绝', blank: 1, answer: '绎', options: ['绎', '译', '择', '驿'], pinyin: 'luò yì bù jué', meaning: '形容行人车马来来往往，接连不断。' },
  { id: 'xiangfuxiangcheng', text: '相辅相成', blank: 1, answer: '辅', options: ['辅', '捕', '补', '浦'], pinyin: 'xiāng fǔ xiāng chéng', meaning: '指两件事物互相补充、互相配合。' },
  { id: 'biechuxincai', text: '别出心裁', blank: 3, answer: '裁', options: ['裁', '载', '栽', '哉'], pinyin: 'bié chū xīn cái', meaning: '形容独创一格，与众不同。' },
  { id: 'xuxurushing', text: '栩栩如生', blank: 0, answer: '栩', options: ['栩', '许', '羽', '诩'], pinyin: 'xǔ xǔ rú shēng', meaning: '形容形象生动逼真，像活的一样。' },
  { id: 'kuaizhirenkou', text: '脍炙人口', blank: 1, answer: '炙', options: ['炙', '灸', '治', '质'], pinyin: 'kuài zhì rén kǒu', meaning: '比喻好的诗文或事物受到人们称赞。' },
  { id: 'yimingjingren', text: '一鸣惊人', blank: 1, answer: '鸣', options: ['鸣', '名', '明', '命'], pinyin: 'yī míng jīng rén', meaning: '比喻平时没有突出表现，一下子做出惊人的成绩。' },
  {"id": "new-master-1", "text": "锲而不舍", "pinyin": "qiè ér bù shě", "meaning": "不断雕刻，比喻坚持到底。", "blank": 0, "answer": "锲", "options": ["锲", "切", "契", "砌"]},
  {"id": "new-master-2", "text": "孜孜不倦", "pinyin": "zī zī bù juàn", "meaning": "勤奋努力，不知疲倦。", "blank": 3, "answer": "倦", "options": ["倦", "卷", "眷", "券"]},
  {"id": "new-master-3", "text": "持之以恒", "pinyin": "chí zhī yǐ héng", "meaning": "长久地坚持下去。", "blank": 3, "answer": "恒", "options": ["恒", "衡", "横", "桓"]},
  {"id": "new-master-4", "text": "融会贯通", "pinyin": "róng huì guàn tōng", "meaning": "把各方面知识联系起来，得到完整理解。", "blank": 2, "answer": "贯", "options": ["贯", "惯", "灌", "罐"]},
  {"id": "new-master-5", "text": "触类旁通", "pinyin": "chù lèi páng tōng", "meaning": "了解一类事物后，推知其他类似事物。", "blank": 2, "answer": "旁", "options": ["旁", "傍", "膀", "磅"]},
  {"id": "new-master-6", "text": "博采众长", "pinyin": "bó cǎi zhòng cháng", "meaning": "广泛吸取各方面的长处。", "blank": 1, "answer": "采", "options": ["采", "彩", "踩", "睬"]},
  {"id": "new-master-7", "text": "循序渐进", "pinyin": "xún xù jiàn jìn", "meaning": "按照步骤逐渐深入。", "blank": 0, "answer": "循", "options": ["循", "寻", "询", "巡"]},
  {"id": "new-master-8", "text": "举足轻重", "pinyin": "jǔ zú qīng zhòng", "meaning": "形容地位重要，能影响全局。", "blank": 2, "answer": "轻", "options": ["轻", "清", "青", "倾"]},
  {"id": "new-master-9", "text": "运筹帷幄", "pinyin": "yùn chóu wéi wò", "meaning": "在后方谋划，指筹划和指挥。", "blank": 2, "answer": "帷", "options": ["帷", "维", "唯", "围"]},
  {"id": "new-master-10", "text": "深思熟虑", "pinyin": "shēn sī shú lǜ", "meaning": "深入、周密地思考。", "blank": 3, "answer": "虑", "options": ["虑", "滤", "绿", "率"]},
  {"id": "new-master-11", "text": "高瞻远瞩", "pinyin": "gāo zhān yuǎn zhǔ", "meaning": "看得高远，形容目光远大。", "blank": 3, "answer": "瞩", "options": ["瞩", "嘱", "属", "煮"]},
  {"id": "new-master-12", "text": "未雨绸缪", "pinyin": "wèi yǔ chóu móu", "meaning": "事先做好准备。", "blank": 2, "answer": "绸", "options": ["绸", "稠", "愁", "筹"]},
  {"id": "new-master-13", "text": "居安思危", "pinyin": "jū ān sī wēi", "meaning": "处于安全环境也想到可能的危险。", "blank": 0, "answer": "居", "options": ["居", "俱", "具", "据"]},
  {"id": "new-master-14", "text": "随机应变", "pinyin": "suí jī yìng biàn", "meaning": "随着情况变化灵活应对。", "blank": 2, "answer": "应", "options": ["应", "映", "影", "迎"]},
  {"id": "new-master-15", "text": "见微知著", "pinyin": "jiàn wēi zhī zhù", "meaning": "从细小迹象看出事物的发展。", "blank": 3, "answer": "著", "options": ["著", "着", "住", "注"]},
  {"id": "new-master-16", "text": "厚积薄发", "pinyin": "hòu jī bó fā", "meaning": "充分积累，谨慎地表现出来。", "blank": 0, "answer": "厚", "options": ["厚", "后", "候", "侯"]},
  {"id": "new-master-17", "text": "学富五车", "pinyin": "xué fù wǔ chē", "meaning": "形容读书很多、学问丰富。", "blank": 1, "answer": "富", "options": ["富", "副", "付", "负"]},
  {"id": "new-master-18", "text": "才华横溢", "pinyin": "cái huá héng yì", "meaning": "才能充分显露。", "blank": 3, "answer": "溢", "options": ["溢", "益", "意", "谊"]},
  {"id": "new-master-19", "text": "文质彬彬", "pinyin": "wén zhì bīn bīn", "meaning": "形容举止文雅、有礼貌。", "blank": 2, "answer": "彬", "options": ["彬", "斌", "宾", "滨"]},
  {"id": "new-master-20", "text": "豁然开朗", "pinyin": "huò rán kāi lǎng", "meaning": "突然变得开阔明亮，也比喻突然领悟。", "blank": 0, "answer": "豁", "options": ["豁", "或", "获", "惑"]},
  {"id": "new-master-21", "text": "顿开茅塞", "pinyin": "dùn kāi máo sè", "meaning": "比喻忽然理解，思路畅通。", "blank": 2, "answer": "茅", "options": ["茅", "矛", "毛", "茂"]},
  {"id": "new-master-22", "text": "不言而喻", "pinyin": "bù yán ér yù", "meaning": "不用说明就能明白。", "blank": 3, "answer": "喻", "options": ["喻", "愉", "渝", "榆"]},
  {"id": "new-master-23", "text": "相得益彰", "pinyin": "xiāng dé yì zhāng", "meaning": "互相配合，使长处更加显现。", "blank": 3, "answer": "彰", "options": ["彰", "章", "张", "障"]},
  {"id": "new-master-24", "text": "水到渠成", "pinyin": "shuǐ dào qú chéng", "meaning": "条件成熟，事情自然成功。", "blank": 2, "answer": "渠", "options": ["渠", "取", "曲", "屈"]},
]

export const idiomPools: Record<IdiomDifficulty, IdiomSource[]> = {
  starter: starterIdioms,
  explorer: explorerIdioms,
  master: masterIdioms,
}

export function isIdiomDifficulty(value: unknown): value is IdiomDifficulty {
  return value === 'starter' || value === 'explorer' || value === 'master'
}

export function idiomById(difficulty: IdiomDifficulty, id: string): IdiomSource | undefined {
  return idiomPools[difficulty].find(item => item.id === id)
}

export function newIdiomRound(difficulty: IdiomDifficulty, rng: Rng = Math.random, history: string[] = []): IdiomRound {
  const pool = [...idiomPools[difficulty]]
  const selected=contentDeck(idiomPools[difficulty],IDIOM_QUESTIONS,item=>item.id,history,rng)
  const used = new Set(idiomPools[difficulty].filter(item=>!selected.includes(item)).map(item=>item.id))
  const questions: IdiomQuestion[] = []
  for (let index = 0; index < IDIOM_QUESTIONS; index++) {
    const available = pool.filter(item => !used.has(item.id))
    const item = available[randomInt(rng, 0, available.length - 1)]
    used.add(item.id)
    questions.push({ idiomId: item.id, options: shuffle(item.options, rng) })
  }
  return {
    version: 1,
    difficulty,
    questions,
    index: 0,
    correct: 0,
    mistakes: 0,
    answered: null,
    finished: false,
  }
}

export function newIdiom(difficulty: IdiomDifficulty = 'starter', rng: Rng = Math.random): IdiomSave {
  return {
    version: 1,
    difficulty,
    round: newIdiomRound(difficulty, rng),
    best: { starter: 0, explorer: 0, master: 0 },
    totalCorrect: 0,
    rounds: 0,
  }
}

export function idiomStars(round: Pick<IdiomRound, 'mistakes'>): number {
  return round.mistakes === 0 ? 3 : round.mistakes === 1 ? 2 : 1
}

export function answerIdiom(save: IdiomSave, char: string): boolean | null {
  const round = save.round
  if (round.finished || round.answered !== null) return null
  const question = round.questions[round.index]
  if (!question.options.includes(char)) return null
  const source = idiomById(round.difficulty, question.idiomId)
  if (!source) return null
  round.answered = char
  if (char === source.answer) round.correct++
  else round.mistakes++
  return char === source.answer
}

export function advanceIdiom(save: IdiomSave): 'next' | 'finished' | null {
  const round = save.round
  if (round.finished || round.answered === null) return null
  if (round.index < IDIOM_QUESTIONS - 1) {
    round.index++
    round.answered = null
    return 'next'
  }
  round.finished = true
  round.answered = null
  save.best[round.difficulty] = Math.max(save.best[round.difficulty], idiomStars(round))
  save.totalCorrect += round.correct
  save.rounds++
  return 'finished'
}

export function restartIdiom(save: IdiomSave, rng: Rng = Math.random): void {
  const history=rememberContent(save,save.difficulty,save.round.questions.map(question=>question.idiomId))
  save.round = newIdiomRound(save.difficulty, rng,history)
}

export function switchIdiomDifficulty(save: IdiomSave, difficulty: IdiomDifficulty, rng: Rng = Math.random): void {
  rememberContent(save,save.difficulty,save.round.questions.map(question=>question.idiomId))
  save.difficulty = difficulty
  save.round = newIdiomRound(difficulty, rng,save.contentHistory?.[difficulty] || [])
}

function isInt(value: unknown, min: number, max: number): value is number {
  return Number.isSafeInteger(value) && Number(value) >= min && Number(value) <= max
}

function validQuestion(question: IdiomQuestion, difficulty: IdiomDifficulty): boolean {
  const source = idiomById(difficulty, question?.idiomId)
  if (!source) return false
  if (!Array.isArray(question.options) || question.options.length !== 4) return false
  if (!question.options.every(char => typeof char === 'string')) return false
  if (new Set(question.options).size !== 4) return false
  return question.options.every(char => source.options.includes(char)) && question.options.includes(source.answer)
}

export function restoreIdiom(raw: string | null): IdiomSave | null {
  if (!raw) return null
  try {
    const value = JSON.parse(raw) as IdiomSave
    if (!value || !validContentHistory(value.contentHistory) || value.version !== 1 || !isIdiomDifficulty(value.difficulty)) return null
    const best = value.best as unknown as Record<string, unknown>
    if (!best || !idiomDifficulties.every(item => isInt(best[item.id], 0, 3))) return null
    if (!isInt(value.totalCorrect, 0, 1_000_000) || !isInt(value.rounds, 0, 1_000_000)) return null
    const round = value.round
    if (!round || round.version !== 1 || round.difficulty !== value.difficulty) return null
    if (!Array.isArray(round.questions) || round.questions.length !== IDIOM_QUESTIONS) return null
    if (!round.questions.every(question => validQuestion(question, value.difficulty))) return null
    if (new Set(round.questions.map(question => question.idiomId)).size !== IDIOM_QUESTIONS) return null
    if (!isInt(round.index, 0, IDIOM_QUESTIONS - 1) || typeof round.finished !== 'boolean') return null
    if (!isInt(round.correct, 0, IDIOM_QUESTIONS) || !isInt(round.mistakes, 0, IDIOM_QUESTIONS)) return null
    const question = round.questions[round.index]
    if (round.answered !== null && (typeof round.answered !== 'string' || !question.options.includes(round.answered))) return null
    if (!round.finished) {
      const answeredCount = round.index + (round.answered === null ? 0 : 1)
      if (round.correct + round.mistakes !== answeredCount) return null
    }
    if (round.finished) {
      if (round.index !== IDIOM_QUESTIONS - 1 || round.answered !== null) return null
      if (round.correct + round.mistakes !== IDIOM_QUESTIONS) return null
      if ((best[value.difficulty] as number) < idiomStars(round)) return null
    }
    return value
  } catch {
    return null
  }
}
