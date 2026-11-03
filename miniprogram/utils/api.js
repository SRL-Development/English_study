// 后端基地址：部署后改成你的备案 HTTPS 域名（如 https://api.你的域名.com）
// 开发阶段可在微信开发者工具「不校验合法域名」下用局域网/公网地址调试。
const DEFAULT_BASE = 'https://englearner.cn';

let BASE = DEFAULT_BASE;
let TOKEN = '';

function setBase(b) {
  if (b) {
    BASE = String(b).replace(/\/+$/, '');
    wx.setStorageSync('apiBase', BASE);
  }
}
function setToken(t) {
  TOKEN = t || '';
}
function getBase() {
  return BASE;
}

function request(method, path, data) {
  return new Promise(function (resolve, reject) {
    wx.request({
      url: BASE + path,
      method: method,
      data: data,
      header: {
        'Content-Type': 'application/json',
        'Authorization': TOKEN ? ('Bearer ' + TOKEN) : ''
      },
      success: function (res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          var msg = (res.data && res.data.error) ? res.data.error : ('请求失败 ' + res.statusCode);
          reject(msg);
        }
      },
      fail: function (err) {
        reject(err.errMsg || '网络错误');
      }
    });
  });
}

function get(path) { return request('GET', path, null); }
function post(path, data) { return request('POST', path, data); }
function put(path, data) { return request('PUT', path, data); }

// 微信登录
function wxlogin(code) { return post('/api/wxlogin', { code: code }); }
// 绑定手机/邮箱
function bind(payload) { return post('/api/bind', payload); }
// 取/存云端进度
function getData() { return get('/api/data'); }
function putData(data) { return put('/api/data', { data: JSON.stringify(data) }); }
function me() { return get('/api/me'); }
function logout() { return post('/api/logout', {}); }

// TTS 音频地址（小程序用 InnerAudioContext 播放）
function ttsUrl(text, voice) {
  var v = voice || 'en-US-AriaNeural';
  return BASE + '/api/tts?text=' + encodeURIComponent(text) + '&voice=' + encodeURIComponent(v);
}

// 录音上传到讯飞纠音
function assess(text, filePath, category) {
  return new Promise(function (resolve, reject) {
    wx.uploadFile({
      url: BASE + '/assess',
      filePath: filePath,
      name: 'audio',
      formData: { text: text, category: category || 'read_sentence' },
      header: { 'Authorization': TOKEN ? ('Bearer ' + TOKEN) : '' },
      success: function (res) {
        try {
          resolve(JSON.parse(res.data));
        } catch (e) {
          reject('评测结果解析失败');
        }
      },
      fail: function (err) {
        reject(err.errMsg || '上传失败');
      }
    });
  });
}

module.exports = {
  setBase: setBase,
  setToken: setToken,
  getBase: getBase,
  get: get,
  post: post,
  put: put,
  wxlogin: wxlogin,
  bind: bind,
  getData: getData,
  putData: putData,
  me: me,
  logout: logout,
  ttsUrl: ttsUrl,
  assess: assess
};
