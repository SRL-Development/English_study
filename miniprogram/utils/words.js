// 内置 starter 词库（小程序端独立维护，可后续扩充/接入后端词库）
// level: 0 零基础 / 1 初中 / 2 高中 / 3 大学
// scene: 日常交流 / 商务洽谈 / 工程技术 / IT / 医疗 / 金融
const ALL = [
  // 零基础 · 日常交流
  { word: 'hello', phonetic: '/həˈloʊ/', meaning: '你好', example: 'Hello, how are you today?', level: 0, scene: '日常交流' },
  { word: 'thanks', phonetic: '/θæŋks/', meaning: '谢谢', example: 'Thanks for your help.', level: 0, scene: '日常交流' },
  { word: 'sorry', phonetic: '/ˈsɒri/', meaning: '对不起', example: 'I am sorry to hear that.', level: 0, scene: '日常交流' },
  { word: 'please', phonetic: '/pliːz/', meaning: '请', example: 'Please sit down.', level: 0, scene: '日常交流' },
  { word: 'goodbye', phonetic: '/ɡʊdˈbaɪ/', meaning: '再见', example: 'Goodbye, see you tomorrow.', level: 0, scene: '日常交流' },
  // 零基础 · 商务洽谈
  { word: 'meeting', phonetic: '/ˈmiːtɪŋ/', meaning: '会议', example: 'We have a meeting at 3 p.m.', level: 0, scene: '商务洽谈' },
  { word: 'price', phonetic: '/praɪs/', meaning: '价格', example: 'What is the price?', level: 0, scene: '商务洽谈' },
  { word: 'order', phonetic: '/ˈɔːdə/', meaning: '订单', example: 'I would like to place an order.', level: 0, scene: '商务洽谈' },

  // 初中 · 日常交流
  { word: 'weather', phonetic: '/ˈweðə/', meaning: '天气', example: 'The weather is nice today.', level: 1, scene: '日常交流' },
  { word: 'family', phonetic: '/ˈfæməli/', meaning: '家庭', example: 'I love my family.', level: 1, scene: '日常交流' },
  { word: 'friend', phonetic: '/frend/', meaning: '朋友', example: 'She is my best friend.', level: 1, scene: '日常交流' },
  { word: 'school', phonetic: '/skuːl/', meaning: '学校', example: 'The school is near my home.', level: 1, scene: '日常交流' },
  // 初中 · 商务洽谈
  { word: 'email', phonetic: '/ˈiːmeɪl/', meaning: '邮件', example: 'Please send me an email.', level: 1, scene: '商务洽谈' },
  { word: 'schedule', phonetic: '/ˈʃedjuːl/', meaning: '日程', example: 'Let us check the schedule.', level: 1, scene: '商务洽谈' },
  { word: 'report', phonetic: '/rɪˈpɔːt/', meaning: '报告', example: 'He wrote a weekly report.', level: 1, scene: '商务洽谈' },
  // 初中 · 工程技术
  { word: 'machine', phonetic: '/məˈʃiːn/', meaning: '机器', example: 'The machine is running.', level: 1, scene: '工程技术' },
  { word: 'power', phonetic: '/ˈpaʊə/', meaning: '电力', example: 'The power is off.', level: 1, scene: '工程技术' },
  { word: 'repair', phonetic: '/rɪˈpeə/', meaning: '维修', example: 'We need to repair the pump.', level: 1, scene: '工程技术' },
  // 初中 · IT
  { word: 'computer', phonetic: '/kəmˈpjuːtə/', meaning: '电脑', example: 'The computer is slow.', level: 1, scene: 'IT' },
  { word: 'network', phonetic: '/ˈnetwɜːk/', meaning: '网络', example: 'The network is down.', level: 1, scene: 'IT' },
  { word: 'password', phonetic: '/ˈpɑːswɜːd/', meaning: '密码', example: 'Change your password often.', level: 1, scene: 'IT' },

  // 高中 · 日常交流
  { word: 'environment', phonetic: '/ɪnˈvaɪrənmənt/', meaning: '环境', example: 'We must protect the environment.', level: 2, scene: '日常交流' },
  { word: 'community', phonetic: '/kəˈmjuːnəti/', meaning: '社区', example: 'Our community is friendly.', level: 2, scene: '日常交流' },
  // 高中 · IT
  { word: 'algorithm', phonetic: '/ˈælɡərɪðəm/', meaning: '算法', example: 'This algorithm is efficient.', level: 2, scene: 'IT' },
  { word: 'server', phonetic: '/ˈsɜːvə/', meaning: '服务器', example: 'The server crashed last night.', level: 2, scene: 'IT' },
  { word: 'security', phonetic: '/sɪˈkjʊərəti/', meaning: '安全', example: 'Security is very important.', level: 2, scene: 'IT' },
  // 高中 · 医疗
  { word: 'symptom', phonetic: '/ˈsɪmptəm/', meaning: '症状', example: 'What is the main symptom?', level: 2, scene: '医疗' },
  { word: 'patient', phonetic: '/ˈpeɪʃnt/', meaning: '病人', example: 'The patient is stable.', level: 2, scene: '医疗' },
  { word: 'treatment', phonetic: '/ˈtriːtmənt/', meaning: '治疗', example: 'The treatment works well.', level: 2, scene: '医疗' },
  // 高中 · 金融
  { word: 'investment', phonetic: '/ɪnˈvestmənt/', meaning: '投资', example: 'Investment carries risk.', level: 2, scene: '金融' },
  { word: 'currency', phonetic: '/ˈkʌrənsi/', meaning: '货币', example: 'The currency is strong.', level: 2, scene: '金融' },
  { word: 'risk', phonetic: '/rɪsk/', meaning: '风险', example: 'We must manage the risk.', level: 2, scene: '金融' },

  // 大学 · 工程技术
  { word: 'voltage', phonetic: '/ˈvəʊltɪdʒ/', meaning: '电压', example: 'Measure the voltage carefully.', level: 3, scene: '工程技术' },
  { word: 'tolerance', phonetic: '/ˈtɒlərəns/', meaning: '公差', example: 'The tolerance is tight.', level: 3, scene: '工程技术' },
  // 大学 · IT
  { word: 'latency', phonetic: '/ˈleɪtənsi/', meaning: '延迟', example: 'Reduce the network latency.', level: 3, scene: 'IT' },
  { word: 'encryption', phonetic: '/ɪnˈkrɪpʃn/', meaning: '加密', example: 'Use encryption for data.', level: 3, scene: 'IT' },
  // 大学 · 医疗
  { word: 'diagnosis', phonetic: '/ˌdaɪəɡˈnəʊsɪs/', meaning: '诊断', example: 'The diagnosis is clear.', level: 3, scene: '医疗' },
  { word: 'clinical', phonetic: '/ˈklɪnɪkl/', meaning: '临床的', example: 'Clinical trials are ongoing.', level: 3, scene: '医疗' },
  // 大学 · 金融
  { word: 'liquidity', phonetic: '/lɪˈkwɪdəti/', meaning: '流动性', example: 'Liquidity is sufficient.', level: 3, scene: '金融' },
  { word: 'portfolio', phonetic: '/pɔːtˈfəʊliəʊ/', meaning: '投资组合', example: 'Diversify your portfolio.', level: 3, scene: '金融' },
  // 大学 · 商务洽谈
  { word: 'compliance', phonetic: '/kəmˈplaɪəns/', meaning: '合规', example: 'Compliance is required.', level: 3, scene: '商务洽谈' },
  { word: 'leverage', phonetic: '/ˈliːvərɪdʒ/', meaning: '杠杆', example: 'Use leverage with caution.', level: 3, scene: '商务洽谈' }
];

function filter(level, scene) {
  return ALL.filter(function (w) {
    return w.level === level && w.scene === scene;
  });
}

// 若指定场景没有词，回退到该阶段“日常交流”
function pick(level, scene) {
  var list = filter(level, scene);
  if (!list.length) {
    list = filter(level, '日常交流');
  }
  if (!list.length) {
    list = filter(1, '日常交流');
  }
  return list;
}

module.exports = {
  ALL: ALL,
  filter: filter,
  pick: pick
};
