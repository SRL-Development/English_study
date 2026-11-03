const api = require('./utils/api.js');

App({
  globalData: {
    token: '',
    baseUrl: ''
  },
  onLaunch() {
    const token = wx.getStorageSync('token') || '';
    const base = wx.getStorageSync('apiBase') || '';
    this.globalData.token = token;
    this.globalData.baseUrl = base;
    api.setBase(base);
    api.setToken(token);
  }
});
